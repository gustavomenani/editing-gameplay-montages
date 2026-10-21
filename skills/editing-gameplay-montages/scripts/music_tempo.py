"""First look at a track: tempo, a provisional beat phase, where the loud / bass-heavy sections are,
and the kick pattern bar by bar. Use it to choose the BPM and the section of the song.

usage: python music_tempo.py [file]         default: src/music.*

Tempo: the fit looks at kicks, snares and (less) hats, then decides which member of the half / double family
is the beat: the slower tempo wins unless the half beats in between are as strong as the beats themselves
(four on the floor at 140 is 140; a boom-bap or trap loop with an empty beat in between is 70). Both
members are printed with their evidence, so you can overrule it: "tempo candidates" is the place to look.
The phase printed here is only provisional (within about 10 ms on drum machines, more on live playing, and
it is the beat grid's phase: the first beat may be a bar or two before the music really starts): ALWAYS refine
it with music_grid.py before placing anything on a beat. Range 68..182 bpm. Is the tempo steady? It is read again
in every 30 s window on its own ("tempo steady?"): windows that differ by more than 0.3 % (a live drummer, a tempo
change) mean one BPM / BEAT0 is only true near the part that was measured. A WEAK fit (under 2.5x the average tempo:
strong off-beats of a live band, a syncopated groove, or no clear drum pattern) is printed WITH a "WEAK" note and the
tables, exit status 0, when the steadiness checks that can judge the track agree on one straight grid (the 30 s tempo
windows, from 45 s of track; the beat phase of the strong attacks in 10 s windows, scatter under 10 ms, from 30 s);
when either says no, or neither can judge (a short track, too few strong attacks), there is no tempo: the script says
"NO TEMPO", skips the beat-based tables and exits with status 1.
The last block lists bass re-entries: the usual place for the first kill ("the drop"). With the drop on
track beat D, M0 = D + 1 makes it timeline beat -1 and the next bar start at beat 0."""
import glob, subprocess, sys
import numpy as np
from ff import FF

if len(sys.argv) > 1:
    SRC = sys.argv[1]
else:
    hits = sorted(glob.glob("src/music.*"))
    if not hits:
        raise SystemExit("usage: python music_tempo.py [file]   (no file given and no src/music.* here)")
    SRC = hits[0]
