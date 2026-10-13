"""Lyric cues where the singer sings each word -> lyric_cues.json (loaded by timeline.py into T.TEXT:
[beat in, beat out, "WORD", style]).

Input: lyrics.txt (the confirmed words, lyrics_words.py), the isolated vocal stem (lyrics_stem.py) and the forced
alignments of those words on it (lyrics_ctc_align.py; give two, from different models: their mean is used).
Method:
  1. aligned start = mean of the alignments (two CTC models typically agree within 20-80 ms);
  2. a word that comes after a silence of the stem starts at the first level rise after it (CTC puts the spike of a
     vowel-initial word late inside the vowel: up to half a beat);
  3. otherwise the stem's level rise (>= 7 dB in 60 ms) nearest to the aligned start within -0.12 .. +0.05 s, never one
     that is closer to the previous word's aligned start;
  4. a word pinned in lyrics.txt (word@beat) starts at that beat instead;
  5. each word stays while it is sung: until the next shown word, or until the voice stops when a silence follows;
  6. a word that would be on screen under 0.22 beat is shown together with the next one;
  7. style: "red" for cues that start inside a --red range (default: the intro, before beat -0.5), otherwise gold, silver
     and white in turn.
Words typed `sung=-` take part in the alignment but get no cue. The table prints per word: the chosen beat, the aligned
beat (mean of the models), the difference in ms, how it was chosen and how far the models were apart. The words under
"CHECK" are the ones to look at on lyric_sync_sheet.py first.
Typed words that are not what is sung (a line missing or extra, another wording, T0 inside a sung line) send the two models
to different places: a word whose models are over 0.35 s apart stops the script before anything is written (--force
writes anyway). With one alignment only this cannot be seen: read the sheet.

usage: python cues_from_alignment.py lyrics.txt STEM.wav T0 ALIGN.json [ALIGN2.json ...]
           [--last-end BEAT] [--adv 0.04] [--red=A:B ...] [--out lyric_cues.json] [--force]
  T0          song time of the stem's first sample
  --last-end  the last cue ends at most at this timeline beat (e.g. a little before the final, biggest kill)
  --red=A:B   beat range whose cues are red (repeatable; write the = because a range may start with a minus sign;
              `--red=none` = no red cue)"""
import argparse
import json
import sys
import warnings

import numpy as np
from scipy import signal
from scipy.io import wavfile

import lyrics_words
import timeline as T

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("words")
ap.add_argument("stem")
ap.add_argument("t0", type=float)
ap.add_argument("align", nargs="+")
ap.add_argument("--last-end", type=float)
ap.add_argument("--adv", type=float, default=0.04)
ap.add_argument("--red", action="append")
ap.add_argument("--out", default="lyric_cues.json")
ap.add_argument("--force", action="store_true")
args = ap.parse_args()
OFF, ADV, LAST_END = args.t0, args.adv, args.last_end
if args.red is None:
    RED = [(-1e9, -0.5)]
else:
    RED = [] if args.red == ["none"] else [tuple(float(v) for v in r.split(":")) for r in args.red]

LYR = lyrics_words.parse(args.words)
als = [json.load(open(p, encoding="utf-8")) for p in args.align]
for p, a in zip(args.align, als):
    if [w["w"] for w in a] != [w["sung"] for w in LYR]:
        sys.exit("cues_from_alignment.py: %s was aligned for other words than %s holds: run lyrics_ctc_align.py again "
                 "(%d words in the alignment, %d in the text)." % (p, args.words, len(a), len(LYR)))
al = [dict(w=ws[0]["w"], s=float(np.mean([w["s"] for w in ws])), e=float(np.mean([w["e"] for w in ws])),
           d=(max(w["s"] for w in ws) - min(w["s"] for w in ws))) for ws in zip(*als)]

with warnings.catch_warnings():                              # soundfile writes a PEAK chunk that scipy skips with a warning
    warnings.simplefilter("ignore", wavfile.WavFileWarning)
    sr, x = wavfile.read(args.stem)
x = x.astype(np.float64)
x = x.mean(1) if x.ndim > 1 else x
hop = int(0.005 * sr)
n = len(x) // hop
db = 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-12) + 1e-9)
db = np.maximum(db, db.max() - 60)
ts = (np.arange(n) + 0.5) * hop / sr + OFF                      # song seconds of each 5 ms level value
rise = np.zeros(n)
rise[:-12] = db[12:] - db[:-12]
pk, _ = signal.find_peaks(rise, height=7.0, distance=16)
ons = []
for p in pk:
    mid = (db[p] + db[min(n - 1, p + 12)]) / 2
    j = p
    while j < min(n - 1, p + 12) and db[j] < mid:
        j += 1
    ons.append(ts[j])
voiced = db > np.percentile(db, 95) - 20                       # 20 dB under the singing level = silent


def silences(a, b, need=0.12):
    """Silences of at least `need` s between song times a and b: [(start, end), ...]."""
    out, k, i1 = [], np.searchsorted(ts, a), np.searchsorted(ts, b)
    while k < i1:
        if not voiced[k]:
            k2 = k
            while k2 < i1 and not voiced[k2]:
                k2 += 1
            if ts[min(k2, n - 1)] - ts[k] >= need:
                out.append((ts[k], ts[min(k2, n - 1)]))
            k = k2
        else:
            k += 1
    return out


