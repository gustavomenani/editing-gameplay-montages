"""Measure where the drum hits of a track really start against a beat grid, say HONESTLY whether one constant grid fits them,
and print the refined first-beat time (BEAT0 for timeline.py) plus any tempo correction.

usage: python music_grid.py BPM BEAT0 [T0 T1] [file]     T0..T1: part of the track to measure (seconds); default the whole track
       e.g. python music_grid.py 130 0.423 27 72
exit status 1: the BPM given does not fit the track (the better one is named; no BEAT0 is printed for the wrong one), or too few
strong hits to say anything.

Method. Every drum attack of the stretch is measured on its own (beat_hits.py: the ONE attack definition of the skill, the half
height of the band's linear envelope across its steepest 6 ms rise, minus the class bias measured on synthetic truth; kick / snare /
hat to about 2.5 ms, an 808 sine about 3.8 ms late of its true start). The strong hits (kick strength >= 0.5, snare >= 0.6, as the
drafters take them; the loud hats too when there are fewer than 12) are laid on the sixteenth-note lines of the grid.
  1. TEMPO CROSS-CHECK: the coherence R of ALL strong attacks (kick, snare, hat bands) with a sixteenth-note grid is scanned over
     +-1.5 % of the BPM given, at 1/12 of its main lobe. A tempo whose R is 1.3x or more of the given one's and that differs from it
     by more than 0.25 lobe (or 0.15 %) is the real one: the script REFUSES the given BPM (exit 1) and names the better one
     (a funk song: 95.7 given, "95.00 fits better"). The BEAT0 of a tempo that does not fit would be a number that happens to fit
     a few hits, so none is printed.
  2. BEAT0: the phase of the sixteenth lines that the strong hits sit on (median of their offsets), taken on the line nearest to
     the BEAT0 given. A move of more than 1/16 beat is announced; a groove whose loud hits sit as much on a half-beat / sixteenth shifted
     line as on the printed one is announced too, with the alternatives (syncopated trap, funk, phonk).
  3. DRIFT: only from 60 s or more of track (and 20 hits) the offsets are fitted against time; a tempo error of 2 ms per minute or
     more (and 3 sigma) is corrected and the corrected BPM printed with a BEAT0 that goes with it. A shorter stretch NEVER corrects
     the tempo (a 30 s section cannot tell a tempo error from a wandering drummer); run on the whole track to correct it.
  4. VERDICT over ALL strong hits of the stretch (not the best 40 %): median, MAD, share beyond 8.3 ms (half a frame), the worst
     hit with its beat, time and ms. More than 5 % beyond 8.3 ms: "constant grid NOT adequate: place on hits.json times" (a live
     drummer, a tempo that wanders or changes, swing): put every kill, cut, bump and boom on the attack time of its hit with
     hit(t) (python music_hits.py writes hits.json), never on a grid beat. A grid that does fit is still only the unit of the
     timeline, the hits are placed on their times anyway.
Run it a second time with the printed values: the median offset must come out within about 2 ms."""
import glob
import os
import sys

import numpy as np

import beat_hits as bh

SR = bh.SR
BAR_MS = 8.3                       # half a frame at 60 fps
ADEQUATE = 0.05                    # share of strong hits beyond BAR_MS above which one constant grid is not adequate
ATT_ALLOW_MS = {"kick": 2.5, "snare": 0.5, "hat": 0.5}     # beat_hits.py: a kick / 808 attack is measured to +-2.5 ms, a snare / hat to +-0.5 ms (synthetic truth);
                                   # a hit counts as off its grid line only beyond BAR_MS plus that (an 808's own scatter is not the grid's fault)
BETTER = 1.3                       # R of another tempo / R of the given one from which the given one is refused
SPAN = 0.015                       # the tempo cross-check scans the BPM given +-1.5 %


def usage(msg):
    raise SystemExit("%s\n\nusage: python music_grid.py BPM BEAT0 [T0 T1] [file]\n       e.g. python music_grid.py 130 0.423 27 72" % msg)


