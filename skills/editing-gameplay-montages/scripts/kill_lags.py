"""For every kill of timeline.py: where does the gunshot start in the clip's own sound, relative to the
frame that sits on the beat? That offset is the segment's `lag` (one value per kill), and audio.py measures it with the
function of this file (measure()) for every kill at render time: the lag of S() is None (measure it) unless you typed one.

usage: python kill_lags.py        -> a strip of sound level per 1/8 frame from K-2 to K+6, the detected onset
                                     and the lag currently in the timeline; onsets.json

Reading a strip: 8 digits per source frame, the first group is frame K-2, so the 3rd group starts at K.
The gunshot is where the digits jump (say from 1-2 to 6-9); its position minus K is the lag.
  onset K+2.7710  clear jump, use it (the refined attack, to the sample, see below)
  onset K~2.2500  weaker jump (found on a second, looser pass): look at the strip before using it; audio.py refuses to use it
                  unless the timeline types the lag (S(lag=...)) after you looked
  onset K ?       nothing clean (voice chat over the shot, slow sounds): read the strip yourself, or take
                  audio_after_K of that kill in kills.json (kills_auto.py), or the value of a neighbouring kill of the clip
With the right lag the gunshot is heard exactly on its hit. Verify afterwards with audio.py, which prints
where the loudest game-sound onset of each kill lands. onsets.json is a record for you; nothing reads it.

The attack is the START of the shot (the drum attacks of beat_hits.py / music_hits.py are the start of the drum too: both are bias-free on
a synthetic hit of known onset): a coarse pass (2.08 ms bins of the first difference, the strip below) finds WHICH rise is the shot, then
attack() reads its first sample to the sample: the first causal 4-sample RMS that reaches 7 % of the peak (-0.4 samples on a hard attack,
+0.3 / +0.4 / +0.5 ms on 1 / 3 / 6 ms ramps; the same rule as the reference style's shot_onset())."""
import json, subprocess
import numpy as np

SR = 48000
BIN = 100                                             # 2.08 ms bins = 8 per source frame (the strip)
aud = {}


