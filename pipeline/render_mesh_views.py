"""
Render 8 orthographic views from a 3D mesh (GLB/OBJ/PLY) for sprite foundry.

Produces 512x512 RGBA renders at 8 azimuth angles with a slight top-down pitch,
ready for BG removal + downscale to 48px sprites.

Usage:
    python -m pipeline.render_mesh_views --mesh output.glb --output bakeoff/mesh_renders
    python -m pipeline.render_mesh_views --mesh output.glb --output bakeoff/mesh_renders --size 512 --pitch 20

Dependencies:
    pip install trimesh pyrender pyglet numpy Pillow
"""

import argparse
import math
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image


# 8 sprite directions with azimuth angles
DIRECTIONS = [
    ("front",       0),
    ("front_right", 45),
    ("right",       90),
    ("back_right",  135),
    ("back",        180),
    ("back_left",   225),
    ("left",        270),
    ("front_left",  315),
]


def look_at(eye, target, up):
    """Build a 4x4 camera-to-world matrix (OpenGL convention)."""
    eye = np.array(eye, dtype=np.float64)
    target = np.array(target, dtype=np.float64)
    up = np.array(up, dtype=np.float64)

    forward = target - eye
    forward = forward / np.linalg.norm(forward)

    right = np.cross(forward, up)
    right = right / np.linalg.norm(right)

    true_up = np.cross(right, forward)

    mat = np.eye(4)
    mat[0, :3] = right
    mat[1, :3] = true_up
    mat[2, :3] = -forward
    mat[0, 3] = -np.dot(right, eye)
    mat[1, 3] = -np.dot(true_up, eye)
    mat[2, 3] = np.dot(forward, eye)

    # Return camera-to-world (inverse of view matrix)
    return np.linalg.inv(mat)


def render_views(mesh_path: str, output_dir: str, size: int = 512, pitch: float = 20.0):
    """Render 8 directional views of a mesh."""
    import pyrender

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Load mesh
    print(f"Loading mesh: {mesh_path}")
    scene_or_mesh = trimesh.load(mesh_path)

    # Handle both Scene and Mesh objects
    if isinstance(scene_or_mesh, trimesh.Scene):
        mesh_list = list(scene_or_mesh.geometry.values())
        combined = trimesh.util.concatenate(mesh_list)
    else:
        combined = scene_or_mesh

    print(f"  Vertices: {len(combined.vertices)}, Faces: {len(combined.faces)}")

    # Center and normalize
    center = combined.bounding_box.centroid
    combined.vertices -= center
    extent = combined.bounding_box.extents.max()
    combined.vertices /= extent  # normalize to [-0.5, 0.5]

    # Build pyrender scene
    scene = pyrender.Scene(bg_color=[0, 0, 0, 0], ambient_light=[0.3, 0.3, 0.3])

    # Add mesh
    if combined.visual.kind == 'texture' and hasattr(combined.visual, 'material'):
        py_mesh = pyrender.Mesh.from_trimesh(combined)
    else:
        py_mesh = pyrender.Mesh.from_trimesh(combined)
    scene.add(py_mesh)

    # Add directional light
    light = pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=3.0)
    light_pose = look_at([1, 2, 2], [0, 0, 0], [0, 1, 0])
    scene.add(light, pose=light_pose)

    # Orthographic camera — scale to fit the normalized mesh
    camera = pyrender.OrthographicCamera(xmag=0.7, ymag=0.7)

    # Offscreen renderer
    renderer = pyrender.OffscreenRenderer(size, size)

    pitch_rad = math.radians(pitch)
    dist = 2.0

    pixel_images = {}

    for dir_name, az_deg in DIRECTIONS:
        az_rad = math.radians(az_deg)

        # Camera position on a sphere
        x = dist * math.sin(az_rad) * math.cos(pitch_rad)
        y = dist * math.sin(pitch_rad)
        z = dist * math.cos(az_rad) * math.cos(pitch_rad)

        eye = [x, y, z]
        target = [0, 0, 0]
        up = [0, 1, 0]

        camera_pose = look_at(eye, target, up)
        cam_node = scene.add(camera, pose=camera_pose)

        color, depth = renderer.render(scene, flags=pyrender.RenderFlags.RGBA)

        scene.remove_node(cam_node)

        # Save RGBA render
        img = Image.fromarray(color)
        img.save(str(out / f"{dir_name}.png"))

        # Compute occupancy
        alpha = color[:, :, 3]
        occ = np.sum(alpha > 0) / (size * size)
        print(f"  {dir_name}: {occ:.0%} occupancy")

        pixel_images[dir_name] = img

    renderer.delete()

    # Make contact sheet
    make_contact_sheet(pixel_images, out)

    print(f"\n8 views rendered to: {out}")
    return pixel_images


def make_contact_sheet(pixel_images: dict, out_dir: Path):
    """Generate a contact sheet of all 8 views."""
    from PIL import ImageDraw, ImageFont

    cell_size = 256
    pad = 4
    cols = 8
    header_h = 30

    total_w = cols * (cell_size + pad) + pad
    total_h = header_h + cell_size + pad * 2

    sheet = Image.new("RGB", (total_w, total_h), (24, 24, 32))
    draw = ImageDraw.Draw(sheet)

    try:
        font = ImageFont.truetype("consola.ttf", 11)
    except (OSError, IOError):
        font = ImageFont.load_default()

    for i, (dir_name, _) in enumerate(DIRECTIONS):
        x = pad + i * (cell_size + pad)
        y = header_h

        draw.text((x, 4), dir_name, fill=(200, 200, 210), font=font)

        if dir_name in pixel_images:
            thumb = pixel_images[dir_name].resize((cell_size, cell_size), Image.LANCZOS)

            # Checkerboard background
            checker = Image.new("RGB", (cell_size, cell_size))
            cd = ImageDraw.Draw(checker)
            for cy in range(0, cell_size, 16):
                for cx in range(0, cell_size, 16):
                    c = (45, 45, 55) if (cx // 16 + cy // 16) % 2 == 0 else (35, 35, 45)
                    cd.rectangle([cx, cy, cx + 15, cy + 15], fill=c)

            if thumb.mode == "RGBA":
                checker.paste(thumb, (0, 0), thumb)
            else:
                checker.paste(thumb, (0, 0))

            sheet.paste(checker, (x, y))

    sheet.save(str(out_dir / "contact_sheet.png"))
    print(f"  Contact sheet saved")


def main():
    parser = argparse.ArgumentParser(description="Render 8 orthographic views from a 3D mesh")
    parser.add_argument("--mesh", required=True, help="Path to GLB/OBJ/PLY mesh file")
    parser.add_argument("--output", default="bakeoff/mesh_renders", help="Output directory")
    parser.add_argument("--size", type=int, default=512, help="Render size (default 512)")
    parser.add_argument("--pitch", type=float, default=20.0, help="Camera pitch in degrees (default 20)")
    args = parser.parse_args()

    render_views(args.mesh, args.output, args.size, args.pitch)


if __name__ == "__main__":
    main()
