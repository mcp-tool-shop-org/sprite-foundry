"""Direct texture-space patch for a retextured GLB, when a prompt/seed reroll can't fix
coverage (e.g. a garment gap exposing skin that survives 3+ text-level fix attempts).

Classifies vertices as skin vs. non-skin by sampling their baked texture color, restricts
to a height band (raw glTF Y-up axis) you supply, then recolors the *texture texels* for
faces fully inside that region to a color sampled from the same-height non-skin (garment)
texels. This edits texture pixels only — geometry is untouched — so it's low-risk and
survives re-export cleanly. Faces (not just point samples) are rasterized via bbox + a
dilation pass so coverage has no speckling between vertex texel samples (a naive
per-vertex disc-paint leaves a mottled look — proven wrong on sea-witch attempt #1).

Origin: sea-witch's coat-front gap (2026-06-30) survived 3 reroll attempts because the
gap is introduced at the image->3D reconstruction step (TRELLIS inferring an open-front
trenchcoat topology from a single 2D front view), downstream of any 2D-stage prompt fix.

Usage:
  python texture_patch_region.py --mesh <retextured.glb> --out <patched.glb> \
      --y-min -0.45 --y-max 0.16 [--skin-lum 0.32 --skin-warm 0.015 --dilate 6]

Find --y-min/--y-max empirically: raw glTF vertices are Y-up (Blender's importer rotates
to Z-up on load, but this script reads the file directly), so print vertex Y range first
and reason from there (feet near Y-min, head near Y-max of the full mesh).
"""
import argparse
import numpy as np
import trimesh
from pathlib import Path
from PIL import Image
from scipy.ndimage import binary_dilation


def classify_skin_mask(colors, lum_thresh, warm_thresh):
    """Classify per-texel/per-vertex RGB samples as skin (True) vs non-skin (False).

    colors: (N, 3) float array, RGB in [0, 1].
    lum_thresh: luminance threshold above which a sample counts as skin.
    warm_thresh: R-B threshold above which a sample counts as warm/skin-toned.
    Returns: (N,) bool array.
    """
    lum = 0.3 * colors[:, 0] + 0.59 * colors[:, 1] + 0.11 * colors[:, 2]
    warm = colors[:, 0] - colors[:, 2]
    return (lum > lum_thresh) & (warm > warm_thresh)


def pick_patch_color(colors, lum, mask, percentile):
    """Pick a representative patch color from colors[mask], favoring well-lit samples.

    colors: (N, 3) float array, RGB in [0, 1] (or 0-255 scale — caller controls scale).
    lum: (N,) float array of per-sample luminance, same indexing as colors.
    mask: (N,) bool array selecting the candidate pool (e.g. non-skin/garment samples
        within the target band).
    percentile: luminance percentile within the masked pool; only samples at or above
        this percentile contribute (favors well-lit over creased/shadowed samples).
    Returns: (3,) float array — the median color of the selected samples, scaled by 255.
    """
    sel_colors = colors[mask]
    sel_lum = lum[mask]
    thresh = np.percentile(sel_lum, percentile)
    return np.median(sel_colors[sel_lum > thresh], axis=0) * 255


