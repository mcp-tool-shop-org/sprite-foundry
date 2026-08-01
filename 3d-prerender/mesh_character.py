import os, time, sys, inspect, argparse
os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
from pathlib import Path
import config

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--ptype', default='512', help="pipeline_type: 512 | 1024 | 1024_cascade | 1536_cascade")
    ap.add_argument('--decimation', type=int, default=1000000)
    ap.add_argument('--texture', type=int, default=4096)
    ap.add_argument('--remesh', type=int, default=1, help="1=True (smoke-test baseline), 0=False (thin-feature)")
    ap.add_argument('--remesh_project', type=int, default=0)
    ap.add_argument('--probe', type=int, default=0, help="1 = load + print API, do NOT run")
    ap.add_argument('--bake', default='clean', choices=['clean', 'ovoxel'],
                    help="clean = our licence-clean bake (default). ovoxel = the old "
                         "o_voxel.postprocess.to_glb path, which loads nvdiffrast "
                         "(NVIDIA Source Code License: research/evaluation only). "
                         "Kept ONLY as the comparison oracle -- never for shipped assets.")
    ap.add_argument('--bake-compare', type=int, default=0,
                    help="1 = bake BOTH ways from one mesh generation and report the "
                         "difference. Writes <out> and <out>.ovoxel.glb.")
    ap.add_argument('--licence-strict', type=int, default=0,
                    help="1 = exit non-zero if non-commercially-licensed code (nvdiffrast) "
                         "was loaded on a run that claimed to be licence-clean.")
    args = ap.parse_args()

    # validate BEFORE the expensive GPU pipeline load: fail in milliseconds, not minutes
    img_path = Path(args.image)
    if not img_path.exists():
        print(f"ERROR: --image not found: {img_path}", flush=True)
        sys.exit(1)
    try:
        from PIL import Image
        with Image.open(img_path) as _probe_img:
            _probe_img.verify()
    except Exception as e:
        print(f"ERROR: --image is not a valid/openable image ({img_path}): {e}", flush=True)
        sys.exit(1)

    import torch
    from PIL import Image
    # The guard MUST be installed before trellis2 is imported. Loading the pipeline pulls
    # o_voxel in via the shape VAE (trellis2/models/sc_vaes/fdg_vae.py -> o_voxel.convert),
    # and o_voxel/__init__.py eagerly imports .postprocess -> nvdiffrast. Nothing on the
    # generation path uses nvdiffrast; it just gets dragged along. Blocking the import is
    # what actually keeps NVIDIA's non-commercial code out of the process.
    want_ovoxel = args.bake == 'ovoxel' or args.bake_compare
    import licence_guard
    if not want_ovoxel:
        licence_guard.block_noncommercial()

    from trellis2.pipelines import Trellis2ImageTo3DPipeline
    import bake_glb

    if want_ovoxel:
        import o_voxel
        print("WARNING: loading o_voxel/nvdiffrast (non-commercial licence). "
              "Comparison/evaluation only -- do not ship assets from this path.", flush=True)

    t0 = time.time()
    print(f"=== mesh run: image={args.image} ptype={args.ptype} remesh={bool(args.remesh)} decim={args.decimation} ===", flush=True)
    print(f"loading {config.TRELLIS_MODEL_ID} (+ dinov3) ...", flush=True)
    pipe = Trellis2ImageTo3DPipeline.from_pretrained(config.TRELLIS_MODEL_ID)
    pipe.cuda()
    print(f"[load] {time.time()-t0:.0f}s | VRAM now {torch.cuda.memory_allocated()/1e9:.1f} GB", flush=True)

    # --- API ground truth (settles the default-resolution question) ---
    try:
        print("run() signature:", inspect.signature(pipe.run), flush=True)
    except Exception as e:
        print("signature introspection failed:", e, flush=True)
    for attr in ('default_pipeline_type', 'pipeline_type', 'available_pipeline_types', 'pipeline_types'):
        if hasattr(pipe, attr):
            print(f"  pipe.{attr} = {getattr(pipe, attr)!r}", flush=True)
    if args.probe:
        print("PROBE ONLY — exiting before run", flush=True)
        sys.exit(0)

    img = Image.open(args.image)
    torch.cuda.reset_peak_memory_stats()
    t1 = time.time()
    print(f"running image -> 3D (pipeline_type={args.ptype}) ...", flush=True)
    try:
        mesh = pipe.run(img, pipeline_type=args.ptype)[0]
        torch.cuda.synchronize()
        gen_peak = torch.cuda.max_memory_allocated()/1e9
        print(f"[mesh] {time.time()-t1:.0f}s | GEN PEAK {gen_peak:.1f} GB | verts {len(mesh.vertices)} faces {len(mesh.faces)}", flush=True)

        mesh.simplify(16777216)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        t2 = time.time()
        bake_kwargs = dict(
            vertices=mesh.vertices, faces=mesh.faces, attr_volume=mesh.attrs,
            coords=mesh.coords, attr_layout=mesh.layout, voxel_size=mesh.voxel_size,
            aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
            decimation_target=args.decimation, texture_size=args.texture,
            remesh=bool(args.remesh), remesh_band=1, remesh_project=args.remesh_project,
            verbose=True)

        if args.bake == 'ovoxel' and not args.bake_compare:
            glb = o_voxel.postprocess.to_glb(**bake_kwargs)
        else:
            glb = bake_glb.bake_glb(**bake_kwargs)
        glb_peak = torch.cuda.max_memory_allocated()/1e9
        glb.export(args.out, extension_webp=True)

        if args.bake_compare:
            import numpy as _np

            def _tex(m):
                return _np.asarray(m.visual.material.baseColorTexture).astype(_np.int16)

            def _diff(label, m1, m2):
                print(f"[compare] {label}: verts {len(m1.vertices)} vs {len(m2.vertices)} | "
                      f"faces {len(m1.faces)} vs {len(m2.faces)}", flush=True)
                a, b = _tex(m1), _tex(m2)
                if a.shape != b.shape:
                    print(f"[compare] {label}: texture shape differs {a.shape} vs {b.shape}", flush=True)
                    return
                d = _np.abs(a - b)
                print(f"[compare] {label}: baseColor MAE {d.mean():.4f}/255 | max {d.max()} | "
                      f"texels >2/255: {100*(d.max(axis=-1) > 2).mean():.4f}%", flush=True)

            # CONTROL ARM. cumesh's remesh/simplify run on the GPU and are not obviously
            # deterministic; if the mesh differs run to run, the UV atlas differs, and a
            # pixel-wise texture diff between two bakes measures atlas packing rather than
            # the rasteriser. Baking the OLD path twice and diffing it against ITSELF
            # establishes the noise floor that any ours-vs-theirs number must beat.
            t3 = time.time()
            ref_a = o_voxel.postprocess.to_glb(**bake_kwargs)
            ref_a.export(args.out + ".ovoxel.glb", extension_webp=True)
            print(f"[compare] ovoxel bake A {time.time()-t3:.0f}s", flush=True)

            t4 = time.time()
            ref_b = o_voxel.postprocess.to_glb(**bake_kwargs)
            print(f"[compare] ovoxel bake B {time.time()-t4:.0f}s", flush=True)

            _diff("CONTROL ovoxel-A vs ovoxel-B", ref_a, ref_b)
            _diff("TEST    ours     vs ovoxel-A", glb, ref_a)
            print("[compare] read: if CONTROL is as large as TEST, the bakes are not "
                  "pixel-comparable at all and the rasteriser must be judged by "
                  "verify_uv_rasterize.py (same mesh, same UVs) instead.", flush=True)
        print(f"[GLB] {args.out} ({os.path.getsize(args.out)/1e6:.1f} MB) | to_glb {time.time()-t2:.0f}s | "
              f"TO_GLB PEAK {glb_peak:.1f} GB | OVERALL PEAK {max(gen_peak, glb_peak):.1f} GB | TOTAL {time.time()-t0:.0f}s", flush=True)
        # --- Licence guard -----------------------------------------------------------
        # Static reading is not enough here: trellis2/models/sc_vaes/fdg_vae.py does
        # `from o_voxel.convert import ...`, and importing ANY o_voxel submodule executes
        # o_voxel/__init__.py, which eagerly imports .postprocess -> nvdiffrast. Whether
        # that fires depends on which models from_pretrained actually instantiates, which
        # only a real run can answer. So ask sys.modules rather than reason about it.
        if not want_ovoxel:
            clean = licence_guard.report("clean bake path:")
            if not clean and args.licence_strict:
                print("LICENCE GUARD: failing (--licence-strict).", flush=True)
                sys.exit(3)
        print("=== MESH RUN COMPLETE ===", flush=True)
    except torch.cuda.OutOfMemoryError as e:
        print(f"ERROR: CUDA out of memory during mesh run: {e}", flush=True)
        print("  suggestion: try a smaller --ptype (e.g. 512 instead of 1024_cascade) or a lower --decimation", flush=True)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: mesh run failed: {e}", flush=True)
        sys.exit(1)
    finally:
        torch.cuda.empty_cache()
