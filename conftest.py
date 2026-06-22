"""Root pytest configuration + shared fixtures for the sprite-foundry suite.

This file does two jobs:

1. Quarantine the GPU scripts. ``pipeline/test_hunyuan3d_*.py`` are NOT tests —
   they import ``torch`` at module scope and fire a real diffusion/paint run as
   an import side effect. Under pytest's default ``test_*.py`` discovery they
   would poison collection (CollectError on a torch-less box, or an actual GPU
   run on a CUDA box). ``collect_ignore_glob`` keeps them out of collection.
   (Each script also has an ``if __name__ == "__main__":`` guard so importing
   them can never trigger a run — see those files.)

2. Provide reusable fixtures every module needs:
   - ``db_conn``     : an isolated temp SQLite DB initialised via ``foundry.db``.
   - ``make_png``    : a Pillow-backed synthetic-sprite factory.
   - ``registry``    : a helper that registers subject/run/attempt/artifact rows
                       so gate/decision tests start from a known DB state.

We deliberately do NOT add a ``pyproject.toml``/``pytest.ini`` here — those are
owned by the ci-tooling domain. ``collect_ignore_glob`` in this conftest is the
pytest-supported, config-file-free way to exclude the GPU scripts.
"""

import pytest
from PIL import Image

from foundry import db

# Keep the GPU scripts out of pytest collection (F-002 / F-003).
collect_ignore_glob = ["pipeline/test_*.py"]


# ── DB fixture ──────────────────────────────────────────────


@pytest.fixture
def db_conn(tmp_path):
    """An isolated SQLite registry, freshly initialised per test.

    Uses ``db.init_db`` so the connection exercises the real schema + migration
    path. The DB lives under ``tmp_path`` so WAL/SHM side files never leak into
    the repo and every test starts from an empty registry.
    """
    conn = db.init_db(tmp_path / "foundry.db")
    try:
        yield conn
    finally:
        conn.close()


# ── PNG factory ─────────────────────────────────────────────


@pytest.fixture
def make_png(tmp_path):
    """Factory that writes a synthetic sprite PNG and returns its absolute Path.

    ``mechanical._resolve_artifact`` resolves a registered path as
    ``db.FOUNDRY_ROOT / stored_path``. On every OS, joining a path with an
    *absolute* path yields that absolute path, so storing the temp file's
    absolute path keeps the gate tests fully isolated inside ``tmp_path`` while
    still resolving through the real resolution code.
    """
    counter = {"n": 0}

    def _make(
        size=(48, 48),
        mode="RGBA",
        *,
        fill=None,
        corners_opaque=0,
        subject="center",
        name=None,
    ):
        """Create a PNG and return its absolute Path.

        Args:
            size: (width, height).
            mode: "RGBA" or "RGB".
            fill: optional explicit fill colour; defaults pick a sensible value
                  per mode (transparent for RGBA, mid-grey for RGB).
            corners_opaque: for RGBA, how many of the 4 corners (TL, TR, BL, BR)
                  to make fully opaque white. Used to drive the corner gate.
            subject: composition for the foreground/single-subject gates.
                  "center"  -> one opaque blob in the centre third (passes).
                  "split"   -> two opaque blobs at far left + far right, weak
                               centre (a multi-subject composition).
                  "empty"   -> no foreground (matches the background corners).
                  "none"    -> leave the canvas at its base fill only.
            name: optional filename stem (defaults to an auto-incrementing one).
        """
        counter["n"] += 1
        w, h = size

        if mode == "RGBA":
            base = (0, 0, 0, 0) if fill is None else fill
            img = Image.new("RGBA", (w, h), base)
            px = img.load()

            if subject == "center":
                # Solid opaque blob occupying the centre third.
                third = w // 3
                for x in range(third, 2 * third):
                    for y in range(h // 4, 3 * h // 4):
                        px[x, y] = (200, 50, 50, 255)
            elif subject == "split":
                # Two opaque masses at the far edges, nothing in the centre.
                third = w // 3
                for y in range(h // 4, 3 * h // 4):
                    for x in range(0, max(third // 2, 1)):
                        px[x, y] = (200, 50, 50, 255)
                    for x in range(w - max(third // 2, 1), w):
                        px[x, y] = (50, 50, 200, 255)
            elif subject == "empty":
                pass  # fully transparent — no foreground

            # Force corner opacity for the corner-transparency gate.
            corner_coords = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
            for i in range(min(corners_opaque, 4)):
                cx, cy = corner_coords[i]
                px[cx, cy] = (255, 255, 255, 255)

            out = tmp_path / (name or f"png_{counter['n']}.png")
            img.save(out)
            return out.resolve()

        # RGB (no alpha)
        base = (128, 128, 128) if fill is None else fill
        img = Image.new("RGB", (w, h), base)
        px = img.load()
        if subject == "center":
            third = w // 3
            for x in range(third, 2 * third):
                for y in range(h // 4, 3 * h // 4):
                    px[x, y] = (200, 50, 50)
        elif subject == "split":
            third = w // 3
            for y in range(h // 4, 3 * h // 4):
                for x in range(0, max(third // 2, 1)):
                    px[x, y] = (200, 50, 50)
                for x in range(w - max(third // 2, 1), w):
                    px[x, y] = (50, 50, 200)
        out = tmp_path / (name or f"png_{counter['n']}.png")
        img.save(out)
        return out.resolve()

    return _make


# ── Registry helper ─────────────────────────────────────────


@pytest.fixture
def registry(db_conn):
    """Helpers that populate the registry with known subject/run/attempt rows.

    Returns an object with ``subject``, ``run``, ``attempt`` and ``artifact``
    methods so each test can build exactly the state it needs and keep the body
    of the test about the invariant under test, not boilerplate INSERTs.
    """
    from datetime import datetime, timezone

    conn = db_conn

    def _now():
        return datetime.now(timezone.utc).isoformat()

    class _Registry:
        conn = db_conn

        def subject(self, sid="subj1", display_name="Subject One"):
            conn.execute(
                "INSERT INTO subjects (id, display_name, created_at) VALUES (?, ?, ?)",
                (sid, display_name, _now()),
            )
            conn.commit()
            return sid

        def run(self, run_id="run1", subject_id="subj1", stack="A", seed=7,
                target=48, gen_width=576, gen_height=768):
            conn.execute(
                """INSERT INTO runs (id, subject_id, stack, seed, gen_width,
                                     gen_height, sprite_target, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, subject_id, stack, seed, gen_width, gen_height,
                 target, _now()),
            )
            conn.commit()
            return run_id

        def attempt(self, run_id="run1", direction="front", seed=7,
                    state="generated", parent_attempt_id=None, created_at=None):
            cur = conn.execute(
                """INSERT INTO attempts (run_id, direction, seed, state,
                                         parent_attempt_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (run_id, direction, seed, state, parent_attempt_id,
                 created_at or _now()),
            )
            conn.commit()
            return cur.lastrowid

        def artifact(self, attempt_id, kind, path, width=None, height=None,
                     file_hash=None):
            """Register an artifact. ``path`` may be absolute (tests pass the
            temp-file absolute path so mechanical's FOUNDRY_ROOT-relative
            resolution still resolves to the real file)."""
            cur = conn.execute(
                """INSERT INTO artifacts (attempt_id, kind, path, width, height,
                                          hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (attempt_id, kind, str(path), width, height, file_hash, _now()),
            )
            conn.commit()
            return cur.lastrowid

    return _Registry()
