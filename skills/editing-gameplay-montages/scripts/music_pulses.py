"""For every half beat of the video: how hard does the track hit there? AND: is every event of the timeline ON a measured attack?
  low  = kick / bass hit arriving (the onset of 30 to 140 Hz: a bass guitar that keeps the band loud does not count, only what newly arrives)
  mid  = snare / clap arriving (the onset of the body, 160 to 1500 Hz, together with the crack, 1.5 to 8 kHz: a band's snare buried in
         guitars still shows, a chord or a lone hat does not)
  high = anything bright arriving (above 2.5 kHz: snares, claps and every hat)
each 0..1 (beat_hits.measure_t is the measure: draft_timeline.py and draft_ref_timeline.py use the same numbers).

usage: python music_pulses.py        -> a printed shortlist and the PLACEMENT CHECK; pulses.json [[beat, low, mid, high], ...]
                                        (a record for you; no other script reads it). Exit status 1 when an event is off its attack.

Needs timeline.py with SYNC = 2 (T.HITS: the musical beat of every kill, = hit(t) of a measured attack; scripts/refstyle/
timeline_ref_example.py). The stars mark the kills of whatever SEGS is in the file.

PLACEMENT CHECK (the rule of the SYNC 2 contract: an event belongs to the ATTACK of a drum hit, never to a grid line):
  * every kill (T.HITS, the musical beat the gunshot sounds on),
  * every transition's musical moment s["m0"] when CUTS_ON = "bass": from a KICK (a snare alone does not count),
  * every BUMPS beat and every BOOMS r,
is compared with the attacks measured in the song (beat_hits.attacks: the one definition of an attack time of the skill, accurate to
about 2.5 ms on drums): the time of the event (beat_time) minus the time of the nearest attack, in ms and in frames. More than 8.3 ms
(half a frame) from every attack (for a bass cut: from every kick of strength >= 0.4) = a FAIL and exit status 1. With CUTS_ON =
"kills" the cut moments are information only (a cut between two hits has no attack to sit on: it sits on a line of the song's
sixteenth-note grid, printed). The strength table below it is the old list: kicks, snares, hats-only half beats, kills on a beat
with neither kick nor snare (house style: that list must be empty; reference style: a loud hat may carry a kill)."""
import json
import sys

import numpy as np

import preflight
T, _err = preflight.load()                 # the music block + the SEGS conversion only: no clip checks (they need src/)
if _err:
    sys.exit("music_pulses.py: " + _err)
if getattr(T, "SYNC", 0) < 2 or not hasattr(T, "HITS"):
    sys.exit("music_pulses.py: timeline.py has no SYNC = 2 / HITS: it is written for the old timing (kills on the grid, beat-domain "
             "tolerances). Rebuild it with draft_timeline.py / draft_ref_timeline.py, or copy the SYNC block, hit(), the draft:cut block "
             "and the loop after SEGS (which builds KILLS, HITS and s[\"m0\"]) from timeline_example.py / refstyle/timeline_ref_example.py.")
if getattr(T, "CUTS_ON", "bass") not in ("bass", "kills"):
    raise SystemExit('CUTS_ON = %r in timeline.py is not valid: it must be exactly "bass" (transitions on kicks / 808s, '
                     'the default) or "kills" (transitions with the kill rhythm)' % (T.CUTS_ON,))
import beat_hits

BAR_MS = 8.3                    # half a frame at 60 fps: the most a placed event may be from its attack
KICK_MIN = 0.4                  # a bass cut sits on a kick of at least this strength (what the drafters admit, with their 0.5, less a margin)
FRAME_MS = 1000.0 / T.FPS

m = beat_hits.decode(T.MUSIC)
dur = len(m) / beat_hits.SR
rows, att = beat_hits.measure_t(m, T.BPM, T.BEAT0, T.M0, T.R0, T.R1)        # the one measure, shared with the drafters (half beats)
rows4, att4 = beat_hits.measure_t(m, T.BPM, T.BEAT0, T.M0, T.R0, T.R1, sub=4, tol=1.0, raw=True)   # sixteenths, every attack filed
out_of_music = [r[0] for r in rows if T.beat_time(r[0]) < 0.07 or T.beat_time(r[0]) > dur - 0.05]
if out_of_music:
    print("NOTE: %d half beats lie outside the music (%.1f s long; beats %g .. %g) and read 0: the video is longer than the music or M0 / BEAT0 "
          "are off" % (len(out_of_music), dur, min(out_of_music), max(out_of_music)))
