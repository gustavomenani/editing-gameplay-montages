"""Lyric cues where the singer sings each word -> lyric_cues.json (loaded by timeline.py into T.TEXT:
[beat in, beat out, "WORD", style]) + the evidence per word (lyrics/cue_audit.json, read by lyrics_audit.py and
lyric_sync_sheet.py).

Input: lyrics.txt (the confirmed words, lyrics_words.py), the isolated vocal stem (lyrics_stem.py) and the forced
alignments of those words on it (lyrics_ctc_align.py: sub-frame runs, exact 20 ms stride; give two, from different
models: their mean is the prior). An alignment made before that change is refused: align again.
Method (lyrics_attack.py holds the definitions and the assignment):
  1. ONE anchor for every word: the sung ATTACK of the stem, the time where its level crosses the middle (in dB) of its
     steepest rise. The cue start of a word is that time; there is NO advance (--adv 0): the only visual lead is the one
     textfx.py draws (first letter HIT_LEAD frames before the cue frame);
  2. the CTC time of a word (mean of the models, each the median of its sub-frame runs) is only a prior: sd ~50 ms, early
     for consonant-initial words, late for fast syllables and for a vowel after a silence. Candidates = the stem's attacks
     (>= 4 dB in 60 ms) within +-0.20 s of the CTC time (+0.025 s, the measured offset); after a silence of the stem
     every attack from the end of the silence on;
  3. the words get their attacks IN ORDER by a dynamic programme (each attack once, >= 50 ms apart) that minimises
     distance-to-prior (heavy tailed) minus attack strength, with a bonus for the first attack after a silence. No hard
     threshold, no window edge that flips: the result follows the audio continuously (stems cut 5 ms apart: same cues);
  4. a word with two almost equal readings is AMBIGUOUS, one with no attack within the window is UNVERIFIED (it keeps the
     CTC time), one whose attack is over 0.10 s from the CTC time is CTC-FAR: all are flagged ("CHECK" below and in
     cue_audit.json), never silently chosen. A flagged word that is wrong is fixed with `word@beat` in lyrics.txt;
  5. a word pinned in lyrics.txt (word@beat) starts at that beat instead;
  6. each word stays while it is sung: until the next shown word, or until the voice stops when a silence follows;
  7. a word that would be on screen under 0.25 beat is shown together with the next one; a cue is never shorter than 0.21 beat (the
     timeline asserts b > a + 0.2: the end cap alone left a 0.19-beat cue on a pair 0.22-0.24 beat apart and the draft refused it);
  8. style: "red" for cues that start inside a --red range (default: the intro, before beat -0.5), otherwise gold, silver
     and white in turn.
Stability: the assignment is repeated on every sub-frame run of the alignment; a word whose cue moves over 8.3 ms between
the runs is listed with the number (an unstable word sits between two attacks).
Words typed `sung=-` take part in the alignment but get no cue. The table prints per word: the chosen beat, the CTC beat
(mean of the models), the difference in ms, how it was chosen (rise in dB), how far the models and the runs were apart and
the flags. The words under "CHECK" are the ones to look at first (lyric_sync_sheet.py zoom panels; lyrics_audit.py).
Cues that start or end outside the timeline's own R0 .. R1 are listed at the end with a WARN: a word pinned or sung past the
section is never (or only partly) drawn there.
Typed words that are not what is sung (a line missing or extra, another wording, T0 inside a sung line) send the two models
to different places: a word whose models are over 0.35 s apart stops the script before anything is written (--force
writes anyway). With one alignment only this cannot be seen: read the sheet.

usage: python cues_from_alignment.py lyrics.txt STEM.wav T0 ALIGN.json [ALIGN2.json ...]
           [--last-end BEAT] [--adv 0] [--red=A:B ...] [--out lyric_cues.json] [--audit-out lyrics/cue_audit.json] [--force]
  T0          song time of the stem's first sample
  --last-end  the last cue ends at most at this timeline beat (e.g. a little before the final, biggest kill)
  --adv       beats a cue is moved EARLIER than the attack (default 0; the visual lead is textfx's HIT_LEAD, not here)
  --red=A:B   beat range whose cues are red (repeatable; write the = because a range may start with a minus sign;
              `--red=none` = no red cue)"""
