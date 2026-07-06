"""Hand-landmark geometry and gesture detection.

Pure functions over a list of MediaPipe hand landmarks (objects with ``.x``,
``.y`` in normalised image coordinates). No camera, no mouse, no OpenCV — so
this module is trivially unit-testable.
"""

import math

# MediaPipe hand landmark indices.
WRIST = 0
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_TIP = 12
RING_MCP = 13
RING_PIP = 14
RING_TIP = 16
PINKY_MCP = 17
PINKY_PIP = 18
PINKY_TIP = 20

# Knuckles that form a stable palm: their centroid barely moves when fingers
# bend, so it makes a steady, jitter-resistant cursor anchor.
PALM_POINTS = [WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP]

# Bone connections for drawing the 21-point hand skeleton.
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),          # index
    (5, 9), (9, 10), (10, 11), (11, 12),     # middle
    (9, 13), (13, 14), (14, 15), (15, 16),   # ring
    (13, 17), (17, 18), (18, 19), (19, 20),  # pinky
    (0, 17),                                 # palm base
]


def _dist(a, b, w, h):
    return math.hypot((a.x - b.x) * w, (a.y - b.y) * h)


def _finger_folded(lm, tip, pip, margin=0.03):
    # Normalised y grows downward; an extended finger points up, so its tip
    # sits above (smaller y) its PIP joint. Folded = tip clearly below the PIP.
    return lm[tip].y > lm[pip].y + margin


def index_folded(lm):
    return _finger_folded(lm, INDEX_TIP, INDEX_PIP)


def middle_folded(lm):
    return _finger_folded(lm, MIDDLE_TIP, MIDDLE_PIP)


def is_two_finger(lm):
    """Index + middle extended, ring + pinky folded ("peace sign")."""
    ring_down = _finger_folded(lm, RING_TIP, RING_PIP)
    pinky_down = _finger_folded(lm, PINKY_TIP, PINKY_PIP)
    return (not index_folded(lm) and not middle_folded(lm)
            and ring_down and pinky_down)


def palm_center(lm):
    """Normalised (x, y) centroid of the palm knuckles. Stable under finger
    bends, which keeps the cursor steady while clicking."""
    xs = sum(lm[i].x for i in PALM_POINTS) / len(PALM_POINTS)
    ys = sum(lm[i].y for i in PALM_POINTS) / len(PALM_POINTS)
    return xs, ys


def hand_scale(lm, w, h):
    """Palm length (wrist -> middle knuckle). Used to normalise other
    distances so thresholds are the same near or far from the camera."""
    return max(1e-6, _dist(lm[WRIST], lm[MIDDLE_MCP], w, h))


def pinch_dists(lm, w, h):
    """Thumb-tip distance to the index tip and to the middle tip, each divided
    by palm length. Small = that finger is pinched to the thumb. Rotation- and
    scale-independent, so far steadier than 'is the finger bent'."""
    s = hand_scale(lm, w, h)
    di = _dist(lm[THUMB_TIP], lm[INDEX_TIP], w, h) / s
    dm = _dist(lm[THUMB_TIP], lm[MIDDLE_TIP], w, h) / s
    return di, dm


def hand_openness(lm, w, h):
    """Mean fingertip-to-wrist distance / palm length. Big when the hand is
    open (~1.8), small when it's a fist (~1.0). Orientation-independent."""
    s = hand_scale(lm, w, h)
    tips = (INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP)
    return sum(_dist(lm[t], lm[WRIST], w, h) for t in tips) / (4.0 * s)