json.dump(rows, open("pulses.json", "w"))
kills = {k for k, lv, i in T.KILLS} | {h for h, lv, i in T.HITS}
mark = lambda r: "%g%s" % (r[0], "*" if r[0] in kills else "")
print("* = a kill of the current SEGS sits there")
print("kicks / bass hits, beat:low  (low >= 0.4):")
print("  " + "  ".join("%s:%.2f" % (mark(r), r[1]) for r in rows if r[1] >= 0.4))
print("snares / claps, beat:mid  (mid >= 0.6):")
print("  " + "  ".join("%s:%.2f" % (mark(r), r[2]) for r in rows if r[2] >= 0.6))
print("half beats with only a hat (high >= 0.5, no kick, no snare): %d of %d" % (
    sum(1 for r in rows if r[3] >= 0.5 and r[1] < 0.4 and r[2] < 0.6), len(rows)))
by_beat = {r[0]: r for r in rows4}
row_of = lambda b: by_beat.get(round(b * 4) / 4.0)
weak = []
for b, lv, i in T.HITS:
    r = row_of(b)
    if r is None or (r[1] < 0.25 and r[2] < 0.4):
        weak.append((round(b, 3), "low %.2f mid %.2f high %.2f" % tuple(r[1:]) if r else "outside the measured window"))
print("kills on a beat with neither kick nor snare:", weak or "none")

# ------------------------------------------------ the placement check: event time against the measured attacks
at = np.array([e[0] for e in att4.all])
ab = [e[1] for e in att4.all]
kick_t = np.array([att4.bands[r[0]]["low"] for r in rows4 if r[1] >= KICK_MIN and "low" in att4.bands.get(r[0], {})])
fails = []


def near(t, arr):
    """(signed ms the event is after the nearest time of arr, that time) or (None, None)"""
    if not len(arr):
        return None, None
    j = int(np.argmin(np.abs(arr - t)))
    return (t - arr[j]) * 1000.0, float(arr[j])


def report(what, label, b, arr, names=None, kick=False):
    t = T.beat_time(b)
    d, tt = near(t, arr)
    if d is None or abs(d) > BAR_MS:
        fails.append(what)
        print("  FAIL %-8s %-16s beat %9.4f  t %8.4f s  %s" % (what, label, b, t, "no %s in the window" % ("kick" if kick else "attack") if d is None else
              "%+.1f ms (%+.2f frames) from the nearest %s (%.4f s): move it onto the attack: hit(%.4f)" % (
                  d, d / FRAME_MS, "kick" if kick else "attack", tt, tt)))
    else:
        print("  ok   %-8s %-16s beat %9.4f  t %8.4f s  %+5.1f ms (%+.2f frames) from the %s at %.4f s%s" % (
            what, label, b, t, d, d / FRAME_MS, "kick" if kick else names[int(np.argmin(np.abs(arr - t)))] + " attack", tt,
            "  [%s]" % ", ".join("%s %.2f" % (k, min(v, 1.0) if k == "high" else v) for k, v in zip(("low", "mid", "high"), (row_of(b) or (0, 0, 0, 0))[1:])) if row_of(b) else ""))


print("PLACEMENT CHECK: each event's time minus its nearest measured attack (limit %.1f ms = half a frame)" % BAR_MS)
for b, lv, i in T.HITS:
    report("kill", "seg %d lv %d" % (i, lv), b, at, ab)
mode = getattr(T, "CUTS_ON", "bass")
cuts = [(s["m0"], s["clip"], j) for j, s in enumerate(T.SEGS[1:], 1) if "m0" in s]
if mode == "bass":
    for b, c, j in cuts:
        report("cut", "seg %d %s" % (j, c), b, kick_t, kick=True)
else:
    print("  (CUTS_ON = \"kills\": %d cut moments, information only)" % len(cuts))
    for b, c, j in cuts:
        t = T.beat_time(b)
        d, tt = near(t, at)
        u = round(b * 4)
        print("  info cut seg %d %-10s beat %9.4f  %s; sixteenth line %+.1f ms" % (
            j, c, b, "%+.1f ms from the nearest attack" % d if d is not None and abs(d) < 60 else "no attack within 60 ms",
            (t - T.beat_time(u / 4.0)) * 1000.0))
for b, w in getattr(T, "BUMPS", []):
    report("bump", "w %.2f" % w, b, at, ab)
for bo in getattr(T, "BOOMS", []):
    report("boom", "gain %.2f" % bo.get("gain", 0.0), bo["r"], at, ab)
n_events = len(T.HITS) + (len(cuts) if mode == "bass" else 0) + len(getattr(T, "BUMPS", [])) + len(getattr(T, "BOOMS", []))
print("%d events checked, %d off their attack by more than %.1f ms%s" % (n_events, len(fails), BAR_MS, "" if not fails else
      ": place them with hit(t) on the times of hits.json (python music_hits.py), and run this again"))
sys.exit(1 if fails else 0)
