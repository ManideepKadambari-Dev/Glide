"""The on-screen overlay — Glide's "face".

A compact, modern heads-up display drawn on top of the camera preview with
translucent rounded panels, a colour-coded gesture badge, live signal gauges,
and a click-flash animation. All colours are BGR (OpenCV order).
"""

import cv2
import numpy as np

from .gestures import (
    HAND_CONNECTIONS, INDEX_TIP, MIDDLE_TIP, THUMB_TIP, palm_center,
)

# ---- Theme (BGR) ---------------------------------------------------------
INK = (30, 27, 24)          # panel background
INK_2 = (52, 48, 44)        # gauge track
FG = (242, 240, 238)        # primary text
MUTED = (150, 145, 138)     # secondary text
ACCENT = (198, 214, 92)     # teal accent
LIVE = (120, 210, 130)      # green
PAUSED = (90, 175, 240)     # amber

GESTURE_COLORS = {
    "move": (205, 178, 120),
    "left": (120, 210, 130),
    "right": (105, 150, 245),
    "drag": (224, 200, 96),
    "scroll": (214, 132, 202),
    "-": (140, 138, 132),
}

_FONT = cv2.FONT_HERSHEY_SIMPLEX
_FONT_B = cv2.FONT_HERSHEY_DUPLEX
_AA = cv2.LINE_AA


def _text(frame, s, org, scale, color, thick=1, font=_FONT):
    cv2.putText(frame, s, org, font, scale, color, thick, _AA)


def _text_size(s, scale, thick=1, font=_FONT):
    (w, h), _ = cv2.getTextSize(s, font, scale, thick)
    return w, h


