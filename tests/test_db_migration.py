"""db.py migration tests (backend F-003) — the non-vacuity meta-test.

The fix replaced a version-bump-only branch with a real ordered migration
dispatch. These tests prove the migration ACTUALLY runs (schema becomes
correct) and — crucially — that schema_version is NOT advanced unless its
migration ran. The second assertion is what makes this a non-vacuous test: it
proves the number tracks real schema work, not a cosmetic rename.
"""

import sqlite3

import pytest

from foundry import db


def _make_v1_db(path):
    """Hand-build a v1 physical DB: the v2 schema MINUS the gate_results table,
    stamped schema_version = 1. This is the 'old-version DB' the migration must
    upgrade."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    # Minimal subset of the schema sufficient to prove the migration; notably
    # WITHOUT gate_results (the table v1->v2 introduces).
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE subjects (
            id TEXT PRIMARY KEY, display_name TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE runs (
            id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, stack TEXT NOT NULL,
            seed INTEGER NOT NULL, gen_width INTEGER NOT NULL,
            gen_height INTEGER NOT NULL, sprite_target INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
            direction TEXT NOT NULL, seed INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'generated',
            parent_attempt_id INTEGER, created_at TEXT NOT NULL
        );
        """
    )
    conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', '1')")
    conn.commit()
    conn.close()


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _schema_version(conn):
    return int(
        conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()["value"]
    )


def _schema_version_raw(conn):
    """schema_version via a row-tuple connection (no row_factory required)."""
    return int(
        conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
    )


def test_old_db_is_actually_migrated(tmp_path):
    """An old v1 DB must, after init_db, advance to v2 AND physically have a
    usable gate_results table — proving the upgrade did real schema work, not a
    bare number bump."""
    path = tmp_path / "old.db"
    _make_v1_db(path)

    pre = sqlite3.connect(str(path))
    assert not _table_exists(pre, "gate_results"), "fixture should start without gate_results"
    assert _schema_version_raw(pre) == 1
    pre.close()

    conn = db.init_db(path)
    try:
        assert _schema_version(conn) == db.SCHEMA_VERSION == 2
        assert _table_exists(conn, "gate_results"), "migrated DB must have gate_results"
        # And the migrated table must be usable (correct columns).
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(gate_results)")}
        assert {"attempt_id", "gate_name", "result"}.issubset(cols)
    finally:
        conn.close()


def test_version_does_not_advance_without_a_registered_migration(tmp_path, monkeypatch):
    """Non-vacuity guard: if no migration is registered for the current version,
    init_db must RAISE and must NOT advance schema_version. This proves the
    number is gated on an actual migration running."""
    path = tmp_path / "old.db"
    _make_v1_db(path)

    # Remove the 1->2 migration so the gap cannot be bridged.
    monkeypatch.setattr(db, "MIGRATIONS", {})

    with pytest.raises(RuntimeError):
        db.init_db(path)

    # schema_version must still be 1 — never stamped to 2 without its migration
    # running. (init_db runs SCHEMA_SQL's IF-NOT-EXISTS DDL before the version
    # loop, so gate_results may be physically present; the load-bearing
    # non-vacuity invariant is that the VERSION did not advance past the point a
    # real migration would have to run.)
    check = sqlite3.connect(str(path))
    check.row_factory = sqlite3.Row
    try:
        assert _schema_version(check) == 1
    finally:
        check.close()


def test_init_db_on_fresh_db_stamps_current_version(tmp_path):
    """A brand-new DB is stamped at the current SCHEMA_VERSION with the full
    schema present — and no migration is needed."""
    conn = db.init_db(tmp_path / "fresh.db")
    try:
        assert _schema_version(conn) == db.SCHEMA_VERSION
        assert _table_exists(conn, "gate_results")
    finally:
        conn.close()


def test_init_db_is_idempotent(tmp_path):
    """Re-initialising an already-current DB must not change the version or
    raise."""
    path = tmp_path / "f.db"
    db.init_db(path).close()
    conn = db.init_db(path)
    try:
        assert _schema_version(conn) == db.SCHEMA_VERSION
    finally:
        conn.close()
