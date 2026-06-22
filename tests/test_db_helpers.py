"""db.py write/validation helper tests (add_review, add_gate_result).

add_review validates review_type against REVIEW_TYPES and decision against
REVIEW_DECISIONS, raising ValueError otherwise — a regression here would let
garbage review codes into the registry and corrupt downstream drift analytics.
These tests pin that the validation actually rejects out-of-enum values and that
valid calls persist.
"""

import pytest

from foundry import db


@pytest.fixture
def attempt(registry):
    registry.subject()
    registry.run()
    return registry.attempt()


def test_add_review_rejects_invalid_review_type(attempt, db_conn):
    with pytest.raises(ValueError):
        db.add_review(db_conn, attempt, "not_a_type", "pass", reviewer="t")


def test_add_review_rejects_invalid_decision(attempt, db_conn):
    with pytest.raises(ValueError):
        db.add_review(db_conn, attempt, "pixel", "not_a_decision", reviewer="t")


def test_add_review_persists_valid_row(attempt, db_conn):
    rid = db.add_review(db_conn, attempt, "pixel", "accept", reviewer="human",
                        code="ok", note="looks good")
    assert isinstance(rid, int)
    rows = db.get_attempt_reviews(db_conn, attempt)
    assert len(rows) == 1
    assert rows[0]["decision"] == "accept"
    assert rows[0]["review_type"] == "pixel"


def test_add_gate_result_persists(attempt, db_conn):
    gid = db.add_gate_result(db_conn, attempt, "dimension", "pass",
                             measured="48x48", expected="48x48")
    assert isinstance(gid, int)
    gates = db.get_attempt_gates(db_conn, attempt)
    assert len(gates) == 1
    assert gates[0]["gate_name"] == "dimension"
    assert gates[0]["result"] == "pass"
