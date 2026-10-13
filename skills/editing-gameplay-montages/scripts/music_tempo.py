"""First look at a track: tempo, a provisional beat phase, where the loud / bass-heavy sections are,
and the kick pattern bar by bar. Use it to choose the BPM and the section of the song.

usage: python music_tempo.py [file]         default: src/music.*

Tempo: the fit looks at kicks, snares and (less) hats, then decides which member of the half / double family
is the beat: the slower tempo wins unless the half beats in between are as strong as the beats themselves
(four on the floor at 140 is 140; a boom-bap or trap loop with an empty beat in between is 70). Both
members are printed with their evidence, so you can overrule it: "tempo candidates" is the place to look.
The phase printed here is only provisional (within about 10 ms on drum machines, more on live playing, and
it is the beat grid's phase: the first beat may be a bar or two before the music really starts): ALWAYS refine
it with music_grid.py before placing anything on a beat. Range 68..182 bpm; a track with no drum pattern
prints "WEAK" under the fit.
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
print("best fit: %.3f bpm, first beat at %.3f s (provisional: refine with  python music_grid.py %.3f %.3f)" % (final, first, final, first))
fit_strength = float(cs.max() / np.median(cs))
print("fit strength: %.1fx the average tempo%s" % (fit_strength, "" if fit_strength >= 2.5 else
      "  <- WEAK: no clear drum pattern in this track (ambient, a cappella, noise, or a very sparse intro): do not trust the tempo above"))
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