import argparse
import json
import os
import sys

import numpy as np

import lyrics_attack as LA
import lyrics_words
import timeline as T

if getattr(T, "SYNC", 0) < 2:
    sys.exit("cues_from_alignment.py: timeline.py has no SYNC = 2: it is written for the old timing (words 0.04 beat early, kills on the grid). The "
             "cues of this script are the sung attack with NO advance (textfx.py draws the first letter HIT_LEAD frames before it): "
             "update the project (copy scripts/ then scripts/refstyle/ over it and the SYNC block of timeline_ref_example.py).")

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("words")
ap.add_argument("stem")
ap.add_argument("t0", type=float)
ap.add_argument("align", nargs="+")
ap.add_argument("--last-end", type=float)
ap.add_argument("--adv", type=float, default=0.0)
ap.add_argument("--red", action="append")
ap.add_argument("--out", default="lyric_cues.json")
ap.add_argument("--audit-out")
ap.add_argument("--force", action="store_true")
args = ap.parse_args()
OFF, ADV, LAST_END = args.t0, args.adv, args.last_end
AUDIT = args.audit_out or os.path.join(os.path.dirname(args.stem) or ".", "cue_audit.json")
MIN_CUE = 0.21          # shortest cue the timeline accepts (timeline_ref_example.py: b > a + 0.2); the end cap is 0.04 before the next cue
MERGE = MIN_CUE + 0.04  # a word closer than this to the group's start joins it: 0.25 - 0.04 = MIN_CUE, so no cue can fall between the two rules
R0, R1 = getattr(T, "R0", None), getattr(T, "R1", None)      # the section the timeline draws
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
    if any("s_runs" not in w for w in a):
        sys.exit("cues_from_alignment.py: %s comes from an older lyrics_ctc_align.py (20 ms grid, stride from the stem "
                 "length: up to +20 ms of drift, no sub-frame runs): run lyrics_ctc_align.py again." % p)
if len({len(a[0]["s_runs"]) for a in als}) != 1:
    sys.exit("cues_from_alignment.py: the alignments were made with different --shifts (%s): align again with the same."
             % ", ".join("%s: %d" % (p, len(a[0]["s_runs"])) for p, a in zip(args.align, als)))
N = len(LYR)
S_MODEL = np.array([[w["s"] for w in a] for a in als])                       # (models, words): median over the runs
E_MODEL = np.array([[w["e"] for w in a] for a in als])
S_RUNS = np.array([[w["s_runs"] for w in a] for a in als]).mean(0)           # (words, runs): the models' mean per run
PRIOR, END = S_MODEL.mean(0), E_MODEL.mean(0)
D_MODELS = S_MODEL.max(0) - S_MODEL.min(0)
D_RUNS = np.array([max(w["s_runs"]) - min(w["s_runs"]) for a in als for w in a]).reshape(len(als), N).max(0)

stem = LA.Stem(args.stem, OFF)


def hit(sec):
    return (sec - T.BEAT0) / T.PER - T.M0


def silence_before(prior, i):
    """End (song s) of the silence the aligner puts before word i, or None."""
    prev_e = END[i - 1] if i else prior[i] - 2.0
    gaps = stem.silences(min(prev_e, prior[i] - 0.05), prior[i] + 0.05)
    return gaps[-1][1] if gaps else None


PINS = [T.beat_time(w["pin"]) if w["pin"] is not None else None for w in LYR]
SIL = [silence_before(PRIOR, i) for i in range(N)]
res = LA.assign(stem, PRIOR, SIL, PINS)
# the same assignment on every sub-frame run of the alignment: how far does one word move when the CTC grid phase moves
runs = [LA.assign(stem, S_RUNS[:, k], SIL, PINS) for k in range(S_RUNS.shape[1])]
SPREAD = np.array([max([r[i]["t"] for r in runs] + [res[i]["t"]]) - min([r[i]["t"] for r in runs] + [res[i]["t"]])
                   for i in range(N)])

