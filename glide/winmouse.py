"""Windows mouse / screen control via ctypes.

Everything addresses the whole *virtual desktop* (the rectangle spanning every
monitor), so multi-monitor setups — including monitors placed left of or above
the primary display (negative coordinates) — work out of the box.
"""

import ctypes
from ctypes import wintypes

_user32 = ctypes.windll.user32

# System-metric indices for the bounding box of ALL monitors combined.
_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79
_SM_CMONITORS = 80

_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_WHEEL = 0x0800

_user32.SetCursorPos.argtypes = [wintypes.INT, wintypes.INT]
_user32.SetCursorPos.restype = wintypes.BOOL
_user32.mouse_event.argtypes = [
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p
]
_user32.GetSystemMetrics.argtypes = [wintypes.INT]
_user32.GetSystemMetrics.restype = wintypes.INT
_user32.GetDoubleClickTime.restype = wintypes.UINT


def set_dpi_aware():
    """Make screen metrics and the cursor use true physical pixels, so
    multi-monitor setups with mixed DPI scaling line up correctly."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        try:
            _user32.SetProcessDPIAware()
        except Exception:
            pass


def virtual_screen():
    """(x, y, w, h) of the rectangle covering every monitor."""
    return (
        _user32.GetSystemMetrics(_SM_XVIRTUALSCREEN),
        _user32.GetSystemMetrics(_SM_YVIRTUALSCREEN),
        _user32.GetSystemMetrics(_SM_CXVIRTUALSCREEN),
        _user32.GetSystemMetrics(_SM_CYVIRTUALSCREEN),
    )


def monitor_count():
    return _user32.GetSystemMetrics(_SM_CMONITORS)


def double_click_ms():
    return _user32.GetDoubleClickTime()


def _event(flags):
    _user32.mouse_event(flags, 0, 0, 0, None)


class WinMouse:
    """The real mouse backend used by the app."""

    def move(self, x, y):
        _user32.SetCursorPos(int(x), int(y))

    def left_down(self):
        _event(_MOUSEEVENTF_LEFTDOWN)

    def left_up(self):
        _event(_MOUSEEVENTF_LEFTUP)

    def left_click(self):
        _event(_MOUSEEVENTF_LEFTDOWN)
        _event(_MOUSEEVENTF_LEFTUP)

    def right_click(self):
        _event(_MOUSEEVENTF_RIGHTDOWN)
        _event(_MOUSEEVENTF_RIGHTUP)

    def wheel(self, delta):
        # delta > 0 scrolls up, < 0 down; masked to unsigned for the DWORD arg.
        _user32.mouse_event(_MOUSEEVENTF_WHEEL, 0, 0, int(delta) & 0xFFFFFFFF, None)
