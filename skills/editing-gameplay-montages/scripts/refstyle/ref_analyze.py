"""Read a reference edit by measurement, before designing ("faz com a MESMA EDICAO desse vídeo").

    python ref_analyze.py <reference video> [--music <the song you will use>] [--out DIR] [--max-seconds N] [--no-sheets]

Writes in DIR (default: the current folder):
    ref_notes.md     the findings in words, ending with SUGGESTED SETTINGS for timeline.py
    ref_notes.json   the same as numbers (cuts with their beat offsets and transition kinds, pacing, text, colour, ...)
    ref_sheets/      images to READ afterwards: the whole video at 4 fps, every frame around three cuts, enlarged centre
                     crops, the first and the last seconds

What it measures (reference-style.md, "Reading the reference"): orientation and layout (full frame, window over a blurred
backdrop, black bars); the beat grid of the reference's own sound (music_tempo.py + music_grid.py) and every cut with its
offset to the grid and its length in beats; how the cuts are made (hard, whip, zoom burst, roll, flash, dip) with a confidence;
slow motion and freezes; big words (no OCR); colour, vignette, grain, colour fringe; shake and zoom around the cuts; the ending.
`--music` is the song of YOUR edit: the clip lengths are then also given for its tempo. A reference without sound is read in
seconds and frames only (with `--music` the grid is fitted to the cuts: offsets are then meaningless and said so).

Every number is a measurement of pixels and sound, not a judgement: the notes say where it is a lower bound or a guess. Needs the
project venv (numpy, opencv) and ffmpeg (ff.py). About 35 s of analysis per minute of video on this skill's PC with the sheets (25 s without), longer while a game or a render runs."""
import argparse
import collections
import datetime
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import refmeasure as rm  # noqa: E402
from ff import FF  # noqa: E402

# What the same measures read on the worked example (reference-style edit, LOOK absent = "padrao"): the yardstick for the LOOK
# suggestion, because the colour of the footage itself moves the raw numbers. Measured with this script on the worked example's render.
V3_BASE = dict(saturation=0.4245, contrast_spread=143.8, vignette_amount=0.1711, noise_sigma=0.124, fringe=1.207, shake_pct_width=0.311, zoom_pct_frame=0.691,
               blur_mean=0.445, blips_per_min=0.0, warmth=0.4187, shadow_warmth=0.4552, light_warmth=0.4177)
SNAP = [0.125, 0.25, 0.375, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]
NOTE = {0.125: "1/32", 0.25: "1/16", 0.375: "dotted 1/16", 0.5: "1/8", 0.75: "dotted 1/8", 1.0: "1/4", 1.5: "dotted 1/4", 2.0: "1/2", 3.0: "dotted 1/2",
        4.0: "whole", 6.0: "1.5 bars", 8.0: "2 bars"}
BLUR_KINDS = ("whip", "zoom", "roll", "blur")


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if (isinstance(o, float) and not math.isfinite(o)) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return jsonable(o.tolist())
    return o


def snap_beats(x, beat_frames):
    """The note value (beats) nearest to x beats, if it is within 1.5 frames (or 8 %) of it, else None. beat_frames = frames per beat."""
    best = min(SNAP, key=lambda v: abs(v - x) / v)
    return best if abs(best - x) * beat_frames <= max(1.5, 0.08 * best * beat_frames) else None


def fmt_beats(v):
    return ("%g" % v) if v is not None else "other"


# ------------------------------------------------------------------------------------------------ cut and beat
def align_cuts(cuts, fps, bpm, beat0):
    """Each cut's position on the beat grid, by circular statistics: for a lattice of 1, 1/2 or 1/4 beat the cut phases are averaged on the
    circle; a mean resultant length R >= 0.6 (chance: about 1 / sqrt(cuts)) means the cuts sit at a FIXED distance from the lattice, and
    the mean phase is that distance (negative = the cut comes before the hit). The coarsest locked lattice is used.
    -> dict(step, offset_ms_median, ...); fills cut['beat'] (beats from the grid's first beat) and cut['offset_ms']."""
    per = 60.0 / bpm
    ts = np.array([c["frame"] / fps for c in cuts])
    if len(ts) < 5:
        return dict(step=None, note="fewer than 5 cuts: no alignment statistics")
    chosen, rows = None, []
    for step in (1.0, 0.5, 0.25):
        lat = per * step
        z = np.mean(np.exp(2j * np.pi * (ts - beat0) / lat))
        R, mu = float(abs(z)), float(np.angle(z) / (2 * np.pi))
        rows.append(dict(step=step, concentration=round(R, 3), chance=round(float(1 / math.sqrt(len(ts))), 3), offset_ms=round(mu * lat * 1000, 1)))
        if chosen is None and R >= 0.6:
            chosen = (step, mu, R)
    if chosen:
        step, mu, R = chosen
    else:
        step = 0.5
        mu = 0.0
        R = 0.0
    lat = per * step
    ph = (ts - beat0) / lat
    off = (ph - np.round(ph - mu)) * lat * 1000                 # distance to the lattice, around the mean offset
    for c, o, t in zip(cuts, off, ts):
        c["beat"] = round(float((t - beat0) / per), 3)
        c["offset_ms"] = round(float(o), 1)
    res = dict(step=step if chosen else None, report_step=step, lattice_tests=rows, concentration=round(R, 3))
    mu_ms = mu * lat * 1000
    lock = np.abs(off - mu_ms) <= 40
    res["locked_share"] = round(float(lock.mean()), 3)
    if chosen and lock.sum() >= 3:
        o = off[lock]
        res.update(offset_ms_median=round(float(np.median(o)), 1), offset_ms_mean=round(float(o.mean()), 1), offset_ms_std=round(float(o.std()), 1),
                   offset_ms_p10=round(float(np.percentile(o, 10)), 1), offset_ms_p90=round(float(np.percentile(o, 90)), 1))
        res["offset_frames_median"] = round(res["offset_ms_median"] * fps / 1000, 2)
        res["offset_beats_median"] = round(res["offset_ms_median"] / (per * 1000), 3)
    return res


def fit_cut_grid(cuts, fps):
    """A reference without sound: the tempo (68..182 BPM) and phase at which the cut times sit best on a lattice of half beats.
    -> (bpm, beat0, concentration) or None. The tempo is only known up to the usual half / double ambiguity, and the phase is fitted to
    the cuts themselves, so no cut-to-beat offset can be read from it."""
    ts = np.array([c["frame"] / fps for c in cuts])
    if len(ts) < 8:
        return None
    best = (0.0, None, 0.0)
    for bpm in np.arange(68.0, 182.01, 0.02):
        lat = 60.0 / bpm / 2
        z = np.mean(np.exp(2j * np.pi * ts / lat))
        if abs(z) > best[0]:
            best = (float(abs(z)), float(bpm), float(np.angle(z) / (2 * np.pi)))
    R, bpm, mu = best
    if R < max(0.6, 3.0 / math.sqrt(len(ts))):
        return None
    lat = 60.0 / bpm / 2
    return bpm, float((mu * lat) % (60.0 / bpm)), R


def clip_lengths(cuts, fps, bpm, ends_with_video_frames=None):
    """Clip length (frames, beats, note value) of each cut's clip; histogram by note value."""
    per = 60.0 / bpm if bpm else None
    out, hist = [], collections.Counter()
    for j, c in enumerate(cuts):
        fr = c.get("clip_frames")
        if not fr:
            continue
        if per:
            b = fr / fps / per
            c["clip_beats"] = round(float(b), 3)
            if j == len(cuts) - 1:                       # the last clip is cut off by the end of the video
                c["note"] = None
                c["last_clip"] = True
                continue
            s = snap_beats(b, per * fps)
            c["note"] = s
            hist[fmt_beats(s)] += 1
    return hist


