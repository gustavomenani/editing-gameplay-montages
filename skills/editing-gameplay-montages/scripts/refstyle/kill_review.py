"""Review sheets for detected kills.

For each kill event: one row = [kill-feed crop after the kill] + gameplay frames around it
(t-0.50, -0.30, -0.20, -0.10, -0.05, 0, +0.10, +0.30 s relative to the feed event).

usage: kill_review.py <src_dir> <kills_dir> <out_dir> [rows_per_sheet]
Writes <out_dir>/review_NN.jpg and <out_dir>/index.json (global kill ids).
"""
import json
import os
import subprocess
import sys

import cv2
import numpy as np
from ff import FF

src_dir, kills_dir, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
ROWS = int(sys.argv[4]) if len(sys.argv) > 4 else 7
os.makedirs(out_dir, exist_ok=True)
OFFS = [-0.50, -0.30, -0.20, -0.10, -0.05, 0.0, 0.10, 0.30]
TW, TH = 288, 162
FEED = (1380, 88, 530, 160)      # x, y, w, h


def grab(path, t):
    """Decode one frame at time t (accurate seek)."""
    t = max(0.0, t)
    raw = subprocess.run([FF, "-v", "error", "-ss", f"{t:.4f}", "-i", path, "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    if len(raw) < 1920 * 1080 * 3:
        return np.zeros((1080, 1920, 3), np.uint8)
    return np.frombuffer(raw, np.uint8).reshape(1080, 1920, 3)


kills = []
for jf in sorted(os.listdir(kills_dir)):
    d = json.load(open(os.path.join(kills_dir, jf)))
    for e in d["events"]:
        kills.append({"file": d["file"], "t": e["t"], "frame": e["frame"]})
for i, k in enumerate(kills):
    k["id"] = i
json.dump(kills, open(os.path.join(out_dir, "index.json"), "w"), indent=1)
print(len(kills), "kills")

def grab_span(path, t0, n):
    """Decode n consecutive frames starting at t0, downscaled to 576x324."""
    t0 = max(0.0, t0)
    raw = subprocess.run([FF, "-v", "error", "-ss", f"{t0:.4f}", "-i", path, "-frames:v", str(n),
                          "-vf", "scale=576:324:flags=area", "-fps_mode", "passthrough",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    m = len(raw) // (576 * 324 * 3)
    return [np.frombuffer(raw, np.uint8, 576 * 324 * 3, i * 576 * 324 * 3).reshape(324, 576, 3) for i in range(m)]


rows = []
sheet = 0
for k in kills:
    path = os.path.join(src_dir, k["file"])
    tiles = []
    f = grab(path, k["t"] + 0.20)
    x, y, w, h = FEED
    feed = cv2.resize(f[y:y + h, x:x + w], (int(w * TH / h), TH), interpolation=cv2.INTER_AREA)
    tiles.append(feed)
    t0 = max(0.0, k["t"] + OFFS[0])
    span = grab_span(path, t0, int((OFFS[-1] - OFFS[0]) * 60) + 4)
    for o in OFFS:
        idx = int(round((k["t"] + o - t0) * 60))
        fr = span[min(max(idx, 0), len(span) - 1)] if span else np.zeros((324, 576, 3), np.uint8)
        tl = cv2.resize(fr, (TW, TH), interpolation=cv2.INTER_AREA)
        # mark screen centre (crosshair) lightly so flick distance is readable
        cv2.putText(tl, f"{o:+.2f}", (4, TH - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
        tiles.append(tl)
    row = np.hstack(tiles)
    label = f"#{k['id']}  {k['file'][:46]}  t={k['t']:.2f}s"
    cv2.rectangle(row, (0, 0), (len(label) * 11 + 10, 22), (0, 0, 0), -1)
    cv2.putText(row, label, (5, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
    rows.append(row)
    if len(rows) == ROWS:
        sheet += 1
        cv2.imwrite(os.path.join(out_dir, f"review_{sheet:02d}.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
        rows = []
if rows:
    sheet += 1
    cv2.imwrite(os.path.join(out_dir, f"review_{sheet:02d}.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
print(sheet, "sheets")
