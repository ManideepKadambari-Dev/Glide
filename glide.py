"""
Glide - control the mouse with hand gestures.

  * Move your hand (open palm) -> the cursor follows your palm
  * Pinch thumb + index together -> left click
  * Pinch thumb + middle together -> right click
  * Close your fist to grab, move, then open your hand to drop -> drag & drop
  * Two fingers up (index + middle, "peace sign") -> scroll by moving up/down

The cursor tracks the centre of your palm, so pinching to click doesn't move
it. Pinches and grab/release are distances between fingertips, which are far
steadier to detect than "is this finger bent".

Works across any number of monitors: the camera frame is mapped onto the
full Windows "virtual desktop" that spans every connected display.

Controls (while the preview window is focused):
  q / Esc : quit
  p       : pause / resume cursor control (tracking keeps running)
  f       : flip the camera mirror on/off

Run:
  py glide.py                 # default camera 0
  py glide.py --camera 1      # pick another webcam
  py glide.py --selftest      # validate logic without camera/mouse
"""

import argparse
import ctypes
import math
import os
import sys
import time
from collections import namedtuple
from ctypes import wintypes

# MediaPipe hand-landmark model (Tasks API). Auto-downloaded next to this
# script on first run if absent.
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/1/hand_landmarker.task")
DEFAULT_MODEL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")


# --------------------------------------------------------------------------
# Windows mouse / screen control (ctypes -> user32)
# --------------------------------------------------------------------------
def set_dpi_aware():
    """Make GetSystemMetrics / SetCursorPos report true physical pixels,
    so multi-monitor setups with mixed DPI scaling line up correctly."""
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


user32 = ctypes.windll.user32

# System-metric indices for the bounding box of ALL monitors combined.
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120  # one wheel notch

user32.SetCursorPos.argtypes = [wintypes.INT, wintypes.INT]
user32.SetCursorPos.restype = wintypes.BOOL
user32.mouse_event.argtypes = [
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p
]
user32.GetSystemMetrics.argtypes = [wintypes.INT]
user32.GetSystemMetrics.restype = wintypes.INT
user32.GetDoubleClickTime.restype = wintypes.UINT


def virtual_screen():
    """(x, y, w, h) of the rectangle covering every monitor. x/y may be
    negative when a monitor sits left of / above the primary display."""
    x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return x, y, w, h


def set_cursor(x, y):
    user32.SetCursorPos(int(x), int(y))


def _mouse_event(flags):
    user32.mouse_event(flags, 0, 0, 0, None)


def left_down():
    _mouse_event(MOUSEEVENTF_LEFTDOWN)


def left_up():
    _mouse_event(MOUSEEVENTF_LEFTUP)


def left_click():
    _mouse_event(MOUSEEVENTF_LEFTDOWN)
    _mouse_event(MOUSEEVENTF_LEFTUP)


def right_click():
    _mouse_event(MOUSEEVENTF_RIGHTDOWN)
    _mouse_event(MOUSEEVENTF_RIGHTUP)


def wheel(delta):
    """Scroll the wheel. delta > 0 scrolls up, < 0 scrolls down
    (one notch = WHEEL_DELTA). Negative ints are masked to unsigned for
    the DWORD-typed mouseData argument."""
    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta & 0xFFFFFFFF, None)


# --------------------------------------------------------------------------
# Hand-landmark gesture logic (pure functions -> easy to self-test)
# --------------------------------------------------------------------------
# MediaPipe hand landmark indices we use.
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
_PALM_POINTS = [WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP]

# Finger (tip, pip) pairs for the four non-thumb fingers.
_FINGERS = [
    (INDEX_TIP, INDEX_PIP),
    (MIDDLE_TIP, MIDDLE_PIP),
    (RING_TIP, RING_PIP),
    (PINKY_TIP, PINKY_PIP),
]

# Bone connections for drawing the hand skeleton (Tasks API has no built-in
# drawing util, so we render it ourselves).
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),          # index
    (5, 9), (9, 10), (10, 11), (11, 12),     # middle
    (9, 13), (13, 14), (14, 15), (15, 16),   # ring
    (13, 17), (17, 18), (18, 19), (19, 20),  # pinky
    (0, 17),                                 # palm base
]


