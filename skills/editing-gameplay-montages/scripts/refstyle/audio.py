"""Sound for the reference-style edit: the track, one gunshot per kill at natural pitch with its onset ON THE MUSICAL HIT
(the takes are fast-forward or slow motion almost all the time, so the game sound does not follow the time maps here),
and the synthesised risers (T.RISERS). Optional timeline names add the rest of the sound of a tight edit: T.KILL_THUMP
(a sub thump under every kill), T.BOOMS (sub drops), T.WHOOSH_BLUR (a swish on every blur-in cut), T.GAME_LEVEL (the
gunshot level), segment key shot_from, T.HEADROOM (the level mix.wav is written at).

Timing contract (timeline.py SYNC = 2; an older timeline.py is refused):
  * the SOUND of a kill sits on its musical hit, s["hits"][j] (a measured drum attack), sample-exact: the gunshot's measured
    onset sample and the thump's first sample are `round((hit - R0) * PER * 48000)`; the song, BOOMS and the end of a RISER
    are on their musical beats the same way. The PICTURE of the kill is on s["kills"][j] (an exact output frame, HIT_LEAD
    frames before the hit); K = s["map"](shown beat)[0] is the source frame of that picture = the muzzle flash.
  * the whoosh of a blur-in cut is centred on s["m0"], the cut's MUSICAL beat (like every sound of a moment); the picture of the cut
    is on s["r0"], CUT_LEAD frames earlier.
  * mix.wav is exactly as long as the picture: N_FRAMES / FPS (the sample-to-beat map is unchanged).
  * the delivered chain (master_chain()) carries `alimiter ... latency=1`: no delay, the sound stays where mix.wav has it.

Gunshot onset: the clip's own audio is searched from K-2 to K+8 frames (real shots land -5 .. +75 ms after the flash) for the
steepest rise of the high-passed signal (2.08 ms bins), then the attack is located to the SAMPLE (first rise of a 4-sample RMS
of the first difference over 7 % of the shot's peak and 3x the noise before it; measured on synthetic truth: -0.4 samples on
a hard attack, +13 samples on a 1 ms ramp, <= 2.5 ms on a 6 ms ramp in -20 dB noise). A clean measured onset is never replaced
by a median: rise >= 15 dB is taken as it is, 8..15 dB only when it lies within 4.75 frames of the flash and agrees with the clip's other shots (1 frame). Only a shot
that has no clean onset uses shot_from (the donor kill's OWN measured onset), then the clip's / the edit's median offset,
printed in ms and marked unverified.

usage: python audio.py      -> mix.wav (written at HEADROOM, 0.8 unless timeline.py says otherwise: run.sh makes it up)
                               + stems + audio_report.json (per kill: onset_ms after the K frame, how it was found, rise,
                               the hit sample and placed_ms = onset sample minus hit sample, 0 within a sample);
                               prints each kill's gunshot offset and how it was found, then how many shots were placed on
                               their own measured onset, how many with an unverified offset, and which kills have no gunshot"""
import os, subprocess, sys, wave
import preflight
import numpy as np
import clipio
from ff import FF, limiter
T = preflight.timeline(music=True)
if getattr(T, "SYNC", 0) < 2:
    sys.exit("audio.py: this timeline.py has no SYNC = 2 (the frame-exact timing contract: musical beats in the entries, s[\"hits\"] for the sound, "
             "vis() / frame_beat() / nearest_frame() for the picture). Update it: copy the SYNC block and the SEGS loop from refstyle/timeline_ref_example.py "
             "into timeline.py, or draft the timeline again (python draft_ref_timeline.py). The sound is not placed with the old rules.")

SR = 48000
DUR = T.N_FRAMES / getattr(T, "FPS", 60)    # exactly as long as the picture (a half-frame different from (R1 - R0) * PER at most)
NS = int(round(DUR * SR))
tt = np.arange(NS) / SR
rr = T.R0 + tt / T.PER                      # beat position of every output sample
HEADROOM = getattr(T, "HEADROOM", 0.8)     # mix.wav level; run.sh / deliver.sh / peakguard.py apply volume = 1.18 / HEADROOM before the limiter


