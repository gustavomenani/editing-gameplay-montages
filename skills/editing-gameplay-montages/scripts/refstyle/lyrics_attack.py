"""The sung ATTACK of a vocal stem and the assignment of lyric words to attacks (shared by cues_from_alignment.py,
lyrics_audit.py and lyric_sync_sheet.py; numpy + scipy only, runs in venv311).

THE definition of a sung attack (one for the whole lyric chain, like beat_hits.py's one definition for drum hits): the
time at which the stem's LEVEL crosses the middle, in dB, of its steepest rise.
  level   10 log10 of the mean square under a 16 ms Hann window (centred: no delay), one value per ms (44 samples at 44.1 kHz);
  rise    level(t + 60 ms) - level(t); every local maximum of >= 4 dB, 30 ms apart, is a candidate (one whose top is more
          than 30 dB under the singing level = the 95th percentile of the stem is a bump in the noise of a pause);
  attack  where the level crosses top - min(top - floor, 20 dB) / 2, linearly interpolated between the ms values, at the
          STEEPEST point of the onset (the 60 ms windows that contain it all give the same time; floor = lowest level in the
          30 ms before it, top = highest in the 60 ms after it). The half height, but of at most 20 dB, so a word out of
          silence does not start in the foot of its rise (the noise floor of the stem decides where a 40 dB rise "begins";
          measured: 25-43 ms between two demucs stems). The time is a continuous function of the audio (a stem cut 5 ms
          later gives the attack 5 ms later to ~1 ms). Attacks closer than 40 ms are one onset (the strongest stays).
For a drum the rise lasts 2 ms and this is its half height; for a syllable it is where the sound becomes a note, 13-31 ms
after the first trace of energy, and where the viewer hears the word begin. The cue of a word IS this time, textfx draws
the first letter one frame earlier (HIT_LEAD): the same convention as the kills.
  strength  the rise in dB;  CONFIDENT = >= 8 dB (g = 1; g falls smoothly to 0 at 4 dB) or a voiced note starts there.
  voiced note: the first 40 ms frame whose normalised autocorrelation (lag 1/900 .. 1/75 s) is >= 0.7 after >= 20 ms of
          frames under 0.65 (Stem.voice_on); a sung syllable is a note, so a legato change from one word to the next (5.8 dB, no dip) starts
          a voiced run although the level barely moves; the nearest attack within -60 / +80 ms of one is `voiced`.

Assignment (assign()): the CTC time of a word (lyrics_ctc_align.py: sub-frame resolution but sd ~50 ms, early for
consonant-initial words, late inside the note of a fast or vowel-initial one, up to 285 ms late after a silence) is only a
PRIOR c = CTC + MU (MU = 25 ms: the measured offset of attack - CTC label). Candidates = the attacks within +-0.20 s of c (from
the end of a silence that the aligner puts before the word on). Cost of a candidate = a heavy-tailed (Student-t, nu = 3) distance
to c, scale 100 ms for an attack before c and 50 ms for one after it, minus its strength (<= 1.5 for 15 dB), minus a bonus for a
voiced note, minus a bonus for the first attack after a silence. "No attack" costs 3.0 and keeps c. A weak attack (g < 1) only
PULLS the word: time = c + g (attack - c), cost = (1 - g) 3.0 + g cost: nothing here is a hard threshold, the result moves
continuously with the inputs (the old rule flipped a word by 171 ms on a 7 dB threshold when the stem moved 5 ms). The words
get their attacks IN ORDER (each once, >= 50 ms apart) by a dynamic programme minimising the total cost. The margin of
a word = how much more the best assignment costs when that word takes ANOTHER real attack (min-sum forward / backward): under
AMBIG_MARGIN the word has two readings and is flagged instead of silently chosen.
Measured on a live-band vocal stem: the old rule (7 dB hard threshold, window -0.12..+0.05 s, "closer to the
previous word" clause) put two words 157 ms and 113 ms late; here both land on their attacks."""
import warnings

import numpy as np
from scipy import signal
from scipy.io import wavfile

WIN_MS = 16.0              # level window (Hann): a flat 8 ms window ripples with the pitch period and moved a 11 dB attack by 9 ms
                           # between two cuts of the same stem; 16 ms Hann: 2 ms
