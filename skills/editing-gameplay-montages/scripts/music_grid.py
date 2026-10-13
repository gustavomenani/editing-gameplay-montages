"""Measure where the drum hits of a track really start, relative to a provisional beat grid, and print
the corrected first-beat time (BEAT0 for timeline.py) plus any tempo drift.

usage: python music_grid.py BPM BEAT0 [T0 T1] [file]     T0..T1: part of the track to measure (seconds)
       e.g. python music_grid.py 130 0.423 27 72

Method: 3 ms envelope of the analytic signal (a sub-bass / 808 wave has no zero-crossing dips in it, so a
long 808 tail cannot fake an attack); around every beat of the grid the log envelope's steepest 6 ms rise.
All beats vote for one consensus offset (a hat, a vinyl crackle or a chord change at a random place cannot
outvote the drums that keep coming back to the same spot), then each beat's own onset is the middle of its
rise within 10 ms of that offset. A tempo that is a little off (or drifting) is found first from the phase
of the beats in windows of about 12 s and corrected; the corrected tempo is printed with a BEAT0 that goes
with it. Run it a second time with the printed values: the median offset must come out within about 2 ms."""
import glob, os, subprocess, sys
import numpy as np
from ff import FF

SR = 44100
K = int(0.006 * SR)                                # the rise is measured over 6 ms


def usage(msg):
    raise SystemExit("%s\n\nusage: python music_grid.py BPM BEAT0 [T0 T1] [file]\n       e.g. python music_grid.py 130 0.423 27 72" % msg)


nums, files = [], []
for a in sys.argv[1:]:
    try:
        if os.path.isfile(a):
            raise ValueError
        nums.append(float(a))
    except ValueError:
        files.append(a)
if len(nums) not in (2, 4):
    usage("need BPM and BEAT0 (and optionally T0 T1), got %d numbers" % len(nums))
BPM, BEAT0 = nums[0], nums[1]
if not 30 <= BPM <= 300:
    usage("BPM %g is not a tempo (30..300)" % BPM)
if files:
    SRC = files[0]
else:
    hits = sorted(glob.glob("src/music.*"))
    if not hits:
        usage("no file given and no src/music.* here")
    SRC = hits[0]
