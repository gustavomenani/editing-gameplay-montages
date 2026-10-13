"""Spectrograms of the finished mix and of its stems, labelled in timeline beats: the editor's "ears".
Shows whether a riser really ends on its beat, a whoosh sits on its transition, the low-pass sweep
closes and opens where intended, and whether the game sound is present under the music.

usage: python mix_spec.py -5.2 5 59 72      pairs of beats: one block (mix / effects / game) per range
       -> mix_spec.png      (needs mix.wav, stem_sfx.wav, stem_game.wav from audio.py)"""
import sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import timeline as T

try:
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 15)
except OSError:
    font = ImageFont.load_default()
SR, N, H = 48000, 2048, 256
fr = np.fft.rfftfreq(N, 1 / SR)


def load(p):
    try:
        w = wave.open(p)
    except (FileNotFoundError, wave.Error) as e:
        raise SystemExit("cannot read %s (%s): run audio.py first" % (p, e))
    if w.getframerate() != SR or w.getsampwidth() != 2:
        raise SystemExit("%s is %d Hz / %d-bit: this script reads the 48000 Hz 16-bit files audio.py writes" % (p, w.getframerate(), 8 * w.getsampwidth()))
    return (np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, w.getnchannels()).mean(1) / 32768.0).astype(np.float32)


def row(x, r0, r1, title, width=2000, sh=260):
    a = max(0, int((r0 - T.R0) * T.PER * SR) - N // 2)
    b = min(len(x), int((r1 - T.R0) * T.PER * SR) + N)
    seg = x[a:b]
    nfr = 1 + (len(seg) - N) // H
    idx = np.arange(N)[None, :] + H * np.arange(nfr)[:, None]
    S = np.abs(np.fft.rfft(seg[idx] * np.hanning(N).astype(np.float32), axis=1))
    rb = T.R0 + (a + np.arange(nfr) * H + N / 2) / SR / T.PER
    fb = np.geomspace(40, 16000, sh)
    ix = np.clip(np.searchsorted(fr, fb), 1, len(fr) - 1)
    L = np.clip((20 * np.log10(S[:, ix] + 1e-5) + 20) / 75, 0, 1)
    cols = np.clip(((rb - r0) / (r1 - r0) * width).astype(int), 0, width - 1)
    img = np.zeros((sh, width), np.float32)
    for c, l in zip(cols, L):
        img[:, c] = np.maximum(img[:, c], l[::-1])
    rgb = np.stack([np.clip(img * 2.2 - 0.9, 0, 1), np.clip(img * 1.6 - 0.25, 0, 1),
                    np.clip(img * 1.2, 0, 1) * (1 - 0.6 * np.clip(img * 2 - 1, 0, 1))], -1)
    out = Image.fromarray((rgb * 255).astype(np.uint8))
    d = ImageDraw.Draw(out)
    for r in range(int(np.ceil(r0)), int(r1) + 1):
        xx = int((r - r0) / (r1 - r0) * width)
        d.line((xx, 0, xx, sh), fill=(150, 150, 150))
        d.text((xx + 2, 2), str(r), fill=(255, 255, 0), font=font)
    d.text((6, sh - 20), title, fill=(255, 255, 255), font=font)
    return out


v = [float(q) for q in sys.argv[1:]]
if len(v) % 2:
    raise SystemExit("usage: python mix_spec.py [r0 r1 [r0 r1 ...]]   pairs of beats (got %d numbers)" % len(v))
ranges = list(zip(v[::2], v[1::2])) or [(T.R0, min(T.R1, T.R0 + 12)), (max(T.R0, T.R1 - 14), T.R1)]
for r0, r1 in ranges:
    if not r1 > r0:
        raise SystemExit("range %g .. %g: the second beat must come after the first" % (r0, r1))
    if r1 <= T.R0 or r0 >= T.R1:
        raise SystemExit("range %g .. %g lies outside the video (beats %g .. %g)" % (r0, r1, T.R0, T.R1))
mix, fx, game = load("mix.wav"), load("stem_sfx.wav"), load("stem_game.wav")
rows = []
for r0, r1 in ranges:
    rows += [row(mix, r0, r1, "MIX  beats %g .. %g" % (r0, r1)), row(fx, r0, r1, "effects stem (risers, whooshes)"),
             row(game, r0, r1, "game stem")]
im = Image.new("RGB", (2000, 264 * len(rows)), (40, 40, 40))
for i, r in enumerate(rows):
    im.paste(r, (0, i * 264))
im.save("mix_spec.png")
print("wrote mix_spec.png:", len(ranges), "ranges x (mix, effects, game)")