SR = 22050
proc = subprocess.run([FF, "-v", "error", "-i", SRC, "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True)
x = np.frombuffer(proc.stdout, dtype=np.float32)
if len(x) < 10 * SR:
    raise SystemExit("cannot find a tempo in %s: %s" % (SRC, proc.stderr.decode(errors="replace").strip()[-200:] or
                                                         "only %.1f s of audio decoded (need at least 10 s)" % (len(x) / SR)))
if float(np.abs(x).max()) < 1e-4:
    raise SystemExit("%s is silent" % SRC)
N, H = 1024, 128
fps = SR / H
nfr = 1 + (len(x) - N) // H
win = np.hanning(N).astype(np.float32)
freqs = np.fft.rfftfreq(N, 1 / SR)
S = np.empty((nfr, len(freqs)), np.float32)
for a in range(0, nfr, 4096):                       # in blocks: a 10 minute track would otherwise need gigabytes
    b = min(nfr, a + 4096)
    idx = np.arange(N)[None, :] + H * np.arange(a, b)[:, None]
    S[a:b] = np.abs(np.fft.rfft(x[idx] * win, axis=1))
L = np.log1p(50 * S)
flux = np.maximum(L[1:] - L[:-1], 0)
band = {"low": freqs < 150, "mid": (freqs >= 150) & (freqs < 2500), "high": freqs >= 2500}
on = {k: flux[:, m].mean(1) for k, m in band.items()}
rms = np.sqrt((S ** 2).mean(1))
low_rms = np.sqrt((S[:, band["low"]] ** 2).mean(1))
LAT = (H + N / 2) / SR + 0.0145                     # a flux frame: centre of its later window, plus the 14.5 ms measured on drum machines


def norm(v):
    v = v - np.convolve(v, np.ones(86) / 86, mode="same")
    v = np.maximum(v, 0)
    return v / (v.std() + 1e-9)


nl, nm, nh = norm(on["low"]), norm(on["mid"]), norm(on["high"])
o = nl + nm + 0.3 * nh                               # kicks and snares carry the beat; hats only help
kd = nl + nm                                         # drums that make a beat: used to decide half / double
if o.std() < 1e-6:
    raise SystemExit("no rhythm found in %s (no onsets)" % SRC)
om = np.maximum(np.maximum(o, np.roll(o, 1)), np.roll(o, -1))        # tolerate one frame (5.8 ms) of jitter in the pegs


def comb(b, nph=48, v=om):
    """Best phase of a comb at tempo b: (score, phase in frames)."""
    per = 60 * fps / b
    k = np.arange(int((len(v) - 2) / per))
    ph = np.linspace(0, per, nph, endpoint=False)
    p = np.round(ph[:, None] + k[None, :] * per).astype(int)
    sc = v[p].sum(1) / np.sqrt(len(k))
    i = int(np.argmax(sc))
    return float(sc[i]), float(ph[i])


# coarse fit over 60..200 bpm, then a fine one around the best
grid = np.arange(60, 200, 0.05)
cs = np.array([comb(b, 24)[0] for b in grid])
b0 = float(grid[int(np.argmax(cs))])
fine = np.arange(b0 - 0.1, b0 + 0.1, 0.004)
fs = np.array([comb(b, 96)[0] for b in fine])
b_best = float(fine[int(np.argmax(fs))])

# the family of that tempo: the member between 68 and 136 (the root; a little margin so that 70.00 is not read as 139.99) and its
# double when that is still <= 182
root = b_best
while root >= 136:
    root /= 2
while root < 68:
    root *= 2
members = [root] + ([root * 2] if root * 2 <= 182 else [])


def strength(b, shift=0.0):
    """Mean strength of kicks + snares on the beats of tempo b (shift = fraction of a beat after the best phase)."""
    per = 60 * fps / b
    _, ph = comb(b, 96, np.maximum(np.maximum(kd, np.roll(kd, 1)), np.roll(kd, -1)))
    k = np.arange(int((len(kd) - 2) / per) - 1)
    p = np.round(ph + (k + shift) * per).astype(int)
    p = p[(p >= 0) & (p < len(kd))]
    return float(np.maximum(np.maximum(kd[p], np.roll(kd, 1)[p]), np.roll(kd, -1)[p]).mean())


rows = []
for b in members:
    rb = b
    sb = max(strength(rb), 1e-9)
    between = strength(rb, 0.5)
    rows.append((rb, sb, between / sb))
final = rows[0][0]
if len(rows) == 2 and rows[0][2] >= 0.6:
    final = rows[1][0]                               # the half beats in between are as strong as the beats: the double is the beat
# refine the tempo that was chosen (the fit above may have sat on the other member of the family): pegs between the frames
# (interpolated), so that the score does not jump with the 5.8 ms frame grid; the best phase is then taken at the best tempo
osm = np.convolve(o, np.hanning(7) / np.hanning(7).sum(), mode="same")
frames = np.arange(len(osm))


def comb_fine(b, nph=192):
    per = 60 * fps / b
    k = np.arange(int((len(osm) - 2) / per))
    p = np.linspace(0, per, nph, endpoint=False)[:, None] + k[None, :] * per
    sc = np.interp(p.ravel(), frames, osm).reshape(p.shape).sum(1) / np.sqrt(len(k))
    i = int(np.argmax(sc))
    return float(sc[i]), float(p[i, 0])


fine = np.arange(final * 0.998, final * 1.002, final * 1e-5)
fs = np.convolve(np.array([comb_fine(b, 96)[0] for b in fine]), np.ones(9) / 9, mode="same")
final = float(fine[int(np.argmax(fs[4:-4])) + 4])
sc, ph = comb_fine(final, 384)
per = 60 * fps / final

print("track %.1f s" % (len(x) / SR))
print("tempo candidates: bpm | kick+snare strength on the beats | strength half way between beats as a share of it")
for rb, sb, bt in rows:
    print("   %7.2f   %5.2f   %3.0f%%%s" % (rb, sb, 100 * bt, "   <- chosen" if abs(rb - final) < 0.5 else ""))
if len(rows) == 2:
    if abs(final - rows[0][0]) < 0.5:
        print("   (%.2f is the same groove counted twice as fast: it would put a beat on every half beat of %.2f; the half beats are only %.0f%% as "
              "strong, so %.2f is taken. A fast groove played in half time (trap, drum and bass): use %.2f instead if you count it that way.)" %
              (rows[1][0], rows[0][0], 100 * rows[0][2], rows[0][0], rows[1][0]))
    else:
        print("   (the half beats in between are %.0f%% as strong as the beats of %.2f: four on the floor or a busy backbeat, so %.2f is the beat. "
              "Count it %.2f if you feel it in half time.)" % (100 * rows[0][2], rows[0][0], rows[1][0], rows[0][0]))
else:
    print("   (half %.2f would be below the 68 bpm limit, double %.2f above 182: no other member of the family fits)" % (root / 2, root * 2))
first = (ph / fps + LAT) % (60 / final)             # frame label -> time of the onset (the flux fires before the audible attack)
if first < 0.05:                                    # a beat that close to the start may really lie before it: count from the next one
    first += 60 / final
fit_strength = float(cs.max() / np.median(cs))
WEAK = fit_strength < 2.5
import contextlib, io
_buf = io.StringIO()
_cm = contextlib.redirect_stdout(_buf)
_cm.__enter__()                                      # the steadiness checks below print into a buffer, see where it is written out


def window_tempo(a, b, centre, span):
    """Best tempo of the onset curve frames a .. b within +-span of `centre` (comb with interpolated pegs, 0.02 % steps): -> (bpm, score)"""
    v = osm[a:b]
    fr_ = np.arange(len(v))

    def score(bpm, nph):
        per_ = 60 * fps / bpm
        k_ = np.arange(int((len(v) - 2) / per_))
        p_ = np.linspace(0, per_, nph, endpoint=False)[:, None] + k_[None, :] * per_
        return float(np.interp(p_.ravel(), fr_, v).reshape(p_.shape).sum(1).max() / np.sqrt(len(k_)))

    cand = centre * (1 + np.arange(-span, span + 1e-9, 0.0007))
    sc_ = np.array([score(bpm, 48) for bpm in cand])
    b1 = float(cand[int(np.argmax(sc_))])
    fine_ = b1 * (1 + np.arange(-0.0006, 0.00061, 0.00002))
    fs_ = np.array([score(bpm, 96) for bpm in fine_])
    return float(fine_[int(np.argmax(fs_))]), float(fs_.max())


# Is the tempo STEADY? One straight grid is only true for a track that does not wander: the tempo of every 30 s window, on its own.
steady = None
if len(x) / SR >= 45:
    wins = []
    n30 = int(30 * fps)
    starts = list(range(0, len(osm) - n30 + 1, n30))
    if len(osm) - (starts[-1] + n30 if starts else 0) >= 10 * fps:         # the stretch after the last whole window, if it is 10 s or more
        starts.append(len(osm) - n30)
    for a0 in starts:
        wb, ws = window_tempo(a0, a0 + n30, final, 0.08)               # +-8 %: a tempo change of a few % is found, not missed
        wins.append((a0 / fps, wb, ws))
    if wins:
        ref_s = float(np.median([w[2] for w in wins]))
        good = [w for w in wins if w[2] >= 0.6 * ref_s]               # a window with no drums in it (a break, an outro) is not judged
        bpms = np.array([w[1] for w in good])
        steady = (len(good) >= 2) and float((bpms.max() - bpms.min()) / np.median(bpms)) <= 0.003
        print("tempo per 30 s window (bpm, from the drums of that window alone): " + "  ".join("%d s %.2f%s" % (w[0], w[1], "" if w in good else " (no clear beat: not judged)") for w in wins))
        if len(good) < 2:
            steady = None
            print("tempo steady? not judged (fewer than two windows with drums)")
        elif steady:
            print("tempo steady? yes: the 30 s windows agree within %.2f %% (%.2f .. %.2f bpm)" % (
                100 * (bpms.max() - bpms.min()) / np.median(bpms), bpms.min(), bpms.max()))
        else:
            first_h, second_h = np.median(bpms[:len(bpms) // 2]), np.median(bpms[len(bpms) // 2:])
            print("WARNING tempo steady? NO: the 30 s windows differ by %.2f %% (%.2f .. %.2f bpm; first half %.2f, second half %.2f): a live drummer "
                  "or a tempo change. One BPM / BEAT0 is only true near the part it was measured on: measure the section you will use "
                  "(music_grid.py BPM BEAT0 T0 T1) and place every event on hits.json times (music_hits.py), never on the grid" % (
                      100 * (bpms.max() - bpms.min()) / np.median(bpms), bpms.min(), bpms.max(), first_h, second_h))
else:
    print("tempo steady? not judged by the 30 s windows (a track under 45 s has fewer than two)")

# The windows above see a tempo that CHANGES; a drummer who wanders around it (+-1.5 % swings every few bars) averages out inside 30 s.
# So the phase is read too: in windows of 10 s the circular mean phase of the strong attacks on the sixteenth lines of the fitted tempo,
# its scatter after removing a straight line (a tempo error of a few hundredths of a percent is a line, a wandering drummer is not):
# measured on synthetic truth 0.4 ms (steady), 19..26 ms (wander, tempo change); real songs 2.7 ms (a funk song), 4.6 ms (a live band, steady).
PHASE_MAX_MS = 10.0
if len(x) / SR >= 30:
    import beat_hits
    t_att = np.array([e[0] for e in beat_hits.strong_attacks(beat_hits.attacks(beat_hits.decode(SRC)))])
    st4 = 60.0 / final / 4
    pw = []
    for a in np.arange(0.0, len(x) / SR - 5.0, 10.0):
        s_ = t_att[(t_att >= a) & (t_att < a + 10.0)]
        if len(s_) >= 20:
            pw.append((a + 5.0, float(np.angle(np.exp(2j * np.pi * s_ / st4).mean())) / (2 * np.pi) * st4 * 1000))
    if len(pw) >= 3:
        pt = np.array([p[0] for p in pw])
        pv = np.unwrap(np.array([p[1] for p in pw]) * 2 * np.pi / (st4 * 1000)) * (st4 * 1000) / (2 * np.pi)
        pr = pv - np.polyval(np.polyfit(pt, pv, 1), pt)
        p_std = float(np.std(pr))
        if p_std <= PHASE_MAX_MS:
            print("beat phase steady? yes: the phase of the strong attacks in %d windows of 10 s scatters %.1f ms (limit %.0f)" % (len(pw), p_std, PHASE_MAX_MS))
            if steady is None:                          # the 30 s windows could not judge: the phase alone says steady
                steady = True
        else:
            print("WARNING beat phase steady? NO: the phase of the strong attacks wanders by %.1f ms (std over %d windows of 10 s, limit %.0f): a live "
                  "drummer or a tempo that swings around %.2f: no straight grid holds it. Place every event on hits.json times (music_hits.py)" % (
                      p_std, len(pw), PHASE_MAX_MS, final))
            steady = False
    else:
        print("beat phase steady? not judged (fewer than three 10 s windows with 20 strong attacks)")
_cm.__exit__(None, None, None)                      # the steadiness lines were collected: what the fit is called depends on them
if WEAK and not steady:
    print("NO TEMPO: a WEAK fit (%.1fx) AND %s: this track has no tempo one straight grid can hold. The strongest candidate (%.3f bpm, first beat %.3f s) "
          "is NOT a tempo; the beat-based tables (kick pattern, drops) are not printed, they would sit on a grid that does not exist." % (
              fit_strength, "a tempo or beat phase that does not stay on one straight grid" if steady is False else "no steadiness evidence (under 30 s, or too few strong attacks)",
              final, first))
    sys.stdout.write(_buf.getvalue())
    sys.exit("music_tempo.py: no tempo found in %s (fit strength %.1fx, WEAK, tempo not steady): give music_grid.py a BPM you know, or choose another track / section." % (SRC, fit_strength))
print("best fit: %.3f bpm, first beat at %.3f s (provisional, +-10 ms on drum machines, more on live playing: refine with  python music_grid.py %.3f %.3f)" % (
    final, first, final, first))
print("fit strength: %.1fx the average tempo" % fit_strength)
if WEAK:
    print("WEAK: the fit is under 2.5x the average tempo: strong off-beats (a live band, a syncopated groove) or no clear drum pattern (ambient, "
          "a cappella, noise, a very sparse intro). It is trusted because the steadiness checks that could judge this track (the 30 s tempo "
          "windows, the 10 s beat phase) found one straight grid.")
sys.stdout.write(_buf.getvalue())
beats = first + np.arange(int(len(x) / SR / (60 / final)) - 1) * (60 / final)

# loudness / bass per second, to find the strongest section
sec = int(len(rms) / fps)
e = [float(rms[int(i * fps):int((i + 1) * fps)].mean()) for i in range(sec)]
lb = [float(low_rms[int(i * fps):int((i + 1) * fps)].mean()) for i in range(sec)]
em, lm = max(e) + 1e-9, max(lb) + 1e-9
print("second: loudness / bass, one digit per second (0-9)")
for i in range(0, sec, 10):
    print("%4d  %s   %s" % (i, "".join(str(min(9, int(10 * v / em))) for v in e[i:i + 10]),
                            "".join(str(min(9, int(10 * v / lm))) for v in lb[i:i + 10])))
# kick strength on every beat, four bars per line: drops and breakdowns show up as dense / empty rows
ol = nl
w0, w1 = int(0.017 * fps), int(0.023 * fps)
kick = np.array([float(ol[max(0, int((t - LAT) * fps) - w0):int((t - LAT) * fps) + w1 + 1].max()) if t - LAT > 0 else 0.0 for t in beats])
km = np.percentile(kick, 98) + 1e-9
print("beat  time   bass onset on each beat, bars of 4 (0-9)")
for i in range(0, len(kick) - 3, 16):
    print("%4d %6.2fs  %s" % (i, beats[i], " ".join("".join(str(min(9, int(9 * v / km))) for v in kick[j:j + 4])
                                                   for j in range(i, min(i + 16, len(kick) - 3), 4))))
# candidate drops: beats where the bass comes back after at least four beats of little bass
lowb = np.array([float(low_rms[int(beats[i] * fps):max(int(beats[i] * fps) + 1, int(beats[i + 1] * fps))].mean()) for i in range(len(beats) - 1)])
ref = np.percentile(lowb, 90)
cand = []
for i in range(4, len(lowb) - 8):
    before, after = lowb[i - 4:i].max(), lowb[i:i + 8].mean()
    if before < 0.25 * ref and lowb[i] > 0.6 * ref:
        quiet = 4
        while i - quiet - 1 >= 0 and lowb[i - quiet - 1] < 0.25 * ref and quiet < 64:
            quiet += 1
        cand.append((min(quiet, 32), after / ref, i, quiet))
print("bass re-entries after a gap (candidate drops, in time order): track beat, time, quiet beats before, bass over the next 8 beats (0-9)")
for _, _, i, quiet in sorted(cand, key=lambda c: c[2])[:24]:
    print("   beat %4d  %6.2fs  after %2d quiet beats  %s" % (i, beats[i], quiet, "".join(str(min(9, int(9 * v / ref))) for v in lowb[i:i + 8])))
if not cand:
    print("   none: the bass never drops out for four beats in a row (no breakdown, or the grid above is wrong)")
print("(beat numbers stay valid after music_grid.py, which only shifts the grid by a few ms)")
