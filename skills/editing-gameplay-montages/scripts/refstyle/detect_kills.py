"""Scan gameplay clips for the local player's kills via the kill feed (top-right).

A "my kill" row is: lime accent on the far left, teal body (killer name "Eu"), red victim
section on the right. Rows are tracked by the x where the red section starts, so background
flicker does not create duplicate events.

usage: detect_kills.py <src_dir> <out_dir> [name-filter ...]

Every frame of a file must be decoded (frame i = packet i of the file): a decode that comes up short (GPU decoder dying, damaged or
truncated recording) is retried in software and, if still short, the file is reported as FAILED, no json is written for it, and the
script exits 1 after the other files are done. A cached json from such a short decode is not trusted: that file is scanned again.
"""
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import tempfile

import cv2
import numpy as np
from ff import FF, FFPROBE

X0, Y0, W, H = 1300, 84, 616, 300          # kill-feed search region (1920x1080 frame)
SKIP_PREFIX = ()    # set per project: file-name prefixes to leave out (the reference video, finished edits), e.g. ("reference", "edit_")
TRIM_RE = re.compile(r"-\d\d\.\d\d\.\d\d\.\d\d\d-\d\d\.\d\d\.\d\d\.\d\d\d")


def probe_pts(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "packet=pts_time", "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout
    return sorted(float(x) for x in out.split() if x.strip() not in ("", "N/A"))


def row_bands(img):
    """Return my-kill bands [(y_top, y_bot, lime_x, red_min_x)] in full-frame coordinates."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    lime = (h >= 22) & (h <= 45) & (s >= 90) & (v >= 180)
    teal = (h >= 70) & (h <= 100) & (s >= 60) & (v >= 130)
    red = ((h <= 7) | (h >= 171)) & (s >= 120) & (v >= 180)
    tc, rc = teal.sum(1), red.sum(1)
    # the white name text covers much of the red section on the middle lines, so keep rc low
    line_ok = (tc >= 30) & (rc >= 20)
    bands = []
    y = 0
    while y < H:
        if not line_ok[y]:
            y += 1
            continue
        y1 = y
        while y1 < H and line_ok[y1]:
            y1 += 1
        hgt = y1 - y
        # one row is ~34 px tall; taller runs are several rows glued together by the background
        k = max(1, int(round(hgt / 37.5)))
        if hgt >= 24 and hgt / k <= 42:
            for j in range(k):
                ya = y + int(round(j * hgt / k))
                yb = y + int(round((j + 1) * hgt / k))
                hh = yb - ya
                rcols = red[ya:yb].sum(0) >= hh * 0.4
                rx = np.flatnonzero(rcols)
                if len(rx) < 25:
                    continue
                # red section = the right-most long run of red columns
                red_max = int(rx.max())
                if red_max + X0 < 1800:
                    continue
                xr = red_max
                gap = 0
                red_min = red_max
                while xr >= 0 and gap <= 70:      # allow white text / portrait gaps
                    if rcols[xr]:
                        red_min = xr
                        gap = 0
                    else:
                        gap += 1
                    xr -= 1
                lo = max(0, red_min - 330)
                hi = max(0, red_min - 90)
                tcols = teal[ya:yb, lo:red_min].sum(0) >= hh * 0.4
                if tcols.sum() < 40:
                    continue
                lcols = lime[ya:yb, lo:hi].sum(0) >= hh * 0.4
                lx = np.flatnonzero(lcols)
                if len(lx) < 4:
                    continue
                # lime wedge must be a compact stripe, left of the teal body
                best = None
                run_start = lx[0]
                prev = lx[0]
                runs = []
                for xq in lx[1:]:
                    if xq - prev > 3:
                        runs.append((run_start, prev))
                        run_start = xq
                    prev = xq
                runs.append((run_start, prev))
                for a, b in runs:
                    wdt = b - a + 1
                    if 4 <= wdt <= 45:
                        teal_right = tcols[min(b + 1, len(tcols) - 1):].sum()
                        if teal_right >= 35 and (best is None or a > best[0]):
                            best = (a, b)
                if best is None:
                    continue
                bands.append((int(ya + Y0), int(yb + Y0), int(lo + best[0] + X0), int(red_min + X0)))
        y = y1
    return bands


MAX_GAP = 2        # frames the decoder may differ from the file's packet count (a cut-off last GOP); anything more is a failed decode


def decode(path, hw):
    """Every frame of the file, scanned for kill-feed bands -> (frames, last ffmpeg messages). hw: GPU decode (-hwaccel auto)."""
    cmd = [FF, "-v", "error"] + (["-hwaccel", "auto"] if hw else []) + ["-i", path, "-map", "0:v:0",
           "-vf", f"crop={W}:{H}:{X0}:{Y0}", "-fps_mode", "passthrough",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    frames = []                 # per frame: list of bands
    fsz = W * H * 3
    with tempfile.TemporaryFile() as err:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, bufsize=W * H * 3 * 8)
        while True:
            buf = p.stdout.read(fsz)
            if len(buf) < fsz:
                break
            img = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
            frames.append(row_bands(img))
        p.wait()
        err.seek(0)
        msg = err.read().decode("utf-8", "replace").strip().splitlines()[-3:]
    return frames, " | ".join(msg)


def scan(path, out_dir):
    name = os.path.basename(path)
    out_json = os.path.join(out_dir, os.path.splitext(name)[0] + ".json")
    pts = probe_pts(path)
    if os.path.exists(out_json):
        try:
            old = json.load(open(out_json))
            n_old, n_pts_old = old["n_frames"], old["n_pts"]
        except (ValueError, KeyError, OSError):
            n_old, n_pts_old = None, None
        if n_old is not None and abs(n_pts_old - n_old) <= MAX_GAP and abs(len(pts) - n_old) <= MAX_GAP:
            return name, "cached"
        print(f"{name}: the cached {out_json} is bad (decoded {n_old} frames, the file has {len(pts)}): scanning it again", flush=True)
    if not pts:
        raise RuntimeError(f"{name}: ffprobe lists no video packets: the file is unreadable or not a video")
    # The decoder must deliver EVERY frame: frame i is pts[i]. A short decode (GPU decoder dying, damaged file) used to be hidden by an
    # offset guess and the scan reported "no kills" (one 8110-frame file decoded 10 frames): try again in software, then stop.
    frames, msg = decode(path, True)
    if abs(len(pts) - len(frames)) > MAX_GAP:
        print(f"{name}: GPU decode gave {len(frames)} of {len(pts)} frames ({msg or 'no message'}): decoding again in software", flush=True)
        frames, msg = decode(path, False)
    n = len(frames)
    if abs(len(pts) - n) > MAX_GAP:
        raise RuntimeError(f"{name}: decoded {n} frames but the file has {len(pts)}: the file is damaged or truncated"
                           + (f" (ffmpeg: {msg})" if msg else "") + "; no kills were scanned for it (repair or re-export the recording)")
    times = [pts[min(i, len(pts) - 1)] for i in range(n)]

    # --- track rows by the x where the red (victim) section starts
    TOL = 6
    tracks = []                 # dicts: red_min, last_seen
    events = []
    for i in range(n):
        tracks = [t for t in tracks if i - t["last"] <= 60]
        used = set()
        for b in frames[i]:
            m = None
            for ti, t in enumerate(tracks):
                if ti not in used and abs(t["red"] - b[3]) <= TOL:
                    m = ti
                    break
            if m is not None:
                used.add(m)
                tracks[m]["last"] = i
                tracks[m]["red"] = 0.8 * tracks[m]["red"] + 0.2 * b[3]
                continue
            # new signature -> must persist in >= 6 of the next 10 frames
            hits = sum(1 for j in range(i + 1, min(n, i + 11))
                       if any(abs(bb[3] - b[3]) <= TOL for bb in frames[j]))
            if hits >= 6:
                tracks.append({"red": float(b[3]), "last": i})
                used.add(len(tracks) - 1)
                events.append({"frame": i, "t": round(times[i], 4), "y": b[0],
                               "lime_x": b[2], "red_min_x": b[3], "rows_now": len(frames[i])})
    counts = [len(f) for f in frames]
    with open(out_json, "w") as fh:
        json.dump({"file": name, "n_frames": n, "n_pts": len(pts), "duration": times[-1] if times else 0,
                   "events": events, "counts": counts, "times": [round(t, 4) for t in times]}, fh)
    return name, f"{n} frames, {len(events)} kills: " + " ".join(f"{e['t']:.2f}" for e in events)


def main():
    src_dir, out_dir = sys.argv[1], sys.argv[2]
    filters = [a.lower() for a in sys.argv[3:]]
    os.makedirs(out_dir, exist_ok=True)
    allf = sorted(f for f in os.listdir(src_dir) if f.lower().endswith(".mp4"))
    raw_names = {os.path.splitext(f)[0] for f in allf}
    todo = []
    for f in allf:
        base = os.path.splitext(f)[0]
        if f.upper().startswith(tuple(p.upper() for p in SKIP_PREFIX)):
            continue
        m = TRIM_RE.search(base)
        if m and base[:m.start()] in raw_names:
            continue            # trimmed duplicate of a raw clip we already scan
        if filters and not any(k in f.lower() for k in filters):
            continue
        todo.append(os.path.join(src_dir, f))

    def safe(p_):
        try:
            return scan(p_, out_dir) + (True,)
        except RuntimeError as e:                    # one bad file must not hide the others: report it, finish the rest, exit 1
            return os.path.basename(p_), "FAILED: " + str(e), False
    failed = []
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        for name, msg, ok in ex.map(safe, todo):
            print(f"{name}: {msg}", flush=True)
            if not ok:
                failed.append(name)
    if failed:
        sys.exit(f"detect_kills.py: {len(failed)} file(s) NOT scanned (decode failed or came up short): {', '.join(failed)}. "
                 "Their kills are missing from the detections: do not use this scan as complete.")


if __name__ == "__main__":
    main()
