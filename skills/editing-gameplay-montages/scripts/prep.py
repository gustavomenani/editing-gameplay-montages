"""Build the sub-frame store used by the renderer.

For every requested source range: read the real frames by exact index, rebuild frames the recording
duplicated, and interpolate between consecutive frames with RIFE. A sub-frame is stored as
store/<clip>/<key>.jpg with key = frame_index * 16 + sixteenths, so a 4x grid uses sixteenths
0, 4, 8, 12 and a dense 16x grid uses all of them. Existing files are kept (resumable).

usage: python prep.py ranges.json        ranges.json = [[clip, t0_seconds, t1_seconds, 4 or 16], ...] (python ranges.py writes it)

Resumable: stop it any time (Ctrl+C, closing the window, a crash) and run the same command again; a sub-frame is only
ever stored whole (rifeutil.write_jpg), so what is in store/ is finished work. Without a usable Vulkan GPU it stops with
a message (rifeutil.py: RIFE_GPU=-1 runs on the CPU, 15 times slower)."""
import os, sys, time, json, glob, shutil
import preflight
import numpy as np
import cv2
import clipio
import rifeutil

CHUNK = 96
MB = 0.38           # one stored sub-frame, MB (1344 px wide crop; ranges.py scales it for a wider store)
DUP = 0.20          # change (see motion) below which a frame is a copy of its predecessor: the two recording
                    # duplicates of the house example measured 0.10 and 0.14, the stillest real pause of the aim 0.32


def path(clip, key):
    return f"store/{clip}/{key:08d}.jpg"


