"""Locate ffmpeg / ffprobe: $FF if set (the ffmpeg file, or the folder that holds it), else PATH, else the usual
Windows installs (winget, scoop, chocolatey, C:/ffmpeg, Program Files).
`python ff.py` prints the path (run.sh uses it)."""
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

if __name__ == "__main__":
    print(FF)
