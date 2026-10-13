"""Exact, index-based access to the source clips.

Frame n of a clip is the n-th frame in presentation order; its time is pts[n] (the clips are
60 fps with ~1 ms timestamp jitter). Frames are always fetched by index, never through an fps
filter, so nothing is duplicated or dropped."""
import glob, json, os, subprocess, sys
import numpy as np
from ff import FF, FFPROBE

SW, SH = 1920, 1080                     # size of the source clips
CROP_X, CROP_W = 288, 1344              # region of the source that the montage can ever show (render.py SRC_W)
_pts = {}
_untagged = {}
BT709 = "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709"


def _no_clip(clip):
    if not os.path.isdir("src"):
        return f"no src/ folder in {os.getcwd()}: run the scripts from the project folder, after `python ingest.py` (it reads clips.json)"
    have = sorted({os.path.splitext(f)[0] for f in os.listdir("src") if not f.startswith("_") and f != "ingest.json"})
    return (f"no clip {clip!r} in src/ (there: {', '.join(have) or 'nothing'}); the names are the keys of clips.json, "
            "`python ingest.py` makes src/, then `python mkpts.py`")


def path(clip):
    """src/<clip>.<any extension>"""
    hits = sorted(glob.glob(f"src/{glob.escape(clip)}.*"))
    if not hits:
        raise FileNotFoundError(_no_clip(clip))
    return hits[0]


def pts(clip):
    if clip not in _pts:
        p = f"pts/{clip}.csv"
        if not os.path.isfile(p):
            path(clip)                                                # raises the "no such clip" message when it is the name
            raise FileNotFoundError(f"{p} is missing: run `python mkpts.py {clip}` (or `python mkpts.py` for every clip) after `python ingest.py`")
        if os.path.getmtime(path(clip)) > os.path.getmtime(p) + 1:
            print(f"clipio: {path(clip)} is newer than {p}: if it was re-ingested, run `python mkpts.py {clip}` again", file=sys.stderr)
        _pts[clip] = np.array(sorted(float(l.split(",")[0]) for l in open(p) if l.strip()))
    return _pts[clip]


def n_frames(clip):
    return len(pts(clip))


def t2n(clip, t):
    """Source time (seconds, same clock as the audio) -> fractional frame index.
    Uses the real time table: a recording linked by ingest.py may have dropped frames (gaps of up to 0.6 s),
    so an even grid over the whole clip would be off by that much after the first gap."""
    p = pts(clip)
    return np.interp(t, p, np.arange(len(p)))


def n2t(clip, n):
    p = pts(clip)
    return np.interp(n, np.arange(len(p)), p)


def colour_fix(clip):
    """A recording linked by ingest.py may carry no colour matrix tag (some recorders): swscale then assumes
    bt601, which tints a bt709 picture. Tell the filter graph it is bt709 (what every 1080p recorder means)."""
    if clip not in _untagged:
        out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=color_space",
                              "-of", "json", path(clip)], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        try:
            cs = (json.loads(out or "{}").get("streams") or [{}])[0].get("color_space", "unknown")
        except ValueError:
            cs = "unknown"
        _untagged[clip] = cs in ("unknown", "unspecified", "reserved", "")
    return BT709 if _untagged[clip] else None


def frame_args(clip, a, b, vf=None):
    """ffmpeg arguments that output exactly frames a..b (inclusive) of the clip."""
    p = pts(clip)
    sel = f"select='between(t\\,{p[a] - 0.004:.4f}\\,{p[b] + 0.004:.4f})'"
    fix = colour_fix(clip)
    return ["-copyts", "-ss", f"{max(0.0, p[a] - 0.5):.4f}", "-i", path(clip), "-map", "0:v:0",
            "-vf", sel + ("," + fix if fix else "") + ("," + vf if vf else ""), "-fps_mode", "passthrough"]


def read_frames(clip, a, b, crop=True):
    """Frames a..b as a uint8 array (N, H, W, 3), RGB, converted with the clip's own colour matrix."""
    w = CROP_W if crop else SW
    vf = (f"crop={CROP_W}:{SH}:{CROP_X}:0," if crop else "") + "scale=in_range=tv:out_range=pc,format=rgb24"
    # -frames:v: stop after the last wanted frame (without it ffmpeg decodes the rest of the file: 30 s on a 2 minute clip)
    r = subprocess.run([FF, "-v", "error"] + frame_args(clip, a, b, vf) + ["-frames:v", str(b - a + 1), "-f", "rawvideo", "-"], capture_output=True)
    arr = np.frombuffer(r.stdout, np.uint8).reshape(-1, SH, w, 3)
    assert len(arr) == b - a + 1, (clip, a, b, len(arr), r.stderr.decode("utf-8", "replace")[-300:])
    return arr
