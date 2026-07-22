"""Regenerate Glide's raster brand assets from the vector design.

This mirrors the hand-authored vector sources (``glide-mark.svg`` /
``glide-logo.svg``) using Pillow, so the PNGs and the multi-size Windows icon
can be rebuilt deterministically:

    py assets/render.py

Outputs:
    assets/glide-mark.png        512x512 icon (README / social)
    assets/glide-logo.png        horizontal lockup banner (README hero)
    glide/assets/glide.ico       multi-size window/taskbar icon (16..256)

Requires Pillow + numpy (dev-only; not runtime dependencies). Text uses
Segoe UI, matching the app's home platform.
"""
import io
import os
import struct
import pathlib

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONTS = pathlib.Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"


# ---- small vector helpers (all coordinates are in 512-space) -------------
def hx(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def over(dst, src):
    sa, da = src[..., 3:4], dst[..., 3:4]
    oa = sa + da * (1 - sa)
    rgb = src[..., :3] * sa + dst[..., :3] * da * (1 - sa)
    out = np.empty_like(dst)
    out[..., :3] = rgb / np.where(oa > 0, oa, 1)
    out[..., 3:4] = oa
    return out


def _grid(n):
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    return xx, yy


def lin_grad(n, s, p0, p1, stops):
    xx, yy = _grid(n)
    p0, p1 = (p0[0] * s, p0[1] * s), (p1[0] * s, p1[1] * s)
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    t = np.clip(((xx - p0[0]) * dx + (yy - p0[1]) * dy) / (dx * dx + dy * dy or 1), 0, 1)
    offs = [o for o, _, _ in stops]
    cols = [hx(c) for _, c, _ in stops]
    out = np.zeros((n, n, 4), np.float32)
    for c in range(3):
        out[..., c] = np.interp(t, offs, [col[c] for col in cols])
    out[..., 3] = np.interp(t, offs, [a for _, _, a in stops])
    return out


def rad_grad(n, s, center, radius, stops):
    xx, yy = _grid(n)
    d = np.sqrt((xx - center[0] * s) ** 2 + (yy - center[1] * s) ** 2) / (radius * s)
    t = np.clip(d, 0, 1)
    offs = [o for o, _, _ in stops]
    cols = [hx(c) for _, c, _ in stops]
    out = np.zeros((n, n, 4), np.float32)
    for c in range(3):
        out[..., c] = np.interp(t, offs, [col[c] for col in cols])
    out[..., 3] = np.interp(t, offs, [a for _, _, a in stops])
    return out


def mask_poly(n, s, pts):
    im = Image.new("L", (n, n), 0)
    ImageDraw.Draw(im).polygon([(x * s, y * s) for x, y in pts], fill=255)
    return np.asarray(im, np.float32) / 255


def mask_rrect(n, s, box, r, outline=False, width=0):
    im = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(im)
    b = [v * s for v in box]
    if outline:
        d.rounded_rectangle(b, radius=r * s, outline=255, width=int(width * s))
    else:
        d.rounded_rectangle(b, radius=r * s, fill=255)
    return np.asarray(im, np.float32) / 255


def mask_polyline(n, s, pts, width):
    im = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(im)
    p = [(x * s, y * s) for x, y in pts]
    w = int(width * s)
    d.line(p, fill=255, width=w, joint="curve")
    for x, y in (p[0], p[-1]):
        d.ellipse([x - w // 2, y - w // 2, x + w // 2, y + w // 2], fill=255)
    return np.asarray(im, np.float32) / 255


def _cubic(p0, c1, c2, p3, k=64):
    ts = np.linspace(0, 1, k)
    return [((1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * c1[0] + 3 * (1 - t) * t * t * c2[0] + t ** 3 * p3[0],
             (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * c1[1] + 3 * (1 - t) * t * t * c2[1] + t ** 3 * p3[1])
            for t in ts]


def _quad(p0, c, p1, k=48):
    ts = np.linspace(0, 1, k)
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p1[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p1[1]) for t in ts]


def _solid(n, color, mask, alpha=1.0):
    out = np.zeros((n, n, 4), np.float32)
    out[..., :3] = hx(color)
    out[..., 3] = mask * alpha
    return out


# ---- the mark ------------------------------------------------------------
def draw_mark(s=4):
    n = 512 * s
    base = np.zeros((n, n, 4), np.float32)
    tile_m = mask_rrect(n, s, (0, 0, 511, 511), 118)

    tile = lin_grad(n, s, (64, 40), (448, 472), [(0, "272C34", 1), (1, "141619", 1)])
    tile[..., 3] *= tile_m
    base = over(base, tile)

    glow = rad_grad(n, s, (300, 208), 236,
                    [(0, "5CD6C6", .30), (.55, "5CD6C6", .07), (1, "5CD6C6", 0)])
    glow[..., 3] *= tile_m
    base = over(base, glow)

    comet_pts = ([(286, 232)] +
                 _cubic((286, 232), (220, 252), (150, 300), (104, 382)) +
                 _cubic((104, 382), (150, 320), (210, 300), (250, 286)))
    comet = lin_grad(n, s, (288, 230), (104, 384),
                     [(0, "7FE7D3", .95), (.55, "4FCBBF", .55), (1, "3AB4AB", 0)])
    comet[..., 3] *= mask_poly(n, s, comet_pts)
    base = over(base, comet)

    base = over(base, _solid(n, "8CEBD8",
                mask_polyline(n, s, _quad((272, 250), (182, 300), (126, 358)), 6), .45))

    cur = [(348, 152), (348, 281.2), (314.6, 252.3), (294, 301),
           (276.6, 293.4), (297.1, 244.7), (260.6, 239.4)]
    fill = lin_grad(n, s, (352, 150), (212, 312),
                    [(0, "9CF0DA", 1), (.5, "5CD6C6", 1), (1, "34AEA6", 1)])
    fill[..., 3] *= mask_poly(n, s, cur)
    base = over(base, fill)
    base = over(base, _solid(n, "0E1013", mask_polyline(n, s, cur + [cur[0]], 6), 1))

    base = over(base, rad_grad(n, s, (348, 152), 30,
                [(0, "F4FFFB", 1), (.35, "B7F4E6", 1), (1, "7FEAD8", 0)]))
    dot = [(348 + 8 * np.cos(a), 152 + 8 * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 40)]
    base = over(base, _solid(n, "F4FFFB", mask_poly(n, s, dot), 1))

    base = over(base, _solid(n, "5CD6C6",
                mask_rrect(n, s, (3, 3, 509, 509), 115, outline=True, width=2), .16))

    base[..., 3] *= tile_m
    return Image.fromarray((np.clip(base, 0, 1) * 255).astype(np.uint8), "RGBA")


# ---- the horizontal lockup banner ----------------------------------------
def _font(name, size):
    try:
        return ImageFont.truetype(str(FONTS / name), size)
    except OSError:
        return ImageFont.load_default()


def draw_banner(rs=2):
    w, h = 1024 * rs, 360 * rs
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = np.clip(xx / w * 0.5 + yy / h * 0.5, 0, 1)
    bg = np.array(hx("1B1F25")) * (1 - t[..., None]) + np.array(hx("101216")) * t[..., None]
    gl = np.clip(1 - np.sqrt((xx - 196 * rs) ** 2 + (yy - 180 * rs) ** 2) / (280 * rs), 0, 1) * 0.16
    bg = bg * (1 - gl[..., None]) + np.array(hx("5CD6C6")) * gl[..., None]
    img = Image.fromarray((np.clip(bg, 0, 1) * 255).astype(np.uint8), "RGB").convert("RGBA")

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=36 * rs, fill=255)
    img.putalpha(mask)

    img.alpha_composite(draw_mark(4).resize((220 * rs, 220 * rs), Image.LANCZOS), (78 * rs, 70 * rs))

    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    do = ImageDraw.Draw(ov)
    do.rounded_rectangle([rs, rs, w - rs, h - rs], radius=34 * rs, outline=(92, 214, 198, 36), width=3 * rs)
    do.rounded_rectangle([352 * rs, 104 * rs, 356 * rs, 256 * rs], radius=2 * rs, fill=(92, 214, 198, 115))
    img = Image.alpha_composite(img, ov)

    d = ImageDraw.Draw(img)
    d.text((392 * rs, 188 * rs), "Glide", font=_font("seguisb.ttf", 132 * rs),
           fill=(241, 244, 246, 255), anchor="ls")
    d.text((396 * rs, 244 * rs), "Control your mouse with hand gestures",
           font=_font("segoeui.ttf", 33 * rs), fill=(167, 173, 180, 255), anchor="ls")
    return img


# ---- multi-size .ico (PNG-compressed frames; Windows Vista+) --------------
def write_ico(master, sizes, path):
    blobs = []
    for s in sizes:
        b = io.BytesIO()
        master.resize((s, s), Image.LANCZOS).save(b, "PNG")
        blobs.append(b.getvalue())
    out = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + len(sizes) * 16
    for s, blob in zip(sizes, blobs):
        w = 0 if s >= 256 else s
        out += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    pathlib.Path(path).write_bytes(out + b"".join(blobs))


def main():
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "glide" / "assets").mkdir(exist_ok=True)
    mark = draw_mark(4)
    mark.resize((512, 512), Image.LANCZOS).save(ROOT / "assets" / "glide-mark.png")
    write_ico(mark, [256, 128, 64, 48, 32, 16], ROOT / "glide" / "assets" / "glide.ico")
    draw_banner(2).save(ROOT / "assets" / "glide-logo.png")
    print("Wrote glide-mark.png, glide-logo.png, glide/assets/glide.ico")


if __name__ == "__main__":
    main()
