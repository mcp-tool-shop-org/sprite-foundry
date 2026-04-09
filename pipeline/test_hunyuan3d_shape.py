"""
Test Hunyuan3D-2mv shape generation (no texture).
Run with WinPortable's Python — not system Python.

Usage (from sprite-foundry root):
    F:/AI-Models/Hunyuan3D-2/Hunyuan3D2_WinPortable/python_standalone/python.exe \
        -s pipeline/test_hunyuan3d_shape.py
"""

import os
import sys
import time

# Point HuggingFace cache to WinPortable's location
WINPORTABLE = "F:/AI-Models/Hunyuan3D-2/Hunyuan3D2_WinPortable"
os.environ["HF_HUB_CACHE"] = os.path.join(WINPORTABLE, "HuggingFaceHub")
os.environ["HY3DGEN_MODELS"] = os.path.join(WINPORTABLE, "HuggingFaceHub")

# Add the Hunyuan3D-2 source to path
sys.path.insert(0, os.path.join(WINPORTABLE, "Hunyuan3D-2"))

import torch
print(f"PyTorch: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"CUDA device: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

# Input images
INPUT_DIR = "F:/AI/sprite-foundry/bakeoff/hunyuan3d_input"
OUTPUT_DIR = "F:/AI/sprite-foundry/bakeoff/hunyuan3d_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"\nInput dir: {INPUT_DIR}")
print(f"Output dir: {OUTPUT_DIR}")

# Check inputs exist
for view in ["front", "left", "back"]:
    path = os.path.join(INPUT_DIR, f"{view}.png")
    if os.path.exists(path):
        print(f"  {view}.png: OK")
    else:
        print(f"  {view}.png: MISSING")

print("\nLoading Hunyuan3D-2mv pipeline...")
t0 = time.time()

from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    "tencent/Hunyuan3D-2mv",
    subfolder="hunyuan3d-dit-v2-mv-turbo",
    use_safetensors=True,
    device="cuda",
)

print(f"Pipeline loaded in {time.time() - t0:.1f}s")

# Check VRAM after loading
if torch.cuda.is_available():
    allocated = torch.cuda.memory_allocated() / 1024**3
    reserved = torch.cuda.memory_reserved() / 1024**3
    print(f"VRAM: {allocated:.1f} GB allocated, {reserved:.1f} GB reserved")

# Build multi-view input dict
image_input = {
    "front": os.path.join(INPUT_DIR, "front.png"),
    "left": os.path.join(INPUT_DIR, "left.png"),
    "back": os.path.join(INPUT_DIR, "back.png"),
}

print(f"\nGenerating mesh (mc_algo=mc, turbo mode)...")
t1 = time.time()

mesh = pipeline(
    image=image_input,
    num_inference_steps=30,
    mc_algo="mc",
    octree_resolution=256,
    generator=torch.manual_seed(42),
    output_type="trimesh",
)[0]

gen_time = time.time() - t1
print(f"Mesh generated in {gen_time:.1f}s")
print(f"  Vertices: {len(mesh.vertices)}")
print(f"  Faces: {len(mesh.faces)}")

# Export
output_path = os.path.join(OUTPUT_DIR, "mage_shape.glb")
mesh.export(output_path)
print(f"\nExported to: {output_path}")
print(f"File size: {os.path.getsize(output_path) / 1024:.0f} KB")

# Final VRAM
if torch.cuda.is_available():
    allocated = torch.cuda.memory_allocated() / 1024**3
    peak = torch.cuda.max_memory_allocated() / 1024**3
    print(f"\nVRAM: {allocated:.1f} GB allocated, {peak:.1f} GB peak")

print("\nDone!")