def _finger_folded(lm, tip, pip, margin=0.03):
    # Normalised y grows downward; an extended finger points up, so its tip
    # sits above (smaller y) its PIP joint. Folded = tip clearly below the PIP.
    return lm[tip].y > lm[pip].y + margin


def index_folded(lm):
    return _finger_folded(lm, INDEX_TIP, INDEX_PIP)


def middle_folded(lm):
    return _finger_folded(lm, MIDDLE_TIP, MIDDLE_PIP)


def is_two_finger(lm):
    """Index + middle extended, ring + pinky folded ("peace sign").
    Distinct from an open palm (all four up) and from a finger tap."""
    ring_down = _finger_folded(lm, RING_TIP, RING_PIP)
    pinky_down = _finger_folded(lm, PINKY_TIP, PINKY_PIP)
    return (not index_folded(lm) and not middle_folded(lm)
            and ring_down and pinky_down)


def palm_center(lm):
    """Normalised (x, y) centroid of the palm knuckles. Stable under finger
    bends, which keeps the cursor steady while clicking."""
    xs = sum(lm[i].x for i in _PALM_POINTS) / len(_PALM_POINTS)
    ys = sum(lm[i].y for i in _PALM_POINTS) / len(_PALM_POINTS)
    return xs, ys


def _dist(a, b, w, h):
    return math.hypot((a.x - b.x) * w, (a.y - b.y) * h)


def hand_scale(lm, w, h):
    """Palm length (wrist -> middle knuckle). Used to normalise other
    distances so thresholds are the same near or far from the camera."""
    return max(1e-6, _dist(lm[WRIST], lm[MIDDLE_MCP], w, h))


def pinch_dists(lm, w, h):
    """Thumb-tip distance to the index tip and to the middle tip, each divided
    by palm length. Small = that finger is pinched to the thumb. Rotation- and
    scale-independent, so it's far steadier than 'is the finger bent'."""
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


