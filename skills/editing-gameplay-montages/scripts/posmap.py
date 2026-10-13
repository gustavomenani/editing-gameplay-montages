"""Where do the stored sub-frames really sit in time?

RIFE has a dead zone at both ends of the time step (see rifeutil.Tween): in a store built with plain
steps, the sub-frames 1/16 and 15/16 copy the real frame and the next few lag behind. fixends.py rebuilds
them; this script instead MEASURES the store as it is, so the renderer can place every sub-frame at its
true position (needed when part of the store is fixed and part is not, or when the GPU is busy).

For every interval between two real frames it classifies the grid (old / fixed) from the first steps, and
for each class it averages the normalised cumulative picture change -> position of each sixteenth.
Writes posmap.json: {"tables": {"old": [17 positions], "fixed": [...]}, "fixed": {clip: [frame indices]}}.
A position of -1 means: do not use that sub-frame (it duplicates the real frame)."""
import glob, json, os
import numpy as np
import cv2


def small(clip, key):
    return cv2.imread(f"store/{clip}/{key:08d}.jpg", cv2.IMREAD_REDUCED_GRAYSCALE_4).astype(np.int16)


def dist(a, b):
    return float(np.abs(a - b).mean())


fixed, cum = {}, {"old": [], "fixed": []}
n_int = 0
for d in sorted(glob.glob("store/*")):
    clip = os.path.basename(d)
    keys = set(int(os.path.basename(f)[:-4]) for f in glob.glob(d + "/*.jpg"))
    fixed[clip] = []
    for j in sorted({k // 16 for k in keys}):
        b = j * 16
        if not {b, b + 2, b + 4, b + 16} <= keys:
            continue                                         # 4x only: nothing to classify
        n_int += 1
        f0, f2, f4 = small(clip, b), small(clip, b + 2), small(clip, b + 4)
        if b + 1 in keys:
            r = dist(f0, small(clip, b + 1)) / (dist(small(clip, b + 1), f2) + 1e-6)
            is_fixed = r > 0.12                              # old grid: sub-frame 1 copies the real frame (r ~0.03);
                                                             # Tween-built: r ~0.45, as low as 0.24 on slow pans
        else:
            r = dist(f0, f2) / (dist(f2, f4) + 1e-6)
            is_fixed = r > 0.7                               # old grid: sub-frame 2 sits at about 1/16
        if is_fixed:
            fixed[clip].append(j)
        if all(b + s in keys for s in range(17)):            # full 16x grid: use it to measure positions
            ims = [small(clip, b + s) for s in range(17)]
            st = np.array([dist(ims[s], ims[s + 1]) for s in range(16)])
            if st.sum() > 2.0:                               # enough motion to measure
                c = np.concatenate([[0], np.cumsum(st)]) / st.sum() * 16
                cum["fixed" if is_fixed else "old"].append(c)
tables = {}
DEFAULT = {"old": [0.0, 0.03, 1.22, 2.45, 3.48, 4.57, 5.62, 6.83, 8.0, 9.17, 10.38, 11.43, 12.52, 13.55, 14.78, 15.97, 16.0],
           "fixed": [0.0, 0.59, 1.61, 2.79, 3.5, 4.58, 5.61, 6.81, 8.0, 9.19, 10.39, 11.42, 12.5, 13.21, 14.39, 15.41, 16.0]}
for name, rows in cum.items():
    if len(rows) < 8:                                      # this kind of grid is (almost) absent from the store:
        tables[name] = list(DEFAULT[name])                 # keep the positions measured on the worked example
        print(name, "grid:", len(rows), "intervals in this store; using the reference table")
        continue
    a = np.array(rows)
    med = np.median(a, axis=0)
    sym = (med + (16 - med[::-1])) / 2                       # the response is symmetric in time
    tables[name] = [round(float(x), 3) for x in sym]
    print(name, "grid: measured on", len(rows), "intervals; position of each sixteenth:")
    print("   ", " ".join("%.2f" % x for x in sym))
old = tables["old"]
old[1], old[15] = -1, -1                                     # copies of the real frames
json.dump({"tables": tables, "fixed": fixed}, open("posmap.json", "w"))
print("intervals denser than 4x:", n_int, "| fixed:", sum(len(v) for v in fixed.values()))
