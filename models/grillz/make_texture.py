"""
Paints grillz_diamond_pave.png (1024x1024) for grillz.obj.

u 0..0.9  : gold setting with a grid of brilliant-cut stones (front of each tooth)
u 0.92..1 : plain polished gold (sides, back and bezels)

Needs Pillow + numpy:  python3 make_texture.py
"""

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
SS = 2                # supersampling for smooth edges
PITCH_UV = 0.16       # must match the pitch used in grillz.py's Blender material
STONE_R = 0.42        # stone radius as a fraction of the pitch
PAVE_END = 0.90

GOLD = (236, 176, 64)
GOLD_DARK = (150, 98, 22)
GOLD_LIGHT = (255, 226, 140)


def main():
    n = SIZE * SS
    img = Image.new("RGB", (n, n), GOLD)
    d = ImageDraw.Draw(img)

    # soft vertical sheen on the gold
    for y in range(n):
        t = 0.5 + 0.5 * math.cos(y / n * math.pi * 2)
        c = tuple(int(GOLD[i] * (0.85 + 0.25 * t)) for i in range(3))
        d.line([(0, y), (n, y)], fill=tuple(min(255, v) for v in c))

    pitch = PITCH_UV * n
    r = STONE_R * pitch
    end_px = PAVE_END * n
    # stone centres sit on (k + 0.5) * pitch in UV space, same as the Blender node grid
    cols = int(end_px / pitch) + 1
    rows = int(n / pitch) + 1
    for row in range(rows):
        for col in range(cols):
            cx = (col + 0.5) * pitch
            # UV v goes up, image rows go down
            cy = n - (row + 0.5) * pitch
            if cx + r > end_px:
                continue
            draw_stone(d, cx, cy, r, seed=row * 31 + col * 7)
            # gold prongs between stones
            for px, py in ((cx + pitch / 2, cy + pitch / 2),):
                if px < end_px:
                    pr = pitch * 0.07
                    d.ellipse([px - pr, py - pr, px + pr, py + pr], fill=GOLD_LIGHT,
                              outline=GOLD_DARK, width=max(1, SS))

    # plain gold strip for the non-stone faces
    d.rectangle([0.915 * n, 0, n, n], fill=GOLD)

    img = img.resize((SIZE, SIZE), Image.LANCZOS).filter(ImageFilter.SHARPEN)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grillz_diamond_pave.png")
    img.save(out, optimize=True)
    print("Wrote", out)


def draw_stone(d, cx, cy, r, seed):
    rng = np.random.default_rng(seed)
    # gold bezel ring
    d.ellipse([cx - r * 1.08, cy - r * 1.08, cx + r * 1.08, cy + r * 1.08], fill=GOLD_DARK)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(170, 180, 195))
    # 8 crown facets, alternating light and dark, rotated a little per stone
    rot = rng.uniform(0, math.pi / 4)
    for k in range(16):
        a0 = rot + k * math.pi / 8
        a1 = a0 + math.pi / 8
        shade = 235 if k % 2 == 0 else 150
        shade += int(rng.integers(-25, 20))
        tint = (shade, min(255, shade + 6), min(255, shade + 18))
        d.polygon([(cx, cy),
                   (cx + r * math.cos(a0), cy + r * math.sin(a0)),
                   (cx + r * math.cos(a1), cy + r * math.sin(a1))], fill=tint)
    # table (flat top) and highlights
    tr = r * 0.45
    pts = [(cx + tr * math.cos(rot + k * math.pi / 4), cy + tr * math.sin(rot + k * math.pi / 4))
           for k in range(8)]
    d.polygon(pts, fill=(222, 230, 242), outline=(140, 150, 170))
    hr = r * 0.18
    hx, hy = cx - r * 0.35, cy - r * 0.35
    d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=(255, 255, 255))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(90, 95, 110), width=2 * SS)


if __name__ == "__main__":
    main()
