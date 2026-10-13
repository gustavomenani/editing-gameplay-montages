"""Measurements behind ref_analyze.py: what a reference edit looks like, from its pixels and its sound.

Every function takes the numpy arrays that `decode()` makes (small gray and colour copies of every frame) and returns
plain numbers / dicts / lists; nothing here prints or writes files. All frame numbers are 0-based frame indexes of the
reference, t = frame / fps.

Layout of the analysis copies: G (n, h, w) uint8 gray, long side 320; C (n, ch, cw, 3) uint8 colour, long side 128.
`roi` = (x0, y0, x1, y1) in G pixels: the part of the canvas that holds the gameplay (the whole frame, or the sharp
window of a window-over-backdrop layout, or the picture inside black bars). Cut and motion measures use the roi only.
"""
import json
import math
import os
import re
import subprocess
import sys

import cv2
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):          # ff.py sits next to this file in a project, one folder up in the repo
    if _p not in sys.path:
        sys.path.insert(0, _p)
from ff import FF, FFPROBE  # noqa: E402

cv2.setNumThreads(1)                                 # the frame loops are small; threads only add overhead


# ------------------------------------------------------------------------------------------------ input
def probe(path):
    """-> dict(width, height, fps, duration, frames, has_audio, audio_duration). width / height are what a player shows
    (a rotated phone clip is swapped)."""
    r = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", path], capture_output=True)
    if r.returncode != 0:
        raise SystemExit("ffprobe cannot read %s: %s" % (path, r.stderr.decode(errors="replace").strip()[-300:]))
    j = json.loads(r.stdout or b"{}")
    vs = [s for s in j.get("streams", []) if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic", 0) == 0]
    if not vs:
        raise SystemExit("%s has no video stream" % path)
    v = vs[0]
    a = [s for s in j.get("streams", []) if s.get("codec_type") == "audio"]
    W, H = int(v["width"]), int(v["height"])
    rot = 0
    try:
        rot = int(float(v.get("tags", {}).get("rotate", 0)))
    except ValueError:
        pass
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(round(float(sd["rotation"])))
    if abs(rot) % 180 == 90:
        W, H = H, W

    def frac(s):
        try:
            p, q = s.split("/")
            return float(p) / float(q) if float(q) else 0.0
        except (ValueError, AttributeError):
            return 0.0
    fps = frac(v.get("avg_frame_rate", "")) or frac(v.get("r_frame_rate", "")) or 30.0
    dur = float(v.get("duration") or j.get("format", {}).get("duration") or 0)
    nb = int(v["nb_frames"]) if str(v.get("nb_frames", "")).isdigit() else int(round(dur * fps))
    return dict(width=W, height=H, fps=fps, duration=dur, frames=nb, has_audio=bool(a),
                audio_duration=float(a[0].get("duration", 0) or 0) if a else 0.0)


def decode(path, info, max_frames):
    """Decode (at most max_frames frames) to small copies. -> G (n,h,w) uint8, C (n,ch,cw,3) uint8, native size (W, H)."""
    W, H = info["width"], info["height"]
    if W >= H:
        aw, ah = 320, int(round(320 * H / W / 2)) * 2
        cw, ch = 128, max(2, int(round(128 * H / W)))
    else:
        ah, aw = 320, int(round(320 * W / H / 2)) * 2
        ch, cw = 128, max(2, int(round(128 * W / H)))
    cmd = [FF, "-v", "error", "-i", path, "-an", "-frames:v", str(max_frames), "-vf", "scale=%d:%d:flags=area,format=rgb24" % (aw, ah),
           "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    G, C, size = [], [], aw * ah * 3
    while True:
        b = p.stdout.read(size)
        if len(b) < size:
            break
        f = np.frombuffer(b, np.uint8).reshape(ah, aw, 3)
        G.append(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY))
        C.append(cv2.resize(f, (cw, ch), interpolation=cv2.INTER_AREA))
    p.stdout.close()
    err = p.stderr.read().decode(errors="replace").strip()
    p.wait()
    if len(G) < 30:
        raise SystemExit("decoded only %d frames from %s (%s)" % (len(G), path, err[-300:] or "too short to analyse"))
    return np.array(G), np.array(C), (W, H)


def sample_native(path, info, count, skip=0.0):
    """About `count` frames spread evenly over the video at NATIVE size: list of (time, rgb uint8 array)."""
    dur = max(info["duration"], 1.0)
    W, H = info["width"], info["height"]
    step = max(dur / count, 0.5)
    cmd = [FF, "-v", "error", "-i", path, "-an", "-vf", "fps=1/%g,format=rgb24" % step, "-frames:v", str(count), "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, size = [], W * H * 3
    while True:
        b = p.stdout.read(size)
        if len(b) < size:
            break
        out.append((step * (len(out) + 0.5), np.frombuffer(b, np.uint8).reshape(H, W, 3)))
    p.stdout.close()
    p.stderr.read()
    p.wait()
    return out


# ------------------------------------------------------------------------------------------------ layout
def _longest_run(on):
    best, s = (0, 0, 0), None
    for i, v in enumerate(list(on) + [False]):
        if v and s is None:
            s = i
        if not v and s is not None:
            if i - s > best[0]:
                best = (i - s, s, i)
            s = None
    return best[1], best[2]


def detect_layout(G, info):
    """Orientation and layout: 'full' (the gameplay fills the canvas), 'window' (a sharp window over a blurred / dimmed
    backdrop) or 'letterbox' (black bars). -> dict with kind, orientation, bars, window rect in fractions, roi in G pixels."""
    n, h, w = G.shape
    idx = np.linspace(0, n - 1, min(n, 150)).astype(int)
    M = np.zeros((h, w), np.float32)
    mean = np.zeros((h, w), np.float32)
    for i in idx:
        g = G[i].astype(np.float32)
        M += np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
        mean += g
    M /= len(idx)
    mean /= len(idx)
    rows_g, cols_g = M.mean(1), M.mean(0)
    rows_l, cols_l = mean.mean(1), mean.mean(0)
    asp = info["width"] / info["height"]
    orient = "horizontal" if asp > 1.15 else ("vertical" if asp < 0.87 else "square")

    def bars(p_l, p_g, n_):
        a = 0
        while a < n_ // 3 and p_l[a] < 14 and p_g[a] < 4:
            a += 1
        b = 0
        while b < n_ // 3 and p_l[n_ - 1 - b] < 14 and p_g[n_ - 1 - b] < 4:
            b += 1
        return a, b
    top, bottom = bars(rows_l, rows_g, h)
    left, right = bars(cols_l, cols_g, w)
    y0, y1, x0, x1 = top, h - bottom, left, w - right
    res = dict(kind="full", orientation=orient, width=info["width"], height=info["height"], aspect=round(asp, 3),
               bars=dict(top=round(top / h, 3), bottom=round(bottom / h, 3), left=round(left / w, 3), right=round(right / w, 3)))
    if top + bottom + left + right >= 0.04 * (h + w) / 2 * 0.5 and (top + bottom >= 0.06 * h or left + right >= 0.06 * w):
        res["kind"] = "letterbox"

    def window(profile, lo, hi):
        """Longest run with energy above 40 % of the 90th percentile, accepted when the outside is much softer and both margins exist."""
        p = profile[lo:hi]
        if len(p) < 20:
            return None
        edge = max(2, len(p) // 60)
        q = p.copy()
        q[:edge] = q[edge]
        q[-edge:] = q[-edge - 1]
        hi90 = np.percentile(q, 90)
        a, b = _longest_run(q > 0.4 * hi90)
        if b - a >= 0.88 * len(q) or a < 0.04 * len(q) or len(q) - b < 0.04 * len(q):
            return None
        inside = q[a:b].mean()
        outside = np.concatenate([q[:a], q[b:]]).mean()
        if outside > 0.45 * inside:
            return None
        return (lo + a, lo + b, float(outside / inside))
    wr = window(rows_g, y0, y1)
    wc = window(M[wr[0]:wr[1]].mean(0) if wr else cols_g, x0, x1)
    if wr or wc:
        wy0, wy1 = (wr[0], wr[1]) if wr else (y0, y1)
        wx0, wx1 = (wc[0], wc[1]) if wc else (x0, x1)
        res["kind"] = "window"
        res["window"] = dict(x0=round(wx0 / w, 3), x1=round(wx1 / w, 3), y0=round(wy0 / h, 3), y1=round(wy1 / h, 3),
                             width_share=round((wx1 - wx0) / w, 3), height_share=round((wy1 - wy0) / h, 3),
                             aspect=round(((wx1 - wx0) * info["width"] / w) / ((wy1 - wy0) * info["height"] / h), 3),
                             backdrop_soft=round(float(wr[2] if wr else wc[2]), 3))
        y0, y1, x0, x1 = wy0, wy1, wx0, wx1
        # the backdrop is also dimmed: mean luma outside against inside
        mask = np.ones((h, w), bool)
        mask[wy0:wy1, wx0:wx1] = False
        res["window"]["backdrop_luma_ratio"] = round(float(mean[mask].mean() / (mean[~mask].mean() + 1e-6)), 3)
    res["roi"] = (int(x0), int(y0), int(x1), int(y1))
    return res


# ------------------------------------------------------------------------------------------------ beat grid
def _run_script(args, timeout=180):
    r = subprocess.run([sys.executable] + args, capture_output=True, timeout=timeout, cwd=_HERE if os.path.exists(os.path.join(_HERE, args[0])) else os.path.dirname(_HERE))
    return r.stdout.decode(errors="replace"), r.stderr.decode(errors="replace")


def _script(name):
    for d in (_HERE, os.path.dirname(_HERE)):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    raise SystemExit("%s not found next to ref_analyze.py (copy scripts/ and scripts/refstyle/ into the project first)" % name)


def beat_grid(audio_src, t0=0.0, t1=None):
    """The tempo and the beat grid of the sound of `audio_src` with music_tempo.py + music_grid.py (the project's own tools).
    -> dict(bpm, beat0, members=[(bpm, strength, between share)], chosen, weak, text) or dict(error=...)."""
    try:
        out, err = _run_script([_script("music_tempo.py"), audio_src])
    except subprocess.TimeoutExpired:
        return dict(error="music_tempo.py timed out")
    m = re.search(r"best fit: ([\d.]+) bpm, first beat at ([\d.]+) s", out)
    if not m:
        return dict(error=(err.strip().splitlines() or out.strip().splitlines() or ["music_tempo.py found no tempo"])[-1])
    bpm, first = float(m.group(1)), float(m.group(2))
    members = [(float(a), float(b), float(c) / 100) for a, b, c in re.findall(r"^\s+([\d.]+)\s+([\d.]+)\s+(\d+)%", out, re.M)]
    fs = re.search(r"fit strength: ([\d.]+)x", out)
    weak = bool(fs and float(fs.group(1)) < 2.5)
    dur = float(re.search(r"track ([\d.]+) s", out).group(1))
    t1 = min(t1 or dur, dur)
    gout, gerr = _run_script([_script("music_grid.py"), "%.3f" % bpm, "%.4f" % first, "0", "%.2f" % t1, audio_src])
    mb = re.search(r"=> BPM = ([\d.]+)\s+BEAT0 = (-?[\d.]+)", gout)
    mb0 = re.search(r"=> BEAT0 = (-?[\d.]+)", gout)
    note = []
    if mb:
        bpm, first = float(mb.group(1)), float(mb.group(2))
        note.append("music_grid.py corrected the tempo to %.3f" % bpm)
    elif mb0:
        first = float(mb0.group(1))
    else:
        note.append("music_grid.py could not refine the grid (%s): the provisional values are used" % ((gerr.strip().splitlines() or gout.strip().splitlines() or ["no output"])[-1][:160]))
    med = re.search(r"median ([+-][\d.]+) ms, spread \(std\) ([\d.]+) ms", gout)
    shift = re.search(r"WARNING|warning:[^\n]*", gout)
    if shift:
        note.append(shift.group(0)[:200])
    if weak:
        note.append("fit strength below 2.5x: no clear drum pattern, do not trust the tempo")
    period = 60.0 / bpm
    first = first % period
    return dict(bpm=round(bpm, 3), beat0=round(first, 4), members=members, weak=weak, notes=note,
                grid_spread_ms=float(med.group(2)) if med else None, track_seconds=dur)


def audio_pulses(src, bpm, beat0, step=0.5):
    """How hard the track hits on every `step` beat of the grid: kick (low), snare / clap (mid), hat (high), each 0..1.
    Same measure as music_pulses.py. -> (times, low, mid, high) arrays."""
    SR = 44100
    raw = subprocess.run([FF, "-v", "error", "-i", src, "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
    m = np.frombuffer(raw, np.float32)
    if len(m) < SR:
        return None
    X = np.fft.rfft(m)
    f = np.fft.rfftfreq(len(m), 1 / SR)
    low = np.fft.irfft(X / np.sqrt(1 + (f / 140.0) ** 8), n=len(m))
    g = (f / 2500.0) ** 4
    high = np.fft.irfft(X * (g / np.sqrt(1 + g * g)), n=len(m))
    g = (f / 900.0) ** 4
    mid = np.fft.irfft(X * (g / np.sqrt(1 + g * g)) / np.sqrt(1 + (f / 3500.0) ** 8), n=len(m))

    def env(y, ms):
        w = int(SR * ms / 1000)
        return np.sqrt(np.convolve(y * y, np.ones(w) / w, mode="same"))
    el, em, eh = env(low, 12), env(mid, 5), env(high, 4)

    def hit(e, t, pre_ms, post_ms):
        c = int(round(t * SR))
        lo, hi = c - int(pre_ms / 1000 * SR), c - int(0.006 * SR)
        a_lo, a_hi = c + int(0.004 * SR), c + int(post_ms / 1000 * SR)
        if lo < 0 or a_hi > len(e):
            return 0.0, 0.0
        return float(e[a_lo:a_hi].max()), float(e[a_lo:a_hi].max() / (e[lo:hi].mean() + 1e-4))
    per = 60.0 / bpm
    ts = np.arange(beat0 % per, len(m) / SR - 0.1, per * step)
    rl, rm, rh = np.percentile(el, 99), np.percentile(em, 99), np.percentile(eh, 99)
    out = np.zeros((len(ts), 3))
    for i, t in enumerate(ts):
        al, ql = hit(el, t, 60, 45)
        am, qm = hit(em, t, 40, 25)
        ah, qh = hit(eh, t, 40, 18)
        out[i] = (min(1.0, al / rl) * min(1.0, max(0.0, (ql - 1.3) / 2.0)),
                  min(1.0, am / rm) * min(1.0, max(0.0, (qm - 1.5) / 3.0)),
                  min(1.0, ah / rh) * min(1.0, max(0.0, (qh - 1.5) / 3.0)))
    return ts, out[:, 0], out[:, 1], out[:, 2]


# ------------------------------------------------------------------------------------------------ cuts
def _roi_gray(G, roi, width):
    x0, y0, x1, y1 = roi
    h = max(8, int(round(width * (y1 - y0) / max(1, x1 - x0))))
    return np.array([cv2.resize(g[y0:y1, x0:x1], (width, h), interpolation=cv2.INTER_AREA) for g in G])


def _roi_thumb(C, roi, G_shape):
    n, ch, cw, _ = C.shape
    _, gh, gw = G_shape
    x0, y0, x1, y1 = roi
    a, b = int(round(y0 / gh * ch)), max(int(round(y1 / gh * ch)), int(round(y0 / gh * ch)) + 2)
    c, d = int(round(x0 / gw * cw)), max(int(round(x1 / gw * cw)), int(round(x0 / gw * cw)) + 2)
    tw = (16, 9) if (x1 - x0) >= (y1 - y0) else (9, 16)
    return np.array([cv2.resize(t[a:b, c:d], tw, interpolation=cv2.INTER_AREA) for t in C]).astype(np.float32)


def frame_pair_features(G, C, roi):
    """Per frame i (pair i-1, i): L = colour-layout distance on a 16x9 thumbnail (0..255), R = phase-correlation response of the gray
    frames (1 = same picture shifted, 0 = unrelated). A hard cut: L high and R low. Also returns the thumbnails."""
    S = _roi_gray(G, roi, 160).astype(np.float32)
    T = _roi_thumb(C, roi, G.shape)
    n = len(G)
    win = cv2.createHanningWindow((S.shape[2], S.shape[1]), cv2.CV_32F)
    L = np.zeros(n)
    R = np.zeros(n)
    for i in range(1, n):
        L[i] = float(np.abs(T[i] - T[i - 1]).mean())
        R[i] = cv2.phaseCorrelate(S[i - 1].copy(), S[i].copy(), win)[1]      # the binding windows its inputs in place: copies
    return L, R, T, S


def detect_cuts(L, R, min_gap=4):
    """Hard cuts: a jump of the layout distance that is a local maximum and starts a run of unrelated frames.
    Validated on the worked example (57 of 57 cuts found, 5 extra). -> list of dict(frame, L, R, strength)."""
    n = len(L)
    cand = []
    for i in range(2, n - 2):
        if L[i] >= 20 and L[i] == L[i - 2:i + 3].max() and L[i] >= 1.3 * max(L[i - 1], L[i + 1], 4) and R[i] < 0.5:
            cand.append(i)
    keep = []
    for i in cand:
        if keep and i - keep[-1] < min_gap:
            if L[i] > L[keep[-1]]:
                keep[-1] = i
            continue
        keep.append(i)
    out = []
    for i in keep:
        s = min(1.0, (L[i] - 14.0) / 30.0) * 0.6 + min(1.0, max(0.0, (0.5 - R[i]) / 0.5)) * 0.4
        out.append(dict(frame=int(i), L=round(float(L[i]), 1), R=round(float(R[i]), 3), strength=round(float(s), 2)))
    return out


def find_blips(T, L):
    """One to three frames that differ from the picture before AND after it (the picture comes back): flashes, white or inverted
    impact frames. -> list of dict(frame, length, luma_jump)."""
    n = len(T)
    luma = T.mean((1, 2, 3))
    out, i = [], 3
    while i < n - 5:
        d = float(np.abs(T[i] - T[i - 1]).mean())
        if d > 15 and L[i] < 40:
            for j in (1, 2, 3):
                back = float(np.abs(T[i + j] - T[i - 1]).mean())
                if back < 0.45 * d and abs(luma[i] - luma[i - 1]) > 8:
                    out.append(dict(frame=int(i), length=j, luma_jump=round(float(luma[i] - luma[i - 1]), 1)))
                    i += j
                    break
        i += 1
    return out


# ------------------------------------------------------------------------------------------------ transitions
_POLAR = {}


def _polar(h, w):
    """cos / sin of the direction from the picture centre and a mask that leaves out the centre (where the direction is undefined)."""
    if (h, w) not in _POLAR:
        ys, xs = np.mgrid[0:h, 0:w]
        dx, dy = xs - w / 2 + 0.5, ys - h / 2 + 0.5
        rr = np.hypot(dx, dy)
        _POLAR[(h, w)] = (dx / (rr + 1e-6), dy / (rr + 1e-6), rr > 0.2 * rr.max())
    return _POLAR[(h, w)]


def _grad_feats(gray):
    """Gradient statistics of a gray frame (centre left out): the 75th and 90th percentile of |gradient| along x, y, radial and
    tangential (8 numbers: x75 x90 y75 y90 r75 r90 t75 t90), then the mean |gx|, |gy|, radial, tangential. Percentiles as well as means:
    the thin rays and streaks a blur-in carries add a few very strong edges and hide a weak loss in a mean."""
    g = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 0.7)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    ct, st, mask = _polar(*g.shape)
    gr, gt = gx * ct + gy * st, -gx * st + gy * ct
    out = []
    for a in (gx, gy, gr, gt):
        v = np.abs(a)[mask]
        out += [np.percentile(v, 75), np.percentile(v, 90)]
    out += [np.abs(gx)[mask].mean(), np.abs(gy)[mask].mean(), np.abs(gr)[mask].mean(), np.abs(gt)[mask].mean()]
    return np.array(out)


def classify_transitions(S, L, cuts, fps):
    """Kind of each cut from the frames around it (S = roi gray, 160 wide). The first 3 frames of a clip are compared with the same clip's
    own steady frames (6 to 14 frames later). A blur-in thins the strong gradients, and the DIRECTION tells the kind
    (xy = log of horizontal over vertical gradient, rt = log of radial over tangential, both against the steady state):
      whip   xy <= -0.35 (horizontal streaks) or >= 0.35 (vertical) on a strong blur (20 % loss of gradient energy), -0.2 on a weak one
      zoom   rt <= -0.2 with xy above -0.3 on a strong blur, -0.15 on a weak one (radial blur)
      roll   a strong blur with no direction (a rotated whip, a roll)
      flash  the mean luma jumps up by more than a quarter around the cut (white flash)
      dip    the picture goes dark at the cut (fade through black)
      hard   none of those: a plain cut
    Checked on the worked example (57 cuts built as 30 whips, 15 zoom bursts, 12 rolls): see the accuracy notes in ref_analyze.py. A weak blur-in
    (a short whip inside a clip that is itself fast) can read as hard: the share of hard cuts is an upper bound.
    Sets cut['kind'], 'kind_conf' (0..1), 'blur' (strongest energy loss of the first 4 frames), 'clip_frames', 'xy', 'rt'."""
    n = len(S)
    frames = [c["frame"] for c in cuts] + [n]
    GF = {}

    def gf(i):
        if i not in GF:
            GF[i] = _grad_feats(S[i])
        return GF[i]
    for k, c in enumerate(cuts):
        f = c["frame"]
        end = frames[k + 1]                           # first frame of the next clip (or the end of the video)
        ln = end - f
        c["clip_frames"] = int(ln)
        if ln < 5:
            c.update(kind="unknown", kind_conf=0.0, blur=0.0)
            continue
        steady = list(range(f + 6, min(end, f + 15))) if ln >= 9 else list(range(max(f + 3, end - 2), end))
        st = np.median(np.array([gf(i) for i in steady]), axis=0) + 1e-3
        post = [f + j for j in range(0, min(5, ln))]
        q = np.array([gf(i) / st for i in post])      # (k, 10): each frame's statistics over the steady ones
        loss = 1.0 - 0.5 * (q[:, 8] + q[:, 9])
        blur = float(max(0.0, loss[:4].max()))
        k_best = int(np.argmax(loss[:4]))
        luma = [float(S[i].mean()) for i in range(max(0, f - 3), min(n, f + 5))]
        pre = float(np.median([S[i].mean() for i in range(max(0, f - 6), max(1, f - 1))])) if f > 1 else luma[0]
        post_l = float(np.median([S[i].mean() for i in steady]))
        base = 0.5 * (pre + post_l) + 1e-3
        flash, dip = (max(luma) - base) / base, (base - min(luma)) / base
        c["blur"] = round(blur, 2)
        if flash > 0.28 and blur < 0.5 and max(luma) > 150:
            c.update(kind="flash", kind_conf=round(min(1.0, flash / 0.6), 2))
            continue
        if dip > 0.45:
            c.update(kind="dip", kind_conf=round(min(1.0, dip), 2))
            continue
        qq = np.log(q[:3].mean(0) + 1e-6)
        xy_p = float(0.5 * ((qq[0] - qq[2]) + (qq[1] - qq[3])))          # percentile measures: they see a weak blur-in
        rt_p = float(0.5 * ((qq[4] - qq[6]) + (qq[5] - qq[7])))
        xy_m, rt_m = float(qq[8] - qq[9]), float(qq[10] - qq[11])        # mean measures: clean when the blur is strong
        c.update(xy=round(xy_p, 2), rt=round(rt_p, 2), blur_frame=k_best)
        if blur >= 0.2:
            if xy_m <= -0.35:
                kind, conf, c["whip_axis"] = "whip", min(1.0, 0.5 + blur), "horizontal"
            elif xy_m >= 0.35:
                kind, conf, c["whip_axis"] = "whip", min(1.0, 0.5 + blur), "vertical"
            elif rt_m <= -0.2 and xy_m > -0.3:
                kind, conf = "zoom", min(1.0, 0.45 + blur)
            elif abs(rt_m) < 0.2 and abs(xy_m) < 0.35:
                kind, conf = "roll", min(0.8, 0.3 + blur)
            else:
                kind, conf = "blur", 0.3
        elif xy_p <= -0.2 and xy_p <= rt_p + 0.05:
            kind, conf, c["whip_axis"] = "whip", min(0.8, 0.35 + (-xy_p - 0.2) * 1.5), "horizontal"
        elif xy_p >= 0.4:
            kind, conf, c["whip_axis"] = "whip", min(0.8, 0.35 + (xy_p - 0.4) * 1.5), "vertical"
        elif rt_p <= -0.15 and xy_p > -0.25:
            kind, conf = "zoom", min(0.8, 0.35 + (-rt_p - 0.15) * 2)
        else:
            kind, conf = "hard", min(1.0, 0.6 + (0.2 - blur) * 2.0 - max(0.0, -xy_p - 0.1))
        c.update(kind=kind, kind_conf=round(float(max(conf, 0.1)), 2))
    return cuts


# ------------------------------------------------------------------------------------------------ motion
def motion_series(S, cuts, fps):
    """Per frame i (pair i-1, i): m = median optical-flow magnitude (px at 160 wide), D = mean |frame difference|,
    t = (tx, ty) global translation, s = zoom per frame, r = rotation per frame (rad), from a 4-parameter fit of the flow.
    Pairs that cross a cut are NaN."""
    n = len(S)
    h, w = S.shape[1:]
    m = np.full(n, np.nan)
    D = np.full(n, np.nan)
    tx = np.full(n, np.nan)
    ty = np.full(n, np.nan)
    sc = np.full(n, np.nan)
    ro = np.full(n, np.nan)
    cutset = {c["frame"] for c in cuts}
    ys, xs = np.mgrid[2:h - 2:4, 2:w - 2:4]
    X = (xs - w / 2.0).ravel()
    Y = (ys - h / 2.0).ravel()
    A = np.zeros((2 * len(X), 4))
    A[:len(X), 0], A[len(X):, 1] = 1, 1
    A[:len(X), 2], A[len(X):, 2] = X, Y
    A[:len(X), 3], A[len(X):, 3] = -Y, X
    for i in range(1, n):
        D[i] = float(np.abs(S[i].astype(np.float32) - S[i - 1]).mean())
        if i in cutset:
            continue
        fl = cv2.calcOpticalFlowFarneback(S[i - 1], S[i], None, 0.5, 3, 15, 3, 5, 1.2, 0)
        mag = np.hypot(fl[..., 0], fl[..., 1])
        m[i] = float(np.median(mag))
        b = np.concatenate([fl[2:h - 2:4, 2:w - 2:4, 0].ravel(), fl[2:h - 2:4, 2:w - 2:4, 1].ravel()])
        keep = np.ones(len(b), bool)
        p = np.zeros(4)
        for _ in range(2):
            p = np.linalg.lstsq(A[keep], b[keep], rcond=None)[0]
            res = np.abs(b - A @ p)
            thr = max(0.3, 2.5 * 1.4826 * np.median(res[keep]))
            keep = res < thr
            if keep.sum() < 0.3 * len(b):
                break
        tx[i], ty[i], sc[i], ro[i] = p
    return dict(m=m, D=D, tx=tx, ty=ty, s=sc, r=ro)


def speed_feel(mo, cuts, fps, exclude_from=None, black=None):
    """Slow motion and freezes. A clip's real-time speed is taken as the 85th percentile of its own motion after the blur frames;
    the typical speed is the median of those over the clips. Slow = motion below 35 % of typical for 5 frames or more."""
    m = mo["m"].copy()
    n = len(m)
    marks = [0] + [c["frame"] for c in cuts] + [n]
    peaks = []
    for a, b in zip(marks[:-1], marks[1:]):
        seg = m[a + 5:b]
        seg = seg[~np.isnan(seg)]
        if len(seg) >= 6:
            peaks.append(float(np.percentile(seg, 85)))
    out = dict(typical=None)
    if len(peaks) < 3:
        return dict(typical=None, slow_share=None, freeze_share=None, note="too few clips to judge speed")
    typical = float(np.median(peaks))
    ms = np.array([np.nanmedian(m[max(0, i - 1):i + 2]) if not np.all(np.isnan(m[max(0, i - 1):i + 2])) else np.nan for i in range(n)])
    D = mo["D"]
    valid = ~np.isnan(ms)
    if exclude_from is not None:                      # the ending fade: black frames repeat, they are no freeze
        valid[exclude_from:] = False
    if black is not None:
        valid &= ~black
    freeze = valid & (D < 0.5)
    slow = valid & (ms < 0.35 * typical) & ~freeze
    # runs of at least 5 frames
    run = np.zeros(n, bool)
    i = 0
    flags = slow | freeze
    while i < n:
        if flags[i]:
            j = i
            while j < n and flags[j]:
                j += 1
            if j - i >= 5:
                run[i:j] = True
            i = j
        else:
            i += 1
    slow_run = run & slow
    rate = None
    if slow_run.sum() >= 10:
        rate = float(np.median(ms[slow_run & (ms > 0.02 * typical)]) / typical) if np.any(slow_run & (ms > 0.02 * typical)) else None
    # dup runs: how many frames in a row repeat (a stutter or a 30 fps source)
    dup = valid & (D < 0.5)
    runs, i = [], 0
    while i < n:
        if dup[i]:
            j = i
            while j < n and dup[j]:
                j += 1
            runs.append(j - i)
            i = j
        else:
            i += 1
    alt = 0
    if n > 40:
        v = (D[1:] < 0.5).astype(int)
        # every second frame a repeat -> a 30 fps picture inside a 60 fps file
        even, odd = v[0::2].mean(), v[1::2].mean()
        alt = float(max(even, odd) - min(even, odd))
    out.update(typical=round(typical, 3), slow_share=round(float(run.sum() / valid.sum()), 3), slow_only_share=round(float(slow_run.sum() / valid.sum()), 3),
               freeze_share=round(float(dup.sum() / valid.sum()), 3), freeze_runs=int(len(runs)), freeze_longest=int(max(runs)) if runs else 0,
               rate=round(rate, 3) if rate else None, alternating_repeat=round(alt, 2), clips_used=len(peaks))
    return out


def shake_zoom(mo, cuts, width=160.0):
    """Camera shake and zoom activity: RMS of the high-passed translation (% of the roi width) and of the zoom rate (% per frame),
    inside the 6 frames after a cut and elsewhere."""
    tx, ty, s = mo["tx"], mo["ty"], mo["s"]
    n = len(tx)

    def hp(v):
        out = np.full(n, np.nan)
        for i in range(n):
            a, b = max(0, i - 4), min(n, i + 5)
            w = v[a:b]
            if np.isnan(v[i]) or np.all(np.isnan(w)):
                continue
            out[i] = v[i] - np.nanmean(w)
        return out
    th = np.hypot(hp(tx), hp(ty))
    zh = np.abs(hp(s))
    near = np.zeros(n, bool)
    for c in cuts:
        near[c["frame"]:c["frame"] + 10] = True
    first = np.zeros(n, bool)
    for c in cuts:
        first[max(0, c["frame"] - 2):c["frame"]] = True        # the lean into a cut

    def rms(v, mask):
        x = v[mask & ~np.isnan(v)]
        return float(np.sqrt(np.mean(x * x))) if len(x) else None
    W = float(width)
    r = dict(shake_rms=rms(th, ~near), shake_rms_cuts=rms(th, near), zoom_rms=rms(zh, ~near), zoom_rms_cuts=rms(zh, near), zoom_lean=rms(zh, first))
    r["shake_pct_width"] = None if r["shake_rms"] is None else round(100 * r["shake_rms"] / W, 3)
    r["shake_pct_width_cuts"] = None if r["shake_rms_cuts"] is None else round(100 * r["shake_rms_cuts"] / W, 3)
    r["zoom_pct_frame"] = None if r["zoom_rms"] is None else round(100 * r["zoom_rms"], 3)
    r["zoom_pct_frame_cuts"] = None if r["zoom_rms_cuts"] is None else round(100 * r["zoom_rms_cuts"], 3)
    r["zoom_pct_frame_lean"] = None if r["zoom_lean"] is None else round(100 * r["zoom_lean"], 3)
    return r


# ------------------------------------------------------------------------------------------------ text
def detect_text(G, fps, step=2):
    """Big words over the picture, without OCR. A frame has text when a row of at least two letter-sized blobs of equal height sits
    on one baseline (MSER regions), and the same row is there on the next sample. Validated on the worked example (79 words, see-through
    letters): 84 % of the words found (66 of 79), 91 % of the finds (95 of 104) inside a word's time. Scenery (vents, stairs, signs) gives
    a few false rows, so a handful of finds is not text; the see-through letters of a busy frame are missed: the counts are LOWER BOUNDS.
    -> dict(share, words, cap_height, cy, cx, runs=[(frame_a, frame_b)])"""
    n, h, w = G.shape
    short = min(h, w)
    ms = cv2.MSER_create(delta=6, min_area=int(0.004 * h * w), max_area=int(0.08 * h * w), max_variation=0.45)
    lo, hi = 0.09 * short, 0.40 * short
    rows_by = []
    idx = list(range(0, n, step))
    for i in idx:
        _, bb = ms.detectRegions(G[i])
        bx = [(x, y, bw, bh) for (x, y, bw, bh) in bb if lo <= bh <= hi and 0.15 * bh <= bw <= 1.5 * bh and 0.18 * h < y + bh / 2 < 0.82 * h]
        best = None
        for (x, y, bw, bh) in bx:
            g = [b for b in bx if abs(b[3] - bh) <= 0.18 * bh and abs((b[1] + b[3] / 2) - (y + bh / 2)) <= 0.08 * bh]
            g2 = []
            for b in sorted(g, key=lambda b: b[0]):
                if all(min(b[0] + b[2], c[0] + c[2]) - max(b[0], c[0]) < 0.5 * min(b[2], c[2]) for c in g2):
                    g2.append(b)
            if len(g2) >= 2 and (best is None or len(g2) > best[0]):
                best = (len(g2), float(np.mean([b[1] + b[3] / 2 for b in g2])), float(np.mean([b[3] for b in g2])),
                        min(b[0] for b in g2), max(b[0] + b[2] for b in g2))
        rows_by.append(best)
    # chains of samples with the same row geometry
    chains, cur = [], None
    for j, r in enumerate(rows_by):
        if r is None:
            if cur and j - cur["last"] > 2:
                chains.append(cur)
                cur = None
            continue
        if cur and j - cur["last"] <= 2 and abs(r[1] - cur["rows"][-1][1]) < 0.04 * h and abs(r[2] - cur["rows"][-1][2]) < 0.2 * cur["rows"][-1][2] \
                and min(r[4], cur["rows"][-1][4]) - max(r[3], cur["rows"][-1][3]) > 0.4 * min(r[4] - r[3], cur["rows"][-1][4] - cur["rows"][-1][3]):
            cur["js"].append(j)
            cur["last"] = j
            cur["rows"].append(r)
        else:
            if cur:
                chains.append(cur)
            cur = dict(js=[j], last=j, rows=[r])
    if cur:
        chains.append(cur)
    chains = [c for c in chains if len(c["js"]) >= 2]
    covered = np.zeros(n, bool)
    runs = []
    for c in chains:
        a, b = idx[c["js"][0]], min(n, idx[c["js"][-1]] + step)
        covered[a:b] = True
        runs.append((int(a), int(b)))
    allrows = [r for c in chains for r in c["rows"]]
    res = dict(share=round(float(covered.mean()), 3), words=len(chains), runs=runs)
    if allrows:
        res.update(cap_height=round(float(np.median([r[2] for r in allrows])) / h, 3), cy=round(float(np.median([r[1] for r in allrows])) / h, 3),
                   cx=round(float(np.median([(r[3] + r[4]) / 2 for r in allrows])) / w, 3), width=round(float(np.median([(r[4] - r[3]) for r in allrows])) / w, 3),
                   letters=round(float(np.mean([r[0] for r in allrows])), 1))
    res["covered"] = covered
    return res


# ------------------------------------------------------------------------------------------------ colour
def colour_stats(G, C, roi, layout):
    """Saturation, contrast, warmth, vignette, and the colour of shadows against lights, over the gameplay area."""
    n, ch, cw, _ = C.shape
    _, gh, gw = G.shape
    x0, y0, x1, y1 = roi
    a, b, c, d = int(y0 / gh * ch), int(np.ceil(y1 / gh * ch)), int(x0 / gw * cw), int(np.ceil(x1 / gw * cw))
    idx = np.linspace(0, n - 1, min(n, 240)).astype(int)
    sat, lmean, spread, warm, sh_rb, hi_rb, lstd = [], [], [], [], [], [], []
    for i in idx:
        t = C[i, a:b, c:d]
        if t.mean() < 8:                                  # a black frame (the end of a fade) tells nothing about the colour
            continue
        hsv = cv2.cvtColor(t, cv2.COLOR_RGB2HSV)
        f = t.astype(np.float32)
        luma = 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]
        sat.append(float(hsv[..., 1].mean()) / 255.0)
        lmean.append(float(luma.mean()))
        p5, p95 = np.percentile(luma, [5, 95])
        spread.append(float(p95 - p5))
        lstd.append(float(luma.std()))
        warm.append(float(np.log2((f[..., 0].mean() + 1) / (f[..., 2].mean() + 1))))
        dark, light = luma <= np.percentile(luma, 25), luma >= np.percentile(luma, 75)
        if dark.any() and light.any() and luma.mean() > 8:
            sh_rb.append(float(np.log2((f[..., 0][dark].mean() + 1) / (f[..., 2][dark].mean() + 1))))
            hi_rb.append(float(np.log2((f[..., 0][light].mean() + 1) / (f[..., 2][light].mean() + 1))))
    # vignette on the gray mean image: corners against the middle (a ratio below 1 = darker corners)
    mean = np.zeros((gh, gw), np.float32)
    for i in np.linspace(0, n - 1, min(n, 150)).astype(int):
        mean += G[i]
    mean /= min(n, 150)
    mean = mean[y0:y1, x0:x1]
    hh, ww = mean.shape
    pw, ph = max(2, int(ww * 0.12)), max(2, int(hh * 0.12))
    corners = np.mean([mean[:ph, :pw].mean(), mean[:ph, -pw:].mean(), mean[-ph:, :pw].mean(), mean[-ph:, -pw:].mean()])
    centre = mean[int(hh * 0.3):int(hh * 0.7), int(ww * 0.3):int(ww * 0.7)].mean()
    edges = np.mean([mean[int(hh * 0.4):int(hh * 0.6), :pw].mean(), mean[int(hh * 0.4):int(hh * 0.6), -pw:].mean()])
    return dict(saturation=round(float(np.mean(sat)), 4), luma_mean=round(float(np.mean(lmean)), 1), contrast_spread=round(float(np.mean(spread)), 1),
                luma_std=round(float(np.mean(lstd)), 1), warmth=round(float(np.mean(warm)), 4), shadow_warmth=round(float(np.mean(sh_rb)) if sh_rb else 0.0, 4),
                light_warmth=round(float(np.mean(hi_rb)) if hi_rb else 0.0, 4), vignette_corner_ratio=round(float(corners / (centre + 1e-6)), 4),
                vignette_edge_ratio=round(float(edges / (centre + 1e-6)), 4))


def _noise_sigma(gray):
    """Immerkaer noise estimate on the flattest quarter of the 32x32 blocks (gray levels)."""
    g = gray.astype(np.float32)
    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    r = np.abs(cv2.filter2D(g, -1, k))
    h, w = g.shape
    bs = 32
    r = r[:h // bs * bs, :w // bs * bs].reshape(h // bs, bs, w // bs, bs).mean((1, 3))
    gx = np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0))[:h // bs * bs, :w // bs * bs].reshape(h // bs, bs, w // bs, bs).mean((1, 3))
    flat = gx.ravel() <= np.percentile(gx.ravel(), 25)
    return float(math.sqrt(math.pi / 2) / 6.0 * np.median(r.ravel()[flat]))


def native_stats(samples, W, H, roi_frac):
    """On native-size frames: noise (grain) and the red-blue colour fringe at the corners of the gameplay area.
    fringe = radial shift of the red channel against the blue one, in thousandths of the half diagonal (0.4 = a visible fringe)."""
    sig, fr = [], []
    x0, y0, x1, y1 = [int(round(v)) for v in (roi_frac[0] * W, roi_frac[1] * H, roi_frac[2] * W, roi_frac[3] * H)]
    P = 192
    win = cv2.createHanningWindow((P, P), cv2.CV_32F)
    half = math.hypot(x1 - x0, y1 - y0) / 2
    for _, img in samples:
        crop = img[y0:y1, x0:x1]
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        sig.append(_noise_sigma(gray))
        ch, cw = crop.shape[:2]
        for (py, px, oy, ox) in ((0, 0, -1, -1), (0, cw - P, -1, 1), (ch - P, 0, 1, -1), (ch - P, cw - P, 1, 1)):
            if py < 0 or px < 0:
                continue
            p = crop[py:py + P, px:px + P].astype(np.float32)
            if p[..., 0].std() < 8:
                continue
            (dx, dy), resp = cv2.phaseCorrelate(np.ascontiguousarray(p[..., 0]), np.ascontiguousarray(p[..., 2]), win)
            if resp < 0.15:
                continue
            nrm = math.hypot(ox, oy)
            fr.append((dx * ox + dy * oy) / nrm)
    return dict(noise_sigma=round(float(np.median(sig)), 3) if sig else None,
                fringe=round(float(np.mean(fr)) / half * 1000, 3) if fr else None, fringe_patches=len(fr))


# ------------------------------------------------------------------------------------------------ ending
def ending_stats(G, fps):
    """The last seconds: luma percentiles per frame -> kind of ending.
    'luma fade' (dark areas go black before the highlights), 'fade to black', 'fade to white', 'cut' (nothing)."""
    n = len(G)
    k = int(min(n // 3, 4 * fps))
    seg = G[n - k:].reshape(k, -1)
    p10 = np.percentile(seg, 10, axis=1)
    p50 = np.percentile(seg, 50, axis=1)
    p90 = np.percentile(seg, 90, axis=1)
    mean = seg.mean(1)
    base = float(np.median(mean[:max(3, k // 4)]))
    base90 = float(np.median(p90[:max(3, k // 4)]))
    base10 = float(np.median(p10[:max(3, k // 4)]))
    last = float(mean[-3:].mean())

    def reach(v, frac, ref):
        idx = np.where(v < frac * ref)[0]
        return int(idx[0]) if len(idx) else k
    kind, start, dur, lag = "cut", None, 0.0, None
    if last < 0.2 * base or float(p90[-3:].mean()) < 0.25 * base90:
        a = k - 1                                      # first frame from which the mean luma stays under 92 % of the base
        for i in range(len(mean)):
            if np.all(mean[i:] < 0.92 * base):
                a = i
                break
        start = float((n - k + a) / fps)
        dur = float(k - a) / fps
        # luma fade: P10 reaches ~black clearly before P90 does
        lag = (reach(p90, 0.25, base90) - reach(p10, 0.25, max(base10, 10))) / fps
        half = np.where(mean < 0.5 * base)[0]               # at half the mean luma: a luma fade keeps its highlights while the midtones are gone
        base50 = float(np.median(p50[:max(3, k // 4)])) + 1e-3
        spread = float(p90[half[0]] / (base90 + 1e-3) - p50[half[0]] / base50) if len(half) else 0.0
        kind = "luma fade" if spread >= 0.2 else "fade to black"
    elif last > 1.6 * base and last > 200:
        kind = "fade to white"
        start = float((n - k) / fps)
    return dict(kind=kind, start=None if start is None else round(start, 2), seconds=round(dur, 2), final_luma=round(last, 1),
                base_luma=round(base, 1), p10_to_p90_lag=None if lag is None else round(float(lag), 2),
                highlight_keep=None if lag is None else round(spread, 2))
