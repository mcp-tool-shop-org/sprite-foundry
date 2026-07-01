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
    from trellis2.pipelines import Trellis2ImageTo3DPipeline
    import o_voxel

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
        glb = o_voxel.postprocess.to_glb(
            vertices=mesh.vertices, faces=mesh.faces, attr_volume=mesh.attrs,
            coords=mesh.coords, attr_layout=mesh.layout, voxel_size=mesh.voxel_size,
            aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
            decimation_target=args.decimation, texture_size=args.texture,
            remesh=bool(args.remesh), remesh_band=1, remesh_project=args.remesh_project, verbose=True)
        glb_peak = torch.cuda.max_memory_allocated()/1e9
        glb.export(args.out, extension_webp=True)
        print(f"[GLB] {args.out} ({os.path.getsize(args.out)/1e6:.1f} MB) | to_glb {time.time()-t2:.0f}s | "
              f"TO_GLB PEAK {glb_peak:.1f} GB | OVERALL PEAK {max(gen_peak, glb_peak):.1f} GB | TOTAL {time.time()-t0:.0f}s", flush=True)
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
