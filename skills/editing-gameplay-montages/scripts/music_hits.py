"""The measured drum hits of a stretch of the song, each with its own TIME: hits.json, and a table.

usage: python music_hits.py                         the music block of timeline.py: MUSIC, BPM, BEAT0, M0, R0, R1 (+ 3 s each side)
       python music_hits.py R0 R1                   another stretch (timeline beats)
       python music_hits.py --music src/music.flac --bpm 95 --beat0 0.32 --m0 0 --r0 0 --r1 60     no timeline.py needed
       options: -o hits.json   --all (also the faint hits)   --sub 4 (lattice the hit is filed on, 2 or 4)
       -> hits.json, and from Python:  load("hits.json"), nearest(hits, t), table(m, bpm, beat0, m0, r0, r1)

Why this exists: a kill, a cut, a bump, a boom, a riser's end and a word belong to the ATTACK of a drum hit (or a sung onset),
a time in the song, never to a grid line (a live drummer, a swung or syncopated hit, a grid a few ms off are all met that way).
timeline.py turns a time into its beat with  hit(t) = (t - BEAT0) / PER - M0  (the "r" of every hit below, 9 decimals), and
every consumer (the drafters, music_pulses.py, the gate) uses the same attack measure (beat_hits.py: ONE definition, the half
height of the band's linear envelope across its steepest 6 ms rise, minus the class bias measured on synthetic truth).

hits.json:
  {"music", "sr", "definition", "bias_ms": {"low", "mid", "high", "808"}, "bpm", "beat0", "m0", "r0", "r1", "sub",
   "hits": [{"t", "r", "band", "low", "mid", "high", "u4", "dt_ms", "tl", "tm", "th"}, ...]}
  t      the attack, TRACK seconds (rounded to 1 us);  r = hit(t)
  band   the strongest class of the hit: "low" (kick / 808 / bass hit), "mid" (snare / clap: body and crack arriving), "high" (hat)
  low / mid / high   unclipped strengths (beat_hits' scale: a kick is 0.5 at its weakest that a drafter takes). low and mid have no
                     upper bound (a hit stronger than the song's 99th-percentile onset is above 1), high is capped at 2.0 (from there
                     on the class pick already saturates on "clearly a hat")
  u4     the nearest sixteenth-note line of the grid (timeline beat * 4), dt_ms = t - that line (grid time) in ms: ORIENTATION ONLY
  tl / tm / th   the attack time of each class that has a strength there (null when the class has none): a bass cut uses "tl"
A hit is listed from low 0.25, mid 0.4 or high 0.5 (what music_pulses.py calls weak; --all lists every attack that carries a
strength). Accuracy of "t" (synthetic songs, sample-exact truth; the same on a wandering or tempo-changing song, no grid is assumed):
kick -0.3 / +0.6 / +1.5 ms mean for a 2 / 3 / 5 ms attack ramp (max |error| 2.0 / 2.4 / 3.3; an instant-onset kick -2.0), snare
+0.1 (max 0.3), hat +0.3 (max 0.5); an 808 sine (no click) reads 4.4 ms late of its true start, std 3.2, max 11 (a sound without a
click has no sharper start): bias_ms in the file is what was subtracted per band, "808" what is left of it for that kind. Real songs
have no truth: these are the limits of the method, measured on numpy songs."""
import argparse
import json
import os
import sys

import numpy as np

import beat_hits as bh

LIST_MIN = {"low": 0.25, "mid": 0.4, "high": 0.5}      # strengths from which a hit is listed (music_pulses.py's "weak" lines)


def table(m, bpm, beat0, m0, r0, r1, sub=4, every=False):
    """The hits of timeline beats r0 .. r1 -> (hits, rows, att): hits = the list of dicts of hits.json (sorted by time), rows / att =
    beat_hits.measure_t's (raw strengths, sub-lattice, every attack filed on its nearest lattice line)."""
    per = 60.0 / bpm
    rows, att = bh.measure_t(m, bpm, beat0, m0, r0, r1, raw=True, sub=sub, tol=1.0)
    hits = []
    for r, lo, mi, hi in rows:
        if r not in att:
            continue
        s = {"low": lo, "mid": mi, "high": hi}
        if not every and not any(s[k] >= LIST_MIN[k] for k in s):
            continue
        t, band = att[r]
        tb = att.bands[r]
        grid = beat0 + (m0 + r) * per
        hits.append({"t": round(t, 6), "r": round((t - beat0) / per - m0, 9), "band": band, "low": lo, "mid": mi, "high": hi,
                     "u4": int(round(r * 4)), "dt_ms": round((t - grid) * 1000, 2),
                     "tl": round(tb["low"], 6) if "low" in tb else None, "tm": round(tb["mid"], 6) if "mid" in tb else None,
                     "th": round(tb["high"], 6) if "high" in tb else None})
    hits.sort(key=lambda h: h["t"])
    return hits, rows, att


