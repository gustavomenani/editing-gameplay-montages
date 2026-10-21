"""The independent end-to-end sync audit: is every picture event of the FINISHED video on its exact frame, and every sound on its exact sample?

Everything is read from the OUTPUT (the decoded frames, the decoded audio, the container's timestamps), never from the render's or the mixer's own
bookkeeping, and compared with (a) what timeline.py (SYNC = 2) says and (b) the REAL song. The delivery gate runs it on the master (gate.py), and
on the upload copy without the master (gate.py --sync-only, which deliver.sh runs on the file that leaves).

usage (from the project folder, with the project's Python; needs timeline.py, src/ (the clips: the muzzle flash), the song and, for the sound checks, audio_report.json):
    python syncaudit.py VIDEO              the whole audit (about 1 minute for a 45 s edit; gate.py --sync-only VIDEO runs exactly this on the upload copy): prints the table (per event: expected frame / measured frame / ms) and the findings; exit 1 on an ERROR
    python syncaudit.py VIDEO --deep       also S10: about 10 frames rendered again with render.py and matched against the file (1-2 minutes more)
    python syncaudit.py VIDEO --legacy     an OLD timeline (SYNC < 2: ceil / beat-domain rules): measure a master of the old pipeline against what
                                           that pipeline meant (cut on ceil of its beat), AND report how far the ceil put each cut from its
                                           nearest frame. Diagnosis only: gate.py refuses an old timeline and says how to update it.
From Python:  audit(video, T, legacy=None, out=print, count_check=True, picture=True, summary=True, deep=False) -> list of dicts {severity, code, where, msg, fix}  (gate.py's shape)

What is measured (S1 .. S10) and how
  S1 container   video pts: 1/60 s lattice (ticks per frame from the time base), count == T.N_FRAMES. A step off by more than half a tick: WARN pts-gap;
                 the cumulative error above 1 ms: ERROR pts-gap; another count: ERROR frame-count.
  S2 audio/song  the decoded audio (aresample=async=1:first_pts=0, so a late or early track start shows) against the song at T.MUSIC_T0: band-pass 80-6000 Hz,
                 FFT cross-correlation, parabolic peak = the lag in samples; then 2 s windows every 1 s (min, max, slope). |lag| > 1 ms: ERROR av-offset
                 (> 0.25 ms WARN); the lag moving by > 1 ms inside the section: ERROR av-drift; no match (peak < 0.5): ERROR audio-unmatched.
  S3 gunshots    placement, independent of WHICH attack of the clip is the shot: for a kill audio_report.json says was placed on its measured onset (state measured: onset_ms, hit_sample) the clip's
                 OWN 60 ms excerpt is matched-filtered against the master's song-free residual (song subtracted, gain fitted in 50 ms blocks, 1.5-12 kHz) within +-20 ms of the hit: sitting more than
                 1 ms from the hit, or missing from the mix (match < 0.3): ERROR kill-audio. A louder attack > 15 ms after the placed one: WARN kill-audio-double. The loudest-attack detector
                 (kill_lags.onset_near) only judges kills without a placement check (house style `heard`: ERROR beyond 4 ms, WARN from 2 ms; others WARN beyond 8.3 ms). Not measurable: WARN gunshot-unmeasured.
  S4 accents     per kill: the frame of the exposure pop (onset of the luma step in +-3 frames of the shot) and, with timeline IMPACT, of the RGB split burst (the first frame with a real share of
                 the window's largest split). Both on the SHOT frame (nearest_frame(shown beat)). A level 3 shot shows the INVERTED monochrome frame there (colour collapses; no split can be seen on it):
                 the burst must start the frame after. A cut / blur-in on the kill: not measurable (WARN fx-unmeasured).
                 Another frame: ERROR fx-frame. (Bumps, T.BUMPS: the pop on nearest_frame(beat) - HIT_LEAD: ERROR bump-frame.)
  S5 flash       the kill's muzzle flash: the difference image of the SOURCE frames K-1 -> K (the clip, K = the take's time map at the shot) is looked for in the master's
                 frame differences around the shot (zero-mean correlation, >= 0.45 or the kill counts as not measurable, never as a pass). The flash MUST be on the
                 shot frame and absent on the frame before: else ERROR kill-flash. This replaces check.py's printed prediction.
  S7 cuts        the frame where every take's picture starts (clearest layout step in +-8 of the expected frame; none clear: WARN cut-unmeasured, never a pass = T.nearest_frame(r0)) must be the expected
                 one: ERROR cut-frame (a dropped / repeated frame or a bad part join moves all later cuts: it names the take). MUSIC: the cut's musical moment (m0) must
                 lie within half a frame of a line of the 1/2, 1/4 or 1/8-beat lattice or of a measured attack of the song (beat_hits.attacks: the skill's one definition of a
                 hit's time), else WARN cut-grid (ERROR beyond 2 frames). The kills' musical beats (T.HITS) must read 0 ms (within 1 ms) against a measured attack: WARN kill-hit
                 up to a frame away, ERROR beyond a frame (the beat was not taken from the measured hit).
  S8 words       the first change of the word's pixels (the centre band) must be on nearest_frame(a) - HIT_LEAD: ERROR word-frame. (Where the cues sit against the SUNG
                 attacks is lyrics_audit.py's job, which gate.py runs: code word-sung.)
  S9 grid        the phase of the song's strong drum hits against BEAT0 + k * PER/2 (or PER/4 for a syncopated song): ERROR grid-phase when the hits agree (concentration >= 0.5)
                 and the grid is more than 25 ms off; WARN grid-unmeasured when they do not agree.
  S10 deep       (--deep) the part joins and some cut frames rendered again with render.py and compared with the file's frames -2..+2 by PSNR: the best match must be the frame itself
                 (ERROR render-mismatch); only the argmax and its margin count (the file is sharpened and encoded: the absolute PSNR is 26-29 dB).
Not measurable events are LISTED as such: the audit never turns "could not measure" into a pass."""
import argparse, json, math, os, subprocess, sys, time
import numpy as np

SR = 48000
LAG_ERR_MS, LAG_WARN_MS = 1.0, 0.25            # S2: |lag| above this = ERROR / WARN (the delivered sound must sit on the song within 1 ms)
DRIFT_ERR_MS = 1.0                              # S2: the lag moving by more than this inside the section
GUN_BAR_MS = 2.0                                # S3: the bar for a gunshot placed on its own measured onset: within this of the musical hit (WARN beyond)
GUN_ERR_MS = 4.0                                # S3: ... and ERROR beyond this: the onset read off the finished mix (song subtracted, loud shots, the 6 ms fade-ins) is good to about 2 ms,
                                                #     so a shot 2-4 ms off is listed, one further off is certainly not on its hit
GUN_WARN_MS = 8.3                               # S3: any other gunshot (placed with the clip's usual offset: not verified): WARN beyond half a frame
FLASH_MIN_CORR = 0.45                           # S5: below this the flash is not found (not measurable)
HALF = 0.5 + 1e-3                               # half a frame, in frames, with a millisecond of room
HIT_EXACT_MS = 1.0                              # a kill the drafter put on a measured hit reads 0.000 ms against beat_hits.attacks; beyond this it was not taken from a measured hit
VERIFIED_STATES = ("measured", "donor", "heard")      # audio_report.json: the gunshot was placed on its own measured onset (refstyle: measured, donor; house: heard)
NONWAIVABLE = ("av-offset", "av-drift", "frame-count", "cut-frame", "pts-gap")       # gate.py: these ERRORs cannot be accepted


def item(sev, code, where, msg, fix=""):
    return dict(severity=sev, code=code, where=where, msg=msg, fix=fix)


# ------------------------------------------------------------------------------------------------------------- helpers
def _ff():
    from ff import FF, FFPROBE
    return FF, FFPROBE


