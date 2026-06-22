"""Database schema, connection, and query helpers for the foundry registry."""

import sqlite3
from pathlib import Path

FOUNDRY_ROOT = Path(__file__).parent.parent
DB_PATH = FOUNDRY_ROOT / "foundry.db"

SCHEMA_VERSION = 2

DIRECTIONS = [
    "front", "front_left", "left", "back_left",
    "back", "back_right", "right", "front_right",
]

LIFECYCLE_STATES = [
    "generated",
    "mechanical_fail",
    "mechanical_pass",
    "raw_review_pending",
    "raw_rejected",
    "raw_accepted",
    "pixel_review_pending",
    "rejected",
    "accepted",
    "finish_review_pending",
    "finish_rejected",
    "finish_accepted",
    "superseded",
]

TERMINAL_FAIL_STATES = {"mechanical_fail", "raw_rejected", "rejected", "finish_rejected"}
REVIEW_PENDING_STATES = {"raw_review_pending", "pixel_review_pending", "finish_review_pending"}

REVIEW_TYPES = ["mechanical", "raw_source", "pixel", "finish"]
REVIEW_DECISIONS = ["pass", "fail", "accept", "reject", "needs_regen"]

ARTIFACT_KINDS = [
    "raw", "pixel",
    "normal_raw", "normal",
    "depth_raw", "depth",
    "contact_sheet", "raw_inspection",
]

# Valid state transitions: current_state → set of allowed next states
VALID_TRANSITIONS = {
    "generated": {"mechanical_pass", "mechanical_fail"},
    "mechanical_pass": {"raw_review_pending"},
    "raw_review_pending": {"raw_accepted", "raw_rejected"},
    "raw_accepted": {"pixel_review_pending"},
    "pixel_review_pending": {"accepted", "rejected"},
    "accepted": {"finish_review_pending"},
    "finish_review_pending": {"finish_accepted", "finish_rejected"},
    "finish_accepted": {"superseded"},
    # Terminal states have no forward transitions
    "mechanical_fail": set(),
    "raw_rejected": set(),
    "rejected": set(),
    "finish_rejected": set(),
    "superseded": set(),
}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subjects (
    id                TEXT PRIMARY KEY,
    display_name      TEXT NOT NULL,
    role              TEXT,
    consumer          TEXT,
    subject_sheet_path TEXT,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id                 TEXT PRIMARY KEY,
    subject_id         TEXT NOT NULL REFERENCES subjects(id),
    stack              TEXT NOT NULL,
    seed               INTEGER NOT NULL,
    gen_width          INTEGER NOT NULL,
    gen_height         INTEGER NOT NULL,
    sprite_target      INTEGER NOT NULL,
    prompt_hash        TEXT,
    subject_sheet_hash TEXT,
    recipe_json        TEXT,
    created_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             TEXT NOT NULL REFERENCES runs(id),
    direction          TEXT NOT NULL,
    seed               INTEGER NOT NULL,
    state              TEXT NOT NULL DEFAULT 'generated',
    parent_attempt_id  INTEGER REFERENCES attempts(id),
    regen_reason       TEXT,
    regen_note         TEXT,
    created_at         TEXT NOT NULL,
    CHECK (parent_attempt_id <> id)
);

CREATE INDEX IF NOT EXISTS idx_attempts_run_dir
    ON attempts(run_id, direction);

CREATE UNIQUE INDEX IF NOT EXISTS idx_attempts_one_accepted
    ON attempts(run_id, direction)
    WHERE state = 'finish_accepted';

