"""Lyric sync sheet: how to SEE whether the on-screen words follow the voice. The isolated vocal stem as a spectrogram
(100-4000 Hz, low at the bottom) with its level curve (green); a red line where each word of lyric_cues.json APPEARS
(label and beat), a blue tick where it leaves; the forced-alignment words (yellow tick + span + label, from
lyrics_ctc_align.py JSON files); white ticks = level rises of the stem; beat grid on top. Panels of 6 beats.
In sync: every red line sits on the left edge of its syllable (after a dip = a consonant, or where the voice returns
after a silence) and under its yellow label. Words placed from whisper's word times have failed this visibly (a word
shown in silence, every word of a line one word early); words from cues_from_alignment.py passed.

usage: python lyric_sync_sheet.py STEM.wav T0 [align.json ...] [--cues lyric_cues.json] [--out lyrics/sync]
                                                                            -> lyrics/sync_1.jpg, _2.jpg ... (4 panels each)
  T0 = song time of the stem's first sample (lyrics/stem.json: the -ss used to cut it)"""
import argparse
import json
import os
import warnings
import numpy as np
import cv2
from scipy import signal
from scipy.io import wavfile
import timeline as T

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("stem")
ap.add_argument("t0", type=float)
ap.add_argument("align", nargs="*")
ap.add_argument("--cues", default="lyric_cues.json")
ap.add_argument("--out", default="lyrics/sync")
args = ap.parse_args()
outp, stem, OFF = args.out, args.stem, args.t0
os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
with warnings.catch_warnings():                              # soundfile writes a PEAK chunk that scipy skips with a warning
    warnings.simplefilter("ignore", wavfile.WavFileWarning)
    sr, x = wavfile.read(stem)
x = x.astype(np.float64)
x = x.mean(1) if x.ndim > 1 else x
hop = int(0.005 * sr)
f, t, Z = signal.stft(x, sr, nperseg=2048, noverlap=2048 - hop)
S = 20 * np.log10(np.abs(Z) + 1e-9)
S = S[(f >= 100) & (f <= 4000)]
n = len(x) // hop
db = 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12) + 1e-9)
db = np.maximum(db, db.max() - 60)
tl = (np.arange(n) + 0.5) * hop / sr
rise = np.zeros(n)
rise[:-12] = db[12:] - db[:-12]
pk, _ = signal.find_peaks(rise, height=7.0, distance=16)
ons = []
for p in pk:
    mid = (db[p] + db[min(n - 1, p + 12)]) / 2
    j = p
    while j < min(n - 1, p + 12) and db[j] < mid:
        j += 1
    ons.append(tl[j] + OFF)
cues = [tuple(c) for c in json.load(open(args.cues, encoding="utf-8"))]
als = [json.load(open(p, encoding="utf-8")) for p in args.align]
YEL = [(0, 230, 255), (0, 160, 255)]


def beat_of(sec):
    return (sec - T.BEAT0) / T.PER - T.M0


lo = min([c[0] for c in cues] + [beat_of(w["s"]) for a in als for w in a]) - 0.5
hi = max([c[1] for c in cues] + [beat_of(w["e"]) for a in als for w in a]) + 0.5
PW, PH, WIN = 1900, 230, 6.0
panels = []
for b0 in np.arange(np.floor(lo), hi, WIN):
    b1 = b0 + WIN
    t0, t1 = T.beat_time(b0) - OFF, T.beat_time(b1) - OFF
    if t1 <= 0 or t0 >= t[-1]:
        continue
    img = S[:, np.searchsorted(t, t0):np.searchsorted(t, t1)]
    img = np.clip((img - (S.max() - 70)) / 70.0, 0, 1)[::-1]
    pan = cv2.cvtColor(cv2.resize((img * 255).astype(np.uint8), (PW, PH), interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)

    def X(b):
        return int(round((b - b0) / (b1 - b0) * (PW - 1)))

    for q in np.arange(np.ceil(b0 * 4) / 4, b1, 0.25):
        cv2.line(pan, (X(q), 0), (X(q), 10), (160, 160, 160) if abs(q - round(q)) < 1e-6 else (90, 90, 90), 1)
    l = db[np.searchsorted(tl, t0):np.searchsorted(tl, t1)]
    if len(l) > 1:
        pts = np.stack([np.linspace(0, PW - 1, len(l)), PH - 1 - np.clip((l - (db.max() - 50)) / 50.0, 0, 1) * (PH - 30)], 1)
        cv2.polylines(pan, [pts.astype(np.int32)], False, (60, 220, 60), 1, cv2.LINE_AA)
    for k, a in enumerate(als):
        for w in a:
            bs, be = beat_of(w["s"]), beat_of(w["e"])
            if be >= b0 and bs <= b1:
                y = PH - 44 - 16 * k
                cv2.line(pan, (X(bs), 0), (X(bs), 22), YEL[k % 2], 2)
                cv2.line(pan, (X(bs), y), (X(max(bs, min(be, b1))), y), YEL[k % 2], 2)
                cv2.putText(pan, w["w"], (X(bs) + 3, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, YEL[k % 2], 1, cv2.LINE_AA)
    for o in ons:
        if b0 <= beat_of(o) <= b1:
            cv2.line(pan, (X(beat_of(o)), PH - 22), (X(beat_of(o)), PH - 1), (255, 255, 255), 2)
    for a, b, wd, st in cues:
        if b >= b0 and a <= b1:
            cv2.line(pan, (X(a), 0), (X(a), PH - 1), (40, 40, 255), 2)
            cv2.line(pan, (X(b), PH - 30), (X(b), PH - 1), (255, 140, 40), 2)
            cv2.putText(pan, wd, (X(a) + 4, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (40, 40, 255), 2, cv2.LINE_AA)
            cv2.putText(pan, "%.2f" % a, (X(a) + 4, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 255), 1, cv2.LINE_AA)
    cv2.putText(pan, "beats %.2f .. %.2f" % (b0, b1), (PW - 230, PH - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
    panels.append(pan)
for k in range(0, len(panels), 4):
    sheet = np.vstack([np.vstack([p, np.zeros((6, PW, 3), np.uint8)]) for p in panels[k:k + 4]])
    cv2.imwrite("%s_%d.jpg" % (outp, k // 4 + 1), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
print(len(panels), "panels ->", outp + "_N.jpg")