def decode(path, file_clock=True):
    """The first audio stream as 48 kHz stereo float; None when the file has none (or does not decode).
    file_clock=True (the game clips): the stream is placed on the file's clock (aresample first_pts=0 pads a stream that starts
    after t=0, ffmpeg's raw decode would drop that start and read every sound that much early; a clip whose audio starts at 0
    decodes bit-identically). The song uses file_clock=False: its BEAT0 / MUSIC_T0 were measured on the plain decode (music_grid.py,
    beat_hits.py), which is the clock its time is in."""
    af = ["-af", "aresample=async=1:first_pts=0"] if file_clock else []
    raw = subprocess.run([FF, "-v", "error", "-i", path, "-map", "0:a:0", *af, "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2) if len(raw) else None


def lowpass(x, fc, order=4):
    """Zero-phase Butterworth-shaped low-pass via FFT."""
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(X / np.sqrt(1 + (f / fc) ** (2 * order))[:, None], n=len(x), axis=0).astype(np.float32)


def highpass(x, fc, order=2):
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = (f / fc) ** order
    return np.fft.irfft(X * (g / np.sqrt(1 + g * g))[:, None], n=len(x), axis=0).astype(np.float32)


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def master_chain(limit=0.82):
    """ffmpeg filter from mix.wav to the delivered sound (run.sh, deliver.sh and peakguard.py use it): make-up gain
    1.18 / HEADROOM, an optional band limit (T.MASTER_LOWPASS, Hz), the limiter, an optional trim after it
    (T.MASTER_TRIM_DB). The limiter is ff.limiter(): `alimiter ... latency=1`, because ffmpeg's alimiter otherwise delays the
    whole sound by its 3 ms look-ahead (143 samples = 2.979 ms in every master measured); with latency=1 the output is the
    same samples 143 earlier, so the delivered sound is where mix.wav has it. A clipped (flat-topped) song master can overshoot
    in the AAC decoder by 3-4 dB above the limiter: a 2017 funk master decoded at +1.8 dBFS through the plain chain (a lower
    limit alone did not fix it: 0.70 still decoded at +0.9); a 16 kHz band limit in front of the limiter plus a -2.2 dB trim
    decoded at -0.7 dBFS, -10.1 LUFS. peakguard.py passes a lower `limit` when the decoded peak of a finished file is too high."""
    af = "volume=%.4f" % (1.18 / HEADROOM)
    lp = getattr(T, "MASTER_LOWPASS", None)
    if lp:
        af += ",lowpass=f=%d:poles=2" % lp
    af += "," + limiter(limit)
    trim = getattr(T, "MASTER_TRIM_DB", 0.0)
    if trim:
        af += ",volume=%.2fdB" % trim
    return af


# ---------------------------------------------------------------- music
def music():
    m = decode(T.MUSIC, file_clock=False)             # the clock BEAT0 was measured in (decode() docstring)
    if m is None:
        sys.exit(f"audio.py: no sound could be decoded from {T.MUSIC}: it is missing or not an audio file. Put the song in clips.json as \"music\" "
                 "and run ingest.py, or set MUSIC in timeline.py.")
    err = preflight.music_problems(T, len(m) / SR)
    if err:
        sys.exit("audio.py: the song does not cover the video:\n  - " + "\n  - ".join(err))
    a = int(round(T.MUSIC_T0 * SR))
    y = m[a:a + NS].copy()
    if len(y) < NS:                             # the preflight formula can be a few hundred samples optimistic; a ValueError from the fade below is not a message
        sys.exit("audio.py: %s is too short for this edit: the mix needs the song from %.3f s to %.3f s (MUSIC_T0 = %.3f s, %.3f s of it) and only "
                 "%.3f s are there: %.1f ms are missing at the end. Lower MUSIC_T0 / R1, or choose a M0 earlier in the track. Nothing was written."
                 % (T.MUSIC, T.MUSIC_T0, T.MUSIC_T0 + NS / SR, T.MUSIC_T0, NS / SR, (len(m) - a) / SR, (NS - len(y)) / SR * 1000.0))
    if T.SWEEP:
        # close a low-pass over the music along T.SWEEP = [(beat, cutoff Hz), ...] and snap it open 4 ms before
        # the last point (in the house example: through the bullet time, opening on the last kill)
        sb, sf = [q[0] for q in T.SWEEP], [q[1] for q in T.SWEEP]
        b0, b1 = np.searchsorted(rr, sb[0]), np.searchsorted(rr, sb[-1]) - int(0.004 * SR)
        pad = SR // 2
        ya, yb = max(0, b0 - pad), min(NS, b1 + pad)
        seg = y[ya:yb]
        cut = slice(b0 - ya, b1 - ya)
        r = rr[b0:b1]
        logfc = np.interp(r, sb, np.log2(sf))
        grid = np.log2([18000, 9000, 4500, 2400, 1400, 900, 620])      # cutoffs outside 620 Hz .. 18 kHz are clamped
        vers = [seg[cut]] + [lowpass(seg, 2 ** g)[cut] for g in grid[1:]]
        out = np.zeros_like(vers[0])
        pos = np.interp(logfc, grid[::-1], np.arange(len(grid))[::-1])
        for j in range(len(grid)):
            w = np.clip(1 - np.abs(pos - j), 0, 1).astype(np.float32)
            out += vers[j] * w[:, None]
        xf = int(0.003 * SR)
        out[-xf:] = out[-xf:] * np.linspace(1, 0, xf)[:, None] + y[b1 - xf:b1] * np.linspace(0, 1, xf)[:, None]
        y[b0:b1] = out
    # A de-click, not a fade: the song must land sample-exact on its hits, and a 50 ms fade-in muted a hit on output sample 0 and cost
    # -15.6 dB at 8.3 ms (half a frame, the placement bar). T.FADE_IN (seconds, squared) still asks for a real fade, e.g. under the picture's.
    fade_in = getattr(T, "FADE_IN", None)
    fi = int((fade_in or 0.005) * SR)
    y[:fi] *= (np.linspace(0, 1, fi) ** (2 if fade_in else 1))[:, None]
    y *= (1 - smooth((rr - T.FADE_OUT[0]) / (T.FADE_OUT[1] - T.FADE_OUT[0] - 0.05)))[:, None].astype(np.float32)
    return y


# ---------------------------------------------------------------- game sound
def wsola(x, pos, win=1440, tol=480):
    """Pitch-preserving time stretch (waveform-similarity overlap-add).
    x: (N, 2) source; pos: wanted source position (in samples) for every output sample."""
    hop = win // 2
    n_out = len(pos)
    pad = win + tol + 8
    xp = np.vstack([np.zeros((pad, 2), np.float32), x, np.zeros((pad, 2), np.float32)])
    mono = xp.mean(1)
    w = np.hanning(win + 1)[:win].astype(np.float32)        # periodic Hann: overlaps add up to 1
    out = np.zeros((n_out + 2 * win, 2), np.float32)
    prev = None
    for m in range(0, n_out + hop, hop):
        ideal = int(round(float(pos[min(m, n_out - 1)]))) + pad - hop
        if prev is None or abs(ideal - (prev + hop)) <= 2:
            start = ideal if prev is None else prev + hop   # real time: plain continuation, bit-exact
        else:
            target = mono[prev + hop: prev + hop + win]     # how the sound would naturally continue
            lo = ideal - tol
            region = mono[lo: lo + 2 * tol + win]
            c = np.correlate(region, target, mode="valid")
            cs = np.concatenate([[0.0], np.cumsum(region.astype(np.float64) ** 2)])
            en = np.sqrt(cs[win:] - cs[:-win]) + 1e-6
            start = lo + int(np.argmax(c / en[: len(c)]))
        out[m: m + win] += xp[start: start + win] * w[:, None]
        prev = start
    return out[hop: hop + n_out]


BIN = 100                                                # 2.083 ms = 1/8 of a 60 fps frame
WIN = 80                                                 # bins searched: K-2 .. K+8 frames (shots land -5 .. +75 ms after the flash)
CLEAN_DB = 15.0                                          # a rise this big is a clean onset whatever the clip's other shots say
MIN_DB = 8.0                                              # below this there is no shot to measure
FRAME_MS = 1000.0 / 60


def shot_onset(mono, t0):
    """The gunshot of a kill in a clip's audio. mono: the clip's mono samples (file clock), t0: the time of the kill's K frame.
    Returns (onset sample, rise dB); (None, best rise) when no onset of at least 8 dB stands out of the window K-2 .. K+8 frames.
    1. Coarse: 2.08 ms bins of the first difference (the crack, not the rumble); the onset bin = the steepest rise against the six
       bins before it, among bins K-0.25 .. K+3.75 frames first (the window of every earlier version: same picks), and only when that
       finds nothing >= 8 dB among K-1.25 .. K+8, with the same rule. A kill near the clip start has fewer baseline bins (>= 3 needed).
    2. Fine: in the bins around it, the first sample where a causal 4-sample RMS of the first difference reaches 7 % of the shot's
       peak (and 3x the noise before it): the attack to the sample. Measured on synthetic shots with a known onset (mc over 200 random
       phases): -0.4 samples on a hard attack, +13 / +17 / +22 samples on 1 / 3 / 6 ms linear ramps, 2.5 ms at worst (6 ms ramp in -20 dB
       noise; the older 2 ms bin start was up to 4.2 ms early on such shots)."""
    n = BIN
    a = int((t0 - 2.0 / 60) * SR)
    lo, hi = max(a, 1), min(a + WIN * n, len(mono))
    if hi - lo < 8 * n:
        return None, 0.0
    d = np.full(WIN * n, np.nan)
    d[lo - a:hi - a] = np.diff(mono[lo - 1:hi])
    e = np.sqrt((d.reshape(WIN, n) ** 2).mean(1)) + 1e-7          # nan where the bin is not fully inside the clip
    ok = ~np.isnan(e)

    def pick(js, emax):
        best, bj = 0.0, None
        for j in js:
            if not ok[j]:
                continue
            v = e[j - 6:j][ok[j - 6:j]]
            if len(v) < 3:
                continue
            r = 20 * np.log10(e[j] / v.mean())
            if r > best and e[j] > 0.25 * emax:
                best, bj = r, j
        return best, bj
    best, bj = pick(range(14, 46), np.nanmax(e[:64]) if ok[:64].any() else 1.0)
    if best < MIN_DB:
        b2, j2 = pick(range(6, WIN), np.nanmax(e))
        if b2 >= MIN_DB:
            best, bj = b2, j2
    if bj is None or best < MIN_DB:
        return None, best
    w = 4                                                           # fine envelope: causal 4-sample RMS (0.083 ms)
    s0 = max(a + (bj - 1) * n, 1 + w)
    s1 = min(a + (bj + 3) * n, len(mono) - 1)
    dd = np.diff(mono[s0 - w - 1:s1 + 1].astype(np.float64))        # dd[i] = x[s0-w+i] - x[s0-w-1+i]
    c = np.concatenate([[0.0], np.cumsum(dd * dd)])
    env = np.sqrt((c[w:] - c[:-w]) / w)                             # env[i] = RMS of dd[i .. i+w-1]; its newest step is into sample s0-1+i
    thr = min(max(3.0 * np.nanmean(e[bj - 6:bj]), 0.07 * env.max()), 0.5 * env.max())
    i = int(np.argmax(env >= thr))
    return s0 - 2 + i, best                                         # the first window whose newest step crossed is one sample after the burst's first step (measured +0.6 .. +1.1 on hard attacks): -1


def hp_causal(x, fc=70.0):
    """2nd-order Butterworth high-pass, CAUSAL: nothing of a shot's low body rings before its onset (the zero-phase FFT high-pass
    this replaces pre-rang 6.75 ms at -18.7 dB). Applied to each excerpt on its own (a linear filter: the sum of excerpts is the same)."""
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(2, fc, "highpass", fs=SR, output="sos"), x, axis=0).astype(np.float32)


def game():
    """Reference-style edit: the takes run in fast-forward or slow motion almost all the time, so the game sound is
    not stretched along with the picture. Every kill gets its own gunshot at natural pitch, cut from the clip and
    placed so that the sample of its measured attack is exactly the sample of the kill's MUSICAL hit (s["hits"]).
    A shot with no clean onset (rise < 8 dB, or 8..15 dB disagreeing with the clip's other shots by more than a frame) takes,
    in this order: the take's shot_from = (clip, K) when the segment names one (another kill's shot of the same weapon, with the
    DONOR KILL's own measured onset; its onset is measured here, whatever kills the edit holds), then its clip's median offset
    ("clip offset"), then the median offset of every measured shot of the edit ("edit median"); those two are printed in ms
    and marked unverified (they can sit a frame or two off). Only a muted take, a clip without sound, or an edit with no measured
    shot at all stays silent (the music hit carries it).
    Returns (buffer, one dict per kill: beat (the hit), shown, clip, state, how, onset_ms, rise, hit, placed_ms)."""
    buf = np.zeros((NS, 2), np.float32)
    clips, monos = {}, {}

    def load(c):
        if c not in clips:
            clips[c] = decode(clipio.path(c))
            if clips[c] is None:                         # a recording without a sound track: its kills are silent, said loudly
                print(f"WARNING: clip {c} ({clipio.path(c)}) has no usable audio track: its game sound (gunshots, voice) is silent in this mix. "
                      "Record again with the game sound on, or accept it: kills of this clip only get the music.", flush=True)
            else:
                monos[c] = clips[c].mean(1)
        return clips[c]
    recs = []
    for s in T.SEGS:
        c = s["clip"]
        for (kb, lv), hb in zip(s["kills"], s["hits"]):
            r = dict(beat=hb, shown=kb, clip=c, lv=lv, hit=int(round((hb - T.R0) * T.PER * SR)), borrow=s.get("shot_from"),
                     state=None, how=None, onset_ms=None, rise=None, placed_ms=None, onset=None)
            recs.append(r)
            if s.get("mute"):
                r["state"], r["how"] = "muted", "mute=True"
                continue
            if load(c) is None:
                r["state"], r["how"] = "silent", "no audio track"
                continue
            K = float(s["map"](kb)[0])                   # the source frame of the picture = the muzzle flash
            r["K"], r["t0"] = K, float(clipio.n2t(c, K))
            r["onset"], r["rise"] = shot_onset(monos[c], r["t0"])
            if r["onset"] is not None:
                r["lag_ms"] = (r["onset"] / SR - r["t0"]) * 1000
    med = {}                                             # per clip: the sound-to-picture offset (ms) of its clearly measured shots
    for c in set(r["clip"] for r in recs):
        v = [r["lag_ms"] for r in recs if r["clip"] == c and r["onset"] is not None and r["rise"] >= 10.0]
        if v:
            med[c] = float(np.median(v))
    allv = [r["lag_ms"] for r in recs if r["onset"] is not None and r["rise"] >= 10.0]
    gmed = float(np.median(allv)) if allv else None      # the whole edit: the last fallback for a clip with no measured shot of its own

    def clean(c, onset, rise, lag_ms):
        """A measured onset is used when it is strong (>= 15 dB: whatever the clip's other shots say), or weak (8..15 dB) and plausible: no
        later than 4.75 frames after the flash (real shots land -5 .. +75 ms after it) and within a frame of the clip's other shots."""
        if onset is None:
            return False
        return rise >= CLEAN_DB or (rise >= MIN_DB and lag_ms <= 4.75 * FRAME_MS and (c not in med or abs(lag_ms - med[c]) <= FRAME_MS))
    PRE = int(0.002 * SR)                                # the excerpt starts 2 ms before the onset, fading in: nothing else precedes it
    L = PRE + int((0.19 + 0.16) * SR)
    env = np.ones(L, np.float32)
    ro = int(0.16 * SR)
    env[:PRE] = (np.arange(PRE) / PRE) ** 2
    env[-ro:] = 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, ro))
    for r in recs:
        if r["state"] in ("muted", "silent"):
            continue
        c = r["clip"]
        src, o = c, r["onset"]
        if clean(c, r["onset"], r["rise"], r.get("lag_ms")):
            r["state"], r["how"], r["onset_ms"] = "measured", "measured (+%.0f dB)" % r["rise"], r["lag_ms"]
        else:
            o = None
            if r["borrow"]:
                # S(shot_from=(clip, K)): no clean shot in this take, so the same weapon's shot from another kill is placed on the hit
                # with ITS OWN measured onset (only when that shot is clean)
                b, Kb = r["borrow"][0], float(r["borrow"][1])
                if load(b) is not None:
                    tb = float(clipio.n2t(b, Kb))
                    ob, rb = shot_onset(monos[b], tb)
                    lb = (ob / SR - tb) * 1000 if ob is not None else None
                    if clean(b, ob, rb, lb):
                        src, o = b, ob
                        r["state"], r["how"], r["onset_ms"] = "donor", "donor %s@%d (+%.0f dB, its own onset)" % (b, Kb, rb), lb
            if o is None:
                m, what = (med[c], "clip offset") if c in med else ((gmed, "edit median") if gmed is not None else (None, None))
                if m is None:
                    print("  kill beat %5.1f %s: no clean gunshot -> silent" % (r["beat"], c))
                    r["state"], r["how"] = "silent", "no clean gunshot"
                    continue
                o = int(round((r["t0"] + m / 1000) * SR))
                r["state"], r["how"], r["onset_ms"] = what, "%s %+.1f ms after the flash (unverified)" % (what, m), m
        x = clips[src]
        lo = o - PRE                                     # the excerpt may start before the clip (a kill near its start): zeros there
        seg = np.zeros((L, 2), np.float32)
        u0, u1 = max(lo, 0), min(lo + L, len(x))
        if u1 > u0:
            seg[u0 - lo:u1 - lo] = x[u0:u1]
        seg *= env[:, None]
        g = min(2.5, max(0.5, 0.55 / (float(np.abs(seg).max()) + 1e-6))) * (1.25 if r["lv"] == 3 else 1.0)
        seg = hp_causal(seg) * np.float32(g)
        d = r["hit"] - PRE
        s0, s1 = max(0, d), min(NS, d + L)
        if s1 > s0:
            buf[s0:s1] += seg[s0 - d:s1 - d]
        r["placed_ms"] = ((d + PRE) - r["hit"]) / SR * 1000     # the excerpt's onset sample (index PRE) minus the hit sample: 0, integer placement
        print("  kill beat %5.1f %s: gunshot onset K%+.2f frames (%+.1f ms after the flash), %s, gain %.2f" % (
            r["beat"], r["clip"], r["onset_ms"] / FRAME_MS, r["onset_ms"], r["how"], g))
    return buf, recs


