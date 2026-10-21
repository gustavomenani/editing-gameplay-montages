"""Checks that turn the usual mistakes into one sentence that says what is wrong and what to do.

`import preflight` (first import of a script) stops with a clear message when this Python has no numpy / cv2, i.e.
when it is not the project's venv. `preflight.timeline()` imports timeline.py and checks it before any hour of work
is started on it; it returns the module. `python preflight.py` does the same check by hand (with the music).

timeline.py checks (all problems are listed at once, not only the first):
  CUTS_ON spelled right; LOOK (the edit options, look.py) has known options with values in range; the model edit's optional names (BUMPS,
  BOOMS, LUMA_IN, sound levels, IMPACT / ACC, segment white / shot_from) have the right shape and lie inside the video; every clip of the
  segments exists in src/ and has its pts/ table; anchor beats AND source frames strictly increasing; every kill inside its segment
  and inside its clip; segments follow each other; FADE_OUT inside the video; with music=True the song covers R0..R1
  (the one place that knows how long it is).

The timing contract (SYNC = 2; a timeline.py without it is refused with the way to update it):
  grid identities   FPS == 60, PER == 60 / BPM, FPB == FPS * PER, MUSIC_T0 == BEAT0 + (M0 + R0) * PER, N_FRAMES == round((R1 - R0) * FPB): audio.py reads
                    MUSIC_T0 / PER, render.py FPB / R0, the entries BEAT0 / M0: one that disagrees desyncs picture and sound silently
  exact frames      every cut (a segment's first anchor) and every shot (a kill's beat) lies on a whole output frame (the SEGS loop places them with vis())
  hits              HITS exists, every segment's s["hits"] holds one musical beat per kill (the measured attack), each inside its take and shown on
                    vis(hit, HIT_LEAD)"""
import difflib, glob, importlib, os, subprocess, sys, traceback, warnings

HOW = ("this is not the project's Python. Run the scripts with the venv from pipeline.md Setup (PY=./venv311/Scripts/python), "
       "or install the requirements into the one you use:  uv pip install --python venv311/Scripts/python.exe -r requirements.txt")
VIDEO = (".mp4", ".mkv", ".mov", ".m4v", ".webm", ".avi", ".ts", ".flv", ".wmv")
CUTS = ("bass", "kills")
CUTS_HINT = {"graves": "bass", "grave": "bass", "baixo": "bass", "kill": "kills", "abates": "kills"}

for _m in ("numpy", "cv2"):
    try:
        importlib.import_module(_m)
    except ImportError as _e:
        sys.exit(f"{sys.executable} cannot import '{_m}' ({_e}).\n{HOW}")


K_HELP = ("run `python kverify.py plan.json` (it measures the ammo step and the muzzle flash on the pictures: sheets kv_NN.jpg), fix K from its verdict "
          "(or `kverify.py kills.json --update`), then set \"k_checked\": true on the plan entry")


