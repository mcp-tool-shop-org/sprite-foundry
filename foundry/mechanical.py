"""
Phase 2C — Mechanical gate functions.

Each gate is a standalone function that inspects one aspect of an attempt's artifacts
and returns structured evidence. Gates never mutate state — the caller decides what
to do with the results.

Evidence structure:
    gate_name:     str  — unique gate identifier
    result:        str  — "pass" or "fail"
    measured:      str  — what was actually found
    expected:      str  — what the gate requires
    artifact_kind: str  — which artifact kind was checked
    artifact_path: str  — relative path to the artifact checked
"""

from pathlib import Path
from PIL import Image

from . import db

FOUNDRY_ROOT = db.FOUNDRY_ROOT


def _resolve_artifact(conn, attempt_id: int, kind: str) -> tuple[Path | None, str | None]:
    """Look up a registered artifact and resolve its path. Returns (abs_path, rel_path) or (None, None)."""
    row = conn.execute(
        "SELECT path FROM artifacts WHERE attempt_id = ? AND kind = ?",
        (attempt_id, kind),
    ).fetchone()
    if not row:
        return None, None
    rel = row["path"]
    return FOUNDRY_ROOT / rel, rel


# ── Individual gates ────────────────────────────────────────

def gate_dimension(conn, attempt_id: int, target: int) -> dict:
    """Check that the pixel artifact is exactly target x target."""
    abs_path, rel_path = _resolve_artifact(conn, attempt_id, "pixel")
    if abs_path is None:
        return dict(
            gate_name="dimension",
            result="fail",
            measured="no pixel artifact registered",
            expected=f"{target}x{target}",
            artifact_kind="pixel",
            artifact_path=None,
        )
    if not abs_path.exists():
        return dict(
            gate_name="dimension",
            result="fail",
            measured=f"file missing: {rel_path}",
            expected=f"{target}x{target}",
            artifact_kind="pixel",
            artifact_path=rel_path,
        )
    img = Image.open(abs_path)
    w, h = img.size
    passed = (w == target and h == target)
    return dict(
        gate_name="dimension",
        result="pass" if passed else "fail",
        measured=f"{w}x{h}",
        expected=f"{target}x{target}",
        artifact_kind="pixel",
        artifact_path=rel_path,
    )


def gate_alpha(conn, attempt_id: int) -> dict:
    """Check that the pixel artifact has an alpha channel (RGBA)."""
    abs_path, rel_path = _resolve_artifact(conn, attempt_id, "pixel")
    if abs_path is None:
        return dict(
            gate_name="alpha",
            result="fail",
            measured="no pixel artifact registered",
            expected="RGBA",
            artifact_kind="pixel",
            artifact_path=None,
        )
    if not abs_path.exists():
        return dict(
            gate_name="alpha",
            result="fail",
            measured=f"file missing: {rel_path}",
            expected="RGBA",
            artifact_kind="pixel",
            artifact_path=rel_path,
        )
    img = Image.open(abs_path)
    return dict(
        gate_name="alpha",
        result="pass" if img.mode == "RGBA" else "fail",
        measured=img.mode,
        expected="RGBA",
        artifact_kind="pixel",
        artifact_path=rel_path,
    )


def gate_corner_transparency(conn, attempt_id: int, target: int) -> dict:
    """Check that at least 3 of 4 corners are transparent (alpha < 128)."""
    abs_path, rel_path = _resolve_artifact(conn, attempt_id, "pixel")
    if abs_path is None:
        return dict(
            gate_name="corner_transparency",
            result="fail",
            measured="no pixel artifact registered",
            expected=">=3/4 corners transparent",
            artifact_kind="pixel",
            artifact_path=None,
        )
    if not abs_path.exists():
        return dict(
            gate_name="corner_transparency",
            result="fail",
            measured=f"file missing: {rel_path}",
            expected=">=3/4 corners transparent",
            artifact_kind="pixel",
            artifact_path=rel_path,
        )
    img = Image.open(abs_path)
    if img.mode != "RGBA":
        return dict(
            gate_name="corner_transparency",
            result="fail",
            measured=f"mode={img.mode}, no alpha to check",
            expected=">=3/4 corners transparent",
            artifact_kind="pixel",
            artifact_path=rel_path,
        )

    w, h = img.size
    corners = [
        img.getpixel((0, 0)),
        img.getpixel((w - 1, 0)),
        img.getpixel((0, h - 1)),
        img.getpixel((w - 1, h - 1)),
    ]
    opaque = sum(1 for c in corners if c[3] > 128)
    transparent = 4 - opaque
    passed = opaque < 3  # fail if 3+ corners are opaque
    return dict(
        gate_name="corner_transparency",
        result="pass" if passed else "fail",
        measured=f"{transparent}/4 corners transparent (alpha values: {[c[3] for c in corners]})",
        expected=">=3/4 corners transparent",
        artifact_kind="pixel",
        artifact_path=rel_path,
    )


