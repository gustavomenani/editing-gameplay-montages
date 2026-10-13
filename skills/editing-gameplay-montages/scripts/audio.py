"""Sound for the montage: the track (with an optional filter sweep, T.SWEEP), the game sound
following the same time maps as the picture (shifted so each shot lands on its hit), and a few
synthesised risers (T.RISERS) / whooshes (one per whip, spin or zoom transition).

usage: python audio.py      -> mix.wav + stem_music.wav / stem_game.wav / stem_sfx.wav, and for every kill where
                               the loudest game-sound onset lands relative to its beat (should be within a few ms)"""
import os, subprocess, sys, wave
import preflight
import numpy as np
import clipio
from ff import FF
T = preflight.timeline(music=True)

SR = 48000
HEADROOM = 0.5                              # level at which the .wav files are written (see the end of this file)
DUR = (T.R1 - T.R0) * T.PER
NS = int(round(DUR * SR))
tt = np.arange(NS) / SR
rr = T.R0 + tt / T.PER                      # beat position of every output sample


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
    fi = int(0.05 * SR)
    y[:fi] *= np.linspace(0, 1, fi)[:, None]
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
    buf = np.zeros((NS, 2), np.float32)
    clips = {}
    report = []
    for i, s in enumerate(T.SEGS):
        c = s["clip"]
        if c not in clips:
            clips[c] = decode(clipio.path(c))
            if clips[c] is None:                    # a recording without a sound track: its segments are silent, said loudly
                print(f"WARNING: clip {c} ({clipio.path(c)}) has no usable audio track: its game sound (shots, voice) is silent in this mix. "
                      "Record again with the game sound on, or accept it: segments of this clip only get the music.", flush=True)
                clips[c] = np.zeros((int((clipio.n2t(c, clipio.n_frames(c) - 1) + 1) * SR), 2), np.float32)
        x = clips[c]
        a, b = max(0, int(np.searchsorted(rr, s["x0"]))), min(NS, int(np.searchsorted(rr, s["x1"])))
        r = rr[a:b]
        p, v = s["map"](r)
        kb = [k for k, _ in s["kills"]]
        lag = np.interp(r, kb, s["lag"]) if len(kb) > 1 else s["lag"][0]
        if s.get("voice"):
            # this clip's sound is mostly people talking: keep their pitch (time-stretch instead of
            # resampling) and let the reaction run on in real time while the picture goes slow motion
            hold = kb[-1] + 0.2
            p_hold, p_first = float(s["map"](hold)[0]), float(s["map"](kb[0])[0])
            p_a = np.where(r <= hold, p, p_hold + (r - hold) * T.FPB)
            p_a = np.where(r < kb[0], p_first - (kb[0] - r) * T.FPB, p_a)   # real time before the first kill too
            ts = clipio.n2t(c, p_a) + lag / 60.0
            y = wsola(x, np.clip(ts * SR, 0, len(x) - 2))
            g = np.full(len(r), s["voice"], np.float32)
        elif s.get("stretch"):
            # keeps the pitch of voice lines where the picture runs a little faster than real time
            ts = clipio.n2t(c, p) + lag / 60.0
            y = wsola(x, np.clip(ts * SR, 0, len(x) - 2))
            g = smooth((v - 0.25) / 0.45) * (1 - smooth((v - 1.3) / 0.5))
        else:
            ts = clipio.n2t(c, p) + lag / 60.0              # the sound of frame p arrives `lag` frames later
            pos = np.clip(ts * SR, 0, len(x) - 2)
            j = pos.astype(np.int64)
            f = (pos - j)[:, None].astype(np.float32)
            y = x[j] * (1 - f) + x[j + 1] * f
            g = smooth((v - 0.25) / 0.45)                   # slow motion: the game goes quiet, music carries
            g = g * (1 - smooth((v - 1.3) / 0.5))           # fast-forward: no chipmunk sound either
            for k, lv in s["kills"]:                        # the big kills are always heard, even slowed down
                if lv >= 2:
                    g = np.maximum(g, smooth((r - (k - 0.06)) / 0.05) * smooth(((k + 0.55) - r) / 0.2))
        d_in = s["r0"] - s["x0"]
        g = g * (smooth((r - s["x0"]) / (2 * d_in)) if d_in > 0 else np.clip((r - s["r0"]) / 0.03, 0, 1))
        d_out = s["x1"] - s["r1"]
        g = g * (smooth((s["x1"] - r) / (2 * d_out)) if d_out > 0 else np.clip((s["r1"] - r) / 0.03, 0, 1))
        if s.get("mute"):
            g = g * 0
        buf[a:b] += y * g[:, None].astype(np.float32)
        for k, lv in s["kills"]:
            report.append((k, c))
    buf = highpass(buf, 70.0)
    return buf, report


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
    # whooshes on the clip changes
    for j, s in enumerate(T.SEGS):
        kind = s["tin"][0]
        if kind not in ("whip", "spin", "zoom"):
            continue
        d = 0.44
        x = np.linspace(0, 1, int(d * SR))
        y = noise_sweep(d, lambda q: 700 * (3400 / 700) ** (1 - abs(2 * q - 1.1) ** 1.5 if abs(2 * q - 1.1) < 1 else 0), 0.9, 10 + j)
        env = np.sin(np.pi * x) ** 2.2
        y = y * (0.085 * env)[:, None]
        if kind == "whip" and s["tin"][2][0] != 0:          # pan with the direction of the move
            pan = 0.5 + 0.38 * s["tin"][2][0] * (1 - 2 * x)
            y = np.stack([y[:, 0] * np.sqrt(1 - pan) * 1.41, y[:, 1] * np.sqrt(pan) * 1.41], 1)
        place(buf, y.astype(np.float32), beat_center=s["r0"])
    return buf


