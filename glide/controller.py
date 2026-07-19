"""GestureController — turns per-frame hand landmarks into cursor moves,
clicks, drags, and scrolls.

The mouse backend and screen bounds are injected, so the whole thing can be
driven in tests with a fake mouse and no real cursor movement.
"""

from .filters import OneEuroFilter
from .gestures import (
    INDEX_TIP, MIDDLE_TIP, hand_openness, is_two_finger, palm_center, pinch_dists,
)


class GestureController:
    def __init__(self, cfg, mouse, screen):
        self.cfg = cfg
        self.mouse = mouse
        self.vx, self.vy, self.vw, self.vh = screen
        self.sx = self.vx + self.vw / 2.0
        self.sy = self.vy + self.vh / 2.0

        self.enabled = True
        self.grabbing = False       # fist -> left button held down (drag)
        self.left_latch = False     # index pinch currently engaged
        self.right_latch = False    # middle pinch currently engaged
        self.last_left = -1e9
        self.last_right = -1e9
        self.click_lockout = -1e9   # pinch clicks blocked until this time
        self.scroll_prev = None
        self.scroll_accum = 0.0
        self.fx = OneEuroFilter(cfg.min_cutoff, cfg.beta)
        self.fy = OneEuroFilter(cfg.min_cutoff, cfg.beta)

    def map_to_screen(self, nx, ny):
        m = self.cfg.margin
        span = max(1e-6, 1.0 - 2.0 * m)
        mx = min(max((nx - m) / span, 0.0), 1.0)
        my = min(max((ny - m) / span, 0.0), 1.0)
        return self.vx + mx * self.vw, self.vy + my * self.vh

    def toggle(self):
        self.enabled = not self.enabled
        if not self.enabled:
            self.release()

    def release(self):
        """Hand lost or control paused: never leave a button stuck down."""
        if self.grabbing:
            self.mouse.left_up()
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
        # of a fist can't flick a stray click), never while grabbing / scrolling.
        if fist or scroll or openness < self.cfg.fist_off:
            left_pinch = right_pinch = False
        else:
            on_i = self.cfg.pinch_off if self.left_latch else self.cfg.pinch_on
            on_m = self.cfg.pinch_off if self.right_latch else self.cfg.pinch_on
            left_pinch = di < on_i and di <= dm      # index is the pinched finger
            right_pinch = dm < on_m and dm < di      # middle is the pinched one

        # Two-finger scroll: vertical motion of the fingertips -> wheel ticks.
        if scroll:
            cy = (lm[INDEX_TIP].y + lm[MIDDLE_TIP].y) / 2.0
            if self.scroll_prev is not None:
                dy = self.scroll_prev - cy          # hand moves up -> positive
                if self.cfg.natural_scroll:
                    dy = -dy
                self.scroll_accum += dy * self.cfg.scroll_speed
                ticks = int(self.scroll_accum)
                if ticks and self.enabled:
                    self.mouse.wheel(ticks)
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
                self.mouse.move(self.sx, self.sy)

        clicked = None
        if self.enabled:
            # Drag: closing to a fist grabs (button down); opening drops it.
            if fist and not self.grabbing:
                self.mouse.left_down()
                self.grabbing = True
            elif not fist and self.grabbing:
                self.mouse.left_up()
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
                    self.mouse.left_click()
                    self.last_left = now
                    clicked = "left"
            elif not left_pinch:
                self.left_latch = False

            # Right click on the engage edge of a middle pinch.
            if right_pinch and not self.right_latch:
                self.right_latch = True
                if allow and (now - self.last_right) > self.cfg.click_cooldown:
                    self.mouse.right_click()
                    self.last_right = now
                    clicked = "right"
            elif not right_pinch:
                self.right_latch = False

        gesture = ("scroll" if scroll else "drag" if self.grabbing else
                   "left" if left_pinch else "right" if right_pinch else "move")
        return {"gesture": gesture, "clicked": clicked,
                "di": di, "dm": dm, "open": openness}
