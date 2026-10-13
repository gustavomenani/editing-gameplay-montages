"""Sound for the reference-style edit: the track, one gunshot per kill at natural pitch with its onset on the
beat (the takes are fast-forward or slow motion almost all the time, so the game sound does not follow the
time maps here), and the synthesised risers (T.RISERS). Optional timeline names add the rest of the sound of a
tight edit: T.KILL_THUMP (a sub thump under every kill), T.BOOMS (sub drops), T.WHOOSH_BLUR (a swish on every
blur-in cut), T.GAME_LEVEL (the gunshot level), segment key shot_from, T.HEADROOM (the level mix.wav is written at).

usage: python audio.py      -> mix.wav (written at HEADROOM, 0.8 unless timeline.py says otherwise: run.sh makes it up)
                               + stems; prints each kill's gunshot offset and how it was found, then how many shots were
                               placed on their own measured onset, how many with the clip's usual offset, and which kills
                               have no gunshot"""
import os, subprocess, sys, wave
import preflight
import numpy as np
import clipio
from ff import FF
T = preflight.timeline(music=True)

SR = 48000
DUR = (T.R1 - T.R0) * T.PER
NS = int(round(DUR * SR))
tt = np.arange(NS) / SR
rr = T.R0 + tt / T.PER                      # beat position of every output sample
HEADROOM = getattr(T, "HEADROOM", 0.8)     # mix.wav level; run.sh / deliver.sh / peakguard.py apply volume = 1.18 / HEADROOM before the limiter


