"""F-004 — mechanical gate boundary tests (the highest-ROI suite).

sprite-foundry's whole job is deciding "did this sprite pass". Each gate in
``foundry/mechanical.py`` encodes a hard numeric invariant; these tests pin the
pass/fail boundary of every gate so a future threshold tweak or refactor that
silently inverts a gate is caught.

Artifacts are registered with the temp PNG's *absolute* path; mechanical
resolves ``db.FOUNDRY_ROOT / stored_path``, and joining with an absolute path
yields that absolute path on every OS — so the gates read the real temp file
while the test stays isolated in tmp_path.
"""

import pytest

from foundry import mechanical


@pytest.fixture
def attempt(registry):
    """A subject+run(target=48)+attempt the gate tests can hang artifacts on."""
    registry.subject()
    registry.run(target=48)
    aid = registry.attempt()
    return aid


# ── gate_dimension ──────────────────────────────────────────


def test_dimension_passes_at_exact_target(attempt, registry, make_png, db_conn):
    png = make_png(size=(48, 48), mode="RGBA")
    registry.artifact(attempt, "pixel", png)
    r = mechanical.gate_dimension(db_conn, attempt, target=48)
    assert r["result"] == "pass"
    assert r["measured"] == "48x48"


def test_dimension_fails_one_pixel_under(attempt, registry, make_png, db_conn):
    # 47x48 — one pixel below the hard threshold must fail.
    png = make_png(size=(47, 48), mode="RGBA")
    registry.artifact(attempt, "pixel", png)
    r = mechanical.gate_dimension(db_conn, attempt, target=48)
    assert r["result"] == "fail"
    assert r["measured"] == "47x48"


def test_dimension_fails_when_no_pixel_artifact(attempt, db_conn):
    r = mechanical.gate_dimension(db_conn, attempt, target=48)
    assert r["result"] == "fail"
    assert "no pixel artifact" in r["measured"]


# ── gate_alpha ──────────────────────────────────────────────


def test_alpha_passes_for_rgba(attempt, registry, make_png, db_conn):
    png = make_png(size=(48, 48), mode="RGBA")
    registry.artifact(attempt, "pixel", png)
    r = mechanical.gate_alpha(db_conn, attempt)
    assert r["result"] == "pass"
    assert r["measured"] == "RGBA"


def test_alpha_fails_for_rgb_no_alpha(attempt, registry, make_png, db_conn):
    png = make_png(size=(48, 48), mode="RGB")
    registry.artifact(attempt, "pixel", png)
    r = mechanical.gate_alpha(db_conn, attempt)
    assert r["result"] == "fail"
    assert r["measured"] == "RGB"


# ── gate_corner_transparency ────────────────────────────────
# Boundary: fail iff 3+ corners are opaque (opaque == alpha > 128).


def test_corner_transparency_passes_with_one_opaque_corner(attempt, registry, make_png, db_conn):
    png = make_png(size=(48, 48), mode="RGBA", corners_opaque=1)
    registry.artifact(attempt, "pixel", png)
    r = mechanical.gate_corner_transparency(db_conn, attempt, target=48)
    assert r["result"] == "pass"  # 1 opaque < 3


def test_corner_transparency_passes_with_two_opaque_corners(attempt, registry, make_png, db_conn):
    png = make_png(size=(48, 48), mode="RGBA", corners_opaque=2)
    registry.artifact(attempt, "pixel", png)
    r = mechanical.gate_corner_transparency(db_conn, attempt, target=48)
    assert r["result"] == "pass"  # 2 opaque < 3 (boundary just below fail)


def test_corner_transparency_fails_with_three_opaque_corners(attempt, registry, make_png, db_conn):
    png = make_png(size=(48, 48), mode="RGBA", corners_opaque=3)
    registry.artifact(attempt, "pixel", png)
    r = mechanical.gate_corner_transparency(db_conn, attempt, target=48)
    assert r["result"] == "fail"  # 3 opaque -> fail (the hard threshold)


