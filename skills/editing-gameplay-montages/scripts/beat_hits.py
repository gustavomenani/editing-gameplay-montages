"""Kick / snare / hat strength on every half beat of a stretch of the song: the measure of music_pulses.py as a
function, so that draft_timeline.py puts kills and cuts on exactly the hits that music_pulses.py will then report.

rows = measure(m, bpm, beat0, m0, r0, r1) -> [[beat, low, mid, high], ...] for the half beats r0 .. r1 (timeline beats),
each strength 0..1 (low: kick / bass arriving below 140 Hz; mid: snare / clap 900..3500 Hz; high: anything bright).
`m` is the mono 44.1 kHz song from decode(). The window the strengths are normalised over is the video plus 3 s each
side, like music_pulses.py, so the numbers are the same ones it prints for a timeline.py with the same music block.
raw=True returns the strengths unclipped (a loud, sharp hit is above 1: the clipped rows saturate on every kick of a dense groove)."""
import subprocess
import numpy as np
from ff import FF

SR = 44100


def decode(path):
    """The song as mono float32 at 44.1 kHz."""
    raw = subprocess.run([FF, "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    m = np.frombuffer(raw, np.float32)
    if len(m) < SR:
        raise SystemExit("cannot read audio from %s" % path)
    return m


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
    low = np.fft.irfft(X / np.sqrt(1 + (f / 140.0) ** 8), n=len(x))
    g = (f / 2500.0) ** 4
    high = np.fft.irfft(X * (g / np.sqrt(1 + g * g)), n=len(x))
    g = (f / 900.0) ** 4
    mid = np.fft.irfft(X * (g / np.sqrt(1 + g * g)) / np.sqrt(1 + (f / 3500.0) ** 8), n=len(x))

    def env(y, ms):
        w = int(SR * ms / 1000)
        return np.sqrt(np.convolve(y * y, np.ones(w) / w, mode="same"))

    el, em, eh = env(low, 12), env(mid, 5), env(high, 4)

    def hit(e, r, pre_ms, post_ms):
        c = int(round((bt(r) - ta) * SR))
        lo, hi = c - int(pre_ms / 1000 * SR), c - int(0.006 * SR)
        a_lo, a_hi = c + int(0.004 * SR), c + int(post_ms / 1000 * SR)
        if lo < 0 or a_hi > len(e):
            return 0.0, 0.0
        before = e[lo:hi].mean()
        after = e[a_lo:a_hi].max()
        return float(after), float(after / (before + 1e-4))

    rows = []
    ref_l, ref_m, ref_h = np.percentile(el, 99), np.percentile(em, 99), np.percentile(eh, 99)
    for r in np.arange(np.ceil(r0 * 2) / 2, r1 + 0.01, 0.5):
        al, rl = hit(el, r, 60, 45)
        am, rm = hit(em, r, 40, 25)
        ah, rh = hit(eh, r, 40, 18)
        if raw:                              # unclipped strengths: the hits that saturate at 1.00 stay comparable (draft_ref_timeline.py ranks its bumps by them)
            sl = (al / ref_l) * max(0.0, (rl - 1.3) / 2.0)
            sm = (am / ref_m) * max(0.0, (rm - 1.5) / 3.0)
            sh = (ah / ref_h) * max(0.0, (rh - 1.5) / 3.0)
        else:
            sl = min(1.0, al / ref_l) * min(1.0, max(0.0, (rl - 1.3) / 2.0))
            sm = min(1.0, am / ref_m) * min(1.0, max(0.0, (rm - 1.5) / 3.0))
            sh = min(1.0, ah / ref_h) * min(1.0, max(0.0, (rh - 1.5) / 3.0))
        rows.append([float(r), round(sl, 2), round(sm, 2), round(sh, 2)])
    return rows
