"""Which footage does the edit need? Derives ranges.json for prep.py from timeline.py:
every source interval that is on screen, at 4 sub-frames per frame, and at 16 where it plays slower
than 0.7x (in slow motion the 4x grid shows as a blend between two in-betweens).

usage: python ranges.py            -> ranges.json, then:  python prep.py ranges.json
                                                          python densify.py run 12 28
                                                          python check_store.py      (must report 0 missing)
Run it again after every change of the anchors; prep.py only builds what is not in the store yet.
It also catches anchors that ask for frames before the start or after the end of a clip."""
import json, os, re, sys
import preflight
import numpy as np
import clipio
T = preflight.timeline(music=True)

SH = float(re.search(r"^SHUTTER = ([0-9.]+)", open("render.py", encoding="utf-8").read(), re.M).group(1))
h = SH / T.FPB / 2
base, dense, bad = {}, {}, 0
for n in range(T.N_FRAMES):
    r = T.frame_beat(n)
    a, b, p, tin = T.active(r)
    for i in ([a] if b is None else [a, b]):
        s = T.SEGS[i]
        c = s["clip"]
        nf = clipio.n_frames(c)
        hh = s.get("shutter", SH) / T.FPB / 2          # a take may set its own shutter (reference-style intro)
        p0, p1 = float(s["map"](r - hh)[0]), float(s["map"](r + hh)[0])
        v = float(s["map"](r)[1])
        if p0 < 0 or p1 > nf - 1:
            bad += 1
            if bad <= 6:
                print("ERROR: output frame %d (beat %.2f) asks %s for frame %.1f..%.1f; the clip has 0..%d" % (n, r, c, p0, p1, nf - 1))
        lo, hi = max(0, int(np.floor(p0)) - 2), min(nf - 1, int(np.ceil(p1)) + 2)
        base.setdefault(c, np.zeros(nf, bool))[lo:hi + 1] = True
        if v < 0.7:
            dense.setdefault(c, np.zeros(nf, bool))[lo:hi + 1] = True


def runs(mask, gap):
    idx = np.flatnonzero(mask)
    out = []
    for j in idx:
        if out and j - out[-1][1] <= gap:
            out[-1][1] = int(j)
        else:
            out.append([int(j), int(j)])
    return out


spec, frames = [], {4: 0, 16: 0}
for fac, table, gap in ((4, base, 30), (16, dense, 4)):
    for c in sorted(table):
        for lo, hi in runs(table[c], gap):
            spec.append([c, round(float(clipio.n2t(c, lo)) - 0.002, 3), round(float(clipio.n2t(c, hi)) + 0.002, 3), fac])
            frames[fac] += hi - lo
            print("%-4s frames %5d..%5d  (%.2f s .. %.2f s)  x%d" % (c, lo, hi, spec[-1][1], spec[-1][2], fac))
if bad:
    sys.exit("ERROR: %d output frames ask for footage outside a clip (the first %d are listed above): move the anchors (or R0 / R1) in timeline.py, "
             "then run  python ranges.py  again. ranges.json was NOT written." % (bad, min(bad, 6)))
json.dump(spec, open("ranges.json", "w"))
est = frames[4] * 3 + frames[16] * 12
wide = clipio.CROP_W > 1344                           # full-width store (reference style): bigger files, slower interpolation
rate, mb = (6.9, 0.38 * clipio.CROP_W / 1344.0) if wide else (8, 0.38)
print("ranges.json: %d ranges, about %d sub-frames to interpolate if the store is empty (%.1f GB of store);" % (len(spec), est, (est + frames[4]) * mb / 1024))
if os.environ.get("RIFE_GPU", "0").strip().lower() in ("-1", "cpu"):
    print("   on the CPU (RIFE_GPU=-1): about %.1f hours at 0.4 sub-frames per second (measured on a 12-thread CPU; a slower CPU takes longer)" % (est / 0.4 / 3600))
else:
    print("   time: %.0f min at %g per second on a fast GPU, %.0f min at 4 per second on a GTX 1650-class one (measured); without a Vulkan GPU "
          "RIFE_GPU=-1 runs on the CPU, %.1f hours" % (est / rate / 60, rate, est / 4 / 60, est / 0.4 / 3600))
print("densify.py then adds about half as many again where the picture moves fast")
