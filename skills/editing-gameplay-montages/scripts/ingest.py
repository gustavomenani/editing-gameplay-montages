"""Bring the source files into the working format and give them short names in src/.

Working format (what clipio.py, mkpts.py, prep.py and everything downstream assume): every video in src/ is
1920x1080, 60 fps constant frame rate, frame n at t0 + n/60 on the original clock, tv-range bt709 yuv420p.

usage: python ingest.py [clips.json] [--only c1,c2] [--exact | --fast] [--aspect stretch|crop|pad] [--force] [--convert]

clips.json:  {"c1": "C:/path/clip1.mp4", "c2": "C:/path/cs2 stretched.mp4", "music": "C:/path/song.flac"}
(forward slashes, or doubled backslashes; UTF-8 with or without BOM, UTF-16 and ANSI files are read too).
Keep clips.json: it is the only record of which original file each short name stands for. The short names are
file names: no / \\ : * ? " < > | and not "ingest". The name "music" is the song: only its sound is used, even when
the file is a video.

What happens to each entry (one table line each: original size @ measured frame rate -> action, time taken):
  * a 1920x1080 video whose frames come every 1/60 s (median frame interval, within 0.5 fps; --convert converts it
    anyway), in a container the tools know (.mp4 .mkv .mov .m4v .webm .avi), whose audio starts at the start of the
    file, and that is not HDR: hard link (same drive, no extra disk space) or copy (other drive): src/c1.mp4.
    Nothing is decoded. A 60 fps recording with dropped frames (average rate a little under 60) is linked too: its
    frame indices stay the original's, which the Valorant raw-recording tools (refstyle/detect_kills.py, mykills.py)
    rely on; mkpts.py lists its gaps. Converting it would cost minutes and shift every frame index after the first gap.
    A song / any audio file: linked as it is (src/music.flac); a song inside a video container is extracted to
    src/music.flac (a few seconds).
  * the same kind of video in another container (.ts .flv .wmv .mts ...), or whose audio starts later / earlier than
    the file (the tools decode the audio from the start of the file, so a late start would put every sound too
    early): REMUXED to src/c1.mkv in seconds, the picture copied bit for bit (same frames, same pts, same indices),
    the audio re-written as FLAC with the offset applied.
  * any other video (other size, 4:3, 21:9, vertical, 120 / 144 / 165 / 240 fps, 30 fps, variable frame rate, HDR,
    full-range 10-bit): a converted working copy src/c1.mkv: x264 (fast, crf 9) yuv420p tv-range bt709 (render.py's
    colour tags) + the clip's audio as FLAC, 24 bit. HDR (PQ / HLG) is tone mapped to SDR (PQ: SDR white at 203 nits,
    mobius curve: the SDR range comes back within 2 grey levels, highlights roll off), approximately:
    for exact colours record SDR.

Geometry. An aspect narrower than 16:9 (4:3, 5:4, 16:10: CS2 "stretched") is STRETCHED to 16:9, which is what the
player saw; a wider one (21:9, 32:9) is cropped at the centre; a VERTICAL recording (phone, 9:16) is placed in the
middle of the 16:9 frame between black bars (the montage is horizontal: it looks small; film horizontally);
--aspect crop|pad|stretch overrides. A recording rotated by metadata (phone) is turned upright first. Scaling is
lanczos. Colour is decoded exactly as clipio.py does it (scale=in_range=tv:out_range=pc,format=rgb24), so a
conforming source that is forced through the conversion comes back with the same pixels up to the x264 rounding.

Time. Output frame n is the picture the source had at t = t0 + n/60, t0 = the first video pts; the source pts
(packet pts, as in mkpts.py) are used, so variable frame rate and any source rate are handled. A source frame
within 1.5 ms of t is used UNCHANGED (120 / 240 fps and any 60 fps source with its ~1 ms timestamp jitter: exact picks,
no interpolation). Otherwise:
  --exact  (default for clips up to 90 s) the two frames around t are interpolated at the exact fraction
           with RIFE (rifeutil.Tween, on the GPU). Slow: 3 to 10 frames per second on a GTX 1650.
  --fast   (default for longer clips) the nearest source frame, at most half a source frame (3.5 ms at 144 fps)
           off in time; where taking the nearest would repeat a frame of the source (a rate just under 60 fps) that
           one frame is interpolated instead. The manifest marks the clip "fast"; upgrade it later with
           `python ingest.py --exact --only c1` (same frame grid, so kill frames and timeline anchors stay valid).
  A source below 59.5 fps is always interpolated exactly, whatever the clip length: repeated frames are the stutter.
  Frames are NEVER passed through an ffmpeg fps filter. A hole of more than 0.25 s in the source timestamps (a
  recorder pause), or two frames with one timestamp, is not interpolated: the nearest frame is held there and the line says so.

Audio. The FIRST audio stream (track 1: OBS with several tracks puts the game / the mix there, the microphone and
Discord after it; a message names the others), FLAC, shifted so that a sound at original time T plays at T - t0 in
a converted copy (silence is added when the audio starts after the video, the head is cut when it starts before),
i.e. the file reads like a clip of the original: video frame n and audio sample n/60*rate belong together. In a
linked or remuxed file the picture keeps the original clock and the audio is placed on that same clock.
A video without audio is ingested all the same (the line says so; audio.py needs a sound track for every clip).

Output. src/ingest.json records per entry: original path and size, width, height, measured fps, method (linked |
copied | remuxed | exact | fast | audio), aspect policy, t0 (first video pts of the original), and for conversions the
frame counts (picked / nearest / interpolated / held, rife calls, largest time error of a non-interpolated frame).
Existing entries are kept (a warning when clips.json now names another file). --force re-ingests the selected entries;
--exact re-ingests the entries that were made with --fast. A re-ingested entry has the same frame grid but other
pictures: delete store/<clip>, re-run prep.py and mkpts.py (the script says so). A run that loaded RIFE ends the way
rifeutil.finish() does (no Vulkan unload crash). One bad entry (missing file, folder, unreadable) never stops the others;
the exit code is 1 when any entry failed, so `ingest.py && mkpts.py` stops. Long conversions print a progress line
every 20 s."""
import argparse, glob, json, os, queue, re, shutil, subprocess, sys, threading, time, traceback
import numpy as np
from ff import FF, FFPROBE

