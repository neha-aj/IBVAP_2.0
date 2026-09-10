import pytest

from app.api.internal_events import ingest_external_event
from app.schemas.internal import ExternalDetectionEvent


class FakePublisher:
    def __init__(self) -> None:
        self.drafts = []

    async def persist_and_publish(self, session, draft) -> None:
        self.drafts.append(draft)


@pytest.mark.asyncio
async def test_ingest_external_event_converts_to_event_draft() -> None:
    publisher = FakePublisher()
    payload = ExternalDetectionEvent(
        source_service="anpr-service",
        event_type="Plate Read",
        camera_id="CAM-01",
        object_type="vehicle",
        severity="low",
        requires_review=True,
        description="Plate ABC123 detected (94% confidence)",
    )

    result = await ingest_external_event(payload, session=None, publisher=publisher)

    assert result == {"status": "accepted"}
    assert len(publisher.drafts) == 1
    draft = publisher.drafts[0]
    assert draft.camera_id == "CAM-01"
    assert draft.event_type == "Plate Read"
    assert draft.object_type == "vehicle"
    assert draft.severity == "low"
    assert draft.requires_review is True
    assert draft.description == "Plate ABC123 detected (94% confidence)"


@pytest.mark.asyncio
async def test_ingest_external_event_defaults_requires_review_true() -> None:
    publisher = FakePublisher()
    payload = ExternalDetectionEvent(
        source_service="tamper-service", event_type="Camera Tamper", camera_id="CAM-02", severity="critical",
    )

    await ingest_external_event(payload, session=None, publisher=publisher)
    assert publisher.drafts[0].requires_review is True
