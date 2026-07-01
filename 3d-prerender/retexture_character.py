import os, time, argparse, inspect, sys
os.environ['OPENCV_IO_ENABLE_OPENEXR'] = '1'
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
from pathlib import Path
import config

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument('--mesh', required=True, help='existing mesh (glb/ply) to re-texture')
    ap.add_argument('--image', required=True, help='reference image to drive the texture bake')
    ap.add_argument('--out', required=True)
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()

    # validate BEFORE the expensive GPU pipeline load
    mesh_path = Path(args.mesh)
    if not mesh_path.exists():
        print(f"ERROR: --mesh not found: {mesh_path}", flush=True)
        sys.exit(1)
    image_path = Path(args.image)
    if not image_path.exists():
        print(f"ERROR: --image not found: {image_path}", flush=True)
        sys.exit(1)
    try:
        from PIL import Image
        with Image.open(image_path) as _probe_img:
            _probe_img.verify()
    except Exception as e:
        print(f"ERROR: --image is not a valid/openable image ({image_path}): {e}", flush=True)
        sys.exit(1)

    import torch
    import trimesh
    from PIL import Image
    from trellis2.pipelines import Trellis2TexturingPipeline

    t0 = time.time()
    print(f"=== retexture run: mesh={args.mesh} image={args.image} ===", flush=True)
    print(f"loading Trellis2TexturingPipeline ({config.TRELLIS_MODEL_ID}) ...", flush=True)
    pipeline = Trellis2TexturingPipeline.from_pretrained(config.TRELLIS_MODEL_ID, config_file="texturing_pipeline.json")
    pipeline.cuda()
    print(f"[load] {time.time()-t0:.0f}s | VRAM now {torch.cuda.memory_allocated()/1e9:.1f} GB", flush=True)

    try:
        print("run() signature:", inspect.signature(pipeline.run), flush=True)
    except Exception as e:
        print("signature introspection failed:", e, flush=True)

    mesh = trimesh.load(args.mesh)
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.to_mesh()
    n_verts, n_faces = len(mesh.vertices), len(mesh.faces)
    print(f"mesh loaded: verts={n_verts} faces={n_faces}", flush=True)
    image = Image.open(args.image)

    t1 = time.time()
    torch.cuda.reset_peak_memory_stats()
    try:
        output = pipeline.run(mesh, image, seed=args.seed)
        torch.cuda.synchronize()
        peak = torch.cuda.max_memory_allocated()/1e9
        print(f"[texture] {time.time()-t1:.0f}s | PEAK {peak:.1f} GB", flush=True)

        output.export(args.out, extension_webp=True)
        print(f"[GLB] {args.out} ({os.path.getsize(args.out)/1e6:.1f} MB) | TOTAL {time.time()-t0:.0f}s", flush=True)
        print("=== RETEXTURE RUN COMPLETE ===", flush=True)
    except torch.cuda.OutOfMemoryError as e:
        print(f"ERROR: CUDA out of memory during retexture run (mesh verts={n_verts} faces={n_faces}): {e}", flush=True)
        print("  suggestion: retry with a lower-poly --mesh (decimate it first) or free VRAM before rerunning", flush=True)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: retexture run failed (mesh verts={n_verts} faces={n_faces}): {e}", flush=True)
        sys.exit(1)
    finally:
        torch.cuda.empty_cache()
