"""Candidate shots for the intro at zoom Z. Use Z = 1: the centre crop that hides the HUD (Z around 2) is the
enlarged gameplay the user rejected ("no comeco aquele zoom ta mt feio").
usage: python introcand.py Z clip:a:b:step [...]  -> introcand.jpg (one row per candidate)"""
import sys
import numpy as np, cv2, clipio
Z = float(sys.argv[1])
rows = []
for spec in sys.argv[2:]:
    c, a, b, st = spec.split(":"); a, b, st = int(a), int(b), int(st)
    fr = clipio.read_frames(c, a, b, crop=False)[::st]
    w, h = int(1920 / Z), int(1080 / Z)
    x0, y0 = (1920 - w) // 2, max(0, min(1080 - h, int(540 - h * 0.52)))
    tiles = []
    for i, f in enumerate(fr[:10]):
        t = np.ascontiguousarray(cv2.resize(f[y0:y0 + h, x0:x0 + w], (288, 162), interpolation=cv2.INTER_AREA))
        cv2.rectangle(t, (0, 0), (96, 18), (0, 0, 0), -1)
        cv2.putText(t, "%s %d" % (c, a + i * st), (2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1)
        tiles.append(t)
    while len(tiles) < 10:
        tiles.append(np.zeros_like(tiles[0]))
    rows.append(np.hstack(tiles))
cv2.imwrite("introcand.jpg", cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])
print("introcand.jpg", len(rows), "rows")