def rasterize_and_dilate(px, py, faces, gap_face_mask, shape, iterations):
    """Rasterize the bbox of each gap face into a hit mask, then binary-dilate it.

    px, py: (N,) int arrays — per-vertex texel x/y coordinates.
    faces: (F, 3) int array — vertex index triplets.
    gap_face_mask: (F,) bool array selecting which faces to rasterize.
    shape: (H, W) tuple for the output mask.
    iterations: binary_dilation iteration count.
    Returns: (H, W) bool array — the dilated hit mask (post-dilation). Callers that want the
        pre-dilate hit count should rasterize separately (this function is pure: array in,
        array out, no I/O), e.g. `hit0 = rasterize_bbox(...); hit = binary_dilation(hit0, ...)`.
    """
    H, W = shape
    gap_faces = faces[gap_face_mask]
    hit = np.zeros((H, W), dtype=bool)
    tpx = px[gap_faces]
    tpy = py[gap_faces]
    for i in range(len(gap_faces)):
        x0, x1 = tpx[i].min(), tpx[i].max()
        y0, y1 = tpy[i].min(), tpy[i].max()
        hit[y0:y1 + 1, x0:x1 + 1] = True
    return binary_dilation(hit, iterations=iterations)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument('--mesh', required=True, help='retextured glb/ply to patch')
    ap.add_argument('--out', required=True)
    ap.add_argument('--y-min', type=float, required=True, help='lower bound of the region to patch (raw Y-up)')
    ap.add_argument('--y-max', type=float, required=True, help='upper bound of the region to patch (raw Y-up)')
    ap.add_argument('--skin-lum', type=float, default=0.32, help='luminance threshold above which a texel counts as skin')
    ap.add_argument('--skin-warm', type=float, default=0.015, help='R-B threshold above which a texel counts as warm/skin-toned')
    ap.add_argument('--color-percentile', type=float, default=60, help='luminance percentile within the band used to pick the patch color from non-skin texels (favors well-lit over creased/shadowed samples)')
    ap.add_argument('--dilate', type=int, default=6, help='binary dilation iterations on the rasterized patch mask (closes gaps between vertex/triangle samples)')
    args = ap.parse_args()

    mesh_path = Path(args.mesh)
    if not mesh_path.exists():
        raise SystemExit(f'--mesh not found: {mesh_path}')

    s = trimesh.load(args.mesh)
    geom_name = list(s.geometry.keys())[0] if isinstance(s, trimesh.Scene) else None
    g = s.geometry[geom_name] if geom_name else s
    V = g.vertices
    UV = g.visual.uv
    F = g.faces
    mat = g.visual.material
    if mat is None or mat.baseColorTexture is None:
        raise SystemExit('mesh has no baked base-color texture to patch')
    orig_rgba = mat.baseColorTexture
    img = orig_rgba.convert('RGB')
    W, H = img.size
    arr = np.asarray(img).astype(np.float32) / 255.0

    print(f'mesh Y range: {V[:,1].min():.3f} to {V[:,1].max():.3f}', flush=True)

    px = np.clip((UV[:, 0] * W).astype(int), 0, W - 1)
    py = np.clip(((1 - UV[:, 1]) * H).astype(int), 0, H - 1)
    colors = arr[py, px]
    lum = 0.3 * colors[:, 0] + 0.59 * colors[:, 1] + 0.11 * colors[:, 2]
    skin_mask = classify_skin_mask(colors, args.skin_lum, args.skin_warm)

    band = (V[:, 1] < args.y_max) & (V[:, 1] > args.y_min)
    gap_mask = skin_mask & band
    print('gap verts:', gap_mask.sum(), '/', len(V), flush=True)
    if gap_mask.sum() == 0:
        raise SystemExit('no skin-classified vertices in the given band -- widen --y-min/--y-max or lower --skin-lum')

    garment_mask = (~skin_mask) & band
    if garment_mask.sum() == 0:
        raise SystemExit('no non-skin (garment) texels found in the band to sample a patch color from')
    target = pick_patch_color(colors, lum, garment_mask, args.color_percentile)
    print('patch color (0-255):', target, flush=True)

    gap_face_mask = gap_mask[F[:, 0]] & gap_mask[F[:, 1]] & gap_mask[F[:, 2]]
    gap_faces = F[gap_face_mask]
    print('gap faces:', len(gap_faces), '/', len(F), flush=True)

    pre_hit = np.zeros((H, W), dtype=bool)
    tpx = px[gap_faces]; tpy = py[gap_faces]
    for i in range(len(gap_faces)):
        x0, x1 = tpx[i].min(), tpx[i].max()
        y0, y1 = tpy[i].min(), tpy[i].max()
        pre_hit[y0:y1 + 1, x0:x1 + 1] = True
    print('hit texels pre-dilate:', pre_hit.sum(), flush=True)

    hit = rasterize_and_dilate(px, py, F, gap_face_mask, (H, W), args.dilate)
    print('hit texels post-dilate:', hit.sum(), flush=True)

    new_img = np.asarray(img).astype(np.float32).copy()
    new_img[hit] = target

    if orig_rgba.mode == 'RGBA':
        alpha = np.asarray(orig_rgba)[:, :, 3]
        rgba = np.dstack([new_img.astype(np.uint8), alpha])
        out_img_full = Image.fromarray(rgba, mode='RGBA')
    else:
        out_img_full = Image.fromarray(new_img.astype(np.uint8), mode='RGB')

    new_mat = mat.copy()
    new_mat.baseColorTexture = out_img_full
    g.visual.material = new_mat
    s.export(args.out)
    print(f'[OUT] {args.out}', flush=True)
    print('=== PATCH COMPLETE ===', flush=True)
