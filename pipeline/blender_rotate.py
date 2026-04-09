"""
Blender-based sprite rotation from turnaround views.

Takes front, side, and back view images, projects them onto a billboard
cylinder, and renders 8 cardinal directions with consistent lighting.

Usage:
    blender --background --python pipeline/blender_rotate.py -- \
        --front bakeoff/.../front_seed.png \
        --side bakeoff/.../side_seed.png \
        --back bakeoff/.../back_seed.png \
        --output bakeoff/blender_rotate/
"""

import bpy
import sys
import os
import math
from pathlib import Path

# Parse args after "--"
argv = sys.argv
if "--" in argv:
    argv = argv[argv.index("--") + 1:]
else:
    argv = []

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--front", required=True)
parser.add_argument("--side", required=True)
parser.add_argument("--back", required=True)
parser.add_argument("--output", default="bakeoff/blender_rotate")
parser.add_argument("--size", type=int, default=256, help="Render resolution")
args = parser.parse_args(argv)

out_dir = Path(args.output)
out_dir.mkdir(parents=True, exist_ok=True)

DIRECTIONS = [
    ("front", 0),
    ("front_right", 45),
    ("right", 90),
    ("back_right", 135),
    ("back", 180),
    ("back_left", 225),
    ("left", 270),
    ("front_left", 315),
]


def clear_scene():
    """Remove default objects."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    # Remove orphan data
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)


def create_billboard_planes(front_path, side_path, back_path):
    """Create textured planes arranged as a cross for front/side/back views.

    The approach: create 3 planes (front-facing, side-facing, back-facing)
    positioned at the origin. Each plane gets its view texture with alpha.
    When rendered from different angles, the correct plane dominates.
    """
    planes = []

    for name, img_path, rotation in [
        ("front", front_path, (math.pi/2, 0, 0)),
        ("side", side_path, (math.pi/2, 0, math.pi/2)),
        ("back", back_path, (math.pi/2, 0, math.pi)),
    ]:
        # Create plane
        bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 0))
        plane = bpy.context.active_object
        plane.name = f"billboard_{name}"
        plane.rotation_euler = rotation
        planes.append(plane)

        # Create material with image texture
        mat = bpy.data.materials.new(name=f"mat_{name}")
        mat.use_nodes = True
        mat.blend_method = 'CLIP'  # For alpha cutout
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # Clear default nodes
        for node in nodes:
            nodes.remove(node)

        # Add nodes: Image Texture -> Principled BSDF -> Output
        output = nodes.new('ShaderNodeOutputMaterial')
        output.location = (400, 0)

        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf.location = (100, 0)
        bsdf.inputs['Roughness'].default_value = 1.0
        bsdf.inputs['Specular IOR Level'].default_value = 0.0

        tex = nodes.new('ShaderNodeTexImage')
        tex.location = (-300, 0)
        tex.image = bpy.data.images.load(os.path.abspath(img_path))

        # Connect
        links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
        links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        plane.data.materials.append(mat)

    return planes


def setup_camera():
    """Create orthographic camera for sprite rendering."""
    bpy.ops.object.camera_add(location=(0, -3, 0.5))
    camera = bpy.context.active_object
    camera.name = "SpriteCamera"
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 2.2

    # Point at origin
    constraint = camera.constraints.new('TRACK_TO')
    constraint.target = bpy.data.objects.get("billboard_front") or bpy.context.scene.objects[0]
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'

    # Actually, use a simpler approach: camera orbits around origin
    # Create empty at origin as camera target
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
    target = bpy.context.active_object
    target.name = "CameraTarget"

    # Parent camera to target for easy rotation
    camera.location = (0, -3, 0.3)
    camera.parent = None

    # Use track-to constraint pointing at origin
    camera.constraints.clear()
    track = camera.constraints.new('TRACK_TO')
    track.target = target
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'

    bpy.context.scene.camera = camera
    return camera, target


def setup_lighting():
    """Simple even lighting for sprite rendering."""
    # Key light
    bpy.ops.object.light_add(type='AREA', location=(2, -2, 3))
    key = bpy.context.active_object
    key.name = "KeyLight"
    key.data.energy = 50
    key.data.size = 5

    # Fill light
    bpy.ops.object.light_add(type='AREA', location=(-2, -2, 2))
    fill = bpy.context.active_object
    fill.name = "FillLight"
    fill.data.energy = 25
    fill.data.size = 5

    # Top ambient
    bpy.ops.object.light_add(type='AREA', location=(0, 0, 4))
    top = bpy.context.active_object
    top.name = "TopLight"
    top.data.energy = 15
    top.data.size = 8


def setup_render(size):
    """Configure render settings."""
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'


def render_directions(camera, output_dir, size):
    """Render from 8 directions by orbiting the camera."""
    for name, angle_deg in DIRECTIONS:
        angle_rad = math.radians(angle_deg)

        # Position camera on a circle around origin
        radius = 3.0
        camera.location.x = radius * math.sin(angle_rad)
        camera.location.y = -radius * math.cos(angle_rad)
        camera.location.z = 0.3

        # Render
        filepath = str(Path(output_dir).resolve() / name)
        bpy.context.scene.render.filepath = filepath
        bpy.ops.render.render(write_still=True)
        print(f"  Rendered {name} ({angle_deg} deg) -> {filepath}")


def main():
    print(f"\n{'=' * 50}")
    print(f"BLENDER SPRITE ROTATION")
    print(f"  Front: {args.front}")
    print(f"  Side:  {args.side}")
    print(f"  Back:  {args.back}")
    print(f"  Output: {args.output}")
    print(f"{'=' * 50}\n")

    clear_scene()
    planes = create_billboard_planes(args.front, args.side, args.back)
    camera, target = setup_camera()
    setup_lighting()
    setup_render(args.size)
    render_directions(camera, args.output, args.size)

    print(f"\n  Done! 8 directions rendered to {args.output}")


main()
