"""Command-line entry point.  py -m glide [options]"""

import argparse
import sys

from . import __version__


def build_parser():
    p = argparse.ArgumentParser(
        prog="glide",
        description="Control the mouse with hand gestures via a webcam.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"glide {__version__}")
    p.add_argument("--config", metavar="FILE",
                   help="TOML config file (defaults to ./glide.toml if present)")
    p.add_argument("--print-config", action="store_true",
                   help="print the effective config as TOML and exit")
    p.add_argument("--selftest", action="store_true",
                   help="validate the logic without a camera or the real mouse")
    p.add_argument("--check", action="store_true",
                   help="verify the hand model loads (no camera or window) and exit")

    # Overrides. Defaults are None so 'unset' falls back to the config file.
    cam = p.add_argument_group("camera")
    cam.add_argument("--camera", type=int, help="webcam index")
    cam.add_argument("--width", type=int)
    cam.add_argument("--height", type=int)
    cam.add_argument("--flip", action=argparse.BooleanOptionalAction,
                     help="mirror the preview (--no-flip to disable)")

    cur = p.add_argument_group("cursor")
    cur.add_argument("--margin", type=float, help="dead border of the frame")
    cur.add_argument("--min-cutoff", dest="min_cutoff", type=float,
                     help="One Euro min cutoff; lower = steadier")
    cur.add_argument("--beta", type=float, help="One Euro beta; higher = less lag")

    clk = p.add_argument_group("clicks / drag")
    clk.add_argument("--pinch", type=float, help="pinch distance to click")
    clk.add_argument("--grab", type=float, help="openness below which a fist grabs")
    clk.add_argument("--click-cooldown", dest="click_cooldown", type=float)

    scr = p.add_argument_group("scroll")
    scr.add_argument("--scroll-speed", dest="scroll_speed", type=float)
    scr.add_argument("--natural-scroll", dest="natural_scroll",
                     action=argparse.BooleanOptionalAction)

    p.add_argument("--model", metavar="PATH", help="path to hand_landmarker.task")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])

    from .config import build_config, to_toml
    try:
        cfg, path = build_config(args)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.print_config:
        if path:
            print(f"# loaded from {path}")
        print(to_toml(cfg), end="")
        return 0

    if args.selftest:
        from .selftest import selftest
        return selftest()

    if args.check:
        from .app import check
        return check(cfg)

    from .app import run, _error_box, _frozen
    if _frozen():
        # A windowed .exe has no console; surface a crash as a dialog.
        try:
            return run(cfg)
        except Exception as e:  # noqa: BLE001
            _error_box(f"Glide failed to start:\n\n{type(e).__name__}: {e}")
            return 1
    return run(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