class OneEuroFilter:
    """1-D One Euro filter: heavy smoothing when the signal is slow (kills
    jitter), light smoothing when it's fast (kills lag). The standard filter
    for hand/pointer tracking."""

    def __init__(self, min_cutoff=1.0, beta=0.5, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def reset(self):
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    def __call__(self, x, t):
        if self.x_prev is None:
            self.x_prev, self.t_prev = x, t
            return x
        dt = t - self.t_prev
        if dt <= 0:
            dt = 1e-3
        dx = (x - self.x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self.dx_prev
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self.x_prev
        self.x_prev, self.dx_prev, self.t_prev = x_hat, dx_hat, t
        return x_hat


# --------------------------------------------------------------------------
# Controller: turns per-frame landmarks into cursor moves and clicks
# --------------------------------------------------------------------------
class Config:
    def __init__(self, args):
        self.margin = args.margin              # dead border of the frame
        self.min_cutoff = args.min_cutoff      # One Euro: lower = steadier
        self.beta = args.beta                  # One Euro: higher = less lag
        # Pinch = thumb-to-fingertip distance / palm length (small = pinched),
        # with hysteresis so a pinch registers once without fluttering.
        self.pinch_on = args.pinch             # distance to engage a pinch
        self.pinch_off = args.pinch + 0.20     # ...and to release it
        # Fist ("grab") = hand openness below this; released above pinch range.
        self.fist_on = args.grab               # openness below this = fist
        self.fist_off = args.grab + 0.25       # ...must rise above this to open
        self.click_cooldown = args.click_cooldown  # min seconds between clicks
        self.scroll_speed = args.scroll_speed  # two-finger scroll sensitivity
        self.natural_scroll = args.natural_scroll  # invert scroll direction


class GestureController:
    def __init__(self, cfg):
        self.cfg = cfg
        self.vx, self.vy, self.vw, self.vh = virtual_screen()
        self.sx = self.vx + self.vw / 2.0
        self.sy = self.vy + self.vh / 2.0
        self.enabled = True
        self.grabbing = False      # fist -> left button held down (drag)
        self.left_latch = False    # index pinch currently engaged
        self.right_latch = False   # middle pinch currently engaged
        self.last_left = -1e9
        self.last_right = -1e9
        self.click_lockout = -1e9  # pinch clicks blocked until this time
        self.scroll_prev = None    # last two-finger midpoint y
        self.scroll_accum = 0.0    # fractional wheel ticks not yet emitted
        self.fx = OneEuroFilter(cfg.min_cutoff, cfg.beta)
        self.fy = OneEuroFilter(cfg.min_cutoff, cfg.beta)

    def map_to_screen(self, nx, ny):
        m = self.cfg.margin
        span = max(1e-6, 1.0 - 2.0 * m)
        mx = min(max((nx - m) / span, 0.0), 1.0)
        my = min(max((ny - m) / span, 0.0), 1.0)
        return self.vx + mx * self.vw, self.vy + my * self.vh

    def release(self):
        """Hand lost or control paused: never leave a button stuck down."""
        if self.grabbing:
            left_up()
            self.grabbing = False
        self.left_latch = False
        self.right_latch = False
        self.click_lockout = -1e9
        self.scroll_prev = None
        self.scroll_accum = 0.0
        self.fx.reset()
        self.fy.reset()

    def update(self, lm, w, h, now):
        """Process one frame of landmarks. Returns a status dict for the HUD."""
        scroll = is_two_finger(lm)
        di, dm = pinch_dists(lm, w, h)
        openness = hand_openness(lm, w, h)

        # Fist / grab (hysteresis). A fist means "grab" -> hold the left button.
        fist = openness < (self.cfg.fist_off if self.grabbing else self.cfg.fist_on)
        if scroll:
            fist = False

        # Pinches are only valid on an open hand (so closing into / opening out
        # of a fist can't flick a stray click), and never while grabbing/scroll.
        if fist or scroll or openness < self.cfg.fist_off:
            left_pinch = right_pinch = False
        else:
            on_i = self.cfg.pinch_off if self.left_latch else self.cfg.pinch_on
            on_m = self.cfg.pinch_off if self.right_latch else self.cfg.pinch_on
            left_pinch = di < on_i and di <= dm      # index is the pinched finger
            right_pinch = dm < on_m and dm < di      # middle is the pinched one

        # Two-finger scroll: turn vertical motion of the fingertips into wheel
        # ticks, accumulating the fraction left over each frame.
        if scroll:
            cy = (lm[INDEX_TIP].y + lm[MIDDLE_TIP].y) / 2.0
            if self.scroll_prev is not None:
                dy = self.scroll_prev - cy          # hand moves up -> positive
                if self.cfg.natural_scroll:
                    dy = -dy
                self.scroll_accum += dy * self.cfg.scroll_speed
                ticks = int(self.scroll_accum)
                if ticks and self.enabled:
                    wheel(ticks)
                    self.scroll_accum -= ticks
            self.scroll_prev = cy
        else:
            self.scroll_prev = None
            self.scroll_accum = 0.0

        # Cursor follows the smoothed palm centre (frozen only while scrolling).
        # It keeps following during a grab, so moving a closed fist drags.
        if not scroll:
            nx, ny = palm_center(lm)
            self.sx, self.sy = self.map_to_screen(
                self.fx(nx, now), self.fy(ny, now))
            if self.enabled:
                set_cursor(self.sx, self.sy)

        clicked = None
        if self.enabled:
            # Drag: closing to a fist grabs (button down); opening drops it.
            if fist and not self.grabbing:
                left_down()
                self.grabbing = True
            elif not fist and self.grabbing:
                left_up()
                self.grabbing = False

            # Block pinch clicks briefly around a grab so the closing/opening
            # motion can't register a stray click.
            if fist:
                self.click_lockout = now + 0.30
            allow = now >= self.click_lockout

            # Left click on the engage edge of an index pinch.
            if left_pinch and not self.left_latch:
                self.left_latch = True
                if allow and (now - self.last_left) > self.cfg.click_cooldown:
                    left_click()
                    self.last_left = now
                    clicked = "left"
            elif not left_pinch:
                self.left_latch = False

            # Right click on the engage edge of a middle pinch.
            if right_pinch and not self.right_latch:
                self.right_latch = True
                if allow and (now - self.last_right) > self.cfg.click_cooldown:
                    right_click()
                    self.last_right = now
                    clicked = "right"
            elif not right_pinch:
                self.right_latch = False

        gesture = ("scroll" if scroll else "drag" if self.grabbing else
                   "left" if left_pinch else "right" if right_pinch else "move")
        return {"gesture": gesture, "clicked": clicked,
                "di": di, "dm": dm, "open": openness}


# --------------------------------------------------------------------------
# Self-test: exercise the logic without a camera or moving the real mouse
# --------------------------------------------------------------------------
def selftest():
    Pt = namedtuple("Pt", "x y")

    # A roughly realistic open right hand (palm to camera, fingers up), in a
    # square coordinate space so distances aren't aspect-distorted.
    BASE = {
        WRIST: (0.50, 0.95),
        1: (0.38, 0.85), 2: (0.33, 0.78), 3: (0.30, 0.72), THUMB_TIP: (0.28, 0.66),
        INDEX_MCP: (0.44, 0.68), INDEX_PIP: (0.43, 0.55), 7: (0.42, 0.47),
        INDEX_TIP: (0.41, 0.40),
        MIDDLE_MCP: (0.50, 0.66), MIDDLE_PIP: (0.50, 0.52), 11: (0.50, 0.44),
        MIDDLE_TIP: (0.50, 0.36),
        RING_MCP: (0.56, 0.67), RING_PIP: (0.57, 0.54), 15: (0.575, 0.47),
        RING_TIP: (0.58, 0.40),
        PINKY_MCP: (0.62, 0.70), PINKY_PIP: (0.63, 0.58), 19: (0.635, 0.52),
        PINKY_TIP: (0.64, 0.46),
    }

    def hand(mode="open", shift=0.0):
        lm = [Pt(BASE[i][0] + shift, BASE[i][1]) for i in range(21)]
        if mode == "pinch_index":              # thumb tip meets index tip
            lm[THUMB_TIP] = Pt(lm[INDEX_TIP].x, lm[INDEX_TIP].y)
        elif mode == "pinch_middle":           # thumb tip meets middle tip
            lm[THUMB_TIP] = Pt(lm[MIDDLE_TIP].x, lm[MIDDLE_TIP].y)
        elif mode == "fist":                   # all fingertips curled to palm
            for tip, mcp in ((INDEX_TIP, INDEX_MCP), (MIDDLE_TIP, MIDDLE_MCP),
                             (RING_TIP, RING_MCP), (PINKY_TIP, PINKY_MCP)):
                lm[tip] = Pt(lm[mcp].x, lm[mcp].y - 0.01)
            lm[THUMB_TIP] = Pt(0.50 + shift, 0.66)
        elif mode == "peace":                  # index+middle up, ring+pinky down
            lm[RING_TIP] = Pt(lm[RING_MCP].x, lm[RING_MCP].y + 0.02)
            lm[PINKY_TIP] = Pt(lm[PINKY_MCP].x, lm[PINKY_MCP].y + 0.02)
        return lm

    w, h = 1000, 1000
    x, y, vw, vh = virtual_screen()
    print(f"Virtual desktop: origin=({x},{y}) size={vw}x{vh}")
    print(f"Monitors reported: {user32.GetSystemMetrics(80)}")  # SM_CMONITORS

    cfg = Config(argparse.Namespace(
        margin=0.1, min_cutoff=1.0, beta=0.5, pinch=0.5, grab=1.2,
        click_cooldown=0.0, scroll_speed=1500.0, natural_scroll=False))

    # Geometry sanity: pinches shrink the right distance; a fist is not open.
    di_o, dm_o = pinch_dists(hand("open"), w, h)
    assert di_o > 0.5 and dm_o > 0.5, f"open hand looks pinched: {di_o:.2f},{dm_o:.2f}"
    di_i, dm_i = pinch_dists(hand("pinch_index"), w, h)
    assert di_i < 0.5 and di_i < dm_i, f"index pinch geometry off: {di_i:.2f},{dm_i:.2f}"
    di_m, dm_m = pinch_dists(hand("pinch_middle"), w, h)
    assert dm_m < 0.5 and dm_m < di_m, f"middle pinch geometry off: {di_m:.2f},{dm_m:.2f}"
    assert hand_openness(hand("open"), w, h) > 1.45, "open hand not open?"
    assert hand_openness(hand("fist"), w, h) < 1.2, "fist not closed?"
    assert is_two_finger(hand("peace")), "peace sign not detected"
    assert not is_two_finger(hand("open")), "open hand misread as peace"

    # State machine, with real mouse calls stubbed so nothing actually happens.
    mod = sys.modules[__name__]
    names = ("set_cursor", "left_down", "left_up", "left_click", "right_click", "wheel")
    saved = {n: getattr(mod, n) for n in names}
    calls = []
    try:
        mod.set_cursor = lambda px, py: None
        mod.left_down = lambda: calls.append("LD")
        mod.left_up = lambda: calls.append("LU")
        mod.left_click = lambda: calls.append("LC")
        mod.right_click = lambda: calls.append("RC")
        mod.wheel = lambda d: calls.append(("W", d))

        # Left click: pinch index, release. One click on the engage edge.
        calls.clear()
        c = GestureController(cfg)
        c.update(hand("open"), w, h, 0.00)
        s = c.update(hand("pinch_index"), w, h, 0.03)
        assert s["gesture"] == "left", f"expected left, got {s['gesture']}"
        c.update(hand("pinch_index"), w, h, 0.06)     # held pinch, no repeat
        c.update(hand("open"), w, h, 0.09)
        assert calls == ["LC"], f"left click wrong: {calls}"

        # Double click: two separate pinches each fire a click, so pinching
        # twice quickly is a double-click at the OS level.
        calls.clear()
        c = GestureController(cfg)
        c.update(hand("open"), w, h, 0.00)
        c.update(hand("pinch_index"), w, h, 0.03)     # click 1
        c.update(hand("open"), w, h, 0.06)
        c.update(hand("pinch_index"), w, h, 0.09)     # click 2 (quick)
        c.update(hand("open"), w, h, 0.12)
        assert calls == ["LC", "LC"], f"double pinch should be two clicks: {calls}"

        # Right click: pinch middle.
        calls.clear()
        c = GestureController(cfg)
        c.update(hand("open"), w, h, 0.00)
        s = c.update(hand("pinch_middle"), w, h, 0.03)
        assert s["gesture"] == "right", f"expected right, got {s['gesture']}"
        c.update(hand("open"), w, h, 0.06)
        assert calls == ["RC"], f"right click wrong: {calls}"

        # Drag: fist grabs (button down), moving drags, opening drops (up).
        calls.clear()
        c = GestureController(cfg)
        c.update(hand("open"), w, h, 0.00)
        s = c.update(hand("fist"), w, h, 0.03)         # grab
        assert s["gesture"] == "drag", f"fist should grab, got {s['gesture']}"
        assert calls == ["LD"], f"grab should press once: {calls}"
        moved0 = (c.sx, c.sy)
        for k in range(5):                             # drag across
            c.update(hand("fist", shift=0.25), w, h, 0.06 + 0.03 * k)
        assert (c.sx, c.sy) != moved0, "fist drag did not move the cursor"
        c.update(hand("open"), w, h, 0.30)             # drop
        assert calls == ["LD", "LU"], f"drop should release: {calls}"

        # A fist must NOT emit a pinch click while grabbing/opening.
        assert "LC" not in calls and "RC" not in calls, f"fist emitted a click: {calls}"

        # Scroll: peace sign moved up -> wheel up.
        calls.clear()
        c = GestureController(cfg)
        up1 = hand("peace")
        up2 = hand("peace")
        for i in (INDEX_TIP, MIDDLE_TIP):
            up2[i] = up2[i]._replace(y=up2[i].y - 0.10)
        c.update(up1, w, h, 0.00)
        s = c.update(up2, w, h, 0.03)
        assert s["gesture"] == "scroll", "scroll not detected"
        assert any(isinstance(it, tuple) and it[1] > 0 for it in calls), \
            f"upward motion did not scroll up: {calls}"
    finally:
        for n, fn in saved.items():
            setattr(mod, n, fn)

    # Mapping: center of active region -> center of virtual desktop.
    c = GestureController(cfg)
    cx, cy = c.map_to_screen(0.5, 0.5)
    assert abs(cx - (x + vw / 2)) < 1 and abs(cy - (y + vh / 2)) < 1, "bad center map"
    assert c.map_to_screen(0.0, 0.0) == (x + 0.0, y + 0.0)
    assert c.map_to_screen(1.0, 1.0) == (x + vw, y + vh)

    print("Gestures: move OK, pinch-index=left OK, double-click OK, "
          "pinch-middle=right OK, fist=drag OK, no-stray-click OK, scroll OK")
    print("Mapping : center + corner clamping OK")
    print("SELFTEST PASSED")
    return 0


# --------------------------------------------------------------------------
# Live loop
# --------------------------------------------------------------------------
def ensure_model(path):
    """Return a usable model path, downloading it next to the script if needed."""
    if os.path.isfile(path):
        return path
    import urllib.request
    print(f"Hand model not found; downloading to {path} ...")
    try:
        urllib.request.urlretrieve(MODEL_URL, path)
        print("Model downloaded.")
        return path
    except Exception as e:
        print(f"ERROR: could not download the hand model.\n  {e}\n"
              f"  Download it from:\n    {MODEL_URL}\n"
              f"  and pass its path with --model.", file=sys.stderr)
        return None


def run(args):
    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    cfg = Config(args)
    controller = GestureController(cfg)
    print(f"Virtual desktop spans {controller.vw}x{controller.vh} "
          f"across {user32.GetSystemMetrics(80)} monitor(s); "
          f"origin ({controller.vx},{controller.vy})")
    print(f"Double-click = pinch index twice within "
          f"{user32.GetDoubleClickTime()} ms (Windows mouse setting)")

    model_path = ensure_model(args.model)
    if model_path is None:
        return 3

    base = mp_python.BaseOptions(model_asset_path=model_path)
    options = vision.HandLandmarkerOptions(
        base_options=base,
        running_mode=vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )
    landmarker = vision.HandLandmarker.create_from_options(options)

    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    # Request MJPG: most webcams are capped at ~7-10 fps in their default raw
    # (YUY2) mode and only reach 30 fps when delivering compressed frames.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, 30)
    if not cap.isOpened():
        print(f"ERROR: could not open camera {args.camera}. "
              f"Try --camera 1, or check the webcam is free.", file=sys.stderr)
        landmarker.close()
        return 2
    fourcc = (int(cap.get(cv2.CAP_PROP_FOURCC)) & 0xFFFFFFFF).to_bytes(4, "little")
    print(f"Camera: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
          f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} "
          f"@ {cap.get(cv2.CAP_PROP_FPS):.0f}fps "
          f"({fourcc.decode('ascii', 'replace')})")

    flip = not args.no_flip
    win = "Glide - Gesture Mouse"
    prev_t = time.time()
    fps = 0.0
    cap_ms = 0.0
    infer_ms = 0.0
    start = time.perf_counter()
    last_ts = -1

    try:
        while True:
            t0 = time.perf_counter()
            ok, frame = cap.read()
            t1 = time.perf_counter()
            if not ok:
                print("WARN: dropped frame", file=sys.stderr)
                continue

            if flip:
                frame = cv2.flip(frame, 1)  # mirror = natural movement
            h, w = frame.shape[:2]

            # Tasks API wants an mp.Image and a monotonically rising timestamp.
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts = int((time.perf_counter() - start) * 1000)
            if ts <= last_ts:
                ts = last_ts + 1
            last_ts = ts
            result = landmarker.detect_for_video(mp_image, ts)
            t2 = time.perf_counter()

            status = {"gesture": "-", "clicked": None}
            if result.hand_landmarks:
                lms = result.hand_landmarks[0]
                status = controller.update(lms, w, h, time.time())
                _draw_hand(cv2, frame, lms)
            else:
                controller.release()

            # HUD + timing (EMA of capture vs. inference cost in ms)
            cap_ms = 0.9 * cap_ms + 0.1 * (t1 - t0) * 1000.0
            infer_ms = 0.9 * infer_ms + 0.1 * (t2 - t1) * 1000.0
            now = time.time()
            dt = now - prev_t
            prev_t = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt)
            _draw_hud(cv2, frame, controller, status, fps, flip,
                      cap_ms, infer_ms)

            cv2.imshow(win, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):       # q or Esc
                break
            elif key == ord("p"):
                controller.enabled = not controller.enabled
                if not controller.enabled:
                    controller.release()
            elif key == ord("f"):
                flip = not flip
            # window closed via the X button
            if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        controller.release()
        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()
    return 0


