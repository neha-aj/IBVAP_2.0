"""Shared name of the Redis set of operator-paused camera ids.

camera-service writes it (POST /cameras/{id}/pause|resume); ingestion stops
publishing frames for a member, and the analysis services skip any frame that
was already queued/in flight when the pause landed -- so a paused camera
produces no further detections, tracks or alerts.
"""

PAUSED_CAMERAS_KEY = "cameras:paused"
