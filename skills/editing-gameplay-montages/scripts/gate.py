"""The delivery gate: nothing leaves the project while an ERROR is left. deliver.sh runs it on the master BEFORE it encodes the upload copy.

usage (from the project folder, with the project's Python):
    python gate.py master.mp4                    list every problem; exit 1 when an ERROR is left (WARNs print and pass)
    python gate.py master.mp4 --accept CODE[,CODE]   waive the ERRORs of these codes only (ACCEPT=CODE,CODE in the environment does the same, which is how
                                                 deliver.sh passes it); each waived code is written to LEIAME.md with the date and the problem, so nothing
                                                 is waived silently. An unknown code is refused (a typo must not waive anything).
    python gate.py master.mp4 --json             the list as JSON on stdout (nothing else is printed)
    python gate.py master.mp4 --no-pixels        skip the checks that decode the master and the clips (timeline, file, sound and audio report only)
    python gate.py --codes                       every code, its usual severity and what it means

From Python:  gate.run(video, accept=(), pixels=True) -> list of dicts {severity: "ERROR" | "WARN" | "ACCEPTED", code, where, msg, fix}
              gate.errors(items) -> the ERRORs left.   Every check is measured (time maps, ffprobe, the decoded master, audio_report.json written by
              audio.py, kill_rank.py): what cannot be measured in a project is reported as a WARN "... unverified", never skipped in silence, and a check that
              crashes is an ERROR (code check-failed, not waivable): a doubtful result is flagged, never passed.

What it checks
  timeline     preflight.check (clips, anchors, music, FADE_OUT ...) and preflight.fast_forward (MAX_SPEED: runs of frames faster than real time; backwards)
  the file     exists, video stream, size of the frame (1080x1920 / 1920x1080), 60 fps, frame count and duration of the timeline, audio stream at 48 kHz,
               audio as long as the picture; a master older than timeline.py (WARN)
  picture      check.py's measures on the master: frames identical to the previous one outside fades (ERROR), one-frame stalls (ERROR; the one frame
               before a cut out of an intro shot is the known false positive and is not counted), one-frame jumps that no kill, cut, accent or transition
               explains (ERROR), and, in the reference style, for every kill whether the master shows the source frame the timeline asks for around the beat
  sound        decoded peak above -0.5 dBFS (ERROR: peakguard.py should have fixed it), loudness outside -14 .. -7 LUFS (WARN)
  audio.py     audio_report.json: made for this timeline.py (else ERROR audio-stale: deliver.sh encodes mix.wav), every kill has a gunshot unless mute=True
               (ERROR in the reference style), mix.wav not clipped and as long as the picture, gunshots placed with an offset that was not measured (WARN)
  kills        kill_rank.check_timeline: hidden, not the player's, duplicated footage, K not the killing shot (ERROR); no kills.json: WARN
  lyrics       with lyrics.txt and lyric_cues.json: a word on screen that is not in the lyrics (ERROR)"""
import argparse, contextlib, datetime, io, json, os, re, subprocess, sys, time, unicodedata, wave
import preflight                                  # a clear message when this is not the project's Python
import numpy as np

