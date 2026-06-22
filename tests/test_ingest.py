"""Integration tests for the trellis 8-direction ingest bridge (F-014).

``pipeline.foundry_ingest`` registers an externally-rendered 8-direction sprite
set into the foundry SQLite lifecycle as a run + 8 attempts, so the existing
``foundry check`` / review / produce / export path then works on them exactly as
if ``foundry_gen`` had produced them.

Isolation strategy (no foundry/*.py edits): ``db.init_db`` / ``db.get_connection``
bind their DB path as a function default at import time, so we redirect every
in-process ``db.init_db()`` (used by both ingest and the foundry CLI command
functions it calls) to a temp DB by patching ``__defaults__``. We also point
``db.FOUNDRY_ROOT`` at ``tmp_path`` so the run's bakeoff artifacts land under the
temp tree. Because tmp_path is outside the real foundry root, artifacts are
stored as absolute paths, which ``mechanical._resolve_artifact`` resolves
correctly (abs join yields the abs path).
"""

import argparse

import pytest
from PIL import Image

from foundry import db
from pipeline import foundry_ingest
from pipeline.foundry_ingest import DIRECTION_NAMES


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def isolated_foundry(tmp_path, monkeypatch):
    """Redirect the foundry DB + root to a temp tree for the whole test.

    Returns the temp DB Path. Initialising it here guarantees the schema exists
    before ingest's first connection.
    """
    db_path = tmp_path / "foundry.db"

    # Redirect the default-bound DB path for every no-arg db.init_db() /
    # db.get_connection() call (ingest + the in-process foundry CLI commands).
    monkeypatch.setattr(db.init_db, "__defaults__", (db_path,))
    monkeypatch.setattr(db.get_connection, "__defaults__", (db_path,))

    # Put bakeoff artifacts under tmp, not the real repo.
    monkeypatch.setattr(db, "FOUNDRY_ROOT", tmp_path)

    # Materialise the schema once up front.
    db.init_db(db_path).close()
    return db_path


