"""Licence-clean UV-space triangle rasteriser.

WHY THIS EXISTS
---------------
Our mesh -> GLB bake had exactly one licence-encumbered step. `o_voxel.postprocess.to_glb`
imports `nvdiffrast` at module scope and calls `dr.RasterizeCudaContext()`, `dr.rasterize()`
and `dr.interpolate()` inside its texture-bake block. nvdiffrast ships under the
"Nvidia Source Code License (1-Way Commercial)", section 3.3:

    "The Work and any derivative works thereof only may be used or intended for use
     non-commercially. ... 'non-commercially' means for research or evaluation purposes
     only and not for any direct or indirect monetary gain."

A studio asset pipeline is neither research nor evaluation, so that call has to go --
independently of whether a given game is sold.

WHAT NVDIFFRAST WAS ACTUALLY DOING
----------------------------------
Only one thing: rasterising the mesh FLAT IN UV SPACE (clip pos = (uv*2-1, 0, 1)) to get,
per texel, a coverage mask and the barycentric-interpolated 3D surface position. That is a
2D triangle rasterisation with barycentric interpolation. Three properties make it far
simpler than the general case nvdiffrast is built for:

  * z is 0 for every vertex, so the depth test is degenerate -- there is nothing to sort.
  * a UV atlas has non-overlapping charts by construction, so at most one triangle covers
    any texel (ties only on shared edges, where both triangles agree on the position).
  * no gradients are needed -- this is a forward bake, not a training loop.

So we do not need a differentiable rasteriser at all. We need a rasteriser.

CONTRACT
--------
`rasterize` and `interpolate` deliberately mirror the nvdiffrast signatures and output
layout for the one call shape we use, so the two implementations can be diffed directly
on real meshes. See verify_uv_rasterize.py -- the orientation and barycentric conventions
below were MEASURED against nvdiffrast, not assumed.

Uses only torch. No new dependencies, no new licence surface.
"""

from typing import Optional, Tuple

import torch


# Determined by measurement against nvdiffrast (verify_uv_rasterize.py), not by reading
# docs. Both are pinned here so a future library change shows up as a verification
# failure rather than as silently mirrored textures.
#
#   ROW0_IS_V0   True  -> output row 0 corresponds to v=0 (array order follows UV).
#                 False -> output row 0 corresponds to v=1 (OpenGL bottom-up).
#   BARY_CHANNELS which vertices the two stored barycentric channels weight.
#
# MEASURED 2026-08-01 (synthetic, 256^2): row0_is_v0=True gives mask IoU 0.999251 and
# position RMSE 9.5e-08; row0_is_v0=False gives IoU 0.104. The "nvdiffrast is OpenGL so
# row 0 is the bottom" assumption is WRONG for this call shape -- it was the first
# default here and the verifier caught it.
ROW0_IS_V0 = True
BARY_CHANNELS = (0, 1)      # rast[...,0]=weight of v0, rast[...,1]=weight of v1.