rows = []
for i, (lw, w) in enumerate(zip(LYR, res)):
    flags, a = [], w["att"]
    if w["kind"] == "pin":
        how = "PINNED at beat %g" % lw["pin"]
        flags.append("pinned")
    elif w["kind"] == "ctc":
        how = "CTC only (no attack within %.2f s)" % LA.WINDOW
        flags.append("unverified")
    else:
        how = "%sattack %.0f dB%s" % ("first " if a["first"] and SIL[i] is not None else "", a["db"], " +note" if a["voiced"] else "")
        if w["g"] < 0.95:
            how = "weak attack %.0f dB (%.0f%%)" % (a["db"], w["g"] * 100)
            flags.append("weak" if w["g"] > 0.05 else "unverified")
        if abs(w["t"] - (PRIOR[i] + LA.MU)) > 0.10:
            flags.append("ctc-far")
    if w["kind"] != "pin":
        if w["margin"] is not None and w["margin"] < LA.AMBIG_MARGIN:
            flags.append("ambiguous")
        if D_MODELS[i] > 0.15:
            flags.append("models-apart")
        if SPREAD[i] > 0.0083:
            flags.append("unstable")
    rows.append(dict(b=hit(w["t"]), t=w["t"], shown=lw["shown"], sung=lw["sung"], ba=hit(PRIOR[i]), e=END[i], how=how,
                     d=float(D_MODELS[i]), dr=float(D_RUNS[i]), spread=float(SPREAD[i]), line=lw["line"], flags=flags,
                     kind=w["kind"], g=w["g"], db=a["db"] if a else None, margin=w["margin"], rival=w["rival"], prior=float(PRIOR[i])))
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
cues, k, notes = [], 0, []
while k < len(shown_rows):
    r = shown_rows[k]
    text, j = r["shown"], k
    while j + 1 < len(shown_rows) and shown_rows[j + 1]["b"] - r["b"] < MERGE:
        j += 1
        text += " " + shown_rows[j]["shown"]
    nxt = shown_rows[j + 1]["b"] if j + 1 < len(shown_rows) else None
    e_last = shown_rows[j]["e"]
    stop = T.beat_time(nxt) if nxt is not None else e_last + 1.0
    sil = stem.silences(e_last - 0.05, stop)
    end_v = hit(sil[0][0]) if sil else hit(stop)
    start = round(r["b"] - ADV, 4)
    if nxt is None:
        end = end_v + 0.10 if LAST_END is None else min(LAST_END, end_v + 0.10)
        if LAST_END is not None and end < start + MIN_CUE:
            notes.append("the last cue would end at %.3f (--last-end %.3f), under the %.2f beat the timeline accepts: it ends at %.3f instead" % (
                end, LAST_END, MIN_CUE, start + MIN_CUE))
    else:
        end = min(nxt - ADV - 0.04, max(end_v + 0.10, r["b"] + 0.35))
    end = round(max(end, start + MIN_CUE), 4)       # never emit a cue the timeline refuses ("word on screen too briefly")
    for q in shown_rows[k:j + 1]:
        q["cue"] = len(cues)
    cues.append([start, end, text])
    k = j + 1
outside = []                                        # words pinned / sung past the section: the timeline draws only R0 .. R1
if isinstance(R0, (int, float)) and isinstance(R1, (int, float)) and R1 > R0:
    for c in cues:
        why = []
        if c[0] < R0 - 1e-9:
            why.append("%.3f beat before R0: its first frames are not drawn" % (R0 - c[0]))
        if c[0] > R1 + 1e-9:
            why.append("%.3f beat after R1: never drawn" % (c[0] - R1))
        if c[1] > R1 + 1e-9:
            why.append("ends %.3f beat after R1: drawn only up to R1" % (c[1] - R1))
        if why:
            outside.append((c, why))
cyc, n_plain = ["gold", "silver", "white"], 0
for c in cues:                                                  # red inside the --red ranges, metallic tints elsewhere
    if any(lo < c[0] < hi for lo, hi in RED):
        c.append("red")
    else:
        c.append(cyc[n_plain % 3])
        n_plain += 1
json.dump(cues, open(args.out, "w", encoding="utf-8"), ensure_ascii=False)

for i, r in enumerate(rows):
    if i and r["b"] - rows[i - 1]["b"] < 0.10:
        r["flags"].append("close-prev")