PER = 60.0 / BPM
proc = subprocess.run([FF, "-v", "error", "-i", SRC, "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                      capture_output=True)
m = np.frombuffer(proc.stdout, np.float32)
if len(m) < 4 * SR:
    raise SystemExit("cannot read audio from %s (%s)" % (SRC, proc.stderr.decode(errors="replace").strip()[-200:] or
                                                         "%.1f s decoded" % (len(m) / SR)))
if len(nums) == 4:
    T0, T1 = nums[2], nums[3]
    if not 0 <= T0 < T1 <= len(m) / SR + 0.5:
        usage("T0..T1 = %g..%g does not fit the track (%.1f s)" % (T0, T1, len(m) / SR))
else:
    T0, T1 = 0.0, len(m) / SR


def analytic_power(x):
    """|analytic signal|^2 / 2 (= x^2 averaged over a cycle), in overlapping FFT blocks."""
    N, O = 1 << 20, 1 << 13
    hil = np.zeros(N)
    hil[0], hil[N // 2], hil[1:N // 2] = 1, 1, 2
    out = np.empty(len(x), np.float32)
    for s in range(0, len(x), N - 2 * O):
        a = s - O
        seg = np.zeros(N, np.float32)
        lo, hi = max(a, 0), min(a + N, len(x))
        seg[lo - a:hi - a] = x[lo:hi]
        p = np.abs(np.fft.ifft(np.fft.fft(seg) * hil)) ** 2 / 2
        e = min(s + N - 2 * O, len(x))
        out[s:e] = p[s - a:e - a]
    return out


# only the part that is measured (plus margin) goes through the envelope
SL0 = max(0, int((T0 - 1.0) * SR))
SL1 = min(len(m), int((T1 + 1.0) * SR) + K)
w = int(SR * 0.003)
env = np.sqrt(np.convolve(analytic_power(m[SL0:SL1]), np.ones(w) / w, mode="same"))
le = np.log(env + 0.1 * np.percentile(env, 95) + 1e-4)       # floor at -20 dB of the loud parts: a quiet hat's rise counts for less than a kick's
R = np.maximum(le[K:] - le[:-K], 0).astype(np.float32)       # R[i]: rise of the log envelope between samples i and i + 6 ms
tsl = SL0 / SR                                     # time of sample 0 of le


def curves(b0, per, step, half_s):
    """Rise curve around each grid position b0 + h * per (h in multiples of step) inside T0..T1.
    Returns grid indices, centres (s) and an array [position, offset] of the rise, offsets -half_s..+half_s."""
    n0, n1 = int(np.ceil((T0 - b0) / per / step)), int(np.floor((T1 - b0) / per / step))
    half = int(half_s * SR)
    hs, ts, rows = [], [], []
    for h in range(n0, n1 + 1):
        tg = b0 + h * step * per
        a = int(round((tg - tsl) * SR)) - half
        if a < 0 or a + 2 * half >= len(R):
            continue
        hs.append(h * step)
        ts.append(tg)
        rows.append(R[a:a + 2 * half])
    return np.array(hs), np.array(ts), (np.array(rows) if rows else np.zeros((0, 2 * half))), half


def smooth_circ(v, n):
    pad = np.concatenate([v[-n:], v, v[:n]])
    return np.convolve(pad, np.ones(n) / n, mode="same")[n:-n]


# ------------------------------------------------ 1. tempo and phase from the beats in windows (drift)
slope, phase0, drift_note = 0.0, 0.0, ""          # beat phase = phase0 + slope * (t - BEAT0)
hs, ts, C, half = curves(BEAT0, PER, 1.0, PER / 2)
if len(hs) >= 12:
    BIN = 44                                       # 1 ms
    nb = C.shape[1] // BIN
    P = np.sqrt(C[:, :nb * BIN].reshape(len(hs), nb, BIN).max(2))
    Wn = max(8, int(round(12.0 / PER)))
    ph, tc, conf = [], [], []
    for i in range(0, max(1, len(hs) - Wn + 1), max(1, Wn // 3)):
        S = smooth_circ(P[i:i + Wn].sum(0), 5)
        conf.append(S.max() / (S.mean() + 1e-9))
        ph.append((int(np.argmax(S)) * BIN + BIN / 2 - half) / SR + K / 2 / SR)      # offset of the onset (middle of the rise)
        tc.append(ts[i:i + Wn].mean())
    ph, tc, conf = np.array(ph), np.array(tc), np.array(conf)
    good = np.where(conf >= max(2.0, 0.6 * np.median(conf)))[0]
    if len(good) >= 3:
        seed = good[int(np.argmax(conf[good]))]
        acc = {seed: ph[seed]}                     # follow the phase outward from the clearest window; a window that jumps by
        for order in (good[good > seed], good[good < seed][::-1]):          # more than 0.3 beat belongs to another part of the groove
            last = ph[seed]
            for j in order:
                d = ph[j] - last
                d -= PER * round(d / PER)
                if abs(d) < 0.3 * PER:
                    last = last + d
                    acc[j] = last
        good = np.array(sorted(acc))
        u, tg_ = np.array([acc[j] for j in good]), tc[good]
        keep = np.ones(len(u), bool)
        for _ in range(3):                         # straight line through the windows, outliers out
            if keep.sum() < 3:
                break
            sl, ic = np.polyfit(tg_[keep] - BEAT0, u[keep], 1)
            res = u - (ic + sl * (tg_ - BEAT0))
            keep = np.abs(res) < max(0.015, 3 * 1.48 * np.median(np.abs(res[keep])))
        if keep.sum() >= 3:
            if tg_[keep].max() - tg_[keep].min() >= 20:
                phase0, slope = float(ic), float(sl)
                spread = float(np.std(res[keep]))
                if spread > 0.008:
                    drift_note = ("the beat phase wanders by %.0f ms around a straight line over this stretch: the tempo is not steady "
                                  "(live playing or a tempo change), so the grid is only good near the part you measured; run again with "
                                  "T0 T1 on the part you will use" % (spread * 1000))
            else:
                phase0 = float(np.median(u[keep]))
if abs(slope) * (T1 - T0) > 0.006:                 # more than 6 ms across the part: correct the tempo before measuring hits
    PER_run = PER * (1 + slope)
    B0_run = BEAT0 + phase0                        # beat phase at BEAT0 from the line
else:
    PER_run, B0_run, slope = PER, BEAT0 + (phase0 + slope * ((T0 + T1) / 2 - BEAT0) if slope else phase0), 0.0


def measure(b0, per, step):
    hs, ts, C, half = curves(b0, per, step, 0.2 * per)
    if len(hs) == 0:
        return np.zeros((0, 4))
    Q = np.sqrt(C)
    sm = int(0.004 * SR)
    # the consensus offset (rise start, samples) of each stretch of about 12 s: it follows a tempo that is not quite steady
    Wn = max(8, int(round(12.0 / (per * step))))
    ct, cd, cc = [], [], []
    for i in range(0, max(1, len(hs) - Wn + 1), max(1, Wn // 2)):
        S = smooth_circ(Q[i:i + Wn].sum(0), sm)
        ct.append(ts[i:i + Wn].mean())
        cd.append(int(np.argmax(S)) - half)
        cc.append(S.max() / (S.mean() + 1e-9))
    ct, cd, cc = np.array(ct), np.array(cd, float), np.array(cc)
    S = smooth_circ(Q.sum(0), sm)
    d_all = int(np.argmax(S)) - half
    ok = cc >= 0.6 * np.median(cc)
    d0 = np.interp(ts, ct[ok], cd[ok]) if ok.sum() >= 1 else np.full(len(ts), float(d_all))
    if ok.sum() >= 1 and np.abs(d0 - d_all).max() > 0.1 * per * SR:     # stretches that disagree with the whole by a tenth of a beat: no tracking
        d0 = np.full(len(ts), float(d_all))
    rf = int(0.010 * SR)
    rows = []
    for idx in range(len(hs)):
        lo, hi = max(0, half + int(d0[idx]) - rf), min(C.shape[1], half + int(d0[idx]) + rf)
        i = lo + int(np.argmax(C[idx][lo:hi]))
        a = int(round((ts[idx] - tsl) * SR)) - half
        seg = le[a + i:a + i + K]
        j = int(np.argmax(seg >= (seg[0] + seg[-1]) / 2))
        rows.append((hs[idx], tsl + (a + i + j) / SR, (i - half + j) / SR * 1000, float(C[idx][i])))
    return np.array(rows)


def clear(rows):
    return rows[rows[:, 3] >= max(0.4, np.percentile(rows[:, 3], 60))] if len(rows) else rows


# ------------------------------------------------ 2. every beat's own onset against the (corrected) grid
rows = measure(B0_run, PER_run, 1.0)
use, unit = clear(rows), "whole beats"
if len(use) < 12:                                  # sparse kicks: look at the half beats as well
    rows2 = measure(B0_run, PER_run, 0.5)
    if len(clear(rows2)) > len(use):
        rows, use, unit = rows2, clear(rows2), "half beats"
if len(use) < 6:
    raise SystemExit("only %d clear hits at %g bpm inside %.1f..%.1f s: the grid does not fit this part of the track, or it has no "
                     "drums there (BPM a half or double of the real tempo? run music_tempo.py)" % (len(use), BPM, T0, T1))
med = float(np.median(use[:, 2]))
core = use[np.abs(use[:, 2] - med) < max(15, 3 * (np.percentile(use[:, 2], 90) - np.percentile(use[:, 2], 10)))]
med = float(np.median(core[:, 2]))
print("%d beat positions (%s), %d clear hits, %d kept (within 15 ms of the others, or following a slow drift)" % (len(rows), unit, len(use), len(core)))
print("offset of the real onsets from the grid: median %+.1f ms, spread (std) %.1f ms" % (med, core[:, 2].std()))
judged = len(core) >= 20 and core[:, 1].max() - core[:, 1].min() >= 20
line = np.polyfit(core[:, 1], core[:, 2], 1) if judged else None               # offset (ms) against time (s)
resid = float(line[0]) if judged else 0.0
rstd = float(np.std(core[:, 2] - np.polyval(line, core[:, 1]))) if judged else float(core[:, 2].std())
sigma = rstd / (core[:, 1].std() * np.sqrt(len(core)) + 1e-9) * 60 if judged else 0.0     # ms per minute the slope is uncertain by
total = (PER_run / PER - 1) + resid / 1000        # relative change of the beat period against the BPM that was given
corrected = abs(total) * 60000 >= max(2.0, 3 * sigma)       # 2 ms per minute = 6 ms over a 3 minute track
if rstd > 8:
    print("warning: the hits stay %.0f ms (std) away from one straight grid: the tempo is not steady (live drummer, tempo change), "
          "so measure the part you will use with T0 T1; or the BPM is a half / double of the real tempo (%.3f or %.3f)" % (rstd, BPM / 2, BPM * 2))
if drift_note:
    print("warning:", drift_note)
if judged:
    print("drift: %+.2f ms per minute%s%s" % (total * 60000, "  -> tempo is really %.3f bpm" % (BPM / (1 + total)) if corrected else "",
                                               "" if core[:, 1].max() - core[:, 1].min() >= 60 else "  (from %.0f s only: rough)" % (core[:, 1].max() - core[:, 1].min())))
else:
    print("drift: not judged (needs 20 hits over 20 s; run without T0 T1 to check the tempo on the whole track)")
# the beat nearest the middle of the hits, on the corrected grid: where its real onset is
tm = float(np.median(core[:, 1]))
n_m = round((tm - B0_run) / PER_run)
g_m = B0_run + n_m * PER_run
o_m = g_m + (np.polyval(line, g_m) if corrected and judged else med) / 1000
n_user = n_m                                      # the same beat counted from the beat 0 of the grid that was given
if corrected:
    BPM_out = round(BPM / (1 + total), 3)
    B0_out = o_m - n_user * 60.0 / BPM_out
else:
    BPM_out = BPM
    B0_out = o_m - n_user * PER
PER_out = 60.0 / BPM_out
# Is the first beat really HERE? A groove that is syncopated (trap kicks a sixteenth before the beat, offbeat 808s) fits a grid
# shifted by a sixteenth or an eighth almost as well: compare the loud hits that land on the grid with those on shifted grids.
LR = np.maximum(env[K:] - env[:-K], 0)
beats_n = np.arange(int(np.ceil((T0 - B0_run) / PER_run)), int(np.floor((T1 - B0_run) / PER_run)) + 1)


def loud_on(shift):
    t = B0_run + beats_n * PER_run + med / 1000 + shift * PER_run
    a = np.round((t - tsl) * SR).astype(int)
    ok = (a >= int(0.01 * SR)) & (a + int(0.01 * SR) < len(LR))
    return float(sum(LR[i - int(0.008 * SR):i + int(0.008 * SR)].max() for i in a[ok]))


base = loud_on(0.0)
alt = {s: loud_on(s) / (base + 1e-9) for s in (-0.375, -0.25, -0.125, 0.125, 0.25, 0.375, 0.5)}
alt = {s: r for s, r in alt.items() if r >= 0.8}
B0_given_by_fit, picked = B0_out, 0.0
if alt and T0 < 1.0:
    # the first loud hit of the track is most often the first beat of a bar: if it sits on a shifted grid and not on this one, take that one
    big = np.where(LR >= 0.3 * np.percentile(LR, 99.8))[0]
    if len(big):
        f = big[0]
        t_first = tsl + (f + int(np.argmax(LR[f:f + int(0.012 * SR)])) + K / 2) / SR
        dist = lambda s: abs((t_first - B0_out - s * PER_out + PER_out / 2) % PER_out - PER_out / 2)
        best = min([0.0] + list(alt), key=dist)
        if best != 0.0 and dist(best) < 0.015 and dist(0.0) > 0.03:
            picked = best
            B0_out += best * PER_out
if corrected:
    print("=> BPM = %.3f   BEAT0 = %.4f   (you gave %.3f / %.4f: use BOTH new values, then run again to confirm the median is "
          "within about 2 ms)" % (BPM_out, B0_out, BPM, BEAT0))
else:
    print("=> BEAT0 = %.4f   (was %.4f; it goes with BPM %g as given: a different BPM needs a new BEAT0)" % (B0_out, BEAT0, BPM))
if alt:
    G = {0.0: 1.0, **alt}                          # shift (beats) against the grid as measured -> how strong the loud hits are on it
    others = [s for s in G if s != picked]
    print("warning: the loud hits also sit on a grid shifted by %s of a beat (%s as strong as on the grid printed above): syncopated groove, "
          "or the first beat is somewhere else.%s If the first kick of a bar is not where music_spec.py shows it on beat 0 / 4 / 8, use "
          "BEAT0 %s instead" % (
              ", ".join("%+.2f" % (s - picked) for s in others), ", ".join("%.0f%%" % (100 * G[s] / G[picked]) for s in others),
              (" The first loud hit of the track (%.3f s) sits on the shifted grid and not on the measured one, so the shifted one is printed." %
               t_first) if picked else "",
              " or ".join("%.4f" % (B0_given_by_fit + s * PER_out) for s in others)))
print("strongest hits: track beat, time, offset ms, rise")
for r in sorted(core, key=lambda q: -q[3])[:24]:
    print("   beat %7.1f  %7.3fs  %+6.1f  %.2f" % tuple(r))
