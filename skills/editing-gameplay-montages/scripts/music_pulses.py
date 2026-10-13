"""For every half beat of the video: how hard does the track hit exactly on the grid?
  low  = kick / bass arriving (below 140 Hz)
  mid  = snare / clap arriving (900 to 3500 Hz; hats barely reach down here)
  high = anything bright arriving (above 2.5 kHz: snares, claps and every hat)
each 0..1 and only large when the hit is loud AND newly arriving at that instant.

usage: python music_pulses.py        -> a printed shortlist, and pulses.json [[beat, low, mid, high], ...]
                                        (a record for you; no other script reads it)

Needs only the music block of timeline.py (MUSIC, BPM, BEAT0, M0, R0, R1); the stars mark the kills of
whatever SEGS is in the file, so ignore them until the segments are yours.
Use it to (1) put every kill on a kick or a snare, never on an empty beat or a bare hat (reference style:
a loud hat may carry a level-1 kill, see reference-style.md), (2) with CUTS_ON = "bass" in timeline.py (the
default), put every transition on a kick / bass hit, never on a snare alone; with "kills" the list is only
information, and (3) fill PULSES in timeline.py with the strong hits that carry no kill (weight about 0.5 to 0.9).
This grid-exact measure outranks the coarse bass table of music_tempo.py when they disagree."""
import json, subprocess
import numpy as np
import timeline as T
if getattr(T, "CUTS_ON", "bass") not in ("bass", "kills"):
    raise SystemExit('CUTS_ON = %r in timeline.py is not valid: it must be exactly "bass" (transitions on kicks / 808s, '
                     'the default) or "kills" (transitions with the kill rhythm)' % (T.CUTS_ON,))
from ff import FF

SR = 44100
raw = subprocess.run([FF, "-v", "error", "-i", T.MUSIC, "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                     capture_output=True).stdout
m = np.frombuffer(raw, np.float32)
if len(m) < SR:
    raise SystemExit("cannot read audio from %s (MUSIC in timeline.py)" % T.MUSIC)
dur = len(m) / SR
ta = max(0.0, T.beat_time(T.R0) - 3.0)
a0, a1 = int(ta * SR), min(len(m), int((T.beat_time(T.R1) + 3.0) * SR))
if a1 - a0 < SR:
    raise SystemExit("timeline.py puts the whole video (beats %g .. %g = %.1f .. %.1f s) outside the music (%.1f s): check MUSIC, BPM, BEAT0, M0" % (
        T.R0, T.R1, T.beat_time(T.R0), T.beat_time(T.R1), dur))
x = m[a0:a1]
X = np.fft.rfft(x)
f = np.fft.rfftfreq(len(x), 1 / SR)
low = np.fft.irfft(X / np.sqrt(1 + (f / 140.0) ** 8), n=len(x))
g = (f / 2500.0) ** 4
high = np.fft.irfft(X * (g / np.sqrt(1 + g * g)), n=len(x))
g = (f / 900.0) ** 4
mid = np.fft.irfft(X * (g / np.sqrt(1 + g * g)) / np.sqrt(1 + (f / 3500.0) ** 8), n=len(x))


def env(y, ms):
    w = int(SR * ms / 1000)
    return np.sqrt(np.convolve(y * y, np.ones(w) / w, mode="same"))


el, em, eh = env(low, 12), env(mid, 5), env(high, 4)


def hit(e, r, pre_ms, post_ms):
    c = int(round((T.beat_time(r) - ta) * SR))
    lo, hi = c - int(pre_ms / 1000 * SR), c - int(0.006 * SR)
    a_lo, a_hi = c + int(0.004 * SR), c + int(post_ms / 1000 * SR)
    if lo < 0 or a_hi > len(e):                  # this beat is before the start / after the end of the music: nothing to measure
        return 0.0, 0.0
    before = e[lo:hi].mean()
    after = e[a_lo:a_hi].max()
    return float(after), float(after / (before + 1e-4))


rows = []
ref_l, ref_m, ref_h = np.percentile(el, 99), np.percentile(em, 99), np.percentile(eh, 99)
for r in np.arange(np.ceil(T.R0 * 2) / 2, T.R1 + 0.01, 0.5):
    al, rl = hit(el, r, 60, 45)
    am, rm = hit(em, r, 40, 25)
    ah, rh = hit(eh, r, 40, 18)
    sl = min(1.0, al / ref_l) * min(1.0, max(0.0, (rl - 1.3) / 2.0))     # loud AND newly arriving
    sm = min(1.0, am / ref_m) * min(1.0, max(0.0, (rm - 1.5) / 3.0))
    sh = min(1.0, ah / ref_h) * min(1.0, max(0.0, (rh - 1.5) / 3.0))
    rows.append([float(r), round(sl, 2), round(sm, 2), round(sh, 2)])
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