# ------------------------------------------------------------------------------------------------ report pieces
def kinds_table(cuts):
    cnt = collections.Counter(c["kind"] for c in cuts)
    conf = collections.defaultdict(list)
    for c in cuts:
        conf[c["kind"]].append(c.get("kind_conf", 0))
    return {k: dict(count=v, share=round(v / max(1, len(cuts)), 3), mean_conf=round(float(np.mean(conf[k])), 2)) for k, v in cnt.most_common()}


def density_sections(cuts, bpm, beat0, fps, dur, win_beats=8):
    per = 60.0 / bpm if bpm else None
    if per:
        n = int(math.ceil((dur - beat0) / (per * win_beats)))
        edges = [beat0 + i * per * win_beats for i in range(max(n, 1) + 1)]
        label = "beats"
    else:
        n = int(math.ceil(dur / 4.0))
        edges = [i * 4.0 for i in range(n + 1)]
        label = "s"
    rows = []
    for a, b in zip(edges[:-1], edges[1:]):
        cs = [c for c in cuts if a <= c["frame"] / fps < b]
        if not cs and a > dur:
            continue
        rows.append(dict(start_s=round(max(a, 0.0), 2), cuts=len(cs), per_beat=round(len(cs) / win_beats, 2) if per else None,
                         per_second=round(len(cs) / (b - a), 2),
                         mean_clip_beats=round(float(np.mean([c["clip_beats"] for c in cs if "clip_beats" in c])), 2) if per and any("clip_beats" in c for c in cs) else None))
    return dict(window=("%d beats" % win_beats) if per else "4 s", rows=rows)


def cuts_on_analysis(cuts, fps, bpm, beat0, pulses, offset_ms=0.0):
    """Which music events the cuts sit on: kick / bass hit, snare / clap, hat only, nothing. CUTS_ON = "bass" when the cuts pick the
    kicks out, "kills" when they follow every hit."""
    ts, lo, mid, hi = pulses
    per = 60.0 / bpm
    kick, snare, hat = lo >= 0.4, mid >= 0.6, hi >= 0.5
    cat = collections.Counter()
    used = 0
    for c in cuts:
        t = c["frame"] / fps - offset_ms / 1000.0        # the hit the cut was made for: the cut's time less its usual lead
        i = int(round((t - ts[0]) / (per * 0.5)))
        if i < 0 or i >= len(ts) or abs(ts[i] - t) > 0.06:
            cat["between half beats"] += 1
            c["on"] = "between"
            continue
        used += 1
        if kick[i]:
            kind = "kick"
        elif snare[i]:
            kind = "snare"
        elif hat[i]:
            kind = "hat only"
        else:
            kind = "nothing"
        c["on"] = kind
        cat[kind] += 1
    n = max(1, len(cuts))
    t0 = cuts[0]["frame"] / fps if cuts else 0
    t1 = cuts[-1]["frame"] / fps if cuts else 0
    span = (ts >= t0 - 0.05) & (ts <= t1 + 0.05)
    base_kick = float(kick[span].mean()) if span.any() else float(kick.mean())
    share = {k: round(v / n, 3) for k, v in cat.items()}
    on_kick = cat.get("kick", 0) / max(1, used)
    res = dict(shares=share, kick_share_of_aligned=round(on_kick, 3), kick_base_rate=round(base_kick, 3), snare_base_rate=round(float(snare[span].mean()) if span.any() else 0.0, 3),
               aligned=used, total=len(cuts))
    res["suggest"] = "bass" if (used >= 8 and on_kick >= 0.65 and on_kick >= base_kick + 0.2) else "kills"
    return res


# ------------------------------------------------------------------------------------------------ suggestions
def mult(ratio, gain):
    """LOOK multiplier for a measured ratio to the worked example's look (look.py: above 1 the scale climbs `gain` times faster)."""
    if ratio is None:
        return None
    if ratio <= 1:
        return max(0.0, round(ratio, 1))
    return round(1 + (ratio - 1) / gain, 1)


def nearest_preset(look):
    import look as lk
    best, bd = "padrao", 1e9
    for name, p in lk.PRESETS.items():
        d = 0.0
        for k in ("vignette", "saturation", "contrast", "shake", "kill_zoom", "blur_in"):
            d += (look.get(k, 1.0) - p.get(k, 1.0)) ** 2
        if d < bd:
            best, bd = name, d
    return best


def suggest_look(col, nat, sz, blur_mean, blips_per_min, blur_share, bars, roi_kind):
    B = V3_BASE
    notes, look = [], {}
    sat_r = col["saturation"] / B["saturation"]
    con_r = col["contrast_spread"] / B["contrast_spread"]
    vig_amt = max(0.0, 1.0 - col["vignette_corner_ratio"])
    vig_r = vig_amt / max(B["vignette_amount"], 1e-3)
    k_sat, k_con, k_vig = mult(sat_r, 2.5), mult(con_r, 2.5), mult(vig_r, 3.5)
    if k_sat is not None and abs(k_sat - 1) >= 0.15:
        look["saturation"] = k_sat
    if k_con is not None and abs(k_con - 1) >= 0.15:
        look["contrast"] = k_con
    if k_vig is not None and abs(k_vig - 1) >= 0.15:
        look["vignette"] = k_vig
    if nat.get("noise_sigma") is not None:
        d = nat["noise_sigma"] - B["noise_sigma"]
        if d >= 1.2:
            look["grain"] = 2.0
        elif d >= 0.6:
            look["grain"] = 1.5
    if nat.get("fringe") is not None and B["fringe"] > 0:
        r = abs(nat["fringe"]) / B["fringe"]
        if abs(r - 1) >= 0.5:
            look["fringe"] = round(min(2.0, max(0.0, r)), 1)
    # camera: the measured motion includes the footage's own camera work, so only a clear difference counts
    if sz.get("shake_pct_width") is not None and B["shake_pct_width"] > 0:
        r = sz["shake_pct_width"] / B["shake_pct_width"]
        if r >= 2.5:
            look["shake"] = 1.5
        elif r <= 0.4:
            look["shake"] = 0.5
    if sz.get("zoom_pct_frame") is not None and B["zoom_pct_frame"] > 0:
        r = sz["zoom_pct_frame"] / B["zoom_pct_frame"]
        if r >= 2.5:
            look["kill_zoom"] = 1.3
        elif r <= 0.4:
            look["kill_zoom"] = 0.5
    if blips_per_min is not None and blips_per_min >= max(4.0, 2.0 * B["blips_per_min"]):
        look["flash"] = round(min(2.0, 1.0 + blips_per_min / 20.0), 1)
    if blur_share is not None and blur_share < 0.15:
        look["blur_in"] = 0.0
    elif blur_mean is not None:
        r = blur_mean / B["blur_mean"]
        if abs(r - 1) >= 0.3:
            look["blur_in"] = round(min(2.0, max(0.3, r)), 1)
    # colour grade
    dw = col["warmth"] - B["warmth"]
    dsh = (col["shadow_warmth"] - col["light_warmth"]) - (B["shadow_warmth"] - B["light_warmth"])
    grade, amount = None, 1.0
    if sat_r < 0.25:
        grade = "mono"
    elif dsh <= -0.35:
        grade, amount = "teal_orange", min(2.0, max(0.5, abs(dsh) / 0.6))
    elif dw >= 0.25:
        grade, amount = "warm", min(2.0, max(0.5, dw / 0.5))
    elif dw <= -0.25:
        grade, amount = "cool", min(2.0, max(0.5, -dw / 0.5))
    elif sat_r >= 1.35:
        grade, amount = "vibrant", min(2.0, max(0.5, (sat_r - 1) / 0.5))
    if grade:
        look["grade"] = grade
        if abs(amount - 1) >= 0.2:
            look["grade_amount"] = round(amount, 1)
    if bars:
        look["bars"] = True
    notes.append("saturation %.2fx, contrast %.2fx, vignette %.2fx of the worked example's measures (footage colour moves these: a heuristic, check stills)" % (sat_r, con_r, vig_r))
    return look, notes


