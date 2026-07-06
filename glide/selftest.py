"""Logic checks that need no camera and never touch the real mouse.

Run with:  py -m glide --selftest
"""

from collections import namedtuple

from . import winmouse
from .config import Config
from .controller import GestureController
from .gestures import (
    INDEX_MCP, INDEX_PIP, INDEX_TIP, MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP,
    PINKY_MCP, PINKY_PIP, PINKY_TIP, RING_MCP, RING_PIP, RING_TIP, THUMB_TIP,
    WRIST, hand_openness, is_two_finger, pinch_dists,
)

Pt = namedtuple("Pt", "x y")


class FakeMouse:
    """Records calls instead of moving the real cursor."""

    def __init__(self):
        self.calls = []

    def move(self, x, y):
        pass

    def left_down(self):
        self.calls.append("LD")

    def left_up(self):
        self.calls.append("LU")

    def left_click(self):
        self.calls.append("LC")

    def right_click(self):
        self.calls.append("RC")

    def wheel(self, delta):
        self.calls.append(("W", delta))


# A roughly realistic open right hand (palm to camera, fingers up).
_BASE = {
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


def _hand(mode="open", shift=0.0):
    lm = [Pt(_BASE[i][0] + shift, _BASE[i][1]) for i in range(21)]
    if mode == "pinch_index":
        lm[THUMB_TIP] = Pt(lm[INDEX_TIP].x, lm[INDEX_TIP].y)
    elif mode == "pinch_middle":
        lm[THUMB_TIP] = Pt(lm[MIDDLE_TIP].x, lm[MIDDLE_TIP].y)
    elif mode == "fist":
        for tip, mcp in ((INDEX_TIP, INDEX_MCP), (MIDDLE_TIP, MIDDLE_MCP),
                         (RING_TIP, RING_MCP), (PINKY_TIP, PINKY_MCP)):
            lm[tip] = Pt(lm[mcp].x, lm[mcp].y - 0.01)
        lm[THUMB_TIP] = Pt(0.50 + shift, 0.66)
    elif mode == "peace":
        lm[RING_TIP] = Pt(lm[RING_MCP].x, lm[RING_MCP].y + 0.02)
        lm[PINKY_TIP] = Pt(lm[PINKY_MCP].x, lm[PINKY_MCP].y + 0.02)
    return lm


def selftest():
    winmouse.set_dpi_aware()
    w = h = 1000
    x, y, vw, vh = winmouse.virtual_screen()
    print(f"Virtual desktop: origin=({x},{y}) size={vw}x{vh}, "
          f"{winmouse.monitor_count()} monitor(s)")

    cfg = Config(margin=0.1, min_cutoff=1.0, beta=0.5, pinch=0.5, grab=1.2,
                 click_cooldown=0.0, scroll_speed=1500.0, natural_scroll=False)

    # --- geometry sanity ---
    di_o, dm_o = pinch_dists(_hand("open"), w, h)
    assert di_o > 0.5 and dm_o > 0.5, f"open hand looks pinched: {di_o:.2f},{dm_o:.2f}"
    di_i, dm_i = pinch_dists(_hand("pinch_index"), w, h)
    assert di_i < 0.5 and di_i < dm_i, f"index pinch off: {di_i:.2f},{dm_i:.2f}"
    di_m, dm_m = pinch_dists(_hand("pinch_middle"), w, h)
    assert dm_m < 0.5 and dm_m < di_m, f"middle pinch off: {di_m:.2f},{dm_m:.2f}"
    assert hand_openness(_hand("open"), w, h) > 1.45, "open hand not open?"
    assert hand_openness(_hand("fist"), w, h) < 1.2, "fist not closed?"
    assert is_two_finger(_hand("peace")), "peace sign not detected"
    assert not is_two_finger(_hand("open")), "open hand misread as peace"

    def ctl():
        return GestureController(cfg, FakeMouse(), (x, y, vw, vh))

    # --- left click ---
    c = ctl()
    c.update(_hand("open"), w, h, 0.00)
    s = c.update(_hand("pinch_index"), w, h, 0.03)
    assert s["gesture"] == "left", f"expected left, got {s['gesture']}"
    c.update(_hand("pinch_index"), w, h, 0.06)
    c.update(_hand("open"), w, h, 0.09)
    assert c.mouse.calls == ["LC"], f"left click wrong: {c.mouse.calls}"

    # --- double click (two quick pinches each fire) ---
    c = ctl()
    c.update(_hand("open"), w, h, 0.00)
    c.update(_hand("pinch_index"), w, h, 0.03)
    c.update(_hand("open"), w, h, 0.06)
    c.update(_hand("pinch_index"), w, h, 0.09)
    c.update(_hand("open"), w, h, 0.12)
    assert c.mouse.calls == ["LC", "LC"], f"double click wrong: {c.mouse.calls}"

    # --- right click ---
    c = ctl()
    c.update(_hand("open"), w, h, 0.00)
    s = c.update(_hand("pinch_middle"), w, h, 0.03)
    assert s["gesture"] == "right", f"expected right, got {s['gesture']}"
    c.update(_hand("open"), w, h, 0.06)
    assert c.mouse.calls == ["RC"], f"right click wrong: {c.mouse.calls}"

    # --- drag: fist grabs, moves, opening drops; no stray click ---
    c = ctl()
    c.update(_hand("open"), w, h, 0.00)
    s = c.update(_hand("fist"), w, h, 0.03)
    assert s["gesture"] == "drag", f"fist should grab, got {s['gesture']}"
    assert c.mouse.calls == ["LD"], f"grab should press once: {c.mouse.calls}"
    moved0 = (c.sx, c.sy)
    for k in range(5):
        c.update(_hand("fist", shift=0.25), w, h, 0.06 + 0.03 * k)
    assert (c.sx, c.sy) != moved0, "fist drag did not move the cursor"
    c.update(_hand("open"), w, h, 0.30)
    assert c.mouse.calls == ["LD", "LU"], f"drop should release: {c.mouse.calls}"

    # --- scroll: peace sign moved up -> wheel up ---
    c = ctl()
    up1, up2 = _hand("peace"), _hand("peace")
    for i in (INDEX_TIP, MIDDLE_TIP):
        up2[i] = up2[i]._replace(y=up2[i].y - 0.10)
    c.update(up1, w, h, 0.00)
    s = c.update(up2, w, h, 0.03)
    assert s["gesture"] == "scroll", "scroll not detected"
    assert any(isinstance(it, tuple) and it[1] > 0 for it in c.mouse.calls), \
        f"upward motion did not scroll up: {c.mouse.calls}"

    # --- multi-monitor mapping ---
    c = ctl()
    cx, cy = c.map_to_screen(0.5, 0.5)
    assert abs(cx - (x + vw / 2)) < 1 and abs(cy - (y + vh / 2)) < 1, "bad center map"
    assert c.map_to_screen(0.0, 0.0) == (x + 0.0, y + 0.0)
    assert c.map_to_screen(1.0, 1.0) == (x + vw, y + vh)

    print("Gestures: move, left, double-click, right, drag, scroll -- OK")
    print("Mapping : center + corner clamping -- OK")
    print("SELFTEST PASSED")
    return 0
