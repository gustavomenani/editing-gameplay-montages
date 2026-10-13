"""Objective checks of a rendered montage, for an editor who cannot watch or hear it.

usage: python check.py video.mp4 [--sheets]

 0. fast-forward from the timeline (not from pixels): "fast-forward: none" or the runs of output frames above MAX_SPEED (an ERROR: the
                 preflight refuses them before this runs; a timeline without MAX_SPEED lists the runs above 1.25x as information)
 1. smoothness   frames identical to the previous one; frames where the motion stops for one frame
                 (each mapped back to the clip and source frame it shows; the frames beside an inverted impact frame, timeline IMPACT,
                 are not judged: the inversion's own motion fills their neighbourhood); one-frame jumps that no
                 kill, accent (bumps included), cut or transition explains; judder index
 2. sync_N.jpg   8 frames around every kill, and a printed table of the tile on which each muzzle flash must
                 first show: +0, +0 only faintly, or +1 when the beat falls after the exposure of frame +0
 3. --sheets     pv_NN.jpg: the whole video, two frames per beat, labelled with the beat
 4. sound        loudness, true peak, and the decoded sample peak (must stay below 0 dBFS)

Reference-style edit (the worked example, 46 s): identical 2 (the black opening fade; black frames are not counted any more), stalled 1 (the frame
before an intro cut: false positive), judder index 0.27, decoded peak -0.4 dBFS.
Vertical frame (FRAME = "vertical" in timeline.py, 1080x1920): same measures and thresholds. The two motion bands lie inside the 1080x608
gameplay window (above and below the words), sync_N.jpg shows the window only, pv_NN.jpg the whole frame. Measured on a 200-frame sample
(3.3 s of the worked example's timeline: a kill with slow motion, 4 words, 2 cuts), the same frames rendered both ways: 0 identical, 0 stalled in both;
judder per half second 0.38 0.19 0.34 0.34 0.27 0.38 vertical against 0.40 0.21 0.39 0.39 0.32 0.43 horizontal.

House-style reference values:  identical   stalled   judder index   decoded peak
  the house example (smooth)       0          1*         0.22          -0.7 dBFS
  a first version ("quedas de fps") 1         20         0.34          +3.0 dBFS (clipping)
  * a real pause of the aim in the source, not a fault. Any other stalled frame is a bug to fix.

For gate.py (the delivery gate): `import check` has no side effects; `analyze(video, T)` prints the report above and returns the measurements
(dict: frames, expected, exact, stalls, jumps, odd, judder, sync, sound, audio_stream, exit); `alignment(video, T)` measures, for every kill,
which source frame the master's picture shows around the beat against the one the timeline asks for (-> list of dicts, nothing printed);
`faithful(video, frames, T)` does the same around any output frames, to tell a jump or pause that is in the footage (the master matches the
timeline: a shot that did not kill, an ability, a real pause) from one the render made."""
import re, subprocess, sys, os, json, math
import preflight
import numpy as np
import cv2
from ff import FF, FFPROBE
import frame

T = None                                        # the timeline module: analyze() / alignment() set it (main loads it with preflight.timeline())
Wd, Hd = 270, 228
TW, TH = (180, 320) if frame.VERT else (320, 180)          # overview tile
# two bands of footage, above and below the lyric words (crop = w:h:x:y). Vertical: inside the 1080x608 window, clear of the words
# (caps 121-135 px centred on y = 960)
BANDS = ("1000:170:40:664", "1000:170:40:1090") if frame.VERT else ("1020:250:460:80", "1020:250:300:660")
PRE_N = 6                                      # kill sync (alignment): frames measured before the shot ...
PRE_CLEAR = PRE_N + 6                          # ... when the take started at least this many frames before it (5-frame blur-in + 1 clear)


class Stop(Exception):
    """what used to be a sys.exit(message) in the middle of the report"""


def frame_of(beat):
    return int(round((beat - T.R0) * T.FPB))