os.makedirs(os.path.dirname(AUDIT) or ".", exist_ok=True)
json.dump(dict(stem=args.stem, t0=OFF, adv=ADV, mu=LA.MU, cues=args.out, words=[
    dict(word=r["shown"], sung=r["sung"], line=r["line"], cue=r.get("cue"), beat=round(r["b"], 4), t=round(r["t"], 5),
         how=r["how"], kind=r["kind"], g=round(r["g"], 3), db=r["db"], ctc=round(r["prior"], 4), d_models=round(r["d"], 4),
         d_runs=round(r["dr"], 4), spread=round(r["spread"], 5), margin=r["margin"], rival=r["rival"], flags=r["flags"],
         attacks=[dict(t=round(a["t"], 5), db=round(a["db"], 1), voiced=a["voiced"]) for a in stem.att if abs(a["t"] - r["t"]) <= 0.25])
    for r in rows]), open(AUDIT, "w", encoding="utf-8"), indent=1)

print("word         chosen    ctc   (ms)   how   (models / runs apart, ms; moves between runs)   flags")
for r in rows:
    print("%-10s %7.3f %7.3f  %+5.0f   %-26s (%3.0f / %3.0f; %2.0f)  %s%s" % (
        r["shown"] or "(hidden)", r["b"], r["ba"], (r["b"] - r["ba"]) * T.PER * 1000, r["how"], r["d"] * 1000, r["dr"] * 1000,
        r["spread"] * 1000, ",".join(r["flags"]), "   not shown" if r["shown"] is None else ""))
print()
for c in cues:
    print("%7.3f %7.3f  %-10s %s" % tuple(c))
print(len(cues), "cues ->", args.out, "; evidence per word ->", AUDIT)
for n_ in notes:
    print("note:", n_)
if outside:
    print("\nWARN: %d of %d cues lie outside the section the timeline draws (R0 = %g, R1 = %g):" % (len(outside), len(cues), R0, R1))
    for c, why in outside:
        print("  %7.3f %7.3f  %-10s %s" % (c[0], c[1], c[2], "; ".join(why)))
    print("  a word pinned or sung outside R0 .. R1 is never (or only partly) drawn: move the pin into the section, or move R0 / R1")
# the words to look at first on the lyric_sync_sheet.py zoom panels
chk = []
for i, r in enumerate(rows):
    why = []
    if "ambiguous" in r["flags"]:
        why.append("two readings: %.3f beat (rival %+.0f ms, %.2f cost apart)" % (hit(r["rival"]), (r["rival"] - r["t"]) * 1000, r["margin"]))
    if "unverified" in r["flags"]:
        why.append("no real attack within %.2f s of the CTC time: CTC time kept" % LA.WINDOW)
    if "weak" in r["flags"]:
        why.append("only a weak attack (%.0f dB): the cue is between the CTC time and the attack" % r["db"])
    if "ctc-far" in r["flags"]:
        why.append("the attack is %+.0f ms from the CTC time" % ((r["t"] - r["prior"]) * 1000))
    if "models-apart" in r["flags"]:
        why.append("the models are %.0f ms apart" % (r["d"] * 1000))
    if r["spread"] > 0.025:
        why.append("moves %.0f ms between the sub-frame runs" % (r["spread"] * 1000))
    if "close-prev" in r["flags"]:
        why.append("only %.2f beat after the previous word" % (r["b"] - rows[i - 1]["b"]))
    if why:
        chk.append("  line %d  %-10s beat %7.3f: %s" % (r["line"], r["shown"] or "(hidden)", r["b"], "; ".join(why)))
kinds = [r["kind"] for r in rows]
print("\n%d words: %d on an attack, %d CTC only, %d pinned; stability: %d words move over 8.3 ms between the runs, %d over 25 ms"
      % (N, kinds.count("attack"), kinds.count("ctc"), kinds.count("pin"), int((SPREAD > 0.0083).sum()), int((SPREAD > 0.025).sum())))
if chk:
    print("\nCHECK (%d of %d words; `lyrics_audit.py`, then the zoom panels, then `word@beat` in lyrics.txt if one is wrong):" % (len(chk), len(rows)))
    print("\n".join(chk))
else:
    print("\nCHECK: no word stands out (every word on an attack, models within 150 ms, runs stable)")
