"""Look at the source footage: a contact sheet of real frames, each labelled with its frame index.
This is how the editor "watches" a clip: to choose moments, find where an ability starts and ends,
check what is on screen at an anchor of timeline.py.

usage: python peek.py c3 268 300            every frame 268..300              -> peek_c3_268.jpg
       python peek.py c3 0 1320 30          every 30th frame (0.5 s steps): overview of a whole clip
       python peek.py c3 268 300 1 full     whole 1920-wide frame instead of the 1344-wide crop the montage can show

Tiles are 320 x 270 (crop) or 384 x 216 (full; always in a reference-style project, whose clipio.py keeps the whole
frame), 8 per row, 64 per sheet (more tiles go to peek_c3_0_2.jpg, ...).
A whole clip at one tile per second:  python peek.py c3 0 99999 60"""
import glob, os, subprocess, sys
import preflight
import numpy as np
import cv2
import clipio
from ff import FF

USAGE = "usage: python peek.py c3 268 300 [step] [full]      clip name (as in src/), first and last source frame, every step-th frame, 'full' = whole 1920 px frame"
if len(sys.argv) < 4:
    sys.exit(USAGE)
clip = sys.argv[1]
try:
    a, b = int(sys.argv[2]), int(sys.argv[3])
    step = int(sys.argv[4]) if len(sys.argv) > 4 else 1
except ValueError:
    sys.exit(f"peek.py: the frame numbers and the step must be whole numbers, got {sys.argv[2:5]}\n{USAGE}")
if not os.path.exists(f"pts/{clip}.csv"):
    have = sorted(os.path.basename(p)[:-4] for p in glob.glob("pts/*.csv"))
    sys.exit(f"peek.py: no clip {clip!r}: pts/{clip}.csv does not exist. Clips here: {', '.join(have) or 'none (run python ingest.py && python mkpts.py)'}")
if step < 1 or a < 0:
    sys.exit(f"peek.py: the first frame ({a}) must be 0 or more and the step ({step}) 1 or more")
if a >= clipio.n_frames(clip):
    sys.exit(f"peek.py: {clip} has frames 0..{clipio.n_frames(clip) - 1} ({clipio.n2t(clip, clipio.n_frames(clip) - 1):.2f} s), the first frame asked for is {a}")
full = (len(sys.argv) > 5 and sys.argv[5] == "full") or clipio.CROP_W >= clipio.SW     # reference style: the montage shows the whole frame
b = min(b, clipio.n_frames(clip) - 1)
if b < a:
    sys.exit(f"peek.py: the last frame ({b}) is before the first ({a})")
tw, th = (384, 216) if full else (320, 270)
crop = "" if full else f"crop={clipio.CROP_W}:{clipio.SH}:{clipio.CROP_X}:0,"
tiles = []
for n in range(a, b + 1, step):
    # one small exact read per tile when stepping (a long range would not fit in memory), one read for a dense range
    if step > 1 or not tiles:
        hi = n if step > 1 else b
        raw = subprocess.run([FF, "-v", "error"] + clipio.frame_args(clip, n, hi, f"{crop}scale={tw}:{th}")
                             + ["-pix_fmt", "bgr24", "-f", "rawvideo", "-"], capture_output=True).stdout
        chunk = np.frombuffer(raw, np.uint8).reshape(-1, th, tw, 3)
        assert len(chunk) == hi - n + 1, (len(chunk), n, hi)
        base = n
    t = chunk[n - base].copy()
    cv2.rectangle(t, (0, 0), (118, 20), (0, 0, 0), -1)
    cv2.putText(t, "%s %d" % (clip, n), (3, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    tiles.append(t)
per = 64                                              # 8 x 8 tiles per sheet stays readable
for pg in range(0, len(tiles), per):
    chunk = tiles[pg:pg + per]
    cols = min(8, len(chunk))
    sheet = np.zeros((th * ((len(chunk) + cols - 1) // cols), tw * cols, 3), np.uint8)
    for i, t in enumerate(chunk):
        sheet[th * (i // cols):th * (i // cols + 1), tw * (i % cols):tw * (i % cols + 1)] = t
    out = "peek_%s_%d%s.jpg" % (clip, a, "" if pg == 0 else "_%d" % (pg // per + 1))
    cv2.imwrite(out, sheet, [cv2.IMWRITE_JPEG_QUALITY, 86])
    print(out, "%d tiles, frames %d..%d step %d" % (len(chunk), a + pg * step, min(b, a + (pg + len(chunk) - 1) * step), step))
print("%d tiles in all, %.2f s .. %.2f s" % (len(tiles), clipio.n2t(clip, a), clipio.n2t(clip, b)))