def decode(path):
    """The first audio stream as 48 kHz stereo float; None when the file has none (or does not decode)."""
    raw = subprocess.run([FF, "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
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
    (T.MASTER_TRIM_DB). A clipped (flat-topped) song master can overshoot in the AAC decoder by 3-4 dB above the
    limiter: a 2017 funk master decoded at +1.8 dBFS through the plain chain (a lower limit alone did not fix it:
    0.70 still decoded at +0.9); a 16 kHz band limit in front of the limiter plus a -2.2 dB trim decoded at -0.7 dBFS,
    -10.1 LUFS. peakguard.py passes a lower `limit` when the decoded peak of a finished file is too high."""
    af = "volume=%.4f" % (1.18 / HEADROOM)
    lp = getattr(T, "MASTER_LOWPASS", None)
    if lp:
        af += ",lowpass=f=%d:poles=2" % lp
    af += ",alimiter=limit=%.4f:attack=3:release=60:level=disabled" % limit
    trim = getattr(T, "MASTER_TRIM_DB", 0.0)
    if trim:
        af += ",volume=%.2fdB" % trim
    return af


# ---------------------------------------------------------------- music
def music():
    m = decode(T.MUSIC)
    if m is None:
        sys.exit(f"audio.py: no sound could be decoded from {T.MUSIC}: it is missing or not an audio file. Put the song in clips.json as \"music\" "
                 "and run ingest.py, or set MUSIC in timeline.py.")
    err = preflight.music_problems(T, len(m) / SR)
    if err:
        sys.exit("audio.py: the song does not cover the video:\n  - " + "\n  - ".join(err))
    a = int(round(T.MUSIC_T0 * SR))
    y = m[a:a + NS].copy()
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
    fade_in = getattr(T, "FADE_IN", None)                # seconds: a squared fade-in of that length (a tight edit: 0.45, under the picture's fade-in); absent: 0.05 s linear
    fi = int((fade_in or 0.05) * SR)
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


def game():
    """Reference-style edit: the takes run in fast-forward or slow motion almost all the time, so the game sound is
    not stretched along with the picture. Every kill gets its own gunshot at natural pitch, cut from the clip and
    placed so that its onset lands exactly on the beat. A shot that does not stand out takes the one of the take's
    shot_from = (clip, K) when the segment names one (another kill's clean shot of the same weapon, placed at that
    clip's usual offset); otherwise its clip's usual offset; when its clip has no measured shot at all (a short edit
    with one or two kills per clip), the median offset of every measured shot of the edit. Only a muted take, a clip
    without sound, or an edit with no measured shot at all stays silent (the music hit carries it)."""
    buf = np.zeros((NS, 2), np.float32)
    clips, report, pending, state = {}, [], [], {}
    n = 100                                              # 2.08 ms bins = 8 per source frame
    for i, s in enumerate(T.SEGS):
        c = s["clip"]
        for k, lv in s["kills"]:
            report.append((k, c))
            if s.get("mute"):
                state[(k, c)] = "muted"
                continue
            if c not in clips:
                clips[c] = decode(clipio.path(c))
                if clips[c] is None:                     # a recording without a sound track: its kills are silent, said loudly
                    print(f"WARNING: clip {c} ({clipio.path(c)}) has no usable audio track: its game sound (gunshots, voice) is silent in this mix. "
                          "Record again with the game sound on, or accept it: kills of this clip only get the music.", flush=True)
            if clips[c] is None:
                state[(k, c)] = "silent"
                continue
            mono = clips[c].mean(1)
            K = float(s["map"](k)[0])
            a = int(clipio.n2t(c, K - 2) * SR)
            hp = np.diff(mono[a - 1:a + 64 * n + 1])[:64 * n]
            e = np.sqrt((hp.reshape(-1, n) ** 2).mean(1)) + 1e-7     # frames K-2 .. K+6
            best, bj = 0.0, None
            for j in range(14, 46):                      # K-0.25 .. K+3.75 frames
                rise = 20 * np.log10(e[j] / e[j - 6:j].mean())
                if rise > best and e[j] > 0.25 * e.max():
                    best, bj = rise, j
            pending.append((k, lv, c, K, (bj / 8.0 - 2.0) if bj is not None else None, best, s.get("shot_from")))
    med = {}                                             # per clip: the sound-to-picture offset of its clearly measured shots
    for c in set(p[2] for p in pending):
        v = [p[4] for p in pending if p[2] == c and p[4] is not None and p[5] >= 10.0]
        if v:
            med[c] = float(np.median(v))
    allv = [p[4] for p in pending if p[4] is not None and p[5] >= 10.0]
    gmed = float(np.median(allv)) if allv else None      # the whole edit: the last fallback for a clip with no measured shot of its own
    pre_s, sus, rel = 0.008, 0.19, 0.16
    L = int((pre_s + sus + rel) * SR)
    env = np.ones(L, np.float32)
    fi, ro = int(0.006 * SR), int(rel * SR)
    env[:fi] = np.linspace(0, 1, fi) ** 2
    env[-ro:] = 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, ro))
    for k, lv, c, K, lag, rise, borrow in pending:
        how = "measured (+%.0f dB)" % rise
        src, Ks = c, K                                    # the clip and source frame the gunshot is cut from
        ok = lag is not None and rise >= 8.0 and (c not in med or abs(lag - med[c]) <= 1.0)
        if not ok and borrow:
            # S(shot_from=(clip, K)): no clean shot in this take, so the same weapon's shot from another kill is placed on
            # the beat, at that clip's own offset (only when that clip has a measured offset)
            b = borrow[0]
            if b not in clips:
                clips[b] = decode(clipio.path(b))
            if clips[b] is not None and b in med:
                src, Ks, lag, how, ok = b, float(borrow[1]), med[b], "borrowed from %s@%d" % (b, borrow[1]), True
        if not ok:
            if c in med:
                lag, how = med[c], "clip offset"
            elif gmed is not None:
                lag, how = gmed, "edit median"
            else:
                print("  kill beat %5.1f %s: no clean gunshot -> silent" % (k, c))
                state[(k, c)] = "silent"
                continue
        x = clips[src]
        a = int(round((float(clipio.n2t(src, Ks + lag)) - pre_s) * SR))
        seg = x[a:a + L].astype(np.float32) * env[:, None]
        g = min(2.5, max(0.5, 0.55 / (float(np.abs(seg).max()) + 1e-6))) * (1.25 if lv == 3 else 1.0)
        d = int(round((k - T.R0) * T.PER * SR)) - int(pre_s * SR)
        s0, s1 = max(0, d), min(NS, d + L)
        buf[s0:s1] += seg[s0 - d:s1 - d] * np.float32(g)
        print("  kill beat %5.1f %s: gunshot onset K%+.2f frames, %s, gain %.2f" % (k, c, lag, how, g))
        state[(k, c)] = how if how in ("clip offset", "edit median") else ("measured" if how.startswith("measured") else "clip offset")
    buf = highpass(buf, 70.0)
    return buf, [(k, c, state[(k, c)]) for k, c in report]


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
    # over the song at every cut
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
        place(buf, y.astype(np.float32), beat_center=s["r0"])
    # 808 sub drops (T.BOOMS = [dict(r=beat, gain=0.26), ...]: a sine gliding ~73 -> 35 Hz over ~1.2 s, hard attack; on
    # the drop, the strongest snare, the mid-song bullet-time kill and the last kill). A little saturation adds
    # harmonics, so speakers without sub bass still carry it.
    for q in getattr(T, "BOOMS", []):
        y = boom()
        a = int(round((q["r"] - T.R0) * T.PER * SR))
        s0, s1 = max(0, a), min(NS, a + len(y))
        buf[s0:s1] += y[s0 - a:s1 - a] * np.float32(q["gain"])
    # a sub thump under every kill (T.KILL_THUMP = gain; level 2 and 3 kills hit harder): measured on a reference edit,
    # sub bass 15-50 dB over the song on its kill and cut hits. Onset on the kill beat, like the gunshot.
    kt = getattr(T, "KILL_THUMP", 0.0)
    if kt:
        y = thump()
        for s in T.SEGS:
            for k, lv in s["kills"]:
                a = int(round((k - T.R0) * T.PER * SR))
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
    for name, x in (("stem_music", m), ("stem_game", g), ("stem_sfx", fx), ("mix", mix)):
        with wave.open(f"{name}.wav", "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    print("mix peak %.3f  rms %.3f | music peak %.3f | game peak %.3f rms %.3f | sfx peak %.3f" % (
        np.abs(mix).max(), np.sqrt((mix ** 2).mean()), np.abs(m).max(), np.abs(g).max(), np.sqrt((g ** 2).mean()), np.abs(fx).max()))
    if np.abs(mix).max() > 1.0:
        sys.exit("audio.py: the mix peaks at %.2f even at HEADROOM %.2g, so it would clip before the limiter (the song is very loud, or the "
                 "gunshots / thumps / booms are hot): set HEADROOM = 0.5 (or lower) in timeline.py (run.sh, deliver.sh and peakguard.py then apply "
                 "volume = 1.18 / HEADROOM), or lower GAME_LEVEL, KILL_THUMP and the BOOMS gains, and run audio.py again"
                 % (np.abs(mix).max(), HEADROOM))
    # How sure is each gunshot? A placed shot has its onset on the beat by construction; what can be wrong is the onset
    # that was found. (Measuring the finished stem tells nothing here: every shot fades in from silence 8 ms before its
    # onset, and shots less than a beat apart overlap.)
    n = {st: sum(1 for q in rep if q[2] == st) for st in ("measured", "clip offset", "edit median", "muted", "silent")}
    print("gunshots: %d placed on their own measured onset; %d placed with their clip's usual offset and %d with the edit's median offset because the "
          "shot itself does not stand out (can sit a frame or two off: not verified); %d kills without a gunshot (%d mute=True, %d not found)"
          % (n["measured"], n["clip offset"], n["edit median"], n["muted"] + n["silent"], n["muted"], n["silent"]))
    for st, label in (("clip offset", "placed with the clip offset"), ("edit median", "placed with the edit median offset"),
                      ("muted", "no gunshot, mute=True"), ("silent", "no gunshot, none found")):
        ks = ["%g %s" % (k, c) for k, c, q in rep if q == st]
        if ks:
            print("  %s: %s" % (label, ", ".join(ks)))
    import hashlib, json                                  # gate.py reads this: one entry per kill (measured / clip offset / edit median / muted / silent)
    json.dump(dict(timeline=hashlib.sha1(open("timeline.py", "rb").read()).hexdigest(), style="reference", written_peak=float(np.abs(mix).max()),
                   kills=[dict(beat=k, clip=c, state=q) for k, c, q in rep]), open("audio_report.json", "w"), indent=1)
