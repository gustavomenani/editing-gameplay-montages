"""Rebuild the in-between frames next to every real frame.

Measured on this RIFE build (v4.25, ncnn): for a time step below about 0.08 the network returns the first
frame unchanged (and the second one above 0.92), then catches up by about 0.25. In a 16x grid that makes
the sub-frames 15/16, 0 and 1/16 identical: slow motion stalls for an eighth of a frame at every real frame
and hurries afterwards. Steps between 0.25 and 0.75 are linear.

Fix: the sub-frames 1, 2, 3 sixteenths are interpolated between the real frame and the 4/16 sub-frame at
steps 0.25 / 0.5 / 0.75 (the linear zone), and 13, 14, 15 between the 12/16 sub-frame and the next real frame.
Intervals that only have an 8x grid get 2/16 and 14/16 the same way.

usage: python fixends.py [clip ...]      resumable (fixends_done.json)"""
import glob, json, os, sys
import preflight
import cv2
import rifeutil

DONE = "fixends_done.json"
try:
    done = set(tuple(x) for x in json.load(open(DONE))) if os.path.exists(DONE) else set()
except ValueError:
    done = set()                                     # a half-written state file (the script was killed while saving it): start over, the rebuild is repeatable


def save_done():
    json.dump(sorted(done), open(DONE + ".part", "w"))
    os.replace(DONE + ".part", DONE)


def p(clip, key):
    return f"store/{clip}/{key:08d}.jpg"


def rd(clip, key):
    if not rifeutil.is_jpeg_complete(p(clip, key)):
        rifeutil.die(f"fixends.py: {p(clip, key)} is truncated or damaged: delete it, run  python prep.py ranges.json  again, then fixends.py "
                     "(python check_store.py lists the damaged files, --delete removes them)")
    return cv2.cvtColor(cv2.imread(p(clip, key)), cv2.COLOR_BGR2RGB)


def wr(clip, key, rgb):
    rifeutil.write_jpg(p(clip, key), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


clips = sys.argv[1:] or sorted(os.path.basename(d) for d in glob.glob("store/*"))
for c in clips:
    if not os.path.isdir(f"store/{c}"):
        sys.exit(f"fixends.py: there is no store/{c}/ (stores here: {', '.join(os.path.basename(d) for d in glob.glob('store/*')) or 'none'}): "
                 "clip names are the short names of src/ (c1, c2 ...)")
if not clips:
    sys.exit("fixends.py: store/ is empty: build it first with  python ranges.py && python prep.py ranges.json")
rife = rifeutil.load()
n = 0
try:
    for clip in clips:
        keys = set(int(os.path.basename(f)[:-4]) for f in glob.glob(f"store/{clip}/*.jpg"))
        for j in sorted({k // 16 for k in keys}):
            b = j * 16
            if (clip, j) in done or not {b, b + 4, b + 12, b + 16} <= keys or b + 2 not in keys:
                continue
            A, K4, K12, B = rd(clip, b), rd(clip, b + 4), rd(clip, b + 12), rd(clip, b + 16)
            jobs = [(1, A, K4, 0.25), (2, A, K4, 0.5), (3, A, K4, 0.75), (13, K12, B, 0.25), (14, K12, B, 0.5), (15, K12, B, 0.75)]
            for s, x, y, t in jobs:
                if b + s in keys:
                    wr(clip, b + s, rife.process_cv2(x, y, t))
                    n += 1
            done.add((clip, j))
            if len(done) % 40 == 0:
                save_done()
                print(clip, j, "| rebuilt", n, flush=True)
except KeyboardInterrupt:
    save_done()
    rifeutil.die("Stopped. Run the same command again to continue (fixends_done.json remembers what is finished).", 130)
save_done()
print("done: rebuilt", n, "sub-frames")
rifeutil.finish()
