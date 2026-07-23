# Packaging Glide as a standalone Windows app

Build a self-contained `Glide.exe` that anyone can run **without installing
Python, the dependencies, or having access to this repository**. This is the
way to share Glide from a portfolio or website while keeping the source private.

## Build

**One command:** run `make.bat build` (or double-click `make.bat` and choose
`2`). It installs PyInstaller if needed, ensures the hand model is present,
freezes the app, zips it, and smoke-tests the result — producing
`dist\Glide-windows.zip`, ready to upload. To run from source instead, use
`make.bat dev` (= `py -m glide`).

### Doing it by hand

One-time setup (dev machine only — not a runtime dependency):

```bash
py -m pip install pyinstaller
```

Make sure the hand model is present first (it's git-ignored and normally
auto-downloaded). This fetches it without opening a camera:

```bash
py -m glide --check
```

Then build:

```bash
py -m PyInstaller --noconfirm Glide.spec
```

Output lands in **`dist/Glide/`** — a folder containing `Glide.exe` plus its
`_internal/` runtime. That whole folder is the app.

### What gets bundled

[`Glide.spec`](../Glide.spec) handles the two things a naive freeze gets wrong:

- **MediaPipe** ships native modules and model graphs (`.binarypb` / `.tflite`)
  that must be collected explicitly (`collect_all("mediapipe")`), and its
  `vision` package pulls in `matplotlib`, so that stays bundled.
- **The hand model** (`hand_landmarker.task`) is bundled at the app root and
  located at runtime via `sys._MEIPASS`, so the packaged app never tries to
  download it. The app icon is embedded too.

## Verify

The app runs windowed (no console). Confirm a build works by exit code — both
should print `... PASSED` / `check: OK` and exit `0`:

```bash
dist/Glide/Glide.exe --selftest    # gesture + multi-monitor logic
dist/Glide/Glide.exe --check       # loads MediaPipe + the bundled model, no camera
```

Then just run `dist/Glide/Glide.exe` to use it for real.

### Debug builds

For a diagnostic console window (startup logs, tracebacks), set an env var
before building:

```bash
# PowerShell:  $env:GLIDE_CONSOLE=1 ;  py -m PyInstaller --noconfirm Glide.spec
GLIDE_CONSOLE=1 py -m PyInstaller --noconfirm Glide.spec
```

## Share it

`make.bat build` already produced **`dist\Glide-windows.zip`** (or zip it
yourself: `Compress-Archive -Path dist\Glide -DestinationPath dist\Glide-windows.zip -Force`).

Users **unzip and double-click `Glide.exe`** — nothing to install. The zip is
~125 MB (MediaPipe + OpenCV are the bulk).

Places to host it that don't expose your source:

- **Your own site / static hosting** — upload the zip, link a "Download for
  Windows" button.
- **[itch.io](https://itch.io)** — purpose-built for distributing downloadable
  apps; gives you a project page and a stable link, free, no source.
- **Object storage** — Cloudflare R2, S3, Backblaze B2, or a direct-download
  link from Drive/Dropbox for a clean URL.
- **A binaries-only public repo** — a *separate* public repo with no source,
  attaching the zip to a GitHub Release. (Releases on a *private* repo are
  private, so use a dedicated public one if you want a GitHub link.)

Do **not** publish to PyPI / `pip install` for this purpose — a wheel contains
your `.py` source.

## Notes for whoever downloads it

- **SmartScreen**: the exe is unsigned, so first launch shows *"Windows
  protected your PC"* → **More info → Run anyway**. Worth stating on your
  download page. To remove it entirely you'd need an (paid) code-signing
  certificate.
- **Webcam permission**: Windows may prompt for camera access on first run.
- **First launch** is a little slower while the runtime unpacks.
