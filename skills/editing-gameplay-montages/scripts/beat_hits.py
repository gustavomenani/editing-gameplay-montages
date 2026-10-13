"""Kick / snare / hat strength on every half beat of a stretch of the song: the measure of music_pulses.py as a
function, so that draft_timeline.py puts kills and cuts on exactly the hits that music_pulses.py will then report.

rows = measure(m, bpm, beat0, m0, r0, r1) -> [[beat, low, mid, high], ...] for the half beats r0 .. r1 (timeline beats),
each strength 0..1:
  low  = kick / 808 / bass hit ARRIVING: the log-spectral onset (flux) of 30..140 Hz, not its energy: on a band mix the bass
         guitar keeps that band loud on nearly every half beat, an energy ratio calls every one a kick, the onset does not
  mid  = snare / clap ARRIVING: the body (160..1500 Hz) and the crack (1.5..8 kHz) must both have an onset at that instant
         (the smaller of the two, less a third of the kick's onset). A guitar chord or a vocal has the body without the crack, a
         hat the crack without the body, so neither counts as a snare; a band's snare, buried in guitars, still does
  high = anything bright arriving (above 2.5 kHz: snares, claps and every hat), the energy of that band against the 40 ms before
`m` is the mono 44.1 kHz song from decode(). The window the strengths are normalised over is the video plus 3 s each
side, like music_pulses.py, so the numbers are the same ones it prints for a timeline.py with the same music block.
An onset is taken as the strongest within +-TOL of the half beat (a live drummer drifts by about +-30 ms; the grid hits of a
produced track fall on it exactly).
raw=True returns the strengths unclipped (a loud, sharp hit is above 1: the clipped rows saturate on every kick of a dense groove)."""
import subprocess
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from ff import FF

SR = 44100
N, HOP = 2048, 256                  # STFT window / hop (samples) of the onset curves
FPS = SR / HOP
LAG = 0.032                         # s: the flux of a frame peaks when the hit sits near the middle of its window, 32 ms after the frame's start
TOL = 0.05                          # s: how far from the half beat an onset still counts
KICK_FLOOR, KICK_SPAN = 0.6, 1.0    # low = (kick onset - KICK_FLOOR) / KICK_SPAN: 0.5 at an onset of 1.1 (a hit as strong as the strongest 1 % of the song's onsets)
SNARE_SPAN, SNARE_KICK = 1.2, 0.3   # mid = (min(body, crack) - SNARE_KICK * kick onset) / SNARE_SPAN


def decode(path):
    """The song as mono float32 at 44.1 kHz."""
    raw = subprocess.run([FF, "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    m = np.frombuffer(raw, np.float32)
    if len(m) < SR:
        raise SystemExit("cannot read audio from %s" % path)
    return m


def onsets(x):
    """x: mono float32. -> (kick, body, crack): the onset curve of 30..140 / 160..1500 / 1500..8000 Hz, one value per HOP samples, each the
    positive log-spectral flux of that band minus its running median over 0.4 s, divided by its own 99th percentile (a strong hit is about 1 or more)"""
    win = np.hanning(N + 1)[:N].astype(np.float32)
    fr = sliding_window_view(x.astype(np.float32), N)[::HOP]
    f = np.fft.rfftfreq(N, 1 / SR)
    nb = int(np.searchsorted(f, 8000))
    S = np.empty((len(fr), nb), np.float32)
    for i in range(0, len(fr), 1024):
        S[i:i + 1024] = np.abs(np.fft.rfft(fr[i:i + 1024] * win, axis=1))[:, :nb]
    f = f[:nb]
    L = np.log1p(30.0 * S / np.percentile(S[:, f < 2000], 99.5))
    d = np.vstack([np.zeros((1, nb), np.float32), np.maximum(L[1:] - L[:-1], 0)])
    pad = int(FPS * 0.4) // 2

    def band(lo, hi):
        v = d[:, (f >= lo) & (f < hi)].sum(1)
        v = np.maximum(v - np.median(sliding_window_view(np.pad(v, pad, mode="edge"), 2 * pad + 1), axis=1), 0)
        return v / (np.percentile(v, 99) + 1e-9)

    return band(30, 140), band(160, 1500), band(1500, 8000)


def measure(m, bpm, beat0, m0, r0, r1, raw=False):
    per = 60.0 / bpm
    bt = lambda r: beat0 + (m0 + r) * per
    dur = len(m) / SR
    ta = max(0.0, bt(r0) - 3.0)
    a0, a1 = int(ta * SR), min(len(m), int((bt(r1) + 3.0) * SR))
    if a1 - a0 < SR:
        raise SystemExit("beats %g .. %g (%.1f .. %.1f s) lie outside the music (%.1f s long)" % (r0, r1, bt(r0), bt(r1), dur))
    x = m[a0:a1]
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = (f / 2500.0) ** 4
    high = np.fft.irfft(X * (g / np.sqrt(1 + g * g)), n=len(x))
    w = int(SR * 4 / 1000)
    eh = np.sqrt(np.convolve(high * high, np.ones(w) / w, mode="same"))
    kick, body, crack = onsets(x)

    def hat(r, pre_ms=40, post_ms=18):
        c = int(round((bt(r) - ta) * SR))
        lo, hi = c - int(pre_ms / 1000 * SR), c - int(0.006 * SR)
        a_lo, a_hi = c + int(0.004 * SR), c + int(post_ms / 1000 * SR)
        if lo < 0 or a_hi > len(eh):
            return 0.0, 0.0
        before = eh[lo:hi].mean()
        after = eh[a_lo:a_hi].max()
        return float(after), float(after / (before + 1e-4))

    ref_h = np.percentile(eh, 99)
    rows = []
    for r in np.arange(np.ceil(r0 * 2) / 2, r1 + 0.01, 0.5):
        c = bt(r) - ta - LAG                                            # the frame whose window holds the hit
        i0, i1 = int((c - TOL) * FPS), int((c + TOL) * FPS) + 1
        if i0 < 0 or i1 >= len(kick):                                   # before the start / after the end of the music: nothing to measure
            sl = sm = 0.0
        else:
            k = float(kick[i0:i1 + 1].max())
            sl = max(0.0, k - KICK_FLOOR) / KICK_SPAN
            sm = max(0.0, min(float(body[i0:i1 + 1].max()), float(crack[i0:i1 + 1].max())) - SNARE_KICK * k) / SNARE_SPAN
        ah, rh = hat(r)
        sh = (ah / ref_h) * max(0.0, (rh - 1.5) / 3.0)
        if not raw:                          # clipped strengths; raw: the hits that saturate at 1.00 stay comparable (draft_ref_timeline.py ranks its bumps by them)
            sl, sm = min(1.0, sl), min(1.0, sm)
            sh = min(1.0, ah / ref_h) * min(1.0, max(0.0, (rh - 1.5) / 3.0))
        rows.append([float(r), round(sl, 2), round(sm, 2), round(sh, 2)])
    return rows