# code -> (usual severity, what it means). --accept only takes these; check-failed is deliberately not in the list.
CODES = {
    "timeline-load": ("ERROR", "timeline.py is missing or does not load"),
    "timeline": ("ERROR", "preflight.check problem of timeline.py (the message says which)"),
    "fast-forward": ("ERROR", "frames play faster than MAX_SPEED"),
    "backwards": ("ERROR", "the footage plays backwards (a pinned speed no anchor allows)"),
    "max-speed": ("ERROR", "MAX_SPEED is not a number"),
    "no-ceiling": ("ERROR", "no MAX_SPEED and frames play above 1.25x: waive (ACCEPT=no-ceiling) only for a user who asked for velocity"),
    "master-older": ("WARN", "timeline.py was changed after the master was rendered"),
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
    "sync-unmeasured": ("WARN", "the kill sync could not be measured for most kills"),
    "peak": ("ERROR", "the decoded audio peak is above -0.5 dBFS (clipping risk)"),
    "loudness": ("WARN", "integrated loudness outside -14 .. -7 LUFS"),
    "audio-unmeasurable": ("ERROR", "ffmpeg could not measure the master's loudness / peak"),
    "audio-unverified": ("WARN", "no audio_report.json: audio.py was not run with this version"),
    "audio-stale": ("ERROR", "mix.wav / audio_report.json were made for another timeline.py"),
    "no-gunshot": ("ERROR", "a kill has no gunshot and is not mute=True"),
    "gunshot-unmeasured": ("WARN", "gunshots placed with an offset that was not measured"),
    "mix-clip": ("ERROR", "mix.wav is clipped"),
    "mix-length": ("ERROR", "mix.wav is not as long as the picture"),
    "kills-unverified": ("WARN", "kill_rank.py is not in this project: kills not verified"),
    "hidden": ("ERROR", "a kill's target is covered at the shot (kill_rank.py)"),
    "not-yours": ("ERROR", "the kill feed row is not the player's (kill_rank.py)"),
    "duplicate": ("ERROR", "the same footage twice (kill_rank.py)"),
    "wrong-shot": ("ERROR", "K is not the killing shot (kill_rank.py)"),
    "unverified": ("WARN", "no kill row follows K (kill_rank.py)"),
    "weak-shot": ("WARN", "K comes from a kill without a shot signal (kill_rank.py)"),
    "no-kills": ("WARN", "no kills.json: kills not verified (kill_rank.py)"),
    "lyrics-word": ("ERROR", "a word on screen is not in lyrics.txt"),
}


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
        # the error the user complained about ("clips acelerados do nada"): the gate refuses it unless waived by code
        sev = "ERROR" if d["code"] == "no-ceiling" else d["severity"]
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
        if da and da < dv - 0.25:
            out.append(item("ERROR", "audio-short", video, "the audio ends %.2f s before the picture (%.2f s against %.2f s)" % (dv - da, da, dv),
                            "audio.py must cover the video: python preflight.py, then run.sh again"))
        elif da and da > dv + 0.25:
            out.append(item("WARN", "audio-long", video, "the audio runs %.2f s past the picture" % (da - dv), "the player cuts it; run.sh again if it matters"))
    tag = " ".join(str(x) for x in (p.get("format", {}).get("tags") or {}).values())
    m = re.search(r"timeline_sha1=([0-9a-f]{40})", tag)
    if m and os.path.isfile("timeline.py"):
        import hashlib
        if m.group(1) != hashlib.sha1(open("timeline.py", "rb").read()).hexdigest():
            out.append(item("ERROR", "master-stale", video, "the master was rendered from another timeline.py than this one (its stamp differs)", "render it again: bash run.sh %s" % video))
    elif os.path.isfile("timeline.py") and os.path.getmtime("timeline.py") > os.path.getmtime(video) + 2:
        out.append(item("WARN", "master-older", video, "timeline.py was changed after %s was rendered (the master carries no timeline stamp)" % video, "if the change touched the picture or the sound, bash run.sh again"))
    return out, usable


