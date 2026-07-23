"""Camera capture + hand tracking run loop."""

import os
import sys
import time
import urllib.request

from . import winicon, winmouse
from .controller import GestureController
from .hud import Hud

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/1/hand_landmarker.task")

WINDOW = "Glide"


def _resource(name):
    """Locate a data file bundled by PyInstaller (frozen build), else None."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = os.path.join(base, name)
        if os.path.isfile(p):
            return p
    return None


def _frozen():
    return getattr(sys, "frozen", False)


def _error_box(msg):
    """Show a modal error dialog. A windowed .exe has no console, so a fatal
    startup problem would otherwise be an invisible no-op. No-op from source."""
    if not _frozen():
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(msg), "Glide", 0x10)
    except Exception:  # noqa: BLE001
        pass


def ensure_model(path):
    """Return a usable model path.

    Prefers an explicit existing path, then a copy bundled into the frozen
    app, and finally downloads it next to the package (source runs only).
    """
    if path and os.path.isfile(path):
        return path
    bundled = _resource("hand_landmarker.task")
    if bundled:
        return bundled
    print(f"Hand model not found; downloading to {path} ...")
    try:
        urllib.request.urlretrieve(MODEL_URL, path)
        print("Model downloaded.")
        return path
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: could not download the hand model.\n  {e}\n"
              f"  Get it from:\n    {MODEL_URL}\n"
              f"  and set model path in config or --model.", file=sys.stderr)
        return None


def _open_camera(cv2, cfg):
    cap = cv2.VideoCapture(cfg.camera, cv2.CAP_DSHOW)
    # MJPG: many webcams are capped at ~7-10 fps in raw (YUY2) mode.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
    cap.set(cv2.CAP_PROP_FPS, 30)
    return cap


def run(cfg):
    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    winmouse.set_dpi_aware()
    winicon.set_app_id()  # taskbar shows Glide's icon, not python.exe
    screen = winmouse.virtual_screen()
    mouse = winmouse.WinMouse()
    controller = GestureController(cfg, mouse, screen)
    hud = Hud(cfg)

    print(f"Glide {_version()} - virtual desktop {screen[2]}x{screen[3]} "
          f"across {winmouse.monitor_count()} monitor(s)")
    print(f"Double-click = pinch index twice within "
          f"{winmouse.double_click_ms()} ms")

    model_path = ensure_model(cfg.model)
    if model_path is None:
        _error_box("Glide could not load its hand-tracking model.")
        return 3

    options = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )
    landmarker = vision.HandLandmarker.create_from_options(options)

    cap = _open_camera(cv2, cfg)
    if not cap.isOpened():
        msg = (f"Glide could not open camera {cfg.camera}.\n\n"
               f"Close other apps that may be using the webcam, or pick "
               f"another camera with:  Glide --camera 1")
        print(f"ERROR: {msg}", file=sys.stderr)
        _error_box(msg)
        landmarker.close()
        return 2
    print(f"Camera: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
          f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @ "
          f"{cap.get(cv2.CAP_PROP_FPS):.0f}fps")

    flip = cfg.flip
    prev_t = time.time()
    start = time.perf_counter()
    fps = cap_ms = infer_ms = 0.0
    last_ts = -1
    icon_set = False
    icon_tries = 0

    try:
        while True:
            t0 = time.perf_counter()
            ok, frame = cap.read()
            t1 = time.perf_counter()
            if not ok:
                continue
            if flip:
                frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts = int((time.perf_counter() - start) * 1000)
            ts = ts if ts > last_ts else last_ts + 1
            last_ts = ts
            result = landmarker.detect_for_video(image, ts)
            t2 = time.perf_counter()

            snap = {"gesture": "-", "clicked": None, "di": None, "dm": None,
                    "open": None, "landmarks": None}
            if result.hand_landmarks:
                lm = result.hand_landmarks[0]
                snap = controller.update(lm, w, h, time.time())
                snap["landmarks"] = lm
                if snap["clicked"]:
                    hud.notify_click((w, h), lm, snap["clicked"])
            else:
                controller.release()

            now = time.time()
            dt = now - prev_t
            prev_t = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 / dt
            cap_ms = 0.9 * cap_ms + 0.1 * (t1 - t0) * 1000
            infer_ms = 0.9 * infer_ms + 0.1 * (t2 - t1) * 1000
            snap.update(enabled=controller.enabled, flip=flip, fps=fps,
                        cap_ms=cap_ms, infer_ms=infer_ms)
            hud.draw(frame, snap)

            cv2.imshow(WINDOW, frame)
            key = cv2.waitKey(1) & 0xFF
            if not icon_set and icon_tries < 30:
                icon_set = winicon.set_window_icon(WINDOW)
                icon_tries += 1
            if key in (ord("q"), 27):
                break
            elif key == ord("p"):
                controller.toggle()
            elif key == ord("f"):
                flip = not flip
            elif key == ord("h"):
                hud.toggle_help()
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        controller.release()
        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()
    return 0


def check(cfg):
    """Load the hand model with no camera or window and exit.

    A quick way to smoke-test a packaged build — it exercises the whole
    MediaPipe + model-bundling path without needing a webcam:

        Glide.exe --check
    """
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    model_path = ensure_model(cfg.model)
    if model_path is None:
        _error_box("Glide could not load its hand-tracking model.")
        return 3
    options = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.VIDEO, num_hands=1)
    vision.HandLandmarker.create_from_options(options).close()
    print(f"check: OK - hand model loaded from {model_path}")
    return 0


def _version():
    from . import __version__
    return __version__