def write(path, music, bpm, beat0, m0, r0, r1, sub, hits):
    doc = {"music": music, "sr": bh.SR, "definition": bh.DEFINITION,
           "bias_ms": {"low": bh.BIAS_MS["low"], "mid": bh.BIAS_MS["mid"], "high": bh.BIAS_MS["high"], "808": bh.BIAS_808_MS},
           "bpm": bpm, "beat0": beat0, "m0": m0, "r0": r0, "r1": r1, "sub": sub, "hits": hits}
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)


def load(path="hits.json"):
    """hits.json -> the dict written by write() (its "hits" list is sorted by time)"""
    with open(path) as f:
        return json.load(f)


def nearest(hits, t, band=None):
    """The hit of `hits` (list of dicts) nearest to song time t, with the attack time of `band` ("low" / "mid" / "high": its
    "tl" / "tm" / "th", hits without that class skipped) or of the hit itself -> (hit, time, ms of t after it); None when empty."""
    best = None
    for h in hits:
        tt = h["t"] if band is None else h.get({"low": "tl", "mid": "tm", "high": "th"}[band])
        if tt is None:
            continue
        if best is None or abs(t - tt) < abs(t - best[1]):
            best = (h, tt)
    return None if best is None else (best[0], best[1], (t - best[1]) * 1000.0)


def main():
    ap = argparse.ArgumentParser(description="measured drum hits with their attack times -> hits.json")
    ap.add_argument("range", nargs="*", type=float, help="R0 R1: timeline beats (default: R0 .. R1 of timeline.py)")
    ap.add_argument("--music"), ap.add_argument("--bpm", type=float), ap.add_argument("--beat0", type=float)
    ap.add_argument("--m0", type=int), ap.add_argument("--r0", type=float), ap.add_argument("--r1", type=float)
    ap.add_argument("--sub", type=int, default=4, choices=(2, 4))
    ap.add_argument("--all", action="store_true"), ap.add_argument("-o", default="hits.json")
    a = ap.parse_args()
    T = None
    if os.path.exists("timeline.py") and not (a.music and a.bpm and a.beat0 is not None):
        import timeline as T
        import preflight
        if getattr(T, "SYNC", 0) < preflight.SYNC_NEEDED:
            sys.exit("music_hits.py: " + preflight.sync_update_message(getattr(T, "SYNC", 0)) + "  (or give --music --bpm --beat0 --r0 --r1 and no timeline.py is read)")
    music = a.music or (T.MUSIC if T else None)
    bpm = a.bpm or (T.BPM if T else None)
    beat0 = a.beat0 if a.beat0 is not None else (T.BEAT0 if T else None)
    m0 = a.m0 if a.m0 is not None else (T.M0 if T else 0)
    if len(a.range) == 2:
        r0, r1 = a.range
    elif a.range:
        raise SystemExit("usage: python music_hits.py [R0 R1]  (two beats, or none)")
    else:
        r0 = a.r0 if a.r0 is not None else (T.R0 if T else None)
        r1 = a.r1 if a.r1 is not None else (T.R1 if T else None)
    if None in (music, bpm, beat0, r0, r1):
        raise SystemExit("no timeline.py here and not enough options: need --music, --bpm, --beat0, --r0 and --r1 (--m0 default 0)")
    m = bh.decode(music)
    hits, rows, att = table(m, bpm, beat0, m0, r0, r1, a.sub, a.all)
    write(a.o, music, bpm, beat0, m0, r0, r1, a.sub, hits)
    per = 60.0 / bpm
    print("hits of beats %g .. %g (%.2f .. %.2f s of %s; BPM %g BEAT0 %.4f M0 %d)  -> %s: %d hits" % (
        r0, r1, beat0 + (m0 + r0) * per, beat0 + (m0 + r1) * per, music, bpm, beat0, m0, a.o, len(hits)))
    print("attack time = %s" % bh.DEFINITION)
    print("%9s %10s %5s %6s %6s %6s %6s %8s" % ("beat r", "t (s)", "band", "low", "mid", "high", "u4", "dt_ms"))
    for h in hits:
        print("%9.4f %10.4f %5s %6.2f %6.2f %6.2f %6d %+8.1f" % (h["r"], h["t"], h["band"], h["low"], h["mid"], h["high"], h["u4"], h["dt_ms"]))
    dt = np.array([h["dt_ms"] for h in hits if max(h["low"] / bh.HIT_LOW, h["mid"] / bh.HIT_MID) >= 1.0])
    if len(dt):
        print("strong kicks / snares (%d): attack minus the %g-BPM grid, ms: median %+.1f, MAD %.1f, %.0f %% beyond 8.3 ms  "
              "(a constant grid is only adequate when this is under 5 %%: place on the times above, hit(t))" % (
                  len(dt), bpm, np.median(dt), 1.4826 * np.median(np.abs(dt - np.median(dt))), 100.0 * np.mean(np.abs(dt) > 8.3)))


if __name__ == "__main__":
    main()
