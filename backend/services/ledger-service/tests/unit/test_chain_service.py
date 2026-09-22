import datetime as dt
import uuid

from app.services.chain_service import GENESIS_HASH, _entry_hash


def test_entry_hash_is_deterministic_for_the_same_inputs() -> None:
    record_id = uuid.uuid4()
    created_at = dt.datetime(2026, 9, 23, 12, 0, 0, tzinfo=dt.UTC)

    a = _entry_hash(
        prev_hash=GENESIS_HASH, record_type="snapshot", record_id=record_id,
        content_hash="deadbeef", created_at=created_at,
    )
    b = _entry_hash(
        prev_hash=GENESIS_HASH, record_type="snapshot", record_id=record_id,
        content_hash="deadbeef", created_at=created_at,
    )

    assert a == b


def test_entry_hash_changes_if_the_content_hash_changes() -> None:
    record_id = uuid.uuid4()
    created_at = dt.datetime(2026, 9, 23, 12, 0, 0, tzinfo=dt.UTC)

    a = _entry_hash(
        prev_hash=GENESIS_HASH, record_type="snapshot", record_id=record_id,
        content_hash="deadbeef", created_at=created_at,
    )
    b = _entry_hash(
        prev_hash=GENESIS_HASH, record_type="snapshot", record_id=record_id,
        content_hash="different", created_at=created_at,
    )

    assert a != b


def test_entry_hash_changes_if_the_previous_hash_changes() -> None:
    """This is the actual chaining property: an entry's hash depends on the
    one before it, so editing any past entry changes every hash after it."""
    record_id = uuid.uuid4()
    created_at = dt.datetime(2026, 9, 23, 12, 0, 0, tzinfo=dt.UTC)

    a = _entry_hash(
        prev_hash=GENESIS_HASH, record_type="snapshot", record_id=record_id,
        content_hash="deadbeef", created_at=created_at,
    )
    b = _entry_hash(
        prev_hash="f" * 64, record_type="snapshot", record_id=record_id,
        content_hash="deadbeef", created_at=created_at,
    )

    assert a != b
