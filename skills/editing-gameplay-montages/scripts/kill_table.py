"""Precise table of every kill: the frame to put on the beat, the gunshot in the sound, and a gallery.

usage: python kill_table.py        reads banners.json, e.g. {"c3": [133, 292], "c4": [306, [842, 838]]}
                                   an entry is a banner frame (from find_kills.py), or [banner frame, K]
                                   to fix K yourself after looking at the gallery

For each kill:
  shot    the gunshot in the clip's sound: the strongest sudden onset 4..75 ms before the banner
  K       the muzzle-flash frame = the frame that goes ON THE BEAT in timeline.py. Suggested as the
          frame, among the 5 up to the gunshot, where the picture around the muzzle changes most
          (the "change" row peaks there; "bright" = share of very bright pixels, for orientation).
          On the house example that was exact for 21 of 22 kills and one frame early on a point-blank
          shot. CONFIRM on the gallery: flash visible on tile "+0" and absent on "-1". If it is not,
          put [banner, K] in banners.json and run again. K is usually 3 or 4 frames before the banner
          (2 to 6 seen).
  lag     shot frame - K: first value for the segment's `lag` (kill_lags.py refines it; 1.4 to 3.3
          frames on the house example). A clip whose sound is voice chat gives a meaningless shot.
-> gallery_N.jpg (one row per kill: tiles K-6 -3 -2 -1 +0 +1 +2 +3 +6) and kills.json, a record for you;
   no other script reads it."""
import json, subprocess
import numpy as np
import cv2
import clipio
from ff import FF

BANNER = json.load(open("banners.json", encoding="utf-8-sig"))
OFFS = (-6, -3, -2, -1, 0, 1, 2, 3, 6)
TW, TH = 222, 187
table, tiles = {}, []
for c, bs in BANNER.items():
    raw = subprocess.run([FF, "-v", "error", "-i", clipio.path(c), "-map", "0:a:0", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    hp = np.diff(x, prepend=0)                                  # emphasise the crack of the shot
    w = 96                                                      # 2 ms
    le = np.log(np.sqrt(np.convolve(hp * hp, np.ones(w) / w, mode="same")) + 1e-5)
    k = 240                                                     # rise over 5 ms
    table[c] = []
    for entry in bs:
        nb, given = (entry[0], entry[1]) if isinstance(entry, (list, tuple)) else (entry, None)
        tb = clipio.pts(c)[nb]
        a, b = int((tb - 0.16) * 48000), int((tb + 0.03) * 48000)
        rise = le[a + k:b + k] - le[a:b]
        pk = [i for i in range(60, len(rise) - 60) if rise[i] == rise[i - 60:i + 60].max() and rise[i] > 0.9]
        cands = [((a + i + k / 2) / 48000, float(rise[i]), float(le[a + i + k])) for i in pk]
        best = [q for q in cands if -0.075 <= q[0] - tb <= -0.004]
        shot = max(best, key=lambda q: q[1] + 0.5 * q[2])[0] if best else tb - 0.025
        sf = float(clipio.t2n(c, shot))
        # the muzzle region (screen centre-right, in the 1344-wide crop): bright pixels, and change from the previous frame
        lo = max(0, nb - 15)
        fr = clipio.read_frames(c, lo, nb + 2).astype(np.int16)
        reg = fr[:, 230:700, 560:1100]
        bright = (reg.max(3) > 235).mean((1, 2))[1:] * 100
        change = np.abs(np.diff(reg, axis=0)).mean((1, 2, 3))   # change INTO each frame from the one before
        frames = np.arange(lo + 1, nb + 3)
        ok = (frames >= np.floor(sf) - 5) & (frames <= np.floor(sf))
        K = given if given is not None else int(frames[ok][np.argmax(change[ok])])
        table[c].append({"banner_frame": int(nb), "shot_frame": round(sf, 2), "K": int(K), "lag": round(sf - K, 2),
                         "K_set_by_hand": given is not None})
        print("%s banner %d | gunshot at frame %.1f (%.0f ms before the banner%s) | K = %d%s | lag %.2f" % (
            c, nb, sf, (tb - shot) * 1000, "" if best else ", NOT FOUND: guessed", K, " (given)" if given is not None else "", sf - K))
        print("    frame :", " ".join("%5d" % n for n in frames))
        print("    bright:", " ".join("%5.2f" % v for v in bright))
        print("    change:", " ".join("%5.1f" % v for v in change))
        g0 = max(0, K - 6)
        g = clipio.read_frames(c, g0, min(clipio.n_frames(c) - 1, K + 6))
        for off in OFFS:
            if not 0 <= K + off - g0 < len(g):
                tiles.append(np.zeros((TH, TW, 3), np.uint8))
                continue
            im = cv2.cvtColor(cv2.resize(g[K + off - g0][:, 32:1312], (TW, TH), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2BGR)
            cv2.rectangle(im, (0, 0), (TW, 17), (0, 0, 0), -1)
            cv2.putText(im, "%s K=%d %+d" % (c, K, off), (3, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
            tiles.append(im)
json.dump(table, open("kills.json", "w"), indent=1)
n = len(OFFS)
per = n * 9
for s in range(0, len(tiles), per):
    chunk = tiles[s:s + per]
    sheet = np.zeros((TH * ((len(chunk) + n - 1) // n), TW * n, 3), np.uint8)
    for i, im in enumerate(chunk):
        sheet[TH * (i // n):TH * (i // n + 1), TW * (i % n):TW * (i % n + 1)] = im
    cv2.imwrite(f"gallery_{s // per}.jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
print("gallery_0.jpg .. gallery_%d.jpg: one row per kill (9 rows per sheet), tiles K-6 -3 -2 -1 +0 +1 +2 +3 +6; kills.json written"
      % ((len(tiles) + per - 1) // per - 1))