CREATE TABLE IF NOT EXISTS artifacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id  INTEGER NOT NULL REFERENCES attempts(id),
    kind        TEXT NOT NULL,
    path        TEXT NOT NULL,
    width       INTEGER,
    height      INTEGER,
    hash        TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id  INTEGER NOT NULL REFERENCES attempts(id),
    review_type TEXT NOT NULL,
    decision    TEXT NOT NULL,
    code        TEXT,
    note        TEXT,
    reviewer    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finish_captures (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id     INTEGER NOT NULL REFERENCES attempts(id),
    lighting_state TEXT NOT NULL,
    path           TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gate_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id    INTEGER NOT NULL REFERENCES attempts(id),
    gate_name     TEXT NOT NULL,
    result        TEXT NOT NULL,
    measured       TEXT,
    expected       TEXT,
    artifact_kind TEXT,
    artifact_path TEXT,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gate_results_attempt
    ON gate_results(attempt_id);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Get a database connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """v1 -> v2: introduce the gate_results table.

    The CREATE TABLE itself is handled by SCHEMA_SQL's IF NOT EXISTS, so this
    migration only has to guarantee the table is present for an existing v1 DB.
    Running the idempotent DDL here keeps the migration self-contained and
    independent of SCHEMA_SQL ordering.
    """
    conn.execute(
        """CREATE TABLE IF NOT EXISTS gate_results (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id    INTEGER NOT NULL REFERENCES attempts(id),
            gate_name     TEXT NOT NULL,
            result        TEXT NOT NULL,
            measured       TEXT,
            expected       TEXT,
            artifact_kind TEXT,
            artifact_path TEXT,
            created_at    TEXT NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_gate_results_attempt ON gate_results(attempt_id)"
    )


# Ordered migration dispatch: {from_version: migration_fn}. Each fn upgrades a DB
# at `from_version` to `from_version + 1`. New migrations append here in sequence.
MIGRATIONS = {
    1: _migrate_v1_to_v2,
}


def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Initialize the database schema. Idempotent."""
    conn = get_connection(db_path)
    conn.executescript(SCHEMA_SQL)

    # Set schema version if not present
    existing = conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
        return conn

    current_ver = int(existing["value"])
    # Apply migrations in sequence inside a single transaction. Only advance
    # schema_version when the corresponding migration actually runs — never
    # stamp a new version onto an old physical schema.
    while current_ver < SCHEMA_VERSION:
        migration_fn = MIGRATIONS.get(current_ver)
        if migration_fn is None:
            raise RuntimeError(
                f"No migration registered for schema version {current_ver} -> "
                f"{current_ver + 1}; cannot safely upgrade to v{SCHEMA_VERSION}."
            )
        try:
            with conn:  # transaction: migration + version bump commit together
                migration_fn(conn)
                conn.execute(
                    "UPDATE meta SET value = ? WHERE key = 'schema_version'",
                    (str(current_ver + 1),),
                )
        except Exception:
            # `with conn` already rolled back; surface so the caller sees the
            # registry was NOT silently renamed to a version it never reached.
            raise
        current_ver += 1

    return conn


def transition_attempt(conn: sqlite3.Connection, attempt_id: int, new_state: str) -> None:
    """Transition an attempt to a new state. Enforces valid transitions."""
    row = conn.execute(
        "SELECT state FROM attempts WHERE id = ?", (attempt_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"Attempt {attempt_id} not found")

    current = row["state"]
    allowed = VALID_TRANSITIONS.get(current, set())
    if new_state not in allowed:
        raise ValueError(
            f"Invalid transition: {current} → {new_state}. "
            f"Allowed: {allowed or 'none (terminal state)'}"
        )

    # Atomic compare-and-set: guard the UPDATE on the state we validated against.
    # Under WAL concurrency another writer may have advanced the row between the
    # SELECT above and this UPDATE; if so rowcount is 0 and we raise rather than
    # double-apply a transition (TOCTOU race).
    cursor = conn.execute(
        "UPDATE attempts SET state = ? WHERE id = ? AND state = ?",
        (new_state, attempt_id, current),
    )
    if cursor.rowcount != 1:
        raise ValueError(
            f"Transition precondition changed under concurrent write: "
            f"attempt {attempt_id} is no longer in state '{current}' "
            f"(expected for {current} → {new_state})."
        )


def add_review(
    conn: sqlite3.Connection,
    attempt_id: int,
    review_type: str,
    decision: str,
    reviewer: str,
    code: str = None,
    note: str = None,
    created_at: str = None,
) -> int:
    """Add a review record. Returns the review ID."""
    if review_type not in REVIEW_TYPES:
        raise ValueError(f"Invalid review_type: {review_type}. Must be one of {REVIEW_TYPES}")
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"Invalid decision: {decision}. Must be one of {REVIEW_DECISIONS}")

    from datetime import datetime, timezone
    if not created_at:
        created_at = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """INSERT INTO reviews (attempt_id, review_type, decision, code, note, reviewer, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (attempt_id, review_type, decision, code, note, reviewer, created_at),
    )
    return cursor.lastrowid


def get_run_status(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    """Get the status of all attempts in a run, grouped by direction."""
    rows = conn.execute(
        """SELECT a.id, a.direction, a.state, a.seed, a.parent_attempt_id,
                  a.regen_reason, a.created_at
           FROM attempts a
           WHERE a.run_id = ?
           ORDER BY a.direction, a.id""",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_attempt_reviews(conn: sqlite3.Connection, attempt_id: int) -> list[dict]:
    """Get all reviews for an attempt, ordered chronologically."""
    rows = conn.execute(
        """SELECT id, review_type, decision, code, note, reviewer, created_at
           FROM reviews
           WHERE attempt_id = ?
           ORDER BY created_at""",
        (attempt_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_attempt_artifacts(conn: sqlite3.Connection, attempt_id: int) -> list[dict]:
    """Get all artifacts for an attempt."""
    rows = conn.execute(
        """SELECT id, kind, path, width, height, hash, created_at
           FROM artifacts
           WHERE attempt_id = ?
           ORDER BY kind""",
        (attempt_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_attempt_gates(conn: sqlite3.Connection, attempt_id: int) -> list[dict]:
    """Get all gate results for an attempt, ordered chronologically."""
    rows = conn.execute(
        """SELECT id, gate_name, result, measured, expected, artifact_kind, artifact_path, created_at
           FROM gate_results
           WHERE attempt_id = ?
           ORDER BY created_at, gate_name""",
        (attempt_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_gate_result(
    conn: sqlite3.Connection,
    attempt_id: int,
    gate_name: str,
    result: str,
    measured: str = None,
    expected: str = None,
    artifact_kind: str = None,
    artifact_path: str = None,
    created_at: str = None,
) -> int:
    """Record a gate result. Returns the gate_result ID."""
    from datetime import datetime, timezone
    if not created_at:
        created_at = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """INSERT INTO gate_results
           (attempt_id, gate_name, result, measured, expected, artifact_kind, artifact_path, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (attempt_id, gate_name, result, measured, expected, artifact_kind, artifact_path, created_at),
    )
    return cursor.lastrowid


# Defense-in-depth cap on lineage walks; far above any real regen chain depth.
MAX_LINEAGE_DEPTH = 1000


def get_attempt_lineage(conn: sqlite3.Connection, attempt_id: int) -> list[dict]:
    """Walk the parent chain back to the root attempt.

    Guards against a cyclic parent_attempt_id (e.g. a corrupted/edited row)
    that would otherwise loop forever and hang every caller (review-show,
    story, lineage, attempt-detail).
    """
    chain = []
    visited: set[int] = set()
    current_id = attempt_id
    while current_id is not None:
        if current_id in visited:
            raise ValueError(
                f"Cycle detected in attempt lineage at #{current_id}; "
                f"parent_attempt_id chain is corrupt."
            )
        if len(visited) >= MAX_LINEAGE_DEPTH:
            raise ValueError(
                f"Lineage exceeded max depth {MAX_LINEAGE_DEPTH} walking from "
                f"#{attempt_id}; likely corrupt parent_attempt_id chain."
            )
        visited.add(current_id)
        row = conn.execute(
            """SELECT id, direction, state, seed, parent_attempt_id,
                      regen_reason, regen_note, created_at
               FROM attempts WHERE id = ?""",
            (current_id,),
        ).fetchone()
        if not row:
            break
        chain.append(dict(row))
        current_id = row["parent_attempt_id"]
    return chain
