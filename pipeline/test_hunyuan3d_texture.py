"""
Test Hunyuan3D-2 texture generation on an existing mesh.
Run with WinPortable's Python.

Usage (from sprite-foundry root):
    F:/AI-Models/Hunyuan3D-2/Hunyuan3D2_WinPortable/python_standalone/python.exe \
        -s pipeline/test_hunyuan3d_texture.py
"""

import os
import sys
import time

# Point HuggingFace cache to WinPortable's location
WINPORTABLE = "F:/AI-Models/Hunyuan3D-2/Hunyuan3D2_WinPortable"
os.environ["HF_HUB_CACHE"] = os.path.join(WINPORTABLE, "HuggingFaceHub")
os.environ["HY3DGEN_MODELS"] = os.path.join(WINPORTABLE, "HuggingFaceHub")

# Add Hunyuan3D-2 source to path
sys.path.insert(0, os.path.join(WINPORTABLE, "Hunyuan3D-2"))

import torch
import trimesh

print(f"PyTorch: {torch.__version__}")
print(f"CUDA: {torch.cuda.get_device_name(0)}")
print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

INPUT_MESH = "F:/AI/sprite-foundry/bakeoff/hunyuan3d_output/mage_shape.glb"
OUTPUT_DIR = "F:/AI/sprite-foundry/bakeoff/hunyuan3d_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load the untextured mesh
print(f"\nLoading mesh: {INPUT_MESH}")
mesh = trimesh.load(INPUT_MESH)
if isinstance(mesh, trimesh.Scene):
    mesh = trimesh.util.concatenate(list(mesh.geometry.values()))
print(f"  Vertices: {len(mesh.vertices)}, Faces: {len(mesh.faces)}")

# Load texture pipeline
print("\nLoading Hunyuan3D Paint pipeline (turbo)...")
t0 = time.time()

from hy3dgen.texgen import Hunyuan3DPaintPipeline

texgen = Hunyuan3DPaintPipeline.from_pretrained("tencent/Hunyuan3D-2")
# Move sub-pipelines to CUDA (the wrapper class has no .to() method)
texgen.models['delight_model'].pipeline = texgen.models['delight_model'].pipeline.to("cuda")
texgen.models['multiview_model'].pipeline = texgen.models['multiview_model'].pipeline.to("cuda")
print(f"Paint pipeline loaded in {time.time() - t0:.1f}s")

if torch.cuda.is_available():
    allocated = torch.cuda.memory_allocated() / 1024**3
    reserved = torch.cuda.memory_reserved() / 1024**3
    print(f"VRAM: {allocated:.1f} GB allocated, {reserved:.1f} GB reserved")

# Generate texture from the front reference image
print("\nGenerating texture...")
t1 = time.time()

from PIL import Image
ref_image = Image.open("F:/AI/sprite-foundry/bakeoff/hunyuan3d_input/front.png")

textured_mesh = texgen(
    mesh,
    image=ref_image,
)

tex_time = time.time() - t1
print(f"Texture generated in {tex_time:.1f}s")

# Export textured mesh
output_path = os.path.join(OUTPUT_DIR, "mage_textured.glb")
textured_mesh.export(output_path)
print(f"\nExported to: {output_path}")
print(f"File size: {os.path.getsize(output_path) / 1024:.0f} KB")

# VRAM stats
if torch.cuda.is_available():
    allocated = torch.cuda.memory_allocated() / 1024**3
    peak = torch.cuda.max_memory_allocated() / 1024**3
    print(f"\nVRAM: {allocated:.1f} GB allocated, {peak:.1f} GB peak")

print("\nDone!")
