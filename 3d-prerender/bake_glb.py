"""Licence-clean mesh -> textured GLB bake.

Replaces `o_voxel.postprocess.to_glb` in our character pipeline.

WHY
---
`o_voxel.postprocess` imports nvdiffrast at MODULE scope, so merely importing it loads
NVIDIA code licensed "for research or evaluation purposes only and not for any direct or
indirect monetary gain" (Nvidia Source Code License 1-Way Commercial, section 3.3). There
is no way to call the surrounding function without loading it, so the bake moves here.

Two things this buys beyond the licence:
  * o_voxel ships NO licence at all -- no LICENSE file, no License field in its METADATA
    -- so depending on it was an unresolved question independent of nvdiffrast. This
    module drops it from the character path.
  * our rasteriser is ~10x faster than nvdiffrast on this workload (0.05s vs 0.52s for
    380k tris at 4096^2), because a UV bake needs no differentiability and no depth sort.

WHAT IT IS
----------
A reimplementation written against the PUBLIC APIs of cumesh (MIT), flex_gemm (MIT),
trimesh (MIT), OpenCV (Apache-2.0) and our own uv_rasterize. The step ORDER is dictated by
those APIs -- clean, simplify, unwrap, bake, sample -- not copied.

Licence surface after this change, for the whole character bake path:
    cumesh MIT | flex_gemm MIT | trimesh MIT | opencv Apache-2.0 | torch BSD-3 | numpy BSD-3

Equivalence to the previous bake is verified by verify_uv_rasterize.py (rasteriser level)
and by --bake-compare in mesh_character.py (whole-GLB level).
"""

from typing import Dict, Optional, Union

import cv2
import numpy as np
import torch
import trimesh
import trimesh.visual
import cumesh
from flex_gemm.ops.grid_sample import grid_sample_3d

import uv_rasterize


def _as_tensor(x, device, dtype=torch.float32, broadcast3=False):
    """Normalise scalar / list / ndarray / tensor to a tensor on `device`.

    `voxel_size` arrives from the TRELLIS pipeline as a bare Python float, so the
    scalar case is the common one, not an edge case.
    """
    if isinstance(x, torch.Tensor):
        x = x.to(device=device, dtype=dtype)
    elif isinstance(x, (int, float, np.integer, np.floating)):
        x = torch.tensor(x, dtype=dtype, device=device)
    else:
        if isinstance(x, (list, tuple)):
            x = np.array(x)
        if isinstance(x, np.ndarray):
            x = torch.tensor(x, dtype=dtype, device=device)
        else:
            raise TypeError(f"cannot convert {type(x)} to tensor")
    if broadcast3 and x.dim() == 0:
        x = x.repeat(3)
    return x


