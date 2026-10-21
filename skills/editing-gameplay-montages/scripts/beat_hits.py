"""Kick / snare / hat strength on every half beat of a stretch of the song AND the time of every drum attack: the measure of
music_pulses.py as a function, so that draft_timeline.py and draft_ref_timeline.py put kills and cuts on exactly the hits that
music_pulses.py will then report.

rows = measure(m, bpm, beat0, m0, r0, r1) -> [[beat, low, mid, high], ...] for the half beats r0 .. r1 (timeline beats),
each strength 0..1 (the old measure: strengths only, an onset within +-TOL of the half beat counts; kept for its callers):
  low  = kick / 808 / bass hit ARRIVING: the log-spectral onset (flux) of 30..140 Hz, not its energy: on a band mix the bass
         guitar keeps that band loud on nearly every half beat, an energy ratio calls every one a kick, the onset does not
  mid  = snare / clap ARRIVING: the body (160..1500 Hz) and the crack (1.5..8 kHz) must both have an onset at that instant
         (the smaller of the two, less a third of the kick's onset). A guitar chord or a vocal has the body without the crack, a
         hat the crack without the body, so neither counts as a snare; a band's snare, buried in guitars, still does
  high = anything bright arriving (above 2.5 kHz: snares, claps and every hat), the energy of that band against the 40 ms before
`m` is the mono 44.1 kHz song from decode(). The window the strengths are normalised over is the video plus 3 s each
side, like music_pulses.py, so the numbers are the same ones it prints for a timeline.py with the same music block.
raw=True returns the strengths unclipped (a loud, sharp hit is above 1: the clipped rows saturate on every kick of a dense groove).

rows, att = measure_t(m, bpm, beat0, m0, r0, r1, raw=False, sub=2) -- the SYNC 2 measure: the same rows on the 1/sub beat lattice
(sub 2: half beats, 4: sixteenths) plus att = {lattice beat: (t_attack in TRACK seconds, band)} for every row with a strength: an
event is put on that time, timeline beat = (t - BEAT0) / PER - M0 (timeline.py's hit(t)), never on the lattice beat. A strength exists
only where a real attack lies within `tol` of the lattice point, so a hit 40 ms from the beat can no longer pass as one.
attacks(x, t0) -> [(t, band, rise)]: every attack of a stretch, no grid. strong_hits(m, t0, t1) -> [(t, kind, strength)]: the kicks /
snares (hats) of a stretch, no grid (music_grid.py reads the grid's fit from these).

THE ATTACK, ONE definition for the whole skill (music_grid.py, music_hits.py, music_pulses.py, music_spec.py, the drafters, the gate):
per band (low 40..150 Hz, mid 200..2000, high 2.5..12 kHz) the analytic envelope smoothed with a 1.5 ms Hann window; the steepest
rise of ln(env) over 6 ms marks the hit; its time is where the LINEAR envelope is half way from the foot of that rise to its top
(12 ms later), minus the class bias BIAS_MS measured on synthetic songs with sample-exact truth (below). Measured: kick -0.3 / +0.6 /
+1.5 ms mean for 2 / 3 / 5 ms attack ramps (max |error| 2.0 / 2.4 / 3.3; an instant-onset kick -2.0), snare +0.1 to +0.2 (max 0.3), hat
+0.3 (max 0.4), a click-less 808 sine +2.8 (std 3.2, max 11): the documented limits of a time that a sound without a click cannot give
more sharply. Real songs have no truth; the numbers above are the synthetic ones.
Strength still never validates a time: it is the onset flux of 3 bands, only a ranking."""
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


