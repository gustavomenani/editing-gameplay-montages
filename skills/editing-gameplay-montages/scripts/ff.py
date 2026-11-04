"""Locate ffmpeg / ffprobe: $FF if set (the ffmpeg file, or the folder that holds it), else PATH, else the usual
Windows installs (winget, scoop, chocolatey, C:/ffmpeg, Program Files).
`python ff.py` prints the path (run.sh uses it).

Also the two timing helpers every script that builds the delivered file shares:
  limiter(limit)   the master limiter filter, `alimiter ... latency=1`. ffmpeg's alimiter delays its output by the look-ahead
                   (attack 3 ms = 143 samples = 2.979 ms in every master measured) unless latency=1; with it the output is the same
                   samples 143 earlier, so the song / gunshots / thumps stay where mix.wav has them (audio.master_chain(),
                   peakguard.filters(), the house run.sh / deliver.sh all take it from here).
  check_pts(...)   the picture's time lattice of a joined video: `python ff.py pts video.mp4 N [join_frame ...]` exits 1 and names
                   the join when a video pts step is not exactly 1/60 s or the frame count is not N (run.sh runs it right after the
                   concat: the mp4 muxer rounds a part's duration to whole milliseconds, concat then starts the next part early)."""
import glob, os, re, shutil, sys

EXE = ".exe" if os.name == "nt" else ""


def _natural(p):
    """sort key that puts ffmpeg-10.0 after ffmpeg-9.0.2 (plain string order would not)"""
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", p.replace("\\", "/"))]


def _from_env():
    p = (os.environ.get("FF") or "").strip().strip('"')
    if not p:
        return None, None
    q = os.path.join(p, "ffmpeg" + EXE) if os.path.isdir(p) else p
    if os.path.isfile(q):
        return q, None
    return shutil.which(p), p                      # FF=ffmpeg (a name on PATH) is fine; a path that does not exist is reported


def _search():
    p = shutil.which("ffmpeg")
    if p:
        return p
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA", "")
    hits = sorted(glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "*", "bin", "ffmpeg.exe")), key=_natural)
    if hits:
        return hits[-1]
    for c in (os.path.join(local, "Microsoft", "WinGet", "Links", "ffmpeg.exe"),
              os.path.join(home, "scoop", "shims", "ffmpeg.exe"),
              os.path.join(home, "scoop", "apps", "ffmpeg", "current", "bin", "ffmpeg.exe"),
              "C:/ProgramData/chocolatey/bin/ffmpeg.exe", "C:/ffmpeg/bin/ffmpeg.exe",
              "C:/Program Files/ffmpeg/bin/ffmpeg.exe", "C:/Program Files (x86)/ffmpeg/bin/ffmpeg.exe"):
        if os.path.isfile(c):
            return c
    return None


def _find():
    found, bad = _from_env()
    if found:
        return found
    found = _search()
    if found:
        if bad:
            print(f"ff.py: FF={bad} does not exist, using {found}", file=sys.stderr)
        return found
    raise SystemExit((f"FF={bad} does not exist and " if bad else "") +
                     "ffmpeg not found: set FF to its full path, or install it (winget install Gyan.FFmpeg)")


def _find_probe(ff):
    p = os.path.join(os.path.dirname(ff), "ffprobe" + os.path.splitext(ff)[1])
    if os.path.isfile(p):
        return p
    p = shutil.which("ffprobe")
    if p:
        return p
    raise SystemExit(f"ffprobe not found next to {ff} or on PATH: install the full ffmpeg build (winget install Gyan.FFmpeg)")


FF = _find()
FFPROBE = _find_probe(FF)


def limiter(limit=0.82):
    """The master limiter (see the module docstring): latency=1 compensates the 3 ms look-ahead, nothing is delayed."""
    return "alimiter=limit=%.4f:attack=3:release=60:level=disabled:latency=1" % limit


def check_pts(video, n_frames, joins=(), fps=60):
    """Every video pts step of `video` must be exactly 1/fps s, the first pts 0 and the packet count n_frames. Returns the list of
    problems (empty = exact). `joins` = the first frame of every joined part after the first (run.sh: N/3 and 2N/3), so a bad step
    is named by the join it sits on."""
    import json, subprocess
    from fractions import Fraction
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=time_base:packet=pts", "-of", "json", video],
                       capture_output=True, text=True)
    if r.returncode or not r.stdout.strip():
        return ["ffprobe could not read %s: %s" % (video, r.stderr.strip()[-200:])]
    try:
        j = json.loads(r.stdout)
        tb = Fraction(j["streams"][0]["time_base"])
    except (ValueError, KeyError, IndexError, TypeError) as e:      # no video stream, or output that is not the JSON asked for: a problem, not a traceback
        return ["ffprobe's output for %s cannot be read (%s: %s)" % (video, type(e).__name__, str(e)[:120] or "empty")]
    pts = sorted(int(p["pts"]) for p in j["packets"] if "pts" in p)
    out = []
    if len(pts) != n_frames:
        out.append("%d video frames instead of %d" % (len(pts), n_frames))
    step = Fraction(1, fps) / tb
    if step.denominator != 1:
        return out + ["the video time base %s cannot hold 1/%d s exactly (a multiple of %d ticks per second is needed)" % (tb, fps, fps)]
    step = int(step)
    if pts and pts[0] != 0:
        out.append("the first pts is %d ticks (%.4f ms), not 0" % (pts[0], float(pts[0] * tb) * 1000))
    bad = [i + 1 for i in range(len(pts) - 1) if pts[i + 1] - pts[i] != step]
    for f in bad[:6]:
        name = ""
        for jn, jf in enumerate(joins):
            if f == jf:
                name = " = the join between part %d and part %d" % (jn, jn + 1)
        out.append("pts step into frame %d is %d ticks, not %d (%.4f ms, not %.4f ms)%s" % (
            f, pts[f] - pts[f - 1], step, float((pts[f] - pts[f - 1]) * tb) * 1000, 1000.0 / fps, name))
    if len(bad) > 6:
        out.append("... %d irregular steps in all" % len(bad))
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "pts":
        if len(sys.argv) < 4:
            sys.exit("usage: python ff.py pts video.mp4 N_FRAMES [first_frame_of_part_1 first_frame_of_part_2 ...]")
        bad = check_pts(sys.argv[2], int(sys.argv[3]), [int(a) for a in sys.argv[4:]])
        for b in bad:
            print("ff.py pts: " + b, file=sys.stderr)
        sys.exit(1 if bad else 0)
    print(FF)
