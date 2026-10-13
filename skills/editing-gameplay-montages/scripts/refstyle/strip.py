"""Every frame a..b of a clip, as a zoom on the crosshair / weapon (to find the muzzle-flash frame) with
the kill feed (top right) and the ammo counter pasted into each tile.

usage: python strip.py c09 7370 7400         -> strip_c09_7370.jpg   (8 tiles per row, label = frame index)"""
import sys
import numpy as np
import cv2
import clipio

clip, a, b = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
step = int(sys.argv[4]) if len(sys.argv) > 4 else 1
FULL = len(sys.argv) > 5 and sys.argv[5] == "full"
fr = clipio.read_frames(clip, a, b, crop=False)
tiles = []
for i, f in enumerate(fr):
    if i % step:
        continue
    if FULL:
        t = np.ascontiguousarray(cv2.resize(f, (352, 198), interpolation=cv2.INTER_AREA))
        cv2.rectangle(t, (0, 0), (62, 18), (0, 0, 0), -1)
        cv2.putText(t, "%d" % (a + i), (2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        tiles.append(t)
        continue
    t = cv2.resize(f[300:810, 610:1516], (352, 198), interpolation=cv2.INTER_AREA)        # crosshair + weapon
    feed = cv2.resize(f[90:210, 1480:1910], (176, 49), interpolation=cv2.INTER_AREA)       # kill feed rows
    ammo = cv2.resize(f[990:1050, 1250:1400], (75, 30), interpolation=cv2.INTER_AREA)
    ban = cv2.resize(f[790:960, 875:1045], (48, 48), interpolation=cv2.INTER_AREA)         # kill banner badge
    t = np.ascontiguousarray(t)
    t[0:49, 176:352] = feed
    t[168:198, 0:75] = ammo
    t[150:198, 304:352] = ban
    cv2.rectangle(t, (0, 0), (62, 18), (0, 0, 0), -1)
    cv2.putText(t, "%d" % (a + i), (2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
    tiles.append(t)
cols = 8
rows = []
for r in range(0, len(tiles), cols):
    ch = tiles[r:r + cols]
    while len(ch) < cols:
        ch.append(np.zeros_like(tiles[0]))
    rows.append(np.hstack(ch))
out = "strip_%s_%d%s.jpg" % (clip, a, "f" if FULL else "")
cv2.imwrite(out, cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])
print(out, len(tiles), "frames")
