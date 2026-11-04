"""Does the sub-frame store hold everything the render will ask for (at the current shutter)?
Run after every change of timeline.py and before a render; "missing footage" must be 0, "too coarse" 0,
"real frames that copy their predecessor" none and "damaged files" 0.

usage: python check_store.py             report; exit code 1 when footage is missing, too coarse, a real frame copies
                                         its predecessor (a freeze) or a file is damaged (run.sh relies on it)
       python check_store.py --delete    also deletes the damaged files, so that  python prep.py ranges.json  rebuilds them
                                         (the code is then 0 although those files are gone: prep.py must run before the render)

A damaged file is a store JPEG that is not whole (zero bytes, or cut off: a script killed while writing it, a full disk,
a copy that was interrupted). A cut-off JPEG still decodes, with a grey bottom, so the renderer would put it in the video.

"Too coarse" is the store holding a grid coarser than 1/16 where the take plays slower than 0.7x (usually a 4x grid):
ranges.py asks for 16x there, and on a 4x grid each output frame becomes a blend between two in-betweens 4 source frames
apart (a double-exposed slow motion, the defect the 16x grid exists for). It happens after a speed change in timeline.py:
run ranges.py, prep.py and densify.py again. At 0.7x and above a 4x grid is fine: a wider gap there is a hole in the
sub-frames (a missing key), which is missing footage, not a coarse grid.

A real frame that copies its predecessor is one the recording duplicated (a hiccup, or a run of them: a freeze of that many frames);
prep.py rebuilds these while it builds, repair.py afterwards.

The reference style paints the frames from LUMA_FADE[1] on black and reads no footage there, so neither this nor ranges.py asks for it."""
import glob, os, re, sys
import preflight
import numpy as np
import cv2
import rifeutil
T = preflight.timeline()
REF = "view" in T.SEGS[0]                          # the reference style's S() has a `view`; the house style's has not
if REF and getattr(T, "SYNC", 0) < 2:              # reference style: hard cuts on exact frames (the house style overlaps its transitions)
    sys.exit("check_store.py: timeline.py has no SYNC = 2 (it predates the frame-exact timing contract): copy the timing block of "
             "scripts/refstyle/timeline_ref_example.py into it, or redraft it with draft_ref_timeline.py.")
SH = float(re.search(r"^SHUTTER = ([0-9.]+)", open("render.py", encoding="utf-8").read(), re.M).group(1))
LF = getattr(T, "LUMA_FADE", None) if REF else None   # the ending fade; render.py returns a black frame from its end on
clips = sorted({s["clip"] for s in T.SEGS})
damaged, files = [], {}
for c in clips:
    names = sorted(os.path.normpath(f) for f in glob.glob(f"store/{c}/*.jpg"))
    files[c] = names
    damaged += [f for f in names if not rifeutil.is_jpeg_complete(f)]
bad_set = set(damaged)
keys = {c: np.array(sorted(int(os.path.basename(f)[:-4]) for f in files[c] if f not in bad_set)) for c in clips}
for c in clips:
    if not len(keys[c]):
        print(f"store/{c}/ has no sub-frames: python ranges.py && python prep.py ranges.json builds the store")
