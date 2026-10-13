"""For every half beat of the video: how hard does the track hit exactly on the grid?
  low  = kick / bass hit arriving (the onset of 30 to 140 Hz: a bass guitar that keeps the band loud does not count, only what newly arrives)
  mid  = snare / clap arriving (the onset of the body, 160 to 1500 Hz, together with the crack, 1.5 to 8 kHz: a band's snare buried in
         guitars still shows, a chord or a lone hat does not)
  high = anything bright arriving (above 2.5 kHz: snares, claps and every hat)
each 0..1 (beat_hits.py is the measure: draft_timeline.py and draft_ref_timeline.py use the same numbers).

usage: python music_pulses.py        -> a printed shortlist, and pulses.json [[beat, low, mid, high], ...]
                                        (a record for you; no other script reads it)

Needs only the music block of timeline.py (MUSIC, BPM, BEAT0, M0, R0, R1); the stars mark the kills of
whatever SEGS is in the file, so ignore them until the segments are yours.
Use it to (1) put every kill on a kick or a snare, never on an empty beat or a bare hat (reference style:
a loud hat may carry a level-1 kill, see reference-style.md), (2) with CUTS_ON = "bass" in timeline.py (the
default), put every transition on a kick / bass hit, never on a snare alone; with "kills" the list is only
information, and (3) fill PULSES in timeline.py with the strong hits that carry no kill (weight about 0.5 to 0.9).
This grid-exact measure outranks the coarse bass table of music_tempo.py when they disagree."""
import json
import timeline as T
if getattr(T, "CUTS_ON", "bass") not in ("bass", "kills"):
    raise SystemExit('CUTS_ON = %r in timeline.py is not valid: it must be exactly "bass" (transitions on kicks / 808s, '
                     'the default) or "kills" (transitions with the kill rhythm)' % (T.CUTS_ON,))
import beat_hits

m = beat_hits.decode(T.MUSIC)
dur = len(m) / beat_hits.SR
rows = beat_hits.measure(m, T.BPM, T.BEAT0, T.M0, T.R0, T.R1)         # the one measure, shared with the drafters
out_of_music = [r[0] for r in rows if T.beat_time(r[0]) < 0.07 or T.beat_time(r[0]) > dur - 0.05]
if out_of_music:
    print("NOTE: %d half beats lie outside the music (%.1f s long; beats %g .. %g) and read 0: the video is longer than the music or M0 / BEAT0 "
          "are off" % (len(out_of_music), dur, min(out_of_music), max(out_of_music)))
json.dump(rows, open("pulses.json", "w"))
kills = {k for k, lv, i in T.KILLS}
mark = lambda r: "%g%s" % (r[0], "*" if r[0] in kills else "")
print("* = a kill of the current SEGS sits there")
print("kicks / bass hits, beat:low  (low >= 0.4):")
print("  " + "  ".join("%s:%.2f" % (mark(r), r[1]) for r in rows if r[1] >= 0.4))
print("snares / claps, beat:mid  (mid >= 0.6):")
print("  " + "  ".join("%s:%.2f" % (mark(r), r[2]) for r in rows if r[2] >= 0.6))
print("half beats with only a hat (high >= 0.5, no kick, no snare): %d of %d" % (
    sum(1 for r in rows if r[3] >= 0.5 and r[1] < 0.4 and r[2] < 0.6), len(rows)))
weak = [r for r in rows if r[0] in kills and r[1] < 0.25 and r[2] < 0.4]
print("kills on a beat with neither kick nor snare:", [(r[0], "low %.2f mid %.2f high %.2f" % tuple(r[1:])) for r in weak] or "none")
# A transition's musical moment: the start of the incoming take rounded to the half beat. House style: an
# overlapping transition is centred there; reference style: the take starts CUT before its beat (0.15 beat in the example;
# a drafted file: LEAD_FRAMES before its first kill, and with CUTS_ON "bass" exactly on a kick).
by_beat = {r[0]: r for r in rows}
tr = [(round(s["r0"] * 2) / 2, s["clip"]) for s in T.SEGS[1:]]
off = [(b, c, "low %.2f mid %.2f" % tuple(by_beat[b][1:3]) if b in by_beat else "outside the grid") for b, c in tr
       if b not in by_beat or by_beat[b][1] < 0.4]
mode = getattr(T, "CUTS_ON", "bass")
print("transitions (%d) not on a kick / bass hit (low >= 0.4), CUTS_ON = %r%s:" % (
    len(tr), mode, ", must be none" if mode == "bass" else ", information only"), off or "none")
