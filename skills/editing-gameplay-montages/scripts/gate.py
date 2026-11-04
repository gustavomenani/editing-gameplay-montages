"""The delivery gate: nothing leaves the project while an ERROR is left. deliver.sh runs it on the master BEFORE it encodes the upload copy.

usage (from the project folder, with the project's Python):
    python gate.py master.mp4                    list every problem; exit 1 when an ERROR is left (WARNs print and pass)
    python gate.py master.mp4 --accept CODE[,CODE]   waive the ERRORs of these codes only (ACCEPT=CODE,CODE in the environment does the same, which is how
                                                 deliver.sh passes it); each waived code is written to LEIAME.md with the date and the problem, so nothing
                                                 is waived silently. An unknown code is refused (a typo must not waive anything).
    python gate.py master.mp4 --json             the list as JSON on stdout (nothing else is printed)
    python gate.py master.mp4 --no-pixels        skip every check that decodes pictures (the master's frames, the clips): picture, kill sync and
                                                 kverify are left out; the timeline, file, audio report, kills, lyrics and the sound / song / grid
                                                 parts of the sync audit still run, and the picture events it cannot measure are WARNed, not dropped
    python gate.py master.mp4 --deep             also render about 10 frames again with render.py (the part joins, some cuts) and compare them with the master (1-2 minutes)
    python gate.py master.mp4 --table            also print the sync audit's table (per event: expected frame / measured frame / ms)
    python gate.py --sync-only VIDEO             ONLY the sync audit of one file, which may be the UPLOAD COPY without the master next to it (deliver.sh runs it on the file that leaves,
                                                 after peakguard): container + pts, the sound against the song, every cut / shot / flash / accent / word frame. Needs timeline.py, src/ and
                                                 the song of the project in the folder. Prints the table and the findings; exit 0 = no ERROR left (WARNs pass), 1 = an ERROR, 2 = bad call
    python gate.py --codes                       every code, its usual severity and what it means

From Python:  gate.run(video, accept=(), pixels=True, log=None, table=None) -> list of dicts {severity: "ERROR" | "WARN" | "ACCEPTED", code, where, msg, fix}; gate.run_sync_only(video, table=None) -> the same for --sync-only
              gate.errors(items) -> the ERRORs left.   Every check is measured (time maps, ffprobe, the decoded master, audio_report.json written by
              audio.py, kill_rank.py): what cannot be measured in a project is reported as a WARN "... unverified", never skipped in silence, and a check that
              crashes is an ERROR (code check-failed, not waivable): a doubtful result is flagged, never passed.

What it checks
  timeline     SYNC = 2 (an older timeline.py is refused: ERROR timeline-old, never waived, the message says how to update), then preflight.check (clips, anchors, music, FADE_OUT ...) and
               preflight.fast_forward (MAX_SPEED: runs of frames faster than real time; backwards)
  the file     exists, video stream, size of the frame (1080x1920 / 1920x1080), 60 fps, frame count and duration of the timeline, audio stream at 48 kHz,
               audio as long as the picture, the START of the two tracks (pts-gap: the picture must begin at 0 and with the sound); a master older than timeline.py (WARN here,
               a refusal in deliver.sh: the upload copy would be audited against the new timeline after the whole encode)
  picture      check.py's measures on the master: frames identical to the previous one outside fades (ERROR), one-frame stalls (ERROR; the one frame
               before a cut out of an intro shot is the known false positive and is not counted), one-frame jumps that no kill, cut, accent or transition
               explains (ERROR), and, in the reference style, for every kill whether the master shows the source frame the timeline asks for around the beat.
               A stall / jump becomes the gameplay WARN only when the master's OWN frame is the one the timeline asks for and, for a stall, when the
               timeline's map itself repeats the source position there (the footage is frozen): a mean over five frames could hide a duplicated frame
  sound        decoded peak above 0 dBFS (ERROR: clipped; peakguard.py keeps the delivered copy below -0.5), loudness outside -14 .. -7 LUFS (WARN)
  audio.py     audio_report.json: made for this timeline.py (else ERROR audio-stale: deliver.sh encodes mix.wav), every kill has a gunshot unless mute=True
               (ERROR in the reference style), mix.wav not clipped and as long as the picture, gunshots placed with an offset that was not measured (WARN)
  kills        kill_rank.check_timeline: hidden, not the player's, duplicated footage, K not the killing shot or 2-12 frames after its feed row (ERROR); no kills.json: WARN; kverify.py: K re-measured on the pictures
               (ammo step / muzzle flash on K, none on K-1): a corrected or suspect K is ERROR kill-frame, not measurable WARN (not in --sync-only: it needs src/ and pts/)
  lyrics       with lyrics.txt and lyric_cues.json: a word on screen that is not in the lyrics (ERROR)
  sync audit   syncaudit.py, independent of the render's and the mixer's own bookkeeping (read its docstring): the file's pts lattice (pts-gap), the sound against the SONG (av-offset > 1 ms, av-drift),
               every cut on nearest_frame (cut-frame) and on the music (cut-grid), the kills on measured attacks of the song (kill-hit), the gunshots on their hits (kill-audio: WARN from 2 ms, ERROR beyond 4 ms), the muzzle flash
               and every accent of a kill on the shot frame (kill-flash, fx-frame), bumps (bump-frame), words (word-frame), the grid phase (grid-phase); lyrics_audit.py (refstyle, run by this gate): every lyric cue start against the sung attack (word-sung). NOT waivable: av-offset, av-drift,
               frame-count, cut-frame, pts-gap (and timeline-old, check-failed); the other sync codes take ACCEPT like any code"""
import argparse, contextlib, datetime, io, json, os, re, subprocess, sys, time, unicodedata, wave
import preflight                                  # a clear message when this is not the project's Python
import syncaudit