RISE_MS = 60               # the rise is measured over this time
MIN_RISE = 4.0             # dB: weakest attack that is a candidate
SING_RANGE = 30.0          # dB: an attack must reach this close to the singing level (95th percentile of the stem)
MERGE = 0.04               # s: attacks closer than this are one onset
MID_CAP = 20.0             # dB: the attack is where the level is top - min(rise, MID_CAP) / 2
CONF = 8.0                 # dB: a CONFIDENT attack (audit)
MIN_GAP = 0.05             # s: attacks of consecutive words are at least this far apart
MU = 0.025                 # s: the sung attack comes this long after the CTC label of the word (median of the test data)
WINDOW = 0.20              # s: candidates within +-WINDOW of CTC time + MU
SIGMA_EARLY = 0.10         # s: scale of the Student-t (nu = 3) distance cost for an attack BEFORE the prior (CTC labels a fast or
SIGMA_LATE = 0.05          #    vowel-initial word late inside its note: wide) and AFTER it (consonant-initial words: CTC early by <= 60 ms)
STRENGTH = 1.5             # cost bonus of a 15 dB attack
FIRST_BONUS = 1.0          # cost bonus of the first attack after a silence, for a word that follows one
NONE_COST = 3.0            # no attack: the CTC time stays (about the cost of a candidate at the window edge)
AMBIG_MARGIN = 0.6         # a word whose second-best reading costs less than this more is ambiguous
SILENCE = 0.12             # s: a gap in the singing
VOICE_BONUS = 1.0          # cost bonus of an attack that starts a voiced note (periodic sound again after >= 20 ms without)
VOICE_GAP = 0.02           # s: unvoiced time (periodicity under F0_OFF) before a voiced note
VOICE_BEFORE, VOICE_AFTER = 0.06, 0.08   # s: a voiced note starts within this much before / after its attack (breathy onsets lag)
F0_MIN, F0_MAX, F0_WIN, F0_HOP, F0_CLEAR, F0_OFF = 75.0, 900.0, 0.040, 0.005, 0.7, 0.65