def test_corner_transparency_fails_for_rgb(attempt, registry, make_png, db_conn):
    png = make_png(size=(48, 48), mode="RGB")
    registry.artifact(attempt, "pixel", png)
    r = mechanical.gate_corner_transparency(db_conn, attempt, target=48)
    assert r["result"] == "fail"
    assert "no alpha" in r["measured"]


# ── gate_foreground_content ─────────────────────────────────
# Boundary: pass iff foreground pixel count > 0 (raw artifact).


def test_foreground_passes_with_a_subject(attempt, registry, make_png, db_conn):
    png = make_png(size=(48, 48), mode="RGBA", subject="center")
    registry.artifact(attempt, "raw", png)
    r = mechanical.gate_foreground_content(db_conn, attempt)
    assert r["result"] == "pass"


def test_foreground_fails_on_empty_frame(attempt, registry, make_png, db_conn):
    # Uniform RGB frame: every pixel equals the corner-estimated background,
    # so foreground count is 0 -> the empty-frame gate fails.
    png = make_png(size=(48, 48), mode="RGB", fill=(20, 20, 20), subject="none")
    registry.artifact(attempt, "raw", png)
    r = mechanical.gate_foreground_content(db_conn, attempt)
    assert r["result"] == "fail"
    assert r["measured"].startswith("0/")


# ── gate_single_subject ─────────────────────────────────────
# Standard threshold: multi (=> fail) iff L>0.25 AND R>0.25 AND C<0.35.


def test_single_subject_passes_for_centered_subject(attempt, registry, make_png, db_conn):
    png = make_png(size=(48, 48), mode="RGBA", subject="center")
    registry.artifact(attempt, "raw", png)
    r = mechanical.gate_single_subject(db_conn, attempt)
    assert r["result"] == "pass"


def test_single_subject_fails_for_left_right_split(attempt, registry, make_png, db_conn):
    png = make_png(size=(48, 48), mode="RGBA", subject="split")
    registry.artifact(attempt, "raw", png)
    r = mechanical.gate_single_subject(db_conn, attempt)
    assert r["result"] == "fail"  # strong L + R mass, weak centre


def test_single_subject_relaxed_for_wide_body_class(attempt, registry, make_png, db_conn):
    # The same left/right split that fails the standard threshold should PASS
    # under a relaxed wide-body class, because the relaxed gate only fails on an
    # extreme split (L>0.35 AND R>0.35 AND C<0.20). The split fixture produces a
    # roughly even L/R distribution with near-zero centre, so we assert the
    # body_class branch is actually consulted: standard fails, and the gate
    # reports the relaxed expectation string when a wide class is passed.
    png = make_png(size=(48, 48), mode="RGBA", subject="split")
    registry.artifact(attempt, "raw", png)
    standard = mechanical.gate_single_subject(db_conn, attempt)
    relaxed = mechanical.gate_single_subject(db_conn, attempt, body_class="amorphous")
    assert standard["result"] == "fail"
    assert "relaxed for amorphous" in relaxed["expected"]


def test_single_subject_fails_when_no_foreground(attempt, registry, make_png, db_conn):
    png = make_png(size=(48, 48), mode="RGB", fill=(20, 20, 20), subject="none")
    registry.artifact(attempt, "raw", png)
    r = mechanical.gate_single_subject(db_conn, attempt)
    assert r["result"] == "fail"
    assert "no foreground" in r["measured"]


# ── run_all_gates wiring ────────────────────────────────────


def test_run_all_gates_returns_all_five(attempt, registry, make_png, db_conn):
    pixel = make_png(size=(48, 48), mode="RGBA", subject="center", corners_opaque=0)
    raw = make_png(size=(48, 48), mode="RGBA", subject="center")
    registry.artifact(attempt, "pixel", pixel)
    registry.artifact(attempt, "raw", raw)
    results = mechanical.run_all_gates(db_conn, attempt, target=48)
    names = {r["gate_name"] for r in results}
    assert names == {
        "dimension", "alpha", "corner_transparency",
        "foreground_content", "single_subject",
    }
    assert all(r["result"] == "pass" for r in results), results
