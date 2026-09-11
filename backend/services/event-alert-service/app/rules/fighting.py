"""Fighting Detection (behavioral analytics): pure geometry/statistics, NOT
action recognition -- no action-recognition model exists in this deployment
(same "no model available" situation Fire/Smoke and Camera Tamper are
already honest about, see their own module docstrings), and there's no
labeled fight/altercation footage available to train or validate one
against.

The proxy this uses instead: two `person` tracks that are (a) very close
together and (b) both moving erratically -- rapid, high-variance
displacement between consecutive updates, as opposed to the steady,
mostly-one-direction motion of walking -- for several consecutive updates
in a row. A physical struggle produces exactly this signature (two bodies
in tight, sudden, changing contact); so does, unavoidably, some things that
aren't a fight: two people dancing, play-wrestling, a boisterous group hug,
one person helping another who has stumbled. This is why `engine.py` always
sets `severity="critical", requires_review=True` for this event type -- an
operator must always visually confirm before anything happens, the same
review-required contract every heuristic-based detector in this codebase
already uses.
"""

from __future__ import annotations

import statistics


def is_erratic(displacements: list[float], *, jitter_threshold: float, min_mean_displacement: float) -> bool:
    """True if this track's last few per-update displacement magnitudes
    (already-computed pixel/percent distances between consecutive
    centroids, oldest first) look like erratic struggle-motion rather than
    steady directional walking: a walking person's displacement per update
    is fairly small and consistent (low coefficient of variation); a
    struggle's is large and wildly inconsistent (high coefficient of
    variation). `min_mean_displacement` is a noise floor -- a near-
    stationary track's tiny tracker jitter would otherwise produce a huge,
    meaningless coefficient of variation. Needs at least 3 samples --
    variance over 1-2 points is meaningless."""
    if len(displacements) < 3:
        return False
    mean = statistics.fmean(displacements)
    if mean < min_mean_displacement:
        return False
    stdev = statistics.pstdev(displacements)
    return (stdev / mean) >= jitter_threshold


def pair_is_fighting(
    distance: float, displacements_a: list[float], displacements_b: list[float],
    *, proximity_threshold: float, jitter_threshold: float, min_mean_displacement: float,
) -> bool:
    """Both tracks in the pair must be close (`distance` is the same
    percentage-of-frame bbox-center distance `engine.py::_bbox_center_
    distance` already computes for the track-merge heuristic) AND both
    erratic -- a lone erratic track (someone stumbling, a dropped phone
    grabbed at) or two calm people standing close (a queue, a conversation)
    must not fire alone."""
    if distance > proximity_threshold:
        return False
    kwargs = {"jitter_threshold": jitter_threshold, "min_mean_displacement": min_mean_displacement}
    return is_erratic(displacements_a, **kwargs) and is_erratic(displacements_b, **kwargs)