nums, files = [], []
for a in sys.argv[1:]:
    try:
        if os.path.isfile(a):
            raise ValueError
        nums.append(float(a))
    except ValueError:
        files.append(a)
if len(nums) not in (2, 4):
    usage("need BPM and BEAT0 (and optionally T0 T1), got %d numbers" % len(nums))
BPM, BEAT0 = nums[0], nums[1]
if not 30 <= BPM <= 300:
    usage("BPM %g is not a tempo (30..300)" % BPM)
if files:
    SRC = files[0]
else:
    found = sorted(glob.glob("src/music.*"))
    if not found:
        usage("no file given and no src/music.* here")
    SRC = found[0]
PER = 60.0 / BPM
m = bh.decode(SRC)
if len(m) < 4 * SR:
    raise SystemExit("cannot read audio from %s (%.1f s decoded)" % (SRC, len(m) / SR))
if len(nums) == 4:
    T0, T1 = nums[2], nums[3]
    if not 0 <= T0 < T1 <= len(m) / SR + 0.5:
        usage("T0..T1 = %g..%g does not fit the track (%.1f s)" % (T0, T1, len(m) / SR))
    T1 = min(T1, len(m) / SR)
else:
    T0, T1 = 0.0, len(m) / SR
span_s = T1 - T0

# ------------------------------------------------ the strong hits and all strong attacks of the stretch (no grid involved)
hits = bh.strong_hits(m, T0, T1)
hats_too = len(hits) < 12
if hats_too:
    hits = bh.strong_hits(m, T0, T1, hats=True)
if len(hits) < 6:
    raise SystemExit("only %d strong hits (kicks / snares / loud hats) inside %.1f..%.1f s: no drums there, or a track without a clear beat "
                     "(run music_tempo.py: NO TEMPO means there is none)" % (len(hits), T0, T1))
th = np.array([h[0] for h in hits])
sw = np.array([h[2] for h in hits])
kinds = [h[1] for h in hits]
allow = np.array([ATT_ALLOW_MS[k] for k in kinds]) / 1000.0            # the attack measure's own accuracy of each kind of hit


def share_beyond(e):
    """share of the strong hits whose offset e (s) from their grid line is more than half a frame plus the accuracy of that kind of attack"""
    return float(np.mean(np.abs(e) > BAR_MS / 1000 + allow))


ev = bh.attacks_between(m, T0, T1)
ta = np.array([e[0] for e in bh.strong_attacks(ev)])


def coherence(times, bpm, sub=4):
    """|mean of exp(2 pi i sub t bpm / 60)|: 1 when every time sits on one line of a 1/sub-beat grid of that tempo, ~0 when at random"""
    return abs(np.exp(2j * np.pi * sub * times * bpm / 60.0).sum()) / len(times)


def wrap(e, step):
    return e - step * np.round(e / step)


def offsets(t, b0, per):
    """offset (s) of each time from the nearest sixteenth line of the grid b0 + n * per / 4, and that line's index"""
    step = per / 4
    u = np.round((t - b0) / step)
    return t - (b0 + u * step), u