def decode(path):
    """Mono 48 kHz float of the first audio stream on the FILE'S clock (the pts table's clock: a stream that starts after the video is
    padded with silence by aresample first_pts=0, otherwise the whole clip's sound would be read early); None when there is none."""
    from ff import FF
    raw = subprocess.run([FF, "-v", "error", "-i", path, "-map", "0:a:0", "-af", "aresample=async=1:first_pts=0", "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.float32) if len(raw) else None


def audio(c):
    import clipio
    if c not in aud:
        aud[c] = decode(clipio.path(c))
    return aud[c]


def attack(hp, a, b, noise=None):
    """The attack of the gunshot whose rise lies in samples a..b of hp (hp = the first difference of the sound: the crack, not the rumble),
    in samples (float), or None: the first sample where a causal 4-sample RMS of hp reaches 7 % of the shot's peak (and 3x the noise before it,
    at most half the peak). Measured on synthetic shots of known onset: -0.4 samples on a hard attack, +13 / +17 / +22 samples on 1 / 3 / 6 ms
    linear ramps (the same rule as the reference style's refstyle/audio.py shot_onset, so both styles read a shot the same way)."""
    w = 4
    s0, s1 = max(a, w + 1), min(b, len(hp) - 1)
    if s1 - s0 < 8 * w:
        return None
    dd = hp[s0 - w: s1].astype(np.float64)                    # dd[i] = the step into sample s0 - w + i
    c = np.concatenate([[0.0], np.cumsum(dd * dd)])
    env = np.sqrt((c[w:] - c[:-w]) / w)                       # env[i] = RMS of dd[i .. i + w - 1]; its newest step is into sample s0 - 1 + i
    if noise is None:
        noise = float(np.median(env[: max(8, len(env) // 4)]))
    top = float(env.max())
    if top <= 0:
        return None
    thr = min(max(3.0 * noise, 0.07 * top), 0.5 * top)
    i = int(np.argmax(env >= thr))
    return float(s0 - 2 + i)                                  # the first window whose newest step crossed is one sample after the burst's first step


def onset_near(hp, centre, half):
    """The gunshot attack (samples, float) of the sharpest rise within `half` samples of sample `centre` of hp (the first difference of a
    sound), or None: the coarse pass of measure() (the bin that jumps most above the six before it) and then attack() inside it. Used to check
    where the finished mix puts a gunshot against its hit."""
    n = BIN
    a = centre - half - 6 * n
    if a < 0 or centre + half + 4 * n >= len(hp):
        return None
    nb = (2 * half) // n + 8
    e = np.sqrt((hp[a:a + nb * n].reshape(nb, n) ** 2).mean(1))
    best, bj = 0.0, None
    for j in range(6, nb - 3):
        pre = e[j - 6:j].mean()
        if e[j] > 0.25 * e.max() and e[j] / (pre + 1e-12) > best:
            best, bj = e[j] / (pre + 1e-12), j
    if bj is None or best < 2.0:
        return None
    s_bin = a + bj * n
    return attack(hp, s_bin - n, s_bin + 3 * n, noise=float(e[max(0, bj - 6):bj].mean()))


def measure(c, K, x=None):
    """The gunshot of the kill whose muzzle flash is frame K of clip c: -> dict(lag, sure, rise, strip) or None when the clip has no sound
    track / the sound is silent around the kill. lag = onset - frame K in source frames (1/60 s) or None when nothing clean is there;
    sure False = only the looser second pass found it; rise = dB the sound jumps; strip = the 0-9 digits of the sound level."""
    import clipio
    if x is None:
        x = audio(c)
    if x is None:
        return None
    n = BIN
    hp = np.diff(x, prepend=x[0])
    hp = np.concatenate([np.zeros(30 * n), hp, np.zeros(64 * n)])         # a kill near the start or the end of the clip still has a full window
    t0 = float(clipio.n2t(c, K - 2))
    a = int(round(t0 * SR)) + 30 * n
    if a < 30 * n:                                                          # a kill before the first 2 frames of the clip: shift the window
        return None
    e = np.sqrt((hp[a:a + 64 * n].reshape(-1, n) ** 2).mean(1))
    floor = np.sqrt((hp[a - 30 * n:a].reshape(-1, n) ** 2).mean(1)).mean()
    mx = e.max()
    if mx == 0:
        return None
    st = "".join(str(min(9, int(v / mx * 9.99))) for v in e)
    onset_bin, sure = None, True                      # first bin from K-0.5 on that jumps well above what came just before it
    for j in range(12, 56):
        base = max(floor, e[max(0, j - 6):j].mean())
        if e[j] > 2.6 * base and e[j] > 0.22 * mx:
            onset_bin = j
            break
    if onset_bin is None:                             # looser: twice the six bins before it, and a good part of the peak
        for j in range(12, 56):
            if e[j] > 2.0 * e[max(0, j - 6):j].mean() and e[j] > 0.35 * mx:
                onset_bin, sure = j, False
                break
    lag, rise = None, 0.0
    if onset_bin is not None:
        s_bin = a + onset_bin * n
        pre = e[max(0, onset_bin - 6):onset_bin].mean()
        rise = 20 * np.log10((e[onset_bin:onset_bin + 6].max() + 1e-12) / (pre + 1e-12))
        at = attack(hp, s_bin - n, s_bin + 3 * n, noise=float(e[max(0, onset_bin - 6):onset_bin].mean()))   # the attack inside the bins around the coarse onset
        if at is None:
            lag = onset_bin / 8 - 2                   # no refinement possible: the start of the bin (still within a bin)
        else:
            lag = ((at - 30 * n) / SR - float(clipio.n2t(c, K))) * 60.0
    return dict(lag=lag, sure=sure, rise=float(rise), strip=st)


if __name__ == "__main__":
    import preflight
    T = preflight.timeline()
    out = {}
    print("source sound (highs) per 1/8 frame, frames K-2 .. K+6, 0-9 relative to the loudest bin in the window")
    for k, lv, i in T.KILLS:
        s = T.SEGS[i]; c = s["clip"]
        K = float(s["map"](k)[0])                      # k = the beat the shot is shown on: the anchor of the muzzle-flash frame
        m = measure(c, K)
        hit = s["hits"][[kk for kk, _ in s["kills"]].index(k)]
        key = "%.9f" % hit
        if m is None:
            x = audio(c)
            print("  beat %5.1f %s: %s" % (hit, c, ("no audio track in src/%s.*: the lag cannot be measured (record with the game sound on; the timeline's lag "
                                                     "stays a guess)" % c) if x is None else
                                           "the clip's sound is silent around this kill (K=%7.1f): the lag cannot be measured here" % K))
            out[key] = None
            continue
        lag = m["lag"]
        out[key] = lag
        now = s["lag"][[kk for kk, _ in s["kills"]].index(k)]
        print("  beat %5.1f %s K=%7.1f  %s | onset K%s  (lag in the timeline %s)" % (
            hit, c, K, " ".join(m["strip"][j:j + 8] for j in range(0, 64, 8)),
            " ?" if lag is None else ("%+.4f" % lag if m["sure"] else "~%.4f" % lag), "measured by audio.py" if now is None else "%.2f typed" % now))
    json.dump(out, open("onsets.json", "w"))
