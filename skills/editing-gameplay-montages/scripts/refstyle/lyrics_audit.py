"""Numeric audit of the lyric cues: every cue start against the sung ATTACK measured on the vocal stem, in milliseconds.
Nothing here uses the CTC models: the stem is measured again (lyrics_attack.py: the one definition of an attack) and the cues
of lyric_cues.json are compared with it, so a cue that was hand-edited, pinned, or placed by an older script is checked too.
Before this check the only test of the words was a picture (lyric_sync_sheet.py) good to ~25 ms; two words of a
live-band test edit were 157 and 113 ms late and passed it.

usage: python lyrics_audit.py [--cues lyric_cues.json] [--dir lyrics] [--tol 25]       (run in the project folder)
  --dir   holds vocals.wav, stem.json (T0 = song time of the stem's first sample) and cue_audit.json (what
          cues_from_alignment.py wrote: the flag of each word; without it every word is judged without flags)
  --tol   ms: how far a cue may sit from a confident attack (default 25 ms = 1.5 frames at 60 fps)
Per cue (first word of a merged cue) the table prints: the cue beat and song time, the NEAREST CONFIDENT attack (a rise of
>= 8 dB in 60 ms, or any rise that starts a voiced note) within +-0.25 s as `cue - attack` in ms (+ = the word shows LATE,
- = EARLY) with its dB, the same for the nearest attack of any strength, the CTC time, and a verdict:
  ok          within --tol of a confident attack
  LATE/EARLY  further than --tol from the nearest confident attack and no flag explains it            -> ERROR
  flagged     further than --tol but cues_from_alignment.py flagged the word (ambiguous / unverified / weak / pinned): WARN,
              look at the zoom panel (lyric_sync_sheet.py --zoom) and pin the word with `word@beat` if it is wrong
  no-attack   no confident attack within 0.25 s (legato syllable, hum): WARN
  stale       the cue start differs from lyrics/cue_audit.json by > 0.3 ms: the cues were edited after the table was made
Also listed: words that move > 8.3 ms between the sub-frame runs of the alignment (WARN) and the stability numbers of the
sidecar. Exit code 1 when there is an ERROR (a cue not on an attack and not flagged), 0 otherwise."""
import argparse
import json
import os
import sys

import numpy as np

import lyrics_attack as LA
import timeline as T

if getattr(T, "SYNC", 0) < 2:
    sys.exit("lyrics_audit.py: timeline.py has no SYNC = 2: it is written for the old timing (words 0.04 beat early, kills on the grid). The "
             "cues of this script are the sung attack with NO advance (textfx.py draws the first letter HIT_LEAD frames before it): "
             "update the project (copy scripts/ then scripts/refstyle/ over it and the SYNC block of timeline_ref_example.py).")

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("--cues", default="lyric_cues.json")
ap.add_argument("--dir", default="lyrics")
ap.add_argument("--tol", type=float, default=25.0)
args = ap.parse_args()
TOL = args.tol / 1000.0
FAR = 0.25                                                   # s: attacks further than this from a cue are not its attacks

vocals = os.path.join(args.dir, "vocals.wav")
side_p, stem_p = os.path.join(args.dir, "cue_audit.json"), os.path.join(args.dir, "stem.json")
if not os.path.isfile(args.cues):
    sys.exit("lyrics_audit.py: %s is missing: run lyrics_sync.py (or cues_from_alignment.py) first." % args.cues)
if not os.path.isfile(vocals):
    sys.exit("lyrics_audit.py: %s is missing: run lyrics_stem.py first (lyrics_sync.py does)." % vocals)
side = json.load(open(side_p, encoding="utf-8")) if os.path.isfile(side_p) else None
if os.path.isfile(stem_p):
    t0 = float(json.load(open(stem_p))["t0"])
elif side:
    t0 = float(side["t0"])
else:
    sys.exit("lyrics_audit.py: %s is missing, T0 of the stem is unknown." % stem_p)
cues = json.load(open(args.cues, encoding="utf-8"))
stem = LA.Stem(vocals, t0)
at = np.array([a["t"] for a in stem.att])
conf = np.array([a["g"] >= 0.95 for a in stem.att], dtype=bool)          # >= ~7.5 dB, or a voiced note starts there
adv = side["adv"] if side else 0.0
first_word = {}                                              # cue index -> the first word record of the sidecar
if side:
    for w in side["words"]:
        if w["cue"] is not None and w["cue"] not in first_word:
            first_word[w["cue"]] = w