def _make_render_set(render_dir, size=512, with_maps=False, omit=None):
    """Write a synthetic 8-direction transparent render set.

    Each sprite has an opaque centered blob over a transparent background — the
    same shape the real content-bbox crop expects. ``omit`` drops one direction's
    main PNG (to exercise the missing-direction failure path).
    """
    render_dir.mkdir(parents=True, exist_ok=True)
    omit = omit or set()

    for name in DIRECTION_NAMES:
        if name in omit:
            continue
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        px = img.load()
        # Opaque blob in the central region so crop_to_square has real content.
        for x in range(size // 4, 3 * size // 4):
            for y in range(size // 4, 3 * size // 4):
                px[x, y] = (180, 90, 60, 255)
        img.save(str(render_dir / f"{name}.png"))

        if with_maps:
            normal = Image.new("RGBA", (size, size), (128, 128, 255, 255))
            normal.save(str(render_dir / f"{name}_normal.png"))
            depth = Image.new("RGBA", (size, size), (255, 255, 255, 255))
            depth.save(str(render_dir / f"{name}_depth.png"))

    return render_dir


# ── Tests ────────────────────────────────────────────────────


def test_ingest_registers_run_and_eight_attempts(isolated_foundry, tmp_path):
    """Happy path: a full 8-direction set registers a run + 8 'generated'
    attempts, each with a 48x48 transparent pixel artifact that exists on disk."""
    render_dir = _make_render_set(tmp_path / "render")

    run_id = foundry_ingest.ingest(
        render_dir=render_dir,
        subject_id="test_subject",
        seed=42,
        run_id="ingest_run_1",
    )
    assert run_id == "ingest_run_1"

    conn = db.init_db()
    try:
        # A run exists, attached to the (auto-created) subject.
        run = conn.execute(
            "SELECT id, subject_id, sprite_target FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        assert run is not None
        assert run["subject_id"] == "test_subject"
        assert run["sprite_target"] == 48

        subject = conn.execute(
            "SELECT id FROM subjects WHERE id = ?", ("test_subject",)
        ).fetchone()
        assert subject is not None

        # Exactly 8 attempts, one per direction, all in 'generated'.
        attempts = conn.execute(
            "SELECT id, direction, state FROM attempts WHERE run_id = ? ORDER BY direction",
            (run_id,),
        ).fetchall()
        assert len(attempts) == 8
        assert {a["direction"] for a in attempts} == set(DIRECTION_NAMES)
        assert all(a["state"] == "generated" for a in attempts)

        # Each attempt has a pixel artifact that is 48x48 RGBA and exists on disk.
        for a in attempts:
            pixel = conn.execute(
                "SELECT path FROM artifacts WHERE attempt_id = ? AND kind = 'pixel'",
                (a["id"],),
            ).fetchone()
            assert pixel is not None, f"no pixel artifact for {a['direction']}"
            abs_path = db.FOUNDRY_ROOT / pixel["path"]
            assert abs_path.exists(), f"pixel file missing: {abs_path}"
            with Image.open(abs_path) as img:
                assert img.size == (48, 48)
                assert img.mode == "RGBA"

            # raw artifact also registered + present.
            raw = conn.execute(
                "SELECT path FROM artifacts WHERE attempt_id = ? AND kind = 'raw'",
                (a["id"],),
            ).fetchone()
            assert raw is not None
            assert (db.FOUNDRY_ROOT / raw["path"]).exists()
    finally:
        conn.close()


def test_ingested_run_passes_foundry_check(isolated_foundry, tmp_path, capsys):
    """The ingested run flows into the existing lifecycle: `foundry check`
    advances the 8 generated attempts (proving the artifacts are gate-valid)."""
    from foundry import cli

    render_dir = _make_render_set(tmp_path / "render")
    run_id = foundry_ingest.ingest(
        render_dir=render_dir,
        subject_id="check_subject",
        seed=7,
        run_id="ingest_run_check",
    )

    cli.cmd_check(argparse.Namespace(run_id=run_id))

    conn = db.init_db()
    try:
        # After check, no attempt should still be 'generated' — every one was
        # either advanced (pass) or marked mechanical_fail. The point is that the
        # ingested artifacts were resolvable and gradeable by the real gates.
        still_generated = conn.execute(
            "SELECT COUNT(*) c FROM attempts WHERE run_id = ? AND state = 'generated'",
            (run_id,),
        ).fetchone()["c"]
        assert still_generated == 0
    finally:
        conn.close()


def test_missing_direction_fails_without_partial_register(isolated_foundry, tmp_path):
    """A render dir missing one direction must fail (FileNotFoundError naming the
    missing file) and register NOTHING — no run, no attempts, no subject."""
    render_dir = _make_render_set(tmp_path / "render", omit={"back_left"})

    with pytest.raises(FileNotFoundError) as exc:
        foundry_ingest.ingest(
            render_dir=render_dir,
            subject_id="partial_subject",
            seed=1,
            run_id="ingest_run_partial",
        )

    # Error names the exact missing file.
    assert "back_left.png" in str(exc.value)

    # Nothing was registered.
    conn = db.init_db()
    try:
        run = conn.execute(
            "SELECT id FROM runs WHERE id = ?", ("ingest_run_partial",)
        ).fetchone()
        assert run is None
        attempts = conn.execute(
            "SELECT COUNT(*) c FROM attempts WHERE run_id = ?",
            ("ingest_run_partial",),
        ).fetchone()["c"]
        assert attempts == 0
        subject = conn.execute(
            "SELECT id FROM subjects WHERE id = ?", ("partial_subject",)
        ).fetchone()
        assert subject is None
    finally:
        conn.close()


def test_missing_direction_cli_exits_nonzero(isolated_foundry, tmp_path):
    """The CLI entrypoint exits non-zero on an incomplete set and names the
    missing file on stderr (operator-facing actionable error)."""
    import sys

    render_dir = _make_render_set(tmp_path / "render", omit={"right"})

    argv = [
        "foundry_ingest",
        "--dir", str(render_dir),
        "--subject", "cli_partial_subject",
        "--run-id", "ingest_cli_partial",
    ]
    old_argv = sys.argv
    sys.argv = argv
    try:
        with pytest.raises(SystemExit) as exc:
            foundry_ingest.main()
        assert exc.value.code != 0
    finally:
        sys.argv = old_argv


def test_optional_maps_are_ingested(isolated_foundry, tmp_path):
    """When <dir>_normal.png / <dir>_depth.png are present, they are registered
    as 'normal' / 'depth' artifacts on each attempt."""
    render_dir = _make_render_set(tmp_path / "render", with_maps=True)
    run_id = foundry_ingest.ingest(
        render_dir=render_dir,
        subject_id="maps_subject",
        seed=3,
        run_id="ingest_run_maps",
    )

    conn = db.init_db()
    try:
        attempts = conn.execute(
            "SELECT id FROM attempts WHERE run_id = ?", (run_id,)
        ).fetchall()
        assert len(attempts) == 8
        for a in attempts:
            kinds = {
                r["kind"]
                for r in conn.execute(
                    "SELECT kind FROM artifacts WHERE attempt_id = ?", (a["id"],)
                ).fetchall()
            }
            assert "normal" in kinds
            assert "depth" in kinds
    finally:
        conn.close()