# code -> (usual severity, what it means). --accept only takes these; check-failed is deliberately not in the list.
CODES = {
    "timeline-load": ("ERROR", "timeline.py is missing or does not load"),
    "timeline": ("ERROR", "preflight.check problem of timeline.py (the message says which)"),
    "fast-forward": ("ERROR", "frames play faster than MAX_SPEED"),
    "backwards": ("ERROR", "the footage plays backwards (a pinned speed no anchor allows)"),
    "max-speed": ("ERROR", "MAX_SPEED is not a number"),
    "no-ceiling": ("ERROR", "timeline.py never wrote MAX_SPEED and frames play above 1.25x: waive (ACCEPT=no-ceiling) only for a user who asked for velocity; an explicit MAX_SPEED = None is a WARN"),
    "master-older": ("WARN", "timeline.py was changed after the master was rendered (deliver.sh refuses such a master before it encodes)"),
    "no-master": ("ERROR", "the master file does not exist"),
    "bad-video": ("ERROR", "the master has no readable video stream"),
    "size": ("ERROR", "frame size does not match FRAME / the style"),
    "master-stale": ("ERROR", "the master carries the stamp of another timeline.py"),
    "picture-unchecked": ("WARN", "the picture checks were not run (the file is unusable)"),
    "fps": ("ERROR", "the master is not 60 fps"),
    "frame-count": ("ERROR", "the master has another number of frames than the timeline (truncated render, or another timeline)"),
    "duration": ("ERROR", "the master's duration is not the timeline's"),
    "no-audio": ("ERROR", "the master has no audio stream"),
    "audio-rate": ("ERROR", "the audio is not 48 kHz"),
    "audio-channels": ("WARN", "the audio is not stereo"),
    "audio-short": ("ERROR", "the audio ends before the picture"),
    "audio-long": ("WARN", "the audio runs past the picture"),
    "frozen-frame": ("ERROR", "frames identical to the previous one outside the fades"),
    "stall": ("ERROR", "the motion stops for one frame (stutter)"),
    "unexplained-jump": ("ERROR", "a one-frame jump that no kill, cut, accent or transition explains"),
    "gameplay-jump": ("WARN", "a one-frame jump / pause the master reproduces from the footage itself (a shot that did not kill, an ability)"),
    "kill-sync": ("ERROR", "the master shows a source frame 2 or more frames off the timeline at a kill"),
    "kill-sync-late": ("WARN", "the master shows a source frame 1 off the timeline at a kill (more than the table predicts)"),
    "sync-unmeasured": ("WARN", "the kill sync could not be measured for some kills (a flat picture, an unreadable frame or clip): listed, never a pass"),
    "peak": ("ERROR", "the decoded audio peak is above 0 dBFS (clipped; peakguard.py keeps the delivered copy below -0.5)"),
    "loudness": ("WARN", "integrated loudness outside -14 .. -7 LUFS"),
    "audio-unmeasurable": ("ERROR", "ffmpeg could not measure the master's loudness / peak"),
    "audio-unverified": ("WARN", "no audio_report.json: audio.py was not run with this version"),
    "audio-stale": ("ERROR", "mix.wav / audio_report.json were made for another timeline.py"),
    "no-gunshot": ("ERROR", "a kill has no gunshot and is not mute=True"),
    "mix-clip": ("ERROR", "mix.wav is clipped"),
    "mix-length": ("ERROR", "mix.wav is not as long as the picture"),
    "kills-unverified": ("WARN", "kill_rank.py is not in this project: kills not verified"),
    "hidden": ("ERROR", "a kill's target is covered at the shot (kill_rank.py)"),
    "not-yours": ("ERROR", "the kill feed row is not the player's (kill_rank.py)"),
    "duplicate": ("ERROR", "the same footage twice (kill_rank.py)"),
    "wrong-shot": ("ERROR", "K is not the killing shot (kill_rank.py)"),
    "k-after-row": ("ERROR", "K lies 2-12 frames after the feed row of a kill of that clip (the row follows the killing shot, never precedes it)"),
    "unverified": ("WARN", "no kill row follows K (kill_rank.py)"),
    "weak-shot": ("WARN", "K comes from a kill without a shot signal (kill_rank.py)"),
    "no-kills": ("WARN", "no kills.json: kills not verified (kill_rank.py)"),
    "kill-frame": ("ERROR", "kverify.py: K of a kill is not the first frame of its shot (CORRECT to another sure K, or SUSPECT): the flash sits a frame off its hit; waive only with ACCEPT"),
    "kill-frame-unmeasured": ("WARN", "kverify.py could not measure K of a kill (replay camera, weapon hidden): K rests on whoever chose it"),
    "lyrics-word": ("ERROR", "a word on screen is not in lyrics.txt"),
    # the sync audit (syncaudit.py): the finished file against the timeline and the REAL song. NOT waivable: timeline-old, av-offset, av-drift, frame-count, cut-frame, pts-gap
    "timeline-old": ("ERROR", "timeline.py has no SYNC = 2: it is from the old pipeline (ceil cuts, beat-domain accents); update the project, never waived"),
    "pts-gap": ("ERROR", "the video's timestamps leave the 1/60 s lattice (WARN below 1 ms, ERROR above: a bad part join, a dropped or repeated frame) or the picture does not start at 0 with its sound (an -itsoffset, an elst / edit list, a mux offset), never waived"),
    "av-offset": ("ERROR", "the sound sits more than 1 ms from the song at the timeline's place (WARN above 0.25 ms), never waived"),
    "av-drift": ("ERROR", "the sound's offset to the song moves by more than 1 ms inside the video (the audio runs at another tempo), never waived"),
    "audio-unmatched": ("ERROR", "the decoded audio does not contain the song section the timeline says"),
    "cut-frame": ("ERROR", "a take's picture starts on another frame than nearest_frame(its cut beat): a dropped or repeated frame, or a late take, never waived"),
    "cut-late": ("ERROR", "legacy diagnosis only: a cut on ceil(x) instead of the nearest frame"),
    "cut-grid": ("ERROR", "a cut more than half a frame from every lattice line and measured attack of the song (WARN up to 2 frames)"),
    "kill-hit": ("ERROR", "a kill's musical beat is more than a frame from every measured attack of the song (WARN when not exactly on one)"),
    "kill-audio": ("ERROR", "a gunshot starts more than 4 ms from the musical hit although audio.py placed it on its measured onset (WARN from 2 ms; WARN above 8.3 ms for the others)"),
    "fx-frame": ("ERROR", "an accent of a kill (exposure pop, inverted frame, burst) is not on the shot's frame"),
    "kill-flash": ("ERROR", "the muzzle flash is not on the shot's frame (found by matching the source's flash image; WARN when it is also on the frame before)"),
    "flash-unmeasured": ("WARN", "the muzzle flash could not be found for half of the kills: not verified"),
    "render-mismatch": ("ERROR", "--deep: a frame of the file matches a fresh render of the timeline best at another frame (a dropped / repeated frame, a shifted part)"),
    "cut-unmeasured": ("WARN", "a hard cut could not be found within +-8 frames of its expected frame (no clear layout change): not verified"),
    "gunshot-unmeasured": ("WARN", "gunshots that could not be found in the master (or placed with an offset that was not measured): not verified"),
    "kill-audio-double": ("WARN", "the placed gunshot is on its hit but a louder attack follows it (two attacks in the clip's shot): listen"),
    "bump-unmeasured": ("WARN", "bumps / pulses that could not be measured (luma ramp, cut or kill accents near, no clear pop): not verified"),
    "fx-unmeasured": ("WARN", "kills whose exposure pop / inverted frame could not be measured: not verified"),
    "bump-frame": ("ERROR", "a bump pops on another frame than nearest_frame(beat) - HIT_LEAD"),
    "word-frame": ("ERROR", "a word first shows on another frame than nearest_frame(cue) - HIT_LEAD"),
    "word-sung": ("ERROR", "a lyric cue starts more than 25 ms from a confident sung attack of the voice stem and no flag explains it (lyrics_audit.py; WARN for flagged words)"),
    "word-unverified": ("WARN", "lyric_cues.json without the voice stem / lyrics_audit.py: the cue starts are not verified against the singing"),
    "grid-phase": ("ERROR", "the song's strong hits agree and sit more than 25 ms from the timeline's BEAT0 / BPM grid"),
    "grid-unmeasured": ("WARN", "the song's hits do not agree on one grid phase: the grid is not verified"),
}
NONWAIVABLE = ("check-failed",) + ("timeline-old",) + syncaudit.NONWAIVABLE      # the codes --accept / ACCEPT never waive