def decode_audio(path, honour_pts=True):
    """Mono 48 kHz float64. honour_pts: the stream's timestamps are honoured (a first sample later than 0 becomes silence, an early one is cut),
    so a late or early audio track is SEEN as late or early."""
    FF, _ = _ff()
    af = ["-af", "aresample=async=1:first_pts=0"] if honour_pts else []
    raw = subprocess.run([FF, "-v", "error", "-i", path, "-map", "0:a:0"] + af + ["-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def band(x, lo, hi, sr=SR):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / sr)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, n=len(x))


def xlag(ref, sig, maxlag):
    """Lag in samples (sub-sample, parabolic peak) with sig[n] ~ ref[n - lag]; positive = sig is LATE. Plus the normalised peak (1 = identical)."""
    n = min(len(ref), len(sig))
    ref, sig = ref[:n], sig[:n]
    N = 1 << int(np.ceil(np.log2(2 * n)))
    w = np.hanning(n)
    a, b = ref * w, sig * w
    c = np.fft.irfft(np.fft.rfft(b, N) * np.conj(np.fft.rfft(a, N)), N)
    c = np.concatenate([c[-maxlag:], c[:maxlag + 1]])
    k = int(np.argmax(c))
    pk = float(c[k]) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12)
    if 0 < k < len(c) - 1:
        p, q, r = c[k - 1], c[k], c[k + 1]
        k = k + 0.5 * (p - r) / (p - 2 * q + r)
    return k - maxlag, pk


def _probe_video(path):
    FF, FFPROBE = _ff()
    r = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-of", "json", path], capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return json.loads(r.stdout or "{}").get("streams", [])
    except ValueError:
        return []


# ------------------------------------------------------------------------------------------------------------- the expected events
class Plan:
    """What timeline.py says, as exact integer frames. sync2: the contract of timeline_ref_example.py (cut = nearest_frame(r0) = nearest_frame(m0) - CUT_LEAD;
    shot = nearest_frame(shown beat); bump / word = nearest_frame(beat) - HIT_LEAD). legacy: the old rules (a cut on ceil of its beat, an accent on the nearest frame)."""

    def __init__(self, T, legacy):
        self.T, self.legacy = T, legacy
        self.fps, self.n = T.FPS, T.N_FRAMES
        self.cut_lead = 0 if legacy else int(getattr(T, "CUT_LEAD", 1))
        self.hit_lead = 0 if legacy else int(getattr(T, "HIT_LEAD", 1))
        self.nf = (lambda r: int(math.floor((r - T.R0) * T.FPB + 0.5))) if legacy else T.nearest_frame
        self.problems = []
        self.cuts, self.shots, self.bumps, self.words = [], [], [], []
        for j, s in enumerate(T.SEGS):
            if j == 0:
                continue
            x = (s["r0"] - T.R0) * T.FPB
            nearest = self.nf(s["r0"])
            exp = int(math.ceil(x - 1e-6)) if legacy else nearest
            hard = not (len(s.get("tin", ())) > 1 and s["tin"][1])          # a transition that overlaps both takes has no cut frame
            m0 = s.get("m0", s["r0"])
            if not legacy and hard and self.nf(m0) - self.cut_lead != exp:
                self.problems.append("segment %d: nearest_frame(m0) - CUT_LEAD = %d, but nearest_frame(r0) = %d (timeline.py is not on the SYNC 2 contract)" % (j, self.nf(m0) - self.cut_lead, exp))
            self.cuts.append(dict(j=j, expected=exp, nearest=nearest, x=x, r0=s["r0"], m0=m0, hard=hard))
        hits = {id(s): list(s.get("hits") or [k for k, _ in s["kills"]]) for s in T.SEGS}
        for i, s in enumerate(T.SEGS):
            for (k, lv), h in zip(s["kills"], hits[id(s)]):
                self.shots.append(dict(i=i, k=k, hit=h, lv=lv, expected=self.nf(k), x=(k - T.R0) * T.FPB, clip=s["clip"], seg=s))
        for b in getattr(T, "BUMPS", []) or []:
            self.bumps.append(dict(beat=b[0], expected=self.nf(b[0]) - self.hit_lead, w=b[1] if len(b) > 1 else 1.0))
        for b in getattr(T, "PULSES", []) or []:                                    # the house style's accents without a kill: musical beats, shown like a shot (nearest_frame - HIT_LEAD)
            self.bumps.append(dict(beat=b[0], expected=self.nf(b[0]) - self.hit_lead, w=b[1] if len(b) > 1 else 1.0))
        for a_, b_, wd, st in getattr(T, "TEXT", []) or []:
            self.words.append(dict(a=a_, word=wd, expected=self.nf(a_) - self.hit_lead, legible=self.nf(a_)))


# ------------------------------------------------------------------------------------------------------------- S1 container
def container(video, T, plan, A):
    FF, FFPROBE = _ff()
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts", "-of", "json", video], capture_output=True, text=True)
    try:
        P = json.loads(r.stdout or "{}").get("packets", [])
    except ValueError:
        P = []
    streams = _probe_video(video)
    vs = [s for s in streams if s.get("codec_type") == "video"]
    if not P or not vs:
        A.add("ERROR", "bad-video", video, "no video packets that ffprobe can read")
        return None
    pts = np.sort(np.array([int(p["pts"]) for p in P if p.get("pts") not in (None, "N/A")]))
    d = np.diff(pts)
    num, den = (int(v) for v in vs[0]["time_base"].split("/"))
    step = den / num / T.FPS                                          # ticks per frame (256 at 1/15360)
    bad = np.nonzero(np.abs(d - step) > 0.5)[0]
    cum = (pts - pts[0] - np.arange(len(pts)) * step) * num / den * 1000.0          # ms against the 1/60 s lattice
    st = {x["codec_type"]: float(x.get("start_time") or 0) for x in streams}
    A.say("container  frames %d (timeline %d)  pts step %s ticks (lattice %g): %d irregular step(s)%s | max |pts - n/60| %.3f ms" % (
        len(pts), T.N_FRAMES, sorted(set(int(v) for v in d))[:4], step, len(bad),
        " at frame " + ", ".join(str(int(i) + 1) for i in bad[:6]) if len(bad) else "", float(np.abs(cum).max()) if len(cum) else 0.0))
    A.say("           stream start_time video %.6f s audio %.6f s" % (st.get("video", 0), st.get("audio", 0)))
    if A.count_check and len(pts) != T.N_FRAMES:
        A.add("ERROR", "frame-count", video, "%d frames in the file, %d in the timeline (a dropped or repeated frame, a truncated render, or another timeline)" % (len(pts), T.N_FRAMES),
              "render the master again: bash run.sh master.mp4")
    if len(cum) and np.abs(cum).max() > 1.0:
        n_bad = int(np.argmax(np.abs(cum) > 1.0))
        A.add("ERROR", "pts-gap", "output frame %d on" % n_bad, "the timestamps drift from the 1/%d s lattice by %.2f ms (a join of the parts, a dropped or repeated frame)" % (T.FPS, float(np.abs(cum).max())),
              "render again; the three parts of run.sh must join on exact multiples of the frame time")
    elif len(bad):
        A.add("WARN", "pts-gap", "output frames " + ", ".join(str(int(i) + 1) for i in bad[:8]),
              "%d video timestamp step(s) are not exactly %g ticks (the largest error %.1f ticks = %.2f ms): a part join that is not on the lattice; harmless below 1 ms" % (
                  len(bad), step, float(np.abs(d[bad] - step).max()), float(np.abs(d[bad] - step).max()) * num / den * 1000.0))
    return len(pts)


# ------------------------------------------------------------------------------------------------------------- S2 audio against the song
_SONG = {}


def song(T):
    """The song as the audio mixer reads it: mono 48 kHz float64 (whole file)."""
    key = os.path.abspath(T.MUSIC)
    if key not in _SONG:
        _SONG.clear()
        _SONG[key] = decode_audio(T.MUSIC, honour_pts=False)
    return _SONG[key]


def audio_vs_song(video, T, A):
    """-> (decoded output audio, lag in samples) or (None, None)."""
    x = decode_audio(video)
    if len(x) < SR:
        A.add("ERROR", "no-audio", video, "the file has no decodable audio (or under a second of it)")
        return None, None
    m = song(T)
    a = int(round(T.MUSIC_T0 * SR))
    ns = int(round((T.R1 - T.R0) * T.PER * SR))
    ref = m[a:a + ns]
    L = min(len(ref), len(x))
    ref, xs = band(ref[:L], 80, 6000), band(x[:L], 80, 6000)
    lag, pk = xlag(ref, xs, int(0.25 * SR))                                   # +-250 ms: wider would let a periodic song match its own next beat
    ms = lag / SR * 1000.0
    A.lag_ms, A.lag = ms, lag
    # windows of 2 s every 1 s, the signal moved by the global lag first, so a 240 ms offset is searched around its own lag
    sh = int(round(lag))
    if sh >= 0:
        xs2 = np.concatenate([xs[sh:], np.zeros(sh)])
    else:
        xs2 = np.concatenate([np.zeros(-sh), xs[:L + sh]])
    W, H = 2 * SR, SR
    ts, ls, ps, n_win = [], [], [], 0
    for s in range(0, L - W, H):
        r = ref[s:s + W]
        if np.sqrt((r ** 2).mean()) < 1e-3:
            continue
        n_win += 1
        l, p = xlag(r, xs2[s:s + W], int(0.1 * SR))
        if p > 0.3:
            ts.append(s / SR)
            ls.append((l + sh) / SR * 1000.0)
            ps.append(p)
    ts, ls = np.array(ts), np.array(ls)
    slope = float(np.polyfit(ts, ls, 1)[0]) if len(ts) > 2 else 0.0
    spread = float(ls.max() - ls.min()) if len(ls) else 0.0
    # a drifting track correlates badly as a whole (the click-like hits slide apart): when most 2 s windows still find the song (match above 0.3) it is the song, drifting; the offset is then the windows' median
    matched = pk >= 0.5 or (len(ps) >= 3 and len(ps) >= 0.6 * n_win)
    if pk < 0.5 and matched:
        ms = float(np.median(ls))
        lag = ms * SR / 1000.0
        A.lag_ms, A.lag = ms, lag
    A.say("audio/song  %+8.3f ms (%+.1f samples, peak %.3f) | %d windows: min %+.3f max %+.3f spread %.3f ms, slope %+.4f ms/s (%+.2f ms over the section)" % (
        ms, lag, pk, len(ls), ls.min() if len(ls) else 0.0, ls.max() if len(ls) else 0.0, spread, slope, slope * L / SR))
    if not matched:
        A.add("ERROR", "audio-unmatched", "audio", "the decoded audio does not contain the song section the timeline says (match %.2f): another song, another section, or an offset above 0.25 s" % pk,
              "mux mix.wav again (audio.py, then run.sh); python gate.py --sync-only on the result")
    elif abs(ms) > LAG_ERR_MS:
        A.add("ERROR", "av-offset", "audio", "the sound sits %+.2f ms (%+.1f samples = %.2f frames) from where the timeline puts the song; the limit is %.1f ms%s" % (
            ms, lag, ms / (1000.0 / T.FPS), LAG_ERR_MS, " (+ = the sound is late)"),
              "the master chain must not delay the sound: audio.master_chain() compensates the limiter's look-ahead; run.sh again, then deliver.sh")
    elif abs(ms) > LAG_WARN_MS:
        A.add("WARN", "av-offset", "audio", "the sound sits %+.2f ms from the song (limit %.1f ms)" % (ms, LAG_ERR_MS), "")
    if matched and spread > DRIFT_ERR_MS:
        A.add("ERROR", "av-drift", "audio", "the offset moves by %.2f ms inside the section (slope %+.3f ms/s = %+.2f ms over the video): the audio's tempo is not the song's" % (spread, slope, slope * L / SR),
              "the audio must be the song at its own speed (no atempo / resample drift): run.sh again")
    return x, lag


# ------------------------------------------------------------------------------------------------------------- the song's attacks
def attacks_for(T, A):
    """Every attack of the song's section as the SKILL's one definition measures it (beat_hits.attacks: half-height of the band's envelope across its steepest
    rise, class bias subtracted, the way the drafters measure the hits they write into timeline.py): list of (t in track seconds, band, rise). Cached on the audit.
    The slice is the one beat_hits.measure_t takes (the video plus 3 s on both sides), so a kill the drafter put on a measured hit reads 0.000 ms here."""
    if A.attacks is not None:
        return A.attacks
    import beat_hits
    t_lo, t_hi = max(0.0, T.beat_time(T.R0) - 3.0), T.beat_time(T.R1) + 3.0
    m = beat_hits.decode(T.MUSIC)
    a0, a1 = int(t_lo * beat_hits.SR), min(len(m), int(t_hi * beat_hits.SR))
    att = beat_hits.attacks(m[a0:a1], a0 / beat_hits.SR)
    A.attacks = [a for a in att if T.MUSIC_T0 - 0.05 <= a[0] <= T.MUSIC_T0 + (T.R1 - T.R0) * T.PER + 0.05]
    return A.attacks


# ------------------------------------------------------------------------------------------------------------- S3 gunshots
def _music_aligned(x, lag, T):
    """The song section as it sits in the decoded audio x (moved by the S2 lag), same length as x."""
    m = song(T)
    a = int(round(T.MUSIC_T0 * SR))
    ns = len(x)
    L = int(round(lag))
    mus = np.zeros(ns)
    seg = m[a:a + ns - max(L, 0)]
    if L >= 0:
        mus[L:L + len(seg)] = seg
    else:
        mus[:len(seg) + L] = seg[-L:len(seg)]
    return mus, a / SR, L


def _residual(x, mus, c, half=0.6):
    """The sound around sample c of x with the song taken out (the song's gain fitted in 50 ms blocks, interpolated), band-passed 1.5-12 kHz: -> (residual, first sample g0 of the window)."""
    ns = len(x)
    g0, g1 = max(0, c - int(half * SR)), min(ns, c + int(half * SR))
    xx, mm = x[g0:g1], mus[g0:g1]
    blk = int(0.05 * SR)
    gs = []
    for s in range(0, len(xx) - blk, blk):
        den = mm[s:s + blk] @ mm[s:s + blk]
        gs.append((xx[s:s + blk] @ mm[s:s + blk]) / den if den > 1e-9 else 0.0)
    gi = np.interp(np.arange(len(xx)), np.arange(len(gs)) * blk + blk / 2, gs)
    return band(xx - gi * mm, 1500, 12000), g0


def gunshots(x, lag, T, plan, A, skip=()):
    """-> {shot index: u ms or None}: the onset of the LOUDEST gunshot-like attack near the hit (kill_lags.onset_near on the song-free residual) minus the musical time of the hit, the S2 lag taken
    out. It does not say which attack is THE shot (a clip's shot can have a second, louder attack 36 ms later): placements() checks the placed excerpt itself. skip: kills with no gunshot (muted)."""
    import kill_lags
    mus, t0, L = _music_aligned(x, lag, T)
    ns = len(x)
    res = {}
    for q, sh in enumerate(plan.shots):
        if q in skip:
            res[q] = None
            continue
        tk = T.beat_time(sh["hit"]) - t0                                         # musical time of the hit inside the output audio
        c = int(round(tk * SR)) + L                                              # where the hit sits in THIS audio (the S2 lag moves it)
        if min(ns, c + int(0.6 * SR)) - max(0, c - int(0.6 * SR)) < SR // 2 or c - max(0, c - int(0.6 * SR)) < int(0.35 * SR):
            res[q] = None
            continue
        rest, g0 = _residual(x, mus, c)
        env = np.convolve(rest ** 2, np.ones(48) / 48, "same")
        w0, w1 = max(0, c - g0 - int(0.040 * SR)), min(len(env), c - g0 + int(0.060 * SR))
        e = env[w0:w1]
        qb = max(0, c - g0 - int(0.30 * SR))
        base = np.median(env[qb:c - g0 - int(0.10 * SR)]) + 1e-12
        if float(e.max()) < 20 * base:                                              # no shot that stands out of the noise: not measurable (listed, never guessed)
            res[q] = None
            continue
        # the attack as the skill defines it (kill_lags.attack: the first sample where a causal 4-sample RMS of the first difference reaches 7 % of the shot's peak; the same rule
        # audio.py places the shots by), on the song-free rest of the sound: coarse bin first, then the sample
        on = kill_lags.onset_near(np.diff(rest), c - g0, int(0.05 * SR))
        if on is None or on < int(0.001 * SR):
            res[q] = None
            continue
        res[q] = ((g0 + on) / SR - tk) * 1000.0 - A.lag_ms
    return res


_CLIP_AUDIO = {}


def _clip_mono(clip):
    """The clip's sound on its file clock (the one audio.py cuts the gunshots from), mono 48 kHz; None without an audio track."""
    if clip not in _CLIP_AUDIO:
        import clipio
        FF, _ = _ff()
        raw = subprocess.run([FF, "-v", "error", "-i", clipio.path(clip), "-map", "0:a:0", "-af", "aresample=async=1:first_pts=0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
        _CLIP_AUDIO[clip] = np.frombuffer(raw, np.float32).astype(np.float64) if len(raw) else None
    return _CLIP_AUDIO[clip]


PLACE_BAR_MS = 1.0                              # S3: the placed excerpt may sit this far from the hit (the placement is by whole samples: 0.02 ms)
PLACE_MIN_CORR = 0.5                            # S3: a match below this is not a match (0.3 and below: the excerpt is not in the mix at all)


def placements(x, lag, T, plan, A, rep):
    """S3, independent of WHICH attack of the clip is 'the shot'. For every kill whose audio_report.json entry says it was placed on its own measured onset (state measured: onset_ms after the
    flash frame, hit_sample), the clip's OWN audio excerpt (the 60 ms from clip time t(K) + onset_ms) is matched-filtered against the master's song-free residual within +-20 ms of the hit.
    -> {shot index: (misplacement ms or None, correlation or None)}: misplacement = where the excerpt sits minus the hit sample (+ = late; ~0 for a correct mix); None when the match is below
    PLACE_MIN_CORR. Kills without such an entry (house style, donors, unverified states, no clip here) are not in the result."""
    import clipio
    mus, t0, L = _music_aligned(x, lag, T)
    out = {}
    PRE, N, W = int(0.002 * SR), int(0.062 * SR), int(0.020 * SR)
    for q, sh in enumerate(plan.shots):
        r = rep.get(round(sh["hit"], 3))
        if not r or r.get("state") != "measured" or r.get("onset_ms") is None or r.get("hit_sample") is None:
            continue
        try:
            mono = _clip_mono(sh["clip"])
            K = float(sh["seg"]["map"](sh["k"])[0])
            o = int(round((float(clipio.n2t(sh["clip"], K)) + r["onset_ms"] / 1000.0) * SR))
        except Exception:
            continue
        if mono is None or o - PRE < 0 or o + N > len(mono):
            continue
        tpl = band(mono[o - 4800:o + N + 4800], 1500, 12000)[4800 - PRE:4800 + N]              # filtered with margin, then cut: no edge ringing
        c = int(r["hit_sample"]) + L                                                             # where the hit sample sits in THIS audio
        rest, g0 = _residual(x, mus, c, 0.4)
        a0 = c - g0 - PRE - W
        if a0 < 0 or a0 + len(tpl) + 2 * W + 1 > len(rest):
            continue
        win = rest[a0:a0 + len(tpl) + 2 * W]
        num = np.correlate(win, tpl, "valid")                                                   # lag index i: the excerpt starts at a0 + i
        cs = np.concatenate([[0.0], np.cumsum(win ** 2)])
        den = np.sqrt((cs[len(tpl):len(tpl) + len(num)] - cs[:len(num)]) * float(tpl @ tpl)) + 1e-12
        cc = num / den
        k = int(np.argmax(cc))
        pk = float(cc[k])
        if 0 < k < len(cc) - 1:
            p_, q_, r_ = cc[k - 1], cc[k], cc[k + 1]
            kk = k + 0.5 * (p_ - r_) / (p_ - 2 * q_ + r_)
        else:
            kk = float(k)
        out[q] = (((kk - W) / SR) * 1000.0 if pk >= PLACE_MIN_CORR else None, pk)
    return out


# ------------------------------------------------------------------------------------------------------------- the picture
class Picture:
    """One pass over the decoded frames (480x270, or 270x480 for the vertical frame): per frame the mean luma, the mean absolute difference to the previous frame,
    the share of changed pixels in the centre band (words), the window's gray image at 192x108 (muzzle flash) and, near the shots, the R-B phase shift (burst)."""

    def __init__(self, video, T, plan, A):
        FF, _ = _ff()
        import cv2
        self.vert = False
        vs = [s for s in _probe_video(video) if s.get("codec_type") == "video"]
        vw, vh = int(vs[0]["width"]), int(vs[0]["height"])
        self.vert = vh > vw
        W, H = (270, 480) if self.vert else (480, 270)
        self.W, self.H = W, H
        # the window of the footage: refstyle frame.py (horizontal: the whole frame; vertical: the 16:9 window), the house style: 1080x912 at y 470 showing the middle 1280 px
        try:
            import frame as _fr
            wy, wh, ww = _fr.WIN_Y, _fr.WIN_H, _fr.W
            self.src_x = (0, 1920)
        except ImportError:
            wy, wh, ww = (470, 912, 1080) if self.vert else (0, vh, vw)
            self.src_x = (320, 1600) if self.vert else (0, 1920)
        sc = W / float(ww)
        self.win = (int(round(wy * sc)), int(round((wy + wh) * sc)))
        n_need = set()
        for sh in plan.shots:
            n_need.update(range(sh["expected"] - 6, sh["expected"] + 8))
        proc = subprocess.Popen([FF, "-v", "error", "-i", video, "-an", "-vf", "scale=%d:%d:flags=area" % (W, H), "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
        fsz = W * H * 3
        Y, D, DS, WD, G, RB, SAT = [], [], [], [], [], {}, []
        prev = None
        prev_s = None
        hwin = cv2.createHanningWindow((W, H), cv2.CV_32F)
        b0, b1 = int(0.36 * H), int(0.64 * H)
        n = 0
        while True:
            buf = proc.stdout.read(fsz)
            if len(buf) < fsz:
                break
            fr = np.frombuffer(buf, np.uint8).reshape(H, W, 3).astype(np.float32)
            g = 0.299 * fr[..., 0] + 0.587 * fr[..., 1] + 0.114 * fr[..., 2]
            Y.append(float(g.mean()))
            SAT.append(float((fr.max(2) - fr.min(2)).mean()))                      # colour: the inverted monochrome frame of a level 3 shot has none
            gs = cv2.resize(g, (32, 18), interpolation=cv2.INTER_AREA)           # the layout of the picture: a blur-in or a lean-in leaves it, a cut changes it
            DS.append(0.0 if prev_s is None else float(np.abs(gs - prev_s).mean()))
            prev_s = gs
            if prev is None:
                D.append(0.0)
                WD.append(0.0)
            else:
                D.append(float(np.abs(g - prev).mean()))
                WD.append(float((np.abs(g[b0:b1] - prev[b0:b1]) > 30).mean() * 100.0))
            G.append(cv2.resize(g[self.win[0]:self.win[1]], (192, 108), interpolation=cv2.INTER_AREA).astype(np.uint8))
            if n in n_need:
                RB[n] = float(cv2.phaseCorrelate(np.ascontiguousarray(fr[..., 0]), np.ascontiguousarray(fr[..., 2]), hwin)[0][0])
            prev = g
            n += 1
        proc.wait()
        self.n = n
        self.Y, self.D, self.DS, self.WD, self.G, self.RB, self.S = np.array(Y), np.array(D), np.array(DS), np.array(WD), G, RB, np.array(SAT)

    def diff_pos(self, n):
        return np.maximum(self.G[n].astype(np.float32) - self.G[n - 1].astype(np.float32), 0.0)


def _z(v):
    v = v.ravel() - v.mean()
    return v / (np.linalg.norm(v) + 1e-9)


def measure_cuts(P, plan, A):
    """For every take: the frame where its picture starts. The measure is the LAYOUT jump: the mean absolute difference of the pictures reduced to 32 x 18 (a blur-in, a streak or the
    lean into the cut moves it little, a cut changes it), as a step against the frame before (DS[n] - max(DS[n-1], DS[n-2])). The search is +-8 frames around the expected frame (bounded by the
    neighbouring cuts): a take that came in late or early is FOUND and reported (cut-frame), not lost. The cut is the expected frame only when it carries a clear step (>= 2 gray levels) that is the largest of the window (within 10 %: a take that came in late
    replays the outgoing take, and its true cut is a later, bigger step); the accent frames of the kills (nk .. nk+2) and bumps are not candidates; else the largest step, provided it is clear (>= 2 levels and 1.4 times every earlier step of the window); else None (cut-unmeasured: listed, never a pass).
    -> the plan's cuts with `measured` (the frame or None) and `step`."""
    out = []
    ex = [c["expected"] for c in plan.cuts]
    accents = set()
    for sh in plan.shots:
        accents.update((sh["expected"], sh["expected"] + 1, sh["expected"] + 2))        # pop / flash / burst steps of a shot
    for b in plan.bumps:
        accents.update((b["expected"], b["expected"] + 1))
    for q, c in enumerate(plan.cuts):
        e = c["expected"]
        lo, hi = e - 8, e + 8
        if q > 0:
            lo = max(lo, (ex[q - 1] + e) // 2 + 1)
        if q + 1 < len(ex):
            hi = min(hi, (e + ex[q + 1]) // 2)
        cand = [n for n in range(max(2, lo), min(P.n, hi + 1)) if n == e or n not in accents]     # a kill's / bump's own accent frames are not cuts
        c.update(measured=None, step=0.0)
        out.append(c)
        if not cand or not c["hard"]:
            continue
        st = {n: float(P.DS[n] - max(P.DS[n - 1], P.DS[n - 2])) for n in cand}
        order = sorted(cand, key=lambda n: -st[n])
        n = order[0]
        before = max([st[m] for m in cand if m < n] or [0.1])                       # what comes BEFORE the candidate competes (a late take first replays the outgoing one: a small rewind step);
        c["step"] = st[n]                                                           # what follows it is the take's own blur-in / lean (secondary steps) and does not
        if e in st and st[e] >= 2.0 and st[e] >= 0.9 * st[n]:
            c["measured"] = e
        elif st[n] >= 2.0 and st[n] >= 1.4 * max(before, 0.1):
            c["measured"] = n
    return out


def flash_template(clip, tmap, k, src_x):
    """The muzzle flash of one kill as an image: the positive difference of the SOURCE frames K-1 -> K (K = the take's time map at the shot beat k, rounded), gray 192x108 over the
    columns src_x of the 1920-wide source (what the master's window shows), zero-mean and unit norm. -> (template or None, why not)."""
    import cv2
    try:
        import clipio
        K = int(round(float(tmap(k)[0])))
        src = clipio.read_frames(clip, K - 1, K, crop=False)
    except Exception as ex:
        return None, "%s: %s" % (type(ex).__name__, str(ex)[:80])
    g = [cv2.resize(cv2.cvtColor(cv2.cvtColor(a, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2GRAY)[:, src_x[0]:src_x[1]], (192, 108), interpolation=cv2.INTER_AREA).astype(np.float32) for a in src]
    tpl = np.maximum(g[1] - g[0], 0)
    if tpl.std() < 0.5:
        return None, "no flash in the source (K-1 -> K does not change)"
    return _z(tpl), None


def flash_templates(jobs, workers=6):
    """flash_template for every (clip, tmap, k, src_x) of `jobs`, the clip reads (one ffmpeg each) in parallel -> list of (template, why not)."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(lambda j: flash_template(*j), jobs))


def flash_score(zt, why, e, diff_at):
    """S5 for one kill, given its template. The flash is looked for in the master's positive frame differences `diff_at(n)` (a 108x192 float array, None outside the video) by zero-mean correlation.
    The flash OF THIS SHOT can only be on e-2 .. e+2 (e = the shot frame): -> dict(flash = the frame of the best match there (None below FLASH_MIN_CORR: not measurable, never a pass), corr, c0 = the
    correlation on frame e, c_prev = on frame e-1, err = why there was no template) plus the best match 3..8 frames away: wide_n, wide_corr (another shot of the same weapon, or this shot moved
    inside its take: audit() decides which from the pop / burst)."""
    out = dict(flash=None, corr=None, c0=None, c_prev=None, err=why, wide_n=None, wide_corr=None)
    if zt is None:
        return out
    cs = {}
    for n in range(e - 8, e + 9):
        d = diff_at(n)
        if d is not None:
            cs[n] = float(zt @ _z(d))
    near = {n: v for n, v in cs.items() if abs(n - e) <= 2}
    far = {n: v for n, v in cs.items() if abs(n - e) >= 3}
    if far:
        wn = max(far, key=far.get)
        out.update(wide_n=wn, wide_corr=far[wn])
    if not near:
        return out
    n = max(near, key=near.get)
    out.update(corr=near[n], c0=cs.get(e), c_prev=cs.get(e - 1))
    if near[n] >= FLASH_MIN_CORR:
        out["flash"] = n
    return out


def _cut_window(plan, e, span=(-3, 9)):
    return any(c["expected"] + span[0] <= e + 3 and e - 3 <= c["expected"] + span[1] for c in plan.cuts)


def measure_shots(P, T, plan, A):
    """Per shot: pop frame (luma), burst frame (RGB split), muzzle flash onset frame + correlation. Each None when not measurable."""
    impact = getattr(T, "IMPACT", None)
    tpls = dict(zip((id(sh) for sh in plan.shots), flash_templates([(sh["clip"], sh["seg"]["map"], sh["k"], P.src_x) for sh in plan.shots])))      # the source reads, in parallel
    for sh in plan.shots:
        e = sh["expected"]
        sh.update(pop=None, burst=None, burst_exp=e, flash=None, corr=None, corr_prev=None, popv=None, wide_n=None, wide_corr=None)
        if e < 4 or e + 4 >= P.n:
            continue
        clear = not _cut_window(plan, e, (-3, 8))
        if clear:
            dl = np.zeros(P.n)
            dl[1:] = np.diff(P.Y)
            w = list(range(e - 3, e + 4))
            inv = None
            if sh["lv"] == 3 and impact is not None:                                   # the inverted monochrome frame: its colour collapses against the frame before
                inv = next((q for q in w if P.S[q - 1] >= 4.0 and P.S[q] < 0.4 * P.S[q - 1]), None)
            if inv is not None:
                sh["pop"], sh["popv"], sh["burst_exp"] = inv, float(abs(dl[inv])), inv + 1   # no RGB split can be seen ON the inverted frame: the burst starts on the next one, by design
            else:
                step = {q: (abs(dl[q]) if sh["lv"] == 3 else dl[q]) for q in w}           # level 3 without the inverted frame: the biggest luma step either way
                top = max(step.values())
                if top >= max(0.6, 0.02 * P.Y[max(0, e - 4)]):                          # a real step (at least 0.6 gray levels and 2 %)
                    n = next(q for q in w if step[q] >= 0.5 * top)                     # ONSET: the first frame of the step (the peak is the same frame for a one-frame accent)
                    sh["pop"], sh["popv"] = n, float(step[n])
            if impact is not None and P.RB:
                base = float(np.median([abs(P.RB[j]) for j in range(e - 6, e - 2) if j in P.RB] or [0.1]))
                win = {j: abs(P.RB[j]) for j in range(e - 3, e + 7) if j in P.RB and j != inv}
                if win:
                    mx = max(win.values())
                    if mx >= max(0.2, 3 * base):                                        # ONSET = the first frame that has a real share of the window's largest split, not the argmax (the split is
                        sh["burst"] = next(j for j in sorted(win) if win[j] >= max(0.12, 2.5 * base, 0.3 * mx))      # measured at 480 px: 0.24 px on the first frame, 0.64 on the next, seen on a real master)
        m = flash_score(*tpls[id(sh)], e, lambda n: P.diff_pos(n) if 1 <= n < P.n else None)
        sh.update(flash=m["flash"], corr=m["corr"], corr_prev=m["c_prev"], corr_at=m["c0"], wide_n=m["wide_n"], wide_corr=m["wide_corr"])
        if m.get("err"):
            sh["flash_err"] = m["err"]
    return plan.shots


# ------------------------------------------------------------------------------------------------------------- S8 words
def measure_words(P, plan, A):
    for w in plan.words:
        e = w["expected"]
        w.update(first=None, why="")
        if e < 14 or e + 6 >= P.n:
            w["why"] = "edge of the video"
            continue
        base = float(np.median(P.WD[max(1, e - 12):e - 3]))
        if base > 1.0 or P.WD[max(1, e - 6):e].max() > 2.0:
            w["why"] = "the picture behind the word moves"
            continue
        n = next((q for q in range(e - 3, e + 5) if P.WD[q] > max(2.0, 4 * base)), None)
        w["first"] = n
        if n is None:
            w["why"] = "no change found"
    return plan.words


# ------------------------------------------------------------------------------------------------------------- S9 grid against the song
def grid_phase(T, A):
    """-> (lattice name, phase ms, concentration, hits) or None. The strongest 40 % of the song's kick / snare attacks (beat_hits.attacks, low and mid band) against the lattice
    BEAT0 + k * PER/2 (and PER/4: the one the hits agree on better is reported): the circular mean of their phase gives the concentration (1 = all on one phase, ~0.1 = no
    grid, e.g. a live drummer) and, with the offsets recentred on it, the median offset in ms (+ = the hits come after the timeline's grid)."""
    att = [a for a in attacks_for(T, A) if a[1] in ("low", "mid")]
    if len(att) < 12:
        return None
    st = np.array([a[2] for a in att])
    keep = [a for a, s in zip(att, st) if s >= np.percentile(st, 60)]
    best = None
    for name, div in (("1/2 beat", 2), ("1/4 beat", 4)):
        per = T.PER / div
        u = np.array([(a[0] - T.BEAT0) / per for a in keep])
        w = np.array([a[2] for a in keep])
        z = (w * np.exp(2j * np.pi * u)).sum() / w.sum()
        centre = float(np.angle(z) / (2 * np.pi))
        d = ((u - centre + 0.5) % 1.0 - 0.5) + centre                        # offsets around the consensus phase, in lattice steps
        conc, pms = abs(z), float(np.median(d) * per * 1000.0)
        if best is None or conc > best[2]:
            best = (name, pms, conc, len(keep))
    return best


# ------------------------------------------------------------------------------------------------------------- S10 fresh-render spot check
def deep_check(video, T, plan, A, n_cuts=6):
    """S10 (--deep): the frames the other checks cannot vouch for are rendered again with render.py (the part joins N/3 - 1, N/3, 2N/3 - 1, 2N/3 and up to `n_cuts` cut frames) and compared with
    the master's frames n-2 .. n+2 by PSNR: the best match must be the frame itself (a dropped / repeated frame or a shifted part shows as another frame). The absolute PSNR is only 26-29 dB
    (the master is sharpened and encoded), so only the argmax and its margin count: best at another frame by 2 dB or more: ERROR render-mismatch; no margin (a still picture): not conclusive, listed."""
    import cv2, tempfile
    N = T.N_FRAMES
    cutf = [c["expected"] for c in plan.cuts if c["hard"]]
    pick = sorted({N // 3 - 1, N // 3, 2 * N // 3 - 1, 2 * N // 3} | {cutf[int(round(i * (len(cutf) - 1) / max(1, n_cuts - 1)))] for i in range(min(n_cuts, len(cutf)))})
    cap = cv2.VideoCapture(video)
    bad, vague = [], []
    A.say("\ndeep: fresh render of %d frames against the master's frames -2..+2 (PSNR dB; the best must be 0)" % len(pick))
    with tempfile.TemporaryDirectory() as td:
        for n in pick:
            if n < 2 or n + 3 > N:
                continue
            png = os.path.join(td, "f%d.png" % n)
            r = subprocess.run([sys.executable, "render.py", str(n), str(n + 1), png], capture_output=True, text=True, encoding="utf-8", errors="replace")
            ref = cv2.imread(png) if os.path.isfile(png) else None
            if ref is None:
                A.add("WARN", "render-mismatch", "frame %d" % n, "render.py could not render the frame for the spot check: %s" % (r.stderr or r.stdout)[-200:], "")
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, n - 2)
            ps = []
            for j in range(-2, 3):
                ok, fr = cap.read()
                if not ok or fr.shape != ref.shape:
                    ps.append(-1.0)
                    continue
                mse = float(np.mean((fr.astype(np.float32) - ref.astype(np.float32)) ** 2))
                ps.append(10 * math.log10(255.0 ** 2 / max(mse, 1e-9)))
            order = sorted(range(5), key=lambda q: -ps[q])
            best, margin = order[0] - 2, ps[order[0]] - ps[order[1]]
            A.say("   frame %5d  %s  best %+d  margin %.1f dB" % (n, " ".join("%5.1f" % v for v in ps), best, margin))
            if best != 0 and margin >= 2.0:
                bad.append((n, best, margin))
            elif margin < 2.0:
                vague.append(n)
    if bad:
        A.add("ERROR", "render-mismatch", "frames " + ", ".join(str(n) for n, _, _ in bad[:8]),
              "%d frame(s) of the master match a fresh render of the timeline best at another frame (frame %d at %+d, margin %.1f dB): a dropped / repeated frame, a shifted part, or a master of another timeline" % (
                  len(bad), bad[0][0], bad[0][1], bad[0][2]),
              "render the master again: bash run.sh master.mp4")
    if vague:
        A.say("   not conclusive (margin < 2 dB, a still picture): %s" % ", ".join(str(n) for n in vague))


class Audit:
    def __init__(self, out=print, count_check=True):
        self.items, self.say, self.count_check = [], out, count_check
        self.lag_ms, self.lag, self.attacks = 0.0, 0.0, None

    def add(self, sev, code, where, msg, fix=""):
        self.items.append(item(sev, code, where, msg, fix))


def _frames(vals, n=8):
    return ", ".join(str(v) for v in vals[:n]) + (" ... (%d in all)" % len(vals) if len(vals) > n else "")


def audit(video, T, legacy=None, out=print, count_check=True, picture=True, summary=True, deep=False):
    """The audit of the file `video` against timeline module T -> list of items (see the module docstring). out: where the table is printed (a callable taking a string).
    legacy None: decided by T.SYNC. count_check False: the caller (gate.py) already reports frame-count. picture False: the frames are not decoded (container, sound, song
    and grid only; the table shows the picture columns as n/a). summary False: the findings list and the count line are not printed (gate.py prints the items itself). deep True: S10, a fresh render of a few frames (render.py in the folder)."""
    A = Audit(out, count_check)
    if legacy is None:
        legacy = int(getattr(T, "SYNC", 0)) < 2
    t_start = time.time()
    plan = Plan(T, legacy)
    ms = 1000.0 / T.FPS
    A.say("SYNC AUDIT %s   (%s; %d frames, %d shots, %d cuts, %d words, BPM %g, section %.3f s .. %.3f s of the song)" % (
        os.path.basename(video), "LEGACY timeline: the old ceil rules" if legacy else "SYNC 2 frame-exact", T.N_FRAMES, len(plan.shots), len(plan.cuts), len(plan.words),
        getattr(T, "BPM", 60.0 / T.PER), T.MUSIC_T0, T.MUSIC_T0 + (T.R1 - T.R0) * T.PER))
    for p in plan.problems:
        A.add("ERROR", "timeline", "timeline.py", p, "python timeline.py asserts the contract; re-draft the take or copy the SYNC 2 block from timeline_ref_example.py")
    n = container(video, T, plan, A)
    x, lag = audio_vs_song(video, T, A)

    # ---------------- the picture
    if picture:
        P = Picture(video, T, plan, A)
        cuts = measure_cuts(P, plan, A)
        shots = measure_shots(P, T, plan, A)
        words = measure_words(P, plan, A)
    else:
        P = None
        cuts, shots, words = plan.cuts, plan.shots, plan.words
        for c in cuts:
            c.update(measured=None)
        for sh in shots:
            sh.update(pop=None, burst=None, burst_exp=sh["expected"], flash=None, corr=None, corr_prev=None, popv=None)
        for w in words:
            w.update(first=None, why="frames not decoded")

    if deep and P is not None:
        deep_check(video, T, plan, A)

    # ---------------- the sound of the shots
    gun, pl, rep_full = {}, {}, {}
    st = {}
    if x is not None and shots:
        if os.path.isfile("audio_report.json"):                                    # per kill: beat = the musical hit, state (refstyle: measured, donor, clip offset, edit median, muted, silent; house: heard, muted, silent)
            try:
                rep_full = {round(q["beat"], 3): q for q in json.load(open("audio_report.json", encoding="utf-8")).get("kills", [])}
                st = {k: q.get("state") for k, q in rep_full.items()}
            except ValueError:
                st = {}
        if not legacy:
            try:
                pl = placements(x, lag, T, plan, A, rep_full)
            except Exception as ex:                                                  # never a silent pass: the detector below still runs, the failure is listed
                A.add("WARN", "gunshot-unmeasured", "placement check", "the matched-filter placement check crashed (%s: %s): the gunshots are judged by the onset detector only" % (type(ex).__name__, str(ex)[:120]), "")
        gun = gunshots(x, lag, T, plan, A, skip={q for q, sh in enumerate(shots) if st.get(round(sh["hit"], 3)) in ("muted", "silent")})

    # ---------------- the song's attacks (cuts and kills against the music)
    att = attacks_for(T, A) if (cuts or shots) and A.lag is not None else []
    at = np.array([a[0] for a in att]) if att else np.zeros(0)

    def attack_near(beat):
        if not len(at):
            return None
        t = T.beat_time(beat)
        i = int(np.argmin(np.abs(at - t)))
        return (at[i] - t) * 1000.0

    # ---------------- cuts table
    A.say("\ncuts   seg  musical beat  expected measured  d.frames | cut vs the music: nearest lattice line (1/2, 1/4, 1/8 beat) ms / nearest attack ms")
    wrong, late, offgrid, unmeas = [], [], [], []
    for c in cuts:
        m0 = c["m0"]
        b = T.M0 + m0 if hasattr(T, "M0") else m0
        lat = min(abs(b / s - round(b / s)) * s * T.PER * 1000.0 for s in (0.5, 0.25, 0.125))
        an = attack_near(m0)
        mf = min(lat, abs(an) if an is not None else 1e9) / ms                          # frames to the nearest lattice line or measured attack
        c["music_frames"], c["lat_ms"] = mf, lat
        if c["measured"] is None:
            unmeas.append(c)
            A.say("   %3d  %12.3f  %8d       n/a             %s" % (c["j"], m0, c["expected"], "a transition, not a hard cut" if not c["hard"] else "no clear cut found in +-8 frames"))
            continue
        d = c["measured"] - c["expected"]
        if d:
            wrong.append(c)
        if legacy and c["expected"] - c["x"] > 0.5 + 1e-3:
            late.append(c)
        if mf > HALF and not legacy:
            offgrid.append(c)
        A.say("   %3d  %12.3f  %8d  %8d  %+6d   | %6.1f / %s%s%s" % (c["j"], m0, c["expected"], c["measured"], d, lat, ("%+6.1f" % an) if an is not None else "   n/a",
                                                                       "   <-- ceil: %.1f ms after its beat (the nearest frame is %d)" % ((c["expected"] - c["x"]) * ms, c["nearest"]) if legacy and c["expected"] != c["nearest"] else "",
                                                                       "   <-- %.1f frames off the music" % mf if (mf > HALF and not legacy) else ""))
    unm_hard = [c for c in unmeas if c["hard"]]
    if unm_hard and not legacy:
        A.add("WARN", "cut-unmeasured", "takes " + _frames([c["j"] for c in unm_hard]),
              "%d hard cut(s) could not be found within +-8 frames of their expected frame (no clear change of the picture's layout: two takes of one clip, a dark or flat picture): their frames are NOT verified" % len(unm_hard),
              "look at them: python preview.py, or render.py n n+1 x.jpg around frame %d" % unm_hard[0]["expected"])
    if wrong:
        A.add("ERROR", "cut-frame", "segments " + _frames([c["j"] for c in wrong]),
              "%d of %d cuts show on another frame than the timeline says (first: segment %d expected %d, found %d): a dropped or repeated frame, a part join, or a take that came in late" % (
                  len(wrong), len(cuts), wrong[0]["j"], wrong[0]["expected"], wrong[0]["measured"]),
              "bash run.sh master.mp4 again; python syncaudit.py shows which take is the first wrong one (every later cut is moved by a dropped / repeated frame)")
    if late:
        A.add("ERROR", "cut-late", "segments " + ", ".join("%d (+%.1f ms)" % (c["j"], (c["expected"] - c["x"]) * ms) for c in late[:10]) + (" ..." if len(late) > 10 else ""),
              "%d of %d cuts sit on ceil(x) of their beat: up to %.1f ms after it, the nearest frame is never more than 8.3 ms away" % (len(late), len(cuts), max((c["expected"] - c["x"]) * ms for c in late)),
              "an old timeline / render (SYNC < 2): update the project to the SYNC 2 scripts and render again")
    if offgrid:
        far = [c for c in offgrid if c["music_frames"] > 2.0]
        if far:
            A.add("ERROR", "cut-grid", "segments " + _frames([c["j"] for c in far]),
                  "%d cut(s) lie more than 2 frames from every 1/2, 1/4, 1/8 beat line and from every measured attack of the song (segment %d: %.1f frames)" % (len(far), far[0]["j"], far[0]["music_frames"]),
                  "move the cut onto a measured hit (music_hits.py) or a lattice line; or ACCEPT=cut-grid when the user chose it")
        near = [c for c in offgrid if c["music_frames"] <= 2.0]
        if near:
            A.add("WARN", "cut-grid", "segments " + _frames([c["j"] for c in near]),
                  "%d cut(s) are between 0.5 and 2 frames from the nearest lattice line / attack of the song" % len(near), "")

    # ---------------- shots table
    A.say("\nshots  beat(hit)  lv  pop/impact  exp  pop  burst  flash(corr; corr on -1) | gunshot - hit ms (state) | picture - hit ms")
    fx_bad, bu_bad, fl_bad, fl_none, hit_far, hit_near = [], [], [], [], [], []
    gun_vals = []
    gun_unm, dbl, fx_unm = [], [], []

    def gtxt(q, g):
        p_ = pl.get(q)
        return ("pl %s" % ("%+5.1f" % p_[0] if p_[0] is not None else "n/a%.2f" % p_[1]) if p_ else "") + (" det %s" % ("%+6.1f" % g if g is not None else "n/a"))
    for q, sh in enumerate(shots):
        e = sh["expected"]
        g = gun.get(q)
        state = st.get(round(sh["hit"], 3), st.get(round(sh["k"], 3)))             # audio_report.json: beat = the musical hit
        an = attack_near(sh["hit"])
        sh["attack_ms"] = an
        pic_ms = ((sh["flash"] if sh["flash"] is not None else e) - (T.nearest_frame(sh["hit"]) if not legacy else plan.nf(sh["hit"]))) * ms
        A.say("  %9.3f  %d   %s  %5d  %s  %s  %s  | %s (%s) | %+6.1f%s" % (
            sh["hit"], sh["lv"], "%s" % ("%.1f" % sh["popv"] if sh["popv"] is not None else "n/a"), e,
            "%4s" % (sh["pop"] if sh["pop"] is not None else "n/a"), "%4s" % (sh["burst"] if sh["burst"] is not None else "-"),
            ("%4d (%.2f; on -1: %s)" % (sh["flash"], sh["corr"], "%.2f" % sh["corr_prev"] if sh["corr_prev"] is not None else "-")) if sh["flash"] is not None else
            ("n/a (best %.2f)" % sh["corr"] if sh["corr"] is not None else "n/a (%s)" % sh.get("flash_err", "no source diff"))[:60],
            gtxt(q, g), state or "?", pic_ms, "" if an is None else " | song attack %+.1f ms" % an))
        if g is not None:
            gun_vals.append(g)
        if sh["pop"] is not None and sh["pop"] != e:
            fx_bad.append((sh, "pop"))
        if sh["pop"] is None:
            fx_unm.append(sh)
        if sh["burst"] is not None and sh["burst"] != sh["burst_exp"]:
            bu_bad.append((sh, "burst"))
        if sh["flash"] is not None and sh["flash"] != e:
            fl_bad.append(sh)
        if sh["flash"] is None:
            fl_none.append(sh)
        pm_ = pl.get(q)
        if state in ("muted", "silent"):
            pass
        elif pm_ is not None and pm_[0] is not None:                               # the placed excerpt was found in the mix: where?
            if abs(pm_[0]) > PLACE_BAR_MS:
                A.add("ERROR", "kill-audio", "hit %.3f" % sh["hit"], "the gunshot excerpt audio.py placed sits %+.2f ms from the musical hit (match %.2f; bar %.1f ms): a placement or mux error" % (pm_[0], pm_[1], PLACE_BAR_MS),
                      "python audio.py, run.sh again; python gate.py --sync-only on the result")
            elif g is not None and g - pm_[0] > 15.0:
                dbl.append((sh, g - pm_[0]))
        elif pm_ is not None and pm_[1] < 0.3:
            A.add("ERROR", "kill-audio", "hit %.3f" % sh["hit"], "audio_report.json says the gunshot was placed (state %s) but its excerpt is not in the master (match %.2f): the shot is missing from the mix" % (state, pm_[1]),
                  "mix.wav and the master do not agree: python audio.py, run.sh again")
        elif g is not None:                                                         # no placement check (house style, a donor, a weak match): the loudest attack near the hit, as a hint
            if abs(g) > GUN_ERR_MS and state == "heard":
                A.add("ERROR", "kill-audio", "hit %.3f" % sh["hit"], "the gunshot starts %+.1f ms from the musical hit although audio.py says it was placed on its measured onset (bar %.0f ms, error beyond %.0f ms)" % (g, GUN_BAR_MS, GUN_ERR_MS),
                      "python audio.py, run.sh again; kill_lags.py shows the clip's onset")
            elif abs(g) > GUN_BAR_MS and state in VERIFIED_STATES:
                A.add("WARN", "kill-audio", "hit %.3f" % sh["hit"], "the loudest gunshot-like attack near the hit starts %+.1f ms from it (state %s; the onset read off the finished mix is good to about 2 ms)" % (g, state), "listen to it; kill_lags.py")
            elif abs(g) > GUN_WARN_MS:
                A.add("WARN", "kill-audio", "hit %.3f" % sh["hit"], "the gunshot starts %+.1f ms from the musical hit (state: %s)" % (g, state or "unknown"), "listen to it; kill_lags.py")
        else:
            gun_unm.append(sh)
        if an is not None and not legacy:
            if abs(an) > ms + 1e-3:
                hit_far.append((sh, an))
            elif abs(an) > HIT_EXACT_MS:
                hit_near.append((sh, an))
    if dbl:
        A.add("WARN", "kill-audio-double", "hits " + ", ".join("%.3f" % sh["hit"] for sh, _ in dbl[:8]),
              "%d kill(s): the placed gunshot is where it belongs, but a louder attack follows it (first: hit %.3f, %+.0f ms later): the clip's shot has two attacks, or another sound sits there" % (len(dbl), dbl[0][0]["hit"], dbl[0][1]),
              "listen to it")
    if gun_unm:
        A.add("WARN", "gunshot-unmeasured", "hits " + ", ".join("%.3f" % sh["hit"] for sh in gun_unm[:12]),
              "%d kill(s): the gunshot could not be found in the master (no shot stands out of the music, or the clip is not in this folder): its placement is NOT verified" % len(gun_unm), "listen to them")
    if gun_vals or pl:
        A.say("gunshots: placed excerpt matched in the master for %d of %d kills (max |misplacement| %.2f ms); loudest-attack detector: %d measurable, median %+.2f ms (the S2 lag %+.3f ms is taken out)" % (
            sum(1 for v in pl.values() if v[0] is not None), len(shots), max([abs(v[0]) for v in pl.values() if v[0] is not None] or [0.0]), len(gun_vals), float(np.median(gun_vals)) if gun_vals else 0.0, A.lag_ms))
    if fx_bad:
        A.add("ERROR", "fx-frame", "hits " + ", ".join("%.3f" % s["hit"] for s, _ in fx_bad[:8]),
              "%d kill(s): the exposure pop / impact frame is not on the shot frame (first: hit %.3f expected %d, found %d = %+.1f ms)" % (
                  len(fx_bad), fx_bad[0][0]["hit"], fx_bad[0][0]["expected"], fx_bad[0][0]["pop"], (fx_bad[0][0]["pop"] - fx_bad[0][0]["expected"]) * ms),
              "render.py puts every accent of a kill on its own frame; render again, or a part of the video was shifted (cut-frame says which take)")
    if bu_bad:
        A.add("ERROR", "fx-frame", "burst at hits " + ", ".join("%.3f" % s["hit"] for s, _ in bu_bad[:8]),
              "%d kill(s): the RGB split burst does not start on its frame (first: expected %d, found %d; a level 3 shot's burst starts the frame after its inverted frame)" % (len(bu_bad), bu_bad[0][0]["burst_exp"], bu_bad[0][0]["burst"]), "render again")
    if fx_unm:
        A.add("WARN", "fx-unmeasured", "hits " + ", ".join("%.3f" % sh["hit"] for sh in fx_unm[:12]),
              "%d kill(s): no exposure pop / inverted frame could be measured (a cut or blur-in is on the kill, or the step is too small): the accent frame is NOT verified" % len(fx_unm), "")
    if fl_bad:
        A.add("ERROR", "kill-flash", "hits " + ", ".join("%.3f" % s["hit"] for s in fl_bad[:8]),
              "%d kill(s): the muzzle flash shows on another frame than the shot's (first: hit %.3f expected %d, flash on %d = %+.1f ms; correlation %.2f)" % (
                  len(fl_bad), fl_bad[0]["hit"], fl_bad[0]["expected"], fl_bad[0]["flash"], (fl_bad[0]["flash"] - fl_bad[0]["expected"]) * ms, fl_bad[0]["corr"]),
              "the take is shifted against the timeline, or K is not the muzzle-flash frame: python kverify.py, python check.py master.mp4 (sync_N.jpg)")
    # the flash is not within 2 frames of the shot but a clear match sits 3..8 frames away: when the pop / burst are not on the shot frame either, THIS shot is off its frame (a kill moved inside
    # its take); when the pop / burst ARE on it, the far match is another shot of the same weapon (info only)
    moved = [sh for sh in shots if sh["flash"] is None and sh.get("wide_corr") is not None and sh["wide_corr"] >= 0.6 and sh["pop"] != sh["expected"] and sh["burst"] != sh["burst_exp"]]
    if moved:
        A.add("ERROR", "kill-flash", "hits " + ", ".join("%.3f" % sh["hit"] for sh in moved[:8]),
              "%d kill(s): no muzzle flash within 2 frames of the shot, no pop / burst on it, and the flash image sits %+d frames away (first: hit %.3f, correlation %.2f): the shot is off its frame" % (
                  len(moved), moved[0]["wide_n"] - moved[0]["expected"], moved[0]["hit"], moved[0]["wide_corr"]),
              "the kill's picture is shifted inside its take: render the master again; python kverify.py")
    meas_flash = [sh for sh in shots if sh["flash"] is not None]
    # a flash on the frame BEFORE the shot's frame too (present at -1 as strongly as on 0) means it was not on one frame
    early = [s for s in meas_flash if s["corr_prev"] is not None and s["corr_prev"] >= 0.6 * s["corr"] and s["flash"] == s["expected"] and not legacy]
    if early:
        A.add("WARN", "kill-flash", "hits " + ", ".join("%.3f" % s["hit"] for s in early[:8]),
              "%d kill(s): the flash is also on the frame before the shot (correlation there >= 60 %% of the shot frame's): it is spread over two frames" % len(early), "")
    if shots and len(meas_flash) < len(shots):
        unm_f = [sh for sh in shots if sh["flash"] is None]
        A.add("WARN", "flash-unmeasured", "hits " + ", ".join("%.3f" % sh["hit"] for sh in unm_f[:12]),
              "the muzzle flash could be found for %d of %d kills only (a level 3 inverted frame, a flat picture, a cut on the kill, or no clip in this folder): the other %d are NOT verified" % (len(meas_flash), len(shots), len(unm_f)),
              "look at the sync_N.jpg strips (python check.py master.mp4)")
    A.say("muzzle flash: measured %d of %d kills, on the shot frame %d, on another frame %d" % (len(meas_flash), len(shots), len(meas_flash) - len(fl_bad), len(fl_bad)))
    pm = [s for s in shots if s["pop"] is not None]
    A.say("exposure pop / impact frame: measured %d of %d kills, on the shot frame %d" % (len(pm), len(shots), sum(1 for s in pm if s["pop"] == s["expected"])))
    if hit_far:
        A.add("ERROR", "kill-hit", "hits " + ", ".join("%.3f (%+.1f ms)" % (s["hit"], a) for s, a in hit_far[:8]),
              "%d kill(s) whose musical beat is more than a frame from every measured attack of the song (nearest %+.1f ms): the kill is not on a drum hit" % (len(hit_far), hit_far[0][1]),
              "write the kill's beat from hits.json (music_hits.py), not from the grid")
    if hit_near:
        A.add("WARN", "kill-hit", "hits " + ", ".join("%.3f (%+.1f ms)" % (s["hit"], a) for s, a in hit_near[:8]),
              "%d kill(s) are not exactly on a measured attack of the song (more than %.0f ms, at most a frame): the beat was not taken from the measured hit" % (len(hit_near), HIT_EXACT_MS),
              "write the kill's beat from hits.json (music_hits.py): hit(t_attack)")

    # ---------------- bumps (and the house style's pulses): the pop on nearest_frame(beat) - HIT_LEAD
    if plan.bumps and P is not None:
        dl = np.zeros(P.n)
        dl[1:] = np.diff(P.Y)
        kill_frames = [s_["expected"] for s_ in shots]
        ramps = []                                                                  # picture ramps move the luma by themselves: not measurable inside them
        for nm in ("LUMA_IN", "LUMA_FADE"):
            v = getattr(T, nm, None)
            if v:
                ramps.append((T.nearest_frame(v[0]) - 3, T.nearest_frame(v[1]) + 3))
        done, bad_b, unm_b = 0, [], []
        for b in plan.bumps:
            e = b["expected"]
            if (e < 14 or e + 4 >= P.n or _cut_window(plan, e, (-3, 8)) or any(kf - 4 <= e <= kf + 9 for kf in kill_frames)      # a cut, or a kill's accent (nk-1 .. nk+6) overlaps the +-3 window
                    or any(a_ <= e <= b_ for a_, b_ in ramps)):
                unm_b.append(b)
                continue
            w = range(e - 3, e + 4)
            n = max(w, key=lambda q: dl[q])
            if dl[n] >= max(1.5, 0.04 * P.Y[max(0, n - 1)]) and dl[n] > 3 * (np.median(np.abs(dl[e - 12:e - 4])) + 0.1):
                done += 1
                if n != e:
                    bad_b.append((b, n))
            else:
                unm_b.append(b)
        A.say("bumps / pulses: %d, measurable %d, on their frame %d" % (len(plan.bumps), done, done - len(bad_b)))
        if bad_b:
            A.add("ERROR", "bump-frame", "beats " + ", ".join("%.3f" % b["beat"] for b, _ in bad_b[:8]),
                  "%d bump(s) pop on another frame than nearest_frame(beat) - HIT_LEAD (first: beat %.3f expected %d, found %d)" % (len(bad_b), bad_b[0][0]["beat"], bad_b[0][0]["expected"], bad_b[0][1]), "render again")
        if unm_b:
            A.add("WARN", "bump-unmeasured", "beats " + ", ".join("%.3f" % b["beat"] for b in unm_b[:12]),
                  "%d of %d bump(s) could not be measured (inside the opening fade / a luma ramp, near a cut or a kill's accents, or no clear pop): NOT verified" % (len(unm_b), len(plan.bumps)), "")

    # ---------------- words
    if plan.words:
        mw = [w for w in words if w["first"] is not None]
        off = [w["first"] - w["expected"] for w in mw]
        A.say("words: %d, measurable %d, first-change frame minus expected frame: %s" % (len(words), len(mw), dict(zip(*[v.tolist() for v in np.unique(off, return_counts=True)])) if off else "-"))
        bad_w = [w for w in mw if w["first"] != w["expected"]]
        if bad_w:
            A.add("ERROR", "word-frame", "words " + ", ".join("%s@%.2f" % (w["word"], w["a"]) for w in bad_w[:8]),
                  "%d word(s) first show on another frame than nearest_frame(cue) - HIT_LEAD (first: %s expected %d, found %d)" % (len(bad_w), bad_w[0]["word"], bad_w[0]["expected"], bad_w[0]["first"]),
                  "render again (textfx.py shows the first letter on nearest_frame(a) - HIT_LEAD)")
        unm_w = [w for w in words if w["first"] is None]
        if unm_w:
            A.add("WARN", "word-unverified", "words " + ", ".join("%s@%.2f" % (w["word"], w["a"]) for w in unm_w[:8]) + (" ..." if len(unm_w) > 8 else ""),
                  "%d of %d word(s) could not be measured on the picture (it moves behind the word, or the video's edge): their frame is NOT verified" % (len(unm_w), len(words)), "lyrics_audit.py checks the cue starts against the singing")

    # ---------------- the grid against the song
    gp = grid_phase(T, A) if A.lag is not None else None
    if gp:
        name, pms, conc, nh = gp
        A.say("grid: strong drum hits sit %+.1f ms from BEAT0 + k * %s (concentration %.2f, %d hits)" % (pms, name, conc, nh))
        if conc >= 0.5 and abs(pms) > 25.0:
            A.add("ERROR", "grid-phase", "timeline.py BEAT0", "the song's strong hits agree (concentration %.2f) and sit %+.1f ms from the timeline's grid (BEAT0 / BPM): the beat axis is not on the music" % (conc, pms),
                  "python music_grid.py measures BEAT0 and BPM; set them in the draft:music block")
        elif conc < 0.5:
            A.add("WARN", "grid-unmeasured", "song", "the song's drum hits do not agree on one grid phase (concentration %.2f): a live or swung song, the grid phase is not verified; events must use the measured hits" % conc, "")
    if summary:
        A.say("\nfindings:")
        order = {"ERROR": 0, "WARN": 1}
        for i in sorted(A.items, key=lambda i: order.get(i["severity"], 2)):
            A.say("  %-5s %-16s %-30s %s" % (i["severity"], i["code"], i["where"][:30], i["msg"]))
        ne, nw = sum(1 for i in A.items if i["severity"] == "ERROR"), sum(1 for i in A.items if i["severity"] == "WARN")
        A.say("sync audit: %d error(s), %d warning(s) in %.0f s" % (ne, nw, time.time() - t_start))
    return A.items


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("video")
    ap.add_argument("--deep", action="store_true", help="also S10: render about 10 frames again with render.py (the part joins, some cuts) and compare them with the master (about 1-2 minutes)")
    ap.add_argument("--legacy", action="store_true", help="an old timeline (SYNC < 2): measure it against the old ceil rules and list the ceil lateness")
    a = ap.parse_args(argv)
    import preflight
    T, err = preflight.load()
    if err:
        print(err, file=sys.stderr)
        return 2
    if int(getattr(T, "SYNC", 0)) < 2 and not a.legacy:
        import preflight as _pf
        print("syncaudit.py: " + _pf.sync_update_message(getattr(T, "SYNC", 0)) + ". To measure an OLD master against the old rules (diagnosis only): python syncaudit.py %s --legacy" % a.video, file=sys.stderr)
        return 2
    if not os.path.isfile(a.video):
        print("syncaudit.py: %s does not exist in %s" % (a.video, os.getcwd()), file=sys.stderr)
        return 2
    items = audit(a.video, T, legacy=True if a.legacy else None, deep=a.deep)
    return 1 if any(i["severity"] == "ERROR" for i in items) else 0


if __name__ == "__main__":
    sys.exit(main())