# ------------------------------------------------ 1. the tempo cross-check
refused = None
lobe = 1.0 / (4 * max(1.0, (ta.max() - ta.min()) * BPM / 60.0)) if len(ta) > 8 else 1.0
if len(ta) >= 24 and span_s >= 8:
    grid_b = BPM * (1 + np.arange(-SPAN, SPAN + 1e-12, lobe / 12))
    R = np.array([coherence(ta, b) for b in grid_b])
    jg = int(np.argmin(np.abs(grid_b - BPM)))
    jb = int(np.argmax(R))
    best = float(grid_b[jb])
    # the peak of R is parabolic around its top: refine
    if 0 < jb < len(R) - 1:
        d = R[jb - 1] - 2 * R[jb] + R[jb + 1]
        if d < 0:
            best += float(grid_b[1] - grid_b[0]) * 0.5 * (R[jb - 1] - R[jb + 1]) / d
    far = abs(best / BPM - 1) >= max(0.0015, 0.25 * lobe)
    print("tempo cross-check over %d strong attacks, %.1f s: R(%.3f bpm, given) = %.3f; best R = %.3f at %.3f bpm (%+.3f %%)" % (
        len(ta), span_s, BPM, R[jg], R[jb], best, (best / BPM - 1) * 100))
    if far and R[jb] >= BETTER * max(R[jg], 1e-9):
        snap = round(best * 20) / 20.0                      # produced music has round tempos: the fit of a short stretch is only good to ~ lobe / 20
        better = snap if abs(best - snap) <= 0.05 * lobe * best else round(best, 2)
        refused = (better, best, float(R[jg]), float(R[jb]))
    elif far and R[jb] >= 1.15 * max(R[jg], 1e-9):
        print("note: another tempo, %.3f bpm, fits a little better (R %.3f vs %.3f): not conclusive over %.0f s; measure the whole track" % (
            best, R[jb], R[jg], span_s))
else:
    print("tempo cross-check: not done (needs 24 strong attacks over 8 s; got %d over %.1f s)" % (len(ta), span_s))
if refused:
    better, best, rg, rb = refused
    # the BEAT0 of the better tempo (nearest sixteenth line to the one given), so that the next run starts close
    e_b, _ = offsets(th, BEAT0, 60.0 / better)
    z = (sw * np.exp(2j * np.pi * e_b / (60.0 / better / 4))).sum()
    b0_better = BEAT0 + float(np.angle(z)) / (2 * np.pi) * (60.0 / better / 4)
    print("")
    print("BPM %g does not fit this track: its strong attacks are coherent on a sixteenth grid at %.2f bpm (R %.2f) and not at %g (R %.2f)" % (
        BPM, better, rb, BPM, rg))
    print("%.2f fits better. No BEAT0 is printed for %g: it would only match the few hits that happen to sit near that grid." % (better, BPM))
    print("run:  python music_grid.py %.2f %.4f%s%s" % (better, b0_better, (" %g %g" % (T0, T1)) if len(nums) == 4 else "",
                                                       (' "%s"' % SRC) if files else ""))
    print("(if music_tempo.py says \"tempo steady? NO\" or \"NO TEMPO\", no single BPM fits this track: a live drummer or a tempo change. "
          "Then take the section you will use and place every event on hits.json times with hit(t).)")
    sys.exit("music_grid.py: BPM %g refused: %.2f fits better (R %.2f vs %.2f); a wrong tempo walks %.0f ms per minute against the real hits" % (
        BPM, better, rb, rg, abs(better / BPM - 1) * 60000))

# ------------------------------------------------ 2. BEAT0: the phase of the sixteenth lines the strong hits sit on
e_given, u_given = offsets(th, BEAT0, PER)
step = PER / 4
z = (sw * np.exp(2j * np.pi * e_given / step)).sum()
phi = float(np.angle(z)) / (2 * np.pi) * step
e_ph = wrap(e_given - phi, step)
phi += float(np.median(e_ph[np.abs(e_ph) < step / 4])) if (np.abs(e_ph) < step / 4).any() else 0.0
med_given = float(np.median(e_given)) * 1000
B0_phase = BEAT0 + phi
print("%d strong hits (%s) in %.1f..%.1f s, %d beats at %g bpm" % (
    len(th), "kicks / snares" + (" / hats" if hats_too else ""), T0, T1, int(span_s / PER), BPM))
e_given_ms = wrap(e_given, step) * 1000
print("offset of the real attacks from the grid you gave: median %+.1f ms, spread (std) %.1f ms  (sixteenth lines of %g bpm / %.4f)" % (
    med_given, float(np.std(e_given_ms)), BPM, BEAT0))