def where(n):
    r = T.frame_beat(n)
    a, b, p, tin = T.active(r)
    s = T.SEGS[a]
    src, v = s["map"](r)
    txt = "beat %6.2f  %s source frame %.1f at %.2fx" % (r, s["clip"], float(src), float(v))
    if b is not None:
        txt += "  (%s transition into %s)" % (tin[0], T.SEGS[b]["clip"])
    return txt


def invert_frames():
    """Output frames of the inverted impact frames (timeline IMPACT, LOOK impact True): the picture flips to its negative for one frame, so
    the motion into and out of it is huge, and the median of the neighbours says nothing about the frames next to it."""
    imp = getattr(T, "IMPACT", None)
    if imp is None:
        return []
    import look
    if not look.get(T)["impact"]:
        return []
    inv = imp.get("invert", (False, False, True))
    return [frame_of(k) for k, lv, i in T.KILLS if inv[lv - 1]]


def probe(VID):
    p = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-of", "json", VID], capture_output=True, text=True).stdout or "{}")
    vs = [s for s in p.get("streams", []) if s.get("codec_type") == "video"]
    if not vs:
        raise Stop(f"check.py: {VID} has no video stream that ffprobe can read (damaged or unfinished file? a render that was interrupted leaves one): render it again")
    if (vs[0].get("width"), vs[0].get("height")) != (frame.W, frame.H):
        raise Stop(f"check.py: {VID} is {vs[0].get('width')}x{vs[0].get('height')}, but timeline.py says FRAME = {frame.FRAME!r}, so this check reads "
                   f"the {frame.W}x{frame.H} montage that render.py makes (a source clip or an upload copy at another size cannot be checked; "
                   "a video of the other frame needs FRAME changed back in timeline.py): pass the master")
    return p