class Stem:
    """The level curve and the attacks of a vocal stem. `t0` = song time of the stem's first sample."""

    def __init__(self, path, t0):
        with warnings.catch_warnings():                      # soundfile writes a PEAK chunk that scipy skips with a warning
            warnings.simplefilter("ignore", wavfile.WavFileWarning)
            sr, x = wavfile.read(path)
        x = x.astype(np.float64)
        x = x.mean(1) if x.ndim > 1 else x
        self.sr, self.t0 = sr, float(t0)
        hop = int(round(sr * 0.001))
        win = int(round(sr * WIN_MS / 1000)) | 1             # odd: centred on a sample
        ker = np.hanning(win + 2)[1:-1]
        e = np.maximum(signal.fftconvolve(x * x, ker / ker.sum(), mode="same"), 0.0)
        idx = np.arange(hop // 2, len(x), hop)
        self.t = self.t0 + idx / sr                          # song seconds of each level value
        db = 10 * np.log10(e[idx] + 1e-12)
        self.db = np.maximum(db, db.max() - 60)
        self.voiced = self.db > np.percentile(self.db, 95) - 20      # 20 dB under the singing level = silent
        self.att = self._attacks()
        self.gaps = self._gaps()
        self._mark_first()
        self.voice_on = self._voicing(x, sr)
        for a in self.att:
            a["voiced"] = False
        for v in self.voice_on:                              # a voiced note supports ONE attack: the nearest within the window
            near = [a for a in self.att if a["t"] - VOICE_BEFORE <= v <= a["t"] + VOICE_AFTER]
            if near:
                min(near, key=lambda a: abs(a["t"] - v))["voiced"] = True
        for a in self.att:
            # how much the attack counts as a real syllable start: 0 at MIN_RISE dB, 1 from CONF dB (smooth in between),
            # 1 when a voiced note starts there (a legato syllable has a small rise but a new note)
            q = min(1.0, max(0.0, (a["db"] - MIN_RISE) / (CONF - MIN_RISE)))
            a["g"] = 1.0 if a["voiced"] else q * q * (3 - 2 * q)

    def _attacks(self):
        db, t, n, k = self.db, self.t, len(self.db), RISE_MS
        rise = np.zeros(n)
        rise[:-k] = db[k:] - db[:-k]
        pk, _ = signal.find_peaks(rise, height=MIN_RISE, distance=30)
        sing = np.percentile(db, 95)                         # the singing level
        out = []
        slope = np.zeros(n)
        slope[4:-4] = db[8:] - db[:-8]                       # dB per 8 ms
        for p in pk:
            # every window that contains the steep part of an onset is a peak of `rise`: they are all moved to the STEEPEST
            # point of that onset (one time, whichever window won), and floor / top are read around it
            ts = p + int(np.argmax(slope[p:min(n, p + k)]))
            floor = db[max(0, ts - 30):ts + 1].min()
            top = db[ts:min(n, ts + k + 1)].max()
            if top < sing - SING_RANGE:                      # a bump in the noise of a pause, not a syllable
                continue
            mid = top - min(top - floor, MID_CAP) / 2          # half height, but of at most MID_CAP dB: a rise out of silence
                                                               # (floor = noise of the stem) must not start in its foot
            j = ts
            if db[j] >= mid:                                 # the crossing just before the steepest point
                while j > max(0, ts - 40) and db[j - 1] >= mid:
                    j -= 1
            else:                                            # or just after it
                while j < min(n - 1, ts + k) and db[j] < mid:
                    j += 1
            if j > 0 and db[j] >= mid > db[j - 1]:           # linear interpolation inside the ms step
                tt = t[j - 1] + (mid - db[j - 1]) / (db[j] - db[j - 1]) * (t[j] - t[j - 1])
            else:
                tt = t[j]
            out.append(dict(t=float(tt), db=float(rise[p]), floor=float(floor), top=float(top), first=False))
        # one onset gives several overlapping 60 ms rises: the strongest of every cluster closer than MERGE s stays
        keep = []
        for a in sorted(out, key=lambda a: -a["db"]):
            if all(abs(a["t"] - b["t"]) >= MERGE for b in keep):
                keep.append(a)
        return sorted(keep, key=lambda a: a["t"])

    def _gaps(self, need=SILENCE):
        """Silences of the stem (>= `need` s of unvoiced level): [(start, end)] in song seconds."""
        v, t, out, k, n = self.voiced, self.t, [], 0, len(self.voiced)
        while k < n:
            if not v[k]:
                k2 = k
                while k2 < n and not v[k2]:
                    k2 += 1
                if t[min(k2, n - 1)] - t[k] >= need:
                    out.append((float(t[k]), float(t[min(k2, n - 1)])))
                k = k2
            else:
                k += 1
        return out

    def silences(self, a, b, need=SILENCE):
        """Silences of at least `need` s between song times a and b, clipped to [a, b]: [(start, end)]."""
        return [(max(s, a), min(e, b)) for s, e in self.gaps
                if min(e, b) - max(s, a) >= need and e > a and s < b]

    def _voicing(self, x, sr):
        """Song times where a VOICED NOTE starts: the first frame with periodic sound (normalised autocorrelation peak
        >= F0_CLEAR at a lag of 1/900 .. 1/75 s) after at least VOICE_GAP s without. A sung syllable is a note: it starts
        a voiced run even when its level barely rises (a legato change from one word to the next: 5.8 dB). One 40 ms frame / 5 ms."""
        w, h = int(round(F0_WIN * sr)), int(round(F0_HOP * sr))
        n = (len(x) - w) // h + 1
        if n < 2:
            return []
        idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
        fr = x[idx] * np.hanning(w)[None, :]
        nfft = 1 << int(np.ceil(np.log2(2 * w)))
        spec = np.fft.rfft(fr, nfft, axis=1)
        r = np.fft.irfft(spec * np.conj(spec), nfft, axis=1)[:, :w]
        cs = np.concatenate([np.zeros((n, 1)), np.cumsum(fr * fr, axis=1)], axis=1)
        tau = np.arange(w)
        m = cs[:, w - tau] + (cs[:, w:w + 1] - cs[:, tau])                       # NSDF denominator (McLeod)
        nsdf = 2 * r / np.maximum(m, 1e-12)
        lo, hi = int(sr / F0_MAX), int(sr / F0_MIN)
        peak = nsdf[:, lo:hi].max(1)
        peak[cs[:, w] <= 1e-9 * cs[:, w].max()] = 0.0
        tf = self.t0 + (np.arange(n) * h + w / 2) / sr                           # frame centres
        out, quiet = [], 0                                                       # frames in a row below F0_OFF
        for k in range(n):
            if peak[k] < F0_OFF:
                quiet += 1
            elif peak[k] >= F0_CLEAR:
                if quiet * h / sr >= VOICE_GAP:
                    out.append(float(tf[k]))
                quiet = 0
        return out

    def _mark_first(self):
        """`first`: the attack is the first one after the end of a silence of the stem."""
        for s, e in self.gaps:
            for a in self.att:
                if a["t"] >= e - 0.06:
                    a["first"] = True
                    break


def _tcost(d):
    """Student-t (nu = 3) cost of the distance d (s) of an attack from the prior (asymmetric scale)."""
    return 2.0 * np.log1p((d / (SIGMA_LATE if d > 0 else SIGMA_EARLY)) ** 2 / 3.0)


def assign(stem, prior, after_silence, pins=None):
    """Words in order -> attacks. prior[i] = CTC time (song s) of word i; after_silence[i] = end of a silence (song s) that
    the aligner puts before the word, or None; pins[i] = song time of a pinned word, or None.
    -> list of dicts per word: t (song s), kind "attack" | "ctc" | "pin", att (the attack dict or None), g (weight of
    the attack in t: 1 = exactly its time, less = between the CTC time and the attack, 0 = CTC), margin (cost of
    the best other reading minus the best; None when there is no other), rival (time of that other reading)."""
    n = len(prior)
    pins = pins or [None] * n
    A = stem.att
    at = np.array([a["t"] for a in A])
    states = []                                              # per word: [(time, unary cost, kind, attack index, weight g)]
    for i in range(n):
        c = prior[i] + MU
        if pins[i] is not None:
            states.append([(pins[i], 0.0, "pin", -1, 1.0)])
            continue
        lo, hi = c - WINDOW, c + WINDOW
        if after_silence[i] is not None:
            lo = min(lo, after_silence[i] - 0.06)
        st = []
        for k in np.where((at >= lo) & (at <= hi))[0] if len(at) else []:
            a = A[k]
            u = _tcost(a["t"] - c) - STRENGTH * min(a["db"], 15.0) / 15.0 - (VOICE_BONUS if a["voiced"] else 0.0)
            if after_silence[i] is not None and a["first"] and a["t"] >= after_silence[i] - 0.06:
                u -= FIRST_BONUS
            g = a["g"]                                       # a weak attack only pulls the word towards itself: the time and
            st.append((c + g * (a["t"] - c), (1 - g) * NONE_COST + g * u, "attack", int(k), g))   # the cost are continuous in the dB
        st.append((c, NONE_COST, "ctc", -1, 0.0))
        states.append(st)

    def link(p, q):                                          # cost of word i-1 in state p followed by word i in state q
        gap = 0.02 if (p[2] == "ctc" or q[2] == "ctc" or p[4] < 1 or q[4] < 1) else MIN_GAP
        return 0.0 if q[0] >= p[0] + gap else 10.0

    F = [[s[1] for s in states[0]]]                          # forward min-sum
    bp = [[-1] * len(states[0])]
    for i in range(1, n):
        row, back = [], []
        for q in states[i]:
            best, arg = 1e18, 0
            for j, p in enumerate(states[i - 1]):
                v = F[i - 1][j] + link(p, q)
                if v < best:
                    best, arg = v, j
            row.append(best + q[1])
            back.append(arg)
        F.append(row)
        bp.append(back)
    B = [None] * n                                           # backward min-sum (cost of words i+1.. given word i in state j)
    B[n - 1] = [0.0] * len(states[n - 1])
    for i in range(n - 2, -1, -1):
        B[i] = [min(link(p, q) + q[1] + B[i + 1][m] for m, q in enumerate(states[i + 1])) for p in states[i]]
    best_total = min(F[-1])
    k = int(np.argmin(F[-1]))
    path = [0] * n
    for i in range(n - 1, -1, -1):
        path[i] = k
        k = bp[i][k]
    out = []
    for i in range(n):
        t_i, _, kind, ak, g_i = states[i][path[i]]
        margin, rival = None, None
        for j, s in enumerate(states[i]):
            if j == path[i] or abs(s[0] - t_i) < 0.010 or s[4] < 0.5:      # only another real attack is a second reading
                continue
            tot = F[i][j] + B[i][j]
            if margin is None or tot - best_total < margin:
                margin, rival = tot - best_total, s[0]
        out.append(dict(t=float(t_i), kind=kind, att=A[ak] if ak >= 0 else None, g=g_i, margin=margin, rival=rival))
    for i in range(1, n):                                    # a word that kept its CTC time stays after its neighbour
        if out[i]["kind"] == "ctc" and out[i]["t"] < out[i - 1]["t"] + 0.02:
            out[i]["t"] = out[i - 1]["t"] + 0.02
    return out
