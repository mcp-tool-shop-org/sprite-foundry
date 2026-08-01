"""Verify uv_rasterize.py against nvdiffrast on real pipeline data.

This is the external verifier for the licence-clean bake. It uses nvdiffrast strictly as
a measurement oracle -- "evaluation purposes" is explicitly permitted by the NVIDIA Source
Code License section 3.3 that forbids the production use we are removing.

The conventions in uv_rasterize.py (row order, barycentric layout) are MEASURED here, not
read off documentation. Run this after any torch / cumesh / driver change; a silent
V-flip or barycentric permutation shows up as a mirrored texture months later, which is
exactly the class of defect that is invisible until it is expensive.

Usage:
    python verify_uv_rasterize.py                       # synthetic + real if available
    python verify_uv_rasterize.py --glb <path> --res 2048
"""

import argparse
import sys

import numpy as np
import torch

import uv_rasterize


def _nvdiffrast_reference(uvs, faces, verts3d, res):
    """Ground truth: rasterise + interpolate exactly as o_voxel.postprocess.to_glb did."""
    import nvdiffrast.torch as dr

    ctx = dr.RasterizeCudaContext()
    uvs_rast = torch.cat(
        [uvs * 2 - 1, torch.zeros_like(uvs[:, :1]), torch.ones_like(uvs[:, :1])], dim=-1
    ).unsqueeze(0)
    rast = torch.zeros((1, res, res, 4), device="cuda", dtype=torch.float32)
    for i in range(0, faces.shape[0], 100000):
        chunk, _ = dr.rasterize(ctx, uvs_rast, faces[i:i + 100000].int(), resolution=[res, res])
        m = chunk[..., 3:4] > 0
        chunk[..., 3:4] += i
        rast = torch.where(m, chunk, rast)
    mask = rast[0, ..., 3] > 0
    pos = dr.interpolate(verts3d.unsqueeze(0), rast, faces.int())[0][0]
    return mask, pos, rast


def _ours(uvs, faces, verts3d, res, row0_is_v0):
    rast = uv_rasterize.rasterize(uvs, faces, res, row0_is_v0=row0_is_v0)
    mask = rast[0, ..., 3] > 0
    pos, _ = uv_rasterize.interpolate(verts3d, rast, faces)
    return mask, pos[0], rast


