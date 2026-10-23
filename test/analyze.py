#!/usr/bin/env python3
"""Samples the test picture. The 640x448 PS2 frame is presented FIT inside the 640x480 canvas: y + 16."""
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert('RGB')
W, H = im.size
oy = (H - 448) // 2
def avg(x0, y0, x1, y1):
    r = g = b = n = 0
    for y in range(y0 + oy, y1 + oy):
        for x in range(x0, x1):
            p = im.getpixel((x, y)); r += p[0]; g += p[1]; b += p[2]; n += 1
    return (r // n, g // n, b // n)
def near(c, want, tol=24): return all(abs(a - b) <= tol for a, b in zip(c, want))
checks = [
    ("background", (600, 400, 630, 440), (0x20, 0x20, 0x20)),
    ("red sprite", (40, 40, 120, 120), (255, 0, 0)),
    ("green sprite", (184, 40, 264, 120), (0, 255, 0)),
    ("blue sprite", (328, 40, 408, 120), (0, 0, 255)),
    ("tex32 top-left (blue)", (32, 176, 128, 272), (0x20, 0x40, 0xFF)),
    ("tex32 top-right (yellow)", (160, 176, 256, 272), (0xFF, 0xFF, 0x00)),
    ("tex32 bottom-left (cyan)", (32, 304, 128, 400), (0x00, 0xFF, 0xFF)),
    ("tex32 bottom-right (magenta)", (160, 304, 256, 400), (0xFF, 0x00, 0xFF)),
]
ok = True
for name, box, want in checks:
    got = avg(*box); good = near(got, want)
    ok &= good
    print(f"{'ok ' if good else 'BAD'} {name:30s} got {got} want {want}")
# PSMT8 texture: cell (cx,cy) has index i = cx + 8*cy -> colour ((i*37)&255, (i*91)&255, (i*53)&255)
bad8 = 0
for cy in range(8):
    for cx in range(8):
        i = cx + 8 * cy
        want = ((i * 37) & 255, (i * 91) & 255, (i * 53) & 255)
        got = avg(288 + cx * 16 + 4, 160 + cy * 16 + 4, 288 + cx * 16 + 12, 160 + cy * 16 + 12)
        if not near(got, want): bad8 += 1
print(f"{'ok ' if bad8 == 0 else 'BAD'} psmt8 clut texture: {64 - bad8}/64 cells match")
ok &= (bad8 == 0)
c = avg(456, 168, 504, 216)
verdict = 'GREEN (alpha channel read as index: correct)' if near(c, (0, 255, 0)) else \
          'RED (red channel read as index: the WebGL swizzle bug)' if near(c, (255, 0, 0)) else \
          'BLUE (alpha read, not doubled)' if near(c, (0, 0, 255)) else f'other {c}'
print(f"8H framebuffer texture sprite: {c} -> {verdict}")
print("ALL OK" if ok and near(c, (0, 255, 0)) else "SOME CHECKS FAILED")
