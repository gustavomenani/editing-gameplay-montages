"""Find recordings that contain the same footage: a full DVR and its trims, identical copies, overlapping trims.

usage: python dupes.py                  every video in src/  (clip names = file names without extension)
       python dupes.py c02 c07 c09      only these clips of src/
       python dupes.py --dir "D:/clips" every video file of a folder (names = file names)   -> dupes.json

Why: the same kill must never enter the montage twice. Folders often hold the full recording AND trims of it (cut by the
recorder, re-encoded: other bitrate, other key-frame phase) or the same file twice ("-seg1" copy); the kill detector then
lists the same kill once per file.

How (cheap, nothing is decoded in full):
  1. Every clip is read once with `-skip_frame nokey`: only the key frames (a picture every 0.5 to 2 s), 96x54 grey.
  2. For every pair, each key frame of the shorter clip B votes for the offset to its most similar key frame of the longer
     clip A (time in A minus time in B). Footage shared by both makes many votes agree; unrelated clips scatter.
  3. The best offset is checked on the pixels: B's key frames are compared with EVERY frame of A in a +-0.75 s window
     (a few frames of A decoded, 96x54 grey). A match must be much closer than the rest of the window (ratio) and tiny
     in absolute terms; at least 3 key frames of B must agree on the same exact offset (within 1 frame at 60 fps).
  Byte-identical files (same size, same hash of 3 chunks) are reported without decoding.
Result per pair: A (the longer clip, the one a kill is kept in), B, offset_s (time in A = time in B + offset_s), the part of B that
is inside A, kind = identical | trim | overlap. frame_map() turns a frame of B into the frame of A.

Rule used by kill_rank.py: a kill in B that lies inside the shared part is the same kill as the one in A at the mapped frame;
only A's entry is kept (A is the longer recording: it has the lead-in and the context). For identical copies the first name wins.
"""
import argparse, glob, hashlib, json, os, pickle, subprocess, sys, tempfile, time
import numpy as np
import cv2
from concurrent.futures import ThreadPoolExecutor
from ff import FF

VIDEO = (".mp4", ".mkv", ".mov", ".m4v", ".webm", ".avi")
W, H = 96, 54
WIN = 0.75          # seconds: refinement window around the voted offset
MAX_MAD = 6.0       # mean abs grey difference (0-255 on 96x54) that still counts as the same picture (re-encodes: 1 to 3)
RATIO = 0.6         # the best frame of the window must be this much closer than the median of the window
MIN_AGREE = 3       # key frames of B that must land on the same offset
AUDIO_Z = 8.0       # peak height (in standard deviations) of the sound cross-correlation that proposes an offset to verify()
SIG_MAX = 0.35      # largest signature difference (z-scored 24x14 grey) of a vote: identical pictures 0, re-encodes < 0.1, other scenes of the map > 0.6


def say(m):
    print(m, flush=True)


