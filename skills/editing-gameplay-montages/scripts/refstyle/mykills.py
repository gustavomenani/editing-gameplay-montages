"""Kill table for this project: the frame K to put on the beat for every detected kill.

Kills were found on the kill feed (detections.json: file + time the feed row appears). The shot frame is
the frame where the HUD ammo counter decrements (it does so on the frame of the shot); the feed row
shows up about 6-10 frames later. The gallery lets the editor confirm K: the muzzle flash / recoil must
start on the tile "+0" and be absent on "-1".

usage: python mykills.py [id,id,...]     -> kills.json  {id: {clip, K, feed, conf, ...}},  gal_NN.jpg (7 kills per sheet)
Row layout: full frame at K-12, K-6, K-2 | zoom on the weapon at K-1, K, K+1 | full frame at K, K+4, K+10"""
import json, os, sys
import numpy as np
import cv2
import clipio

CL = json.load(open("clips.json", encoding="utf-8-sig"))
F2C = {os.path.basename(p): c for c, p in CL.items()}
DET = json.load(open("detections.json"))
BAD = set()         # set per project: detection ids rejected on the review sheets
only = set(int(x) for x in sys.argv[1].split(",")) if len(sys.argv) > 1 else None
AX0, AY0, AW, AH = 1262, 998, 84, 44            # big ammo digits
out = json.load(open("kills.json")) if os.path.exists("kills.json") else {}
_auto = [i for i, v in out.items() if "method" in v]          # entries of kills_auto.py (another layout, numbered from 0 like these)
for i in _auto:
    del out[i]
if _auto:
    print("kills.json held %d entries written by kills_auto.py: dropped, they are not detection ids of this project" % len(_auto))
rows, sheet, missing = [], 0, set()
order = sorted([k for k in DET if k["id"] not in BAD and (only is None or k["id"] in only)],
               key=lambda k: (list(only).index(k["id"]) if only and False else k["id"]))
if only:
    ids = [int(x) for x in sys.argv[1].split(",")]
    order.sort(key=lambda k: ids.index(k["id"]))
for k in order:
    c = F2C.get(k["file"])
    if c is None:
        missing.add(k["file"])
        continue
    p = clipio.pts(c)
    fi = int(np.argmin(np.abs(p - k["t"])))       # frame where the feed row is first complete
    a, b = max(0, fi - 40), min(len(p) - 1, fi + 14)
    fr = clipio.read_frames(c, a, b, crop=False)
    masks = [fr[i, AY0:AY0 + AH, AX0:AX0 + AW].min(axis=2) > 205 for i in range(len(fr))]
    chg = np.zeros(len(fr))
    for i in range(1, len(fr)):
        u = (masks[i] | masks[i - 1]).sum()
        chg[i] = (masks[i] ^ masks[i - 1]).sum() / max(u, 40)
    cands = [i for i in range(3, len(fr) - 3)
             if chg[i] > 0.28 and max(chg[i + 1], chg[i + 2], chg[i - 1], chg[i - 2]) < 0.15 and masks[i].sum() > 60]
    fl = fi - a
    good = [i for i in cands if 5 <= fl - i <= 12]
    loose = [i for i in cands if 2 <= fl - i <= 30]
    if good:
        kl, conf = min(good, key=lambda i: abs((fl - i) - 8)), "ammo"
    elif loose:
        kl, conf = min(loose, key=lambda i: abs((fl - i) - 8)), "ammo-loose"
    else:
        kl, conf = max(0, fl - 8), "guess"
    K = a + kl
    out[str(k["id"])] = {"clip": c, "K": int(K), "feed": int(fi), "conf": conf, "file": k["file"],
                         "changes": [int(a + i) for i in cands]}
    print("#%-3d %s K=%d (feed %d, lag %d) %s  ammo changes at K%s" % (
        k["id"], c, K, fi, fi - K, conf, [int(a + i - K) for i in cands]), flush=True)

    def full(off):
        j = min(max(kl + off, 0), len(fr) - 1)
        t = cv2.resize(fr[j], (320, 180), interpolation=cv2.INTER_AREA)
        return lab(t, "%+d" % off)

    def zoom(off):
        j = min(max(kl + off, 0), len(fr) - 1)
        t = cv2.resize(fr[j][330:780, 760:1560], (320, 180), interpolation=cv2.INTER_AREA)
        return lab(t, "zoom %+d" % off)

    def lab(t, s):
        t = np.ascontiguousarray(t)
        cv2.rectangle(t, (0, 160), (86, 180), (0, 0, 0), -1)
        cv2.putText(t, s, (3, 175), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        return t

    row = np.hstack([full(-12), full(-6), full(-2), zoom(-1), zoom(0), zoom(1), full(0), full(4), full(10)])
    s = "#%d %s K=%d %s" % (k["id"], c, K, conf)
    cv2.rectangle(row, (0, 0), (len(s) * 11 + 8, 22), (0, 0, 0), -1)
    cv2.putText(row, s, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 2)
    rows.append(row)
    if len(rows) == 7:
        sheet += 1
        cv2.imwrite("gal_%02d.jpg" % sheet, cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 86])
        rows = []
if rows:
    sheet += 1
    cv2.imwrite("gal_%02d.jpg" % sheet, cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 86])
json.dump(out, open("kills.json", "w"), indent=1)
print("kills.json: %d kills; sheets gal_01..gal_%02d.jpg" % (len(out), sheet))
if missing:
    print("NOT in clips.json, so their kills were skipped (add them, run ingest.py and mkpts.py, then this again):")
    for f in sorted(missing):
        print("   ", f)