# ---------------------------------------------------------------- synthesised effects
def noise_sweep(dur, fc_of_x, width_oct, seed):
    """Stereo noise whose band centre follows fc_of_x(x), x in 0..1 (STFT shaping, overlap-add)."""
    n = int(dur * SR)
    N, Hh = 2048, 512
    rng = np.random.default_rng(seed)
    win = np.sqrt(np.hanning(N + 1)[:N]).astype(np.float32)
    f = np.fft.rfftfreq(N, 1 / SR)
    lf = np.log2(np.maximum(f, 20.0))
    out = np.zeros((n + 2 * N, 2), np.float32)
    for ch in range(2):
        w = rng.standard_normal(n + 2 * N).astype(np.float32)
        for st in range(0, n + N, Hh):
            x = min(1.0, max(0.0, (st + N / 2 - N) / n))
            mask = np.exp(-0.5 * ((lf - math_log2(fc_of_x(x))) / width_oct) ** 2)
            out[st:st + N, ch] += np.fft.irfft(np.fft.rfft(w[st:st + N] * win) * mask, n=N).astype(np.float32) * win
    y = out[N:N + n]
    return y / (np.abs(y).max() + 1e-9)


def math_log2(v):
    return float(np.log2(v))


def place(buf, y, beat_end=None, beat_center=None):
    n = len(y)
    if beat_end is not None:
        a = int(round((beat_end - T.R0) * T.PER * SR)) - n
    else:
        a = int(round((beat_center - T.R0) * T.PER * SR)) - n // 2
    s0, s1 = max(0, a), min(NS, a + n)
    buf[s0:s1] += y[s0 - a:s1 - a]


