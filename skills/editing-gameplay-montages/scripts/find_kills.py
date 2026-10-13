"""Locate the kills of a Valorant clip by its kill banner (the skull badge that pops up bottom-centre).

usage: python find_kills.py c3              whole clip
       python find_kills.py c1 82 97        only seconds 82..97 (long clips: look at peek.py overviews first)

1. Writes kills_<clip>_NN.jpg: the banner region, 10 pictures per second, each labelled with its time in
   tenths of a second. READ THESE SHEETS: to the eye the banner is unmistakable, and they also show
   what the pixel counts cannot (which weapon, how many skulls, an ability flashing through the region).
2. Prints candidate banner frames from pixel counts inside the badge: "new" = it appears on an empty
   region, "again" = it changes while on screen. On the house example all 26 real kills had a
   candidate (the 22 whose frame was measured: within 1 frame), next to about two false candidates
   per kill: the badge's own animation and fade-out, and bright or red effects crossing the region.
   The sheet decides.
Then write the confirmed frames to banners.json for kill_table.py:  {"c3": [133, 292, 556, 1187], ...}

Geometry is the 1920x1080 Valorant HUD (scaled for other sizes). Other games need their own regions."""
import subprocess, sys
import numpy as np
import cv2
import clipio
from ff import FF

clip = sys.argv[1]
t0 = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
t1 = float(sys.argv[3]) if len(sys.argv) > 3 else float(clipio.pts(clip)[-1])
k = clipio.SH / 1080.0
BIG = [int(round(v * k)) for v in (220, 220, 850, 756)]          # w, h, x, y: banner with some surroundings (sheets)
ICON = [int(round(v * k)) for v in (50, 50, 935, 841)]           # the badge itself (pixel counts)

# ---------------------------------------------------------------- 1. sheets for the eyes
raw = subprocess.run([FF, "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", clipio.path(clip), "-map", "0:v:0",
                      "-vf", "fps=10,crop=%d:%d:%d:%d,scale=110:110" % tuple(BIG), "-pix_fmt", "bgr24", "-f", "rawvideo", "-"],
                     capture_output=True).stdout
tiles = np.frombuffer(raw, np.uint8).reshape(-1, 110, 110, 3).copy()
for i, t in enumerate(tiles):
    cv2.rectangle(t, (0, 0), (46, 15), (0, 0, 0), -1)
    cv2.putText(t, "%d" % round((t0 + i / 10) * 10), (2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)
per = 18 * 13
for s in range(0, len(tiles), per):
    chunk = tiles[s:s + per]
    sheet = np.zeros((110 * ((len(chunk) + 17) // 18), 110 * 18, 3), np.uint8)
    for q, t in enumerate(chunk):
        sheet[110 * (q // 18):110 * (q // 18 + 1), 110 * (q % 18):110 * (q % 18 + 1)] = t
    cv2.imwrite("kills_%s_%02d.jpg" % (clip, s // per + 1), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
print("sheets: kills_%s_01.jpg .. _%02d.jpg (labels = tenths of a second; %d tiles)" % (clip, (len(tiles) + per - 1) // per, len(tiles)))

# ---------------------------------------------------------------- 2. candidates from pixel counts, exact frames
a = max(0, int(np.floor(clipio.t2n(clip, t0))))
b = min(clipio.n_frames(clip) - 1, int(np.ceil(clipio.t2n(clip, t1))))
raw = subprocess.run([FF, "-v", "error"] + clipio.frame_args(clip, a, b, "crop=%d:%d:%d:%d" % tuple(ICON))
                     + ["-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True).stdout
f = np.frombuffer(raw, np.uint8).reshape(-1, ICON[1], ICON[0], 3).astype(int)
assert len(f) == b - a + 1, (len(f), a, b)
area = ICON[0] * ICON[1] / 2500.0
white = (f.min(3) > 185).sum((1, 2)) / area                       # bright, colourless pixels
red = ((f[..., 0] > 170) & (f[..., 1] < 90) & (f[..., 2] < 90)).sum((1, 2)) / area
cands = []
for n in range(8, len(f) - 6):
    before, after = white[n - 8:n], white[n:n + 6]
    if np.median(before) < 20 and white[n - 1] < 40 and white[n] >= 80 and (after >= 80).sum() >= 5:
        cands.append((n, "new"))
    elif np.median(before) >= 100 and (after[2:] >= 80).sum() >= 3:
        r0 = np.median(red[n - 8:n])
        if (r0 >= 40 and red[n] < 0.5 * r0 and red[n - 1] >= 0.5 * r0) or \
           (white[n] < 0.5 * np.median(before) and white[n - 1] >= 0.5 * np.median(before)):
            if not cands or n - cands[-1][0] > 6:
                cands.append((n, "again"))
print("candidate banner frames: frame, seconds, sheet tile, kind, frames since the previous candidate")
prev = None
for n, kind in cands:
    t = clipio.n2t(clip, a + n)
    print("   %5d  %6.2fs  tile %4d  %-5s %s" % (a + n, t, int(round(t * 10)), kind, "" if prev is None else "+%d" % (n - prev)))
    prev = n
print("How to read them: a kill is where the badge APPEARS on the sheet; take the candidate frame at that tile.\n"
      "The badge animates for half a second and stays about 1.9 s, so candidates +10, +21 and +30 frames after\n"
      "a real one, and one at about +113 (it fading out), are the same kill, not new ones.\n"
      "Kills less than 2 s apart: the second badge starts while the first is still up (it turns red, more skulls),\n"
      "and no candidate is reliable. Count the shots instead: python peek.py <clip> <frame-20> <frame+30> shows each\n"
      "muzzle flash and the ammo counter dropping; the banner frame is then the flash frame + 3 or 4, and\n"
      "kill_table.py accepts [banner, K] to set the flash frame directly.")
