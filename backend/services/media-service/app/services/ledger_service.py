"""Client for the independent ledger-service (M25 blockchain-style
anchoring, see that service's own module docstrings for what "independent"
means here and its real limits in this dev deployment).

Both calls are best-effort and never raise: anchoring an evidence file must
never block its capture just because an optional external service is
briefly down, and a `/verify` check that can't reach the ledger must report
that honestly (`"unavailable"`) rather than silently skip the check or
claim success -- same convention NI-7's own `LedgerProvider` contract uses
(`UNAVAILABLE` is a real outcome, never treated as `VERIFIED`).
"""

from __future__ import annotations

import httpx
from ibvap_common.logging import correlated_headers, get_logger

from app.core.config import Settings

logger = get_logger(__name__)


async def anchor(*, record_type: str, record_id: str, content_hash: str, settings: Settings) -> None:
    try:
        async with httpx.AsyncClient(timeout=settings.ledger_request_timeout_seconds) as client:
            response = await client.post(
                f"{settings.ledger_service_url}/ledger/anchor",
                json={"recordType": record_type, "recordId": record_id, "contentHash": content_hash},
                headers={"X-Internal-Token": settings.internal_service_token, **correlated_headers()},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.info("ledger_anchor_skipped", record_id=record_id, error=str(exc))


async def verify(*, record_type: str, record_id: str, content_hash: str, settings: Settings) -> str:
    """One of `"anchored"`, `"not_anchored"`, `"mismatch"`, `"unavailable"`."""
    try:
        async with httpx.AsyncClient(timeout=settings.ledger_request_timeout_seconds) as client:
            response = await client.get(
                f"{settings.ledger_service_url}/ledger/verify",
                params={"recordType": record_type, "recordId": record_id, "contentHash": content_hash},
                headers={"X-Internal-Token": settings.internal_service_token, **correlated_headers()},
            )
            response.raise_for_status()
            return response.json()["status"]
    except httpx.HTTPError as exc:
        logger.info("ledger_verify_unavailable", record_id=record_id, error=str(exc))
        return "unavailable"