def _draw_hand(cv2, frame, lms):
    """Render the 21-point hand skeleton (Tasks API has no drawing helper)."""
    h, w = frame.shape[:2]
    pts = [(int(p.x * w), int(p.y * h)) for p in lms]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (0, 200, 0), 2)
    for i, (x, y) in enumerate(pts):
        # Highlight index + middle tips (the click fingers).
        if i in (INDEX_TIP, MIDDLE_TIP):
            cv2.circle(frame, (x, y), 7, (0, 255, 255), -1)
        else:
            cv2.circle(frame, (x, y), 4, (0, 0, 255), -1)


def _draw_hud(cv2, frame, controller, status, fps, flip, cap_ms=0.0, infer_ms=0.0):
    h, w = frame.shape[:2]
    gesture = status["gesture"]
    colors = {"move": (255, 200, 0), "left": (0, 255, 0),
              "right": (0, 0, 255), "scroll": (255, 0, 255),
              "drag": (0, 220, 220), "-": (160, 160, 160)}
    color = colors.get(gesture, (200, 200, 200))

    cv2.rectangle(frame, (0, 0), (w, 64), (24, 24, 24), -1)
    state = "ON " if controller.enabled else "PAUSED"
    cv2.putText(frame, f"Glide  [{state}]  gesture: {gesture.upper()}",
                (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    di = status.get("di")
    dm = status.get("dm")
    op = status.get("open")
    metr = f"pinch i{di:.2f} m{dm:.2f} open{op:.2f}  " if di is not None else ""
    cv2.putText(frame,
                f"FPS {fps:4.0f} cam{cap_ms:3.0f} ai{infer_ms:3.0f}ms  "
                f"{metr}"
                f"pinch=click fist=drag peace=scroll  q/p/f",
                (12, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)

    # Draw the active region the hand maps from (frame minus margin border).
    m = controller.cfg.margin
    cv2.rectangle(frame,
                  (int(m * w), int(m * h)),
                  (int((1 - m) * w), int((1 - m) * h)),
                  (90, 90, 90), 1)


# --------------------------------------------------------------------------
def parse_args(argv):
    p = argparse.ArgumentParser(description="Control the mouse with hand gestures.")
    p.add_argument("--camera", type=int, default=0, help="webcam index (default 0)")
    p.add_argument("--width", type=int, default=640, help="capture width")
    p.add_argument("--height", type=int, default=480, help="capture height")
    p.add_argument("--margin", type=float, default=0.12,
                   help="dead border of the frame, 0..0.4 (default 0.12)")
    p.add_argument("--min-cutoff", dest="min_cutoff", type=float, default=1.0,
                   help="One Euro min cutoff; lower = steadier cursor (default 1.0)")
    p.add_argument("--beta", type=float, default=0.5,
                   help="One Euro beta; higher = less lag when moving (default 0.5)")
    p.add_argument("--pinch", type=float, default=0.5,
                   help="thumb-to-finger distance (/palm) to count as a pinch; "
                        "higher = easier clicks (default 0.5)")
    p.add_argument("--grab", type=float, default=1.2,
                   help="hand openness below which a fist grabs (drag); higher "
                        "= easier to trigger a grab (default 1.2)")
    p.add_argument("--click-cooldown", dest="click_cooldown", type=float,
                   default=0.12, help="minimum seconds between clicks; keep it "
                        "below the system double-click time so a fast second "
                        "pinch double-clicks (default 0.12)")
    p.add_argument("--scroll-speed", dest="scroll_speed", type=float,
                   default=1500.0, help="two-finger scroll sensitivity (default 1500)")
    p.add_argument("--natural-scroll", dest="natural_scroll", action="store_true",
                   help="reverse scroll direction (content follows fingers)")
    p.add_argument("--no-flip", action="store_true",
                   help="disable the mirror flip of the camera")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help="path to hand_landmarker.task (auto-downloaded if missing)")
    p.add_argument("--selftest", action="store_true",
                   help="validate logic without opening the camera or mouse")
    return p.parse_args(argv)


def main(argv=None):
    set_dpi_aware()
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.selftest:
        return selftest()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