def kills_db():
    """kills.json of the project folder as a dict ({} when it is absent or unreadable): the one loader of both drafters' K rule"""
    import json
    try:
        d = json.load(open("kills.json", encoding="utf-8-sig"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def k_check(db, k):
    """The K rule of both drafters (a K one frame off is 16.7 ms of desync between the shot and the drum). k = {"clip", "K"} and
    optionally "id" (K = the PLAN's K). -> the reason this K is unverified, or None when kills.json verifies it. Unverified (refused unless the plan entry says
    "k_checked": true): no kills.json; no entry (by id, else clip + K, also the K that kverify.py corrected: "K_was"); the plan's K differs from the entry's;
    the entry's how is not "ammo" / "flash" (ammo-loose, guess, none: an old entry); its conf is "low" / "guess"."""
    if not db:
        return "there is no kills.json in this folder, so nothing verifies this K"
    kid, entry = k.get("id"), None
    if kid is not None:
        entry = db.get(str(kid))
    else:
        for i_, e in db.items():
            if e.get("clip") == k["clip"] and k["K"] in (e.get("K"), e.get("K_was")):
                kid, entry = i_, e
                break
    if entry is None:
        return "kills.json has no entry for %s K=%s (nothing verifies it)" % (k["clip"], k["K"])
    if entry.get("K") != k["K"]:
        if entry.get("K_was") == k["K"]:
            return "kills.json id %s: kverify.py corrected this K (%s) to %s" % (kid, k["K"], entry.get("K"))
        return "the plan's K = %s differs from kills.json id %s (K = %s)" % (k["K"], kid, entry.get("K"))
    how, conf = entry.get("how"), entry.get("conf")
    if how in ("ammo", "flash") and conf not in ("low", "guess"):
        return None
    if how is None:
        return 'kills.json id %s has no "how" (an old or hand-written entry), conf = %r' % (kid, conf)
    return "kills.json id %s: how = %r, conf = %r" % (kid, how, conf)


def duration(path):
    """Seconds of an audio / video file (None when ffprobe cannot tell)."""
    from ff import FFPROBE
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return None


def music_problems(T, seconds=None):
    """The song must cover timeline beats R0..R1. seconds = its length when already known (audio.py decoded it)."""
    err = []
    mus = getattr(T, "MUSIC", None)
    if not mus or not os.path.exists(mus):
        return [f"{mus} not found: put the song in clips.json as \"music\" and run ingest.py (it creates src/music.*), "
                "or point MUSIC in timeline.py at the file"]
    dur = seconds if seconds is not None else duration(mus)
    if not dur:
        return [f"{mus} has no readable audio (ffprobe reports no duration): is it a damaged or empty file? Re-export it as FLAC / WAV / MP3 and run ingest.py --force --only music"]
    t0 = T.MUSIC_T0
    t1 = t0 + (T.R1 - T.R0) * T.PER
    if t0 < -1e-3:
        err.append(f"R0 = {T.R0:g} starts {-t0:.2f} s before the beginning of the song (M0 = {T.M0}: timeline beat 0 is beat {T.M0} of the track): "
                   f"raise R0 to at least {(-T.BEAT0) / T.PER - T.M0 + 0.05:.1f}, or raise M0")
    if t1 > dur + 1e-3:
        rmax = (dur - T.BEAT0) / T.PER - T.M0 - 0.05
        err.append(f"R1 = {T.R1:g} runs {t1 - dur:.1f} s past the end of the song ({mus} is {dur:.1f} s long, the edit needs it until {t1:.1f} s): "
                   + (f"lower R1 (and FADE_OUT) to at most {rmax:.1f}, or choose an earlier M0" if rmax > T.R0 + 1 else
                      f"M0 = {T.M0} is itself too late (it is at {t0:.1f} s of the track): choose an earlier M0, the song has about {(dur - T.BEAT0) / T.PER:.0f} beats"))
    return err


def frame_speeds(T):
    """The speed every output frame plays at, from the time maps alone (no pixels): -> (segment index, speed) as numpy arrays of
    N_FRAMES. speed[n] = source frames the picture advances from output frame n to n+1 (1.0 = real time; the clips and the
    output both run at 60 fps). A segment's last frame uses the speed the map has at its end (the next segment starts a new clip position)."""
    import numpy as np
    N = int(T.N_FRAMES)
    r = T.R0 + np.arange(N) / T.FPB
    ends = np.array([s["a"][-1][0] for s in T.SEGS])
    seg = np.minimum(np.searchsorted(ends - 0.25 / T.FPB, r, side="right"), len(T.SEGS) - 1)       # a take starts on the frame whose beat is its first anchor (an exact frame: no float compare)
    sp = np.zeros(N)
    for i, s in enumerate(T.SEGS):
        m = seg == i
        if m.any():
            rr = r[m]
            sp[m] = (s["map"](rr + 1.0 / T.FPB)[0] - s["map"](rr)[0])
    return seg, sp


def fast_runs(T, limit, tol=1.02):
    """Runs of consecutive output frames of one segment that play faster than limit * tol: a list of dicts (segment, clip, frames
    n0..n1, beats b0..b1, vmax, vmean). [] when none."""
    import numpy as np
    seg, sp = frame_speeds(T)
    bad = sp > limit * tol
    runs, n, N = [], 0, len(sp)
    while n < N:
        if not bad[n]:
            n += 1
            continue
        e = n
        while e + 1 < N and bad[e + 1] and seg[e + 1] == seg[n]:
            e += 1
        runs.append(dict(segment=int(seg[n]), clip=T.SEGS[int(seg[n])].get("clip"), n0=n, n1=e, b0=T.R0 + n / T.FPB, b1=T.R0 + e / T.FPB,
                         vmax=float(sp[n:e + 1].max()), vmean=float(sp[n:e + 1].mean())))
        n = e + 1
    return runs


def fast_text(runs):
    """one line per run for a report"""
    return ["segment %d (%s): output frames %d-%d (beats %.2f-%.2f) up to %.2fx, mean %.2fx" % (
        r["segment"], r["clip"], r["n0"], r["n1"], r["b0"], r["b1"], r["vmax"], r["vmean"]) for r in runs]


def _where_in_take(T, r):
    """-> (part of the take the run sits in, what to do about it)"""
    s = T.SEGS[r["segment"]]
    ks = sorted(k for k, lv in s["kills"])
    r0 = s["a"][0][0]
    mid = (r["b0"] + r["b1"]) / 2
    before = [k for k in ks if k <= mid + 1e-9]
    if not before:
        if r["b0"] < r0 + 9.0 / T.FPB:
            return ("the blur-in at the start of the take",
                    "the take enters faster than real time: remove `n=` from the entry (pre() then enters at real time, the take starts %.1f source frames before the shot)" % (T.CUT * T.FPB if hasattr(T, "CUT") else 4.2))
        return ("the lead-in before the first shot", "the lead-in anchors run faster than real time: slow them (bullet time is 0.5x and below), or start the lead-in earlier")
    k = before[-1]
    nxt = [x for x in ks if x > k + 1e-9]
    if nxt and r["b1"] <= nxt[0] + 1e-9 + 1.0 / T.FPB:
        a = (s["map"](nxt[0])[0] - s["map"](k)[0]) / T.FPB
        return ("between the kills at beats %g and %g" % (k, nxt[0]),
                "the kills are %.2f beats apart at real time and sit closer than that: move the later kill to a hit at or after beat %.2f (slower between kills is fine), "
                "or split the take in two (a cut, on a kick with CUTS_ON \"bass\")" % (a, k + a))
    return ("after the shot at beat %g" % k,
            "the footage speeds up after the shot: use post() (it eases down to slow motion and back to real time, never above it); a hand-written post= list must stay at or below real time, "
            "and the take must not be longer than its footage allows")


def fast_forward(T):
    """MAX_SPEED (the timeline's ceiling for the playback speed; None = no ceiling) against the time maps, from the timeline alone (no pixels).
    -> list of dicts, machine-readable: severity "ERROR" | "WARN", code, where (text), msg, fix, and for a run: segment, clip, n0, n1 (output
    frames), b0, b1 (beats), vmax, vmean. ERROR: one per run of frames above MAX_SPEED * 1.02, or a MAX_SPEED that is not a number.
    WARN: MAX_SPEED is None and frames play above 1.25x (the user must have asked for velocity). [] = nothing plays faster than the ceiling."""
    import numpy as np
    seg, sp = frame_speeds(T)
    out = []
    back = np.flatnonzero(sp < 0)
    if len(back):
        n0, n1 = int(back[0]), int(back[-1])
        out.append(dict(severity="ERROR", code="backwards", segment=int(seg[n0]), clip=T.SEGS[int(seg[n0])].get("clip"), n0=n0, n1=n1,
                        where="segment %d (%s), output frames %d-%d" % (int(seg[n0]), T.SEGS[int(seg[n0])].get("clip"), n0, n1),
                        msg="the footage plays backwards (%d frames, down to %.2fx)" % (len(back), sp.min()),
                        fix="a pinned speed (third number of an anchor) asks more than the neighbouring anchors allow: unpin it, or move the anchors so the speed between them is above a third of the pinned speed"))
    ms = getattr(T, "MAX_SPEED", None)
    if ms is None:
        n = int((sp > 1.25).sum())
        if n:
            out.append(dict(severity="WARN", code="no-ceiling", where="timeline.py", n=n, share=n / len(sp), vmax=float(sp.max()),
                            msg="MAX_SPEED is None and %d output frames (%.0f %%) play above 1.25x, up to %.2fx" % (n, 100.0 * n / len(sp), sp.max()),
                            fix="deliver this only when the user asked for velocity / aceleracao; otherwise MAX_SPEED = 1.0 and re-draft (draft_ref_timeline.py)"))
        return out
    if isinstance(ms, bool) or not isinstance(ms, (int, float)) or not ms > 0:
        return out + [dict(severity="ERROR", code="max-speed", where="MAX_SPEED", msg="MAX_SPEED = %r is not a number above 0" % (ms,),
                           fix="1.0 = nothing plays faster than real time; None = no ceiling")]
    for r in fast_runs(T, ms):
        part, fix = _where_in_take(T, r)
        out.append(dict(r, severity="ERROR", code="fast-forward",
                        where="segment %d (%s), output frames %d-%d (beats %.2f-%.2f), %s" % (r["segment"], r["clip"], r["n0"], r["n1"], r["b0"], r["b1"], part),
                        msg="plays up to %.2fx (mean %.2fx), above MAX_SPEED = %g" % (r["vmax"], r["vmean"], ms), fix=fix + "; raise MAX_SPEED only if the user asked for velocity"))
    return out


def speed_problems(T):
    """the ERRORs of fast_forward(T) as the one-line strings check() lists"""
    return ["%s: %s %s. Fix: %s" % (d["code"], d["where"], d["msg"], d["fix"]) for d in fast_forward(T) if d["severity"] == "ERROR"]


def fast_report(T, limit=12):
    """Lines for check.py: what plays faster than real time, from the timeline. With MAX_SPEED: 'fast-forward: none ...' or the runs (ERROR).
    Without it (the house style, an old timeline): the runs above 1.25x, for information."""
    ms = getattr(T, "MAX_SPEED", None)
    if ms is not None and isinstance(ms, (int, float)) and not isinstance(ms, bool) and ms > 0:
        runs = fast_runs(T, ms)
        if not runs:
            return ["fast-forward: none (MAX_SPEED = %g: no output frame plays above %.2fx)" % (ms, ms * 1.02)]
        head = "fast-forward: %d run(s) of frames above MAX_SPEED = %g (ERROR; preflight.py says how to fix each):" % (len(runs), ms)
    else:
        runs = fast_runs(T, 1.25, tol=1.0)
        if not runs:
            return ["fast-forward: none above 1.25x (MAX_SPEED is not set in this timeline)"]
        head = "fast-forward: MAX_SPEED is not set in this timeline; %d run(s) of frames above 1.25x (information):" % len(runs)
    return [head] + ["   " + t for t in fast_text(runs[:limit])] + (["   ... %d more" % (len(runs) - limit)] if len(runs) > limit else [])


def fx_problems(T):
    """The optional names of the model edit (timeline_ref_example.py, draft:fx block; every one may be absent): BUMPS [(beat, 0..1)], BOOMS
    [dict(r=beat, gain=0..1)], LUMA_IN (beat a, beat b), KILL_THUMP / WHOOSH_BLUR / GAME_LEVEL / HEADROOM / FADE_IN numbers, ACC {level: (punch,
    shake px, exposure pop)}, IMPACT dict, and the segment keys white [(beat, 0..1)] and shot_from (clip, K). A wrong shape would be ignored or
    crash the renderer an hour in: -> list of problems (strings)."""
    E = []
    R0, R1 = T.R0, T.R1

    def num(name, lo, hi):
        v = getattr(T, name, None)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi):
            E.append(f"{name} = {v!r} must be a number from {lo:g} to {hi:g} (timeline.py)")
    for name, lo, hi in (("KILL_THUMP", 0, 2), ("WHOOSH_BLUR", 0, 2), ("GAME_LEVEL", 0, 2), ("HEADROOM", 0.1, 1.0), ("FADE_IN", 0, 5)):
        num(name, lo, hi)
    try:
        for b, st in getattr(T, "BUMPS", None) or []:
            if not R0 <= b <= R1 or not 0 <= st <= 1:
                E.append(f"BUMPS holds ({b!r}, {st!r}): a bump is (beat inside the video {R0:g} .. {R1:g}, strength 0 .. 1)")
                break
    except (TypeError, ValueError):
        E.append("BUMPS must be a list of (beat, strength) pairs, e.g. [(17.5, 0.8), ...]")
    try:
        for q in getattr(T, "BOOMS", None) or []:
            if not R0 <= q["r"] <= R1 or not 0 < q["gain"] <= 1:
                E.append(f"BOOMS holds {q!r}: a boom is dict(r=beat inside the video {R0:g} .. {R1:g}, gain=0 .. 1)")
                break
    except (TypeError, KeyError):
        E.append("BOOMS must be a list of dict(r=beat, gain=0.26)")
    li = getattr(T, "LUMA_IN", None)
    if li is not None:
        try:
            if not R0 <= li[0] < li[1] <= R1:
                E.append(f"LUMA_IN = {li!r} must be (beat a, beat b) with {R0:g} <= a < b <= {R1:g}")
        except (TypeError, IndexError):
            E.append(f"LUMA_IN = {li!r} must be (beat a, beat b)")
    acc = getattr(T, "ACC", None)
    if acc is not None and not (isinstance(acc, dict) and all(isinstance(acc.get(k), (tuple, list)) and len(acc[k]) == 3 for k in (1, 2, 3))):
        E.append("ACC must be a dict {1: (punch, shake px, exposure pop), 2: (...), 3: (...)}")
    imp = getattr(T, "IMPACT", None)
    if imp is not None and not (isinstance(imp, dict) and all(isinstance(imp.get(k, (0, 0, 0)), (tuple, list)) and len(imp.get(k, (0, 0, 0))) == 3 for k in ("blur", "split", "rays", "invert"))):
        E.append("IMPACT must be a dict(frames=6, blur=(3 numbers), split=(3 numbers), rays=(3 bools), invert=(3 bools)): one value per kill level 1..3")
    for i, s in enumerate(getattr(T, "SEGS", [])):
        w = s.get("white")
        if w:
            try:
                ok = all(R0 - 1e-9 <= b <= R1 + 1e-9 and 0 <= v <= 1 for b, v in w) and all(w[j][0] < w[j + 1][0] for j in range(len(w) - 1))
            except (TypeError, ValueError):
                ok = False
            if not ok:
                E.append(f"segment {i} ({s.get('clip')}): white = {w!r} must be [(beat, 0..1), ...] with increasing beats inside the video (flash(beat) in timeline.py writes it)")
        sf = s.get("shot_from")
        if sf is not None and not (isinstance(sf, (tuple, list)) and len(sf) == 2 and isinstance(sf[0], str) and glob.glob(f"src/{sf[0]}.*")):
            E.append(f"segment {i} ({s.get('clip')}): shot_from = {sf!r} must be (clip, K) of a clip in src/")
    return E


SYNC_NEEDED = 2
FRAME_TOL = 1e-3                                           # frames: a cut / shot beat further from a whole output frame than this is off the frame grid


def sync_update_message(sync):
    """the one sentence a timeline.py without the timing contract (SYNC = 2) gets"""
    have = "has no SYNC constant" if not sync else f"has SYNC = {sync!r}"
    return (f"timeline.py {have}, this skill version needs SYNC = {SYNC_NEEDED}: its old timing placed events on grid beats and showed them on the first frame at or "
            "after the beat (0 to 16.7 ms late, sound and picture apart). The new contract puts every picture event on an exact output frame and every sound on the measured "
            "hit. Update: copy the SYNC = 2 block (`hit(t)`, `frame_beat(n)`, `nearest_frame(r)`, `vis(r, lead)`, `SYNC = 2`), `CUT_LEAD` / `HIT_LEAD` in the cut block, "
            "the SEGS loop (s[\"m0\"], s[\"hits\"], KILLS / HITS, take_of) and the entries' musical beats from scripts/refstyle/timeline_ref_example.py (house style: "
            "scripts/timeline_example.py) into timeline.py, write each kill / cut / bump / boom / riser end as `hit(t)` of its measured attack (music_hits.py writes hits.json), "
            "or draft a new one with draft_ref_timeline.py / draft_timeline.py")


def grid_problems(T):
    """The grid constants of timeline.py must agree: audio.py reads MUSIC_T0 / PER, render.py reads FPB / R0, the entries read BEAT0 / M0 / PER. A constant that
    disagrees (an FPB typed with 29.0 for 29.032, a BEAT0 changed without MUSIC_T0) desyncs picture and sound silently by up to dozens of ms: -> problems"""
    E = []
    if T.FPS != 60:
        E.append(f"FPS = {T.FPS!r} must be 60 (the clips and the output run at 60 fps; render.py and the frame math assume it)")
    if abs(T.PER - 60.0 / T.BPM) > 1e-9:
        E.append(f"PER = {T.PER!r} is not 60.0 / BPM = {60.0 / T.BPM!r} (BPM = {T.BPM!r}): write PER = 60.0 / BPM")
    if abs(T.FPB - T.FPS * T.PER) > 1e-9:
        E.append(f"FPB = {T.FPB!r} is not FPS * PER = {T.FPS * T.PER!r}: the picture would drift {abs(T.FPB - T.FPS * T.PER) * (T.R1 - T.R0) / 60 * 1000:.1f} ms by the end; write FPB = FPS * PER")
    t0 = T.BEAT0 + (T.M0 + T.R0) * T.PER
    if abs(T.MUSIC_T0 - t0) > 1e-6:
        E.append(f"MUSIC_T0 = {T.MUSIC_T0!r} is not beat_time(R0) = BEAT0 + (M0 + R0) * PER = {t0!r} ({(T.MUSIC_T0 - t0) * 1000:+.1f} ms): the song would start that far from the picture; "
                 "write MUSIC_T0 = beat_time(R0)")
    n = int(round((T.R1 - T.R0) * T.FPB))
    if int(T.N_FRAMES) != n:
        E.append(f"N_FRAMES = {T.N_FRAMES!r} is not round((R1 - R0) * FPB) = {n}: write N_FRAMES = int(round((R1 - R0) * FPB))")
    return E


def _cap(lines, n=8):
    return lines if len(lines) <= n else lines[:n] + [f"... and {len(lines) - n} more of the same kind"]


def sync_problems(T):
    """SYNC 2 on the segments: every cut (a segment's first anchor) and every shot (a kill's beat) on an exact output frame; HITS present, one musical beat per kill, each
    inside its take and shown on vis(hit, HIT_LEAD). The fix for each is the same: write the MUSICAL beat in E and let the SEGS loop place it (timeline_ref_example.py)"""
    segs, R0, F = T.SEGS, T.R0, T.FPB
    frame = lambda b: (b - R0) * F
    off = lambda b: abs(frame(b) - round(frame(b))) > FRAME_TOL
    cut, shot, hit = [], [], []
    for i, s in enumerate(segs):
        b0 = s["a"][0][0]
        if off(b0):
            cut.append(f"segment {i} ({s.get('clip')}): its cut (first anchor, beat {b0:.9f}) falls on output frame {frame(b0):.4f}, not on a whole frame: a cut is shown on an exact frame "
                       "(write the cut's musical beat in E and let the SEGS loop place it with vis(m0, CUT_LEAD))")
        for k, lv in s["kills"]:
            if off(k):
                shot.append(f"segment {i} ({s.get('clip')}): the shot at beat {k:.9f} falls on output frame {frame(k):.4f}, not on a whole frame: a shot is shown on an exact frame "
                            "(write the kill's measured hit in E and let the SEGS loop place it with vis(hit, HIT_LEAD))")
    hits = getattr(T, "HITS", None)
    nk = sum(len(s["kills"]) for s in segs)
    if hits is None:
        hit.append("HITS is missing in timeline.py (the musical beat of every kill: copy the SEGS loop and the KILLS / HITS lists from timeline_ref_example.py)")
    elif len(hits) != nk:
        hit.append(f"HITS holds {len(hits)} musical beats for {nk} kills (the SEGS loop of timeline_ref_example.py builds both lists)")
    vis, HL = getattr(T, "vis", None), getattr(T, "HIT_LEAD", 1)
    for i, s in enumerate(segs):
        hb = s.get("hits")
        if hb is None or len(hb) != len(s["kills"]):
            hit.append(f"segment {i} ({s.get('clip')}): s[\"hits\"] must hold one musical beat per kill ({len(s['kills'])}), it holds {None if hb is None else len(hb)}: S(..., hits=...) / the SEGS loop sets it")
            continue
        r0, r1 = s["a"][0][0], s["a"][-1][0]
        for (k, lv), m in zip(s["kills"], hb):
            if not r0 - 1e-6 <= m <= r1 + 1e-6:
                hit.append(f"segment {i} ({s.get('clip')}): the hit at beat {m:.9f} lies outside its take (beats {r0:.6f} .. {r1:.6f}): a kill's hit belongs to the take that shows it")
            elif vis is not None and abs(vis(m, HL) - k) > 1e-6:
                hit.append(f"segment {i} ({s.get('clip')}): the shot is shown at beat {k:.9f} but its hit (beat {m:.9f}) is shown at vis(hit, HIT_LEAD) = {vis(m, HL):.9f}: the picture would "
                           "not sit on the frame HIT_LEAD frames before the drum (let the SEGS loop place the shot)")
    return _cap(cut) + _cap(shot) + _cap(hit)


def check(T, music=False, speed=True):
    """-> list of problems (strings) of the timeline module T. speed=False leaves the MAX_SPEED errors to the caller (gate.py asks fast_forward() itself)."""
    E = []
    for name in ("SEGS", "R0", "R1", "PER", "FPB", "BEAT0", "M0", "MUSIC", "FADE_OUT", "MUSIC_T0"):
        if not hasattr(T, name):
            E.append(f"{name} is missing in timeline.py (copy it from timeline_example.py / timeline_ref_example.py)")
    if E:
        return E
    sync = getattr(T, "SYNC", 0)
    if not isinstance(sync, (int, float)) or sync < SYNC_NEEDED:
        return [sync_update_message(sync)]
    for name in ("BPM", "FPS", "N_FRAMES"):
        if not hasattr(T, name):
            E.append(f"{name} is missing in timeline.py (copy it from timeline_example.py / timeline_ref_example.py)")
    if E:
        return E
    E += grid_problems(T)                                  # the grid constants agree with each other (audio.py and render.py read different ones)
    if E:
        return E
    cuts = getattr(T, "CUTS_ON", None)
    if cuts is not None and cuts not in CUTS:
        hint = CUTS_HINT.get(str(cuts).lower()) or (difflib.get_close_matches(str(cuts).lower(), CUTS, 1, 0.6) or [None])[0]
        E.append(f"CUTS_ON = {cuts!r} is not valid: it must be exactly \"bass\" (transitions on kicks / 808s, the default) or "
                 f"\"kills\" (transitions with the kill rhythm)" + (f"; did you mean \"{hint}\"?" if hint else ""))
    import look
    E += look.problems(T)                                  # LOOK (edit options): misspelled option, value out of range, unknown grade / preset
    E += fx_problems(T)                                    # the model edit's optional names: BUMPS, BOOMS, LUMA_IN, sound levels, IMPACT / ACC, white, shot_from
    if not T.R0 < T.R1:
        E.append(f"R0 = {T.R0:g} must be smaller than R1 = {T.R1:g}")
    f0, f1 = T.FADE_OUT
    if not (T.R0 < f0 < f1 <= T.R1 + 1e-9):
        E.append(f"FADE_OUT = {T.FADE_OUT} must lie inside the video (R0 = {T.R0:g} .. R1 = {T.R1:g}) with the start before the end")
    have = sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob("src/*") if f.lower().endswith(VIDEO))
    n_of, nosrc, nopts = {}, {}, {}
    prev = None
    for i, s in enumerate(T.SEGS):
        clip = s.get("clip")
        tag = f"segment {i} ({clip})"
        if clip in nosrc or clip in nopts:
            (nosrc if clip in nosrc else nopts)[clip].append(i)
        elif not glob.glob(f"src/{clip}.*"):
            nosrc[clip] = [i]
        elif not os.path.exists(f"pts/{clip}.csv"):
            nopts[clip] = [i]
        else:
            import clipio
            n_of[clip] = clipio.n_frames(clip)
        a = s["a"]
        for j in range(1, len(a)):
            if a[j][0] <= a[j - 1][0]:
                E.append(f"{tag}: anchor beats must increase, but anchor {j - 1} is at beat {a[j - 1][0]:g} and anchor {j} at beat {a[j][0]:g}")
                break
        for j in range(1, len(a)):
            if a[j][1] <= a[j - 1][1]:
                E.append(f"{tag}: source frames must increase (the take plays forward), but anchor {j - 1} is frame {a[j - 1][1]:g} and "
                         f"anchor {j} (beat {a[j][0]:g}) is frame {a[j][1]:g}")
                break
        r0, r1 = a[0][0], a[-1][0]
        for k, lv in s["kills"]:
            if not r0 - 1e-9 <= k <= r1 + 1e-9:
                E.append(f"{tag}: the kill at beat {k:g} lies outside the segment (its anchors run from beat {r0:g} to {r1:g}): "
                         "move the kill, or let this segment's anchors reach it")
            elif clip in n_of and not any(a[j][1] <= a[j - 1][1] or a[j][0] <= a[j - 1][0] for j in range(1, len(a))):
                kf = float(s["map"](k)[0])
                if not -0.5 <= kf <= n_of[clip] - 0.5:
                    E.append(f"{tag}: the kill at beat {k:g} falls on source frame {kf:.0f} but {clip} only has frames 0..{n_of[clip] - 1} "
                             f"({n_of[clip] / 60:.1f} s): check the kill's frame in kills.json")
            if lv not in (1, 2, 3):
                E.append(f"{tag}: the kill at beat {k:g} has level {lv!r}: use 1 (normal), 2 (slow-motion finisher) or 3 (impact frame)")
        if prev is not None and abs(r0 - prev) > 1e-9:
            E.append(f"segment {i} ({clip}) starts at beat {r0:g} but segment {i - 1} ends at beat {prev:g}: "
                     "the first anchor of a segment must be on the beat where the previous segment's last anchor is")
        prev = r1
    for clip, segs in nosrc.items():
        E.append(f"clip {clip!r} (segment{'s' if len(segs) > 1 else ''} {', '.join(map(str, segs[:6]))}{' ...' if len(segs) > 6 else ''}): there is no file src/{clip}.*. "
                 f"Clips in src/: {', '.join(have) or 'none'} (the names of clips.json after ingest.py). "
                 "Fix the clip name in timeline.py, or add the clip to clips.json and run ingest.py and mkpts.py")
    for clip, segs in nopts.items():
        E.append(f"clip {clip!r} (segment{'s' if len(segs) > 1 else ''} {', '.join(map(str, segs[:6]))}{' ...' if len(segs) > 6 else ''}): pts/{clip}.csv is missing: run  python mkpts.py {clip}")
    if T.SEGS:
        if T.SEGS[0]["a"][0][0] > T.R0 + 1e-9:
            E.append(f"the first segment starts at beat {T.SEGS[0]['a'][0][0]:g}, after R0 = {T.R0:g}: its first anchor must be at or before R0")
        if prev < T.R1 - 1e-9:
            E.append(f"the last segment ends at beat {prev:g}, before R1 = {T.R1:g}: its last anchor must be at or after R1")
    else:
        E.append("SEGS is empty: the timeline has no segments")
    if not E:                                              # the contract's checks need sound anchors / maps
        E += sync_problems(T)
    if speed and not E:                                    # the maps are sound: now the speed ceiling (MAX_SPEED)
        E += speed_problems(T)
    if music:
        E += music_problems(T)
    return E