def rasterize(
    uvs: torch.Tensor,
    faces: torch.Tensor,
    resolution: int,
    max_candidates: int = 1 << 23,
    row0_is_v0: Optional[bool] = None,
) -> torch.Tensor:
    """Rasterise a UV atlas into a texel buffer.

    Args:
        uvs: (V, 2) float tensor of per-vertex UVs in [0, 1].
        faces: (F, 3) int tensor of vertex indices.
        resolution: texture side length T.
        max_candidates: chunking budget -- candidate texels evaluated per batch.
        row0_is_v0: override the measured orientation (verification only).

    Returns:
        (1, T, T, 4) float tensor matching nvdiffrast's layout:
        [..., 0:2] barycentric weights of vertices 0 and 1 (v2 weight is 1-u-v),
        [..., 2]   depth (always 0 here -- the atlas is flat),
        [..., 3]   triangle id PLUS ONE (0 means background).
    """
    if row0_is_v0 is None:
        row0_is_v0 = ROW0_IS_V0

    device = uvs.device
    T = int(resolution)
    faces = faces.long()
    F = faces.shape[0]

    out = torch.zeros((T, T, 4), device=device, dtype=torch.float32)
    if F == 0:
        return out.unsqueeze(0)

    # Triangle corners in texel space. Texel centres sit at integer + 0.5, matching the
    # NDC mapping nvdiffrast uses: ndc = 2*(px + 0.5)/T - 1, and uv = (ndc + 1)/2.
    tri = uvs[faces] * T                                    # (F, 3, 2)
    if not row0_is_v0:
        tri = torch.stack([tri[..., 0], T - tri[..., 1]], dim=-1)

    # Integer bounding box per triangle, clamped to the buffer.
    lo = torch.floor(tri.amin(dim=1) - 0.5).clamp_(0, T - 1).long()   # (F, 2)
    hi = torch.ceil(tri.amax(dim=1) + 0.5).clamp_(0, T).long()        # (F, 2)
    span = (hi - lo).clamp_(min=0)

    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    # Signed area * 2. Degenerate triangles (zero area) cover nothing and would divide
    # by zero -- drop them rather than emitting NaNs into the position map.
    det = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    alive = (span[:, 0] > 0) & (span[:, 1] > 0) & (det.abs() > 1e-12)
    if not bool(alive.any()):
        return out.unsqueeze(0)

    # Bucket triangles by bounding-box side rounded up to a power of two, so every
    # triangle in a bucket shares one dense candidate grid. Small triangles dominate
    # (a 380k-tri mesh in a 4096 atlas averages ~7x7 texels), and a handful of large
    # ones land in their own high buckets instead of forcing a worst-case grid on all.
    side = span.amax(dim=1)
    side_pow2 = torch.where(
        alive,
        torch.pow(2, torch.ceil(torch.log2(side.clamp(min=1).float())).clamp(min=0)).long(),
        torch.zeros_like(side),
    )

    for s in sorted(int(v) for v in torch.unique(side_pow2).tolist()):
        if s <= 0:
            continue
        bucket = torch.nonzero(side_pow2 == s, as_tuple=False).squeeze(1)
        if bucket.numel() == 0:
            continue

        # Chunk so candidate count stays inside the memory budget.
        per_tri = s * s
        step = max(1, int(max_candidates // max(per_tri, 1)))
        dy, dx = torch.meshgrid(
            torch.arange(s, device=device), torch.arange(s, device=device), indexing="ij"
        )
        dx = dx.reshape(1, -1)
        dy = dy.reshape(1, -1)

        for start in range(0, bucket.numel(), step):
            idx = bucket[start:start + step]                 # (n,)
            n = idx.numel()

            X = lo[idx, 0].unsqueeze(1) + dx                 # (n, s*s)
            Y = lo[idx, 1].unsqueeze(1) + dy
            valid = (
                (X < hi[idx, 0].unsqueeze(1)) & (Y < hi[idx, 1].unsqueeze(1))
                & (X < T) & (Y < T)
            )

            sx = X.float() + 0.5
            sy = Y.float() + 0.5

            ai, bi, ci = a[idx], b[idx], c[idx]
            di = det[idx].unsqueeze(1)

            # Edge functions -> barycentric weights for v0, v1, v2.
            w0 = ((bi[:, 0:1] - sx) * (ci[:, 1:2] - sy) - (bi[:, 1:2] - sy) * (ci[:, 0:1] - sx)) / di
            w1 = ((ci[:, 0:1] - sx) * (ai[:, 1:2] - sy) - (ci[:, 1:2] - sy) * (ai[:, 0:1] - sx)) / di
            w2 = 1.0 - w0 - w1

            # Inclusive test: a texel centre exactly on a shared edge is claimed by one
            # of the two triangles, which agree on the interpolated position there.
            eps = -1e-6
            keep = valid & (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
            if not bool(keep.any()):
                continue

            sel = torch.nonzero(keep, as_tuple=False)
            ti = sel[:, 0]
            flat = Y[keep].long() * T + X[keep].long()

            packed = torch.stack(
                [w0[keep], w1[keep], torch.zeros_like(w0[keep]), (idx[ti] + 1).float()],
                dim=-1,
            )
            # Last write wins, matching the chunked overwrite the previous
            # implementation performed across its own face chunks.
            out.view(-1, 4).index_copy_(0, flat, packed)

    return out.unsqueeze(0)


def interpolate(
    attrs: torch.Tensor,
    rast: torch.Tensor,
    faces: torch.Tensor,
) -> Tuple[torch.Tensor, None]:
    """Barycentric-interpolate per-vertex attributes over a rasterised buffer.

    Mirrors nvdiffrast.torch.interpolate for our call shape.

    Args:
        attrs: (1, V, C) or (V, C) per-vertex attributes.
        rast: (1, T, T, 4) buffer from `rasterize`.
        faces: (F, 3) int tensor of vertex indices.

    Returns:
        ((1, T, T, C) interpolated attributes, None) -- tuple shape matches nvdiffrast.
    """
    if attrs.dim() == 3:
        attrs = attrs.squeeze(0)
    faces = faces.long()

    tri_id = rast[0, ..., 3].long() - 1                      # -1 where background
    covered = tri_id >= 0

    T = rast.shape[1]
    C = attrs.shape[-1]
    out = torch.zeros((T, T, C), device=attrs.device, dtype=attrs.dtype)
    if not bool(covered.any()):
        return out.unsqueeze(0), None

    f = faces[tri_id[covered]]                               # (n, 3)
    w0 = rast[0, ..., 0][covered].unsqueeze(-1)
    w1 = rast[0, ..., 1][covered].unsqueeze(-1)
    w2 = 1.0 - w0 - w1

    out[covered] = w0 * attrs[f[:, 0]] + w1 * attrs[f[:, 1]] + w2 * attrs[f[:, 2]]
    return out.unsqueeze(0), None