def sfx():
    buf = np.zeros((NS, 2), np.float32)
    # risers: filtered noise that climbs in pitch and level and stops dead on a beat
    # (in the house example: through the breakdown into the drop, and through the bullet time into the last kill)
    for q in T.RISERS:
        d = (q["b"] - q["a"]) * T.PER
        x = np.linspace(0, 1, int(d * SR))
        y = noise_sweep(d, lambda u, q=q: q["f0"] * (q["f1"] / q["f0"]) ** (u ** q["curve"]), q["width"], q["seed"])
        env = x ** q["power"]
        nc = int(q["cut"] * SR)
        env[-nc:] *= np.linspace(1, 0, nc)
        place(buf, y * (q["gain"] * env)[:, None].astype(np.float32), beat_end=q["b"])
    # whooshes on the clip changes: the house style's whip / spin / zoom always; the reference style's blur-in cuts
    # (bwhip / bzoom / broll) when T.WHOOSH_BLUR (gain) is set: measured on a reference edit, a 3-10 kHz swish 10-25 dB
    # over the song at every cut. Centred on the cut's musical beat s["m0"] (the picture's cut is s["r0"], shown CUT_LEAD frames earlier)
    wb = getattr(T, "WHOOSH_BLUR", 0.0)
    for j, s in enumerate(T.SEGS):
        kind = s["tin"][0]
        if kind in ("whip", "spin", "zoom"):
            gain, d = 0.085, 0.44
            dirn = s["tin"][2][0] if kind == "whip" else 0
            lo, hi = 700, 3400
        elif wb and kind in ("bwhip", "bzoom", "broll"):
            gain, d = wb, 0.36
            dirn = s["tin"][2] if kind in ("bwhip", "broll") else 0
            lo, hi = (900, 5200) if kind == "bzoom" else (650, 3800)
        else:
            continue
        x = np.linspace(0, 1, int(d * SR))
        y = noise_sweep(d, lambda q, lo=lo, hi=hi: lo * (hi / lo) ** (1 - abs(2 * q - 1.1) ** 1.5 if abs(2 * q - 1.1) < 1 else 0), 0.9, 10 + j)
        env = np.sin(np.pi * x) ** 2.2
        y = y * (gain * env)[:, None]
        if dirn:                                            # pan with the direction of the move
            pan = 0.5 + 0.38 * dirn * (1 - 2 * x)
            y = np.stack([y[:, 0] * np.sqrt(1 - pan) * 1.41, y[:, 1] * np.sqrt(pan) * 1.41], 1)
        place(buf, y.astype(np.float32), beat_center=s["m0"])
    # 808 sub drops (T.BOOMS = [dict(r=beat, gain=0.26), ...]: a sine gliding ~73 -> 35 Hz over ~1.2 s, hard attack; on
    # the drop, the strongest snare, the mid-song bullet-time kill and the last kill). A little saturation adds
    # harmonics, so speakers without sub bass still carry it.
    for q in getattr(T, "BOOMS", []):
        y = boom()
        a = int(round((q["r"] - T.R0) * T.PER * SR))
        s0, s1 = max(0, a), min(NS, a + len(y))
        buf[s0:s1] += y[s0 - a:s1 - a] * np.float32(q["gain"])
    # a sub thump under every kill (T.KILL_THUMP = gain; level 2 and 3 kills hit harder): measured on a reference edit,
    # sub bass 15-50 dB over the song on its kill and cut hits. First sample on the kill's MUSICAL hit (s["hits"]), like the gunshot.
    kt = getattr(T, "KILL_THUMP", 0.0)
    if kt:
        y = thump()
        for s in T.SEGS:
            for hb, (k, lv) in zip(s["hits"], s["kills"]):
                a = int(round((hb - T.R0) * T.PER * SR))
                s0, s1 = max(0, a), min(NS, a + len(y))
                buf[s0:s1] += y[s0 - a:s1 - a] * np.float32(kt * (1.0, 1.25, 1.5)[lv - 1])
    return buf