def null(VID, af):
    return subprocess.run([FF, "-hide_banner", "-nostats", "-i", VID, "-vn", "-af", af, "-f", "null", "-"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace").stderr


def analyze(VID, T_=None, sheets=False, strips=True):
    global T
    T = T_ if T_ is not None else (T or preflight.timeline())
    _probe = probe(VID)
    res = dict(exit=0)
    # ---------------------------------------------------------------- 0. fast-forward (timeline maps)
    for _l in preflight.fast_report(T):
        print(_l)

    # ---------------------------------------------------------------- 1. smoothness
    raw = subprocess.run([FF, "-v", "error", "-i", VID, "-vf", f"split[a][b];[a]crop={BANDS[0]}[t];[b]crop={BANDS[1]}[u];[t][u]vstack,scale={Wd}:{Hd}",   # two bands, above and below the lyric words
                          "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    f = np.frombuffer(raw, np.uint8).reshape(-1, Hd, Wd).astype(np.int16)
    d = np.abs(np.diff(f, axis=0)).mean((1, 2))          # d[i] = motion between frame i and frame i+1
    print("frames", len(f), "(timeline expects %d)" % T.N_FRAMES)
    res.update(frames=len(f), expected=T.N_FRAMES)
    if len(f) != T.N_FRAMES:
        print(f"WARNING: {VID} has {len(f)} frames but timeline.py has {T.N_FRAMES}: this file is a part, or it was rendered from another timeline. "
              "Everything below maps frames to the CURRENT timeline and will be wrong; render the master again (bash run.sh).")
    last = frame_of(T.LUMA_FADE[0])
    lum = f.mean((1, 2))
    exact = [i + 1 for i in range(len(d)) if d[i] < 0.03 and i + 1 < last and lum[i + 1] >= 12]      # black frames of a fade are identical by nature
    print("frames identical to the previous one (outside the black fades):", len(exact))
    for n in exact:
        print("   frame %4d  %s" % (n, where(n)))
    stalls, jumps = [], []
    inv = invert_frames()
    for i in range(2, len(d) - 2):
        if lum[i + 1] < 12:                               # fade to or from black: no motion to measure
            continue
        nb = np.median([d[i - 2], d[i - 1], d[i + 1], d[i + 2]])
        if nb > 0.6 and d[i] < 0.12 * nb:
            if not any(abs(i + 1 - z) <= 3 for z in inv):      # beside an inverted frame the neighbours' motion is the inversion's, not the footage's
                stalls.append((i + 1, d[i], nb))
        elif nb > 0.8 and d[i] > 2.6 * nb and d[i] > 3.0:
            jumps.append((i + 1, d[i], nb))
    print("frames where the motion stops for one frame (stutter unless the source really pauses there):", len(stalls))
    for n, v, nb in stalls:
        print("   frame %4d  t=%6.2fs  motion %.2f vs %.2f around it | %s" % (n, n / T.FPS, v, nb, where(n)))
    if stalls:
        print("   -> look at the source: python cadence.py <clip> <frame-8> <frame+8> --detail")
    # one-frame jumps are normal on a kill (flash, impact frame), on an accent (exposure pop), on a cut and
    # inside a transition; what is left is usually a shot that did not kill, a flick or an ability
    kills = [frame_of(k) for k, lv, i in T.KILLS]
    pulses = [frame_of(k) for k, wt in T.PULSES] + [frame_of(b) for b, st in getattr(T, "BUMPS", [])]      # bumps: a light flash on a hit without a kill
    spans = []
    for j in range(1, len(T.SEGS)):
        r0, dlen = T.SEGS[j]["r0"], T.SEGS[j]["tin"][1]
        spans.append((frame_of(r0) - 3, frame_of(r0) + 9))          # hard cut + blur-in + streaks
    odd = [(n, v, nb) for n, v, nb in jumps
           if not any(-3 <= n - k <= 12 for k in kills) and not any(-1 <= n - k <= 3 for k in pulses)
           and not any(a <= n <= b for a, b in spans)]
    print("one-frame jumps: %d, of which %d are not on a kill, an accent, a cut or a transition (peek.py shows what they are)"
          % (len(jumps), len(odd)))
    for n, v, nb in odd:
        print("   frame %4d  t=%6.2fs  motion %.2f vs %.2f around it | %s" % (n, n / T.FPS, v, nb, where(n)))
    r = np.abs(np.log((d[1:] + 0.3) / (d[:-1] + 0.3)))
    print("judder index per half second (mean |log ratio| of consecutive motions):")
    print(" ".join("%.2f" % r[i:i + 30].mean() for i in range(0, len(r) - 30, 30)))
    print("overall judder index %.3f" % r[:int(len(r) * 0.95)].mean())
    res.update(exact=exact, stalls=stalls, jumps=jumps, odd=odd, judder=float(r[:int(len(r) * 0.95)].mean()), motion=d, luma=lum)

    # ---------------------------------------------------------------- 2. kill strips
    cap = cv2.VideoCapture(VID)
    tiles = []
    for k, lv, i in (T.KILLS if strips else []):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_of(k) - 3)
        row = []
        for j in range(8):
            ok, fr = cap.read()
            if not ok:
                break
            crop = cv2.resize(fr[frame.WIN_Y:frame.WIN_Y + frame.WIN_H], (240, 135), interpolation=cv2.INTER_AREA)      # the gameplay (vertical: the window)
            cv2.putText(crop, f"{k:g} {j - 3:+d}", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
            row.append(crop)
        if len(row) == 8:
            tiles.append(np.hstack(row))
    for s in range(0, len(tiles), 7):
        cv2.imwrite(f"sync_{s // 7}.jpg", np.vstack(tiles[s:s + 7]), [cv2.IMWRITE_JPEG_QUALITY, 86])
    if strips:
        print("kill strips: sync_0.jpg .. sync_%d.jpg (%d kills, 7 per sheet). Where the flash must first show:" % ((len(tiles) + 6) // 7 - 1, len(tiles)))
    count = {"+0": 0, "+0 faint": 0, "+1": 0}
    sync = []
    for k, lv, i in T.KILLS:
        x = (k - T.R0) * T.FPB                            # the beat in output frames; frame +0 is round(x)
        sh = T.SEGS[i]["shutter"]                         # footage shutter of the take, in output frames
        part = min(1.0, max(0.0, (round(x) + sh / 2 - x) / sh))     # share of frame +0's exposure that lies after the shot
        key = "+1" if part <= 0 else "+0" if part >= 0.25 else "+0 faint"
        count[key] += 1
        sync.append(dict(beat=k, level=lv, take=i, frame=x, tile=key))
        tile = "+1 (the shot comes after frame +0's exposure)" if part <= 0 else \
               "+0" if part >= 0.25 else "+0, faint (only %d %% of its exposure is after the shot), full on +1" % max(1, round(100 * part))
        print("   beat %6g  frame %8.2f  -> %s" % (k, x, tile))
    print("   in all: %d on +0, %d faint on +0, %d on +1. A flash later than its tile means K or the beat is wrong." % (
        count["+0"], count["+0 faint"], count["+1"]))
    res["sync"] = sync

    # ---------------------------------------------------------------- 3. overview sheets
    if sheets:
        beats = np.arange(np.ceil(T.R0 * 2) / 2, T.R1, 0.5)
        thumbs = []
        for b in beats:
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(len(f) - 1, frame_of(b)))
            ok, fr = cap.read()
            if not ok:
                break
            t = cv2.resize(fr, (TW, TH), interpolation=cv2.INTER_AREA)
            cv2.rectangle(t, (0, 0), (74, 30), (0, 0, 0), -1)
            cv2.putText(t, "%g" % b, (4, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            thumbs.append(t)
        per = 9 * 6
        for s in range(0, len(thumbs), per):
            chunk = thumbs[s:s + per]
            sheet = np.zeros((TH * ((len(chunk) + 8) // 9), TW * 9, 3), np.uint8)
            for q, t in enumerate(chunk):
                sheet[TH * (q // 9):TH * (q // 9 + 1), TW * (q % 9):TW * (q % 9 + 1)] = t
            cv2.imwrite("pv_%02d.jpg" % (s // per + 1), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
        print("overview: pv_01.jpg .. pv_%02d.jpg (two frames per beat)" % ((len(thumbs) + per - 1) // per))

    # ---------------------------------------------------------------- 4. sound
    e = null(VID, "ebur128=peak=true:framelog=quiet")
    e = e[e.rfind("Summary:"):] if "Summary:" in e else ""
    lufs, tp = re.search(r"I:\s+(-?[\d.]+) LUFS", e), re.search(r"Peak:\s+(-?[\d.]+) dBFS", e)
    pk = re.search(r"Peak level dB:\s+(-?[\d.]+)", null(VID, "aformat=sample_fmts=flt,astats=measure_overall=Peak_level:measure_perchannel=none"))
    res["audio_stream"] = any(s.get("codec_type") == "audio" for s in _probe.get("streams", []))
    res["sound"] = None
    if lufs and pk:
        res["sound"] = dict(lufs=float(lufs.group(1)), true_peak=float(tp.group(1)) if tp else None, peak=float(pk.group(1)))
        print("sound: integrated loudness %s LUFS, true peak %s dBFS, decoded sample peak %s dBFS"
              % (lufs.group(1), tp.group(1) if tp else "?", pk.group(1)))
        if float(pk.group(1)) >= 0.0:
            print("   WARNING: the decoded sound exceeds 0 dBFS (clipping). Encode AAC with -aac_pns 0 -aac_tns 0 -aac_is 0 after the limiter.")
    elif not res["audio_stream"]:
        print(f"WARNING: {VID} has no audio stream, so loudness and clipping cannot be checked and the upload would be silent. "
              "bash run.sh master.mp4 adds the sound (video.mp4 and part_N.mp4 are silent by design); a master without sound: "
              "run audio.py, then mux mix.wav as the last lines of run.sh do.")
        res["exit"] = 1
    else:
        print(f"WARNING: {VID} has an audio stream but ffmpeg could not measure it (loudness / peak not found in its report): "
              f"run  {FF} -i {VID} -vn -af ebur128=peak=true -f null -  and read the error")
        res["exit"] = 1
    return res


def _match(VID, cases, workers=6):
    """Compare the master with the clips. cases: [(key, segment index, n0, [j, ...])]. The master's frames n0+j are compared, in the two motion
    bands above and below the words (normalised correlation of 80x24 gray bands), with the clip's frames p_j + delta, p_j = the source frame the
    timeline's map gives that output frame, delta = -4 .. +4. -> {key: dict(flat, scores {delta: mean correlation over the frames})}.
    A render of this timeline matches at delta 0 (+-1 from the shutter blur) with 0.65 and more; a master of another timeline scores about 0."""
    import clipio
    from concurrent.futures import ThreadPoolExecutor
    cap = cv2.VideoCapture(VID)
    sx = 1920.0 / frame.WIN_W                                   # master pixels of the window -> source pixels

    def band(img, y0, y1, x0, x1):
        return cv2.resize(img[y0:y1, x0:x1], (80, 24), interpolation=cv2.INTER_AREA).astype(np.float32)

    def z(v):
        v = v - v.mean()
        return v / (np.linalg.norm(v) + 1e-6)

    (x0a, y0a) = (40, 664 - frame.WIN_Y) if frame.VERT else (460, 80)
    (x0b, y0b) = (40, 1090 - frame.WIN_Y) if frame.VERT else (300, 660)
    wa, ha = (1000, 170) if frame.VERT else (1020, 250)
    jobs = []
    for key, i, n0, js in cases:
        js = [j for j in js if 0 <= n0 + j < T.N_FRAMES]
        if not js:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, n0 + js[0])
        m, flat, got = [], False, []
        for j in range(js[0], js[-1] + 1):                      # consecutive frames: read them all, keep the wanted ones
            ok, fr = cap.read()
            if not ok:
                break
            if j not in js:
                continue
            gray = cv2.cvtColor(fr[frame.WIN_Y:frame.WIN_Y + frame.WIN_H, :frame.WIN_W], cv2.COLOR_BGR2GRAY)
            vv = np.concatenate([band(gray, y0a, y0a + ha, x0a, x0a + wa).ravel(), band(gray, y0b, y0b + ha, x0b, x0b + wa).ravel()])
            flat = flat or float(vv.std()) < 3.0                  # black / one colour: nothing to match
            m.append(z(vv))
            got.append(j)
        if got == js:
            jobs.append((key, i, n0, js, m, flat))

    def work(job):
        key, i, n0, js, zm, flat = job
        s = T.SEGS[i]
        pj = [float(s["map"](T.frame_beat(n0 + j))[0]) for j in js]
        lo, hi = max(0, int(np.floor(min(pj))) - 5), min(clipio.n_frames(s["clip"]) - 1, int(np.ceil(max(pj))) + 5)
        try:
            src = clipio.read_frames(s["clip"], lo, hi, crop=False)
        except AssertionError:
            return None
        zs = []
        for a in src:                                           # source frame (1920x1080) in the same band geometry: the window is scaled by sx
            g = cv2.cvtColor(cv2.cvtColor(a, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2GRAY)
            zs.append(z(np.concatenate([band(g, int(y0a * sx), int((y0a + ha) * sx), int(x0a * sx), int((x0a + wa) * sx)).ravel(),
                                        band(g, int(y0b * sx), int((y0b + ha) * sx), int(x0b * sx), int((x0b + wa) * sx)).ravel()])))
        scores = {}
        for dl in range(-4, 5):
            c = [float(zm[t] @ zs[int(round(pj[t])) + dl - lo]) for t in range(len(js)) if 0 <= int(round(pj[t])) + dl - lo < len(zs)]
            if len(c) == len(js):
                scores[dl] = float(np.mean(c))
        return (key, dict(flat=flat, scores=scores)) if scores else None

    with ThreadPoolExecutor(workers) as ex:
        return dict(r for r in ex.map(work, jobs) if r)


def alignment(VID, T_=None, back=0, ahead=5):
    """For every kill: does the master show the source frames the timeline asks for around the beat? Nothing is printed. The master's frames
    n0+j (n0 = the kill's frame) against the clip's frames, see _match. Which j: when the take has PRE_CLEAR frames or more before the shot
    (the 14-frame lead of a drafted take, a bullet-time lead-in, a later kill of an M take), the frames -6 .. -1: footage only, before any
    kill accent (punch, shake, exposure pop, radial burst, rays, inverted frame), so the measure is clean (measured on a vertical edit with
    the model accents: 0.69 to 0.98 at offset 0 before the shot against 0.57 with a false best offset of +4 after a level-3 shot). A take cut
    a few frames before its shot (the worked example's 4-frame lead): j = -back .. ahead after it, a level 3 kill's impact frames +0..+2
    left out. -> list of dicts: beat, level, take, clip, K, n0, measurable (False: a flat picture, nothing to match), delta
    (the best offset; None when nothing matched: score under 0.5), score, clear (the score of delta against the score of 0: how clearly it beats
    'no offset'; a static scene has ~0 and says nothing), scores."""
    global T
    T = T_ if T_ is not None else (T or preflight.timeline())
    kills = {}
    cases = []
    for q, (k, lv, i) in enumerate(T.KILLS):
        n0 = frame_of(k)
        lead = n0 - int(math.ceil((T.SEGS[i]["r0"] - T.R0) * T.FPB - 1e-6))     # output frames from the take's cut to this shot
        if lead >= PRE_CLEAR:
            js = list(range(-PRE_N, 0))
        else:
            js = list(range(3 if lv == 3 else -back, (ahead + 2 if lv == 3 else ahead) + 1))
        cases.append((q, i, n0, js))
        kills[q] = (k, lv, i, n0)
    out = []
    for q, r in sorted(_match(VID, cases).items()):
        k, lv, i, n0 = kills[q]
        sc = r["scores"]
        best = max(sc, key=sc.get)
        out.append(dict(beat=k, level=lv, take=i, clip=T.SEGS[i]["clip"], K=float(T.SEGS[i]["map"](k)[0]), n0=n0, measurable=not r["flat"],
                        delta=best if sc[best] >= 0.5 else None, score=sc[best], clear=sc[best] - sc.get(0, sc[best]), scores=sc))
    return out


def faithful(VID, frames, T_=None):
    """Does the master show, around each output frame of `frames` (the jumps / stalls analyze() flagged), the source frames the timeline asks for?
    If it does, the jump or pause is in the footage itself (a shot that did not kill, an ability, a real pause of the aim): the render is
    faithful, the edit is not at fault. -> {n: dict(ok, delta, score, scores)}; ok = the match at delta 0 is 0.6 or more and no offset of 2 or
    more beats it by 0.03 (a flat picture gives ok False: not measurable). Only the frames n-2 .. n+2 of the same take count."""
    global T
    T = T_ if T_ is not None else (T or preflight.timeline())
    cases = []
    for n in frames:
        i = T.active(T.frame_beat(n))[0]
        js = [j for j in range(-2, 3) if 0 <= n + j < T.N_FRAMES and T.active(T.frame_beat(n + j))[0] == i]
        cases.append((n, i, n, js))
    out = {}
    for n, r in _match(VID, cases).items():
        sc = r["scores"]
        best = max(sc, key=sc.get)
        out[n] = dict(ok=(not r["flat"]) and sc.get(0, 0) >= 0.6 and not (abs(best) >= 2 and sc[best] - sc.get(0, 0) >= 0.03),
                      delta=best, score=sc.get(0, 0), scores=sc)
    return out


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        sys.exit("usage: python check.py master.mp4 [--sheets]      (the montage made by run.sh: 1920x1080, or 1080x1920 when timeline.py says FRAME = \"vertical\"; with sound)")
    VID = sys.argv[1]
    if not os.path.isfile(VID):
        sys.exit(f"check.py: {VID} not found in {os.getcwd()}: give the path of the rendered montage (bash run.sh master.mp4 makes it)")
    try:
        res = analyze(VID, preflight.timeline(), "--sheets" in sys.argv)
    except Stop as e:
        sys.exit(str(e))
    if res["exit"]:
        sys.exit(res["exit"])


if __name__ == "__main__":
    main()