# ------------------------------------------------ 3. drift: a tempo correction only from 60 s or more
PER_out, B0_out, corrected, drift_note = PER, B0_phase, False, ""
g_lat = BEAT0 + u_given * step
res0 = wrap(e_given - phi, step)                      # offsets against the phase line
if span_s >= 60 and len(th) >= 20:
    x = g_lat - BEAT0
    keep = np.abs(res0) < max(BAR_MS / 1000, 3 * 1.4826 * float(np.median(np.abs(res0 - np.median(res0)))))
    sl = ic = 0.0
    for _ in range(4):                                # straight line through the offsets, outliers out
        if keep.sum() < 12:
            break
        A = np.vstack([x[keep], np.ones(keep.sum())]).T
        (sl, ic), *_ = np.linalg.lstsq(A, res0[keep], rcond=None)
        rr = res0 - (ic + sl * x)
        keep = np.abs(rr) < max(BAR_MS / 1000, 3 * 1.4826 * float(np.median(np.abs(rr[keep]))))
    if keep.sum() >= 12:
        rr = res0[keep] - (ic + sl * x[keep])
        sigma = float(np.std(rr)) / (float(np.std(x[keep])) * np.sqrt(keep.sum()) + 1e-12) * 60000      # ms per minute the slope is uncertain by
        drift = sl * 60000                                                                               # ms per minute
        print("drift: %+.2f ms per minute (+-%.2f)" % (drift, sigma))
        if abs(drift) >= max(2.0, 3 * sigma):
            trial_per, trial_b0 = PER * (1 + sl), B0_phase + ic
            e_t, _ = offsets(th, trial_b0, trial_per)
            mad_t = 1.4826 * float(np.median(np.abs(e_t - np.median(e_t))))
            mad_0 = 1.4826 * float(np.median(np.abs(res0 - np.median(res0))))
            if mad_t <= 1.05 * mad_0 + 0.0005 and share_beyond(e_t) <= share_beyond(res0) + 0.02:
                PER_out, B0_out, corrected = trial_per, trial_b0, True
            else:
                drift_note = ("the drift fit does not bring the hits closer to a grid (MAD %.1f ms against %.1f ms): a wandering or changing "
                              "tempo, not a tempo error; the BPM is kept" % (mad_t * 1000, mad_0 * 1000))
    else:
        print("drift: not judged (fewer than 12 hits stay near one straight line)")
else:
    print("drift: not judged (needs 60 s of track and 20 strong hits; this is %.0f s and %d: a short stretch cannot tell a tempo error from "
          "a wandering drummer, so the BPM is never corrected from it: run without T0 T1 on the whole track)" % (span_s, len(th)))
BPM_out = 60.0 / PER_out

# ------------------------------------------------ 4. the honest verdict over ALL strong hits, on the grid that will be printed
e_out, u_out = offsets(th, B0_out, PER_out)
e_ms = e_out * 1000
med = float(np.median(e_ms))
mad = 1.4826 * float(np.median(np.abs(e_ms - med)))
beyond = share_beyond(e_out)
jw = int(np.argmax(np.abs(e_out) - allow))
print("grid residual over ALL %d strong hits (%g bpm, BEAT0 %.4f): median %+.1f ms, MAD %.1f ms, %.0f %% beyond %.1f ms (+%.1f ms for a kick / 808 attack, "
      "the accuracy of its measure), worst: track beat %.2f (%.3f s, %s) %+.1f ms" % (
          len(th), BPM_out, B0_out, med, mad, 100 * beyond, BAR_MS, ATT_ALLOW_MS["kick"], (th[jw] - B0_out) / PER_out, th[jw], kinds[jw], e_ms[jw]))
# does the phase wander? the median offset of the hits in windows of 12 s
win = 12.0
meds = []
for a in np.arange(T0, T1 - win / 2, win):
    sel = (th >= a) & (th < a + win)
    if sel.sum() >= 5:
        meds.append((a, float(np.median(e_ms[sel])), int(sel.sum())))