def bake_glb(
    vertices: torch.Tensor,
    faces: torch.Tensor,
    attr_volume: torch.Tensor,
    coords: torch.Tensor,
    attr_layout: Dict[str, slice],
    aabb: Union[list, tuple, np.ndarray, torch.Tensor],
    voxel_size: Union[float, list, tuple, np.ndarray, torch.Tensor, None] = None,
    grid_size: Union[int, list, tuple, np.ndarray, torch.Tensor, None] = None,
    decimation_target: int = 1000000,
    texture_size: int = 2048,
    remesh: bool = False,
    remesh_band: float = 1,
    remesh_project: float = 0.9,
    mesh_cluster_threshold_cone_half_angle_rad: float = np.radians(90.0),
    mesh_cluster_refine_iterations: int = 0,
    mesh_cluster_global_iterations: int = 1,
    mesh_cluster_smooth_strength: float = 1,
    verbose: bool = False,
) -> trimesh.Trimesh:
    """Clean, unwrap and texture-bake an extracted mesh into a trimesh.Trimesh.

    Signature deliberately matches o_voxel.postprocess.to_glb so callers swap with one
    import change. Returns the Trimesh; the caller exports it.
    """
    device = coords.device

    # --- Input normalisation -------------------------------------------------------
    aabb = _as_tensor(aabb, device)
    assert aabb.shape == (2, 3), f"aabb must be (2,3), got {tuple(aabb.shape)}"
    extent = aabb[1] - aabb[0]

    if voxel_size is not None:
        voxel_size = _as_tensor(voxel_size, device, broadcast3=True)
        grid_size = torch.round(extent / voxel_size).long()
    elif grid_size is not None:
        grid_size = _as_tensor(grid_size, device, dtype=torch.long, broadcast3=True)
        voxel_size = extent / grid_size.float()
    else:
        raise ValueError("one of voxel_size / grid_size is required")

    assert voxel_size.shape == (3,), f"voxel_size must be (3,), got {tuple(voxel_size.shape)}"
    assert grid_size.shape == (3,), f"grid_size must be (3,), got {tuple(grid_size.shape)}"

    vertices = vertices.cuda()
    faces = faces.cuda()

    # --- Clean ---------------------------------------------------------------------
    mesh = cumesh.CuMesh()
    mesh.init(vertices, faces)
    mesh.fill_holes(max_hole_perimeter=3e-2)
    if verbose:
        print(f"[bake] after fill_holes: {mesh.num_vertices} verts / {mesh.num_faces} faces")

    # BVH is built on the PRE-simplification mesh: it is the reference surface that
    # simplification/remeshing errors get projected back onto during sampling.
    ref_vertices, ref_faces = mesh.read()
    bvh = cumesh.cuBVH(ref_vertices, ref_faces)

    if not remesh:
        # Overshoot, clean, then hit the target: cleaning topology after an aggressive
        # pass removes the degenerate faces that would otherwise survive into the atlas.
        mesh.simplify(decimation_target * 3, verbose=verbose)
        mesh.remove_duplicate_faces()
        mesh.repair_non_manifold_edges()
        mesh.remove_small_connected_components(1e-5)
        mesh.fill_holes(max_hole_perimeter=3e-2)
        mesh.simplify(decimation_target, verbose=verbose)
        mesh.remove_duplicate_faces()
        mesh.repair_non_manifold_edges()
        mesh.remove_small_connected_components(1e-5)
        mesh.fill_holes(max_hole_perimeter=3e-2)
        mesh.unify_face_orientations()
    else:
        center = aabb.mean(dim=0)
        scale = float(extent.max())
        resolution = int(grid_size.max())
        mesh.init(*cumesh.remeshing.remesh_narrow_band_dc(
            ref_vertices, ref_faces,
            center=center,
            scale=(resolution + 3 * remesh_band) / resolution * scale,
            resolution=resolution,
            band=remesh_band,
            project_back=remesh_project,
            verbose=verbose,
            bvh=bvh,
        ))
        mesh.simplify(decimation_target, verbose=verbose)
    if verbose:
        print(f"[bake] after clean: {mesh.num_vertices} verts / {mesh.num_faces} faces")

    # --- UV unwrap -----------------------------------------------------------------
    out_vertices, out_faces, out_uvs, out_vmaps = mesh.uv_unwrap(
        compute_charts_kwargs={
            "threshold_cone_half_angle_rad": mesh_cluster_threshold_cone_half_angle_rad,
            "refine_iterations": mesh_cluster_refine_iterations,
            "global_iterations": mesh_cluster_global_iterations,
            "smooth_strength": mesh_cluster_smooth_strength,
        },
        return_vmaps=True,
        verbose=verbose,
    )
    out_vertices = out_vertices.cuda()
    out_faces = out_faces.cuda()
    out_uvs = out_uvs.cuda()
    out_vmaps = out_vmaps.cuda()
    mesh.compute_vertex_normals()
    out_normals = mesh.read_vertex_normals()[out_vmaps]

    # --- Texture bake (this is the step that used nvdiffrast) -----------------------
    rast = uv_rasterize.rasterize(out_uvs, out_faces, texture_size)
    mask = rast[0, ..., 3] > 0
    pos, _ = uv_rasterize.interpolate(out_vertices, rast, out_faces)
    valid_pos = pos[0][mask]

    # Project each texel's position back onto the ORIGINAL high-res surface, so the
    # colour is sampled where the real geometry is rather than where simplification
    # moved it to.
    _, face_id, uvw = bvh.unsigned_distance(valid_pos, return_uvw=True)
    orig_tri = ref_vertices[ref_faces[face_id.long()]]
    valid_pos = (orig_tri * uvw.unsqueeze(-1)).sum(dim=1)

    attrs = torch.zeros(texture_size, texture_size, attr_volume.shape[1], device="cuda")
    attrs[mask] = grid_sample_3d(
        attr_volume,
        torch.cat([torch.zeros_like(coords[:, :1]), coords], dim=-1),
        shape=torch.Size([1, attr_volume.shape[1], *grid_size.tolist()]),
        grid=((valid_pos - aabb[0]) / voxel_size).reshape(1, -1, 3),
        mode="trilinear",
    )

    # --- Channels, inpaint, material ------------------------------------------------
    mask_np = mask.cpu().numpy()

    def ch(key):
        return np.clip(attrs[..., attr_layout[key]].cpu().numpy() * 255, 0, 255).astype(np.uint8)

    base_color = ch("base_color")
    metallic = ch("metallic")
    roughness = ch("roughness")
    alpha = ch("alpha")

    # Texels no triangle covered would otherwise bake black and bleed dark seams along
    # every chart edge under bilinear filtering. Inpaint fills them from their neighbours.
    mask_inv = (~mask_np).astype(np.uint8)
    base_color = cv2.inpaint(base_color, mask_inv, 3, cv2.INPAINT_TELEA)
    metallic = cv2.inpaint(metallic, mask_inv, 1, cv2.INPAINT_TELEA)[..., None]
    roughness = cv2.inpaint(roughness, mask_inv, 1, cv2.INPAINT_TELEA)[..., None]
    alpha = cv2.inpaint(alpha, mask_inv, 1, cv2.INPAINT_TELEA)[..., None]

    from PIL import Image
    material = trimesh.visual.material.PBRMaterial(
        baseColorTexture=Image.fromarray(np.concatenate([base_color, alpha], axis=-1)),
        baseColorFactor=np.array([255, 255, 255, 255], dtype=np.uint8),
        # glTF packs occlusion/roughness/metallic into R/G/B.
        metallicRoughnessTexture=Image.fromarray(
            np.concatenate([np.zeros_like(metallic), roughness, metallic], axis=-1)),
        metallicFactor=1.0,
        roughnessFactor=1.0,
        alphaMode="OPAQUE",
        doubleSided=not remesh,
    )

    # --- glTF coordinate convention -------------------------------------------------
    v = out_vertices.cpu().numpy().copy()
    n = out_normals.cpu().numpy().copy()
    uv = out_uvs.cpu().numpy().copy()
    f = out_faces.cpu().numpy()

    # Z-up -> Y-up. Explicit .copy() on both sources: the chained form is correct only
    # because negating column 1 happens to materialise a copy during RHS evaluation
    # (verified). Relying on that is a trap for anyone who later edits the signs, so the
    # copies are spelled out.
    v[:, 1], v[:, 2] = v[:, 2].copy(), -v[:, 1].copy()
    n[:, 1], n[:, 2] = n[:, 2].copy(), -n[:, 1].copy()
    uv[:, 1] = 1 - uv[:, 1]

    return trimesh.Trimesh(
        vertices=v,
        faces=f,
        vertex_normals=n,
        process=False,
        visual=trimesh.visual.TextureVisuals(uv=uv, material=material),
    )
