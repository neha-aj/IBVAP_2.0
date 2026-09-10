"""Camera-offline rule (SAS §5.4.2: "camera offline -> 'Connection Lost'
alert"), driven by the `camera.status_changed` Pub/Sub channel rather than
`cam:{id}:tracks` -- a camera that's offline produces no tracks at all, so
this is the only rule that can ever detect that condition."""

from __future__ import annotations


def is_connection_lost(status: str) -> bool:
    return status == "offline"