# ------------------------------------------------------------------------------------------------ sheets
def run_ff(args):
    return subprocess.run([FF, "-v", "error", "-y"] + args, capture_output=True)


def make_sheets(src, info, outdir, cuts, text, ending, fps, t_first_cut):
    sd = os.path.join(outdir, "ref_sheets")
    os.makedirs(sd, exist_ok=True)
    for f in os.listdir(sd):
        if f.endswith(".jpg"):
            os.remove(os.path.join(sd, f))
    W, H, dur = info["width"], info["height"], info["duration"]
    vertical = H > W * 1.2
    tw, cols, rows = (120, 12, 4) if vertical else (240, 8, 6)
    made = []

    def add(name, caption):
        if os.path.exists(os.path.join(sd, name)):
            made.append((os.path.join("ref_sheets", name), caption))
    ov_fps = min(4.0, 144.0 / max(dur, 1))
    run_ff(["-i", src, "-an", "-vf", "fps=%g,scale=%d:-2,tile=%dx%d" % (ov_fps, tw, cols, rows), "-q:v", "3", os.path.join(sd, "overview_%02d.jpg")])
    for f in sorted(os.listdir(sd)):
        if f.startswith("overview_"):
            made.append((os.path.join("ref_sheets", f), "the whole video at %g fps, %d tiles per sheet, in reading order" % (ov_fps, cols * rows)))
    # three cuts to look at every frame of: the first after the intro, the strongest blur-in, one from the middle
    picks = []
    ok = [c for c in cuts if c["frame"] / fps >= 0.3 and c.get("kind") != "unknown"]
    if ok:
        picks.append(ok[0])
        bl = [c for c in ok if c.get("kind") in BLUR_KINDS and c not in picks]
        if bl:
            picks.append(max(bl, key=lambda c: c.get("blur", 0)))
        mid = [c for c in ok if c not in picks and abs(c["frame"] - ok[len(ok) // 2]["frame"]) < 3]
        rest = [c for c in ok if c not in picks]
        if rest:
            picks.append(min(rest, key=lambda c: abs(c["frame"] - ok[len(ok) // 2]["frame"])))
        for c in ok:
            if len(picks) >= 3:
                break
            if c not in picks and c.get("kind") != picks[0].get("kind"):
                picks.append(c)
    nframes = cols * rows
    for i, c in enumerate(picks[:3]):
        t = max(0.0, c["frame"] / fps - 0.2 * 60 / 60 * (cols * rows / 48))
        t = max(0.0, c["frame"] / fps - 12.0 / fps)
        name = "cut%d_%s_t%.2f.jpg" % (i + 1, c.get("kind", "?"), c["frame"] / fps)
        run_ff(["-ss", "%.3f" % t, "-i", src, "-an", "-t", "%.3f" % (nframes / fps + 0.01), "-vf", "scale=%d:-2,tile=%dx%d" % (tw, cols, rows), "-frames:v", "1", "-q:v", "3", os.path.join(sd, name)])
        add(name, "EVERY frame from 12 frames before the cut at %.2f s (tile 13 is the first frame of the new clip; kind: %s, confidence %.2f)" % (c["frame"] / fps, c.get("kind"), c.get("kind_conf", 0)))
    # enlarged centre crops: where the text evidence is strongest, else evenly spread
    times = []
    runs = sorted(text.get("runs", []), key=lambda r: -(r[1] - r[0]))
    for a, b in runs:
        t = (a + b) / 2 / fps
        if all(abs(t - u) > 1.0 for u in times):
            times.append(t)
        if len(times) >= 4:
            break
    k = 0
    while len(times) < 4:
        t = dur * (k + 1) / 5
        if all(abs(t - u) > 0.5 for u in times):
            times.append(t)
        k += 1
    times = sorted(times)[:4]
    crops = []
    for j, t in enumerate(times):
        p = os.path.join(sd, "_crop%d.jpg" % j)
        cw, chh = ("iw*0.9", "ih*0.34") if vertical else ("iw*0.78", "ih*0.52")
        cx, cy = ("iw*0.05", "ih*0.33") if vertical else ("iw*0.11", "ih*0.24")
        run_ff(["-ss", "%.3f" % t, "-i", src, "-an", "-frames:v", "1", "-vf", "crop=%s:%s:%s:%s,scale=%d:-2" % (cw, chh, cx, cy, 480 if vertical else 800), "-q:v", "2", p])
        if os.path.exists(p):
            crops.append(cv2.imread(p))
            os.remove(p)
    if crops:
        hh = min(c.shape[0] for c in crops)
        crops = [cv2.resize(c, (int(c.shape[1] * hh / c.shape[0]), hh)) for c in crops]
        while len(crops) < 4:
            crops.append(np.zeros_like(crops[0]))
        wmax = max(c.shape[1] for c in crops)
        crops = [cv2.copyMakeBorder(c, 0, 0, 0, wmax - c.shape[1], cv2.BORDER_CONSTANT) for c in crops]
        grid = np.vstack([np.hstack(crops[:2]), np.hstack(crops[2:])])
        cv2.imwrite(os.path.join(sd, "centre_crops.jpg"), grid, [cv2.IMWRITE_JPEG_QUALITY, 90])
        add("centre_crops.jpg", "ENLARGED centre crops at %s s (reading order): judge the words' fill (see-through or solid), colour and size here, not on the small tiles" % ", ".join("%.1f" % t for t in times))
    # first and last seconds
    run_ff(["-t", "3", "-i", src, "-an", "-vf", "fps=8,scale=%d:-2,tile=%dx%d" % (tw, cols if not vertical else 12, 2 if not vertical else 2), "-frames:v", "1", "-q:v", "3", os.path.join(sd, "start_3s.jpg")])
    add("start_3s.jpg", "the first 3 s at 8 fps (the intro)")
    run_ff(["-ss", "%.3f" % max(0.0, dur - 3.0), "-i", src, "-an", "-vf", "fps=8,scale=%d:-2,tile=%dx%d" % (tw, cols if not vertical else 12, 2), "-frames:v", "1", "-q:v", "3", os.path.join(sd, "end_3s.jpg")])
    add("end_3s.jpg", "the last 3 s at 8 fps (the ending: %s)" % ending["kind"])
    return made


# ------------------------------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="Measure a reference edit: layout, cuts and beats, transitions, speed, text, colour, ending.")
    ap.add_argument("video")
    ap.add_argument("--music", help="the song of YOUR edit (clip lengths are then also given for its tempo)")
    ap.add_argument("--out", default=".", help="folder for ref_notes.md, ref_notes.json, ref_sheets/ (default: here)")
    ap.add_argument("--max-seconds", type=float, default=150.0, help="analyse at most this much of the video (default 150)")
    ap.add_argument("--no-sheets", action="store_true", help="skip the contact sheets")
    a = ap.parse_args()
    src = os.path.abspath(a.video)                    # the helper scripts run in another folder: absolute paths
    if not os.path.exists(src):
        raise SystemExit("%s does not exist" % src)
    if a.music:
        a.music = os.path.abspath(a.music)
        if not os.path.exists(a.music):
            raise SystemExit("--music %s does not exist" % a.music)
    os.makedirs(a.out, exist_ok=True)
    T0 = time.time()
    tm = {}

    def lap(name, t):
        tm[name] = round(time.time() - t, 2)

    t = time.time()
    info = rm.probe(src)
    fps = info["fps"]
    max_frames = int(a.max_seconds * fps)
    ex = ThreadPoolExecutor(max_workers=3)           # the sound, the words and the colour run beside the picture work

    def audio_job():
        beat_, err_, song_, serr_, pul_ = None, None, None, None, None
        if info["has_audio"]:
            beat_ = rm.beat_grid(src, 0.0, min(info["duration"], a.max_seconds))
            if "error" in beat_:
                err_, beat_ = beat_["error"], None
        if a.music:
            song_ = rm.beat_grid(a.music)
            if "error" in song_:
                serr_, song_ = song_["error"], None
        if beat_:
            pul_ = rm.audio_pulses(src, beat_["bpm"], beat_["beat0"], 0.5)
        return beat_, err_, song_, serr_, pul_
    f_audio = ex.submit(audio_job)
    G, C, nat_size = rm.decode(src, info, max_frames)
    n = len(G)
    dur = n / fps
    lap("decode", t)
    clipped = n >= max_frames and info["duration"] > a.max_seconds + 0.5
    print("%s: %dx%d, %.2f fps, %.1f s%s, audio: %s" % (os.path.basename(src), info["width"], info["height"], fps, dur, " (first %.0f s of %.1f)" % (a.max_seconds, info["duration"]) if clipped else "",
                                                     "yes" if info["has_audio"] else "NO"))

    t = time.time()
    lay = rm.detect_layout(G, info)
    roi = lay["roi"]
    lap("layout", t)
    f_text = ex.submit(rm.detect_text, G, fps, 2 if dur < 100 else 3)

    def colour_job():
        gh, gw = G.shape[1:]
        col_ = rm.colour_stats(G, C, roi, lay)
        samples = rm.sample_native(src, info, 12)
        nat_ = rm.native_stats(samples, info["width"], info["height"], (roi[0] / gw, roi[1] / gh, roi[2] / gw, roi[3] / gh))
        return col_, nat_, rm.ending_stats(G, fps)
    f_col = ex.submit(colour_job)
    t = time.time()
    L, R, Th, S = rm.frame_pair_features(G, C, roi)
    cuts = rm.detect_cuts(L, R)
    rm.classify_transitions(S, L, cuts, fps)
    blips = rm.find_blips(Th, L)
    lap("cuts", t)

    # ---- beat grid
    t = time.time()
    beat, beat_err, song, song_err, pul = f_audio.result()
    grid_source = "the reference's own sound" if beat else None
    if beat_err:
        print("beat grid of the reference: %s" % beat_err)
    if song_err:
        print("beat grid of --music: %s" % song_err)
    if beat is None and cuts:
        fit = fit_cut_grid(cuts, fps)
        if fit:
            beat = dict(bpm=round(fit[0], 2), beat0=round(fit[1], 4), members=[], weak=False,
                        notes=["no usable sound in the reference: the tempo and phase are FITTED TO THE CUTS (half-beat lattice, concentration %.2f); it is only known up to half / double time" % fit[2]])
            grid_source = "a tempo fitted to the cuts (no usable sound)"
    if beat is None and song is not None:
        # no usable sound and no clear rhythm of cuts: the tempo of the song, the phase fitted to the cuts (offsets then mean nothing)
        bpm = song["bpm"]
        per = 60.0 / bpm
        ts = np.array([c["frame"] / fps for c in cuts])
        ph = np.angle(np.mean(np.exp(2j * np.pi * (ts / (per * 0.5))))) / (2 * np.pi) if len(ts) else 0.0
        beat = dict(bpm=bpm, beat0=round(float((ph * per * 0.5) % per), 4), members=song["members"], weak=False, notes=["no sound in the reference: the song's tempo, the phase fitted to the cuts"])
        grid_source = "the song's tempo (--music), phase fitted to the cuts"
    lap("beat grid (wait)", t)
    bpm = beat["bpm"] if beat else None
    beat0 = beat["beat0"] if beat else 0.0

    for c in cuts:
        c["t"] = round(c["frame"] / fps, 3)
    al = hist = None
    if bpm:
        al = align_cuts(cuts, fps, bpm, beat0)
        if grid_source != "the reference's own sound":
            al["offset_note"] = "the grid was fitted to the cuts, so the offsets are meaningless"
            for c in cuts:
                c.pop("offset_ms", None)
        hist = clip_lengths(cuts, fps, bpm)
    cuts_on = None
    if beat and grid_source == "the reference's own sound" and pul is not None and len(cuts) >= 5:
        cuts_on = cuts_on_analysis(cuts, fps, bpm, beat0, pul, (al or {}).get("offset_ms_median") or 0.0)

    # ---- speed, shake, zoom
    t = time.time()
    h8 = 128
    S8 = np.array([cv2.resize(s.astype(np.uint8), (h8, max(8, int(round(h8 * s.shape[0] / s.shape[1])))), interpolation=cv2.INTER_AREA) for s in S])
    mo = rm.motion_series(S8, cuts, fps)
    black = np.array([float(g.mean()) < 8 for g in G])
    spd = rm.speed_feel(mo, cuts, fps, exclude_from=None, black=black)
    sz = rm.shake_zoom(mo, cuts, h8)
    lap("motion", t)

    t = time.time()
    txt = f_text.result()
    col, nat, end = f_col.result()
    ex.shutdown()
    lap("text, colour, ending (wait)", t)

    # ---- assembled facts
    kinds = kinds_table(cuts)
    blur_cuts = [c for c in cuts if c.get("kind") in BLUR_KINDS]
    blur_share = len(blur_cuts) / max(1, len([c for c in cuts if c.get("kind") != "unknown"]))
    blur_mean = float(np.mean([c["blur"] for c in blur_cuts])) if blur_cuts else None
    first_cut_t = cuts[0]["frame"] / fps if cuts else dur
    pacing = dict(cuts=len(cuts), cuts_per_minute=round(len(cuts) / dur * 60, 1), bpm=bpm, first_cut_s=round(first_cut_t, 2))
    lengths = [c["clip_frames"] for c in cuts if c.get("clip_frames")]
    pacing["clip_frames_median"] = float(np.median(lengths)) if lengths else None
    pacing["clip_seconds_median"] = round(float(np.median(lengths)) / fps, 3) if lengths else None
    if bpm and hist is not None:
        notes_only = {k: v for k, v in hist.items() if k != "other"}
        tot = max(1, sum(hist.values()))
        pacing["clip_beats_dist"] = {k: int(v) for k, v in sorted(hist.items(), key=lambda kv: (kv[0] == "other", float(kv[0]) if kv[0] != "other" else 0))}
        top = max(notes_only.items(), key=lambda kv: kv[1])[0] if notes_only else None
        pacing["clip_beats"] = float(top) if top else None
        bs = [c["clip_beats"] for c in cuts if "clip_beats" in c]
        pacing["clip_beats_median"] = round(float(np.median(bs)), 3) if bs else None
        pacing["offset_ms_median"] = al.get("offset_ms_median") if al else None
        pacing["lattice_step_beats"] = al.get("step") if al else None
        pacing["sections"] = density_sections(cuts, bpm, beat0, fps, dur)
    else:
        pacing["sections"] = density_sections(cuts, None, 0.0, fps, dur)
    # the clip lengths for the user's own song, counted in ITS beats (pacing.clip_beats is then in your beats)
    music_pacing = None
    if song and lengths:
        per_f = 60.0 / song["bpm"] * fps
        body = [c for c in cuts[:-1] if c.get("clip_frames")]
        sec = float(np.median(lengths)) / fps
        near = min(SNAP, key=lambda v: abs(v * per_f / fps - sec))
        if beat and not grid_source.startswith("the song"):
            # same musical value: the reference's tempo is taken as the member of its family (x2 or /2) nearest to the song's
            k = int(round(math.log2(bpm / song["bpm"])))
            fac = 2.0 ** (-k)
            dm = collections.Counter(fmt_beats(c["note"] * fac) if c.get("note") else "other" for c in body)
            method = "the reference's note values at %.2f BPM%s, counted in your %.2f BPM beats" % (bpm if k == 0 else bpm / 2 ** k, "" if k == 0 else " (its %s reading)" % ("half-time" if k > 0 else "double-time"), song["bpm"])
            tempo_ratio = (bpm / 2.0 ** k) / song["bpm"]
        else:
            dm = collections.Counter(fmt_beats(snap_beats(c["clip_frames"] / per_f, per_f)) for c in body)
            method = "the reference's clip lengths in seconds, counted in your beats (the reference has no sound of its own)"
            tempo_ratio = 1.0
        notes_m = {k_: v for k_, v in dm.items() if k_ != "other"}
        top = float(max(notes_m.items(), key=lambda kv: kv[1])[0]) if notes_m else near
        music_pacing = dict(bpm=song["bpm"], beat0=song["beat0"], clip_beats=top, clip_beats_nearest_seconds=near, clip_seconds_at_that_tempo=round(top * per_f / fps, 3),
                            reference_clip_seconds=round(sec, 3), clip_frames_at_that_tempo=round(top * per_f, 1), members=song["members"], method=method,
                            reference_tempo_over_yours=round(tempo_ratio, 3),
                            clip_beats_dist={k_: int(v) for k_, v in sorted(dm.items(), key=lambda kv: (kv[0] == "other", float(kv[0]) if kv[0] != "other" else 0))})
        pacing["clip_beats_reference_tempo"] = pacing.get("clip_beats")
        pacing["clip_beats_dist_reference_tempo"] = pacing.get("clip_beats_dist")
        pacing["clip_beats"] = top
        pacing["clip_beats_dist"] = music_pacing["clip_beats_dist"]
        pacing["music_bpm"] = song["bpm"]
    # ending / intro / words / slow motion
    intro_beats = None
    ib = (song or beat or {}).get("bpm")
    if ib and first_cut_t >= 2.0:
        intro_beats = int(round(first_cut_t / (60.0 / ib)))
    words_yes = txt["share"] >= 0.10 and txt["words"] >= 12            # a few rows of letter-like shapes also come from scenery (vents, stairs)
    words_check = (not words_yes) and (txt["share"] >= 0.04 or txt["words"] >= 3)
    sl = spd.get("slow_share")
    slow_rate = spd.get("rate")
    nominal_bars = lay.get("bars", {})
    bars_on = lay["kind"] == "letterbox" and lay["orientation"] == "horizontal" and (nominal_bars.get("top", 0) + nominal_bars.get("bottom", 0)) >= 0.06
    look, look_notes = suggest_look(col, nat, sz, blur_mean, len(blips) / dur * 60, blur_share if cuts else None, bars_on, lay["kind"])
    frame_s = "vertical" if info["height"] > info["width"] * 1.2 else "horizontal"
    fx = []
    if cuts:
        order = [("whip", ("bwhip", 0.0, 1)), ("zoom", ("bzoom", 0.0)), ("roll", ("broll", 0.0, 1)), ("hard", ("cut", 0.0)), ("whip", ("bwhip", 0.0, -1)), ("roll", ("broll", 0.0, -1))]
        shares = collections.Counter(c["kind"] for c in cuts if c["kind"] in ("whip", "zoom", "roll", "hard", "blur", "flash", "dip"))
        shares["roll"] += shares.pop("blur", 0)
        tot = max(1, sum(shares.values()))
        want = {k: shares.get(k, 0) / tot for k in ("whip", "zoom", "roll", "hard")}
        for _ in range(8):                         # largest remainder: fill 8 slots in the measured proportions
            k = max(want, key=lambda kk: want[kk])
            want[k] -= 1 / 8.0
            if k == "whip":
                fx.append(("bwhip", 0.0, 1 if fx.count(("bwhip", 0.0, 1)) <= fx.count(("bwhip", 0.0, -1)) else -1))
            elif k == "zoom":
                fx.append(("bzoom", 0.0))
            elif k == "roll":
                fx.append(("broll", 0.0, 1 if fx.count(("broll", 0.0, 1)) <= fx.count(("broll", 0.0, -1)) else -1))
            else:
                fx.append(("cut", 0.0))
        # interleave so the same kind does not run twice
        fx.sort(key=lambda e: e[0])
        out_fx, pool = [], fx[:]
        last = None
        while pool:
            pick = next((e for e in pool if e[0] != last), pool[0])
            pool.remove(pick)
            out_fx.append(pick)
            last = pick[0]
        fx = out_fx
    suggested = dict(FRAME=frame_s, CUTS_ON=cuts_on["suggest"] if cuts_on else None, clip_beats=pacing.get("clip_beats"),
                     clip_beats_reference_tempo=pacing.get("clip_beats_reference_tempo", pacing.get("clip_beats")), blur_in_share=round(blur_share, 2) if cuts else None, FX_cycle=fx, LOOK=look, LOOK_preset=None,
                     slow_rate=(max(0.06, min(0.3, slow_rate)) if (sl is not None and sl >= 0.08 and slow_rate) else None), slow_motion=bool(sl is not None and sl >= 0.08),
                     intro_beats=intro_beats, words=bool(words_yes), words_check=bool(words_check), ending=end["kind"], ending_seconds=end.get("seconds"))
    suggested["LOOK_preset"] = nearest_preset(look)

    total = time.time() - T0
    tm["total"] = round(total, 1)
    result = dict(
        file=os.path.basename(src), analysed_seconds=round(dur, 2), info=info, layout=lay, beat=beat, beat_source=grid_source, music=music_pacing,
        alignment=al, cuts_on=cuts_on, pacing=pacing, transitions=kinds, blips=dict(count=len(blips), per_minute=round(len(blips) / dur * 60, 1), kinds=collections.Counter("white/bright" if b["luma_jump"] > 0 else "dark" for b in blips),
                                                                           frames=[b["frame"] for b in blips][:40]),
        speed=spd, shake_zoom=sz, text={k: v for k, v in txt.items() if k not in ("covered",)}, colour=col, native=nat, ending=end, suggested=suggested,
        cuts=[{k: c[k] for k in ("frame", "t", "beat", "offset_ms", "clip_frames", "clip_beats", "note", "kind", "kind_conf", "blur", "on", "xy", "rt", "whip_axis", "L", "R") if k in c} for c in cuts],
        timing_seconds=tm, versions=dict(opencv=cv2.__version__, numpy=np.__version__))
    # ---- sheets
    sheets = []
    if not a.no_sheets:
        t = time.time()
        sheets = make_sheets(src, info, a.out, cuts, txt, end, fps, first_cut_t)
        tm["sheets"] = round(time.time() - t, 1)
        tm["total"] = round(time.time() - T0, 1)
    result["sheets"] = sheets
    with open(os.path.join(a.out, "ref_notes.json"), "w", encoding="utf-8") as f:
        json.dump(jsonable(result), f, indent=1, ensure_ascii=False)
    md = write_notes(result, cuts, blips, spd, txt, hist, a)
    with open(os.path.join(a.out, "ref_notes.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    print("\nwritten: %s, %s%s   (%.1f s for %.1f s of video = %.2f s per minute)" % (os.path.join(a.out, "ref_notes.md"), os.path.join(a.out, "ref_notes.json"),
                                                                                 ", ref_sheets/" if sheets else "", tm["total"], dur, tm["total"] / dur * 60))


def write_notes(r, cuts, blips, spd, txt, hist, args):
    info, lay, beat, al = r["info"], r["layout"], r["beat"], r["alignment"]
    P, S, sg = r["pacing"], r["suggested"], r["shake_zoom"]
    L = []
    w = L.append
    fps = info["fps"]
    w("# Reference notes: %s" % r["file"])
    w("")
    w("Measured by `ref_analyze.py` on %s: %d x %d, %.2f fps, %.1f s analysed, %s. Numbers, not judgement; limits at the end." % (
        datetime.date.today().isoformat(), info["width"], info["height"], fps, r["analysed_seconds"], "with sound" if info["has_audio"] else "NO sound"))
    w("")
    w("## 1. Format and layout")
    if lay["kind"] == "window":
        wd = lay["window"]
        w("- **Window over a backdrop**: %s canvas, the sharp gameplay window covers x %.0f-%.0f %%, y %.0f-%.0f %% of the frame (%.0f %% of the width, %.0f %% of the height, window aspect %.2f); outside it the picture is %s as sharp and %.0f %% as bright (the blurred, dimmed backdrop)." % (
            lay["orientation"], wd["x0"] * 100, wd["x1"] * 100, wd["y0"] * 100, wd["y1"] * 100, wd["width_share"] * 100, wd["height_share"] * 100, wd["aspect"],
            "%.0f %%" % (wd["backdrop_soft"] * 100), wd.get("backdrop_luma_ratio", 0) * 100))
        w("  The gameplay is shown WHOLE in the window (not cropped to fill the screen). Cut and motion measures below use the window only.")
    elif lay["kind"] == "letterbox":
        b = lay["bars"]
        w("- **Black bars**: top %.1f %%, bottom %.1f %%, left %.1f %%, right %.1f %% of the frame; the %s picture inside is what is measured." % (b["top"] * 100, b["bottom"] * 100, b["left"] * 100, b["right"] * 100, lay["orientation"]))
    else:
        if lay["orientation"] == "vertical":
            w("- **Full-screen vertical**: the whole 9:16 canvas is sharp gameplay, no window and no backdrop. A 16:9 recording fills it only by CROPPING to a third of its width, the standing zoom the user rejects (reference-style.md, \"Vertical frame\"): the skill builds a window over a blurred backdrop instead and says so in the report.")
        elif lay["orientation"] == "square":
            w("- **Square full frame** (1:1). Not built: the skill outputs 1920x1080 or 1080x1920.")
        else:
            w("- **Full frame**, %d x %d (aspect %.3f): the gameplay fills the canvas with its HUD." % (info["width"], info["height"], lay["aspect"]))
    w("- Frame rate %.2f; duration %.2f s." % (fps, info["duration"]))
    if spd.get("alternating_repeat", 0) >= 0.5:
        w("- Every other frame repeats (%.0f %% alternation): the picture runs at %.0f fps inside this file. The skill delivers 60 fps anyway." % (spd["alternating_repeat"] * 100, fps / 2))
    w("")
    w("## 2. Beat grid")
    if beat:
        mem = ", ".join("%.2f (strength %.2f, half-beats %.0f %%)" % m for m in beat.get("members", []))
        w("- Source: %s. **%.2f BPM**, first beat at %.4f s%s." % (r["beat_source"], beat["bpm"], beat["beat0"], "" if not beat.get("weak") else "  (WEAK fit: no clear drum pattern, do not trust)"))
        if mem:
            w("- Tempo candidates from `music_tempo.py`: %s. Both members are real readings: a clip of `x` beats at %.2f BPM is `x/2` beats at %.2f." % (mem, beat["bpm"], beat["bpm"] / 2))
        for n_ in beat.get("notes", []):
            w("- note: %s" % n_)
    else:
        w("- No beat grid: %s." % ("the reference has no sound; pass `--music <song>` to read the pacing in beats" if not info["has_audio"] else "music_tempo.py found no tempo in its sound"))
    if r.get("music"):
        m = r["music"]
        w("- Your song (`--music`): %.2f BPM, first beat %.4f s. Clip lengths for it: %s. Typical clip **%g beat** = %.3f s = %.1f frames at your tempo (the reference's own median clip: %.3f s%s). Distribution in your beats: %s." % (
            m["bpm"], m["beat0"], m["method"], m["clip_beats"], m["clip_seconds_at_that_tempo"], m["clip_frames_at_that_tempo"], m["reference_clip_seconds"],
            "" if abs(m["reference_tempo_over_yours"] - 1) < 0.05 else ", your song runs %.0f %% %s than the reference's tempo, so the same note values last %.0f %% %s" % (
                abs(m["reference_tempo_over_yours"] - 1) * 100, "slower" if m["reference_tempo_over_yours"] > 1 else "faster", abs(m["reference_tempo_over_yours"] - 1) * 100, "longer" if m["reference_tempo_over_yours"] > 1 else "shorter"),
            ", ".join("%s: %d" % kv for kv in m["clip_beats_dist"].items())))
    w("")
    w("## 3. Cuts")
    w("- **%d cuts** in %.1f s (%.1f per minute); first cut at %.2f s." % (P["cuts"], r["analysed_seconds"], P["cuts_per_minute"], P["first_cut_s"]))
    if P.get("clip_frames_median"):
        w("- Clip length: median %.0f frames (%.3f s)." % (P["clip_frames_median"], P["clip_seconds_median"]))
    if hist is not None and beat:
        bpm = beat["bpm"]
        per_f = 60.0 / bpm * fps
        d = P.get("clip_beats_dist_reference_tempo", P["clip_beats_dist"])
        w("- Clip lengths by note value (at %.2f BPM one beat = %.1f frames; the last clip is cut off by the end and left out):" % (bpm, per_f))
        w("")
        w("  | note value (beats) | clips | frames | note at %.2f BPM | note in the half-time reading (%.2f BPM) |" % (bpm, bpm / 2))
        w("  |---|---|---|---|---|")
        for k, v in d.items():
            if k == "other":
                w("  | other lengths | %d | %s | | |" % (v, ", ".join(str(x) for x in sorted(c["clip_frames"] for c in cuts[:-1] if c.get("clip_frames") and c.get("note") is None))[:90]))
            else:
                w("  | %s | %d | %.1f | %s | %s |" % (k, v, float(k) * per_f, NOTE.get(float(k), "?"), NOTE.get(float(k) / 2, "%g beat" % (float(k) / 2))))
        w("")
        if P.get("clip_beats"):
            rb = P.get("clip_beats_reference_tempo", P["clip_beats"])
            dref = P.get("clip_beats_dist_reference_tempo", d)
            w("- **Typical clip: %g beat** at the reference's %.2f BPM (%d of %d clips)." % (rb, bpm, dref.get(fmt_beats(rb), 0), sum(dref.values())))
    if al and al.get("step") is not None and not al.get("offset_note"):
        w("- **Cut to beat**: on the %g-beat lattice the cuts sit at a fixed distance from the grid (concentration %.2f; %.2f would be chance). Median offset **%+.0f ms = %+.2f beat = %+.1f frames** (negative = the cut comes BEFORE the hit), spread %.0f ms, 10-90 %% range %+.0f to %+.0f ms; %.0f %% of the cuts are within 40 ms of that offset." % (
            al["step"], al["concentration"], [t_ for t_ in al["lattice_tests"] if t_["step"] == al["step"]][0]["chance"], al["offset_ms_median"], al["offset_beats_median"], al["offset_frames_median"],
            al["offset_ms_std"], al["offset_ms_p10"], al["offset_ms_p90"], al["locked_share"] * 100))
        w("  A cut's time is the start of its first frame (frame / fps). The grid time is the measured onset of the hit (`music_grid.py`).")
    elif al and al.get("note"):
        w("- %s" % al["note"])
    elif al:
        w("- The cuts are NOT locked to the beat (concentration %s; chance about %.2f): cut times follow something else (a sound other than the grid, or no sound)." % (
            ", ".join("%.2f at %g beat" % (t_["concentration"], t_["step"]) for t_ in al["lattice_tests"]), al["lattice_tests"][0]["chance"]))
    if al and al.get("offset_note"):
        w("- %s" % al["offset_note"])
    if r.get("cuts_on"):
        co = r["cuts_on"]
        w("- **Cuts on which hits** (%d of %d cuts within 60 ms of a half-beat grid point): %s. Kicks / bass hits are %.0f %% of the half beats in this stretch; %.0f %% of the aligned cuts are on one. -> `CUTS_ON = \"%s\"`." % (
            co["aligned"], co["total"], ", ".join("%s %.0f %%" % (k, v * 100) for k, v in co["shares"].items()), co["kick_base_rate"] * 100, co["kick_share_of_aligned"] * 100, co["suggest"]))
    sec = P.get("sections")
    if sec and sec["rows"]:
        w("- Cut density per %s (start s: cuts%s): %s" % (sec["window"], ", mean clip beats" if beat else "", " | ".join("%.0f s: %d%s" % (row["start_s"], row["cuts"], (" (%.2f)" % row["mean_clip_beats"]) if row.get("mean_clip_beats") else "") for row in sec["rows"])))
    w("")
    w("## 4. Transitions around the cuts")
    tr = r["transitions"]
    names = dict(hard="hard cut (no blur)", whip="whip (directional blur)", zoom="zoom burst (radial blur)", roll="roll / rotated whip (blur without a direction)", blur="blur of no clear kind",
                 flash="white flash", dip="dip to black", unknown="unknown (clip under 5 frames)")
    for k, v in tr.items():
        w("- %s: %d (%.0f %%), mean confidence %.2f" % (names.get(k, k), v["count"], v["share"] * 100, v["mean_conf"]))
    w("- Blur-in kinds together: %.0f %% of the cuts%s. A whip is read horizontal when the horizontal gradient falls and the vertical one stays (`whip_axis` in the json); the sign of the move is not measurable." % (S["blur_in_share"] * 100 if S["blur_in_share"] is not None else 0,
                                                                                                                                                   " (a short blur-in inside a fast clip can read as hard: an upper bound for the hard cuts)"))
    bl = r["blips"]
    w("- Isolated flash / impact frames (1-3 frames that differ from the picture before and after, then it returns): %d (%.1f per minute)%s." % (bl["count"], bl["per_minute"], ": " + ", ".join("%s %d" % kv for kv in bl["kinds"].items()) if bl["count"] else ""))
    w("")
    w("## 5. Speed feel")
    if spd.get("typical") is None:
        w("- %s" % spd.get("note", "not measured"))
    else:
        w("- Slow motion (motion under 35 %% of the clips' typical speed for 5+ frames): **%.0f %% of the frames**%s. Freezes (identical frames): %.1f %% of the frames in %d runs, longest %d frames." % (
            spd["slow_share"] * 100, (", at about %.2fx the typical speed" % spd["rate"]) if spd.get("rate") else "", spd["freeze_share"] * 100, spd["freeze_runs"], spd["freeze_longest"]))
        w("  Caveats: a player standing still in real time reads as slow motion; the typical speed is the median over %d clips of each clip's own fast part." % spd["clips_used"])
    w("")
    w("## 6. Text overlays (no OCR)")
    if txt["words"]:
        w("- %s: **%d** word-sized appearances, on **%.0f %%** of the frames (a LOWER BOUND: see-through letters over busy footage are missed; measured 84 %% of the words on the worked example)." % (
            "Big words found" if r["suggested"]["words"] else "Rows of letter-like shapes found", txt["words"], txt["share"] * 100))
        w("- Letters about **%.0f %%** of the frame height, %.1f letters per word on average, centred at y = %.0f %% / x = %.0f %% of the frame, word width %.0f %% of the frame." % (txt["cap_height"] * 100, txt["letters"], txt["cy"] * 100, txt["cx"] * 100, txt["width"] * 100))
        if beat:
            per = 60.0 / beat["bpm"]
            w("- About %.2f word appearances per beat (%.1f beats between words); look at `centre_crops.jpg` for the fill (see-through or solid), colour and font." % (txt["words"] / (r["analysed_seconds"] / per), (r["analysed_seconds"] / per) / max(1, txt["words"])))
    else:
        w("- No big words found. (Small text and a corner watermark are not looked for; read `ref_sheets/` to be sure.)")
    if txt["words"] and not r["suggested"]["words"]:
        w("- Too few and too sparse to count as lyric words (the rule: 12 appearances on 10 % of the frames): vents, stairs and signs also look like letters to this detector. Decide on `centre_crops.jpg`.")
    w("")
    w("## 7. Colour and look")
    c = r["colour"]
    n_ = r["native"]
    w("- Saturation %.3f (worked example: %.3f), contrast spread %.1f levels (worked example %.1f), mean luma %.0f, warmth log2(R/B) %+.2f (worked example %+.2f), shadows %+.2f / lights %+.2f." % (c["saturation"], V3_BASE["saturation"], c["contrast_spread"], V3_BASE["contrast_spread"], c["luma_mean"], c["warmth"], V3_BASE["warmth"], c["shadow_warmth"], c["light_warmth"]))
    w("- Vignette: the corners are %.0f %% as bright as the middle (worked example: %.0f %%; 100 %% = none)." % (c["vignette_corner_ratio"] * 100, (1 - V3_BASE["vignette_amount"]) * 100))
    w("- Grain: noise sigma %s gray levels (worked example %.2f; compression noise counts); colour fringe (red against blue at the corners): %s thousandths of the half diagonal (worked example %.2f)." % (
        "%.2f" % n_["noise_sigma"] if n_.get("noise_sigma") is not None else "n/a", V3_BASE["noise_sigma"], "%.2f" % abs(n_["fringe"]) if n_.get("fringe") is not None else "n/a", V3_BASE["fringe"]))
    w("- Camera: shake %.3f %% of the width per frame RMS elsewhere, %s in the 10 frames after a cut (worked example %.3f); zoom rate %.3f %% per frame elsewhere, %s after a cut, %s in the 2 frames before a cut (worked example %.3f)." % (
        sg["shake_pct_width"] or 0, "%.3f %%" % sg["shake_pct_width_cuts"] if sg["shake_pct_width_cuts"] is not None else "n/a", V3_BASE["shake_pct_width"],
        sg["zoom_pct_frame"] or 0, "%.3f %%" % sg["zoom_pct_frame_cuts"] if sg["zoom_pct_frame_cuts"] is not None else "n/a", "%.3f %%" % sg["zoom_pct_frame_lean"] if sg["zoom_pct_frame_lean"] is not None else "n/a", V3_BASE["zoom_pct_frame"]))
    w("")
    w("## 8. Intro and ending")
    first = P["first_cut_s"]
    if first >= 2.0:
        w("- Intro: no hard cut for the first %.2f s%s: a slow opening, not the cut rhythm of the rest (any change of view inside it is a move of the camera or a soft transition; look at `start_3s.jpg`)." % (first, " (%d beats)" % S["intro_beats"] if S.get("intro_beats") else ""))
    else:
        w("- No intro: the first cut comes at %.2f s." % first)
    e = r["ending"]
    if e["kind"] == "cut":
        w("- Ending: **cut** (the last frames are as bright as the rest: final luma %.0f, base %.0f)." % (e["final_luma"], e["base_luma"]))
    elif e["kind"] == "fade to white":
        w("- Ending: **fade to white** from %.2f s." % e["start"])
    else:
        w("- Ending: **%s** from %.2f s over %.2f s (final luma %.0f of %.0f)%s." % (e["kind"], e["start"], e["seconds"], e["final_luma"], e["base_luma"], (": the dark areas reach black %.2f s before the highlights" % e["p10_to_p90_lag"]) if e["kind"] == "luma fade" else ""))
    w("")
    w("## 9. Images to read before designing")
    for p, cap in r["sheets"]:
        w("- `%s`: %s" % (p.replace("\\", "/"), cap))
    if not r["sheets"]:
        w("- (sheets skipped)")
    w("")
    w("## SUGGESTED SETTINGS for timeline.py")
    w("")
    w("A starting point from measurements; the user's words outrank it (SKILL.md, \"Edit options\").")
    w("")
    w("```python")
    w("FRAME = %r%s" % (S["FRAME"], "      # the reference puts the gameplay in a window over a backdrop: that is what FRAME = \"vertical\" builds" if lay["kind"] == "window" else ""))
    w("CUTS_ON = %s" % (repr(S["CUTS_ON"]) if S["CUTS_ON"] else "\"bass\"   # not measured (no usable sound): default"))
    if S["clip_beats"]:
        w("# typical clip: %g beat%s%s" % (S["clip_beats"], " at the tempo of your song" if r.get("music") else " at the reference's %.2f BPM" % beat["bpm"] if beat else "",
                                          " (reference tempo: %g)" % S["clip_beats_reference_tempo"] if r.get("music") and S["clip_beats_reference_tempo"] else ""))
    w("# blur-in cuts: %.0f %% of the cuts; hard cuts the rest. Measured mix as a cycle for _FX (8 takes):" % ((S["blur_in_share"] or 0) * 100))
    w("_FX = %s" % repr(S["FX_cycle"]))
    w("LOOK = %s      # nearest preset: %s" % (repr(S["LOOK"]) if S["LOOK"] else "{}", S["LOOK_preset"]))
    if S["slow_motion"]:
        w("# slow motion: yes, about %.2fx -> post(... rate=%.2f)" % (r["speed"].get("rate") or 0, S["slow_rate"] or 0.16))
    else:
        w("# slow motion: little or none measured -> real time after the kill (post() with rate 1, or short)")
    w("# intro: %s" % ("%d beats before the first cut (R0 = -%d), slow shots" % (S["intro_beats"], S["intro_beats"]) if S["intro_beats"] else "none"))
    w("# words: %s" % ("yes (big words on about %.0f %% of the frames, caps about %.0f %% of the frame height)" % (txt["share"] * 100, txt["cap_height"] * 100) if S["words"] else
                       ("probably no: %d rows of letter-like shapes, but scenery gives those too: look at centre_crops.jpg" % txt["words"] if S.get("words_check") else "no")))
    w("# ending: %s" % (("luma fade over the last %.1f s -> LUMA_FADE" % e["seconds"]) if e["kind"] == "luma fade" else ("fade to black over the last %.1f s" % e["seconds"] if e["kind"] == "fade to black" else e["kind"])))
    w("```")
    for n_ in suggest_look_notes(r):
        w("- LOOK: %s" % n_)
    w("")
    w("## Limits (read before trusting a number)")
    for line in LIMITS:
        w("- %s" % line)
    w("")
    w("Time: %s s (%.2f s per minute of video)." % (", ".join("%s %.1f" % kv for kv in r["timing_seconds"].items()), r["timing_seconds"]["total"] / max(r["analysed_seconds"], 1) * 60))
    return "\n".join(L) + "\n"


def suggest_look_notes(r):
    c = r["colour"]
    B = V3_BASE
    return ["saturation %.2fx, contrast %.2fx, vignette %.2fx of the worked example's measures; the footage's own colour moves them, so this is a heuristic: compare enlarged stills of the reference and of the first render (verification.md)" % (
        c["saturation"] / B["saturation"], c["contrast_spread"] / B["contrast_spread"], max(0.0, 1 - c["vignette_corner_ratio"]) / max(B["vignette_amount"], 1e-3))]


LIMITS = [
    "Hard cuts are found well (57 of 57 on the worked example, none missed, 3 extra, every one within 1 frame of where it was built). Soft transitions that move BOTH clips (whips through, spins, dissolves, as in the house style) are mostly missed (5 of 13 on the house example): the cut list is then a lower bound.",
    "The kind of a blur-in was right for 54 of the 57 cuts of the worked example (30 whips, 15 zoom bursts, 12 rolls as built). A weak blur-in inside a fast clip can read as hard, so the hard-cut share is an upper bound. The sign of a whip is not measurable.",
    "Text is found by letter shapes (no OCR): 66 of the 79 words of the worked example (84 %), 91 % of the finds inside a word's time; the words are never read and neither is whether the letters are see-through or solid: read `centre_crops.jpg` (a mistake made once on small tiles). Scenery (vents, stairs) gives a few false rows: a handful is not text. Letter height reads 10 to 30 % low on see-through letters.",
    "Slow motion is motion magnitude against the clips' own typical speed: a player standing still looks like slow motion.",
    "Colour, shake and zoom numbers are relative to the worked example and the footage's own colour and camera work move them; the LOOK is a first guess, to be checked on enlarged stills of the reference and of the first render.",
    "The reference's sound is used as it is: a reference whose audio is not the song (voice-over, other music) has another grid than your song's. Without sound the tempo is fitted to the cut times (half / double ambiguity) and no cut-to-beat offset can be read.",
]

if __name__ == "__main__":
    main()