def compare(uvs, faces, verts3d, res, label):
    print(f"\n=== {label}  ({faces.shape[0]} tris, {res}x{res}) ===")
    nv_mask, nv_pos, nv_rast = _nvdiffrast_reference(uvs, faces, verts3d, res)
    nv_cov = int(nv_mask.sum())
    print(f"nvdiffrast coverage: {nv_cov} texels ({100*nv_cov/(res*res):.2f}%)")

    best = None
    for row0_is_v0 in (False, True):
        our_mask, our_pos, our_rast = _ours(uvs, faces, verts3d, res, row0_is_v0)
        inter = int((nv_mask & our_mask).sum())
        union = int((nv_mask | our_mask).sum())
        iou = inter / union if union else 1.0

        both = nv_mask & our_mask
        if int(both.sum()):
            err = (nv_pos[both] - our_pos[both]).norm(dim=-1)
            rmse = float((err ** 2).mean().sqrt())
            pmax = float(err.max())
        else:
            rmse, pmax = float("inf"), float("inf")

        tag = "row0=v0 " if row0_is_v0 else "row0=v1 (GL)"
        print(f"  {tag}: mask IoU {iou:.6f} | pos RMSE {rmse:.3e} | pos max {pmax:.3e}")
        if best is None or iou > best[1]:
            best = (row0_is_v0, iou, rmse, pmax, our_mask, our_rast)

    row0_is_v0, iou, rmse, pmax, our_mask, our_rast = best
    print(f"  -> best orientation: row0_is_v0={row0_is_v0} "
          f"(module default is {uv_rasterize.ROW0_IS_V0})")

    # Is our rast buffer itself a drop-in for nvdiffrast's, or only equivalent
    # end-to-end? Compare the raw triangle-id channel on commonly covered texels.
    both = nv_mask & our_mask
    if int(both.sum()):
        id_agree = float((nv_rast[0, ..., 3][both] == our_rast[0, ..., 3][both]).float().mean())
        bary_err = float((nv_rast[0, ..., :2][both] - our_rast[0, ..., :2][both]).abs().max())
        print(f"  raw buffer: triangle-id agreement {100*id_agree:.3f}% | bary max abs diff {bary_err:.3e}")

    # Coverage disagreement is expected and is NOT itself a defect: at 380k tris in a
    # 2048 atlas a triangle covers ~5 texels, so almost every texel is a boundary texel
    # and the two fill rules tie differently. What matters is not whether the tie is
    # broken identically but whether it changes the baked colour. Two physical criteria:
    #
    #   1. Position error relative to a VOXEL. `pos` feeds bvh.unsigned_distance ->
    #      trilinear grid_sample_3d into the attribute volume, so an error well under
    #      one voxel cannot move the sampled colour meaningfully.
    #   2. Whether disagreement is confined to the coverage BOUNDARY. Structural error
    #      (a flip, a half-texel shift) contaminates chart interiors; a tie does not.
    #      Boundary texels are additionally inpainted downstream (cv2.INPAINT_TELEA),
    #      which is what that step is for.
    only_nv = int((nv_mask & ~our_mask).sum())
    only_ours = int((our_mask & ~nv_mask).sum())
    delta_frac = (only_nv + only_ours) / max(nv_cov, 1)
    print(f"  coverage delta: nv-only {only_nv}, ours-only {only_ours} "
          f"({100*delta_frac:.3f}% of nv coverage)")

    extent = float((verts3d.amax(0) - verts3d.amin(0)).max())
    interior_ok, voxel_ok = True, True
    if int(both.sum()):
        err = (nv_pos[both] - our_pos[both]).norm(dim=-1)
        for grid in (512, 1024):
            vox = extent / grid
            frac = float((err > 0.5 * vox).float().mean())
            print(f"  pos err > half a voxel @ grid {grid} (voxel={vox:.2e}): {100*frac:.4f}%")
            if grid == 1024:
                voxel_ok = frac < 1e-3

        # Boundary test: dilate the disagreement-free region and see whether disputed
        # texels sit on the edge of coverage or inside a chart.
        disp = (nv_mask ^ our_mask)
        m = nv_mask.float().unsqueeze(0).unsqueeze(0)
        eroded = -torch.nn.functional.max_pool2d(-m, 3, stride=1, padding=1)[0, 0] > 0.5
        boundary = nv_mask & ~eroded
        n_disp = int(disp.sum())
        if n_disp:
            on_b = float((disp & (boundary | ~nv_mask)).float().sum() / n_disp)
            print(f"  disputed texels on a coverage boundary: {100*on_b:.2f}%")
            interior_ok = on_b > 0.95

    ok = (rmse < 1e-4) and (row0_is_v0 == uv_rasterize.ROW0_IS_V0) \
        and (delta_frac < 0.01) and voxel_ok and interior_ok
    print(f"  VERDICT: {'PASS' if ok else 'FAIL'}")
    return ok


def synthetic():
    torch.manual_seed(0)
    uvs = torch.tensor(
        [[0.10, 0.10], [0.45, 0.12], [0.20, 0.48],
         [0.55, 0.55], [0.95, 0.60], [0.60, 0.95],
         [0.05, 0.60], [0.30, 0.62], [0.08, 0.92]],
        device="cuda", dtype=torch.float32,
    )
    faces = torch.tensor([[0, 1, 2], [3, 4, 5], [6, 7, 8]], device="cuda", dtype=torch.int64)
    verts3d = torch.tensor(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.2], [0.0, 1.0, -0.3],
         [0.5, 0.5, 0.5], [-0.4, 0.9, 0.1], [0.2, -0.7, 0.8],
         [-1.0, 0.3, 0.4], [0.7, -0.2, -0.6], [0.1, 0.8, 0.9]],
        device="cuda", dtype=torch.float32,
    )
    return compare(uvs, faces, verts3d, 256, "synthetic (3 triangles)")


def from_glb(path, res):
    import trimesh

    scene = trimesh.load(path, process=False)
    mesh = scene.dump(concatenate=True) if hasattr(scene, "dump") else scene
    uv = getattr(getattr(mesh, "visual", None), "uv", None)
    if uv is None:
        print(f"SKIP {path}: no UVs on this mesh")
        return None
    uvs = torch.as_tensor(np.asarray(uv), dtype=torch.float32, device="cuda")
    faces = torch.as_tensor(np.asarray(mesh.faces), dtype=torch.int64, device="cuda")
    verts = torch.as_tensor(np.asarray(mesh.vertices), dtype=torch.float32, device="cuda")
    return compare(uvs, faces, verts, res, f"real mesh {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb", default=None)
    ap.add_argument("--res", type=int, default=2048)
    args = ap.parse_args()

    if not torch.cuda.is_available():
        print("CUDA required (nvdiffrast reference is CUDA-only)")
        sys.exit(2)

    results = [synthetic()]
    if args.glb:
        r = from_glb(args.glb, args.res)
        if r is not None:
            results.append(r)

    print("\n" + "=" * 60)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    sys.exit(0 if all(results) else 1)