def save(clip, key, rgb):
    rifeutil.write_jpg(path(clip, key), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def motion(a, b):
    return float(np.abs(a[::6, ::6].astype(np.int16) - b[::6, ::6]).mean())


def run(clip, t0, t1, factor, rife, log):
    tween = rifeutil.Tween(rife)                     # never ask RIFE for a time step near 0 or 1 (see rifeutil.Tween)
    os.makedirs(f"store/{clip}", exist_ok=True)
    step = 16 // factor
    a = max(0, int(np.floor(clipio.t2n(clip, t0))))
    b = min(clipio.n_frames(clip) - 1, int(np.ceil(clipio.t2n(clip, t1))))
    done = made = fixed = 0
    t_run = time.time()
    n = a
    while n < b:
        m = min(b, n + CHUNK)
        need = [k for j in range(n, m) for k in range(j * 16, j * 16 + 16, step) if not os.path.exists(path(clip, k))]
        if not os.path.exists(path(clip, m * 16)):
            need.append(m * 16)
        if not need:
            done += (m - n) * factor
            n = m
            continue
        fa, fb = max(0, n - 1), min(clipio.n_frames(clip) - 1, m + 4)
        try:
            fr = clipio.read_frames(clip, fa, fb)
        except (AssertionError, ValueError) as e:
            rifeutil.die(f"prep.py: ffmpeg could not decode frames {fa}..{fb} of {clipio.path(clip)} ({type(e).__name__}: {e}). The file is cut off or damaged "
                         f"(an unfinished recording, an interrupted copy), or it changed after mkpts.py ran. Copy it again, then  python ingest.py --force --only {clip} && python mkpts.py {clip}  "
                         "and run prep.py again; what was built before this point is kept.")
        off = max(0, n - 1)
        mo = [motion(fr[i], fr[i + 1]) for i in range(len(fr) - 1)]
        med = float(np.median(mo))
        # a frame (or a run of up to 3) that repeats its predecessor while the scene is moving is a recording
        # hiccup: interpolate straight across it, from the real frames on both sides
        prv = list(range(len(fr)))                   # for every frame: the real frame at or before it ...
        nxt = list(range(1, len(fr) + 1))            # ... and the next real frame after it
        i = 1
        while i < len(fr):
            if mo[i - 1] < DUP and med > 0.6:
                j = i
                while j < len(fr) - 1 and mo[j] < DUP:
                    j += 1                            # fr[i..j] repeat fr[i-1]; fr[j+1] is the next real frame
                if j + 1 < len(fr) and j - i + 1 <= 3:
                    for q in range(i - 1, j + 1):
                        prv[q], nxt[q] = i - 1, j + 1
                    if (clip, off + i, j - i + 1) not in log:
                        log.append((clip, off + i, j - i + 1))
                        fixed += j - i + 1
                i = j + 1
            else:
                i += 1

        def sub(q, s):                                # the picture s/16 of a frame after frame q of this chunk
            t = (q - prv[q] + s / 16) / (nxt[q] - prv[q])
            return fr[prv[q]] if t == 0 else tween(fr[prv[q]], fr[nxt[q]], t, tag=(clip, off + prv[q], off + nxt[q]))

        for j in range(n, m):
            for s in range(0, 16, step):
                k = j * 16 + s
                if os.path.exists(path(clip, k)):
                    continue
                save(clip, k, sub(j - off, s))
                made += 1
        if not os.path.exists(path(clip, m * 16)):
            save(clip, m * 16, sub(m - off, 0))
            made += 1
        n = m
        print(f"    {clip}: frame {n} of {b}, {made} sub-frames written, {made / max(1e-9, time.time() - t_run):.1f} per second", flush=True)
    return a, b, made, fixed


def load_spec(arg):
    """ranges.json -> [[clip, t0, t1, factor], ...], every entry checked against src/ and the pts tables."""
    if not os.path.exists(arg):
        sys.exit(f"{arg} not found in {os.getcwd()}: python ranges.py writes it (from timeline.py); then  python prep.py ranges.json")
    try:
        spec = json.load(open(arg, encoding="utf-8-sig"))
        spec = [(str(c), float(t0), float(t1), int(f)) for c, t0, t1, f in spec]
    except (ValueError, TypeError) as e:
        sys.exit(f"{arg} is not a list of [clip, t0_seconds, t1_seconds, factor] ({e}): do not edit it by hand, run  python ranges.py  to write it again")
    for c, t0, t1, f in spec:
        if not os.path.exists(f"pts/{c}.csv"):
            sys.exit(f"{arg}: clip {c!r} has no pts/{c}.csv: it is not in src/ (clips there: "
                     f"{', '.join(sorted(os.path.basename(p)[:-4] for p in glob.glob('pts/*.csv'))) or 'none'}). "
                     "Run  python ingest.py && python mkpts.py  or fix the clip name in timeline.py, then  python ranges.py")
        if 16 % f or f < 1:
            sys.exit(f"{arg}: factor {f} for {c} must be 1, 2, 4, 8 or 16 (a divisor of 16)")
        if not t0 < t1:
            sys.exit(f"{arg}: range {c} {t0:g}..{t1:g} s is empty or backwards")
        if t0 > clipio.n2t(c, clipio.n_frames(c) - 1):
            sys.exit(f"{arg}: range {c} {t0:g}..{t1:g} s starts after the end of the clip ({clipio.n2t(c, clipio.n_frames(c) - 1):.2f} s): "
                     "the file is out of date, run  python ranges.py  again")
    return spec


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python prep.py ranges.json      (python ranges.py writes ranges.json from timeline.py)")
    spec = load_spec(sys.argv[1])                                       # [[clip, t0, t1, factor], ...]
    need_mb = sum((clipio.t2n(c, t1) - clipio.t2n(c, t0)) * f * MB * clipio.CROP_W / 1344.0 for c, t0, t1, f in spec)
    os.makedirs("store", exist_ok=True)
    free_mb = shutil.disk_usage("store").free / 2**20
    if free_mb < need_mb:
        print(f"WARNING: ranges.json needs up to {need_mb / 1024:.1f} GB in store/ (less if part of it is already there), the drive has "
              f"{free_mb / 1024:.1f} GB free: the disk may fill up. Free space or move the project folder; a full disk stops the script with "
              "a message and the run can be continued.", flush=True)
    rife = rifeutil.load()
    log, t_start, kept = [], time.time(), 0
    try:
        for clip, t0, t1, factor in spec:
            ts = time.time()
            a, b, made, fixed = run(clip, t0, t1, factor, rife, log)
            kept += (b - a) * factor + 1 - made
            print(f"{clip} {t0:.2f}-{t1:.2f}s  frames {a}-{b}  x{factor}: wrote {made} sub-frames, repaired {fixed} duplicates, "
                  f"{time.time() - ts:.0f}s", flush=True)
    except KeyboardInterrupt:
        rifeutil.die("Stopped. What is in store/ is complete: run the same command again to continue from here.", 130)
    print("frames the recording duplicated, rebuilt from their neighbours (clip, frame, how many):", log)
    if log:
        print("   check each with:  python cadence.py <clip> <frame-8> <frame+8> --detail")
    print(f"total {time.time() - t_start:.0f}s" + (f" ({kept} sub-frames were already in the store, from an earlier run or an overlapping range)" if kept > 0 else ""), flush=True)
    rifeutil.finish()