def hit(sec):
    return (sec - T.BEAT0) / T.PER - T.M0


rows = []
for i, (lw, w) in enumerate(zip(LYR, al)):
    s, how = w["s"], "aligned"
    prev_e = al[i - 1]["e"] if i else s - 2.0
    gaps = silences(min(prev_e, s - 0.05), s + 0.05)
    if gaps:
        after = [o for o in ons if gaps[-1][1] - 0.06 <= o <= s + 0.05]
        if after:
            s, how = after[0], "first rise after the silence %.2f-%.2f" % (hit(gaps[-1][0]), hit(gaps[-1][1]))
    if how == "aligned":
        lo = max(-0.12, (al[i - 1]["s"] - s) / 2) if i else -0.12
        near = [o for o in ons if lo <= o - s <= 0.05]
        if near:
            s2 = min(near, key=lambda o: abs(o - s))
            s, how = s2, "rise %+.0f ms" % ((s2 - w["s"]) * 1000)
    b = hit(s)
    if lw["pin"] is not None:
        b, how = lw["pin"], "PINNED at beat %g" % lw["pin"]
    rows.append(dict(b=b, shown=lw["shown"], ba=hit(w["s"]), e=w["e"], how=how, d=w["d"], line=lw["line"]))
shown_rows = [r for r in rows if r["shown"] is not None]
if len(als) > 1 and not args.force:
    lost = [r for r in rows if r["d"] > 0.35]
    if lost:
        sys.exit("cues_from_alignment.py: the typed words do not match the singing near: %s.\nThe two models put these words "
                 "over 0.35 s apart. Compare lines %s of %s with the voice (a line missing or extra, another wording, a "
                 "section that starts inside a sung line); fix the text or the section and align again. --force writes the "
                 "cues anyway."
                 % ("; ".join("line %d %s (%.1f s apart)" % (r["line"], r["shown"] or "(hidden)", r["d"]) for r in lost[:6]),
                    sorted({r["line"] for r in lost})[:6], args.words))
if not shown_rows:
    sys.exit("cues_from_alignment.py: every word of %s is marked as not shown (sung=-)." % args.words)
cues, k = [], 0
while k < len(shown_rows):
    r = shown_rows[k]
    text, j = r["shown"], k
    while j + 1 < len(shown_rows) and shown_rows[j + 1]["b"] - r["b"] < 0.22:
        j += 1
        text += " " + shown_rows[j]["shown"]
    nxt = shown_rows[j + 1]["b"] if j + 1 < len(shown_rows) else None
    e_last = shown_rows[j]["e"]
    stop = T.beat_time(nxt) if nxt is not None else e_last + 1.0
    sil = silences(e_last - 0.05, stop)
    end_v = hit(sil[0][0]) if sil else hit(stop)
    if nxt is None:
        end = end_v + 0.10 if LAST_END is None else min(LAST_END, end_v + 0.10)
    else:
        end = min(nxt - ADV - 0.04, max(end_v + 0.10, r["b"] + 0.35))
    cues.append([round(r["b"] - ADV, 3), round(end, 3), text])
    k = j + 1
cyc, n_plain = ["gold", "silver", "white"], 0
for c in cues:                                                  # red inside the --red ranges, metallic tints elsewhere
    if any(lo < c[0] < hi for lo, hi in RED):
        c.append("red")
    else:
        c.append(cyc[n_plain % 3])
        n_plain += 1
json.dump(cues, open(args.out, "w", encoding="utf-8"), ensure_ascii=False)

print("word         chosen  aligned  (ms)   how   (alignments differ)")
for r in rows:
    print("%-10s %7.2f %8.2f  %+5.0f   %s   (%.0f ms)%s" % (r["shown"] or "(hidden)", r["b"], r["ba"], (r["b"] - r["ba"]) * T.PER * 1000,
                                                       r["how"], r["d"] * 1000, "   not shown" if r["shown"] is None else ""))
print()
for c in cues:
    print("%7.2f %7.2f  %-10s %s" % tuple(c))
print(len(cues), "cues ->", args.out)
# the words to look at first on lyric_sync_sheet.py
chk = []
for i, r in enumerate(rows):
    why = []
    if len(als) > 1 and r["d"] > 0.15:
        why.append("the models are %.0f ms apart" % (r["d"] * 1000))
    if abs(r["b"] - r["ba"]) * T.PER > 0.12 and "PINNED" not in r["how"]:
        why.append("moved %+.0f ms from the alignment" % ((r["b"] - r["ba"]) * T.PER * 1000))
    if i and r["b"] - rows[i - 1]["b"] < 0.10:
        why.append("only %.2f beat after the previous word" % (r["b"] - rows[i - 1]["b"]))
    if why:
        chk.append("  line %d  %-10s beat %7.2f: %s" % (r["line"], r["shown"] or "(hidden)", r["b"], "; ".join(why)))
if chk:
    print("\nCHECK (%d of %d words):" % (len(chk), len(rows)))
    print("\n".join(chk))
else:
    print("\nCHECK: no word stands out (models within 150 ms, none moved over 120 ms)")