def thump(dur=0.30):
    """Kill thump: a sine gliding 95 -> 42 Hz with a 2 ms attack and a ~70 ms decay, saturated a little so small
    speakers still carry it, plus a 4 ms high-passed click on top."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 42.0 + 53.0 * np.exp(-t / 0.045)
    ph = 2 * np.pi * np.cumsum(f) / SR
    env = (1 - np.exp(-t / 0.002)) * np.exp(-t / 0.07)
    y = np.tanh(2.2 * np.sin(ph)) / np.tanh(2.2) * env
    rng = np.random.default_rng(5)
    c = highpass(np.stack([rng.standard_normal(n), rng.standard_normal(n)], 1).astype(np.float32), 2500.0)
    c *= (np.exp(-t / 0.004) * 0.35)[:, None]
    return (np.stack([y, y], 1) + c).astype(np.float32)


def boom(dur=2.6, f0=73.0, f1=34.0, glide=1.25):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f0 * (f1 / f0) ** (np.clip(t / glide, 0, 1) ** 0.8)
    ph = 2 * np.pi * np.cumsum(f) / SR
    env = (1 - np.exp(-t / 0.0025)) / (1 + (t / 1.25) ** 4)
    y = np.tanh(1.8 * np.sin(ph)) / np.tanh(1.8) * env
    return np.stack([y, y], 1).astype(np.float32)


if __name__ == "__main__":
    m = music()
    g, rep = game()
    fx = sfx()
    # HEADROOM: mix.wav is written at 0.8 unless timeline.py sets another level (a loud song plus loud gunshots, thumps and
    # booms needs 0.5-0.7: HEADROOM = 0.5 in timeline.py); run.sh / deliver.sh / peakguard.py give it back with
    # volume = 1.18 / HEADROOM in front of the limiter (master_chain()). GAME_LEVEL = the gunshot level (0.60).
    mix = (0.84 * m + getattr(T, "GAME_LEVEL", 0.60) * g + fx) * HEADROOM
    # The peak is checked BEFORE anything is written: a failed run must not leave a clipped mix.wav behind that a later
    # deliver.sh / mux would pick up as if it were good.
    print("mix peak %.3f  rms %.3f | music peak %.3f | game peak %.3f rms %.3f | sfx peak %.3f" % (
        np.abs(mix).max(), np.sqrt((mix ** 2).mean()), np.abs(m).max(), np.abs(g).max(), np.sqrt((g ** 2).mean()), np.abs(fx).max()))
    if np.abs(mix).max() > 1.0:
        sys.exit("audio.py: the mix peaks at %.2f even at HEADROOM %.2g, so it would clip before the limiter (the song is very loud, or the "
                 "gunshots / thumps / booms are hot): set HEADROOM = 0.5 (or lower) in timeline.py (run.sh, deliver.sh and peakguard.py then apply "
                 "volume = 1.18 / HEADROOM), or lower GAME_LEVEL, KILL_THUMP and the BOOMS gains, and run audio.py again. Nothing was written."
                 % (np.abs(mix).max(), HEADROOM))
    for name, x in (("stem_music", m), ("stem_game", g), ("stem_sfx", fx), ("mix", mix)):
        with wave.open(f"{name}.wav", "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    # How sure is each gunshot? A placed shot has its onset sample on the hit sample by construction (placed_ms = 0); what can be
    # wrong is the onset that was found: "measured" = the shot's own clean onset, "donor" = the shot_from donor's own clean onset,
    # "clip offset" / "edit median" = a median offset, NOT verified.
    n = {st: sum(1 for q in rep if q["state"] == st) for st in ("measured", "donor", "clip offset", "edit median", "muted", "silent")}
    print("gunshots: %d placed on their own measured onset, %d on a donor shot's own onset; %d placed with their clip's usual offset and %d with the edit's "
          "median offset because the shot itself does not stand out (can sit a frame or two off: NOT VERIFIED); %d kills without a gunshot (%d mute=True, %d not found)"
          % (n["measured"], n["donor"], n["clip offset"], n["edit median"], n["muted"] + n["silent"], n["muted"], n["silent"]))
    for st, label in (("clip offset", "placed with the clip offset"), ("edit median", "placed with the edit median offset"),
                      ("muted", "no gunshot, mute=True"), ("silent", "no gunshot, none found")):
        ks = ["%g %s%s" % (q["beat"], q["clip"], " (%+.1f ms)" % q["onset_ms"] if q["onset_ms"] is not None else "") for q in rep if q["state"] == st]
        if ks:
            print("  %s: %s" % (label, ", ".join(ks)))
    import hashlib, json                                  # gate.py reads this: one entry per kill
    json.dump(dict(timeline=hashlib.sha1(open("timeline.py", "rb").read()).hexdigest(), style="reference", written_peak=float(np.abs(mix).max()),
                   samples=NS, sync=2,
                   kills=[dict(beat=q["beat"], shown=q["shown"], clip=q["clip"], state=q["state"], how=q["how"], hit_sample=q["hit"],
                               onset_ms=None if q["onset_ms"] is None else round(q["onset_ms"], 3), rise_db=None if q["rise"] is None else round(q["rise"], 1),
                               placed_ms=q["placed_ms"]) for q in rep]), open("audio_report.json", "w"), indent=1)
