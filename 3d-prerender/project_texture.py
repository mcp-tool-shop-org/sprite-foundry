"""Re-texture a baked GLB by projecting the CONCEPT IMAGE onto it.

WHY
---
Faces came out of the pipeline with smeared eyes -- a black bar where the lash, iris and
pupil should be. The stage was located by holding the mesh constant and varying only the
shading: the SAME mesh rendered solid has clean eyelids and lid creases, and rendered
textured has no iris at all. So the geometry is fine and the colour is wrong.

Measured, on lady_decim400k.glb (see the numbers in the module test and the session
record), the chain is:

    concept image     eye ~24 px wide, iris + pupil + sclera all legible
    texture SLAT      64^3 latent  -> the whole eye is ~1.25 latent cells   <-- DIES HERE
    attribute volume  1024^3 grid  -> eye spans 20 x 13 voxels, already a smear
    UV atlas          4096^2       -> eye gets ~40 texels, 1.14x the density of the
                                      surrounding skin, and faithfully carries the smear

Two candidate mechanisms were separated before writing this. Atlas starvation is RULED
OUT: the eye is not short of texels, it has slightly more than neighbouring cheek and
forehead, and there is enough room in ~40 texels to draw an iris that is 24 px in the
source. The information is destroyed upstream, in a 64^3 texture latent, and no
bake-side or unwrap-side change can recover what was never there.

So: stop asking the volume for the colour. The concept image still has the eye. Project
it back on.

WHAT THIS DOES
--------------
For every texel the atlas covers, this takes its 3D surface position (via our own
uv_rasterize, so no nvdiffrast), projects it into the concept camera, and samples the
concept image there. Volume colour is KEPT wherever the projection has nothing to say:
back-facing surface, occluded surface, off-image, or outside the concept's silhouette.
The two are blended by how squarely the surface faces the camera, so the changeover is
gradual and there is no hard seam at the terminator.

THE CAMERA IS CALIBRATED, NOT ASSUMED
-------------------------------------
TRELLIS's own preprocess_image() is replicated to derive the mapping analytically (scale
to max side 1024, alpha bbox, SQUARE crop of side max(w,h) centred on the bbox centre),
then refined by maximising silhouette IoU against the mesh's own front projection, and
the achieved IoU is PRINTED. A calibration that has not been checked against the
silhouette is a guess; --min-iou makes a bad one fail the run instead of quietly
producing a face-shaped smear in the wrong place.

A BODY-WIDE FIT IS NOT GOOD ENOUGH FOR A FACE. Measured here: a fit at body IoU 0.948 put
the eye 7 px low, which is most of a 24 px eye, and the projection then sampled lower-lid
skin where the iris should be. The tell that this was calibration and not geometry was a
CONTROL -- the eyebrow was displaced by the same amount, so nothing local to the eye was
wrong. --align-head re-fits on the head region alone and closes the eye error to 0 px, at
a cost of ~0.011 body IoU. (The brow keeps a genuine +5 px offset afterwards: TRELLIS's
brow ridge really does sit lower than the concept's, which is geometry and not fixable
here.) Any future subject should be checked the same way -- feature offsets in pixels,
against a control feature -- because the body IoU will look fine either way.

LICENCE
-------
torch BSD-3 / numpy BSD-3 / trimesh MIT / OpenCV Apache-2.0 / Pillow HPND, plus our own
uv_rasterize. Deliberately NOT Trellis2TexturingPipeline: that class carries the
top-level `import nvdiffrast.torch` (NVIDIA Source Code License 1-Way Commercial s3.3,
research/evaluation only), which is why retexture_character.py cannot be used for this.

  python project_texture.py --glb <baked.glb> --image <concept.png> --out <out.glb>
"""

import argparse
from pathlib import Path
from typing import Tuple

import cv2
import numpy as np
import torch
import trimesh
import trimesh.visual
from PIL import Image

import uv_rasterize


# uv_rasterize returns row 0 = v0 (see ROW0_IS_V0 there). A baseColorTexture read back out
# of a GLB with PIL is in the OPPOSITE row order, because the bake writes `uv[:,1] = 1-v`
# on export. Mixing the two silently writes projected colour into mirrored atlas rows --
# which does not look like a crash, it looks like plausible texture with polygonal shards
# scattered over the model, and it cost a debugging round here.
#
# MEASURED, not derived: taking the eye's texels via a Blender UV pass (a mapping already
# validated against the render to 0.99/255) and reading the rasteriser's position buffer
# at those indices gives mean position y = -0.035 as-is (the waist, 41.6% covered) and
# y = +0.399 flipped (the eye, 95.5% covered).
#
# bake_glb.py is NOT affected: it builds the atlas in rasteriser order and exports it, and
# never indexes a PIL-loaded atlas with a rasterised mask. This is a hazard of re-entering
# an existing GLB, so it lives here.
ATLAS_ROWS_ARE_FLIPPED = True


