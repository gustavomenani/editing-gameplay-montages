"""Rebuild source frames that the recording duplicated: every stored sub-frame between the two real
neighbours of the bad frame is re-interpolated directly from those neighbours.

usage: python repair.py c3:125 c1:5683        clip:frame of each frame that is a copy of its neighbour

prep.py already repairs the exact duplicates it meets while it builds the store; use this for frames
found afterwards (cadence.py marks them with D). Do NOT use it on a real pause of the aim (cadence.py
--detail tells the two apart)."""
import os, sys, glob
import preflight
import cv2, numpy as np
import rifeutil


def parse(arg):
    try:
        clip, j = arg.rsplit(":", 1)
        return clip, int(j)
    except ValueError:
        sys.exit(f"repair.py: {arg!r} is not clip:frame, e.g. c3:125 (the clip's short name from src/, and the source frame number cadence.py printed)")


def read(clip, j, what):
    f = f"store/{clip}/{j * 16:08d}.jpg"
    if not os.path.exists(f):
        sys.exit(f"repair.py: {f} is not in the store ({what} of {clip}:{j}). Frame {j} must lie inside a range the store was built for: "
                 f"python ranges.py && python prep.py ranges.json builds it (check with python check_store.py)")
    if not rifeutil.is_jpeg_complete(f):
        sys.exit(f"repair.py: {f} is truncated or damaged: delete it, run  python prep.py ranges.json  to build it again, then repair.py")
    im = cv2.imread(f)
    if im is None:                                          # a whole FFD9 tail does not prove the picture decodes: imread returns None
        sys.exit(f"repair.py: {f} does not decode (a damaged JPEG that still ends in FFD9): python check_store.py --delete removes it, "
                 "python prep.py ranges.json rebuilds it, then run repair.py again")
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB)


jobs = [parse(a) for a in sys.argv[1:]]
if not jobs:
    sys.exit(__doc__)
for clip, j in jobs:
    if not os.path.isdir(f"store/{clip}"):
        sys.exit(f"repair.py: there is no store/{clip}/ (stores here: {', '.join(os.path.basename(d) for d in glob.glob('store/*')) or 'none'}): "
                 "clip names are the short names of src/ (c1, c2 ...)")
    read(clip, j - 1, "the frame before it")
    read(clip, j, "the frame itself")
    read(clip, j + 1, "the frame after it")
rife = rifeutil.load()
tween = rifeutil.Tween(rife)                         # no time steps near 0 or 1 (see rifeutil.Tween)
for clip, j in jobs:
    k0, k1 = (j - 1) * 16, (j + 1) * 16
    f0 = read(clip, j - 1, "the frame before it")
    f1 = read(clip, j + 1, "the frame after it")
    n = 0
    for path in sorted(glob.glob(f"store/{clip}/*.jpg")):
        k = int(os.path.basename(path)[:-4])
        if k0 < k < k1:
            out = tween(f0, f1, (k - k0) / 32.0, tag=(clip, j))
            rifeutil.write_jpg(path, cv2.cvtColor(out, cv2.COLOR_RGB2BGR))
            n += 1
    # check: the rebuilt frame must now differ from both neighbours (read through read(): a store file that does not decode stops here instead of raising)
    mid = read(clip, j, "the rebuilt frame").astype(np.int16)
    a = read(clip, j - 1, "the frame before it").astype(np.int16); b = read(clip, j + 1, "the frame after it").astype(np.int16)
    print(clip, j, "rewrote", n, "sub-frames; rebuilt frame vs previous %.2f, vs next %.2f" % (np.abs(mid - a).mean(), np.abs(mid - b).mean()))
rifeutil.finish()
