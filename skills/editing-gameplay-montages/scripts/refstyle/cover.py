"""Cover image for the edit: a clean frame of the video (no crop, no zoom), darkened a little, with the title
in the same lettering as the video, centred on the exact middle of the frame.

usage: python cover.py <plate.png> <out.jpg> <title style: red|gold|silver|white> <TITLE> [subtitle]
(no subtitle by default). The size follows FRAME in timeline.py: 1920x1080, or 1080x1920 when it says "vertical"
(the plate must come from cover_plates.py of the same frame)."""
import os, sys
import numpy as np, cv2
import textfx, frame

W, H, G = frame.W, frame.H, 2.2


def cue(word, style, **over):
    c = textfx.Cue.__new__(textfx.Cue)
    c.a, c.b, c.word, c.st, c.fade, c.n_in = 0.0, 1.0, word, dict(textfx.STYLES[style], **over), 0.3, 0
    c.appear = {i: -10 for i, ch in enumerate(word) if ch != " "}
    c.n_settled, c.n_end, c.built = 0, 10 ** 9, False
    c.build()
    return c


def paint(canvas, c, shadow=0.45):
    a3, c3, share = c.layer(5)
    st = c.st
    ya, yb = max(0, c.y0), min(H, c.y0 + c.hb)
    sl = slice(ya - c.y0, yb - c.y0)
    reg = canvas[ya:yb]
    a3, c3 = a3[sl], c3[sl]
    reg *= (1 - c.shadow[sl, :, None] * np.float32(shadow))
    base = np.clip(reg, 0, 1) ** np.float32(1 / G)
    t = np.clip(c3 / np.maximum(a3, 1e-3), 0, 1)
    ov = np.where(base < 0.5, 2 * base * t, 1 - 2 * (1 - base) * (1 - t))
    mix = ov * np.float32(st["ov"]) + t * np.float32(1 - st["ov"])
    out = base + a3 * np.float32(st["strength"]) * (mix - base)
    reg[:] = np.clip(out, 0, 1) ** np.float32(G)
    reg += c.glow[sl, :, None] * (c.glowcol * np.float32(st["glow_a"]))


if len(sys.argv) < 5:
    sys.exit(__doc__)
plate, out, style = sys.argv[1], sys.argv[2], sys.argv[3]
if os.path.exists(out):
    sys.exit("refusing to overwrite %s: write each cover under a new name" % out)
title = sys.argv[4].upper()                                               # the song title unless the user names one; capitals like the video's words
subtitle = sys.argv[5] if len(sys.argv) > 5 else ""          # the user had the "VALORANT EDIT" line removed: title only
if not os.path.exists(plate):
    sys.exit("cover.py: plate %s not found (cover_plates.py writes cover/plate_<name>.png)" % plate)
img = (cv2.cvtColor(cv2.imdecode(np.fromfile(plate, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0) ** G     # fromfile: cv2.imread cannot open a non-ASCII path on Windows
if img.shape[:2] != (H, W):
    sys.exit(f"cover.py: {plate} is {img.shape[1]}x{img.shape[0]} but timeline.py says FRAME = {frame.FRAME!r} ({W}x{H}): make the plates again with cover_plates.py")
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
vig = 1.0 - 0.55 * np.clip(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.66)) ** 2, 0, 1) ** 1.2
band = 1.0 - 0.38 * np.exp(-((yy - (H / 2 + 32 if frame.VERT else H * 0.53)) / (200.0 if frame.VERT else 230.0)) ** 2)       # a darker band behind the words
img *= (0.74 * vig * band)[:, :, None]
CAP0, INK_MAX = (200, 900) if frame.VERT else (236, 800)                  # vertical: the window is 608 px tall, the canvas 1080 wide
t = cue(title, style, cap=CAP0, cy=0.5, strength=0.94, ov=0.30, glow_a=0.34)
while t.ink[1] - t.ink[0] > INK_MAX:                                       # horizontal: stays inside a vertical centre crop of the cover
    t = cue(title, style, cap=t.st["cap"] - 6, cy=0.5, strength=0.94, ov=0.30, glow_a=0.34)
paint(img, t)
cap = t.st["cap"]
if subtitle:
    s = cue(subtitle, "white", cap=46, cy=0.5 + (cap / 2 + 78) / H, strength=0.90, ov=0.15, glow_a=0.10, track=0.20, gloss=0.0)
    paint(img, s, shadow=0.6)
d = (np.clip(img, 0, 1) ** (1 / G) * 255 + 0.5).astype(np.uint8)
open(out, "wb").write(cv2.imencode(".jpg", cv2.cvtColor(d, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes())     # not cv2.imwrite: it writes a mojibake name for "ção" in the path
print(out, "| title ink x %d..%d (centre %.1f), caps centred on y=%g, cap height %d px, %dx%d" % (t.ink[0], t.ink[1], (t.ink[0] + t.ink[1] + 1) / 2, H / 2, cap, W, H))
