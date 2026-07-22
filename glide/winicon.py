"""Windows application icon — taskbar identity + window icon, via ctypes.

Gives the process its own taskbar identity (so Windows shows *Glide's* icon and
groups its windows under it, instead of the generic ``python.exe`` icon) and
attaches ``assets/glide.ico`` to the OpenCV preview window's title bar,
taskbar button and Alt-Tab card. Everything here is best-effort: if the icon
file or a Win32 call is unavailable, the app runs on with no icon.
"""

import ctypes
import os
from ctypes import wintypes

APP_ID = "Glide.GestureMouse"
ICON_PATH = os.path.join(os.path.dirname(__file__), "assets", "glide.ico")

_WM_SETICON = 0x0080
_ICON_SMALL = 0
_ICON_BIG = 1
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010


def icon_path():
    """Path to the bundled .ico, or None if it isn't present."""
    return ICON_PATH if os.path.isfile(ICON_PATH) else None


def set_app_id(app_id=APP_ID):
    """Claim a distinct AppUserModelID so the taskbar uses our icon.

    Call this once, as early as possible (before the window appears).
    """
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:  # noqa: BLE001 - purely cosmetic; never fatal
        pass


def _load_icon(path, size):
    u = ctypes.windll.user32
    u.LoadImageW.restype = wintypes.HANDLE
    u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                             ctypes.c_int, ctypes.c_int, wintypes.UINT]
    return u.LoadImageW(None, path, _IMAGE_ICON, size, size, _LR_LOADFROMFILE)


def _find_window(title):
    """HWND of a top-level window owned by this process whose title matches."""
    u = ctypes.windll.user32
    pid = ctypes.windll.kernel32.GetCurrentProcessId()
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lparam):
        wpid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and u.GetWindowTextLengthW(hwnd):
            buf = ctypes.create_unicode_buffer(u.GetWindowTextLengthW(hwnd) + 1)
            u.GetWindowTextW(hwnd, buf, len(buf))
            if buf.value == title:
                found.append(hwnd)
                return False  # stop enumerating
        return True

    u.EnumWindows(_cb, 0)
    return found[0] if found else None


def set_window_icon(title):
    """Attach the bundled icon to the window called `title`. Best-effort.

    Returns True if the icon was applied. The OpenCV window must already
    exist (call after the first ``imshow``).
    """
    path = icon_path()
    if not path:
        return False
    try:
        u = ctypes.windll.user32
        # LRESULT / WPARAM / LPARAM aren't all exposed by ctypes.wintypes,
        # so use pointer-sized base types (correct on 32- and 64-bit).
        u.SendMessageW.restype = ctypes.c_ssize_t
        u.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                   ctypes.c_size_t, ctypes.c_ssize_t]
        hwnd = _find_window(title)
        if not hwnd:
            return False
        big, small = _load_icon(path, 32), _load_icon(path, 16)
        if big:
            u.SendMessageW(hwnd, _WM_SETICON, _ICON_BIG, big)
        if small:
            u.SendMessageW(hwnd, _WM_SETICON, _ICON_SMALL, small)
        return bool(big or small)
    except Exception:  # noqa: BLE001 - cosmetic only
        return False
