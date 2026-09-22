import datetime as dt
import uuid

from app.services.audit_log_service import GENESIS_HASH, _entry_hash


def _at(hour: int = 12) -> dt.datetime:
    return dt.datetime(2026, 9, 23, hour, 0, 0, tzinfo=dt.UTC)


def test_entry_hash_is_deterministic() -> None:
    record_id = uuid.uuid4()
    a = _entry_hash(
        prev_hash=GENESIS_HASH, record_type="snapshot", record_id=record_id,
        action="view", actor="alice", result=None, created_at=_at(),
    )
    b = _entry_hash(
        prev_hash=GENESIS_HASH, record_type="snapshot", record_id=record_id,
        action="view", actor="alice", result=None, created_at=_at(),
    )

    assert a == b


def test_entry_hash_changes_if_the_actor_changes() -> None:
    record_id = uuid.uuid4()
    a = _entry_hash(
        prev_hash=GENESIS_HASH, record_type="snapshot", record_id=record_id,
        action="view", actor="alice", result=None, created_at=_at(),
    )
    b = _entry_hash(
        prev_hash=GENESIS_HASH, record_type="snapshot", record_id=record_id,
        action="view", actor="mallory", result=None, created_at=_at(),
    )

    assert a != b


def test_entry_hash_changes_if_the_previous_hash_changes() -> None:
    """The chaining property: an entry's hash depends on the one before it."""
    record_id = uuid.uuid4()
    a = _entry_hash(
        prev_hash=GENESIS_HASH, record_type="snapshot", record_id=record_id,
        action="view", actor="alice", result=None, created_at=_at(),
    )
    b = _entry_hash(
        prev_hash="f" * 64, record_type="snapshot", record_id=record_id,
        action="view", actor="alice", result=None, created_at=_at(),
    )

    assert a != b


def test_a_missing_actor_or_result_does_not_collide_with_an_empty_string() -> None:
    """`None` is stored as an empty string in the hashed payload (see
    `_entry_hash`'s `actor or ""`) -- confirm that doesn't accidentally make
    `actor=None` and `actor=""` hash the same as some other field shift."""
    record_id = uuid.uuid4()
    a = _entry_hash(
        prev_hash=GENESIS_HASH, record_type="snapshot", record_id=record_id,
        action="view", actor=None, result="verified", created_at=_at(),
    )
    b = _entry_hash(
        prev_hash=GENESIS_HASH, record_type="snapshot", record_id=record_id,
        action="view", actor="verified", result=None, created_at=_at(),
    )

    assert a != b