if len(meds) >= 3:
    mv = np.array([q[1] for q in meds])
    if span_s >= 60 and len(meds) >= 5:
        tt = np.array([q[0] for q in meds])
        mv = mv - np.polyval(np.polyfit(tt, mv, 1), tt)
    if float(np.std(mv)) > 8 or float(np.ptp(mv)) > 25:
        print("WARNING the beat phase wanders: the median offset of the hits in windows of %g s runs %s ms: the tempo is not steady "
              "(live drummer, tempo change)%s" % (win, " ".join("%+.0f" % q[1] for q in meds),
                                                   ", or the BPM is wrong by a little: a straight grid is only true near where it was measured"))
if drift_note:
    print("warning:", drift_note)
if beyond > ADEQUATE:
    print("WARNING constant grid NOT adequate: place on hits.json times (python music_hits.py; hit(t) in timeline.py): %.0f %% of the strong hits "
          "are more than %.1f ms from their grid line, the grid is not where this music's hits are. Kills, cuts, bumps and booms go on the "
          "attack times, never on grid beats (the half-beat grid of the drafters is only a candidate list). Possible causes: live playing, "
          "a tempo that wanders or changes, swing, a BPM that is a half / double of the real one (%.3f or %.3f)." % (
              100 * beyond, BAR_MS, BPM_out / 2, BPM_out * 2))
else:
    print("constant grid adequate for this stretch: %.1f %% of the strong hits beyond %.1f ms (a hit is still placed on its own attack time)" % (
        100 * beyond, BAR_MS))

# ------------------------------------------------ the beat of the first line, and syncopation
shift = (B0_out - BEAT0) / PER
if abs(shift) > 1 / 16:
    print("warning: BEAT0 moved by %+.0f ms = %+.3f beat (a sixteenth is 0.25): the lines the strong hits sit on are not where you put the "
          "first beat. If the first kick of a bar is not on beat 0 / 4 / 8 in music_spec.py, shift BEAT0 by whole sixteenths yourself" % (
              (B0_out - BEAT0) * 1000, shift))
pos = np.mod(u_out.astype(int), 4)
share = [float(sw[pos == q].sum() / sw.sum()) for q in range(4)]
print("strong hits by position in the beat (on the beat / a sixteenth after / on the half beat / three sixteenths after): %s" % (
    " / ".join("%.0f %%" % (100 * s) for s in share)))
if share[2] >= 0.8 * share[0] and share[2] > 0.2 or share[1] >= 0.8 * share[0] and share[1] > 0.2 or share[3] >= 0.8 * share[0] and share[3] > 0.2:
    alts = []
    for q, nm in ((2, "a half beat"), (1, "a sixteenth"), (3, "three sixteenths")):
        if share[q] >= 0.8 * share[0] and share[q] > 0.2:
            alts.append("%+.2f beat (%s) -> BEAT0 %.4f: %.0f %% of the strong hits" % (q / 4.0, nm, B0_out + q * step, 100 * share[q]))
    print("warning: the strong hits sit as much on a shifted grid as on the printed one (on the printed beat lines %.0f %%; by position in the beat "
          "beat / e / and / a: %s): a syncopated groove (funk, trap, phonk) or the first beat is somewhere else. Alternatives: %s. If the "
          "first kick of a bar is not on beat 0 / 4 / 8 in music_spec.py, use one of these BEAT0 values (the BPM stays)" % (
              100 * share[0], " / ".join("%.0f %%" % (100 * s) for s in share), "; ".join(alts)))
if corrected:
    print("=> BPM = %.3f   BEAT0 = %.4f   (you gave %.3f / %.4f: use BOTH new values, then run again to confirm the median is "
          "within about 2 ms)" % (BPM_out, B0_out, BPM, BEAT0))
else:
    print("=> BEAT0 = %.4f   (was %.4f; it goes with BPM %g as given: a different BPM needs a new BEAT0)" % (B0_out, BEAT0, BPM))
print("strongest hits: track beat, time, offset from the grid ms, strength, kind")
for i in np.argsort(-sw)[:24]:
    print("   beat %7.2f  %7.3fs  %+6.1f  %.2f  %s" % ((th[i] - B0_out) / PER_out, th[i], e_ms[i], sw[i], kinds[i]))
