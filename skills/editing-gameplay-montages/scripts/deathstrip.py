"""When does each enemy visibly DIE, and does the edit show it? Per kill, 1:1 crops (400x225 around the crosshair)
at K-8, K, K+4 ... K+52, and the kill feed at K+4, K+8, K+12, K+20. Tiles the current edit shows are labelled
green ("shown"), the rest red. A kill is good when the body visibly falls on a green tile and the player's own feed
row (lime wedge, "Eu" on the left) arrives 5-12 frames after K.

Why: the model edit's takes end when the enemy is down (timeline entry option `upto` = frames from the shot until the body is
down; fall() in timeline_ref_example.py lands on it). Measure `upto` here, per kill, and write it in plan.json
(draft_ref_timeline.py) or in the entry: the first green tile after the last tile with the body still standing.

usage: python deathstrip.py out.jpg                every kill of timeline.py, 2 kills per sheet (out_01.jpg ...); prints, per kill, how
                                                   many frames after the shot the edit shows (and warns when that is less than the
                                                   entry's `upto`)
       python deathstrip.py out.jpg c19@4571 ...   these kills (nothing counts as shown)
       add --fine for K, K+2 ... K+30 (find the exact frame the body starts to fall)"""
import os
import sys
import numpy as np
import cv2
import clipio

FINE = "--fine" in sys.argv
sys.argv = [a for a in sys.argv if a != "--fine"]
if len(sys.argv) < 2:
    sys.exit(__doc__)
out = sys.argv[1]
OFFS = list(range(0, 31, 2)) if FINE else [-8, 0, 4, 8, 12, 16, 20, 24, 28, 34, 42, 52]
FEED = [] if FINE else [4, 8, 12, 20]
TW, TH = 400, 225
SX, SY = clipio.SW / 1920.0, clipio.SH / 1080.0              # the crops below are written for 1920x1080
items = []
if len(sys.argv) > 2:
    for a in sys.argv[2:]:
        c, K = a.split("@")
        items.append((c, int(K), None, a, None))
else:
    import preflight
    T = preflight.timeline(music=False)
    ents = getattr(T, "E", [])
    fade = getattr(T, "LUMA_FADE", None)
    for i, s in enumerate(T.SEGS):
        ks = [k for k, lv in s["kills"]]
        up = ents[i][-1].get("upto") if i < len(ents) and isinstance(ents[i][-1], dict) else None
        for j, k in enumerate(ks):
            K = int(round(float(s["map"](k)[0])))
            r_end = ks[j + 1] if j + 1 < len(ks) else min(s["r1"], fade[1]) if fade else s["r1"]
            last = int(np.floor(float(s["map"](r_end)[0])))
            warn = up if j + 1 == len(ks) and up else None
            items.append((s["clip"], K, last, "take %d %s K=%d beat %.2f: edit shows up to K+%d%s" % (
                i, s["clip"], K, k, last - K, "" if warn is None else " (upto %d)" % warn), warn))


def label(t, text, col):
    cv2.rectangle(t, (0, 0), (10 + 9 * len(text), 20), (0, 0, 0), -1)
    cv2.putText(t, text, (4, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)


blocks = []
for clip, K, last, title, upto in items:
    nf = clipio.n_frames(clip)
    a, b = max(0, K + OFFS[0]), min(nf - 1, K + OFFS[-1])
    fr = clipio.read_frames(clip, a, b, crop=False)
    tiles = []
    for o in OFFS:
        n = min(max(K + o, a), b)
        # fine mode: a wider 640x360 crop (the body falls away from the crosshair), full mode: 400x225
        if FINE:
            crop = fr[n - a][int(360 * SY):int(720 * SY), int(640 * SX):int(1280 * SX)]
        else:
            crop = fr[n - a][int(448 * SY):int(673 * SY), int(760 * SX):int(1160 * SX)]
        t = np.ascontiguousarray(cv2.resize(crop, (TW, TH), interpolation=cv2.INTER_AREA)[:, :, ::-1])
        shown = last is not None and o >= 0 and K + o <= last
        label(t, ("K" if o == 0 else "K%+d" % o) + (" shown" if shown else (" NOT shown" if last is not None and o > 0 else "")),
              (0, 255, 0) if shown or o <= 0 else (0, 0, 255))
        tiles.append(t)
    for o in FEED:
        n = min(max(K + o, a), b)
        f = np.ascontiguousarray(cv2.resize(fr[n - a][int(80 * SY):int(250 * SY), int(1380 * SX):int(1915 * SX)], (TW, 127), interpolation=cv2.INTER_AREA)[:, :, ::-1])
        t = np.zeros((TH, TW, 3), np.uint8)
        t[:127] = f
        label(t, "feed K+%d" % o, (0, 255, 255))
        tiles.append(t)
    cols = 4
    while len(tiles) % cols:
        tiles.append(np.zeros((TH, TW, 3), np.uint8))
    grid = np.vstack([np.hstack(tiles[r * cols:(r + 1) * cols]) for r in range(len(tiles) // cols)])
    bar = np.zeros((26, grid.shape[1], 3), np.uint8)
    cv2.putText(bar, title, (4, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1)
    blocks.append(np.vstack([bar, grid]))
    if last is not None and upto is not None and last - K < upto - 0.75:
        print("WARNING: %s: the edit shows %d frames after the shot but upto = %d: the death is cut short" % (title, last - K, upto))
stem, ext = os.path.splitext(out)
for p in range(0, len(blocks), 2):
    name = "%s_%02d%s" % (stem, p // 2 + 1, ext or ".jpg")
    cv2.imwrite(name, np.vstack(blocks[p:p + 2]), [cv2.IMWRITE_JPEG_QUALITY, 86])
    print(name)