def keyframes(path):
    """-> (times (n,), frames (n, H, W) float32 grey) of the key frames, in presentation order."""
    with tempfile.TemporaryFile() as err:
        p = subprocess.run([FF, "-v", "info", "-skip_frame", "nokey", "-i", path, "-an", "-sn", "-vf",
                            f"scale={W}:{H}:flags=area,format=gray,showinfo", "-fps_mode", "passthrough", "-f", "rawvideo", "-"],
                           stdout=subprocess.PIPE, stderr=err)
        err.seek(0)
        log = err.read().decode("utf-8", "replace")
    ts = [float(l.split("pts_time:")[1].split()[0]) for l in log.splitlines() if "pts_time:" in l and "showinfo" in l]
    raw = np.frombuffer(p.stdout, np.uint8)
    n = min(len(ts), len(raw) // (W * H))
    return np.array(ts[:n]), raw[:n * W * H].reshape(n, H, W).astype(np.float32)


def window(path, t0, dur):
    """All frames in [t0, t0+dur] at 96x54 grey: (times, frames)."""
    t0 = max(0.0, t0)
    with tempfile.TemporaryFile() as err:
        p = subprocess.run([FF, "-v", "info", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", path, "-an", "-sn", "-copyts", "-vf",
                            f"scale={W}:{H}:flags=area,format=gray,showinfo", "-fps_mode", "passthrough", "-f", "rawvideo", "-"],
                           stdout=subprocess.PIPE, stderr=err)
        err.seek(0)
        log = err.read().decode("utf-8", "replace")
    ts = [float(l.split("pts_time:")[1].split()[0]) for l in log.splitlines() if "pts_time:" in l and "showinfo" in l]
    raw = np.frombuffer(p.stdout, np.uint8)
    n = min(len(ts), len(raw) // (W * H))
    ts = np.array(ts[:n])
    fr = raw[:n * W * H].reshape(n, H, W).astype(np.float32)
    keep = (ts >= t0 - 1e-3) & (ts <= t0 + dur + 1e-3)
    return ts[keep], fr[keep]


def small(frames):
    """24x14 normalised (mean 0, std 1) version of 96x54 frames, flattened: the cheap picture signature."""
    s = np.stack([cv2.resize(f, (24, 14), interpolation=cv2.INTER_AREA) for f in frames]).reshape(len(frames), -1)
    s = s - s.mean(1, keepdims=True)
    return s / (s.std(1, keepdims=True) + 1e-3)


def file_id(path):
    """size + hash of 3 chunks: equal -> the very same bytes (for all practical purposes)."""
    size = os.path.getsize(path)
    h = hashlib.sha1(str(size).encode())
    with open(path, "rb") as f:
        for pos in (0, size // 2, max(0, size - (1 << 20))):
            f.seek(pos)
            h.update(f.read(1 << 20))
    return size, h.hexdigest()


ENV_HZ = 100


def audio_env(path):
    """Loudness envelope of the first audio stream, 100 values per second, standardised (loudness trends removed), or None without audio.
    Survives re-encoding, scaling and a trim; the same recording gives the same curve whatever the picture file looks like."""
    p = subprocess.run([FF, "-nostdin", "-v", "error", "-i", path, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "8000", "-f", "f32le", "-"], capture_output=True)
    x = np.frombuffer(p.stdout, np.float32)
    n = len(x) // 80
    if n < 300:
        return None
    e = np.log1p(200.0 * np.sqrt((x[:n * 80].reshape(n, 80) ** 2).mean(1)))
    e = e - np.convolve(e, np.ones(101) / 101, "same")
    sd = e.std()
    return None if sd < 1e-4 else (e / sd).astype(np.float32)


def audio_vote(a, b):
    """Offset (time in a minus time in b) by cross-correlating the audio envelopes -> (offset, z) or (None, 0); z = how far the best
    peak stands out of the rest of the curve (unrelated recordings: 4 to 5; the same recording: 10+)."""
    if a.env is None or b.env is None or len(b.env) < 500:
        return None, 0.0
    n = 1 << int(np.ceil(np.log2(len(a.env) + len(b.env))))
    c = np.fft.irfft(np.fft.rfft(a.env, n) * np.conj(np.fft.rfft(b.env, n)), n)
    lags = np.r_[np.arange(0, len(a.env)), np.arange(-len(b.env) + 1, 0)]          # lag k: a[t + k] ~ b[t]
    valid = np.r_[np.arange(0, len(a.env)), np.arange(n - len(b.env) + 1, n)]
    c = c[valid] / len(b.env)
    k = int(np.argmax(c))
    z = float((c[k] - c.mean()) / (c.std() + 1e-9))
    return float(lags[k]) / ENV_HZ, z


class Clip:
    def __init__(self, name, path, cache=None):
        self.name, self.path = name, path
        key = f"{os.path.abspath(path)}|{os.path.getsize(path)}|{int(os.path.getmtime(path))}"
        if cache is not None and key in cache:
            self.t, self.f, self.env = cache[key]
        else:
            self.t, self.f = keyframes(path)
            self.env = audio_env(path)
            if cache is not None:
                cache[key] = (self.t, self.f, self.env)
        self.sig = small(self.f) if len(self.f) else np.zeros((0, 336), np.float32)
        self.dur = float(self.t[-1] - self.t[0]) if len(self.t) > 1 else 0.0
        self.size, self.fid = file_id(path)


def vote(a, b):
    """Offset (time in a minus time in b) most key frames of b agree on -> (offset, n_votes, [(i_b, j_a)])."""
    if len(a.t) < 2 or len(b.t) < 2:
        return None, 0, []
    d = np.empty((len(b.t), len(a.t)), np.float32)
    for i in range(len(b.t)):                                               # (nb, na) mean squared difference of the signatures
        d[i] = ((a.sig - b.sig[i]) ** 2).mean(1)
    j = d.argmin(1)
    close = d[np.arange(len(j)), j] <= SIG_MAX                              # a vote needs a similar picture, not just the least different one
    off = a.t[j] - b.t
    best, bn, bl = None, 0, []
    for o in off[close]:                                                    # the offset that most key frames agree on (+-0.3 s)
        m = close & (np.abs(off - o) <= 0.3)
        if m.sum() > bn:
            best, bn, bl = float(np.median(off[m])), int(m.sum()), [(int(i), int(j[i])) for i in np.flatnonzero(m)]
    return best, bn, bl


def verify(a, b, off):
    """Check the voted offset on the pixels. -> None or {offset_s (refined), n (key frames of b that agree), mad}."""
    # key frames of b whose partner time falls inside a
    inside = [i for i in range(len(b.t)) if a.t[0] - 1e-3 <= b.t[i] + off <= a.t[-1] + 0.5]
    if len(inside) < MIN_AGREE:
        return None
    pick = [inside[int(round(q))] for q in np.linspace(0, len(inside) - 1, min(6, len(inside)))]
    offs, mads = [], []
    for i in pick:
        wt, wf = window(a.path, b.t[i] + off - WIN, 2 * WIN)
        if len(wf) < 4:
            continue
        diff = np.abs(wf - b.f[i][None]).mean((1, 2))
        k = int(diff.argmin())
        if diff[k] <= MAX_MAD and diff[k] <= RATIO * float(np.median(diff)):
            offs.append(float(wt[k] - b.t[i]))
            mads.append(float(diff[k]))
    if len(offs) < MIN_AGREE:
        return None
    med = float(np.median(offs))
    agree = [o for o in offs if abs(o - med) <= 1.5 / 60]
    if len(agree) < MIN_AGREE:
        return None
    return {"offset_s": round(float(np.median(agree)), 4), "n": len(agree), "of": len(pick), "mad": round(float(np.mean(mads)), 2)}


def compare(x, y):
    """-> pair dict or None. a = the longer clip."""
    a, b = (x, y) if (x.dur, x.name) >= (y.dur, y.name) else (y, x)
    if x.size == y.size and x.fid == y.fid:
        a, b = sorted((x, y), key=lambda c: c.name)
        return {"a": a.name, "b": b.name, "offset_s": 0.0, "kind": "identical", "b_in_a_s": [0.0, round(b.dur, 3)], "evidence": "same bytes"}
    off, n, _ = vote(a, b)
    v, how = None, f"{n} key-frame votes"
    if off is not None and n >= MIN_AGREE:
        v = verify(a, b, off)
    if v is None:                                   # no identical key frames (a re-encoded trim has its own): find the offset by the sound instead
        off, z = audio_vote(a, b)
        if off is not None and z >= AUDIO_Z:
            v = verify(a, b, off)
            how = f"sound offset {off:.2f} s, z {z:.0f}"
    if v is None:
        return None
    o = v["offset_s"]
    lo, hi = max(b.t[0], a.t[0] - o), min(b.t[-1], a.t[-1] - o)
    if hi - lo < 0.5:
        return None
    inside = (hi - lo) / max(b.dur, 1e-6)
    kind = "identical" if abs(o) < 2 / 60 and abs(a.dur - b.dur) < 0.5 else "trim" if inside > 0.9 else "overlap"
    return {"a": a.name, "b": b.name, "offset_s": o, "kind": kind, "b_in_a_s": [round(float(lo), 3), round(float(hi), 3)],
            "evidence": f"{v['n']}/{v['of']} key frames of {b.name} match {a.name} pixel by pixel (mean grey diff {v['mad']}), {how}"}


def find(clips, cache=None):
    """clips: [(name, path)] -> list of pair dicts. cache: dict that keeps the key frames between calls (optional)."""
    cl = []

    def load(q):
        try:
            return Clip(q[0], q[1], cache)
        except OSError as e:
            say(f"dupes: {q[0]}: cannot read {q[1]}: {e}")

    with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as ex:      # ffmpeg does the work: threads are enough
        cl = [c for c in ex.map(load, clips) if c]
    out = []
    for i in range(len(cl)):
        for j in range(i + 1, len(cl)):
            r = compare(cl[i], cl[j])
            if r:
                out.append(r)
    return out


def groups(pairs):
    """{b: (a, offset_s, [lo, hi])} - every duplicate clip -> the clip that keeps its kills (the top-most parent).
    A chain (trim of a trim) is followed to the end and the offsets add up."""
    parent = {p["b"]: p for p in pairs}
    res = {}
    for b in parent:
        a, off, seen = b, 0.0, {b}
        rng = None
        while a in parent and parent[a]["a"] not in seen:
            p = parent[a]
            off += p["offset_s"]
            rng = p["b_in_a_s"] if rng is None else rng
            a = p["a"]
            seen.add(a)
        res[b] = (a, round(off, 4), parent[b]["b_in_a_s"])
    return res


def frame_map(clip, frame, mapping, pts_of):
    """Frame `frame` of `clip` -> (clip it lives in, frame index there) when `clip` is a duplicate whose frame lies in the shared
    part, else (clip, frame). mapping = groups(pairs); pts_of(name) -> pts array (seconds) of that clip."""
    if clip not in mapping:
        return clip, frame
    a, off, (lo, hi) = mapping[clip]
    pb = pts_of(clip)
    t = float(pb[min(frame, len(pb) - 1)])
    if not lo - 0.05 <= t <= hi + 0.05:
        return clip, frame
    pa = pts_of(a)
    return a, int(np.abs(pa - (t + off)).argmin())


def clips_of(args):
    if args.dir:
        files = sorted(f for f in glob.glob(os.path.join(args.dir, "*")) if f.lower().endswith(VIDEO))
        return [(os.path.splitext(os.path.basename(f))[0], f) for f in files]
    names = args.clips or sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob("src/*") if f.lower().endswith(VIDEO))
    names = [n for n in names if n.lower() != "music"]
    out = []
    for n in names:
        hits = sorted(glob.glob(f"src/{glob.escape(n)}.*"))
        if not hits:
            sys.exit(f"dupes.py: no clip {n!r} in src/ (python ingest.py makes src/)")
        out.append((n, hits[0]))
    return out


def report(pairs, label=None):
    """Printed form (also used by ingest.py)."""
    for p in pairs:
        a, b = p["a"], p["b"]
        la, lb = (label or {}).get(a, a), (label or {}).get(b, b)
        if p["kind"] == "identical":
            say(f"  DUPLICATE {lb} is the same footage as {la} ({p['evidence']}): use only one of them")
        else:
            lo, hi = p["b_in_a_s"]
            say(f"  DUPLICATE {lb} ({p['kind']}) lies inside {la}: {lb} t={lo:.2f}..{hi:.2f}s is {la} t={lo + p['offset_s']:.2f}..{hi + p['offset_s']:.2f}s "
                f"({p['evidence']}): a kill in that part is the same kill, keep the one in {la}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("clips", nargs="*", help="clip names of src/ (default: all)")
    ap.add_argument("--dir", help="a folder of video files instead of src/")
    ap.add_argument("--out", default="dupes.json")
    ap.add_argument("--cache", help="pickle file that keeps the key frames of the clips between runs (a second run takes seconds)")
    args = ap.parse_args()
    t0 = time.time()
    cl = clips_of(args)
    if len(cl) < 2:
        sys.exit("dupes.py: need at least two clips")
    cache = None
    if args.cache:
        cache = pickle.load(open(args.cache, "rb")) if os.path.exists(args.cache) else {}
    pairs = find(cl, cache)
    if args.cache:
        pickle.dump(cache, open(args.cache, "wb"))
    json.dump(pairs, open(args.out, "w", encoding="utf-8"), indent=1)
    report(pairs)
    say(f"dupes.py: {len(cl)} clips, {len(pairs)} duplicate pairs -> {args.out} ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