err, warn, rows = [], [], []
print("cue beat   song s   | nearest CONFIDENT attack  | nearest any attack | CTC    | verdict")
print("                     |  cue-attack (ms)   dB     |  cue-attack (ms)   |        |")
for k, c in enumerate(cues):
    a_beat, text = c[0], c[2]
    t_cue = T.beat_time(a_beat + adv)                        # the intended anchor: the cue plus the advance it was made with
    w = first_word.get(k)
    flags = set(w["flags"]) if w else set()
    stale = bool(w) and abs((w["beat"] - adv) - a_beat) * T.PER > 0.0003
    d_all = at - t_cue
    d_conf = np.where(conf, d_all, np.inf)
    i_all = int(np.argmin(np.abs(d_all))) if len(at) else -1
    i_conf = int(np.argmin(np.abs(d_conf))) if conf.any() else -1
    near = i_conf >= 0 and abs(d_conf[i_conf]) <= FAR
    verdict, note = "ok", ""
    if not near:
        verdict, note = "no-attack", "no confident attack within %.2f s" % FAR
        warn.append((text, a_beat, note))
    else:
        dc = -d_conf[i_conf]                                 # cue - attack
        if abs(dc) > TOL:
            why = [f for f in ("ambiguous", "unverified", "weak", "pinned", "ctc-far") if f in flags]
            kind = "LATE" if dc > 0 else "EARLY"
            if why:
                verdict, note = "flagged", "%s by %+.0f ms to the nearest confident attack; flagged: %s" % (kind, dc * 1000, ",".join(why))
                warn.append((text, a_beat, note))
            else:
                verdict, note = kind, "%+.0f ms from the nearest confident attack (%.1f dB) and no flag" % (dc * 1000, stem.att[i_conf]["db"])
                err.append((text, a_beat, note))
    if stale:
        warn.append((text, a_beat, "stale: the cue start is %+.2f ms from cue_audit.json (edited after the table was made)"
                     % ((a_beat - (w["beat"] - adv)) * T.PER * 1000)))
        verdict = verdict if verdict not in ("ok",) else "stale"
    if w and w.get("spread", 0) > 0.0083:
        warn.append((text, a_beat, "moves %.0f ms between the sub-frame runs of the alignment" % (w["spread"] * 1000)))
    ctc = ("%+5.0f ms" % ((t_cue - w["ctc"]) * 1000)) if w else "   -    "
    print("%7.3f %9.3f | %+8.1f   %5s  %-7s | %+8.1f           | %s | %-9s %s %s" % (
        a_beat, t_cue, -d_conf[i_conf] * 1000 if near else float("nan"),
        ("%.1f" % stem.att[i_conf]["db"]) if near else "-", "(note)" if near and stem.att[i_conf]["voiced"] else "",
        -d_all[i_all] * 1000 if i_all >= 0 and abs(d_all[i_all]) <= FAR else float("nan"), ctc, verdict, text,
        ("[" + ",".join(sorted(flags)) + "]") if flags else ""))
    rows.append(dict(text=text, beat=a_beat, verdict=verdict, delta=None if not near else -d_conf[i_conf] * 1000))

dev = np.array([abs(r["delta"]) for r in rows if r["delta"] is not None])
print()
if len(dev):
    print("%d cues: %d within %.0f ms of a confident attack (median |cue - attack| %.1f ms, 90 %% within %.1f ms, max %.1f ms); "
          "%d without a confident attack nearby" % (len(rows), int((dev <= args.tol).sum()), args.tol, np.median(dev),
                                                    np.percentile(dev, 90), dev.max(), len(rows) - len(dev)))
if side:
    sp = np.array([w["spread"] for w in side["words"] if w["kind"] != "pin"])
    if len(sp):
        print("stability over the sub-frame runs: %d of %d words move over 8.3 ms (max %.0f ms)" % ((sp > 0.0083).sum(), len(sp), sp.max() * 1000))
else:
    print("(no %s: the cues are judged without cues_from_alignment.py's flags and stability numbers)" % side_p)
if warn:
    print("\nWARN (%d): look at these on the zoom panels (lyric_sync_sheet.py --zoom flagged), `word@beat` in lyrics.txt fixes one:" % len(warn))
    for text, b, note in warn:
        print("  %-10s beat %7.3f: %s" % (text, b, note))
if err:
    print("\nERROR (%d): cues that are not on a sung attack:" % len(err))
    for text, b, note in err:
        print("  %-10s beat %7.3f: %s" % (text, b, note))
    sys.exit(1)
print("\nlyrics audit: no ERROR")