def _rounded_mask(h, w, r):
    r = int(max(0, min(r, h // 2, w // 2)))
    m = np.zeros((h, w), np.uint8)
    if r == 0:
        m[:] = 255
        return m
    cv2.rectangle(m, (r, 0), (w - r, h), 255, -1)
    cv2.rectangle(m, (0, r), (w, h - r), 255, -1)
    for cx, cy in ((r, r), (w - r, r), (r, h - r), (w - r, h - r)):
        cv2.circle(m, (cx, cy), r, 255, -1)
    return m


def _panel(frame, x1, y1, x2, y2, color, alpha=0.6, radius=12):
    """Blend a translucent rounded rectangle onto the frame in place."""
    H, W = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(W, x2), min(H, y2)
    if x2 <= x1 or y2 <= y1:
        return
    roi = frame[y1:y2, x1:x2]
    overlay = np.empty_like(roi)
    overlay[:] = color
    blended = cv2.addWeighted(overlay, alpha, roi, 1 - alpha, 0)
    mask = _rounded_mask(y2 - y1, x2 - x1, radius)
    roi[mask == 255] = blended[mask == 255]


def _pill(frame, x1, y1, x2, y2, color, radius=None):
    """Opaque rounded rectangle (for solid badges)."""
    if radius is None:
        radius = (y2 - y1) // 2
    roi = frame[max(0, y1):y2, max(0, x1):x2]
    if roi.size == 0:
        return
    overlay = np.empty_like(roi)
    overlay[:] = color
    mask = _rounded_mask(roi.shape[0], roi.shape[1], radius)
    roi[mask == 255] = overlay[mask == 255]


def _diamond(frame, cx, cy, r, color):
    pts = np.array([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], np.int32)
    cv2.fillConvexPoly(frame, pts, color, _AA)


def _clamp01(v):
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def draw_hand(frame, lm, gesture):
    """Refined 21-point skeleton with the active click fingers highlighted."""
    h, w = frame.shape[:2]
    pts = [(int(p.x * w), int(p.y * h)) for p in lm]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (96, 92, 88), 2, _AA)
    for i, (x, y) in enumerate(pts):
        cv2.circle(frame, (x, y), 3, (196, 194, 190), -1, _AA)
    for i in (THUMB_TIP, INDEX_TIP, MIDDLE_TIP):
        cv2.circle(frame, pts[i], 5, ACCENT, -1, _AA)
    # palm anchor (where the cursor is driven from)
    nx, ny = palm_center(lm)
    col = GESTURE_COLORS.get(gesture, ACCENT)
    cv2.circle(frame, (int(nx * w), int(ny * h)), 9, col, 2, _AA)


class Hud:
    def __init__(self, cfg):
        self.cfg = cfg
        self.show_help = False
        self._flash = None  # {"x","y","age","color"}

    def toggle_help(self):
        self.show_help = not self.show_help

    # -- gauges -----------------------------------------------------------
    def _gauge(self, frame, x, y, width, label, fill, tick, active, color):
        _text(frame, label, (x, y - 6), 0.36, MUTED if not active else color, 1)
        track_h = 7
        cv2.rectangle(frame, (x, y), (x + width, y + track_h), INK_2, -1, _AA)
        fw = int(width * _clamp01(fill))
        if fw > 0:
            c = color if active else (110, 106, 100)
            cv2.rectangle(frame, (x, y), (x + fw, y + track_h), c, -1, _AA)
        if 0.0 < tick < 1.0:
            tx = x + int(width * tick)
            cv2.line(frame, (tx, y - 2), (tx, y + track_h + 2), FG, 1, _AA)

    def _draw_gauges(self, frame, snap):
        cfg = self.cfg
        H = frame.shape[0]
        x, w = 22, 196
        top = H - 104
        _panel(frame, 14, top - 16, 14 + w + 16, top + 74, INK, 0.55, 12)
        _text(frame, "SIGNALS", (x, top - 4), 0.36, MUTED, 1)

        di, dm, op = snap.get("di"), snap.get("dm"), snap.get("open")
        po, pon = cfg.pinch_off, cfg.pinch_on
        fl = _clamp01((po - di) / po) if di is not None else 0.0
        fr = _clamp01((po - dm) / po) if dm is not None else 0.0
        tick_p = _clamp01((po - pon) / po)
        fg = _clamp01((2.0 - op) / (2.0 - 1.0)) if op is not None else 0.0
        tick_g = _clamp01((2.0 - cfg.fist_on) / (2.0 - 1.0))
        g = snap.get("gesture")
        self._gauge(frame, x, top + 12, w, "PINCH  L", fl, tick_p,
                    g == "left", GESTURE_COLORS["left"])
        self._gauge(frame, x, top + 38, w, "PINCH  R", fr, tick_p,
                    g == "right", GESTURE_COLORS["right"])
        self._gauge(frame, x, top + 64, w, "GRAB", fg, tick_g,
                    g == "drag", GESTURE_COLORS["drag"])

    # -- header -----------------------------------------------------------
    def _draw_header(self, frame, snap):
        W = frame.shape[1]
        _panel(frame, 0, 0, W, 44, INK, 0.62, 0)
        cv2.line(frame, (0, 44), (W, 44), ACCENT, 1, _AA)
        _diamond(frame, 20, 22, 7, ACCENT)
        _text(frame, "GLIDE", (34, 28), 0.66, FG, 1, _FONT_B)

        enabled = snap.get("enabled", True)
        dot = LIVE if enabled else PAUSED
        cv2.circle(frame, (124, 22), 5, dot, -1, _AA)
        _text(frame, "LIVE" if enabled else "PAUSED", (134, 26), 0.44, dot, 1)

        fps = snap.get("fps", 0.0)
        s = f"{fps:.0f}"
        fw, _ = _text_size(s, 0.7, 1, _FONT_B)
        _text(frame, s, (W - fw - 58, 28), 0.7, FG, 1, _FONT_B)
        _text(frame, "FPS", (W - 52, 18), 0.36, MUTED, 1)
        sub = f"cam {snap.get('cap_ms', 0):.0f} | ai {snap.get('infer_ms', 0):.0f} ms"
        sw, _ = _text_size(sub, 0.34, 1)
        _text(frame, sub, (W - sw - 10, 36), 0.34, MUTED, 1)

    def _draw_badge(self, frame, snap):
        g = snap.get("gesture", "-")
        color = GESTURE_COLORS.get(g, MUTED)
        label = g.upper()
        tw, th = _text_size(label, 0.5, 1, _FONT_B)
        x1, y1 = 14, 56
        x2, y2 = x1 + tw + 26, y1 + th + 16
        # click flash: brighten the badge briefly
        flash = self._flash and self._flash["age"] < 4
        _pill(frame, x1, y1, x2, y2, color if flash else INK, 12)
        if not flash:
            cv2.rectangle(frame, (x1, y1), (x1 + 4, y2), color, -1, _AA)
        txt_c = INK if flash else color
        _text(frame, label, (x1 + 16, y2 - 9), 0.5, txt_c, 1, _FONT_B)

    def _draw_footer(self, frame):
        H, W = frame.shape[:2]
        _panel(frame, 0, H - 24, W, H, INK, 0.55, 0)
        _text(frame, "Q  quit      P  pause      F  flip      H  help",
              (14, H - 8), 0.4, MUTED, 1)

    def _draw_active_region(self, frame):
        H, W = frame.shape[:2]
        m = self.cfg.margin
        x1, y1 = int(m * W), int(m * H)
        x2, y2 = int((1 - m) * W), int((1 - m) * H)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (86, 82, 78), 1, _AA)
        _text(frame, "active", (x1 + 4, y1 - 6), 0.34, (110, 106, 100), 1)

    def _draw_flash(self, frame):
        f = self._flash
        if not f:
            return
        r = 12 + f["age"] * 6
        a = max(0.0, 1.0 - f["age"] / 7.0)
        if a <= 0:
            self._flash = None
            return
        overlay = frame.copy()
        cv2.circle(overlay, (f["x"], f["y"]), r, f["color"], 2, _AA)
        cv2.addWeighted(overlay, a, frame, 1 - a, 0, frame)
        f["age"] += 1

    def _draw_help(self, frame):
        H, W = frame.shape[:2]
        _panel(frame, 0, 0, W, H, (12, 11, 10), 0.84, 0)
        rows = [
            ("Move", "open hand - cursor follows your palm"),
            ("Left click", "pinch thumb + index"),
            ("Double click", "pinch thumb + index twice, quickly"),
            ("Right click", "pinch thumb + middle"),
            ("Drag & drop", "close fist to grab, move, open hand to drop"),
            ("Scroll", "peace sign (index + middle), move up / down"),
        ]
        x, y = 40, 84
        _text(frame, "GESTURES", (x, 56), 0.6, ACCENT, 1, _FONT_B)
        for name, desc in rows:
            _text(frame, name, (x, y), 0.5, FG, 1, _FONT_B)
            _text(frame, desc, (x + 150, y), 0.44, MUTED, 1)
            y += 34
        _text(frame, "press  H  to close", (x, y + 6), 0.4, MUTED, 1)

    # -- public -----------------------------------------------------------
    def notify_click(self, frame_wh, lm, kind):
        if lm is None:
            return
        w, h = frame_wh
        nx, ny = palm_center(lm)
        self._flash = {"x": int(nx * w), "y": int(ny * h), "age": 0,
                       "color": GESTURE_COLORS["left" if kind == "left" else "right"]}

    def draw(self, frame, snap):
        lm = snap.get("landmarks")
        if lm is not None:
            draw_hand(frame, lm, snap.get("gesture", "-"))
        self._draw_active_region(frame)
        self._draw_flash(frame)
        self._draw_header(frame, snap)
        self._draw_badge(frame, snap)
        self._draw_gauges(frame, snap)
        self._draw_footer(frame)
        if self.show_help:
            self._draw_help(frame)
