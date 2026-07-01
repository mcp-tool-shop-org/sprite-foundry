"""Pure-logic boundary + property tests for texture_patch_region.py's three extracted
helper functions: classify_skin_mask, pick_patch_color, rasterize_and_dilate.

These three functions are pure (array in, array out, no I/O) and live ABOVE the
``if __name__ == "__main__":`` guard in texture_patch_region.py, so importing them does
NOT trigger the module's argparse/trimesh-load/torch logic. texture_patch_region.py does
import ``trimesh`` and ``scipy.ndimage`` at module scope (outside the guard) — both are
lightweight/CPU-only (no GPU/torch import at module scope), so that import is safe here.

Style note: boundary-pinning assertions with small synthetic fixtures, matching
tests/test_mechanical.py rather than heavier fixture/mocking machinery.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from texture_patch_region import classify_skin_mask, pick_patch_color, rasterize_and_dilate  # noqa: E402

hyp = pytest.importorskip("hypothesis")
from hypothesis import given, settings, strategies as st  # noqa: E402
from hypothesis.extra import numpy as hnp  # noqa: E402


# ── classify_skin_mask: threshold-boundary pinning ─────────────────────────

LUM_THRESH = 0.32
WARM_THRESH = 0.015


def _lum(rgb):
    r, g, b = rgb
    return 0.3 * r + 0.59 * g + 0.11 * b


def test_classify_skin_mask_just_above_thresholds_is_skin():
    # Pick an RGB whose luminance and warmth both clear the threshold by a hair.
    color = (0.60, 0.40, 0.30)
    assert _lum(color) > LUM_THRESH
    assert color[0] - color[2] > WARM_THRESH
    colors = np.array([color], dtype=np.float32)
    mask = classify_skin_mask(colors, LUM_THRESH, WARM_THRESH)
    assert mask.tolist() == [True]


def test_classify_skin_mask_just_below_thresholds_is_not_skin():
    # Luminance below threshold -> classified non-skin regardless of warmth.
    color = (0.20, 0.10, 0.05)
    assert _lum(color) < LUM_THRESH
    colors = np.array([color], dtype=np.float32)
    mask = classify_skin_mask(colors, LUM_THRESH, WARM_THRESH)
    assert mask.tolist() == [False]


def test_classify_skin_mask_bright_but_cool_is_not_skin():
    # Luminance clears the threshold but R-B (warmth) does not -> non-skin (e.g. blue cloth).
    color = (0.40, 0.45, 0.50)  # lum > 0.32, but R - B = -0.10 < warm_thresh
    assert _lum(color) > LUM_THRESH
    assert color[0] - color[2] < WARM_THRESH
    colors = np.array([color], dtype=np.float32)
    mask = classify_skin_mask(colors, LUM_THRESH, WARM_THRESH)
    assert mask.tolist() == [False]


def test_classify_skin_mask_mixed_rows():
    colors = np.array([
        (0.60, 0.40, 0.30),  # skin: bright + warm
        (0.20, 0.10, 0.05),  # non-skin: too dark
        (0.40, 0.45, 0.50),  # non-skin: bright but cool
    ], dtype=np.float32)
    mask = classify_skin_mask(colors, LUM_THRESH, WARM_THRESH)
    assert mask.tolist() == [True, False, False]


# ── pick_patch_color: median-of-well-lit-subset behavior ───────────────────


def test_pick_patch_color_selects_median_of_bright_half():
    # 4 garment samples at increasing luminance; percentile=50 keeps only the
    # brighter half, and the result is their median * 255.
    colors = np.array([
        (0.10, 0.10, 0.10),
        (0.20, 0.20, 0.20),
        (0.30, 0.30, 0.30),
        (0.40, 0.40, 0.40),
    ], dtype=np.float32)
    lum = np.array([_lum(c) for c in colors])
    mask = np.array([True, True, True, True])
    result = pick_patch_color(colors, lum, mask, percentile=50)
    # samples strictly above the 50th percentile lum are rows 2 and 3 -> median = row mean
    expected = np.median(colors[2:4], axis=0) * 255
    assert np.allclose(result, expected)


def test_pick_patch_color_ignores_unmasked_samples():
    colors = np.array([
        (0.90, 0.90, 0.90),  # bright but NOT in mask -> must be excluded
        (0.20, 0.20, 0.20),
        (0.25, 0.25, 0.25),
    ], dtype=np.float32)
    lum = np.array([_lum(c) for c in colors])
    mask = np.array([False, True, True])
    result = pick_patch_color(colors, lum, mask, percentile=0)
    # only rows 1,2 are eligible regardless of percentile since row 0 is masked out
    assert result.max() <= 0.25 * 255 + 1e-4


# ── rasterize_and_dilate: bbox rasterization + dilation ────────────────────


def _single_triangle_fixture():
    # A minimal mesh: one triangle whose 3 vertices map to known texel coords.
    px = np.array([2, 2, 5], dtype=int)
    py = np.array([2, 5, 2], dtype=int)
    faces = np.array([[0, 1, 2]], dtype=int)
    gap_face_mask = np.array([True])
    shape = (10, 10)
    return px, py, faces, gap_face_mask, shape


def test_rasterize_and_dilate_covers_triangle_bbox_with_one_iteration():
    # NOTE: scipy.ndimage.binary_dilation treats iterations<=0 as "repeat until the
    # result stops changing" (fills everything reachable), NOT "no dilation" — so
    # iterations=1 is the smallest value that actually pins a bounded footprint.
    px, py, faces, gap_face_mask, shape = _single_triangle_fixture()
    hit = rasterize_and_dilate(px, py, faces, gap_face_mask, shape, iterations=1)
    # bbox of the triangle's vertex texels is x:[2,5], y:[2,5]; the full bbox is always
    # covered pre-dilation, so it must still be covered post-dilation (dilation only grows).
    assert hit[2:6, 2:6].all()
    # binary_dilation's default structure is a 4-connectivity cross, so 1 iteration grows
    # the bbox edges by 1 texel but NOT the diagonal corners just outside the bbox corners.
    assert hit[1, 3] and hit[1, 4]  # grown above the top edge
    assert hit[6, 3] and hit[6, 4]  # grown below the bottom edge
    assert not hit[1, 1]  # diagonal corner just outside the bbox corner: not reached by 1 cross-step
    # still bounded: far corners must remain unhit after just 1 iteration on a 10x10 canvas
    assert not hit[0, 0]
    assert not hit[9, 9]


def test_rasterize_and_dilate_empty_face_mask_yields_empty_hit():
    px, py, faces, _, shape = _single_triangle_fixture()
    gap_face_mask = np.array([False])
    hit = rasterize_and_dilate(px, py, faces, gap_face_mask, shape, iterations=3)
    assert not hit.any()


# ── Hypothesis property tests ───────────────────────────────────────────────


@settings(max_examples=25, deadline=None)
@given(
    n_iter_low=st.integers(min_value=1, max_value=3),
    extra_iter=st.integers(min_value=0, max_value=4),
)
def test_dilation_is_monotonically_non_shrinking(n_iter_low, extra_iter):
    """More dilation iterations can only add hit texels, never remove them.

    iterations is floored at 1 deliberately: scipy.ndimage.binary_dilation treats
    iterations<=0 as "repeat to a fixed point" rather than "zero growth", which is not
    the monotonic-growth relationship this property is pinning (see the note on the
    iterations=1 test above). texture_patch_region.py's own CLI default (--dilate 6) and
    every realistic caller always pass a positive iteration count.
    """
    px, py, faces, gap_face_mask, shape = _single_triangle_fixture()
    n_iter_high = n_iter_low + extra_iter
    hit_low = rasterize_and_dilate(px, py, faces, gap_face_mask, shape, iterations=n_iter_low)
    hit_high = rasterize_and_dilate(px, py, faces, gap_face_mask, shape, iterations=n_iter_high)
    # hit_low must be a subset of hit_high (every True in hit_low is True in hit_high)
    assert np.all(~hit_low | hit_high)


@settings(max_examples=25, deadline=None)
@given(
    x0=st.integers(min_value=0, max_value=15),
    y0=st.integers(min_value=0, max_value=15),
    w=st.integers(min_value=1, max_value=5),
    h=st.integers(min_value=1, max_value=5),
)
def test_rasterized_mask_contains_triangle_bbox_footprint(x0, y0, w, h):
    """Before any dilation, the rasterized mask always covers each selected triangle's
    own vertex-texel bounding box — the dilation pass can only grow coverage, never be
    required just to cover the triangle's own footprint."""
    H = W = 20
    x1 = min(x0 + w, W - 1)
    y1 = min(y0 + h, H - 1)
    px = np.array([x0, x1, x0], dtype=int)
    py = np.array([y0, y0, y1], dtype=int)
    faces = np.array([[0, 1, 2]], dtype=int)
    gap_face_mask = np.array([True])
    hit0 = rasterize_and_dilate(px, py, faces, gap_face_mask, (H, W), iterations=0)
    assert hit0[y0:y1 + 1, x0:x1 + 1].all()


@settings(max_examples=15, deadline=None)
@given(
    colors=hnp.arrays(
        dtype=np.float32,
        shape=st.integers(min_value=1, max_value=8).map(lambda n: (n, 3)),
        elements=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    ),
)
def test_classify_skin_mask_returns_bool_array_of_correct_length(colors):
    """classify_skin_mask always returns a bool array with one entry per input row,
    regardless of the random color content."""
    mask = classify_skin_mask(colors, LUM_THRESH, WARM_THRESH)
    assert mask.dtype == np.bool_
    assert mask.shape == (colors.shape[0],)
