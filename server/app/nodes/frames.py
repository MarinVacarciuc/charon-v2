"""Frame orientation, applied once per node as close to the source as possible.

Rotation is a PER-NODE property, never a global constant: six cameras get mounted six ways,
and the previous build's single hard-coded 180 degree rotation - inherited from when there
was only one camera - was wrong for every node that did not happen to match it
(REBUILD_PROMPT §0.6.9).

Applied in the poller rather than at the point of use, for two reasons. Recognition is the
one that matters: YuNet detects an upside-down face far worse than an upright one, so a node
whose rotation is not corrected before detection degrades recognition, not just the view.
And doing it once per fetched frame is cheaper than doing it per HTTP request, since the
dashboard pulls each tile several times a second.
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

log = logging.getLogger(__name__)

_ROTATIONS = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}

# Matches the node's own encoder settings, so a re-encoded frame is not visibly worse than
# one that needed no rotation.
_JPEG_QUALITY = 85


def rotate_jpeg(jpeg: bytes, degrees: int) -> bytes:
    """Return the frame rotated by `degrees`, re-encoded. A rotation of 0 - the common case
    for a correctly-mounted node - returns the original bytes untouched, paying nothing."""
    if degrees == 0:
        return jpeg
    code = _ROTATIONS.get(degrees)
    if code is None:
        log.warning("ignoring unsupported rotation %r (expected 0, 90, 180 or 270)", degrees)
        return jpeg
    frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return jpeg  # undecodable: hand back what we got rather than dropping the frame
    ok, buf = cv2.imencode(".jpg", cv2.rotate(frame, code),
                           [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY])
    return buf.tobytes() if ok else jpeg
