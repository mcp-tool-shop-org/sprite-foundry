# Hunyuan3D-2mv Pipeline Handoff

## What Was Proven

CharTurn LoRA → Hunyuan3D-2mv → textured 3D mesh → 8-angle orthographic render. Full pipeline runs on RTX 5080 16GB VRAM (10.3GB peak). Shape takes 44s, texture takes 65s.

## How to Run (Step by Step)

### Prerequisites (already installed)

- WinPortable: `F:/AI-Models/Hunyuan3D-2/Hunyuan3D2_WinPortable/`
- CUDA 12.9 toolkit: `F:/CUDA/v12.9/`
- Model weights cached in `F:/AI-Models/Hunyuan3D-2/Hunyuan3D2_WinPortable/HuggingFaceHub/`
- C++ extensions compiled (diso, custom_rasterizer, differentiable_renderer)
- Python used for Hunyuan3D: `F:/AI-Models/Hunyuan3D-2/Hunyuan3D2_WinPortable/python_standalone/python.exe`
- Python used for rendering: system Python (pyrender + trimesh installed)

### Step 1: Generate a CharTurn turnaround sheet

Requires ComfyUI running at localhost:8188.

```bash
cd F:/AI/sprite-foundry
python -m pipeline.foundry_gen_turnaround --config pipeline/chars/YOUR_CHAR.json
```

Character config JSON format:
```json
{
  "subject_id": "dark_knight",
  "display_name": "Dark Knight",
  "seed": 42,
  "subject_prompt": "a dark armored knight with a great sword, full plate armor, menacing red visor",
  "negative_prompt": "cute, chibi, cartoon"
}
```

Output: `bakeoff/<run_id>/turnaround_sheet.png`

### Step 2: Prep input images for Hunyuan3D

```bash
cd F:/AI/sprite-foundry
python -m pipeline.prep_hunyuan3d_input \
  --sheet bakeoff/<run_id>/turnaround_sheet.png \
  --output bakeoff/hunyuan3d_input_<name>
```

This extracts front/left/back at 512x512 with white background. Check the crops — if two figures merged in one bbox (CharTurn artifact), you may need to manually split.

### Step 3: Shape generation

```bash
cd F:/AI/sprite-foundry
F:/AI-Models/Hunyuan3D-2/Hunyuan3D2_WinPortable/python_standalone/python.exe \
  -s pipeline/test_hunyuan3d_shape.py
```

**Edit the script first** to point `INPUT_DIR` and `OUTPUT_DIR` to your paths. Or write a new script using this pattern:

```python
import os, sys, torch
os.environ["HF_HUB_CACHE"] = "F:/AI-Models/Hunyuan3D-2/Hunyuan3D2_WinPortable/HuggingFaceHub"
os.environ["HY3DGEN_MODELS"] = "F:/AI-Models/Hunyuan3D-2/Hunyuan3D2_WinPortable/HuggingFaceHub"
sys.path.insert(0, "F:/AI-Models/Hunyuan3D-2/Hunyuan3D2_WinPortable/Hunyuan3D-2")

from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    "tencent/Hunyuan3D-2mv",
    subfolder="hunyuan3d-dit-v2-mv-turbo",
    use_safetensors=True,
    device="cuda",
)

mesh = pipeline(
    image={"front": "front.png", "left": "left.png", "back": "back.png"},
    num_inference_steps=30,
    mc_algo="mc",
    octree_resolution=256,
    generator=torch.manual_seed(42),
    output_type="trimesh",
)[0]

mesh.export("output_shape.glb")
```

VRAM: ~4.9 GB peak. Takes ~44 seconds.

### Step 4: Texture generation

```python
from hy3dgen.texgen import Hunyuan3DPaintPipeline
from PIL import Image

texgen = Hunyuan3DPaintPipeline.from_pretrained("tencent/Hunyuan3D-2")
# IMPORTANT: must move sub-pipelines to CUDA individually
texgen.models['delight_model'].pipeline = texgen.models['delight_model'].pipeline.to("cuda")
texgen.models['multiview_model'].pipeline = texgen.models['multiview_model'].pipeline.to("cuda")

ref_image = Image.open("front.png")
textured_mesh = texgen(mesh, image=ref_image)
textured_mesh.export("output_textured.glb")
```

VRAM: ~10.3 GB peak. Takes ~65 seconds.

### Step 5: Render 8 angles

```bash
cd F:/AI/sprite-foundry

# Convert texture to vertex colors first (PyOpenGL can't bind textures in offscreen mode)
python -c "
import trimesh
mesh = trimesh.load('output_textured.glb')
geom = list(mesh.geometry.values())[0]
geom.visual = geom.visual.to_color()
geom.export('output_vertexcolor.glb')
"

# Render 8 views
python -m pipeline.render_mesh_views \
  --mesh output_vertexcolor.glb \
  --output renders/ \
  --size 512 --pitch 20
```

### Step 6: Downsample to 48px sprites (not yet automated)

Manual for now — crop tight around the figure, downsample with nearest-neighbor.

## Known Issues

1. **Camera too zoomed out**: occupancy 8-12%, needs tighter orthographic camera (adjust xmag/ymag in render script)
2. **Vertex-color bake**: loses texture sharpness vs actual texture map
3. **PyOpenGL glGenTextures bug**: offscreen renderer can't bind texture objects — workaround is vertex-color bake
4. **CharTurn merged figures**: front crop sometimes contains 2 figures if CharTurn placed them too close
5. **Hunyuan3D-2mv input**: accepts `{"front", "left", "back"}` — note it's "left" not "right"
6. **Flat 2D details don't transfer**: golden orbs, floating effects, etc. from the 2D art won't appear in 3D
7. **Ground plane artifact**: small flat area at mesh base from reconstruction

## Style Exploration Ideas

To learn the limits, try varying:
- **Body type**: humanoid, armored, robed, monster, quadruped
- **Detail level**: simple silhouette vs ornate detail
- **Thin features**: weapons, wings, tails, antennae (likely to blob out)
- **Color contrast**: high contrast (easy) vs subtle shading (harder to preserve)
- **Character scale**: large boss vs small minion

## Files Reference

| Script | Purpose | Python |
|---|---|---|
| `pipeline/prep_hunyuan3d_input.py` | Extract crops from turnaround sheet | System |
| `pipeline/test_hunyuan3d_shape.py` | Shape generation test | WinPortable |
| `pipeline/test_hunyuan3d_texture.py` | Texture generation test | WinPortable |
| `pipeline/render_mesh_views.py` | 8-angle orthographic render | System |
| `pipeline/foundry_gen_turnaround.py` | CharTurn LoRA sheet generation | System (needs ComfyUI) |