def report(E):
    sys.exit("timeline.py has %d problem%s:\n  - %s\nFix them in timeline.py, then run  python timeline.py  (it must pass) before anything else."
             % (len(E), "" if len(E) == 1 else "s", "\n  - ".join(E)))


def require(T, music=False):
    """For timeline.py's own `python timeline.py` check: pass the module (sys.modules[__name__])."""
    E = check(T, music)
    if E:
        report(E)


def load():
    """Import timeline.py without exiting: -> (module, None), or (None, one-sentence reason)."""
    if not os.path.exists("timeline.py"):
        return None, (f"timeline.py not found in {os.getcwd()}. Run the scripts from the project folder (the one they were copied into), "
                      "and write timeline.py from timeline_example.py (house style) or timeline_ref_example.py (reference style): pipeline.md Setup, SKILL.md step 5.")
    try:
        with warnings.catch_warnings():                  # anchors that do not increase make TimeMap divide by zero: the checks below say it in words
            warnings.simplefilter("ignore", RuntimeWarning)
            return importlib.import_module("timeline"), None
    except (Exception, SystemExit) as e:
        frames = [f for f in traceback.extract_tb(e.__traceback__) if os.path.basename(f.filename) == "timeline.py"]
        where = f" at timeline.py line {frames[-1].lineno}: {frames[-1].line}" if frames else ""
        return None, f"timeline.py does not load: {type(e).__name__}: {e}{where}\nFix that line, then run  python timeline.py"


def timeline(music=False):
    """Import timeline.py with a readable failure, check it, return the module."""
    T, err = load()
    if err:
        sys.exit(err)
    E = check(T, music)
    if E:
        report(E)
    return T


if __name__ == "__main__":
    T = timeline(music=True)
    print("timeline.py passes the preflight checks (%d segments, %d frames, song covered)" % (len(T.SEGS), T.N_FRAMES))
