"""db.py lineage cycle-guard tests (backend F-004).

get_attempt_lineage walks parent_attempt_id back to the root. A corrupt/cyclic
parent pointer would loop forever and hang every caller. The fix added a
visited-set cycle guard plus a MAX_LINEAGE_DEPTH cap. These tests assert the
walk TERMINATES (raises) on a cycle instead of hanging, and behaves correctly
on a healthy chain.

Cycle construction is timeout-safe: we build a 2-node cycle by direct UPDATEs.
The DB CHECK(parent_attempt_id <> id) blocks a *self*-parent, so the cycle is
built across two distinct rows (A -> B -> A), which the CHECK permits and which
only the runtime visited-set guard can catch.
"""

import sqlite3

import pytest

from foundry import db


@pytest.fixture
def base(registry):
    registry.subject()
    registry.run()
    return registry


def test_healthy_chain_terminates_at_root(base, db_conn):
    root = base.attempt(direction="front", state="generated")
    child = base.attempt(direction="front", parent_attempt_id=root)
    grandchild = base.attempt(direction="front", parent_attempt_id=child)

    chain = db.get_attempt_lineage(db_conn, grandchild)
    ids = [c["id"] for c in chain]
    assert ids == [grandchild, child, root]  # leaf -> ... -> root order


def test_root_only_chain_is_single_element(base, db_conn):
    root = base.attempt(parent_attempt_id=None)
    chain = db.get_attempt_lineage(db_conn, root)
    assert [c["id"] for c in chain] == [root]


def test_two_node_cycle_raises_not_hangs(base, db_conn):
    """A -> B -> A is a cycle the DB CHECK can't catch (no self-parent). The
    runtime visited-set guard must raise ValueError rather than loop forever."""
    a = base.attempt(direction="front", parent_attempt_id=None)
    b = base.attempt(direction="front", parent_attempt_id=a)
    # Close the loop: make A point back to B.
    db_conn.execute("UPDATE attempts SET parent_attempt_id = ? WHERE id = ?", (b, a))
    db_conn.commit()

    with pytest.raises(ValueError):
        db.get_attempt_lineage(db_conn, a)


def test_cycle_guard_does_not_silently_truncate_a_healthy_chain(base, db_conn):
    """Defensive: the guard must not false-positive on a long-but-acyclic chain.
    Build a deep healthy chain and assert all nodes are returned."""
    prev = base.attempt(direction="front", parent_attempt_id=None)
    ids = [prev]
    for _ in range(20):
        prev = base.attempt(direction="front", parent_attempt_id=prev)
        ids.append(prev)
    chain = db.get_attempt_lineage(db_conn, prev)
    assert [c["id"] for c in chain] == list(reversed(ids))
