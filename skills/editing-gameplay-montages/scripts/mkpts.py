"""Write pts/<clip>.csv (the presentation time of every video frame) for the clips in src/, and report
what matters for smoothness: real frame rate, timestamp jitter, and gaps (frames the recorder dropped).

usage: python mkpts.py            every video file in src/
       python mkpts.py c1 c2      only these

Everything downstream addresses frames by INDEX through these tables (clipio.py); never by seeking to
a time and resampling with an fps filter. Exit code 1 when a named clip has no video frames."""
import glob, os, subprocess, sys
import numpy as np
from ff import FFPROBE
import clipio

VIDEO = (".mp4", ".mkv", ".mov", ".m4v", ".webm", ".avi")
try:
    sys.stdout.reconfigure(errors="replace")           # a clip name with an emoji must not crash a cp1252 console
except AttributeError:
    pass


def probe_text(args):
    return subprocess.run([FFPROBE, "-v", "error"] + args, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def packet_rows(p):
    """-> csv rows 'pts,duration,flags' of the first video stream (the decode time when a packet has no pts)"""
    out = probe_text(["-select_streams", "v:0", "-show_entries", "packet=pts_time,dts_time,duration_time,flags", "-of", "csv=p=0", p])
    rows = []
    for l in out.splitlines():
        f = l.strip().split(",")          # pts, dts, duration, flags
        if len(f) < 2:
            continue
        t = f[0] if f[0] not in ("", "N/A") else f[1]
        try:
            float(t)
        except ValueError:
            continue
        rows.append(",".join([t] + f[2:]))
    return rows


if sys.argv[1:]:
    names = sys.argv[1:]
else:
    names = sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob("src/*") if f.lower().endswith(VIDEO))
    names = [c for c in names if c.lower() != "music"]      # the song may be a video file: only its sound is used
os.makedirs("pts", exist_ok=True)
failed = 0
for c in names:
    try:
        p = clipio.path(c)
    except FileNotFoundError as e:
        print(f"{c}: {e}")
        failed += 1
        continue
    info = probe_text(["-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,r_frame_rate", "-of", "csv=p=0", p]).strip()
    rows = packet_rows(p)
    if len(rows) < 2:
        print(f"{c}: {p} has no video frames (an audio file? give it a name that is not a clip) -> no pts/{c}.csv")
        if os.path.exists(f"pts/{c}.csv"):
            os.remove(f"pts/{c}.csv")
        failed += 1
        continue
    open(f"pts/{c}.csv", "w", newline="\n").write("\n".join(rows) + "\n")
    t = np.array(sorted(float(r.split(",")[0]) for r in rows))
    n = len(t)
    d = np.diff(t) * 1000
    rate = (n - 1) / (t[-1] - t[0]) if t[-1] > t[0] else 0.0
    med = float(np.median(d))
    dev = (t - (t[0] + np.arange(n) / rate)) * 1000 if rate else np.zeros(n)
    gaps = np.where(d > 1.5 * med)[0]
    print(f"{c}: {info} | {n} frames, {t[-1] - t[0]:.2f} s, first pts {t[0]:.4f}, real rate {rate:.4f} fps")
    print("    frame interval ms: min %.1f  median %.1f  max %.1f | drift from an even grid: %+.1f .. %+.1f ms"
          % (d.min(), med, d.max(), dev.min(), dev.max()))
    w = info.split(",")
    if len(w) >= 3 and (int(w[1]), int(w[2])) != (clipio.SW, clipio.SH):
        print(f"    WARNING: {w[1]}x{w[2]}, not the working format {clipio.SW}x{clipio.SH}: src/ was not made by ingest.py; run it")
    k = min(30, n - 1)                       # the recorder's rate, as ingest.py measures it (dropped frames do not count)
    if abs(1000.0 / float(np.median((t[k:] - t[:-k]) / k * 1000)) - 60) > 0.5:
        print("    WARNING: not 60 fps, not the working format: src/ was not made by ingest.py; run it")
    if len(gaps):
        print("    WARNING: %d gaps (dropped frames in the recording) at frame (time, ms): " % len(gaps)
              + ", ".join("%d (%.2fs, %.0f)" % (i, t[i], d[i]) for i in gaps[:20]))
if failed:
    sys.exit(1)