# ================================================================ the attack: ONE definition of "the time of a hit" for the whole skill
BANDS = {"low": (40.0, 150.0), "mid": (200.0, 2000.0), "high": (2500.0, 12000.0)}   # Hz; zero-phase 4th-order band-pass of each
SMOOTH_MS = 1.5                     # Hann smoothing of the analytic envelope
RISE_MS = 3.0                       # D(t) = ln(env(t + 3 ms)) - ln(env(t - 3 ms)): the steepest rise of the log envelope marks the hit
FOOT_FRAC = 0.25                    # the foot of the rise: the last sample before the steepest point where D is still above this share of its peak
AFTER_MS = 12.0                     # the top of the rise: the highest envelope within 12 ms after the steepest point
HALF = 0.5                          # the attack time is where the envelope has climbed this share of the way from the foot to the top
FLOOR_REL = 0.03                    # ln(env + 3 % of the band's 95th percentile): a rise out of near silence is not a rise out of nothing
MIN_RISE = 0.3                      # ln units over 6 ms: a flatter rise is not an attack (steady tones, vinyl crackle)
REL_RISE = 0.35                     # an attack is at least this share of the band's 90th percentile of rises
MIN_GAP = 0.03                      # s between two attacks of one band (a 16th hat at 250 bpm is 60 ms)
# The attack time = the moment the LINEAR envelope is half way between its value at the foot and its top (the half-height of
# the rise), minus BIAS_MS[band]: what that definition reads late against the TRUE START of a synthetic sound. Measured on
# numpy-made songs with sample-exact truth (the wave-2 work's bias_test.py / bias_dp.py): hats +0.0..+0.7 ms (std <= 0.2),
# snares +0.0..+0.9 (std 0.0), kicks -0.7..+4.8 depending on how sharp the onset is (a sweep with an instant start: -0.6..+0.6;
# 2 / 3 / 5 ms linear attack ramps: +1.2 / +2.1 / +3.1, std 1.1 from the bass under it), a click-less 808 sine +5.9 (std 3.2, max
# 12.9). One bias per band, the middle of what was measured: after the subtraction hats and snares read within +-0.5 ms of the true
# start, kicks within +-2.5 ms (a very soft 5 ms-ramp kick up to +3.3 late, an instant one up to -2.2 early), an 808 sine is
# BIAS_808_MS late and scatters +-3 ms (a sound without a click has no sharper start to show): documented, not hidden.
BIAS_MS = {"low": 1.5, "mid": -0.4, "high": 0.3}       # "mid" reads -0.3..-0.6 ms EARLY on snares and kicks, hence the minus sign
BIAS_808_MS = 4.4                   # what is left of a click-less sine (808) in the low band after BIAS_MS["low"] (informative; std 3.2)
TOL_T = 0.05                        # s: how far from a lattice point an attack still belongs to it (never more than half a lattice step)
HIT_LOW, HIT_MID, HIT_HIGH = 0.5, 0.6, 0.65     # strengths from which the drafters take a hit as a kick / snare / hat: they rank the band of a row
DEFINITION = ("half-height of the linear envelope (1.5 ms Hann-smoothed analytic signal of the band) across the steepest 6 ms rise of "
              "ln(env), foot = 25 % of the rise rate, top = 12 ms later; minus the class bias")