def item(sev, code, where, msg, fix=""):
    return dict(severity=sev, code=code, where=where, msg=msg, fix=fix)


def errors(items):
    return [i for i in items if i["severity"] == "ERROR"]


def _frames_text(ns, limit=8):
    return ", ".join(str(n) for n in ns[:limit]) + (" ... (%d in all)" % len(ns) if len(ns) > limit else "")


# ---------------------------------------------------------------------------------------------------------------- the checks
def check_timeline(T):
    out = []
    for p in preflight.check(T, music=True, speed=False):
        out.append(item("ERROR", "timeline", "timeline.py", p, "fix timeline.py as the message says, then python timeline.py"))
    for d in preflight.fast_forward(T):
        # preflight only warns (the worked example must still load), but a delivery with unrequested fast-forward is
        # the error the user complained about ("clips acelerados do nada"): the gate refuses it unless waived by code.
        # A timeline that never wrote MAX_SPEED omitted its choice; an explicit MAX_SPEED = None ("no ceiling", documented as
        # only on a velocity request) is a decision, so it keeps preflight's WARN.
        sev = "ERROR" if d["code"] == "no-ceiling" and not d.get("explicit") else d["severity"]
        out.append(item(sev, d["code"], d["where"], d["msg"], d["fix"]))
    return out


