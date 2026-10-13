"""Draw the music as a spectrogram labelled in TIMELINE beats, with the onsets of three drum bands
underneath (red = kick / bass below 150 Hz, green = snare body, blue = hats above 6 kHz).
Read it to see, beat by beat, what hits where: the kills go on the tall red or green bars.

usage: python music_spec.py [r0 r1]      beats to draw; default: the video plus 8 beats on each side
-> spec_0.png, spec_1.png, ...  (two rows of 26 beats per picture, white line every 4 beats)

Needs BPM / BEAT0 / M0 / MUSIC in timeline.py (BEAT0 from music_grid.py; M0 = 0 while still choosing
the section, so the labels are plain beats of the track)."""
import glob, os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import timeline as T
from ff import FF

SR, N, H = 44100, 2048, 256
raw = subprocess.run([FF, "-v", "error", "-i", T.MUSIC, "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                     capture_output=True).stdout
x = np.frombuffer(raw, np.float32)
if len(x) < SR:
    raise SystemExit("cannot read audio from %s (MUSIC in timeline.py)" % T.MUSIC)
fr = np.fft.rfftfreq(N, 1 / SR)
try:
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 15)
except OSError:
    font = ImageFont.load_default()


def stft(seg):
    nfr = 1 + (len(seg) - N) // H
    idx = np.arange(N)[None, :] + H * np.arange(nfr)[:, None]
    return np.abs(np.fft.rfft(seg[idx] * np.hanning(N).astype(np.float32), axis=1))


def row(r0, r1, width=2000, sh=300):
    t0, t1 = T.beat_time(r0), T.beat_time(r1)
    a = max(0, int(t0 * SR) - N // 2)
    seg = x[a:int(t1 * SR) + N]
    out = Image.new("RGB", (width, sh + 150), (0, 0, 0))
    d = ImageDraw.Draw(out)
    if len(seg) > 2 * N:
        S = stft(seg)
        tt = (a + np.arange(len(S)) * H + N / 2) / SR
        fbins = np.geomspace(40, 14000, sh)                      # log-frequency picture
        idx = np.clip(np.searchsorted(fr, fbins), 1, len(fr) - 1)
        L = 20 * np.log10(S[:, idx] + 1e-4)
        L = np.clip((L - L.max() + 75) / 75, 0, 1)
        cols = np.clip(((tt - t0) / (t1 - t0) * width).astype(int), 0, width - 1)
        img = np.zeros((sh, width), np.float32)
        for c, l in zip(cols, L):
            img[:, c] = np.maximum(img[:, c], l[::-1])
        rgb = np.stack([np.clip(img * 2.2 - 0.9, 0, 1), np.clip(img * 1.6 - 0.25, 0, 1),
                        np.clip(img * 1.2, 0, 1) * (1 - 0.6 * np.clip(img * 2 - 1, 0, 1))], -1)
        out.paste(Image.fromarray((rgb * 255).astype(np.uint8)), (0, 0))
        Lg = np.log1p(30 * S)
        flux = np.maximum(Lg[3:] - Lg[:-3], 0)
        for bi, (name, m, col) in enumerate([("low<150", fr < 150, (255, 80, 80)), ("mid", (fr >= 200) & (fr < 2500), (90, 255, 120)),
                                             ("high>6k", fr >= 6000, (120, 180, 255))]):
            e = flux[:, m].sum(1)
            e = e / (np.percentile(e, 99.7) + 1e-9)
            y0 = sh + 4 + bi * 48
            for c, v in zip(cols[3:], e):
                hgt = int(min(1.0, v) * 44)
                if hgt > 2:
                    d.line((c, y0 + 44, c, y0 + 44 - hgt), fill=col)
            d.text((2, y0), name, fill=col, font=font)
    for r in np.arange(np.ceil(r0 * 2) / 2, r1, 0.5):
        xx = int((r - r0) / (r1 - r0) * width)
        if abs(r - round(r)) < 1e-6:
            d.line((xx, 0, xx, sh + 150), fill=(255, 255, 255) if int(round(r)) % 4 == 0 else (130, 130, 130), width=1)
            d.text((xx + 2, 2), str(int(round(r))), fill=(255, 255, 0), font=font)
        else:
            d.line((xx, sh, xx, sh + 150), fill=(60, 60, 60))
    return out


if len(sys.argv) not in (1, 3):
    raise SystemExit("usage: python music_spec.py [r0 r1]   (both beats, or none for the video plus 8 beats on each side)")
beat_first = np.ceil((0.0 - T.BEAT0) / T.PER - T.M0)                       # timeline beat of the first / last moment of the music
beat_last = np.floor((len(x) / SR - T.BEAT0) / T.PER - T.M0)
if len(sys.argv) == 3:
    r0, r1 = float(sys.argv[1]), float(sys.argv[2])
else:
    r0, r1 = max(np.floor(T.R0) - 8, beat_first), min(np.ceil(T.R1) + 8, beat_last)
if not r1 > r0:
    raise SystemExit("r1 (%g) must be after r0 (%g)" % (r1, r0))
if r1 < beat_first or r0 > beat_last:
    raise SystemExit("beats %g .. %g are outside the music (it covers timeline beats %g .. %g with this BPM / BEAT0 / M0)" % (
        r0, r1, beat_first, beat_last))
starts = np.arange(r0, r1, 26)
for old in glob.glob("spec_*.png"):                                        # pictures of an earlier, longer run would mislead
    os.remove(old)
for i in range(0, len(starts), 2):
    im = Image.new("RGB", (2000, 904), (30, 30, 30))
    for j, s in enumerate(starts[i:i + 2]):
        im.paste(row(float(s), float(s) + 26), (0, 454 * j))
    im.save(f"spec_{i // 2}.png")
n_png = (len(starts) + 1) // 2
print("wrote %s, beats %g .. %g (the music covers %g .. %g)" % (
    "spec_0.png" if n_png == 1 else "spec_0.png .. spec_%d.png" % (n_png - 1), r0, starts[-1] + 26, beat_first, beat_last))
