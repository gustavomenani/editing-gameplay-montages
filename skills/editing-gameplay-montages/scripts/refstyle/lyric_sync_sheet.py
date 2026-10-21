"""Lyric sync sheets: how to SEE whether the on-screen words follow the voice (the numbers are lyrics_audit.py's).
1. The OVERVIEW sheet: the isolated vocal stem as a spectrogram (100-4000 Hz, low at the bottom, 46 ms window) with its level
   curve (green); a red line where each word of lyric_cues.json APPEARS (label and beat), a blue tick where it leaves; the
   forced-alignment words (yellow tick + span + label, from lyrics_ctc_align.py JSON files); white ticks = the sung attacks
   of lyrics_attack.py (long = confident); beat grid on top. Panels of 6 beats. It reads to ~+-25 ms only (two words of a
   live-band test edit, 157 and 113 ms late, passed it): it shows where a word is, lyrics_audit.py says how far it is.
2. ZOOM panels (--zoom): one panel per word, +-250 ms around the cue, 10 ms STFT window with a 1 ms hop (100-8000 Hz), the
   level curve of the whole stem (green), HF 4-12 kHz (cyan) and LF 100-1500 Hz (orange) level curves, white ticks = attacks
   (label: dB; thick = confident, magenta M = a voiced note starts), yellow ticks = the CTC words' starts (one per model; thin
   = each sub-frame run), the red line = the cue, the dark red dashed line = the frame the first letter is drawn on
   (nearest_frame(cue) - HIT_LEAD) and the 60 fps frame ticks along the bottom (the cue's frame in red). In sync: the red line
   on the left edge of the syllable's energy (the attack), the first-letter line one frame before it.

usage: python lyric_sync_sheet.py STEM.wav T0 [align.json ...] [--cues lyric_cues.json] [--out lyrics/sync]
                                  [--zoom flagged|all|WORD,WORD] [--audit lyrics/cue_audit.json]
                                                           -> lyrics/sync_1.jpg, _2.jpg ... (4 panels each) and, with --zoom,
                                                              lyrics/zoom_1.jpg, _2.jpg ... (6 words each: 2 x 3)
  T0 = song time of the stem's first sample (lyrics/stem.json: the t0 used to cut it)
  --zoom flagged  the words cues_from_alignment.py flagged (ambiguous, weak, unverified, ctc-far, models-apart, unstable)
         all      every word;   WORD,WORD  the named words (shown spelling, e.g. HELLO,WORLD)"""
import argparse
import json
import os
import sys
import warnings

import cv2
import numpy as np
from scipy import signal
from scipy.io import wavfile

import lyrics_attack as LA
import timeline as T

if getattr(T, "SYNC", 0) < 2:
    sys.exit("lyric_sync_sheet.py: timeline.py has no SYNC = 2: it is written for the old timing (words 0.04 beat early, kills on the grid). The "
             "cues of this script are the sung attack with NO advance (textfx.py draws the first letter HIT_LEAD frames before it): "
             "update the project (copy scripts/ then scripts/refstyle/ over it and the SYNC block of timeline_ref_example.py).")

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("stem")
ap.add_argument("t0", type=float)
ap.add_argument("align", nargs="*")
ap.add_argument("--cues", default="lyric_cues.json")
ap.add_argument("--out", default="lyrics/sync")
ap.add_argument("--zoom")
ap.add_argument("--audit")
args = ap.parse_args()
outp, stem_p, OFF = args.out, args.stem, args.t0
os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
with warnings.catch_warnings():                              # soundfile writes a PEAK chunk that scipy skips with a warning
    warnings.simplefilter("ignore", wavfile.WavFileWarning)
    sr, x = wavfile.read(stem_p)
x = x.astype(np.float64)
x = x.mean(1) if x.ndim > 1 else x
stem = LA.Stem(stem_p, OFF)
hop = int(0.005 * sr)
f, t, Z = signal.stft(x, sr, nperseg=2048, noverlap=2048 - hop)
S = 20 * np.log10(np.abs(Z) + 1e-9)
S = S[(f >= 100) & (f <= 4000)]
n = len(x) // hop
db = 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12) + 1e-9)
db = np.maximum(db, db.max() - 60)
tl = (np.arange(n) + 0.5) * hop / sr
cues = [tuple(c) for c in json.load(open(args.cues, encoding="utf-8"))]
als = [json.load(open(p, encoding="utf-8")) for p in args.align]
audit_p = args.audit or os.path.join(os.path.dirname(args.stem) or ".", "cue_audit.json")
side = json.load(open(audit_p, encoding="utf-8")) if os.path.isfile(audit_p) else None
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
    for at_ in stem.att:
        bo = beat_of(at_["t"])
        if b0 <= bo <= b1:
            cv2.line(pan, (X(bo), PH - (22 if at_["g"] >= 0.95 else 10)), (X(bo), PH - 1), (255, 255, 255), 2)
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

