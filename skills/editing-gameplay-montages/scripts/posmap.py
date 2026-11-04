"""Where do the stored sub-frames really sit in time?

RIFE has a dead zone at both ends of the time step (see rifeutil.Tween): in a store built with plain
steps, the sub-frames 1/16 and 15/16 copy the real frame and the next few lag behind. fixends.py rebuilds
them; this script instead MEASURES the store as it is, so the renderer can place every sub-frame at its
true position (needed when part of the store is fixed and part is not, or when the GPU is busy).

For every interval between two real frames it classifies the grid (old / fixed) from the first steps, and
for each class it averages the normalised cumulative picture change -> position of each sixteenth.
Writes posmap.json: {"tables": {"old": [17 positions], "fixed": [...]}, "fixed": {clip: [frame indices]}}.
A position of -1 means: do not use that sub-frame (it duplicates the real frame).

An interval that only has the 4x keys cannot be classified (the ratio that tells an old grid from a rebuilt
one needs the 2/16 and 1/16 keys), so it counts as plain ("old") - and when no old-style interval could be
measured, that class falls back to the table measured on the worked example, which marks the 1/16 and 15/16
slots -1 (duplicates of the real frame: true of the old grid, never of a rebuilt one) and puts 4/16 at 3.48.
A 4x store built today has real in-betweens (rifeutil.Tween: the steps 0.25 / 0.5 / 0.75 are linear), so a
store with 4x intervals and nothing old-style to measure gets the nominal positions instead: 4/16 at 4, 8/16
at 8, 12/16 at 12, no -1. The renderer then places those sub-frames where they really are and keeps every key
the store has (the old table put them half a sixteenth early / late). When the store holds enough 16x intervals
to measure, that path is unchanged."""
import glob, json, os, sys
import numpy as np
import cv2


def small(clip, key):
    f = f"store/{clip}/{key:08d}.jpg"
    im = cv2.imread(f, cv2.IMREAD_REDUCED_GRAYSCALE_4)
    if im is None:                                          # a damaged picture (imread says None): every position measured after it would be wrong
        sys.exit(f"posmap.py: {f} does not decode (a damaged store JPEG, even when it ends in FFD9): python check_store.py --delete removes it, "
                 "python prep.py ranges.json rebuilds it, then run python posmap.py again")
    return im.astype(np.int16)


def dist(a, b):
    return float(np.abs(a - b).mean())


NOMINAL = [float(s) for s in range(17)]                      # a sub-frame built at time step s/16 (Tween: linear between 0.25 and 0.75)
fixed, cum = {}, {"old": [], "fixed": []}
n_int = n_4x = 0
for d in sorted(glob.glob("store/*")):
    clip = os.path.basename(d)
    keys = set(int(os.path.basename(f)[:-4]) for f in glob.glob(d + "/*.jpg"))
    fixed[clip] = []
    for j in sorted({k // 16 for k in keys}):
        b = j * 16
        if not {b, b + 2, b + 4, b + 16} <= keys:
            if {b, b + 4, b + 8, b + 12, b + 16} <= keys:
                n_4x += 1                                    # 4x only: no 2/16 key to classify it (see the docstring)
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
tables, nominal_old = {}, False
DEFAULT = {"old": [0.0, 0.03, 1.22, 2.45, 3.48, 4.57, 5.62, 6.83, 8.0, 9.17, 10.38, 11.43, 12.52, 13.55, 14.78, 15.97, 16.0],
           "fixed": [0.0, 0.59, 1.61, 2.79, 3.5, 4.58, 5.61, 6.81, 8.0, 9.19, 10.39, 11.42, 12.5, 13.21, 14.39, 15.41, 16.0]}
for name, rows in cum.items():
    if len(rows) < 8:                                      # this kind of grid is (almost) absent from the store:
        if name == "old" and n_4x and not rows:             # the store holds 4x intervals and no old-style one to measure:
            tables[name] = list(NOMINAL)                    # they are Tween-built in-betweens at their time steps (no -1)
            nominal_old = True
            print(name, "grid:", len(rows), "intervals in this store;", n_4x, "4x intervals sit at their nominal sixteenths")
            continue
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
if nominal_old:
    print("4x store: positions are the nominal 0 1 2 ... 16, no slot is -1")
else:
    old[1], old[15] = -1, -1                                 # copies of the real frames
json.dump({"tables": tables, "fixed": fixed}, open("posmap.json", "w"))
print("intervals denser than 4x:", n_int, "| fixed:", sum(len(v) for v in fixed.values()))
