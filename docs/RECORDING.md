# Recording the demo GIF

The README embeds `docs/demo.gif`. Until that file exists the image link at the
top of the README renders broken — record it before pushing publicly.

## What to capture

Roughly 10–15 seconds, showing the gestures in the order the README lists them:

1. **Move** — open palm, cursor tracking the palm anchor. Let the HUD gauges be
   visible; the live `PINCH L` / `PINCH R` / `GRAB` bars are half the appeal.
2. **Left click** — pinch thumb + index on something that visibly reacts. The
   badge flashes and a ring animates at the palm.
3. **Right click** — pinch thumb + middle, opening a context menu.
4. **Drag** — close fist on a window title bar, move, open hand to drop.
5. **Scroll** — peace sign, move up and down over a long page.

Press `h` once at the end to flash the gesture guide overlay.

## Capturing

Record the Glide preview window plus enough desktop to show the cursor actually
responding — a crop of just the preview hides the point of the project.

- Windows: **Xbox Game Bar** (`Win+G`) or **ScreenToGif** (records straight to
  GIF, and lets you drop frames to hit a size budget).
- Keep it under ~10 MB so GitHub renders it inline without a slow load.
- 800–1000 px wide is plenty; the README column is narrower than that.

Save the result as `docs/demo.gif`.
