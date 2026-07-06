"""Glide — control the mouse with hand gestures.

A small, modular package:

  glide.config      configuration (dataclass + TOML file + CLI merge)
  glide.winmouse    Windows cursor / click / wheel control (ctypes)
  glide.filters     One Euro smoothing filter
  glide.gestures    hand-landmark geometry and gesture detection (pure)
  glide.controller  turns detections into cursor moves and clicks
  glide.hud         the on-screen overlay (the "professional UI")
  glide.app         camera + tracker run loop
  glide.selftest    logic checks that need no camera or real mouse

Run with:  py -m glide     (or  py run.py)
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