SW, SH, FPS = 1920, 1080, 60
LINKABLE = (".mp4", ".mkv", ".mov", ".m4v", ".webm", ".avi")      # what mkpts.py / kills_auto.py look for in src/
TOL = 0.0015                # s: a source frame this close to the wanted time is used unchanged
MAXGAP = 0.25               # s: a bigger hole between two source timestamps is not interpolated
EXACT_MAX_S = 90            # clips up to this length default to --exact
CONFORM_FPS = 0.5           # |rate - 60| below this and 1920x1080: link, do not convert
MIN_FPS_FAST = 59.5         # below this --fast is not allowed (it would repeat frames)
AUDIO_TOL = 0.004           # s: a linked file whose audio starts later than this would sound early: remux it
HDR_TRC = ("smpte2084", "arib-std-b67")
TONEMAP = ("zscale=t=linear:npl={npl},format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=mobius:param=0.5:desat=0:peak=4,"
           "zscale=t=bt709:m=bt709:r=tv,format=yuv420p")
RIFE_CALLS = 0
RIFE_LOADED = False


class Skip(Exception):
    """this entry cannot be ingested: the message says why; the other entries go on"""


def say(msg):
    print(msg, flush=True)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe(p):
    """-> (first real video stream dict or None, [audio stream dicts])"""
    st = []
    try:
        st = json.loads(run([FFPROBE, "-v", "error", "-show_streams", "-of", "json", p]).stdout or "{}").get("streams", [])
    except ValueError:
        pass
    vs = [s for s in st if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")]
    return (vs[0] if vs else None), [s for s in st if s.get("codec_type") == "audio"]


def packet_pts(p, index):
    """presentation time of every packet of video stream `index` (its decode time when a container has no pts), sorted"""
    out = run([FFPROBE, "-v", "error", "-select_streams", str(index), "-show_entries", "packet=pts_time,dts_time",
               "-of", "csv=p=0", p]).stdout
    vals = []
    for l in out.splitlines():
        f = l.strip().split(",")
        for x in f[:2]:
            try:
                vals.append(float(x))
                break
            except ValueError:
                continue
    return np.array(sorted(vals))


def fnum(s, default=None):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def sar_of(v):
    s = v.get("sample_aspect_ratio", "1:1")
    try:
        a, b = s.split(":")
        return float(a) / float(b) if float(b) and float(a) else 1.0
    except ValueError:
        return 1.0


def rotation(v):
    """degrees (0 / 90 / 180 / 270) the player turns the picture by: a phone holds the sensor sideways"""
    for sd in v.get("side_data_list") or []:
        if "rotation" in sd:
            return int(round(fnum(sd["rotation"], 0))) % 360
    return int(round(fnum((v.get("tags") or {}).get("rotate"), 0))) % 360


def shown_size(v):
    """(width, height) of the picture as ffmpeg decodes it (turned upright)"""
    w, h = int(v["width"]), int(v["height"])
    return (h, w) if rotation(v) in (90, 270) else (w, h)


def geometry(w, h, sar, policy):
    """-> (policy actually applied, text, filter chain up to the scale, pad filter or None, resamples?)"""
    target = SW / SH
    ar = w * sar / h
    resize = f"scale={SW}:{SH}"
    if abs(ar / target - 1) < 0.005:
        return "none", ("scale to 1920x1080" if (w, h) != (SW, SH) else "no resize"), [resize], None, (w, h) != (SW, SH)
    if policy == "auto":
        policy = "pad" if ar < 1 else "stretch" if ar < target else "crop"      # vertical: stretching would be absurd
    if policy == "stretch":
        return "stretch", f"stretch {w}x{h} to 16:9", [resize], None, True
    if policy == "crop":
        if ar > target:
            cw, ch = int(h * target / sar) // 2 * 2, h
        else:
            cw, ch = w, int(w * sar / target) // 2 * 2
        x, y = (w - cw) // 4 * 2, (h - ch) // 4 * 2
        return "crop", f"crop centre {cw}x{ch}", [f"crop={cw}:{ch}:{x}:{y}", resize], None, True
    if ar > target:
        sw, sh = SW, int(round(SW / ar / 2)) * 2
    else:
        sw, sh = int(round(SH * ar / 2)) * 2, SH
    return "pad", f"pad {sw}x{sh} in 16:9", [f"scale={sw}:{sh}"], f"pad={SW}:{SH}:{(SW - sw) // 2}:{(SH - sh) // 2}:black", True


def decode_filter(v, policy, hdr):
    w, h = shown_size(v)
    used, text, chain, pad, resample = geometry(w, h, sar_of(v), policy)
    rng = "pc" if v.get("color_range") == "pc" else "tv"
    flags = ":flags=lanczos+accurate_rnd+full_chroma_int" if resample else ""
    mat = "" if v.get("color_space") in ("bt709", "bt470bg", "smpte170m", "bt2020nc") else \
        f":in_color_matrix={'bt709' if h >= 720 else 'bt601'}"
    if hdr:
        # size first (in the source's own 10 bit YUV), tone map at 1080p, then the same RGB conversion as everything else
        tm = TONEMAP.format(npl=203 if v.get("color_transfer") == "smpte2084" else 100)      # HLG: scene referred, 100 nit display
        chain = chain[:-1] + [chain[-1] + flags, tm, "scale=in_range=tv:out_range=pc", "format=rgb24"]
        text += ", HDR tone mapped"
    else:
        chain = chain[:-1] + [chain[-1] + flags + f":in_range={rng}:out_range=pc" + mat, "format=rgb24"]
    if pad:
        chain.append(pad)
    return ",".join(chain), used, text


def has_filter(name):
    return f" {name} " in run([FF, "-hide_banner", "-filters"]).stdout


DECODE_FAULT = re.compile(r"error while decoding|missing picture|concealing|no frame|invalid data|non-existing PPS|corrupt|truncated", re.I)


def decode_faults(p, v):
    """[(start | end, first complaint, number of complaints)] of ffmpeg decoding the first and the last 2 s: a recording
    that crashed or starts in the middle of a GOP is damaged there, and frame indices read through clipio fail"""
    out = []
    for where, opts in (("start", ["-t", "2"]), ("end", ["-sseof", "-2"])):
        r = run([FF, "-v", "error"] + opts + ["-i", p, "-map", f"0:{v['index']}", "-f", "null", "-"])
        hits = [l.strip() for l in r.stderr.splitlines() if DECODE_FAULT.search(l)]
        if hits:
            out.append((where, hits[0], len(hits)))
    return out


def audio_filter(a, t_ref):
    """filter that makes the audio start at original time t_ref (-> working time 0); None without audio"""
    if a is None:
        return None
    sr = int(a.get("sample_rate") or 48000)
    shift = int(round((fnum(a.get("start_time"), t_ref) - t_ref) * sr))
    af = f"adelay=delays={shift}S:all=1," if shift > 0 else f"atrim=start_sample={-shift}," if shift < 0 else ""
    return af + "asetpts=N/SR/TB"


def make_plan(ts, fast):
    """Per output frame n: src (source index of the picture or the first of the pair), frac (0 = a source picture;
    otherwise the interpolation fraction towards src + 1), kind. The same grid in both modes."""
    n_src, t0 = len(ts), ts[0]
    N = int(np.floor((ts[-1] - t0 + TOL) * FPS)) + 1
    tn = t0 + np.arange(N) / FPS
    j = np.clip(np.searchsorted(ts, tn, side="right") - 1, 0, n_src - 2)
    lo, hi = ts[j], ts[j + 1]
    near = np.where(tn - lo <= hi - tn, j, j + 1)
    err = np.abs(tn - ts[near])
    gap = ((hi - lo) > MAXGAP) | ((hi - lo) < 1e-6)       # a hole, or two frames with the same timestamp
    frac = np.clip((tn - lo) / np.maximum(hi - lo, 1e-6), 0, 1)
    pick = err <= TOL
    kind = np.empty(N, "U7")                      # pick | nearest | interp | held
    if fast:
        dup = np.zeros(N, bool)
        dup[1:] = near[1:] == near[:-1]
        interp = dup & ~gap & ~pick
        kind[:] = np.where(pick, "pick", np.where(gap, "held", "nearest"))
        kind[interp] = "interp"
    else:
        kind[:] = np.where(pick, "pick", np.where(gap, "held", "interp"))
    src = np.where(kind == "interp", j, near)
    frac = np.where(kind == "interp", frac, 0.0)
    return N, src, frac, kind, err


class Counting:
    """Counts the calls RIFE gets (rifeutil.Tween calls process_cv2 once or twice)."""

    def __init__(self, rife):
        self.rife = rife

    def process_cv2(self, a, b, t):
        global RIFE_CALLS
        RIFE_CALLS += 1
        return self.rife.process_cv2(a, b, t)


def drop(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def convert(name, path, v, a, ts, mode, policy):
    """Write src/<name>.mkv. -> manifest fields."""
    global RIFE_LOADED
    import rifeutil
    rate = (len(ts) - 1) / (ts[-1] - ts[0])
    dur = ts[-1] - ts[0]
    if mode is None:
        mode = "exact" if dur <= EXACT_MAX_S else "fast"
    forced = ""
    if mode == "fast" and rate < MIN_FPS_FAST:
        mode, forced = "exact", " (below 60 fps: always exact)"
    N, src, frac, kind, err = make_plan(ts, mode == "fast")
    n_interp = int((kind == "interp").sum())
    hdr = v.get("color_transfer") in HDR_TRC
    if hdr and not has_filter("zscale"):
        raise Skip("HDR source and this ffmpeg has no zscale filter (needs libzimg: winget install Gyan.FFmpeg): cannot tone map; record SDR")
    vf, used, text = decode_filter(v, policy, hdr)

    tween = None
    if n_interp:                                  # load RIFE now: a PC that cannot run it must fail before the long decode
        try:
            tween = rifeutil.Tween(Counting(rifeutil.load()))
            RIFE_LOADED = True
        except SystemExit as e:
            raise Skip(str(e.code))
        except Exception as e:
            raise Skip(f"RIFE (the GPU interpolation) could not start: {type(e).__name__}: {e}; needs a Vulkan GPU and its driver")
    af = audio_filter(a, ts[0])
    dst = os.path.join("src", name + ".mkv")
    part = os.path.join("src", "_" + name + ".part")
    say(f"  {name}: converting {N} frames ({N / FPS:.0f} s)" + (f", {n_interp} of them interpolated with RIFE" if n_interp else "") + " ...")
    dec = subprocess.Popen([FF, "-v", "error", "-i", path, "-map", f"0:{v['index']}", "-vf", vf, "-fps_mode", "passthrough",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc_cmd = [FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{SW}x{SH}", "-framerate", str(FPS), "-i", "-"]
    if af is not None:
        enc_cmd += ["-i", path]
    enc_cmd += ["-map", "0:v:0"] + (["-map", f"1:{a['index']}", "-af", af, "-c:a", "flac", "-sample_fmt", "s32"] if af is not None else []) + [
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-vf", "scale=out_color_matrix=bt709:out_range=tv,setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv,format=yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "9", "-g", "60",
        "-f", "matroska", part]
    enc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE)

    frames_q, out_q = queue.Queue(maxsize=6), queue.Queue(maxsize=6)

    def reader():
        for _ in range(len(ts)):
            buf = np.empty((SH, SW, 3), np.uint8)
            mv, got = memoryview(buf).cast("B"), 0
            while got < len(mv):
                k = dec.stdout.readinto(mv[got:])
                if not k:
                    break
                got += k
            if got < len(mv):
                frames_q.put(None)
                return
            frames_q.put(buf)
        frames_q.put(None)

    def writer():
        ok = True
        while True:
            img = out_q.get()
            if img is None:
                return
            if ok:
                try:
                    enc.stdin.write(img)
                except OSError:
                    ok = False                            # the encoder died (reported below); keep draining so nothing blocks

    threading.Thread(target=reader, daemon=True).start()
    wt = threading.Thread(target=writer, daemon=True)
    wt.start()

    cache, loaded = {}, -1

    def get(i):
        nonlocal loaded
        while loaded < i:
            f = frames_q.get()
            if f is None:
                raise Skip(f"ffmpeg decoded only {loaded + 1} of the {len(ts)} frames that the packet table lists "
                           f"(a broken start or end?): cannot index frames; re-encode the source or trim it first")
            loaded += 1
            cache[loaded] = f
        return cache[i]

    t_start = last = time.time()
    tty = sys.stderr.isatty()
    try:
        for n in range(N):
            i = int(src[n])
            for k in [k for k in cache if k < i]:
                del cache[k]
            if kind[n] == "interp":
                img = tween(get(i), get(i + 1), float(frac[n]), tag=i)
            else:
                img = get(i)
            out_q.put(np.ascontiguousarray(img))
            now = time.time()
            if n and now - last >= (1.0 if tty else 20.0):
                last = now
                fps = (n + 1) / (now - t_start)
                msg = f"{name}: {n + 1}/{N} frames, {fps:.1f} fps, about {(N - n - 1) / fps / 60:.1f} min left"
                if tty:
                    sys.stderr.write("\r  " + msg + "  ")
                else:
                    say("  " + msg)
        out_q.put(None)
        wt.join()
        try:
            enc.stdin.close()
        except OSError:
            pass                                          # the encoder died: its exit code is checked below
        # the reader may be ahead of the last frame used: drain its queue so the decoder can end
        while frames_q.get() is not None:
            pass
    except BaseException:
        dec.kill()
        enc.kill()
        drop(part)
        raise
    dec.stdout.close()
    dec.wait()
    rc = enc.wait()
    if tty:
        sys.stderr.write("\r" + " " * 70 + "\r")
    if rc != 0:
        drop(part)
        raise Skip(f"the ffmpeg encoder failed (exit code {rc})")
    for old in glob.glob(os.path.join("src", glob.escape(name) + ".*")):
        os.remove(old)
    os.replace(part, dst)
    fixed = ~np.isin(kind, ["interp"])
    return dst, dict(
        method=mode, aspect=used, frames=N, picked=int((kind == "pick").sum()), nearest=int((kind == "nearest").sum()),
        interpolated=n_interp, held=int((kind == "held").sum()), rife_calls=RIFE_CALLS,
        max_error_ms=round(float(err[fixed].max() * 1000), 3) if fixed.any() else 0.0), \
        f"converted: {text}, {mode}{forced}: {int((kind == 'pick').sum())} picked, {int((kind == 'nearest').sum())} nearest, " \
        f"{n_interp} interpolated" + (f", {int((kind == 'held').sum())} held across a hole or repeated timestamps" if (kind == "held").any() else ""), \
        N, n_interp > 0


def remux(name, path, v, a):
    """Same picture (stream copy: same frames, pts and indices), audio placed on the file's own clock. -> dst"""
    dst = os.path.join("src", name + ".mkv")
    part = os.path.join("src", "_" + name + ".part")
    cmd = [FF, "-v", "error", "-y", "-copyts", "-i", path, "-map", f"0:{v['index']}", "-c:v", "copy"]
    if a is not None:
        cmd += ["-map", f"0:{a['index']}", "-af", audio_filter(a, 0.0), "-c:a", "flac", "-sample_fmt", "s32"]
    cmd += ["-map_metadata", "-1", "-map_chapters", "-1", "-f", "matroska", part]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        drop(part)
        return None, (r.stderr.strip().splitlines() or ["ffmpeg failed"])[-1]
    for old in glob.glob(os.path.join("src", glob.escape(name) + ".*")):
        os.remove(old)
    os.replace(part, dst)
    return dst, None


def extract_audio(name, path, a):
    """a song inside a video container (or an audio file that a tool would mistake for a clip): src/<name>.flac"""
    dst = os.path.join("src", name + ".flac")
    part = os.path.join("src", "_" + name + ".part")
    r = subprocess.run([FF, "-v", "error", "-y", "-i", path, "-map", f"0:{a['index']}", "-vn", "-c:a", "flac", "-sample_fmt", "s32",
                        "-map_metadata", "-1", "-f", "flac", part], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        drop(part)
        raise Skip("could not extract the sound: " + (r.stderr.strip().splitlines() or ["ffmpeg failed"])[-1])
    for old in glob.glob(os.path.join("src", glob.escape(name) + ".*")):
        os.remove(old)
    os.replace(part, dst)
    return dst


def link(p, dst):
    """hard link (same drive: instant, no disk space) or, when that is impossible (another drive, a FAT / network
    drive), a copy written under a temporary name so that an interrupted copy is never mistaken for the clip"""
    drop(dst)
    try:
        os.link(p, dst)
        return "linked"
    except OSError:
        pass
    part = os.path.join(os.path.dirname(dst), "_" + os.path.basename(dst) + ".part")
    say(f"  copying {os.path.getsize(p) / 1e6:.0f} MB (the original is on another drive or one without hard links) ...")
    try:
        shutil.copy2(p, part)
    except BaseException:
        drop(part)
        raise
    os.replace(part, dst)
    return "copied"


def read_text(path):
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):                   # PowerShell 5 `>` and Out-File write UTF-16
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")                          # PowerShell's Set-Content -Encoding UTF8 adds a BOM
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")           # Notepad "ANSI"


def load_spec(path):
    if not os.path.isfile(path):
        raise SystemExit(f"{path} not found: write it first, {{\"c1\": \"C:/path/clip.mp4\", \"music\": \"C:/path/song.flac\"}} (forward slashes)")
    try:
        spec = json.loads(read_text(path))
    except ValueError as e:
        raise SystemExit(f"{path} is not valid JSON: {e}. Windows paths need forward slashes (C:/Users/me/clip.mp4) "
                         "or doubled backslashes (C:\\\\Users\\\\me\\\\clip.mp4), and commas between the entries")
    if not isinstance(spec, dict) or not spec:
        raise SystemExit(f"{path} must be an object {{\"c1\": \"C:/path/clip.mp4\", ...}} with at least one entry")
    return spec


BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]|^(con|prn|aux|nul|com\d|lpt\d)$', re.I)       # characters Windows refuses, device names


def check_names(spec):
    low = {}
    for k, p in spec.items():
        if BAD_NAME.search(k) or k != k.strip() or k.endswith(".") or not k or k.lower() == "ingest":
            raise SystemExit(f"clips.json: {k!r} cannot be a short name (it becomes src/{k}.mp4): no / \\ : * ? \" < > |, "
                             "no spaces at the ends, not \"ingest\", not a Windows device name (con, nul, aux, com1 ...)")
        if not isinstance(p, str) or not p.strip():
            raise SystemExit(f"clips.json: the value of {k!r} must be the path of a file, as text")
        if k.lower() in low:
            raise SystemExit(f"clips.json: {k!r} and {low[k.lower()]!r} differ only by case: Windows would make one file of them")
        low[k.lower()] = k


def same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def ingest_entry(name, p, args, mode):
    """-> (manifest entry, summary line, used RIFE?)"""
    t_in = time.time()
    is_music = name.lower() == "music"
    v, audios = probe(p)
    a = audios[0] if audios else None
    ts = None
    if v is not None and not is_music:
        ts = packet_pts(p, v["index"])
        if len(ts) < 2:
            v = None                                  # one picture: the cover art of a song, not a video
    elif is_music:
        v = None
    ext = os.path.splitext(p)[1].lower()
    ent = dict(original=p, size=os.path.getsize(p))
    if len(audios) > 1:
        names = ", ".join(f"#{i + 1} {s.get('tags', {}).get('title') or s.get('tags', {}).get('handler_name') or ''}".strip() for i, s in enumerate(audios))
        say(f"{name}: {len(audios)} audio tracks ({names}): using the first (OBS: track 1 = game / mix); the others are not used")
    if v is None:
        if a is None:
            raise Skip(f"{p} has no sound and no video frames: not a clip or a song ffmpeg can read (corrupt or unfinished recording?)")
        if ext in LINKABLE:                           # an audio file with a video extension would be taken for a clip
            dst = extract_audio(name, p, a)
            ent["method"] = "audio"
            return ent, f"audio in a {ext} container -> extracted {dst}  ({time.time() - t_in:.1f} s)", False
        for o in glob.glob(os.path.join("src", glob.escape(name) + ".*")):
            os.remove(o)
        dst = os.path.join("src", name + ext)
        how = link(p, dst)
        ent["method"] = how
        return ent, f"not a video -> {how} {dst}  ({time.time() - t_in:.1f} s)", False

    w, h = shown_size(v)
    if ts[-1] - ts[0] <= 0:
        raise Skip(f"all {len(ts)} video frames of {p} carry the same timestamp: cannot place them in time; re-encode it with ffmpeg first")
    rate = (len(ts) - 1) / (ts[-1] - ts[0])
    k = min(30, len(ts) - 1)                          # the recorder's frame rate, unaffected by dropped frames: median
    mrate = 1.0 / float(np.median((ts[k:] - ts[:-k]) / k))     # over 30-frame spans (pts are rounded to ms: 16/17/17)
    desc = f"{w}x{h} @ {rate:.3f} fps"
    ent.update(width=w, height=h, fps=round(rate, 4), t0=round(float(ts[0]), 6))
    if a is None:
        say(f"{name}: NO AUDIO in {p}: its game sound will be silent (audio.py needs a sound track for every clip it uses)")
    hdr = v.get("color_transfer") in HDR_TRC
    full10 = v.get("color_range") == "pc" and not str(v.get("pix_fmt", "")).startswith("yuvj")    # clipio reads tv
    conform = (w, h) == (SW, SH) and abs(mrate - FPS) < CONFORM_FPS and not hdr and not full10
    a0 = fnum(a.get("start_time"), 0.0) if a is not None else 0.0
    why = []
    if ext not in LINKABLE:
        why.append(f"the {ext} container is not one the other tools read")
    if abs(a0) > AUDIO_TOL:
        why.append(f"its audio starts {a0 * 1000:+.0f} ms from the start of the file")
    if rotation(v) in (90, 270):
        say(f"{name}: WARNING rotated by {rotation(v)} degrees in the metadata ({v['width']}x{v['height']} coded): turned upright, now {w}x{h}")
    if h > w:
        say(f"{name}: WARNING vertical recording ({w}x{h}): the montage is horizontal 16:9, so this clip will sit in the middle "
            "between black bars and look small; film horizontally, or pass --aspect stretch|crop")
    if conform:                                       # nothing decodes a linked clip here: look at its first and last 2 s
        for where, line, n in decode_faults(p, v):
            say(f"{name}: WARNING damaged {where} of the recording ({n} ffmpeg messages, first: {line}): the frames there cannot be "
                "read, a tool that starts at frame 0 (or ends at the last frame) will stop; use footage away from the damaged part")
    if conform and not args.convert and not why:
        for o in glob.glob(os.path.join("src", glob.escape(name) + ".*")):
            os.remove(o)
        dst = os.path.join("src", name + ext)
        how = link(p, dst)
        ent.update(method=how, aspect="none")
        gap = "" if abs(rate - FPS) < CONFORM_FPS else f"; 60 fps with dropped frames ({rate:.3f} on average): see mkpts.py"
        return ent, f"{desc} -> {how} {dst}{gap}  ({time.time() - t_in:.1f} s)", False
    if conform and not args.convert:
        dst, err = remux(name, p, v, a)
        if dst:
            ent.update(method="remuxed", aspect="none")
            return ent, f"{desc} -> remuxed {dst} ({'; '.join(why)}; picture untouched)  ({time.time() - t_in:.1f} s)", False
        say(f"{name}: remux failed ({err}); converting instead")
    if hdr:
        say(f"{name}: WARNING HDR source ({v['color_transfer']}): tone mapped to SDR, colours are approximate; record SDR for exact colours")
    if full10:
        say(f"{name}: full-range {v.get('pix_fmt')} source: converted (the tools read video as limited range)")
    dst, info, text, nfr, used_rife = convert(name, p, v, a, ts, mode, args.aspect)
    ent.update(info)
    el = time.time() - t_in
    return ent, f"{desc} -> {text}  ({el:.1f} s, {nfr / el:.1f} frames/s)", used_rife


def end_now(code):
    """End the process without running the unload handlers: the Vulkan runtime behind RIFE segfaults while the process
    unloads (exit code 139) although all the work is written. Same as rifeutil.finish(), which has no exit code."""
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = ctypes.c_void_p
        k.TerminateProcess(ctypes.c_void_p(k.GetCurrentProcess()), code)
    os._exit(code)


def main():
    try:
        sys.stdout.reconfigure(errors="replace")      # an emoji in a path must not crash a cp1252 console
        sys.stderr.reconfigure(errors="replace")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clips", nargs="?", default="clips.json")
    ap.add_argument("--only", help="comma separated names")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--exact", action="store_true", help="interpolate frames that fall between source frames (default up to 90 s)")
    g.add_argument("--fast", action="store_true", help="nearest source frame instead (default for longer clips)")
    ap.add_argument("--aspect", choices=("stretch", "crop", "pad"), default="auto",
                    help="stretch (default for narrower than 16:9), crop (default for wider), pad (default for vertical)")
    ap.add_argument("--convert", action="store_true", help="also convert a 1920x1080 ~60 fps source instead of linking it (testing)")
    ap.add_argument("--force", action="store_true", help="re-ingest entries that already exist")
    args = ap.parse_args()

    spec = load_spec(args.clips)
    check_names(spec)
    names = list(spec)
    if args.only:
        want = [x.strip() for x in args.only.split(",") if x.strip()]
        bad = [x for x in want if x not in spec]
        if bad:
            raise SystemExit(f"--only: not in {args.clips}: {', '.join(bad)}")
        names = [x for x in names if x in want]
    mode = "exact" if args.exact else "fast" if args.fast else None
    os.makedirs("src", exist_ok=True)
    for stale in glob.glob(os.path.join("src", "_*.part")):          # an interrupted run's half-written file
        drop(stale)
    mf_path = os.path.join("src", "ingest.json")
    manifest = json.load(open(mf_path, encoding="utf-8")) if os.path.exists(mf_path) else {}
    global RIFE_CALLS
    rife_used = False
    redo, failed = [], []
    for name in names:
        p = os.path.expanduser(spec[name].strip().strip('"'))
        have = sorted(glob.glob(os.path.join("src", glob.escape(name) + ".*")))
        old = manifest.get(name)
        try:
            if have and not args.force and not (args.exact and old and old.get("method") == "fast"):
                note = ""
                if old and old.get("original") and not same_path(old["original"], p):
                    note = f"  WARNING clips.json now names {p}, but this was made from {old['original']}: --force to redo it"
                elif old and old.get("size") and os.path.isfile(p) and os.path.getsize(p) != old["size"]:
                    note = f"  WARNING the original changed size since it was ingested: --force to redo it"
                say(f"{name}: kept {have[0]}" + (f" ({old['method']})" if old else "") + note)
                continue
            if os.path.isdir(p):
                raise Skip(f"{p} is a folder, not a file: name the video file")
            if not os.path.isfile(p):
                raise Skip(f"MISSING original {p}")
            RIFE_CALLS = 0
            ent, line, used = ingest_entry(name, p, args, mode)
            rife_used |= used
            manifest[name] = ent
            say(f"{name}: {line}")
            if have and ent["method"] in ("exact", "fast"):
                redo.append(name)
        except Skip as e:
            say(f"{name}: {e}")
            failed.append(name)
        except KeyboardInterrupt:
            raise
        except Exception as e:                                       # a bug or an odd file: report it, go on with the rest
            say(f"{name}: FAILED with {type(e).__name__}: {e}")
            if not isinstance(e, OSError):                          # disk full / permission: the message says it all
                traceback.print_exc()
            failed.append(name)
        if name in manifest and not glob.glob(os.path.join("src", glob.escape(name) + ".*")):
            del manifest[name]                                       # the failed re-ingest removed the old file: no stale record
        json.dump(manifest, open(mf_path, "w", encoding="utf-8"), indent=1)
    for name in redo:
        todo = f"delete store/{name}, re-run mkpts.py {name} and prep.py" if os.path.isdir(os.path.join("store", name)) else f"re-run mkpts.py {name}"
        say(f"{name}: re-ingested (same frame grid, other pictures): {todo}")
    if failed:
        say(f"{len(failed)} of {len(names)} entries NOT ingested: {', '.join(failed)}")
    if RIFE_LOADED or rife_used:
        end_now(1 if failed else 0)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
