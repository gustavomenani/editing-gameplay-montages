"""For every kill of timeline.py: where does the gunshot start in the clip's own sound, relative to the
frame that sits on the beat? That offset is the segment's `lag` (one value per kill).

usage: python kill_lags.py        -> a strip of sound level per 1/8 frame from K-2 to K+6, the detected onset
                                     and the lag currently in the timeline; onsets.json

Reading a strip: 8 digits per source frame, the first group is frame K-2, so the 3rd group starts at K.
The gunshot is where the digits jump (say from 1-2 to 6-9); its position minus K is the lag.
  onset K+2.75    clear jump, use it
  onset K~2.25    weaker jump (found on a second, looser pass): look at the strip before using it
  onset K ?       nothing clean (voice chat over the shot, slow sounds): read the strip yourself, or take
                  audio_after_K of that kill in kills.json (kills_auto.py), or the value of a neighbouring kill of the clip
With the right lag the gunshot is heard exactly on the beat. Verify afterwards with audio.py, which prints
where the loudest game-sound onset of each kill lands. onsets.json is a record for you; nothing reads it."""
import json, subprocess
import preflight
import numpy as np
T = preflight.timeline()
import clipio
from ff import FF

SR = 48000
aud = {}


def audio(c):
    if c not in aud:
        raw = subprocess.run([FF, "-v", "error", "-i", clipio.path(c), "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                             capture_output=True).stdout
        aud[c] = np.frombuffer(raw, np.float32) if len(raw) else None
    return aud[c]


n = 100                                               # 2.08 ms bins = 8 per source frame
out = {}
print("source sound (highs) per 1/8 frame, frames K-2 .. K+6, 0-9 relative to the loudest bin in the window")
for k, lv, i in T.KILLS:
    s = T.SEGS[i]; c = s["clip"]
    K = float(s["map"](k)[0])
    x = audio(c)
    if x is None:
        print("  beat %5.1f %s: no audio track in src/%s.*: the lag cannot be measured (record with the game sound on; the timeline's lag stays a guess)" % (k, c, c))
        out[str(k)] = None
        continue
    hp = np.diff(x, prepend=x[0])
    hp = np.concatenate([np.zeros(30 * n), hp, np.zeros(64 * n)])         # a kill near the start or the end of the clip still has a full window
    a = int(clipio.n2t(c, K - 2) * SR) + 30 * n
    e = np.sqrt((hp[a:a + 64 * n].reshape(-1, n) ** 2).mean(1))
    floor = np.sqrt((hp[a - 30 * n:a].reshape(-1, n) ** 2).mean(1)).mean()
    mx = e.max()
    if mx == 0:
        print("  beat %5.1f %s K=%7.1f  the clip's sound is silent around this kill: the lag cannot be measured here" % (k, c, K))
        out[str(k)] = None
        continue
    st = "".join(str(min(9, int(v / mx * 9.99))) for v in e)
    onset, sure = None, True                          # first bin from K-0.5 on that jumps well above what came just before it
    for j in range(12, 56):
        base = max(floor, e[max(0, j - 6):j].mean())
        if e[j] > 2.6 * base and e[j] > 0.22 * mx:
            onset = j / 8 - 2
            break
    if onset is None:                                 # looser: twice the six bins before it, and a good part of the peak
        for j in range(12, 56):
            if e[j] > 2.0 * e[max(0, j - 6):j].mean() and e[j] > 0.35 * mx:
                onset, sure = j / 8 - 2, False
                break
    out[str(k)] = onset
    now = s["lag"][[kk for kk, _ in s["kills"]].index(k)]
    print("  beat %5.1f %s K=%7.1f  %s | onset K%s  (lag in the timeline %.2f)" % (
        k, c, K, " ".join(st[j:j + 8] for j in range(0, 64, 8)),
        " ?" if onset is None else ("%+.2f" % onset if sure else "~%.2f" % onset), now))
json.dump(out, open("onsets.json", "w"))