def to_raster_rows(a: np.ndarray) -> np.ndarray:
    """PIL/glTF atlas row order -> uv_rasterize row order (and back; it is an involution)."""
    return a[::-1].copy() if ATLAS_ROWS_ARE_FLIPPED else a


# ----------------------------------------------------------------------------------
# concept-side: foreground mask and TRELLIS's square crop
# ----------------------------------------------------------------------------------
def foreground_mask(concept: Image.Image) -> Tuple[np.ndarray, float]:
    """Segment the figure exactly the way the generating pipeline did.

    Uses TRELLIS's own BiRefNet wrapper (MIT; already on the pipeline's import path, so no
    new licence surface) on the SAME 1024-max-side resize TRELLIS feeds it. Matching the
    segmenter matters more than it looks: the framing this drives is derived from the mask
    bbox, so any disagreement with the pipeline's mask is a systematic misprojection.

    A colour threshold was tried first and MEASURED to be unusable on this subject: the
    figure's white cap sits within ~20/255 of the light-grey backdrop while the cast
    shadow sits further from it, so every threshold either swallows the shadow (bbox runs
    to the image edge) or amputates the head (bbox y-start jumps 95 -> 300). No global
    threshold separates them; that is why this loads a model.

    Returns (mask at RESIZED resolution, the resize scale).
    """
    scale = min(1.0, 1024.0 / max(concept.size))
    small = concept
    if scale < 1:
        small = concept.resize((int(concept.width * scale), int(concept.height * scale)),
                               Image.Resampling.LANCZOS)

    from trellis2.pipelines.rembg import BiRefNet
    net = BiRefNet("ZhengPeng7/BiRefNet")
    net.cuda()
    rgba = net(small.convert("RGB").copy())
    alpha = np.array(rgba)[:, :, 3]
    del net
    torch.cuda.empty_cache()
    return alpha > 0.8 * 255, scale          # the same 0.8 cut preprocess_image() uses


def trellis_square_crop(mask: np.ndarray, scale: float) -> Tuple[float, float, float]:
    """Replicate preprocess_image()'s framing. Returns (cx, cy, side) in ORIGINAL pixels.

    TRELLIS takes the alpha bbox on the resized image and crops a SQUARE of side
    max(bbox_w, bbox_h) centred on the bbox centre. The resize is a similarity transform,
    so dividing through by `scale` puts the same square back in original-image pixels --
    where the concept still has its full resolution, which is the whole point of sampling
    from the image instead of the volume.
    """
    ys, xs = np.nonzero(mask)
    x0, x1 = float(xs.min()), float(xs.max())
    y0, y1 = float(ys.min()), float(ys.max())
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    side = float(int(max(x1 - x0, y1 - y0)))
    return cx / scale, cy / scale, side / scale


# ----------------------------------------------------------------------------------
# projection
# ----------------------------------------------------------------------------------
def project(pos: torch.Tensor, cx: float, cy: float, side: float,
            img_w: int, img_h: int) -> torch.Tensor:
    """glTF-space positions -> concept pixel coords.

    glTF is Y-up with +Z toward the front view TRELLIS was conditioned on, and the square
    crop maps to [-0.5, 0.5] in (x, y). Image rows run downward, hence the y negation.
    """
    px = cx + pos[:, 0] * side
    py = cy - pos[:, 1] * side
    return torch.stack([px, py], dim=-1)


