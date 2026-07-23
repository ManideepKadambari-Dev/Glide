# Glide.spec - PyInstaller build for the standalone Windows app.
#
#   py -m PyInstaller --noconfirm Glide.spec
#
# Produces a self-contained folder in  dist/Glide/  whose  Glide.exe  runs
# with no Python install and no source. Zip that folder and share it.
#
# Set GLIDE_CONSOLE=1 before building for a diagnostic console window
# (handy while debugging a build); the default is a clean, windowed app.
import os

from PyInstaller.utils.hooks import collect_all

CONSOLE = os.environ.get("GLIDE_CONSOLE", "") == "1"

# MediaPipe ships native modules + model graphs (.binarypb / .tflite) that a
# naive freeze misses; collect_all pulls its data, binaries and submodules.
datas, binaries, hiddenimports = [], [], []
for pkg in ("mediapipe",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# The hand-landmark model, bundled at the app root (found via sys._MEIPASS).
datas += [("hand_landmarker.task", ".")]
# The app icon, so the runtime window/taskbar icon code works when frozen too.
datas += [("glide/assets/glide.ico", "glide/assets")]
hiddenimports += ["cv2"]

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # NOTE: MediaPipe's vision package imports matplotlib (drawing_utils), so
    # it must stay bundled even though Glide never draws with it.
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Glide",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CONSOLE,
    disable_windowed_traceback=False,
    icon="glide/assets/glide.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Glide",
)