h = SH / T.FPB / 2
bad, thin, nkeys, used = 0, 0, [], set()
# what the render reads per output frame: the take(s) T.active() gives for that frame (reference style: the one take of T.take_of(n), chosen
# by frame index; house style: both layers during an overlapping transition) over the shutter window [p(r - h), p(r + h)]; the reference
# style's shot frame nk and the one before read the exact position p(r) only (render.py, crisp frames), a point inside the same window.
for n in range(T.N_FRAMES):
    r = T.frame_beat(n)
    if LF is not None and r >= LF[1]:
        continue                                           # black: render.py reads no footage here, ranges.py asks for none
    a, b, p, tin = T.active(r)
    shown = [a] if b is None else [a, b]
    tot = 0
    for i in shown:
        s = T.SEGS[i]; mp = s["map"]
        hh = s.get("shutter", SH) / T.FPB / 2
        p0, p1 = float(mp(r - hh)[0]) * 16, float(mp(r + hh)[0]) * 16
        v = float(mp(r)[1])                                  # speed of the take here: the value ranges.py puts the 16x request on
        k = keys[s["clip"]]
        i0 = max(0, int(np.searchsorted(k, p0, side="right")) - 1); i1 = min(len(k) - 1, int(np.searchsorted(k, p1, side="left")))
        ks = k[i0:i1 + 1]; tot += len(ks)
        used.update((s["clip"], j) for j in range(int(p0 // 16), int(p1 // 16) + 2))
        step = float(np.diff(ks).max()) if len(ks) > 1 else 0.0
        if len(ks) == 0 or not (ks[0] <= p0 + 1e-6 and ks[-1] >= p1 - 1e-6):
            bad += 1
            if bad < 8: print("MISSING frame", n, "beat %.2f" % r, s["clip"], "need %.2f..%.2f" % (p0 / 16, p1 / 16),
                              "have %.2f..%.2f" % (ks[0] / 16, ks[-1] / 16) if len(ks) else "have nothing")
        elif step > (1.01 if v < 0.7 else 4.01):
            if v < 0.7:
                # a 4x grid where the take plays slower than 0.7x: each output frame is then a blend of two in-betweens as far
                # apart as 4 source frames, i.e. a double-exposed slow motion
                thin += 1
                if thin < 8: print("TOO COARSE frame", n, "beat %.2f" % r, s["clip"], "at %.2fx it needs a 1/16 grid, the store has one key every %g/16" % (v, step))
            else:
                # at real time a 4x grid is enough: a wider gap is a hole in the sub-frames (a missing key), not a coarse grid
                bad += 1
                if bad < 8: print("MISSING sub-frames at frame", n, "beat %.2f" % r, s["clip"], "the store has one key every %g/16 where a 4x grid has 4/16" % (step,))
    nkeys.append(tot)
nkeys = np.array(nkeys)
if bad:
    print("-> python ranges.py && python prep.py ranges.json   (builds exactly what is missing)")
if thin:
    print("-> python ranges.py && python prep.py ranges.json && python densify.py run 12 28   (rebuilds the 1/16 grid the slow takes need)")
print("shutter", SH, "| output frames with missing footage:", bad, "| too coarse:", thin,
      "| sub-frames blended per output frame: median %d, 90%% %d, max %d" % (np.median(nkeys), np.percentile(nkeys, 90), nkeys.max()))
if damaged:
    print("damaged files (not whole JPEGs): %d, e.g. %s" % (len(damaged), ", ".join(damaged[:4])))
    if "--delete" in sys.argv:
        for f in damaged:
            os.remove(f)
        print("deleted them: now  python prep.py ranges.json  rebuilds them, then run check_store.py again")
    else:
        print("-> python check_store.py --delete   (removes them), then  python prep.py ranges.json  (rebuilds them)")

# a frame the recording duplicated must have been rebuilt (prep.py does it while building; repair.py afterwards)
def small(c, j):
    f = f"store/{c}/{j * 16:08d}.jpg"
    if not os.path.exists(f) or os.path.normpath(f) in bad_set:
        return None
    im = cv2.imread(f, cv2.IMREAD_REDUCED_GRAYSCALE_4)
    return None if im is None else im.astype(np.int16)


dups, prev = [], (None, None, None)
for c, j in sorted(used):
    im = small(c, j)
    if im is not None and prev[2] is not None and prev[:2] == (c, j - 1):
        ch = float(np.abs(im - prev[2]).mean())
        if ch < 0.13:                                 # an unrepaired copy measured 0.07, the stillest real pause 0.20
            dups.append((c, j, round(ch, 3)))
    prev = (c, j, im)
# a RUN of duplicated frames (two or three in a row) is a freeze, and the longer the run the worse it looks; the old filter kept only
# the duplicates with no other one within 4 frames, so exactly the runs disappeared from the report and from the exit code below.
runs = []
for c, j, ch in dups:
    if runs and runs[-1][0] == c and runs[-1][2] + 1 == j:
        runs[-1][2] = j
        runs[-1][3] += 1
    else:
        runs.append([c, j, j, 1, ch])
print("real frames in the store that copy their predecessor (a run is a freeze of that many frames):",
      "; ".join("%s:%d x%d" % (r[0], r[1], r[3]) for r in runs) if runs else "none")
if runs:
    print("-> confirm with  python cadence.py <clip> <frame-8> <frame+8> --detail , then  python repair.py " +
          " ".join("%s:%d" % (r[0], r[2]) for r in runs) + "   (and render again)")
sys.exit(1 if bad or thin or runs or (damaged and "--delete" not in sys.argv) else 0)