def check_picture(T, video, pixels_log):
    """check.py's measures on the master -> items. Everything check.py prints goes to pixels_log."""
    import check
    out = []
    try:
        with contextlib.redirect_stdout(pixels_log):
            res = check.analyze(video, T, strips=False)
    except check.Stop as e:
        return [item("ERROR", "bad-video", video, str(e), "pass the master that run.sh made")], None
    R0, F = T.R0, T.FPB
    if res["exact"]:
        out.append(item("ERROR", "frozen-frame", "output frames " + _frames_text(res["exact"]),
                        "%d frame(s) identical to the previous one outside the fades (a duplicated source frame, a hole in the store)" % len(res["exact"]),
                        "python check.py %s names the clip and source frame; a duplicate: python repair.py; a store gap: python check_store.py, densify.py" % video))
    first = {}
    for j in range(1, len(T.SEGS)):
        first[int(np.ceil((T.SEGS[j]["r0"] - R0) * F - 1e-9))] = j
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
    gameplay = [n for n in cand if fa.get(n, {}).get("ok")]
    real = [(n, v, nb) for n, v, nb in real if n not in gameplay]
    odd = [(n, v, nb) for n, v, nb in res["odd"] if n not in gameplay]
    if real:
        out.append(item("ERROR", "stall", "output frames " + _frames_text([n for n, _, _ in real]),
                        "the motion stops for one frame (%s) and the master does not show the footage the timeline asks for there" % "; ".join(
                            "frame %d: %.2f against %.2f around it" % (n, v, nb) for n, v, nb in real[:4]),
                        "look at the source: python cadence.py <clip> <frame-8> <frame+8> --detail; a duplicated source frame: python repair.py; a store gap: python check_store.py"))
    if odd:
        out.append(item("ERROR", "unexplained-jump", "output frames " + _frames_text([n for n, _, _ in odd]),
                        "%d one-frame jump(s) that no kill, accent, cut or transition explains, and the master does not show the footage the timeline asks for there" % len(odd),
                        "python peek.py shows what they are; a store gap or a wrong frame: python check_store.py, python posmap.py, then render again"))
    if gameplay:
        out.append(item("WARN", "gameplay-jump", "output frames " + _frames_text(gameplay),
                        "%d one-frame jump / pause(s) the master reproduces from the footage (the timeline asks for exactly these frames): a shot that did not kill, an ability, a pause of the aim" % len(gameplay),
                        "python peek.py shows what they are; cut them out of the take if they distract"))
    s = res["sound"]
    if res["audio_stream"] and s is None:
        out.append(item("ERROR", "audio-unmeasurable", video, "ffmpeg could not measure the loudness / peak of the master's audio", "ffmpeg -i %s -vn -af ebur128=peak=true -f null -" % video))
    if s:
        if s["peak"] > -0.5:
            out.append(item("ERROR", "peak", video, "decoded peak %+.2f dBFS, above -0.5 (clips on some players)" % s["peak"],
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
                        "the picture sits one frame off the timeline at %d kill(s) (the shutter blur allows it; the sync_N.jpg strips show the flash)" % len(late),
                        "python check.py %s and look at sync_N.jpg for these kills" % video))
    if al and len(meas) < len(al) / 2:
        out.append(item("WARN", "sync-unmeasured", "kill sync", "%d of %d kills sit on a flat picture (black / one colour): nothing to match" % (len(al) - len(meas), len(al)),
                        "look at sync_N.jpg for the kills (python check.py %s)" % video))
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


# ---------------------------------------------------------------------------------------------------------------- the gate
def run(video, accept=(), pixels=True, log=None):
    """All the checks -> list of items. accept: codes whose ERRORs are waived (severity becomes ACCEPTED). log: where check.py's own report goes."""
    items = []
    log = log or io.StringIO()
    T, err = preflight.load()
    if err:
        return [item("ERROR", "timeline-load", "timeline.py", err, "fix timeline.py (python timeline.py shows the line)")]

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
    elif pixels and not usable:
        items.append(item("WARN", "picture-unchecked", "picture", "the picture checks (frozen frames, stalls, kill sync, sound) were not run: the file above is unusable", "fix the file first"))
    items += part("audio", check_audio_report, T)
    items += part("kills", check_kills, T)
    items += part("lyrics", check_lyrics, T)
    acc = set(accept)
    for i in items:
        if i["severity"] == "ERROR" and i["code"] in acc and i["code"] != "check-failed":
            i["severity"] = "ACCEPTED"
    return items


def note_accepted(items, video):
    """Append the waived problems to LEIAME.md (created when the project has none): nothing is waived silently."""
    acc = [i for i in items if i["severity"] == "ACCEPTED"]
    if not acc:
        return
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = ["", "## Aceito na entrega de %s (%s)" % (video, now), "",
             "O gate de entrega (gate.py) achou estes problemas e o usuário pediu para entregar assim mesmo (`--accept`):", ""]
    for i in acc:
        lines.append("- `%s` em %s: %s" % (i["code"], i["where"], i["msg"]))
    with open("LEIAME.md", "a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?")
    ap.add_argument("--accept", default="", help="comma-separated codes whose ERRORs are waived (also: ACCEPT in the environment)")
    ap.add_argument("--json", action="store_true", help="print the list as JSON and nothing else")
    ap.add_argument("--no-pixels", action="store_true", help="skip the checks that decode the master and the clips")
    ap.add_argument("--codes", action="store_true", help="list every code")
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
    t0 = time.time()
    log = io.StringIO()
    items = run(a.video, accept, not a.no_pixels, log)
    left = errors(items)
    if not left:                                      # the waivers are recorded only when the delivery goes ahead
        note_accepted(items, a.video)
    if a.json:
        print(json.dumps(items, indent=1, ensure_ascii=False))
        return 1 if left else 0
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