# ------------------------------------------------------------------ zoom panels
if args.zoom:
    ZF = ("ambiguous", "weak", "unverified", "ctc-far", "models-apart", "unstable")
    if not side:
        raise SystemExit("lyric_sync_sheet.py: --zoom needs %s (cues_from_alignment.py writes it; --audit PATH)." % audit_p)
    if args.zoom == "all":
        sel = list(side["words"])
    elif args.zoom == "flagged":
        sel = [w for w in side["words"] if any(f in ZF for f in w["flags"])]
    else:
        want = {v.strip().upper() for v in args.zoom.split(",") if v.strip()}
        sel = [w for w in side["words"] if (w["word"] or "").upper() in want]
        miss = want - {(w["word"] or "").upper() for w in sel}
        if miss:
            raise SystemExit("lyric_sync_sheet.py: --zoom words not in %s: %s" % (audit_p, ", ".join(sorted(miss))))
    if not sel:
        print("zoom: no flagged word")
        raise SystemExit(0)
    ZW, ZH, HALF = 900, 300, 0.25
    nfft = int(round(0.010 * sr))
    zh = max(1, int(round(0.001 * sr)))
    zf, zt, ZZ = signal.stft(x, sr, nperseg=nfft, noverlap=nfft - zh, boundary=None, padded=False)
    zt = zt + OFF
    ZS = 20 * np.log10(np.abs(ZZ[(zf >= 100) & (zf <= 8000)]) + 1e-9)
    ZS = np.clip((ZS - (ZS.max() - 75)) / 75.0, 0, 1)

    def band_db(lo_hz, hi_hz):
        sos = signal.butter(4, [lo_hz, hi_hz], "band", fs=sr, output="sos")
        y = signal.sosfilt(sos, x)
        h2 = max(1, int(round(0.002 * sr)))
        m = len(y) // h2
        e = (y[:m * h2].reshape(m, h2) ** 2).mean(1)
        return 10 * np.log10(e + 1e-12), (np.arange(m) + 0.5) * h2 / sr + OFF

    hf_db, hf_t = band_db(4000, 12000)
    lf_db, lf_t = band_db(100, 1500)
    music_t0 = getattr(T, "MUSIC_T0", T.beat_time(getattr(T, "R0", 0.0)))
    fps = getattr(T, "FPS", 60)
    lead = getattr(T, "HIT_LEAD", 1)
    tiles = []
    for w in sel:
        tc = w["t"]
        c0, c1 = tc - HALF, tc + HALF
        i0, i1 = np.searchsorted(zt, c0), np.searchsorted(zt, c1)
        if i1 - i0 < 10:
            continue
        img = (ZS[:, i0:i1][::-1] * 255).astype(np.uint8)
        pan = cv2.applyColorMap(cv2.resize(img, (ZW, ZH), interpolation=cv2.INTER_AREA), cv2.COLORMAP_INFERNO)

        def XZ(s):
            return int(round((s - c0) / (c1 - c0) * (ZW - 1)))

        for dd, tt_, col in ((db, tl + OFF, (80, 255, 80)), (hf_db, hf_t, (255, 255, 0)), (lf_db, lf_t, (60, 160, 255))):
            k0, k1 = np.searchsorted(tt_, c0), np.searchsorted(tt_, c1)
            seg = dd[k0:k1]
            if len(seg) > 1:
                yy = ZH - 1 - np.clip((seg - (dd.max() - 60)) / 60.0, 0, 1) * (ZH - 40)
                pts = np.stack([np.linspace(0, ZW - 1, len(seg)), yy], 1).astype(np.int32)
                cv2.polylines(pan, [pts], False, col, 1, cv2.LINE_AA)
        n_c = int(round((tc - music_t0) * fps))                        # the frame the word is legible on
        for q in range(int(np.floor((c0 - music_t0) * fps)), int(np.ceil((c1 - music_t0) * fps)) + 1):
            xq = XZ(music_t0 + q / fps)
            if 0 <= xq < ZW:
                cv2.line(pan, (xq, ZH - 8), (xq, ZH - 1), (0, 0, 255) if q == n_c else (255, 255, 255), 2 if q == n_c else 1)
        xl = XZ(music_t0 + (n_c - lead) / fps)
        for yy in range(0, ZH, 10):
            cv2.line(pan, (xl, yy), (xl, yy + 4), (60, 60, 190), 1)
        for at_ in w["attacks"]:
            xa = XZ(at_["t"])
            if 0 <= xa < ZW:
                conf = at_["db"] >= LA.CONF or at_.get("voiced")
                cv2.line(pan, (xa, 24), (xa, 44 if conf else 34), (255, 255, 255), 3 if conf else 1)
                cv2.putText(pan, "%.0f%s" % (at_["db"], "M" if at_.get("voiced") else ""), (xa + 2, 56 if conf else 46),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1, cv2.LINE_AA)
        for k_, a in enumerate(als):
            for v in a:
                if v["w"] != w["sung"] or abs(v["s"] - w["ctc"]) > 0.4:
                    continue
                for r_ in v.get("s_runs", []):
                    cv2.line(pan, (XZ(r_), 0), (XZ(r_), 12), YEL[k_ % 2], 1)
                cv2.line(pan, (XZ(v["s"]), 0), (XZ(v["s"]), 22), YEL[k_ % 2], 3)
        cv2.line(pan, (XZ(tc), 0), (XZ(tc), ZH - 1), (40, 40, 255), 2)
        cv2.putText(pan, "%s  beat %.3f  song %.3f s  frame %d  [%s]" % (w["word"], w["beat"], tc, n_c, ",".join(w["flags"])), (6, ZH - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(pan, w["how"], (6, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 255, 200), 1, cv2.LINE_AA)
        for q in range(-5, 6):                                         # 50 ms scale
            cv2.line(pan, (XZ(tc + q * 0.05), ZH - 22), (XZ(tc + q * 0.05), ZH - 16), (200, 200, 200), 1)
        tiles.append(pan)
    per = 6
    for k in range(0, len(tiles), per):
        grp = tiles[k:k + per]
        if len(grp) % 2:
            grp.append(np.zeros_like(grp[0]))
        sheet = np.vstack([np.hstack(grp[i:i + 2]) for i in range(0, len(grp), 2)])
        cv2.imwrite("%s_%d.jpg" % (os.path.join(os.path.dirname(outp) or ".", "zoom"), k // per + 1), sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("zoom: %d words (%s) -> %s_N.jpg" % (len(tiles), args.zoom, os.path.join(os.path.dirname(outp) or ".", "zoom")))
