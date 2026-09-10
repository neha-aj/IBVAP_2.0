def compute_delta_pct(current: float, average: float) -> float:
    """`eventsTodayDeltaPct` (API Spec §7): current value vs. a trailing
    average, as a percentage. Guards the zero-average case (a brand new
    system with no history yet) rather than dividing by zero."""
    if average <= 0:
        return 0.0
    return (current - average) / average * 100