def _gains(n):
    """one-sided gains of the three bands for an FFT of n points (zero phase), times the analytic-signal weights"""
    f = np.arange(n // 2 + 1) * (SR / n)
    out = {}
    for nm, (lo, hi) in BANDS.items():
        g = np.ones_like(f)
        g *= (f / lo) ** 4 / np.sqrt(1 + (f / lo) ** 8)
        g /= np.sqrt(1 + (f / hi) ** 8)
        g[1:n // 2] *= 2.0                                   # analytic signal: positive frequencies doubled, negative ones dropped
        out[nm] = g
    return out


_BLOCK, _OVER = 1 << 20, 1 << 14


def _envelopes(x):
    """yield (s, e): for each stretch s .. s + len of x, the smoothed envelope of each band, with the overlap on both sides
    (e[nm][i] belongs to sample s - _OVER + i); blocks are processed one at a time so a whole track needs no whole-track arrays"""
    n = len(x)
    k = int(round(SMOOTH_MS / 1000 * SR))
    win = np.hanning(2 * k + 3)[1:-1]
    win /= win.sum()
    g = _gains(_BLOCK)
    step = _BLOCK - 2 * _OVER
    for s in range(0, max(n, 1), step):
        a = s - _OVER
        seg = np.zeros(_BLOCK)
        lo, hi = max(a, 0), min(a + _BLOCK, n)
        seg[lo - a:hi - a] = x[lo:hi]
        X = np.fft.rfft(seg)
        e = {}
        for nm in BANDS:
            Y = np.zeros(_BLOCK, complex)
            Y[:_BLOCK // 2 + 1] = X * g[nm]
            env = np.abs(np.fft.ifft(Y))
            e[nm] = np.convolve(env, win, mode="same")
        yield s, a, min(step, n - s), e


def _floors(blocks):
    """per band: 3 % of the 95th percentile of the envelope over the whole of x (the median of the blocks' own 95th percentiles)"""
    p = {nm: [] for nm in BANDS}
    for s, a, nv, e in blocks:
        for nm in BANDS:
            p[nm].append(np.percentile(e[nm][_OVER:_OVER + max(nv, 1)], 95))
    return {nm: FLOOR_REL * float(np.median(v)) + 1e-7 for nm, v in p.items()}


def attacks(x, t0=0.0, bias=True, rel=REL_RISE):
    """Every attack of the three bands of x (mono float 44.1 kHz; t0 = the track time of x[0]) -> list of (t, band, rise) sorted
    by t: t in TRACK seconds (the module's one definition above, class bias subtracted when bias=True), band "low" / "mid" /
    "high", rise = the steepest 6 ms rise of ln(env) (a strength: larger = sharper). Needs no grid. An attack is a rise of at
    least MIN_RISE and REL_RISE of the band's 90th percentile of rises, at least MIN_GAP from the next of its band."""
    from scipy.ndimage import maximum_filter1d
    x = np.asarray(x, np.float64)
    blocks = [(s, a, nv, {nm: v.astype(np.float32) for nm, v in e.items()}) for s, a, nv, e in _envelopes(x)]
    fl = _floors(blocks)
    d = int(round(RISE_MS / 1000 * SR))
    lim, aft = int(0.03 * SR), int(round(AFTER_MS / 1000 * SR))
    cand = {nm: [] for nm in BANDS}
    for s, a, nv, e in blocks:
        for nm in BANDS:
            env = e[nm].astype(np.float64)
            L = np.log(env + fl[nm])
            D = np.zeros_like(L)
            D[d:-d] = L[2 * d:] - L[:-2 * d]
            lo_i, hi_i = _OVER, _OVER + nv                  # the stretch this block owns (the rest is margin for the foot / the top)
            dist = int(MIN_GAP * SR)
            pk = np.nonzero((D == maximum_filter1d(D, size=2 * dist + 1)) & (D >= MIN_RISE))[0]
            pk = pk[np.concatenate([[True], np.diff(pk) >= dist])] if len(pk) else pk      # a plateau counts once
            for i in pk[(pk >= lo_i) & (pk < hi_i)]:
                if i - lim < 0 or i + aft + 1 >= len(D):
                    continue
                back = D[i - lim:i + 1][::-1]
                below = np.nonzero(back <= FOOT_FRAC * D[i])[0]
                j = i - (int(below[0]) if len(below) else lim)
                top = float(env[i:i + aft + 1].max())
                half = env[j] + HALF * (top - env[j])
                k = j + int(np.argmax(env[j:i + aft + 1] >= half))
                cand[nm].append((a + k, float(D[i])))                # a + k: the sample of the whole of x (block-local index k, block start a)
    out = []
    for nm, rows in cand.items():
        if not rows:
            continue
        h = np.array([r[1] for r in rows])
        thr = max(MIN_RISE, rel * float(np.percentile(h, 90)))
        b = BIAS_MS[nm] / 1000 if bias else 0.0
        for gk, rise in rows:
            if rise >= thr:
                out.append((t0 + gk / SR - b, nm, rise))
    out.sort()
    return out


_LAST = [None, None, None]             # measure_t's cache: [window key, the song array it was made from, its attacks]


class Att(dict):
    """measure_t's second result: {lattice beat: (t_attack_seconds_in_track, band)}. `bands[beat]` = {band: t} for every band that
    carries a strength on that row (a bass cut wants the "low" time of a row whose strongest band is a snare); `unassigned` =
    attacks (t, band) that lie farther than the tolerance from every lattice point (swung / syncopated / flams); `all` = every
    attack (t, band, rise) of the measured window, strong or weak, assigned or not (what a placed event is checked against)."""
    bands = None
    unassigned = None
    all = None


class _Win:
    """The analysis of one stretch of the song (samples a0 .. a1): its attacks and the strength curves every consumer reads, once."""

    def __init__(self, m, a0, a1):
        x = m[a0:a1]
        self.ta = a0 / SR
        X = np.fft.rfft(x)
        f = np.fft.rfftfreq(len(x), 1 / SR)
        g = (f / 2500.0) ** 4
        w = int(SR * 4 / 1000)
        self.eh = np.sqrt(np.convolve(np.fft.irfft(X * (g / np.sqrt(1 + g * g)), n=len(x)) ** 2, np.ones(w) / w, mode="same"))
        self.ref_h = np.percentile(self.eh, 99)
        self.kick, self.body, self.crack = onsets(x)
        self.ev = attacks(x, a0 / SR)

    def flux(self, curve, t, w=0.02):
        c = (t - self.ta) - LAG
        i0, i1 = int((c - w) * FPS), int((c + w) * FPS) + 1
        return float(curve[i0:i1 + 1].max()) if i0 >= 0 and i1 < len(curve) else 0.0

    def s_kick(self, t):
        """unclipped kick strength of a "low" attack at t"""
        return max(0.0, self.flux(self.kick, t) - KICK_FLOOR) / KICK_SPAN

    def s_snare(self, t):
        """unclipped snare / clap strength of a "high" / "mid" attack at t: body and crack both arriving, less a share of the kick's onset"""
        return max(0.0, min(self.flux(self.body, t), self.flux(self.crack, t)) - SNARE_KICK * self.flux(self.kick, t)) / SNARE_SPAN

    def hat(self, t, pre_ms=40, post_ms=18):
        """(energy after, its ratio to the 40 ms before) of the bright band around a "high" attack at t"""
        c = int(round((t - self.ta) * SR))
        lo, hi = c - int(pre_ms / 1000 * SR), c - int(0.006 * SR)
        a_lo, a_hi = c + int(0.004 * SR), c + int(post_ms / 1000 * SR)
        if lo < 0 or a_hi > len(self.eh):
            return 0.0, 0.0
        return float(self.eh[a_lo:a_hi].max()), float(self.eh[a_lo:a_hi].max() / (self.eh[lo:hi].mean() + 1e-4))

    def s_hat(self, t):
        """unclipped hat strength of a "high" attack at t; (strength, energy ratio part, energy part) for the clipped variant"""
        ah, rh = self.hat(t)
        return (ah / self.ref_h) * max(0.0, (rh - 1.5) / 3.0), ah, rh


def _win(m, a0, a1):
    key = (id(m), len(m), a0, a1)
    if _LAST[0] != key or _LAST[1] is not m:          # the analysis of a window is the expensive part: a second call on the same window (another sub / tol) reuses it
        _LAST[:] = [key, m, _Win(m, a0, a1)]
    return _LAST[2]


def measure_t(m, bpm, beat0, m0, r0, r1, raw=False, sub=2, tol=TOL_T):
    """measure() on the 1/sub beat lattice (sub = 2: half beats, 4: sixteenths) with the TIME of every hit.
    -> (rows, att): rows = [[beat, low, mid, high], ...] as measure() (strengths 0..1, or unclipped with raw=True) for the
    lattice beats r0 .. r1 (timeline beats); att = {beat: (t, band)} (an Att) for every row with a strength: t = the attack time in
    TRACK seconds (module docstring: one definition, class bias subtracted; accuracy on drums <= 2.5 ms) and band = "low" / "mid" /
    "high": the first of kick (strength 0.5), snare (0.6), hat (0.65) that the row reaches, as the drafters ask (a kick under a loud
    hat is a kick), else the class closest to its threshold.
    Put an event on this time: timeline beat = (t - beat0) / PER - m0 (timeline.py's hit(t)), never on the lattice beat.
    A strength exists only where an attack of the band lies within `tol` seconds of the lattice point (never more than half
    a lattice step, and each attack belongs to its nearest lattice point only): a hit farther away has no row and no att
    entry, so a hit that is not near the beat can no longer pass as one (measure() accepts any onset within +-50 ms of the point).
    low = a "low"-band attack and the kick's onset (as measure()); mid = a "mid" or "high" attack at which body and crack
    both arrive (the time is the mid attack's, the snare's body, else the high attack's, the crack: a hat just ahead of a snare hides
    the crack's attack, never the body's); high = a "high" attack and its energy against
    the 40 ms before it. The strengths are evaluated AT the attack, not at the lattice point."""
    per = 60.0 / bpm
    bt = lambda r: beat0 + (m0 + r) * per
    dur = len(m) / SR
    a0, a1 = int(max(0.0, bt(r0) - 3.0) * SR), min(len(m), int((bt(r1) + 3.0) * SR))
    if a1 - a0 < SR:
        raise SystemExit("beats %g .. %g (%.1f .. %.1f s) lie outside the music (%.1f s long)" % (r0, r1, bt(r0), bt(r1), dur))
    W = _win(m, a0, a1)
    ev = W.ev
    step = per / sub
    tol = min(tol, step / 2)
    u_lo, u_hi = int(np.ceil(r0 * sub - 1e-9)), int(np.floor(r1 * sub + 1e-9))
    owner = {b: {} for b in BANDS}                                  # band -> {lattice index: (t, rise)}: the strongest attack within tol of each point
    free = []
    for t, b, rise in ev:
        u = int(round((t - beat0) / step - m0 * sub))
        if abs(t - (beat0 + (m0 * sub + u) * step)) > tol:
            free.append((t, b))
            continue
        if u not in owner[b] or rise > owner[b][u][1]:
            owner[b][u] = (t, rise)
    rows, att = [], Att()
    att.bands, att.unassigned, att.all = {}, free, ev
    for u in range(u_lo, u_hi + 1):
        r = u / sub
        sl = sm = sh = 0.0
        tt = {}
        if u in owner["low"]:
            tl_ = owner["low"][u][0]
            sl = W.s_kick(tl_)
            if sl > 0:
                tt["low"] = tl_
        mh, hh = owner["mid"].get(u), owner["high"].get(u)
        tm_ = mh[0] if mh is not None else (hh[0] if hh is not None else None)     # the snare's own body attack when there is one (a hat in front of it can shadow its crack)
        if tm_ is not None:
            sm = W.s_snare(tm_)
            if sm > 0:
                tt["mid"] = tm_
        ah = rh = 0.0
        if u in owner["high"]:
            sh, ah, rh = W.s_hat(owner["high"][u][0])
            if sh > 0:
                tt["high"] = owner["high"][u][0]
        if not raw:
            sl, sm = min(1.0, sl), min(1.0, sm)
            sh = min(1.0, ah / W.ref_h) * min(1.0, max(0.0, (rh - 1.5) / 3.0))
        rows.append([float(r), round(sl, 2), round(sm, 2), round(sh, 2)])
        st = {"low": rows[-1][1], "mid": rows[-1][2], "high": rows[-1][3]}
        tt = {k: v for k, v in tt.items() if st[k] > 0}
        if tt:
            # the class of the row: the first of kick, snare, hat whose strength reaches what a drafter takes as that hit (a kick
            # under a loud hat is a kick, whose time a bass cut needs); none reaches it: the one closest to its threshold
            thr = {"low": HIT_LOW, "mid": HIT_MID, "high": HIT_HIGH}
            ok = [k for k in ("low", "mid", "high") if k in tt and st[k] >= thr[k]]
            band = ok[0] if ok else max(tt, key=lambda k: min(1.0, st[k]) / thr[k])
            att[float(r)] = (float(tt[band]), band)
            att.bands[float(r)] = {k: float(v) for k, v in tt.items()}
    return rows, att


def strong_hits(m, t0, t1, hats=False):
    """The strong hits of the song between track seconds t0 and t1, WITHOUT any grid: -> [(t, kind, strength)] sorted by time, t = the
    attack in track seconds (module docstring), kind "kick" (a "low" attack whose kick strength is >= 0.5), "snare" (a "high" / "mid"
    attack at which body and crack arrive, strength >= 0.6) and with hats=True also "hat" (a "high" attack, >= 0.65); strength =
    that class's unclipped strength (beat_hits' scale). A snare's time is its "mid"-band (body) attack when it has one, else its "high" one (crack).
    The window the strengths are normalised over is t0 - 3 s .. t1 + 3 s, as measure_t's for the same stretch."""
    a0, a1 = int(max(0.0, t0 - 3.0) * SR), min(len(m), int((t1 + 3.0) * SR))
    if a1 - a0 < SR:
        raise SystemExit("%.1f .. %.1f s lie outside the music (%.1f s long)" % (t0, t1, len(m) / SR))
    W = _win(m, a0, a1)
    out = []
    mid_t = np.array([e[0] for e in W.ev if e[1] == "mid"])
    for t, b, rise in W.ev:
        if not t0 <= t <= t1:
            continue
        if b == "low":
            s = W.s_kick(t)
            if s >= HIT_LOW:
                out.append((t, "kick", s))
        elif b == "mid":
            # the time of a snare is its body's attack (mid band: it shows at the snare itself, a kick's click too); its crack (high band) is only
            # the time when no mid attack exists: a hat a few ms ahead of the snare hides the crack's attack (attacks of one band are 30 ms apart
            # at least) and a jittering hat would then be taken for the snare (measured: up to -20 ms)
            s = W.s_snare(t)
            if s >= HIT_MID:
                out.append((t, "snare", s))
        else:
            if len(mid_t) and np.abs(mid_t - t).min() <= 0.025:
                continue                                    # belongs to the snare candidate of that mid attack
            s = W.s_snare(t)
            if s >= HIT_MID:
                out.append((t, "snare", s))
            elif hats and W.s_hat(t)[0] >= HIT_HIGH:
                out.append((t, "hat", W.s_hat(t)[0]))
    out.sort()
    return out


def attacks_between(m, t0, t1):
    """Every attack (t, band, rise) of the song between track seconds t0 and t1 (analysed with 3 s of margin each side, like strong_hits
    and measure_t for the same stretch; the window is analysed once)."""
    a0, a1 = int(max(0.0, t0 - 3.0) * SR), min(len(m), int((t1 + 3.0) * SR))
    if a1 - a0 < SR:
        raise SystemExit("%.1f .. %.1f s lie outside the music (%.1f s long)" % (t0, t1, len(m) / SR))
    return [e for e in _win(m, a0, a1).ev if t0 <= e[0] <= t1]


def strong_attacks(ev, frac=0.6):
    """The attacks of `ev` ([(t, band, rise)]) that are sharp: rise >= frac x the 90th percentile of their own band's rises (what the
    tempo cross-check of music_grid.py and the marks of music_spec.py / mix_spec.py use; a weak ripple of a steady bass is not a hit)."""
    out = []
    for band in BANDS:
        rr = np.array([e[2] for e in ev if e[1] == band])
        if len(rr):
            thr = frac * np.percentile(rr, 90)
            out += [e for e in ev if e[1] == band and e[2] >= thr]
    out.sort()
    return out
