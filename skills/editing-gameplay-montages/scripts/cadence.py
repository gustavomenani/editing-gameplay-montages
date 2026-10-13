"""Frame cadence of a SOURCE clip: how much the picture changes from each real frame to the next
(every value is labelled with the later frame of the pair).
Finds frames the recorder duplicated (they must be repaired before interpolating, or slow motion
freezes on them) and tells them apart from real pauses of the aim.

usage: python cadence.py c1 5290 5725             map, one character per frame:
                                                    .  normal     D  identical to the previous frame
                                                    d  almost still     ^  big jump (flick, cut, flash)
       python cadence.py c1 5296 5316 --detail    per-frame numbers by screen region

Reading --detail:
  recording duplicate  one frame where EVERY region drops to about 0.0x between normally moving frames
                       -> python repair.py clip:frame
  real pause           the world region slows down over several frames, stops, starts again, while the
                       weapon (viewmodel) region still moves a little -> leave it alone, it is gameplay"""
import subprocess, sys
import numpy as np
import clipio
from ff import FF

clip, a, b = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
detail = "--detail" in sys.argv
# 672 x 540 grey copy of the 1344 x 1080 region the montage can show
vf = f"crop={clipio.CROP_W}:{clipio.SH}:{clipio.CROP_X}:0,scale=672:540"
raw = subprocess.run([FF, "-v", "error"] + clipio.frame_args(clip, a, b, vf) + ["-pix_fmt", "gray", "-f", "rawvideo", "-"],
                     capture_output=True).stdout
f = np.frombuffer(raw, np.uint8).reshape(-1, 540, 672).astype(np.int16)
assert len(f) == b - a + 1, (len(f), a, b)
df = np.abs(np.diff(f, axis=0))
d = df.mean((1, 2))                                   # d[i]: change from frame a+i to a+i+1
med = float(np.median(d))
print(f"{clip} frames {a}-{b}: median change {med:.2f}")
line = ""
for i, v in enumerate(d):
    line += "D" if v < 0.10 else ("d" if v < 0.25 * med else ("^" if v > 2.5 * med else "."))
    if len(line) == 100 or i == len(d) - 1:
        print("   %6d %s" % (a + i + 2 - len(line), line))
        line = ""
dups = [a + i + 1 for i, v in enumerate(d) if v < 0.10]
print("   identical to the previous frame (D): %d %s | almost still (d): %d | big jumps (^): %d | of %d" % (
    len(dups), dups[:30], ((d >= 0.10) & (d < 0.25 * med)).sum(), (d > 2.5 * med).sum(), len(d)))
if detail:
    regs = {"whole": (slice(0, 540), slice(0, 672)), "world (top middle)": (slice(60, 260), slice(150, 520)),
            "weapon (bottom right)": (slice(320, 520), slice(380, 650)), "centre": (slice(220, 320), slice(286, 386))}
    print("   change from the previous frame into each frame, by region:")
    print("   frame   " + "  ".join("%-22s" % k for k in regs))
    for i in range(len(df)):
        print("   %6d  %s" % (a + i + 1, "  ".join("%-22.2f" % df[i][rs].mean() for rs in regs.values())))