def silhouette_iou(pos: torch.Tensor, cx: float, cy: float, side: float,
                   fg: torch.Tensor, img_w: int, img_h: int, res: int = 1024,
                   box=None) -> float:
    """IoU between the mesh's front projection and the concept's foreground mask.

    `box` restricts the objective to an (x0, y0, x1, y1) region of the concept. The body
    silhouette is dominated by the skirt, and MEASURED on this subject a fit that is
    excellent body-wide (IoU 0.948) still lands the brow and the eye 5-7 px low -- most of
    an eye height. That is not a bug in the search: the reconstruction's proportions differ
    slightly from the image, so no single orthographic mapping satisfies both the hem and
    the face. Restricting the objective to the head buys face registration at the cost of a
    few pixels on the body, which is the right trade when the face is the deliverable.
    """
    uvp = project(pos, cx, cy, side, img_w, img_h)
    inb = ((uvp[:, 0] >= 0) & (uvp[:, 0] < img_w) & (uvp[:, 1] >= 0) & (uvp[:, 1] < img_h))
    fgm = fg
    if box is not None:
        x0, y0, x1, y1 = box
        inb = inb & (uvp[:, 0] >= x0) & (uvp[:, 0] < x1) & (uvp[:, 1] >= y0) & (uvp[:, 1] < y1)
        fgm = torch.zeros_like(fg)
        fgm[y0:y1, x0:x1] = fg[y0:y1, x0:x1]
    gx = (uvp[:, 0] / img_w * res).long().clamp(0, res - 1)
    gy = (uvp[:, 1] / img_h * res).long().clamp(0, res - 1)
    a = torch.zeros(res * res, dtype=torch.bool, device=pos.device)
    a[(gy[inb] * res + gx[inb])] = True
    b = torch.nn.functional.interpolate(
        fgm.float()[None, None], size=(res, res), mode="area")[0, 0] > 0.5
    b = b.reshape(-1)
    inter = (a & b).sum().item()
    union = (a | b).sum().item()
    return inter / max(union, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb", required=True, help="baked GLB to re-texture")
    ap.add_argument("--image", required=True, help="the concept image the mesh was generated from")
    ap.add_argument("--out", required=True)
    ap.add_argument("--facing-min", type=float, default=0.15,
                    help="cos(angle) below which the surface is too edge-on to sample; "
                         "the blend fades to volume colour over [facing-min, facing-full]")
    ap.add_argument("--facing-full", type=float, default=0.45,
                    help="cos(angle) at or above which the projection is used at full strength")
    ap.add_argument("--depth-tol", type=float, default=0.01,
                    help="world units a texel may sit behind the front-most surface at its "
                         "pixel and still count as visible")
    ap.add_argument("--strength", type=float, default=1.0,
                    help="global multiplier on the projected contribution (1 = full)")
    ap.add_argument("--min-iou", type=float, default=0.80,
                    help="fail the run if silhouette calibration lands below this")
    ap.add_argument("--no-refine", action="store_true")
    ap.add_argument("--align-head", type=int, default=1,
                    help="1 = after the body-wide fit, re-fit using ONLY the head region "
                         "of the silhouette. A body-wide fit leaves the face several px "
                         "off, which is most of an eye; this trades a little body accuracy "
                         "for a registered face.")
    ap.add_argument("--debug-dir", default=None)
    args = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"

    # --- the baked GLB ---------------------------------------------------------------
    scene = trimesh.load(args.glb)
    mesh = scene.to_mesh() if isinstance(scene, trimesh.Scene) else scene
    mat = mesh.visual.material
    assert mat is not None and mat.baseColorTexture is not None, "GLB has no baked baseColorTexture"
    atlas_img = mat.baseColorTexture
    atlas = to_raster_rows(np.asarray(atlas_img.convert("RGB")))
    T = atlas.shape[0]
    assert atlas.shape[0] == atlas.shape[1], f"non-square atlas {atlas.shape}"

    V = torch.as_tensor(np.asarray(mesh.vertices), dtype=torch.float32, device=dev)
    F = torch.as_tensor(np.asarray(mesh.faces), dtype=torch.int64, device=dev)
    UV = torch.as_tensor(np.asarray(mesh.visual.uv), dtype=torch.float32, device=dev)
    N = torch.as_tensor(np.asarray(mesh.vertex_normals), dtype=torch.float32, device=dev)

    print(f"[glb ] {args.glb}")
    print(f"[glb ] verts {len(V):,} faces {len(F):,} atlas {T}x{T}")
    print(f"[glb ] bbox lo={np.round(mesh.vertices.min(0), 4).tolist()} "
          f"hi={np.round(mesh.vertices.max(0), 4).tolist()}")

    # --- the concept -----------------------------------------------------------------
    concept = Image.open(args.image).convert("RGB")
    cimg = np.asarray(concept)
    ih, iw = cimg.shape[:2]
    fg_small, sc = foreground_mask(concept)
    cx, cy, side = trellis_square_crop(fg_small, sc)
    # upsample the mask to original resolution for the per-texel silhouette test
    fg = np.asarray(Image.fromarray(fg_small.astype(np.uint8) * 255).resize(
        (iw, ih), Image.Resampling.NEAREST)) > 127
    print(f"[img ] {args.image}  {iw}x{ih}  BiRefNet foreground {100*fg.mean():.1f}%")
    print(f"[cal ] TRELLIS square crop: centre=({cx:.1f},{cy:.1f}) side={side:.1f} px")

    # --- rasterise the atlas: 3D position + normal per texel -------------------------
    rast = uv_rasterize.rasterize(UV, F, T)
    covered = rast[0, ..., 3] > 0
    pos, _ = uv_rasterize.interpolate(V, rast, F)
    nrm, _ = uv_rasterize.interpolate(N, rast, F)
    pos = pos[0][covered]
    nrm = nrm[0][covered]
    nrm = nrm / nrm.norm(dim=-1, keepdim=True).clamp(min=1e-8)
    n_tex = pos.shape[0]
    print(f"[rast] {n_tex:,} covered texels ({100*n_tex/(T*T):.1f}% of the atlas)")

    # --- calibrate: refine the mapping by silhouette IoU -----------------------------
    fg_t = torch.as_tensor(fg, device=dev)
    front = pos[nrm[:, 2] > 0]                       # only the camera-facing shell
    iou0 = silhouette_iou(front, cx, cy, side, fg_t, iw, ih)
    best = (iou0, cx, cy, side)
    if not args.no_refine:
        # Coarse-to-fine. A single coarse pass is not enough and the failure is quiet: the
        # search step IS the accuracy floor, and an error of a few pixels is invisible in a
        # body-wide IoU (the skirt dominates the area) while being most of an eye at the
        # head. MEASURED on this subject: a 2%-step search left the brow AND the eye both
        # 5 px low -- a uniform head offset, not an eye-geometry problem, which is what the
        # eyebrow control established. Refining to ~0.5 px steps removes it.
        for step in (0.02, 0.005, 0.00125):
            improved = True
            while improved:
                improved = False
                for ds in (0.0, -step, step):
                    for dx in (0.0, -step, step):
                        for dy in (0.0, -step, step):
                            s2 = best[3] * (1 + ds)
                            c2x = best[1] + dx * best[3]
                            c2y = best[2] + dy * best[3]
                            v = silhouette_iou(front, c2x, c2y, s2, fg_t, iw, ih)
                            if v > best[0] + 1e-6:
                                best = (v, c2x, c2y, s2)
                                improved = True
    iou, cx, cy, side = best
    print(f"[cal ] silhouette IoU (body): {iou0:.4f} initial -> {iou:.4f} refined")

    if args.align_head:
        # Head box = the top of the projected silhouette, in concept pixels.
        uvh = project(front, cx, cy, side, iw, ih)
        top = float(uvh[:, 1].min())
        hb = (0, max(int(top) - 8, 0), iw, min(int(top + 0.20 * side), ih))
        hbest = (silhouette_iou(front, cx, cy, side, fg_t, iw, ih, box=hb), cx, cy, side)
        print(f"[cal ] head box y[{hb[1]}:{hb[3]}]  head IoU before: {hbest[0]:.4f}")
        for step in (0.01, 0.0025, 0.000625):
            improved = True
            while improved:
                improved = False
                for ds in (0.0, -step, step):
                    for dx in (0.0, -step, step):
                        for dy in (0.0, -step, step):
                            s2 = hbest[3] * (1 + ds)
                            c2x = hbest[1] + dx * hbest[3]
                            c2y = hbest[2] + dy * hbest[3]
                            v = silhouette_iou(front, c2x, c2y, s2, fg_t, iw, ih, box=hb)
                            if v > hbest[0] + 1e-6:
                                hbest = (v, c2x, c2y, s2); improved = True
        print(f"[cal ] head IoU after : {hbest[0]:.4f}  "
              f"(body IoU now {silhouette_iou(front, hbest[1], hbest[2], hbest[3], fg_t, iw, ih):.4f})")
        _, cx, cy, side = hbest
    print(f"[cal ] final centre=({cx:.1f},{cy:.1f}) side={side:.1f} px "
          f"({side/1.0:.1f} px per world unit)")

    # Written BEFORE the gate below: when calibration fails, this overlay is the only
    # thing that says WHY (offset vs scale vs mirrored), so it has to survive the exit.
    if args.debug_dir:
        dd = Path(args.debug_dir)
        dd.mkdir(parents=True, exist_ok=True)
        uvd = project(front, cx, cy, side, iw, ih)
        sil = np.zeros((ih, iw), bool)
        okd = ((uvd[:, 0] >= 0) & (uvd[:, 0] < iw) & (uvd[:, 1] >= 0) & (uvd[:, 1] < ih))
        sil[uvd[okd, 1].long().cpu().numpy(), uvd[okd, 0].long().cpu().numpy()] = True
        ov = cimg.copy()
        ov[fg & ~sil] = (0.5 * ov[fg & ~sil] + 0.5 * np.array([255, 0, 0])).astype(np.uint8)
        ov[sil & ~fg] = (0.5 * ov[sil & ~fg] + 0.5 * np.array([0, 128, 255])).astype(np.uint8)
        ov[sil & fg] = (0.6 * ov[sil & fg] + 0.4 * np.array([0, 255, 0])).astype(np.uint8)
        Image.fromarray(ov).save(dd / "calib_silhouette.png")
        print(f"[dbg ] {dd}/calib_silhouette.png  "
              f"(green = agree, RED = concept only, BLUE = mesh only)")

    if iou < args.min_iou:
        raise SystemExit(
            f"CALIBRATION FAILED: silhouette IoU {iou:.4f} < --min-iou {args.min_iou}. "
            "The concept image and the mesh do not line up, so projecting would paint the "
            "face onto the wrong geometry. Check that --image is the image this GLB was "
            "generated from.")

    # --- visibility: front-most surface per concept pixel ----------------------------
    uvp = project(pos, cx, cy, side, iw, ih)
    inb = ((uvp[:, 0] >= 0) & (uvp[:, 0] <= iw - 1) &
           (uvp[:, 1] >= 0) & (uvp[:, 1] <= ih - 1))
    gx = uvp[:, 0].long().clamp(0, iw - 1)
    gy = uvp[:, 1].long().clamp(0, ih - 1)
    flat = gy * iw + gx
    depth = torch.full((ih * iw,), -1e9, device=dev)
    depth.scatter_reduce_(0, flat[inb], pos[inb, 2], reduce="amax", include_self=True)
    visible = pos[:, 2] >= depth[flat] - args.depth_tol

    # --- weight ----------------------------------------------------------------------
    facing = nrm[:, 2]
    w = ((facing - args.facing_min) / (args.facing_full - args.facing_min)).clamp(0, 1)
    w = w * w * (3 - 2 * w)                                       # smoothstep
    on_fig = fg_t.reshape(-1)[flat]
    w = w * inb.float() * visible.float() * on_fig.float() * args.strength

    # --- sample the concept, bilinear ------------------------------------------------
    src = torch.as_tensor(cimg, dtype=torch.float32, device=dev).permute(2, 0, 1)[None] / 255.0
    gu = (uvp[:, 0] / (iw - 1)) * 2 - 1
    gv = (uvp[:, 1] / (ih - 1)) * 2 - 1
    grid = torch.stack([gu, gv], dim=-1)[None, None]
    samp = torch.nn.functional.grid_sample(
        src, grid, mode="bilinear", padding_mode="border", align_corners=True)
    samp = samp[0, :, 0].permute(1, 0)                            # (n_tex, 3)

    # --- composite -------------------------------------------------------------------
    old = torch.as_tensor(atlas, dtype=torch.float32, device=dev).reshape(-1, 3)
    cov_flat = covered.reshape(-1)
    base = old[cov_flat] / 255.0

    # AGREEMENT GUARD. The volume bake and the concept are the same figure lit the same
    # way; they should disagree in fine detail (the iris) and broadly agree on colour. If
    # the atlas row order, the UV convention or the camera calibration is wrong, we are
    # comparing the concept's face against some other part of the body, and this number
    # explodes. This is the check that would have caught the flipped-rows bug immediately
    # instead of it surviving as "plausible texture with shards".
    hi_w = w > 0.5
    if int(hi_w.sum()) > 1000:
        disagree = (samp[hi_w] - base[hi_w]).abs().mean().item() * 255
        print(f"[gard] projected vs existing bake on w>0.5 texels: {disagree:.1f}/255 mean")
        if disagree > 40:
            raise SystemExit(
                f"ALIGNMENT GUARD FAILED: the projected colour disagrees with the existing "
                f"bake by {disagree:.1f}/255 on texels the projection is confident about. "
                f"They are the same figure, so they should broadly agree. Suspect the atlas "
                f"row order (ATLAS_ROWS_ARE_FLIPPED), the UV convention, or the calibration.")

    new = w[:, None] * samp + (1 - w[:, None]) * base
    old[cov_flat] = (new * 255.0).clamp(0, 255)
    out_atlas = old.reshape(T, T, 3).to(torch.uint8).cpu().numpy()

    # Re-inpaint the gutters. Only COVERED texels were rewritten, so every uncovered texel
    # still holds colour inpainted from the ORIGINAL bake. Bilinear filtering at render
    # time reaches across chart edges into those texels, so a stale gutter draws a thin
    # line of old colour along every seam -- which is exactly what showed up as red cracks
    # over the face. bake_glb.py inpaints for the same reason; this keeps the invariant.
    inv = (~covered).cpu().numpy().astype(np.uint8)
    out_atlas = cv2.inpaint(out_atlas, inv, 3, cv2.INPAINT_TELEA)
    out_atlas = to_raster_rows(out_atlas)

    # Per-region breakdown. An aggregate percentage hid a total failure once already:
    # "63.8% occluded" is unremarkable for a closed figure seen from one side, and read as
    # healthy while the entire face was being rejected. Report where it matters.
    REGIONS = {                                    # glTF (x, y-up) boxes on the face
        "eye":      ((-0.0289, -0.0094), (0.4114, 0.4243)),
        "forehead": ((-0.0400, 0.0400), (0.4400, 0.4600)),
        "cheek":    ((-0.0400, -0.0100), (0.3800, 0.4050)),
        "lips":     ((-0.0200, 0.0200), (0.3550, 0.3700)),
    }
    print(f"[reg ] {'region':<9} {'front':>7} {'inb':>7} {'visible':>8} {'facing':>7} "
          f"{'on_fig':>7} {'w>0.5':>7}")
    for rn, ((rx0, rx1), (ry0, ry1)) in REGIONS.items():
        s = ((pos[:, 0] >= rx0) & (pos[:, 0] <= rx1) &
             (pos[:, 1] >= ry0) & (pos[:, 1] <= ry1) & (pos[:, 2] > 0))
        k = int(s.sum())
        if k == 0:
            print(f"[reg ] {rn:<9} {'(empty)':>7}")
            continue
        print(f"[reg ] {rn:<9} {k:>7,} {100*inb[s].float().mean():>6.1f}% "
              f"{100*visible[s].float().mean():>7.1f}% "
              f"{100*(facing[s] > args.facing_min).float().mean():>6.1f}% "
              f"{100*on_fig[s].float().mean():>6.1f}% "
              f"{100*(w[s] > 0.5).float().mean():>6.1f}%")

    print(f"[proj] texels taking projected colour (w>0.5): {100*(w > 0.5).float().mean():.1f}%")
    print(f"[proj] texels keeping volume colour  (w=0)   : {100*(w == 0).float().mean():.1f}%")
    print(f"[proj] rejected: {100*(~inb).float().mean():.1f}% off-image, "
          f"{100*(~visible).float().mean():.1f}% occluded, "
          f"{100*(facing <= args.facing_min).float().mean():.1f}% back/edge-on, "
          f"{100*(~on_fig).float().mean():.1f}% off-silhouette")

    # --- write it back ---------------------------------------------------------------
    src_rgba = np.asarray(atlas_img)
    if atlas_img.mode == "RGBA":
        out_img = Image.fromarray(np.dstack([out_atlas, src_rgba[..., 3]]), mode="RGBA")
    else:
        out_img = Image.fromarray(out_atlas, mode="RGB")

    new_mat = mat.copy()
    new_mat.baseColorTexture = out_img
    mesh.visual = trimesh.visual.TextureVisuals(uv=mesh.visual.uv, material=new_mat)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    mesh.export(args.out)
    print(f"[out ] {args.out} ({Path(args.out).stat().st_size/1e6:.1f} MB)")

    if args.debug_dir:
        dd = Path(args.debug_dir)
        dd.mkdir(parents=True, exist_ok=True)
        Image.fromarray(out_atlas).save(dd / "atlas_projected.png")
        wm = torch.zeros(T * T, device=dev)
        wm[cov_flat] = w
        # written in PIL row order so it overlays the atlas it belongs to
        Image.fromarray(to_raster_rows(
            (wm.reshape(T, T).cpu().numpy() * 255).astype(np.uint8))).save(
            dd / "atlas_weight.png")
        ov = cimg.copy()
        ov[~fg] = (ov[~fg] * 0.35).astype(np.uint8)
        Image.fromarray(ov).save(dd / "concept_foreground.png")
        print(f"[dbg ] wrote {dd}/atlas_projected.png, atlas_weight.png, concept_foreground.png")


if __name__ == "__main__":
    main()
