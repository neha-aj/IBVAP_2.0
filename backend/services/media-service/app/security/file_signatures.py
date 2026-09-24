# M2.0 security review follow-up (IBVAP_2.0_Security_and_Novelty_Review):
# "Validate MIME and file signatures" for uploaded media. Snapshots/
# recordings are opaque byte blobs this service only hashes/stores/serves --
# never parsed here. Camera source-video uploads (sources.py) are the one
# exception: ingestion-service later feeds the saved file straight into
# `cv2.VideoCapture()`, a real decoder, so an upload that isn't actually a
# video container is the meaningful attack surface (malformed-file decoder
# bugs, disguised non-video payloads). This checks the file's magic bytes
# against known video-container signatures before anything is written to
# disk -- content-based, not filename-extension-based, so a renamed file
# can't bypass it.


def looks_like_video(data: bytes) -> bool:
    """Best-effort content-based check, not a full container parse --
    matches this codebase's existing "classical heuristic, documented
    limitation" convention (see fire-smoke-service's heuristics.py). A
    crafted file could still forge these bytes; this is a first line of
    defense against obviously-wrong uploads, not a substitute for
    ingestion-service's own decoder robustness."""
    if len(data) < 12:
        return False
    if data[4:8] == b"ftyp":  # ISO-BMFF: size(4) + "ftyp" + brand -- mp4/mov/m4v
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"AVI ":
        return True
    if data[:4] == b"\x1aE\xdf\xa3":  # Matroska/WebM
        return True
    return False