def probe(video):
    from ff import FFPROBE
    r = subprocess.run([FFPROBE, "-v", "error", "-count_packets", "-show_streams", "-show_format", "-of", "json", video], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        return json.loads(r.stdout or "{}")
    except ValueError:
        return {}


def expected_size(T):
    try:
        import frame                                  # the reference style: FRAME in timeline.py
        return frame.W, frame.H
    except ImportError:
        return 1080, 1920


def _start_time(stream):
    """The stream's start_time in seconds (ffprobe), or None when it has none ("N/A" in some matroska files): not measurable."""
    try:
        return float(stream.get("start_time"))
    except (TypeError, ValueError, AttributeError):
        return None


def check_file(T, video):
    """-> (items, usable): usable = the pixel checks can run on it"""
    out = []
    if not os.path.isfile(video):
        return [item("ERROR", "no-master", video, "%s does not exist in %s" % (video, os.getcwd()), "render it: bash run.sh %s" % video)], False
    p = probe(video)
    vs = [s for s in p.get("streams", []) if s.get("codec_type") == "video"]
    au = [s for s in p.get("streams", []) if s.get("codec_type") == "audio"]
    if not vs:
        return [item("ERROR", "bad-video", video, "no video stream that ffprobe can read (a render that was interrupted leaves such a file)",
                     "render the master again: bash run.sh %s" % video)], False
    v = vs[0]
    usable = True
    W, H = expected_size(T)
    if (v.get("width"), v.get("height")) != (W, H):
        usable = False
        out.append(item("ERROR", "size", video, "the picture is %sx%s, the timeline's FRAME says %dx%d" % (v.get("width"), v.get("height"), W, H),
                        "deliver the master that render.py makes (not an upload copy or a clip), or change FRAME in timeline.py back"))
    fr = v.get("avg_frame_rate", "0/1")
    try:
        a, b = fr.split("/")
        fps = float(a) / float(b)
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    if abs(fps - 60.0) > 0.01:
        out.append(item("ERROR", "fps", video, "the master runs at %.3f fps, not 60" % fps, "render it again with run.sh (render.py writes 60 fps)"))
    n = int(v.get("nb_read_packets") or v.get("nb_frames") or 0)
    nb = int(v.get("nb_frames") or n)
    if n != nb:
        out.append(item("ERROR", "frame-count", video, "the container says %d frames but holds %d packets: a damaged file" % (nb, n), "render the master again"))
    if n != T.N_FRAMES:
        out.append(item("ERROR", "frame-count", video, "%d frames in the file, %d in the timeline (%.2f s against %.2f s): a truncated render, one part, "
                        "or another timeline" % (n, T.N_FRAMES, n / 60.0, T.N_FRAMES / 60.0), "render the master again: bash run.sh %s" % video))
        usable = False
    try:
        dv = float(v.get("duration") or p.get("format", {}).get("duration") or 0)
    except ValueError:
        dv = 0.0
    if abs(dv - T.N_FRAMES / 60.0) > 0.1 and n == T.N_FRAMES:
        out.append(item("ERROR", "duration", video, "the video lasts %.2f s, the timeline %.2f s" % (dv, T.N_FRAMES / 60.0), "render the master again"))
    if not au:
        out.append(item("ERROR", "no-audio", video, "no audio stream: the upload would be silent",
                        "bash run.sh adds the sound; a master without: python audio.py, then mux mix.wav as the last lines of run.sh do"))
    else:
        a0 = au[0]
        if int(a0.get("sample_rate") or 0) != 48000:
            out.append(item("ERROR", "audio-rate", video, "the audio is %s Hz, not 48000" % a0.get("sample_rate"), "mux mix.wav again (run.sh's last ffmpeg line)"))
        if int(a0.get("channels") or 0) != 2:
            out.append(item("WARN", "audio-channels", video, "the audio has %s channel(s), not stereo" % a0.get("channels"), "mux mix.wav again"))
        try:
            da = float(a0.get("duration") or 0)
        except ValueError:
            da = 0.0
        # one frame of tolerance: a silent tail of 0.2 s (12 frames) used to pass without an item, a whole AAC padding frame is 21 ms
        if da and da < dv - 1.0 / T.FPS - 0.001:
            out.append(item("ERROR", "audio-short", video, "the audio ends %.2f s before the picture (%.2f s against %.2f s)" % (dv - da, da, dv),
                            "audio.py must cover the video: python preflight.py, then run.sh again"))
        elif da and da > dv + 0.25:
            out.append(item("WARN", "audio-long", video, "the audio runs %.2f s past the picture" % (da - dv), "the player cuts it; run.sh again if it matters"))
    # WHERE the tracks start, not only how long they are: an -itsoffset, an elst / edit list or a mux offset leaves a video that is
    # 0.5 s late with the right size, frame count, fps and sound, so every check above passes while the whole edit plays over the
    # wrong part of the song. The picture starts at 0 (half a tick of its time base is rounding) and the sound starts with it
    # (within a frame; a longer start difference is a late or early track, whatever moved it).
    try:
        tn, td = (int(x) for x in (v.get("time_base") or "1/15360").split("/"))
        tick = tn / float(td)
    except (ValueError, ZeroDivisionError):
        tick = 1.0 / 15360.0
    sv = _start_time(v)
    sa = _start_time(au[0]) if au else None
    late = []
    if sv is not None and abs(sv) > 0.5 * tick:
        late.append("the picture starts at %.6f s, not at 0" % sv)
    if sv is not None and sa is not None and abs(sv - sa) > 1.0 / T.FPS:
        late.append("the sound starts at %.6f s, %.1f ms away from the picture (more than a frame)" % (sa, abs(sv - sa) * 1000.0))
    if late:
        out.append(item("ERROR", "pts-gap", video, "; ".join(late) + ": every picture event sits that far from its sound",
                        "re-mux the master from 0: run.sh's last ffmpeg line (ffmpeg -i video.mp4 -i mix.wav -map 0:v -map 1:a ...) with no "
                        "-itsoffset, no -avoid_negative_ts and no elst edit list on the picture"))
    tag = " ".join(str(x) for x in (p.get("format", {}).get("tags") or {}).values())
    m = re.search(r"timeline_sha1=([0-9a-f]{40})", tag)
    if m and os.path.isfile("timeline.py"):
        import hashlib
        if m.group(1) != hashlib.sha1(open("timeline.py", "rb").read()).hexdigest():
            out.append(item("ERROR", "master-stale", video, "the master was rendered from another timeline.py than this one (its stamp differs)", "render it again: bash run.sh %s" % video))
    elif os.path.isfile("timeline.py") and os.path.getmtime("timeline.py") > os.path.getmtime(video) + 2:
        out.append(item("WARN", "master-older", video, "timeline.py was changed after %s was rendered (the master carries no timeline stamp)" % video, "if the change touched the picture or the sound, bash run.sh again"))
    return out, usable


def footage_frozen(T, n):
    """Does the timeline's own map ask for the same source frame at n and n-1? Only then is an output frame that repeats the one before it
    the footage's own pause (a real hold of the aim, an anchor pair that repeats a source frame) and not a frame the render duplicated.
    One take only: across a cut the two frames are different footage, so a repeat there is always the render's."""
    try:
        if n < 1 or T.take_of(n) != T.take_of(n - 1):
            return False
        s = T.SEGS[T.take_of(n)]
        return abs(float(s["map"](T.frame_beat(n))[0]) - float(s["map"](T.frame_beat(n - 1))[0])) < 1e-6
    except Exception:
        return False                                      # not measurable: never a pass


def check_picture(T, video, pixels_log):
    """check.py's measures on the master -> items. Everything check.py prints goes to pixels_log."""
    import check
    out = []
    try:
        with contextlib.redirect_stdout(pixels_log):
            res = check.analyze(video, T, strips=False)
    except check.Stop as e:
        return [item("ERROR", "bad-video", video, str(e), "pass the master that run.sh made")], None
    if res["exact"]:
        out.append(item("ERROR", "frozen-frame", "output frames " + _frames_text(res["exact"]),
                        "%d frame(s) identical to the previous one outside the fades (a duplicated source frame, a hole in the store)" % len(res["exact"]),
                        "python check.py %s names the clip and source frame; a duplicate: python repair.py; a store gap: python check_store.py, densify.py" % video))
    first = {}
    for j in range(1, len(T.SEGS)):
        first[T.nearest_frame(T.SEGS[j]["r0"])] = j
    real, cutting = [], []
    for n, v, nb in res["stalls"]:
        if n in res["exact"]:                                     # already reported as a frozen frame
            continue
        j = first.get(n + 1)
        if j is not None and T.SEGS[j - 1].get("intro"):          # the one frame before a cut out of an intro shot: slow motion against the cut's jump
            cutting.append(n)
        else:
            real.append((n, v, nb))
    cand = [n for n, _, _ in real] + [n for n, _, _ in res["odd"]]
    fa = {}
    if cand:
        try:
            fa = check.faithful(video, cand, T) or {}              # the house check cannot (returns None): then they stay errors
        except Exception as e:
            out.append(item("ERROR", "check-failed", "jump / stall", "the faithfulness measure crashed: %s: %s" % (type(e).__name__, e), "tell the maintainer; do not deliver on a doubt"))
    ok = {n for n in cand if fa.get(n, {}).get("ok")}
    acc = set(getattr(check, "accent_frames", tuple)())    # an older check.py has none: then only the map rule below explains a stall
    # the footage explains a flagged frame only when that frame ITSELF is what the timeline asks for (a mean over four good neighbours
    # used to hide one bad frame, and a stutter passed as gameplay), and a stall (an output frame that repeats the one before it) only
    # when the timeline's own map repeats the source position there: otherwise the render duplicated a frame the timeline moves past.
    # An accent frame (the reference style's inverted impact frame) is deliberately not the source picture, and stays allowed.
    gameplay = [n for n, _, _ in real if n in ok and (n in acc or footage_frozen(T, n))]
    gameplay += [n for n, _, _ in res["odd"] if n in ok and n not in gameplay]
    real = [(n, v, nb) for n, v, nb in real if n not in gameplay]
    odd = [(n, v, nb) for n, v, nb in res["odd"] if n not in gameplay]
    if real:
        out.append(item("ERROR", "stall", "output frames " + _frames_text([n for n, _, _ in real]),
                        "the motion stops for one frame (%s) and the master does not show the footage the timeline asks for there, or the timeline's map moves past that source position (the render repeated a frame)" % "; ".join(
                            "frame %d: %.2f against %.2f around it" % (n, v, nb) for n, v, nb in real[:4]),
                        "look at the source: python cadence.py <clip> <frame-8> <frame+8> --detail; a duplicated source frame: python repair.py; a store gap: python check_store.py"))
    if odd:
        out.append(item("ERROR", "unexplained-jump", "output frames " + _frames_text([n for n, _, _ in odd]),
                        "%d one-frame jump(s) that no kill, accent, cut or transition explains, and the master does not show the footage the timeline asks for there" % len(odd),
                        "python peek.py shows what they are; a store gap or a wrong frame: python check_store.py, python posmap.py, then render again"))
    if gameplay:
        out.append(item("WARN", "gameplay-jump", "output frames " + _frames_text(gameplay),
                        "%d one-frame jump / pause(s) the master reproduces from the footage (the timeline asks for exactly these frames, or for the accent on them): a shot that did not kill, an ability, a pause of the aim" % len(gameplay),
                        "python peek.py shows what they are; cut them out of the take if they distract"))
    s = res["sound"]
    if res["audio_stream"] and s is None:
        out.append(item("ERROR", "audio-unmeasurable", video, "ffmpeg could not measure the loudness / peak of the master's audio", "ffmpeg -i %s -vn -af ebur128=peak=true -f null -" % video))
    if s:
        if s["peak"] > 0.0:
            out.append(item("ERROR", "peak", video, "decoded peak %+.2f dBFS, above 0 (clips on some players)" % s["peak"],
                            "python peakguard.py %s <volume> mix.wav (house style 2.36; reference style: chain) (run.sh and deliver.sh call it); lower the game / effect levels in audio.py if it stays" % video))
        if not -14.0 <= s["lufs"] <= -7.0:
            out.append(item("WARN", "loudness", video, "integrated loudness %.1f LUFS, outside -14 .. -7" % s["lufs"],
                            "a quiet song or a hot mix: the platforms normalise to about -14; check the music gain in audio.py"))
    return out, res


def check_alignment(T, video):
    import check
    try:
        al = check.alignment(video, T)
    except Exception as e:
        return [item("ERROR", "check-failed", "kill sync", "the alignment measure crashed: %s: %s" % (type(e).__name__, e), "tell the maintainer; do not deliver on a doubt")]
    if al is None:
        return []
    out = []
    meas = [a for a in al if a.get("measurable", True)]
    unm = [a for a in al if not a.get("measurable", True)]
    other = [a for a in meas if a["score"] < 0.35]
    best = {id(a): max(a["scores"], key=a["scores"].get) for a in meas}
    bad = [a for a in meas if a["score"] >= 0.35 and abs(best[id(a)]) >= 2 and a["scores"][best[id(a)]] - a["scores"].get(0, 0) >= 0.03]
    late = [a for a in meas if a["score"] >= 0.35 and abs(best[id(a)]) == 1 and a["scores"][best[id(a)]] - a["scores"].get(0, 0) >= 0.03]
    if other:
        out.append(item("ERROR", "kill-sync", "beats " + ", ".join("%g (%s)" % (a["beat"], a["clip"]) for a in other[:8]) + (" ..." if len(other) > 8 else ""),
                        "around %d of %d kill(s) the master does not show the footage the timeline asks for (match %s; a render of this timeline matches 0.65 and more)" % (
                            len(other), len(meas), ", ".join("%.2f" % a["score"] for a in other[:6])),
                        "the master is a render of another timeline (render it again: bash run.sh %s), or the store / posmap does not hold these frames: python check_store.py, python posmap.py" % video))
    if bad:
        out.append(item("ERROR", "kill-sync", "beats " + ", ".join("%g (%s, %+d)" % (a["beat"], a["clip"], best[id(a)]) for a in bad[:8]),
                        "around %d kill(s) the master shows the source 2 or more frames away from what the timeline asks" % len(bad),
                        "the picture is shifted against the timeline: render the master again, python check_store.py, python posmap.py"))
    if late:
        out.append(item("WARN", "kill-sync-late", "beats " + ", ".join("%g" % a["beat"] for a in late[:8]),
                        "the picture's source sits one frame off the timeline at %d kill(s) (this band correlation cannot always tell one frame; the sync audit's flash / cut-frame lines are the exact test)" % len(late),
                        "python check.py %s and look at sync_N.jpg for these kills" % video))
    if unm:
        # an event that cannot be measured is listed, never counted as a pass: check.py returns a not-measurable entry for every kill
        # it could not read (a flat / black picture, the master ending early, a missing clip), so a project where several or all kills
        # cannot be read still says so here instead of looking clean
        out.append(item("WARN", "sync-unmeasured", "beats " + ", ".join("%g (%s)" % (a["beat"], a["clip"]) for a in unm[:8]) + (" ..." if len(unm) > 8 else ""),
                        "%d of %d kill(s) could not be measured (a flat / black picture, or the master's frames / the clip could not be read): their sync is NOT verified" % (len(unm), len(al)),
                        "look at sync_N.jpg for these kills (python check.py %s); a store gap or a wrong frame: python check_store.py" % video))
    return out


def check_audio_report(T):
    out = []
    style_ref = "view" in T.SEGS[0]
    try:
        import hashlib
        sha = hashlib.sha1(open("timeline.py", "rb").read()).hexdigest()
    except OSError:
        sha = None
    if not os.path.isfile("mix.wav"):
        out.append(item("ERROR", "mix-length", "mix.wav", "mix.wav is not in %s: deliver.sh encodes the sound from it" % os.getcwd(), "python audio.py (run.sh does it)"))
    else:
        try:
            with wave.open("mix.wav", "rb") as w:
                dur = w.getnframes() / float(w.getframerate())
            want = T.N_FRAMES / 60.0
            if abs(dur - want) > 0.3:
                out.append(item("ERROR", "mix-length", "mix.wav", "mix.wav lasts %.2f s, the picture %.2f s" % (dur, want), "python audio.py again (the timeline changed after it ran?)"))
        except (wave.Error, EOFError, OSError) as e:
            out.append(item("ERROR", "mix-length", "mix.wav", "mix.wav cannot be read: %s" % e, "python audio.py"))
    if not os.path.isfile("audio_report.json"):
        out.append(item("WARN", "audio-unverified", "audio_report.json", "audio.py has not written audio_report.json here (an older audio.py?): the gunshots and the mix peak are not verified",
                        "python audio.py (about a minute), then the gate again"))
        return out
    try:
        R = json.load(open("audio_report.json", encoding="utf-8"))
    except ValueError:
        return out + [item("ERROR", "audio-unverified", "audio_report.json", "audio_report.json is not valid JSON", "python audio.py")]
    if sha and R.get("timeline") != sha:
        out.append(item("ERROR", "audio-stale", "mix.wav", "audio.py ran for another timeline.py than this one: mix.wav (which deliver.sh encodes) has the sound of an older edit",
                        "python audio.py, then bash run.sh master.mp4 (the master's sound is the old one too)"))
    wp = R.get("written_peak")
    if wp is not None and wp > 1.0:
        out.append(item("ERROR", "mix-clip", "mix.wav", "the mix is written at a peak of %.2f (above 1.0): clipped" % wp, "lower the gains in audio.py and run it again"))
    silent = [k for k in R.get("kills", []) if k.get("state") == "silent"]
    if silent:
        out.append(item("ERROR" if style_ref else "WARN", "no-gunshot", "kills at beats " + ", ".join("%g (%s)" % (k["beat"], k["clip"]) for k in silent[:12]) +
                        (" ... (%d in all)" % len(silent) if len(silent) > 12 else ""),
                        "%d kill(s) have no gunshot and are not mute=True (the clip has no usable game sound, or the shot does not stand out)" % len(silent),
                        "record again with game sound, put mute=True on the take if voice chat covers it, or --accept no-gunshot when the music hit alone is wanted"))
    unm = [k for k in R.get("kills", []) if k.get("state") in ("clip offset", "edit median")]
    if unm:
        out.append(item("WARN", "gunshot-unmeasured", "kills at beats " + ", ".join("%g (%s)" % (k["beat"], k["clip"]) for k in unm[:12]),
                        "%d gunshot(s) were placed with the clip's / the edit's usual offset because the shot itself does not stand out: they can sit a frame or two off" % len(unm),
                        "listen to those kills, or kill_lags.py"))
    return out


def check_kills(T):
    try:
        import kill_rank
    except ImportError:
        return [item("WARN", "kills-unverified", "kill_rank.py", "kills not verified (kill_rank.py not run: it is not in this project)",
                     "copy scripts/kill_rank.py and run  python kills_auto.py <game>, then python kill_rank.py")]
    out = []
    for d in kill_rank.check_timeline(T):
        out.append(item(d["severity"], d["code"], d.get("where", ""), d.get("message", d.get("msg", "")), d.get("fix", "")))
    return out


def check_lyric_audit(T):
    """lyrics_audit.py (refstyle): every cue start of lyric_cues.json against the sung ATTACK measured on the voice stem (25 ms). Run as the script it is, in the project folder.
    Exit 1 = a cue that is not on an attack and not flagged (ERROR word-sung); its WARN block (flagged / no attack) is a WARN word-sung."""
    if not os.path.isfile("lyric_cues.json"):
        return []
    if not (os.path.isfile("lyrics_audit.py") and os.path.isfile(os.path.join("lyrics", "vocals.wav"))):
        return [item("WARN", "word-unverified", "lyric_cues.json", "the cue starts were not checked against the singing: %s" % (
            "lyrics_audit.py is not in this folder" if not os.path.isfile("lyrics_audit.py") else "lyrics/vocals.wav is missing (lyrics_stem.py makes it)"),
                     "python lyrics_stem.py, then python lyrics_audit.py")]
    r = subprocess.run([sys.executable, "lyrics_audit.py"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = []
    blocks = {}
    cur = None
    for line in (r.stdout or "").splitlines():
        m = re.match(r"(ERROR|WARN) \((\d+)\)", line)
        if m:
            cur = m.group(1)
            blocks[cur] = [line]
        elif cur and line.startswith("  "):
            blocks[cur].append(line.strip())
        elif cur:
            cur = None
    if r.returncode not in (0, 1) or (r.returncode == 1 and "ERROR" not in blocks):
        return [item("ERROR", "check-failed", "lyrics_audit.py", "lyrics_audit.py failed: %s" % ((r.stderr or r.stdout).strip().splitlines() or ["no output"])[-1][:300], "run python lyrics_audit.py and read its message")]
    for sev in ("ERROR", "WARN"):
        if sev in blocks:
            out.append(item(sev, "word-sung", "lyric_cues.json", " | ".join(blocks[sev][:7]) + (" ..." if len(blocks[sev]) > 7 else ""),
                            "python lyrics_audit.py shows the table; python lyrics_sync.py again, or `word@beat` in lyrics.txt pins a word"))
    return out


def kverify_game(T):
    """The game profile kverify.py needs (games/<name>.json): T.GAME, else the one profile every kills.json entry was measured with
    (kills_auto.py writes "game"), else the KVERIFY_GAME environment variable, else valorant (the default; said in the output).
    Not clips.json: ingest.py reads every key there as a clip."""
    g = getattr(T, "GAME", None)
    if not g and os.path.isfile("kills.json"):
        try:
            games = {e.get("game") for e in json.load(open("kills.json", encoding="utf-8-sig")).values() if isinstance(e, dict)} - {None}
            g = games.pop() if len(games) == 1 else None
        except (ValueError, AttributeError):
            g = None
    return g or os.environ.get("KVERIFY_GAME") or "valorant"


def check_kverify(T):
    """kverify.py (Kills): re-measures every kill's K on the clips' pictures (the ammo-counter step / muzzle flash on K, none on K-1); K = the time map at the shot beat. Needs src/ and pts/, not the
    master. CORRECT (another sure K) and SUSPECT -> ERROR kill-frame (the flash would sit a frame off its hit); not measurable -> WARN. The per-kill verdict lines are in the messages. The game profile
    is kverify_game(T) (passed as --game). kverify.py missing: WARN kills-unverified."""
    if not os.path.isfile("kverify.py"):
        return [item("WARN", "kills-unverified", "kverify.py", "kverify.py is not in this project: the K of every kill (the muzzle-flash frame the picture and the sound hang on) was not re-measured on the pictures",
                     "copy scripts/kverify.py and scripts/games/ into the project and run python kverify.py timeline.py")]
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        prefix = os.path.join(td, "kv")
        r = subprocess.run([sys.executable, "kverify.py", "timeline.py", "--no-sheets", "--out", prefix, "--game", kverify_game(T)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        try:
            res = json.load(open(prefix + ".json", encoding="utf-8"))
        except (OSError, ValueError):
            if "SYNC" in (r.stderr or ""):
                return [item("ERROR", "timeline-old", "timeline.py", (r.stderr or "").strip()[-600:], "")]
            return [item("ERROR", "check-failed", "kverify.py", "kverify.py (profile %s) failed: %s" % (kverify_game(T), ((r.stderr or r.stdout).strip().splitlines() or ["no output"])[-1][:300]),
                         "run python kverify.py timeline.py --game %s and read its message" % kverify_game(T))]
    lines = [l.rstrip() for l in (r.stdout or "").splitlines() if l.startswith(tuple(res)) or " CORRECT " in l or " SUSPECT " in l or "not measurable" in l]
    bad = [(t, v) for t, v in res.items() if v["verdict"] in ("correct", "suspect")]
    unm = [(t, v) for t, v in res.items() if v["verdict"] == "unmeasurable"]
    out = []
    if bad:
        out.append(item("ERROR", "kill-frame", "kills " + ", ".join("%s%s" % (t, " -> K %d" % v["K_sure"] if v.get("K_sure") else "") for t, v in bad[:10]),
                        "%d of %d kill(s): K is not the first frame of the shot (the flash would sit a frame off its hit). Verdict lines: %s" % (
                            len(bad), len(res), " | ".join(l for l in lines if " CORRECT " in l or " SUSPECT " in l)[:700]),
                        "move the anchor to the sure K (kverify.py --update for kills.json, then draft again); read the kv_NN.jpg sheets (python kverify.py timeline.py)"))
    if unm:
        out.append(item("WARN", "kill-frame-unmeasured", "kills " + ", ".join(t for t, _ in unm[:10]),
                        "%d kill(s) could not be measured by kverify.py (replay camera, weapon hidden, counter off screen): K rests on whoever chose it" % len(unm),
                        "python kverify.py timeline.py and read the sheets"))
    return out


def _tokens(text):
    t = unicodedata.normalize("NFC", text).upper()
    return [w for w in re.split(r"[^\w']+", t) if w]


def check_lyrics(T):
    if not (os.path.isfile("lyrics.txt") and os.path.isfile("lyric_cues.json")):
        return []                                     # not measurable here (no typed lyrics): not invented
    allowed = set(_tokens(open("lyrics.txt", encoding="utf-8-sig").read()))
    bad = []
    for c in json.load(open("lyric_cues.json", encoding="utf-8")):
        for w in _tokens(str(c[2])):
            if w not in allowed:
                bad.append((c[0], w))
    if not bad:
        return []
    return [item("ERROR", "lyrics-word", "beats " + ", ".join("%g" % b for b, _ in bad[:8]),
                 "word(s) on screen that are not in lyrics.txt: %s" % ", ".join(sorted({w for _, w in bad})),
                 "fix lyrics.txt (the confirmed lyrics), then run lyrics_sync.py; or --accept lyrics-word if the text is intended")]


# ---------------------------------------------------------------------------------------------------------------- the sync audit
def old_timeline_message(T):
    """preflight.sync_update_message (it names both styles' templates) + the diagnosis-only option"""
    return preflight.sync_update_message(getattr(T, "SYNC", 0)) + ". To measure an OLD master for diagnosis only: python syncaudit.py master.mp4 --legacy"


def old_timeline(T):
    return int(getattr(T, "SYNC", 0)) < 2


def check_sync(T, video, log, picture=True, count_check=False, deep=False):
    """The independent end-to-end audit (syncaudit.py) of the finished file -> items; its printed table goes to log (an object with write())."""
    return syncaudit.audit(video, T, out=lambda s: log.write(s + "\n"), count_check=count_check, picture=picture, summary=False, deep=deep)


def run_sync_only(video, table=None, deep=False):
    """gate.py --sync-only: the sync audit of ONE file, usable on the upload copy without the master (container, audio against the song, cut frames, shot frames, flash, accents, words) -> items."""
    table = table if table is not None else io.StringIO()
    T, err = preflight.load()
    if err:
        return [item("ERROR", "timeline-load", "timeline.py", err, "fix timeline.py (python timeline.py shows the line)")]
    if old_timeline(T):
        return [item("ERROR", "timeline-old", "timeline.py", old_timeline_message(T), "")]
    if not os.path.isfile(video):
        return [item("ERROR", "no-master", video, "%s does not exist in %s" % (video, os.getcwd()), "")]
    try:
        return check_sync(T, video, table, picture=True, count_check=True, deep=deep)
    except Exception as e:
        return [item("ERROR", "check-failed", "sync", "the check crashed: %s: %s" % (type(e).__name__, e), "tell the maintainer; do not deliver on a doubt")]


# ---------------------------------------------------------------------------------------------------------------- the gate
def run(video, accept=(), pixels=True, log=None, table=None, deep=False):
    """All the checks -> list of items. accept: codes whose ERRORs are waived (severity becomes ACCEPTED). log: where check.py's own report goes; table: where the sync audit's table goes."""
    items = []
    log = log or io.StringIO()
    T, err = preflight.load()
    if err:
        return [item("ERROR", "timeline-load", "timeline.py", err, "fix timeline.py (python timeline.py shows the line)")]
    if old_timeline(T):                                              # clean cutover: no silent fallback to the old rules
        return [item("ERROR", "timeline-old", "timeline.py", old_timeline_message(T), "")]

    def part(name, fn, *a):
        try:
            return fn(*a)
        except Exception as e:                                       # a check that crashes is itself an error: never a silent pass
            return [item("ERROR", "check-failed", name, "the check crashed: %s: %s" % (type(e).__name__, e), "tell the maintainer; do not deliver on a doubt")]

    items += part("timeline", check_timeline, T)
    try:
        fl, usable = check_file(T, video)
    except Exception as e:
        fl, usable = [item("ERROR", "check-failed", "file", "the check crashed: %s: %s" % (type(e).__name__, e), "tell the maintainer; do not deliver on a doubt")], False
    items += fl
    if pixels and usable:
        r = None
        try:
            pl, r = check_picture(T, video, log)
        except Exception as e:
            pl = [item("ERROR", "check-failed", "picture", "the check crashed: %s: %s" % (type(e).__name__, e), "tell the maintainer; do not deliver on a doubt")]
        items += pl
        if r is not None and r.get("frames") == T.N_FRAMES:
            items += part("kill sync", check_alignment, T, video)
        elif r is not None:
            # check.py's own warning about the frame count goes to its log (discarded unless --json): the kill sync that could not be run
            # must still be an item, never a silent skip
            items.append(item("WARN", "sync-unmeasured", "kill sync",
                              "the kill sync was not measured: %s decodes to %s frames, timeline.py has %d (check.py's warning is in its report)"
                              % (video, r.get("frames"), T.N_FRAMES),
                              "render the master again: bash run.sh %s (a container whose frame count disagrees is an ERROR above)" % video))
    elif pixels and not usable:
        items.append(item("WARN", "picture-unchecked", "picture", "the picture checks (frozen frames, stalls, kill sync, sound) were not run: the file above is unusable", "fix the file first"))
    items += part("audio", check_audio_report, T)
    if not any(i["code"] in ("no-master", "bad-video") for i in fl):
        items += part("sync audit", check_sync, T, video, table if table is not None else io.StringIO(), pixels and usable, False, deep)
    items += part("kills", check_kills, T)
    if pixels:                                                       # needs src/ and pts/ (not the master); never in --sync-only
        items += part("kverify", check_kverify, T)
    items += part("lyrics", check_lyrics, T)
    items += part("lyric cues", check_lyric_audit, T)
    waive(items, accept)
    return items


def waive(items, accept):
    """The ERRORs of the codes in `accept` become ACCEPTED, except the codes that are never waived (NONWAIVABLE: a crashed check, an old timeline, the sound / frame / pts errors of the sync audit)."""
    acc = set(accept)
    for i in items:
        if i["severity"] == "ERROR" and i["code"] in acc and i["code"] not in NONWAIVABLE:
            i["severity"] = "ACCEPTED"


def note_accepted(items, video):
    """Append the waived problems to LEIAME.md (created when the project has none): nothing is waived silently. Idempotent: a waiver
    line already in the file (same code, place and message) is not written again, so running the gate or deliver.sh twice on the same
    file does not duplicate the record."""
    acc = [i for i in items if i["severity"] == "ACCEPTED"]
    if not acc:
        return
    try:
        with open("LEIAME.md", encoding="utf-8") as f:
            have = set(f.read().splitlines())
    except OSError:
        have = set()                                      # no LEIAME.md yet: everything is new
    bullets = ["- `%s` em %s: %s" % (i["code"], i["where"], i["msg"]) for i in acc]
    new = [b for b in bullets if b not in have]
    if not new:
        return
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = ["", "## Aceito na entrega de %s (%s)" % (video, now), "",
             "O gate de entrega (gate.py) achou estes problemas e o usuário pediu para entregar assim mesmo (`--accept`):", ""] + new
    with open("LEIAME.md", "a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?")
    ap.add_argument("--accept", default="", help="comma-separated codes whose ERRORs are waived (also: ACCEPT in the environment)")
    ap.add_argument("--json", action="store_true", help="print the list as JSON and nothing else")
    ap.add_argument("--no-pixels", action="store_true", help="skip every check that decodes pictures (picture, kill sync, kverify); timeline, file, sound, audio report, kills and lyrics still run")
    ap.add_argument("--codes", action="store_true", help="list every code")
    ap.add_argument("--sync-only", action="store_true", help="only the sync audit of this ONE file (container, sound against the song, cut / shot / flash / accent frames, words): the upload copy, no master needed")
    ap.add_argument("--deep", action="store_true", help="also render about 10 frames again with render.py (part joins, some cuts) and compare them with the file (1-2 minutes more)")
    ap.add_argument("--table", action="store_true", help="also print the sync audit's table (per event: expected / measured frame and ms)")
    a = ap.parse_args(argv)
    if a.codes:
        for c, (s, d) in CODES.items():
            print("%-20s %-6s %s" % (c, s, d))
        return 0
    if not a.video:
        ap.error("the master is missing: python gate.py master.mp4")
    accept = [c.strip() for c in (a.accept + "," + os.environ.get("ACCEPT", "")).split(",") if c.strip()]
    unknown = [c for c in accept if c not in CODES]
    if unknown:
        print("gate.py: unknown code(s) in --accept / ACCEPT: %s. Nothing was waived. Codes: python gate.py --codes" % ", ".join(unknown), file=sys.stderr)
        return 2
    never = [c for c in accept if c in NONWAIVABLE]
    if never:
        print("gate.py: %s cannot be waived (a wrong sound offset, drift, frame count, cut frame or timestamp is never what the user asked for; an old timeline cannot be checked). Fix the file." % ", ".join(never), file=sys.stderr)
        return 2
    t0 = time.time()
    log, table = io.StringIO(), io.StringIO()
    if a.sync_only and not os.path.isfile(a.video):
        print("gate.py: %s does not exist: --sync-only audits one named file, so a missing path is a bad call (exit 2), not a finding" % a.video, file=sys.stderr)
        return 2
    if a.sync_only:
        items = run_sync_only(a.video, table, a.deep)
        waive(items, accept)
    else:
        items = run(a.video, accept, not a.no_pixels, log, table, a.deep)
    left = errors(items)
    if not left and not a.sync_only:                  # the waivers are recorded only when the delivery goes ahead (the upload copy repeats the master's waivers)
        note_accepted(items, a.video)
    if a.json:
        print(json.dumps(items, indent=1, ensure_ascii=False))
        return 1 if left else 0
    if (a.sync_only or a.table) and table.getvalue():
        print(table.getvalue())
    order = {"ERROR": 0, "ACCEPTED": 1, "WARN": 2}
    for i in sorted(items, key=lambda x: order[x["severity"]]):
        print("%-8s %-18s %s" % (i["severity"], i["code"], i["where"]))
        print("         %s" % i["msg"])
        if i["fix"]:
            print("         fix: %s" % i["fix"])
    unused = [c for c in accept if not any(i["code"] == c and i["severity"] == "ACCEPTED" for i in items)]
    if unused:
        print("note: --accept %s waived nothing (no such ERROR here)" % ", ".join(unused))
    if left and any(i["severity"] == "ACCEPTED" for i in items):
        print("note: the accepted codes are written to LEIAME.md only when no error is left")
    w = sum(1 for i in items if i["severity"] == "WARN")
    ac = sum(1 for i in items if i["severity"] == "ACCEPTED")
    print("gate: %d error(s)%s, %d warning(s) in %.0f s: %s" % (len(left), (", %d accepted" % ac) if ac else "", w, time.time() - t0,
                                                                "NOT delivered, fix the errors above" if left else "passes"))
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())