def gate_foreground_content(conn, attempt_id: int) -> dict:
    """Check that the raw artifact has foreground content (not an empty frame)."""
    import numpy as np

    abs_path, rel_path = _resolve_artifact(conn, attempt_id, "raw")
    if abs_path is None:
        return dict(
            gate_name="foreground_content",
            result="fail",
            measured="no raw artifact registered",
            expected="foreground pixels > 0",
            artifact_kind="raw",
            artifact_path=None,
        )
    if not abs_path.exists():
        return dict(
            gate_name="foreground_content",
            result="fail",
            measured=f"file missing: {rel_path}",
            expected="foreground pixels > 0",
            artifact_kind="raw",
            artifact_path=rel_path,
        )

    raw_img = Image.open(abs_path).convert("RGBA")
    arr = np.array(raw_img)
    h, w = arr.shape[:2]

    # Estimate background from corners
    corners_arr = np.array([
        arr[0, 0, :3], arr[0, w - 1, :3],
        arr[h - 1, 0, :3], arr[h - 1, w - 1, :3],
    ], dtype=np.float32)
    bg = np.mean(corners_arr, axis=0)
    diff = np.sqrt(np.sum((arr[:, :, :3].astype(np.float32) - bg) ** 2, axis=2))
    fg_count = int(np.sum(diff > 40))
    total = h * w

    return dict(
        gate_name="foreground_content",
        result="pass" if fg_count > 0 else "fail",
        measured=f"{fg_count}/{total} foreground pixels ({fg_count * 100 / total:.1f}%)",
        expected="foreground pixels > 0",
        artifact_kind="raw",
        artifact_path=rel_path,
    )


def gate_single_subject(conn, attempt_id: int, body_class: str = None) -> dict:
    """Check that the raw artifact contains a single subject (thirds analysis).

    Body classes like 'amorphous' and 'wide_squat' have relaxed thresholds
    because their mass naturally spreads across the frame.
    """
    import numpy as np

    abs_path, rel_path = _resolve_artifact(conn, attempt_id, "raw")
    if abs_path is None:
        return dict(
            gate_name="single_subject",
            result="fail",
            measured="no raw artifact registered",
            expected="single subject (center-dominant composition)",
            artifact_kind="raw",
            artifact_path=None,
        )
    if not abs_path.exists():
        return dict(
            gate_name="single_subject",
            result="fail",
            measured=f"file missing: {rel_path}",
            expected="single subject (center-dominant composition)",
            artifact_kind="raw",
            artifact_path=rel_path,
        )

    raw_img = Image.open(abs_path).convert("RGBA")
    arr = np.array(raw_img)
    h, w = arr.shape[:2]

    corners_arr = np.array([
        arr[0, 0, :3], arr[0, w - 1, :3],
        arr[h - 1, 0, :3], arr[h - 1, w - 1, :3],
    ], dtype=np.float32)
    bg = np.mean(corners_arr, axis=0)
    diff = np.sqrt(np.sum((arr[:, :, :3].astype(np.float32) - bg) ** 2, axis=2))
    fg_mask = diff > 40

    total_fg = int(np.sum(fg_mask))
    if total_fg == 0:
        return dict(
            gate_name="single_subject",
            result="fail",
            measured="no foreground detected (0 fg pixels)",
            expected="single subject (center-dominant composition)",
            artifact_kind="raw",
            artifact_path=rel_path,
        )

    third = w // 3
    left_fg = int(np.sum(fg_mask[:, :third]))
    center_fg = int(np.sum(fg_mask[:, third:2 * third]))
    right_fg = int(np.sum(fg_mask[:, 2 * third:]))
    left_r = left_fg / total_fg
    center_r = center_fg / total_fg
    right_r = right_fg / total_fg

    # Body-class-aware thresholds
    # Amorphous/wide creatures naturally spread mass across the frame
    WIDE_BODY_CLASSES = {"amorphous", "wide_squat", "quadruped", "arthropod"}
    if body_class in WIDE_BODY_CLASSES:
        # Relaxed: only fail if extreme split with very weak center
        multi = left_r > 0.35 and right_r > 0.35 and center_r < 0.20
        expected = f"single subject (relaxed for {body_class})"
    else:
        # Standard: significant mass in both edges, weak center
        multi = left_r > 0.25 and right_r > 0.25 and center_r < 0.35
        expected = "single subject (center-dominant composition)"

    return dict(
        gate_name="single_subject",
        result="fail" if multi else "pass",
        measured=f"thirds: L={left_r:.2f} C={center_r:.2f} R={right_r:.2f} (total_fg={total_fg})",
        expected=expected,
        artifact_kind="raw",
        artifact_path=rel_path,
    )


# ── Gate runner ─────────────────────────────────────────────

# Map gate_name → mechanical decision code for failures
GATE_FAIL_CODES = {
    "dimension": "wrong_size",
    "alpha": "no_alpha",
    "corner_transparency": "background_opaque",
    "foreground_content": "empty_frame",
    "single_subject": "multi_subject_composition",
}


def run_all_gates(conn, attempt_id: int, target: int, body_class: str = None) -> list[dict]:
    """Run all mechanical gates on an attempt. Returns list of evidence dicts.

    Args:
        body_class: Optional body class for relaxed gate thresholds (e.g. 'amorphous', 'wide_squat').
                    Loaded from subject config if available.
    """
    return [
        gate_dimension(conn, attempt_id, target),
        gate_alpha(conn, attempt_id),
        gate_corner_transparency(conn, attempt_id, target),
        gate_foreground_content(conn, attempt_id),
        gate_single_subject(conn, attempt_id, body_class=body_class),
    ]