if __name__ == "__main__":
    m = music()
    g, rep = game()
    fx = sfx()
    # game sound and effects fade out with the picture too (music() already fades the track)
    out = (1 - smooth((rr - T.FADE_OUT[0]) / (T.FADE_OUT[1] - T.FADE_OUT[0] - 0.05)))[:, None].astype(np.float32)
    g, fx = g * out, fx * out
    mix = 0.84 * m + 0.60 * g + fx
    # The files are written at HEADROOM (half level): the mix peaks above full scale (a loud master resampled,
    # plus shots), and a 16-bit file would flatten those peaks before the limiter in run.sh ever sees them.
    # run.sh / deliver.sh give the level back (volume = 1.18 / HEADROOM) in front of the limiter.
    for name, x in (("stem_music", m), ("stem_game", g), ("stem_sfx", fx), ("mix", mix)):
        with wave.open(f"{name}.wav", "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((np.clip(x * HEADROOM, -1, 1) * 32767).astype(np.int16).tobytes())
    print("mix peak %.3f  rms %.3f | music peak %.3f | game peak %.3f rms %.3f | sfx peak %.3f  (1.0 = full scale; written at x%.1f, "
          "so peaks up to %.1f are safe)" % (np.abs(mix).max(), np.sqrt((mix ** 2).mean()), np.abs(m).max(), np.abs(g).max(),
                                             np.sqrt((g ** 2).mean()), np.abs(fx).max(), HEADROOM, 1 / HEADROOM))
    if np.abs(mix).max() * HEADROOM > 1.0:
        sys.exit("audio.py: the mix peaks at %.2f, above the %.1f this file's headroom allows (the song is very loud or the game sound is hot): "
                 "lower the gains in the line  mix = 0.84 * m + 0.60 * g + fx  (music 0.84, game 0.60), e.g. to 0.7 and 0.5, and run audio.py again"
                 % (np.abs(mix).max(), 1 / HEADROOM))
    # where does each kill's gunshot land relative to its beat?
    e = np.abs(np.diff(g.mean(1), prepend=0))
    k5 = int(0.004 * SR)
    env = np.convolve(e, np.ones(k5) / k5, mode="same")
    muted = {(k, s["clip"]) for s in T.SEGS if s.get("mute") for k, _ in s["kills"]}
    states = []                                           # gate.py reads these from audio_report.json: heard / muted / silent, per kill
    for k, c in rep:
        cidx = int(round((k - T.R0) * T.PER * SR))
        a, b = max(0, cidx - int(0.12 * SR)), min(NS, cidx + int(0.12 * SR))
        if b - a <= 2 * k5 or env[a:b].max() < 1e-7:
            print("  kill beat %5.1f (%s): no game sound around it (silent or muted clip, or the kill is at the very start / end of the video)" % (k, c))
            states.append(dict(beat=k, clip=c, state="muted" if (k, c) in muted else "silent"))
            continue
        seg = np.log(env[a:b] + 1e-6)
        rise = seg[k5:] - seg[:-k5]
        i = int(np.argmax(rise))
        print("  kill beat %5.1f (%s): strongest game-sound onset at %+4.0f ms" % (k, c, (a + i + k5 / 2 - cidx) / SR * 1000))
        states.append(dict(beat=k, clip=c, state="heard", onset_ms=float((a + i + k5 / 2 - cidx) / SR * 1000)))
    import hashlib, json
    json.dump(dict(timeline=hashlib.sha1(open("timeline.py", "rb").read()).hexdigest(), style="house", written_peak=float(np.abs(mix).max() * HEADROOM),
                   kills=states), open("audio_report.json", "w"), indent=1)
