"""Read a reference edit by measurement, before designing ("faz com a MESMA EDICAO desse vídeo").

    python ref_analyze.py <reference video> [--music <the song you will use>] [--out DIR] [--max-seconds N] [--no-sheets]

Writes in DIR (default: the current folder):
    ref_notes.md     the findings in words, ending with SUGGESTED SETTINGS for timeline.py
    ref_notes.json   the same as numbers (cuts with their lattice lines and transition kinds, pacing, text, colour, ...) and the block
                     `adopt` (version 2): the numbers draft_ref_timeline.py takes from the reference (see below)
    ref_sheets/      images to READ afterwards: the whole video at 4 fps, every frame around three cuts, enlarged centre
                     crops, the first and the last seconds

What it measures (reference-style.md, "Reading the reference"): orientation and layout (full frame, window over a blurred
backdrop, black bars); every cut (the FIRST frame of each change of picture, 2 frames apart at the least) and the lattice of
1, 1/2, 1/4 or 1/8 beat they sit on (step in seconds, offset in output frames, the gaps between cuts in lattice steps: the reference's
rhythm); the beat grid of the reference's own sound (music_tempo.py + music_grid.py, or your song's own grid when the reference's sound
IS your song: cross-correlated, `same_song.offset_s`); how many frames its cuts (`cut_lead_frames`) and the pops / muzzle flashes of its KILLS
(`hit_lead_frames`, kills only: flash frames at cuts are cut evidence) come before the drum attack of their lattice line (attacks measured on its own sound, the skill's one attack definition); its kills (the
kill feed, 1920x1080 Valorant: rate, gaps in steps, lock to the lattice); how the cuts are made (hard, whip, zoom burst, roll, flash,
dip) with a confidence; slow motion and freezes; big words (no OCR); colour, vignette, grain, colour fringe; shake and zoom around the
cuts; the ending (fade seconds and black seconds apart).
`--music` is the song of YOUR edit: the clip lengths are then also given for its tempo, and it is tested for being the reference's own
sound. A reference without sound is read in seconds and frames only (with `--music` the grid is fitted to the cuts: offsets are then
meaningless and said so).

`adopt` keys: version, frame ("horizontal" / "vertical", or null when the reference is square: the skill builds neither), layout ("full" /
"window" / "letterbox": the drafter is told when the measured layout is a window the frame it builds does not reproduce), same_song{offset_s, ncc,
second_best} | null, lattice{step_s, step_beats_ref, ref_bpm_read, locked_R, offset_frames, offset_s, residual_ms, locked_share} | null,
cut_gaps_steps{steps: count} | null, cut_rate_per_s (null with fewer than 5 cuts or a window under 1 s), kills{per_s, count, gap_steps_median,
lock_R, lock_steps} | null (per_s null on the same rule: the span from the first cut collapses when the detector finds no cut), transitions{hard,
whip, zoom, roll, [flash, dip]} | null (null = no cut kind was measured), slow{share, rate}, intro_steps, ending{kind, fade_s, black_s, dim_s},
look{...}, look_preset, words{cap_height, centre} | null (only when the detection is confident), cut_lead_frames (int 0..3 | null) +
cut_lead_note (why it was not measured), hit_lead_frames (int 0..3 | null: null = not measured from kills, the draft keeps its default) +
hit_lead_note (the numbers seen when null). Positions and lengths are in lattice steps, never in seconds of the reference; null = not measured.

Every number is a measurement of pixels and sound, not a judgement: the notes say where it is a lower bound or a guess. Needs the
project venv (numpy, opencv, scipy) and ffmpeg (ff.py). About 40-50 s per 33 s clip on this skill's PC (the kill feed and the drum
attacks run beside the picture work), longer while a game or a render runs; a reference that makes ffmpeg print decode errors no longer
hangs it."""
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
import beat_hits as bh  # noqa: E402  (refmeasure put the scripts folder on sys.path): the skill's one attack definition and its class biases

# What the same measures read on the worked example (reference-style edit, LOOK absent = "padrao"): the yardstick for the LOOK
# suggestion, because the colour of the footage itself moves the raw numbers. Measured with this script on the worked example's render.
V3_BASE = dict(saturation=0.4245, contrast_spread=143.8, vignette_amount=0.1711, noise_sigma=0.124, fringe=1.207, shake_pct_width=0.311, zoom_pct_frame=0.691,
               blur_mean=0.445, blips_per_min=0.0, warmth=0.4187, shadow_warmth=0.4552, light_warmth=0.4177)
SNAP = [0.125, 0.25, 0.375, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0]
NOTE = {0.125: "1/32", 0.25: "1/16", 0.375: "dotted 1/16", 0.5: "1/8", 0.75: "dotted 1/8", 1.0: "1/4", 1.5: "dotted 1/4", 2.0: "1/2", 3.0: "dotted 1/2",
        4.0: "whole", 6.0: "1.5 bars", 8.0: "2 bars"}
BLUR_KINDS = ("whip", "zoom", "roll", "blur")
# The edit is always 60 fps and a reference is whatever its upload is (24, 25, 29.97, 30, 60, 120 ...). A lead measured on the reference
# in ms must therefore become frames of the OUTPUT before the drafter writes it into CUT_LEAD / HIT_LEAD, which vis() applies as whole
# output frames: in the reference's own frames a 30 fps one halves the lead (2 frames read as 1) and a 25 fps one loses it (1 -> 0).
OUT_FPS = 60.0


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
LATTICES = (1.0, 0.5, 0.25, 0.125)                   # beats; the lattice of the reference's rhythm is the coarsest of these that the cuts sit on


def align_cuts(cuts, fps, bpm, beat0):
    """Each cut's position on the beat grid, by circular statistics: for a lattice of 1, 1/2, 1/4 or 1/8 beat the cut phases are averaged on
    the circle; a mean resultant length R >= max(0.3, 3 / sqrt(cuts)) (a Rayleigh test: chance gives about 1 / sqrt(cuts)) means the cuts sit at
    a FIXED distance from the lattice, and the mean phase is that distance (negative = the cut comes before the line). Cuts that sit on a
    coarse lattice also sit on the finer ones, so the COARSEST accepted lattice whose R is within 15 % of the best finer one is used, among
    the lattices whose offset is plausible (a cut leads or trails its line by at most 80 ms = 5 frames: a funk reference reads 1/2 beat at
    -102 ms but 1/4 beat at +48 ms, the same cuts).
    The offset is reported in seconds, ms and OUTPUT FRAMES; the lattice step in seconds (the unit the drafter maps to the user's song);
    the gaps between consecutive cuts in lattice steps (the reference's rhythm template: 72 of 73 gaps of a test reference are whole
    steps); `step_idx` / `line_t` of each cut = its lattice line.
    -> dict(step (beats, None when not locked), step_s, offset_s_median, offset_frames_median, residual_ms, gaps_steps, ...);
    fills cut['beat'] (beats from the grid's first beat), cut['offset_ms'], cut['step_idx'], cut['line_t']."""
    per = 60.0 / bpm
    ts = np.array([c["frame"] / fps for c in cuts])
    if len(ts) < 5:
        return dict(step=None, note="fewer than 5 cuts: no alignment statistics")
    thr = max(0.3, 3.0 / math.sqrt(len(ts)))
    rows = []
    for step in LATTICES:
        lat = per * step
        z = np.mean(np.exp(2j * np.pi * (ts - beat0) / lat))
        R, mu = float(abs(z)), float(np.angle(z) / (2 * np.pi))
        rows.append(dict(step=step, concentration=round(R, 3), chance=round(float(1 / math.sqrt(len(ts))), 3), threshold=round(thr, 3), accepted=bool(R >= thr),
                         offset_ms=round(mu * lat * 1000, 1), mu=mu))
    chosen = None
    acc = [r for r in rows if r["accepted"]]
    acc = [r for r in acc if abs(r["offset_ms"]) <= 80.0] or acc
    for i, r in enumerate(acc):                      # coarse -> fine
        if r["concentration"] >= 0.85 * max([q["concentration"] for q in acc[i:]]):
            chosen = r
            break
    if chosen:
        step, mu, R = chosen["step"], chosen["mu"], chosen["concentration"]
    else:
        step, mu, R = 0.5, 0.0, 0.0
    lat = per * step
    ph = (ts - beat0) / lat
    idx = np.round(ph - mu).astype(int)
    off = (ph - idx) * lat * 1000                           # distance to the lattice line, around the mean offset
    for c, o, t, k in zip(cuts, off, ts, idx):
        c["beat"] = round(float((t - beat0) / per), 3)
        c["offset_ms"] = round(float(o), 1)
        c["step_idx"] = int(k)
        c["line_t"] = round(float(beat0 + k * lat), 4)
    for r in rows:
        r.pop("mu")
    res = dict(step=step if chosen else None, report_step=step, lattice_tests=rows, concentration=round(R, 3), threshold=round(thr, 3))
    mu_ms = mu * lat * 1000
    tol = min(40.0, 0.25 * lat * 1000)                      # 40 ms, or a quarter of the step on a fine lattice
    lock = np.abs(off - mu_ms) <= tol
    res["locked_share"] = round(float(lock.mean()), 3)
    if chosen and lock.sum() >= 3:
        o = off[lock]
        res.update(step_s=round(float(lat), 4), offset_ms_median=round(float(np.median(o)), 1), offset_ms_mean=round(float(o.mean()), 1), offset_ms_std=round(float(o.std()), 1),
                   offset_ms_p10=round(float(np.percentile(o, 10)), 1), offset_ms_p90=round(float(np.percentile(o, 90)), 1))
        res["offset_s_median"] = round(res["offset_ms_median"] / 1000.0, 5)
        res["offset_frames_median"] = round(res["offset_ms_median"] * OUT_FPS / 1000, 2)
        res["offset_beats_median"] = round(res["offset_ms_median"] / (per * 1000), 3)
        res["residual_ms"] = round(float(o.std()), 1)
        gaps = np.diff(idx)
        res["gaps_steps"] = {str(int(k)): int(v) for k, v in sorted(collections.Counter(gaps.tolist()).items()) if k >= 1}
        res["gaps_same_step"] = int(np.sum(gaps < 1))           # two cuts on one line (flash cuts 2-3 frames apart): no rhythm step
        res["gaps_whole_share"] = round(float(np.mean(np.abs(np.diff(ts) - gaps * lat) <= max(0.03, 0.2 * lat))), 3)
    return res


STRONG_RISE = 1.0                                   # ln units over 6 ms (the envelope at least 2.7x): the strong half of the kick / snare attacks; the leads below read the same (38.3 ms) from 0.8 to 1.4


def _strong_attacks(attacks, min_rise=STRONG_RISE, bands=("low", "mid")):
    a = [x for x in (attacks or []) if x["band"] in bands and x["rise"] >= min_rise]
    return np.array([x["t"] for x in a]), np.array([x["rise"] for x in a])


def _lead_stats(leads_ms, fps):
    """Lead statistics of a list of leads in ms. `fps` is the REFERENCE's rate and is used only where the reference's own frames are the
    right unit (how tightly the leads cluster: 1.5 frames of the reference). `median_frames` is in OUTPUT frames, the unit CUT_LEAD /
    HIT_LEAD are written and applied in (OUT_FPS), whatever the reference was recorded at."""
    x = np.array(leads_ms, float)
    med = float(np.median(x))
    return dict(n=int(len(x)), median_ms=round(med, 1), mean_ms=round(float(x.mean()), 1), std_ms=round(float(x.std()), 1),
                median_frames=round(med * OUT_FPS / 1000.0, 2),
                stable_share=round(float(np.mean(np.abs(x - med) <= 1.5 * 1000.0 / fps)), 2))


def cut_lead(cuts, attacks, fps, al):
    """How many frames the reference's cuts come BEFORE the drum attack of their lattice line (the moment of the music the cut belongs to).
    For every cut: the strongest kick / snare attack (`drum_attacks`, rise >= STRONG_RISE) within 45 ms of its lattice line; lead = attack - cut
    (positive = the picture comes first). Needs a locked lattice on the reference's own sound, 8 cuts with an attack, and 55 % of the leads
    within 1.5 frames of their median (a convention, not scatter). -> dict(frames (rounded, 0..3), n, median_ms, ...) or dict(frames=None, why=...)."""
    if not attacks or al.get("step") is None or "step_s" not in al:
        return dict(frames=None, why="no locked lattice on the reference's own sound, or no sound")
    ta, lv = _strong_attacks(attacks)
    if not len(ta):
        return dict(frames=None, why="no clear kick / snare attacks in the reference's sound")
    leads = []
    for c in cuts:
        sel = np.nonzero(np.abs(ta - c["line_t"]) <= 0.045)[0]
        if len(sel):
            leads.append((ta[sel[int(np.argmax(lv[sel]))]] - c["frame"] / fps) * 1000.0)
    if len(leads) < 8:
        return dict(frames=None, why="only %d cuts have a kick / snare attack on their lattice line (8 needed)" % len(leads))
    st = _lead_stats(leads, fps)
    if st["stable_share"] < 0.55:
        st.update(frames=None, why="the leads are scattered (%.0f %% within 1.5 frames of their median): no stable convention" % (st["stable_share"] * 100))
        return st
    st["frames"] = int(max(0, min(3, round(st["median_frames"]))))
    return st


def hit_lead(sources, attacks, fps, al, beat0):
    """How many frames the reference's KILL accents (the pop / muzzle flash of a kill) come BEFORE the drum attack they belong to. `sources` =
    [(name, [(frame, line_t or None)])]; the drafter's call passes only the pops tied to a kill of the kill feed: flash frames at cuts are cut
    evidence (they feed `cut_lead`) and never set the kill lead. Each accent is matched to the strongest kick / snare attack within 30 ms of
    the first lattice line after it (with no lattice: within -3..+6 frames); lead = attack - accent. A source is used when 6 of its accents
    have an attack and 55 % of those leads are within 1.5 frames of their median.
    -> dict(frames (rounded, 0..3), n, median_ms, source, tried) or dict(frames=None, why=..., tried)."""
    if not attacks:
        return dict(frames=None, why="the reference has no sound")
    ta, lv = _strong_attacks(attacks)
    if not len(ta):
        return dict(frames=None, why="no clear kick / snare attacks in the reference's sound")
    lat = al.get("step_s") if (al and al.get("step") is not None) else None
    tried = []
    for name, items in sources:
        leads = []
        for f, line in items:
            t = f / fps
            if lat and line is None:
                line = beat0 + math.ceil((t - 3.0 / fps - beat0) / lat) * lat
            sel = np.nonzero(np.abs(ta - line) <= 0.03)[0] if line is not None else np.nonzero((ta - t >= -3.0 / fps) & (ta - t <= 6.0 / fps))[0]
            if len(sel):
                leads.append((ta[sel[int(np.argmax(lv[sel]))]] - t) * 1000.0)
        if len(leads) < 6:
            tried.append("%s: %d accents, %d with an attack (6 needed)" % (name, len(items), len(leads)))
            continue
        st = _lead_stats(leads, fps)
        if st["stable_share"] < 0.55:
            tried.append("%s: %d accents, leads scattered (median %+.0f ms, std %.0f ms, %.0f %% within 1.5 frames of it)" % (name, len(leads), st["median_ms"], st["std_ms"], st["stable_share"] * 100))
            continue
        st.update(source=name, accents=len(items), frames=int(max(0, min(3, round(st["median_frames"])))), tried=tried)
        return st
    return dict(frames=None, why="; ".join(tried) or "no accent frames (flashes, pops) in the reference", tried=tried)


def kills_block(events, pops, cuts, fps, lat_s, beat0, t_span):
    """The reference's kills from its kill feed (`detect_kills.scan` events: the frame a kill row appears, about 8 frames after the shot, a
    constant lag): de-duplicated (rows < 9 frames apart are one kill), each with the lattice step of the cut lattice, the gap to the previous kill
    in steps and its pop frame (the first isolated luma pop from 25 frames before the row to 3 after it, else None).
    per_s = kills / the span from the first cut to the end of the picture (None with fewer than 5 cuts or a window under 1 s: with no cut
    the span collapses and the rate is meaningless); lock_R = circular concentration of the kill times on the lattice (the constant feed lag
    only shifts the phase). -> dict or None."""
    fe = []
    for e in events:
        if not fe or e["frame"] - fe[-1] >= 9:
            fe.append(int(e["frame"]))
    if not fe:
        return None
    rows = []
    for f in fe:
        p = [q for q in pops if f - 25 <= q <= f + 3]
        rows.append(dict(frame=f, t=round(f / fps, 3), pop_frame=int(p[0]) if p else None))
    ts = np.array([r["t"] for r in rows])
    out = dict(count=len(rows), per_s=round(len(rows) / max(t_span, 1e-6), 3) if (len(cuts) >= 5 and t_span > 1.0) else None, kills=rows)
    if len(ts) >= 2:
        out["gap_s_median"] = round(float(np.median(np.diff(ts))), 3)
    if lat_s:
        ph = (ts - beat0) / lat_s
        for r, k in zip(rows, ph):
            r["step"] = round(float(k), 2)
        if len(ts) >= 2:
            out["gap_steps_median"] = round(float(np.median(np.diff(ts))) / lat_s, 2)
        if len(ts) >= 5:
            by = {m_: float(abs(np.mean(np.exp(2j * np.pi * ph / m_)))) for m_ in (1, 2, 4)}       # kills often sit on every 2nd or 4th line
            best = max(by, key=lambda m_: by[m_])
            out["lock_R"] = round(by[best], 3)
            out["lock_steps"] = best
            out["lock_R_by_steps"] = {str(m_): round(v, 3) for m_, v in by.items()}
            out["lock_chance"] = round(1.0 / math.sqrt(len(ts)), 3)
    return out


def kill_feed(src, info):
    """The reference's kill feed: `detect_kills.scan` (kill rows in the top-right corner of a 1920x1080 frame) on a temp copy of its result.
    -> (events [dict(frame, t, ...)], note). Any other game / resolution simply finds nothing."""
    import tempfile
    import detect_kills as dk
    with tempfile.TemporaryDirectory() as td:
        try:
            dk.scan(src, td)
            p = os.path.join(td, os.path.splitext(os.path.basename(src))[0] + ".json")
            ev = json.load(open(p, encoding="utf-8"))["events"] if os.path.exists(p) else []
        except Exception as e:                    # a broken scan must not stop the analysis: the kills are reported as not measured
            return [], "kill feed scan failed: %s" % str(e)[:160]
    return ev, ("" if ev else "no kill feed rows found (detect_kills.py reads the Valorant feed of a 1920x1080 frame)")


def text_sane(txt):
    """Is a row of letter-like shapes a word measurement worth adopting? The cap height must be word-sized (4 to 30 % of the frame height:
    a bigger row is a sign or a HUD bar, a smaller one a texture) and the row's centre inside the middle of the frame (25..75 % across,
    20..80 % down: the user's words sit centred; a row at the edge is scenery). A few rows also come from vents and stairs, so the caller
    still requires the confident count (12+ rows over 10 % of the frames); a trait that was not measured is None in `adopt`, never a guess."""
    cap, cx, cy = txt.get("cap_height"), txt.get("cx"), txt.get("cy")
    return cap is not None and 0.04 <= cap <= 0.30 and 0.25 <= cx <= 0.75 and 0.20 <= cy <= 0.80


def adopt_frame(lay):
    """The FRAME the drafter builds: the reference's canvas orientation, or None for a square one. The skill outputs 1920x1080 or 1080x1920
    only, so a square reference must not be adopted as horizontal (that silently filled a 1:1 reference into 16:9, item 8)."""
    return lay.get("orientation") if lay.get("orientation") in ("horizontal", "vertical") else None


def build_adopt(frame, same, al, own_sound, bpm, cuts, t_first, t_end, kb, spd, look, look_preset, txt, words_found, end, cl, hl, layout=None):
    """ref_notes.json["adopt"], version 2: the block the drafter reads (reference-style.md, "What the draft takes from the reference").
    Every position or length of the reference is in LATTICE STEPS of its own measured grid (the drafter turns them into the user's song by the
    step, never by seconds); only latency-like constants stay in frames or seconds. A trait that was not measured is None, never a guess:
    no classified cut gives transitions=None (not a zero pattern), the rates need 5 cuts and a window over 1 s (with no cut t_first = the
    duration and the span collapses to 0), the words need a confident, word-like detection (text_sane). `layout` is the measured layout kind
    so the drafter can say when the frame it builds does not reproduce a window over a backdrop."""
    locked = al is not None and al.get("step") is not None and "step_s" in al
    kinds = collections.Counter(c["kind"] for c in cuts if c.get("kind") not in (None, "unknown"))
    kinds["roll"] += kinds.pop("blur", 0)
    tot = sum(kinds.values())                  # NOT max(1, ...) and not `if kinds`: the line above adds "roll" even when it is 0
    trans = None
    if tot:                                    # every cut "unknown": no transition kind was measured (the drafter only reads a real pattern)
        trans = {k: round(kinds.get(k, 0) / tot, 3) for k in ("hard", "whip", "zoom", "roll")}
        for k in ("flash", "dip"):
            if kinds.get(k):
                trans[k] = round(kinds[k] / tot, 3)
    span = max(t_end - t_first, 1e-6)
    # 0-1 cuts: t_first falls back to the duration, so the span collapses and a "per second" rate would be ~1e6 (the drafter printed it)
    window_ok = len(cuts) >= 5 and span > 1.0
    adopt = dict(
        version=2,
        frame=frame,
        layout=layout,
        same_song=dict(offset_s=same["offset_s"] if (same and same.get("same")) else None, ncc=(same or {}).get("ncc"), second_best=(same or {}).get("second")),
        lattice=None, cut_gaps_steps=None, intro_steps=None,
        cut_rate_per_s=round(len(cuts) / span, 2) if window_ok else None,
        kills=None,
        transitions=trans,
        slow=dict(share=spd.get("slow_share"), rate=spd.get("rate")),
        ending=dict(kind=end["kind"], fade_s=end.get("fade_s"), black_s=end.get("black_s"), dim_s=end.get("dim_s")),
        look=look, look_preset=look_preset,
        words=dict(cap_height=txt["cap_height"], centre=[txt["cx"], txt["cy"]]) if (words_found and text_sane(txt)) else None,
        cut_lead_frames=cl.get("frames") if cl else None,
        cut_lead_note=(cl.get("why") if cl else None),
        hit_lead_frames=hl.get("frames") if hl else None,
        hit_lead_note=(hl.get("note") if hl else None))
    if locked:
        adopt["lattice"] = dict(step_s=al["step_s"], step_beats_ref=al["step"], ref_bpm_read=bpm, locked_R=al["concentration"],
                                offset_frames=al["offset_frames_median"] if own_sound else None, offset_s=al["offset_s_median"] if own_sound else None,
                                residual_ms=al["residual_ms"], locked_share=al["locked_share"])
        adopt["cut_gaps_steps"] = al["gaps_steps"]
        adopt["intro_steps"] = int(round((t_first - (al["offset_s_median"] if own_sound else 0.0)) / al["step_s"])) if t_first >= 2.0 else 0
    if kb:
        adopt["kills"] = dict(per_s=round(kb["count"] / span, 2) if window_ok else None, count=kb["count"], gap_steps_median=kb.get("gap_steps_median"),
                              lock_R=kb.get("lock_R"), lock_steps=kb.get("lock_steps"))
    return adopt


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
    ap.add_argument("--music", help="the song of YOUR edit (clip lengths are then also given for its tempo; when the reference's sound IS this song, its own grid is used and `same_song.offset_s` says where)")
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
    ex = ThreadPoolExecutor(max_workers=5)           # the sound, the words, the colour, the kill feed and the drum attacks run beside the picture work
    av = info.get("av_offset_s", 0.0)                # where the sound starts against the picture (0.000 in every reference seen): the beat grid,
    #                                                  the pulses and same_song live on the sound's clock, the cuts and attacks on the video's:
    #                                                  the same offset must be applied to all of them or every lattice phase shifts by it

    def audio_job():
        beat_, err_, song_, serr_, pul_, same_ = None, None, None, None, None, None
        if info["has_audio"]:
            beat_ = rm.beat_grid(src, 0.0, min(info["duration"], a.max_seconds), av)
            if "error" in beat_:
                err_, beat_ = beat_["error"], None
        if a.music:
            song_ = rm.beat_grid(a.music)
            if "error" in song_:
                serr_, song_ = song_["error"], None
            if info["has_audio"]:
                same_ = rm.same_song(src, a.music, offset_s=av)
        if beat_:
            pul_ = rm.audio_pulses(src, beat_["bpm"], beat_["beat0"], 0.5, av)
        return beat_, err_, song_, serr_, pul_, same_
    f_audio = ex.submit(audio_job)
    f_att = ex.submit(rm.drum_attacks, src, a.max_seconds, info.get("av_offset_s", 0.0)) if info["has_audio"] else None
    f_kills = ex.submit(kill_feed, src, info) if (info["width"] >= 1900 and info["height"] >= 1000) else None
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
    cuts = rm.detect_cuts(L, R, S)
    rm.classify_transitions(S, L, cuts, fps)
    blips = rm.find_blips(Th, L)
    pops = rm.find_pops(G, [c["frame"] for c in cuts])
    lap("cuts", t)

    # ---- beat grid
    t = time.time()
    beat, beat_err, song, song_err, pul, same = f_audio.result()
    attacks = f_att.result() if f_att else []
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
    if same and same["same"] and song is not None:
        # the reference's sound IS the song: the song's own (cleaner) grid, moved to the reference's clock, replaces the tempo family reading
        per_s = 60.0 / song["bpm"]
        beat = dict(bpm=song["bpm"], beat0=round(float((song["beat0"] - same["offset_s"]) % per_s), 4), members=song["members"], weak=bool(song.get("weak")), grid_adequate=song.get("grid_adequate", True),
                    notes=["the reference's sound is your song (cross-correlation %.2f, second best %.2f): its own grid on the reference's clock, song time = reference time %+.4f s" % (same["ncc"], same["second"], same["offset_s"])] + list(song.get("notes", [])))
        grid_source = "the reference's own sound (= your song)"
        pul = rm.audio_pulses(src, beat["bpm"], beat["beat0"], 0.5, av)
    lap("beat grid (wait)", t)
    bpm = beat["bpm"] if beat else None
    beat0 = beat["beat0"] if beat else 0.0
    own_sound = bool(grid_source) and grid_source.startswith("the reference's own sound")

    for c in cuts:
        c["t"] = round(c["frame"] / fps, 3)
    al = hist = None
    if bpm:
        al = align_cuts(cuts, fps, bpm, beat0)
        if not own_sound:
            al["offset_note"] = "the grid was fitted to the cuts, so the offsets are meaningless"
            for c in cuts:
                c.pop("offset_ms", None)
        hist = clip_lengths(cuts, fps, bpm)
    cuts_on = None
    if beat and own_sound and pul is not None and len(cuts) >= 5:
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
    kf, kf_note = f_kills.result() if f_kills else ([], "the kill feed is read on 1920x1080 references only")
    ex.shutdown()
    lap("text, colour, ending (wait)", t)

    # ---- assembled facts
    kinds = kinds_table(cuts)
    blur_cuts = [c for c in cuts if c.get("kind") in BLUR_KINDS]
    blur_share = len(blur_cuts) / max(1, len([c for c in cuts if c.get("kind") != "unknown"]))
    blur_mean = float(np.mean([c["blur"] for c in blur_cuts])) if blur_cuts else None
    first_cut_t = cuts[0]["frame"] / fps if cuts else dur
    t_end = end["start"] if (end["kind"] in ("luma fade", "fade to black") and end.get("start")) else dur       # the cut rhythm ends where the ending fade starts
    lat_s = (al or {}).get("step_s") or ((60.0 / bpm / 2) if (bpm and own_sound) else None)
    kb = kills_block(kf, pops, cuts, fps, lat_s, beat0, max(t_end - first_cut_t, 1e-6)) if kf else None
    kill_pops = [r["pop_frame"] for r in kb["kills"] if r["pop_frame"] is not None] if kb else []
    cl = cut_lead(cuts, attacks, fps, al) if (al and own_sound) else dict(frames=None, why="no beat grid of the reference's own sound")
    line_of = {c["frame"]: c.get("line_t") for c in cuts} if own_sound else {}
    nk = len(kb["kills"]) if kb else 0
    # hit_lead = the KILL moments only (pops / flashes tied to a kill-feed row); flash frames at cuts are cut evidence and only reported
    hl = hit_lead([("kill pops", [(f, None) for f in kill_pops])], attacks, fps, al if own_sound else None, beat0) if attacks else dict(frames=None, why="the reference has no sound")
    cfl = hit_lead([("flash frames at cuts", [(fj, line_of.get(fc)) for fc, fj in rm.find_cut_flashes(G, [c["frame"] for c in cuts])])], attacks, fps, al if own_sound else None, beat0) if attacks else {}
    hl["kills_with_pop"], hl["kills"] = len(kill_pops), nk
    if cfl.get("median_frames") is not None:
        hl["cut_flash"] = dict(median_frames=cfl["median_frames"], n=cfl["n"], median_ms=cfl["median_ms"], std_ms=cfl["std_ms"], stable_share=cfl["stable_share"])
    if hl.get("frames") is None:
        cf = hl.get("cut_flash")
        hl["note"] = "not measured from kills: %s%s" % (
            ("%d of %d kills have a pop / flash" % (len(kill_pops), nk)) if nk else ("no kill feed read (%s)" % (kf_note or "no kills")),
            ("; cut-flash lead (cut evidence, NOT used for kills): median %.1f frames, n=%d" % (cf["median_frames"], cf["n"])) if cf else
            ("; cut-flash lead (cut evidence, NOT used for kills): %s" % cfl["why"] if cfl.get("why") else ""))
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
    frame_s = adopt_frame(lay)                       # the reference's orientation, None for a square one (item 8: the skill builds neither 1:1)
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
    adopt = build_adopt(frame_s, same, al, own_sound, bpm, cuts, first_cut_t, t_end, kb, spd, look, suggested["LOOK_preset"], txt, bool(words_yes), end, cl, hl, lay["kind"])
    if al and al.get("gaps_steps") is not None:
        pacing["cut_gaps_steps"] = al["gaps_steps"]
        pacing["cut_lattice_step_s"] = al["step_s"]
        pacing["cut_lattice_residual_ms"] = al["residual_ms"]

    total = time.time() - T0
    tm["total"] = round(total, 1)
    result = dict(
        file=os.path.basename(src), analysed_seconds=round(dur, 2), info=info, layout=lay, beat=beat, beat_source=grid_source, music=music_pacing,
        alignment=al, cuts_on=cuts_on, pacing=pacing, transitions=kinds, blips=dict(count=len(blips), per_minute=round(len(blips) / dur * 60, 1), kinds=collections.Counter("white/bright" if b["luma_jump"] > 0 else "dark" for b in blips),
                                                                           frames=[b["frame"] for b in blips][:40]),
        speed=spd, shake_zoom=sz, text={k: v for k, v in txt.items() if k not in ("covered",)}, colour=col, native=nat, ending=end, suggested=suggested,
        cuts=[{k: c[k] for k in ("frame", "t", "beat", "offset_ms", "step_idx", "line_t", "clip_frames", "clip_beats", "note", "kind", "kind_conf", "blur", "blur_len", "on", "xy", "rt", "whip_axis", "L", "R") if k in c} for c in cuts],
        same_song=same, drum_attacks=dict(count=len(attacks), strong_kick_snare=int(len(_strong_attacks(attacks)[0])), strong_rise=STRONG_RISE, bias_ms=bh.BIAS_MS),
        pops=dict(count=len(pops), frames=pops[:60]), cut_lead=cl, hit_lead=hl, kills=kb, kills_note=kf_note, adopt=adopt,
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
        if lay["orientation"] == "horizontal":
            w("  The skill builds this window only in the VERTICAL frame (FRAME = \"vertical\"); a horizontal edit fills the frame with the clip. `adopt.layout` carries the measured layout so the drafter can say the window is not reproduced.")
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
        w("- Source: %s. **%.2f BPM**, first beat at %.4f s%s." % (r["beat_source"], beat["bpm"], beat["beat0"], "" if not beat.get("weak") else "  (a WEAK fit: no strong drum pattern; kept because the steadiness checks of music_tempo.py agree)"))
        if mem:
            w("- Tempo candidates from `music_tempo.py`: %s. Both members are real readings: a clip of `x` beats at %.2f BPM is `x/2` beats at %.2f." % (mem, beat["bpm"], beat["bpm"] / 2))
        for n_ in beat.get("notes", []):
            w("- note: %s" % n_)
        if beat.get("grid_adequate") is False:
            w("- **A constant grid is NOT adequate for this sound** (a wandering tempo or too many hits off the grid): its lattice numbers below are approximate; an edit that copies it must place kills / cuts on measured hit times (`hit(t)`), never on grid lines.")
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
        lt = [t_ for t_ in al["lattice_tests"] if t_["step"] == al["step"]][0]
        w("- **Cut to beat**: the cuts sit on a lattice of **%g beat = %.4f s = %.1f frames** (`step_s`; concentration %.2f, accepted from %.2f, chance %.2f), at a fixed distance from its lines. Median offset **%+.0f ms = %+.2f frames** (negative = the cut comes BEFORE the line), residual spread %.0f ms, 10-90 %% range %+.0f to %+.0f ms; %.0f %% of the cuts are within %.0f ms of that offset." % (
            al["step"], al["step_s"], al["step_s"] * fps, al["concentration"], lt["threshold"], lt["chance"], al["offset_ms_median"], al["offset_frames_median"],
            al["offset_ms_std"], al["offset_ms_p10"], al["offset_ms_p90"], al["locked_share"] * 100, min(40.0, 0.25 * al["step_s"] * 1000)))
        w("  Lattices tried (concentration): %s. A cut's time is the start of its first frame (frame / fps); the lines are the grid of %s." % (
            ", ".join("%g beat %.2f%s" % (t_["step"], t_["concentration"], "" if t_["accepted"] else " (rejected)") for t_ in al["lattice_tests"]), r["beat_source"]))
        w("- **Rhythm in lattice steps** (gap between consecutive cuts, steps: cuts): %s%s. %.0f %% of the gaps are whole steps within %.0f ms. The first cut is %d steps (%.2f s) into the video." % (
            ", ".join("%s: %d" % kv for kv in al["gaps_steps"].items()), "" if not al.get("gaps_same_step") else "; %d cuts share a line with the cut before (flash cuts 2-3 frames apart)" % al["gaps_same_step"],
            al["gaps_whole_share"] * 100, max(30.0, 0.2 * al["step_s"] * 1000), r["adopt"]["intro_steps"] if r["adopt"]["intro_steps"] is not None else 0, P["first_cut_s"]))
    elif al and al.get("note"):
        w("- %s" % al["note"])
    elif al:
        w("- The cuts are NOT locked to the beat (concentration %s; chance about %.2f): cut times follow something else (a sound other than the grid, or no sound)." % (
            ", ".join("%.2f at %g beat" % (t_["concentration"], t_["step"]) for t_ in al["lattice_tests"]), al["lattice_tests"][0]["chance"]))
    if al and al.get("offset_note"):
        w("- %s" % al["offset_note"])
    if r.get("same_song") and r["same_song"].get("same"):
        ss = r["same_song"]
        w("- **The reference's sound IS your song** (waveform correlation %.2f in %d of %d windows, onset score %.2f against %.2f): its time t is the song's time t %+.4f s; the grid above is the song's own." % (
            ss["ncc"], ss["windows_good"], ss["windows"], ss["score"], ss["second"], ss["offset_s"]))
    elif r.get("same_song") and r["same_song"].get("windows") is not None:
        ss = r["same_song"]
        w("- The reference's sound is NOT your song (%d of %d waveform windows match any offset)." % (ss["windows_good"], ss["windows"]))
    cl_, hl_ = r.get("cut_lead") or {}, r.get("hit_lead") or {}
    if cl_.get("frames") is not None:
        w("- **Lead before the drum attack**: its cuts come a median **%.1f frames (%.0f ms)** before the kick / snare attack of their lattice line (negative = after it; %d cuts, std %.0f ms, %.0f %% within 1.5 frames of the median) -> `cut_lead_frames = %d`, clamped to 0..3 (the attack is the half-height of the band envelope, one definition for the whole skill)." % (
            cl_["median_frames"], cl_["median_ms"], cl_["n"], cl_["std_ms"], cl_["stable_share"] * 100, cl_["frames"]))
    elif cl_:
        w("- Lead of the cuts before the drum attack: not measurable (%s%s) -> `cut_lead_frames = null`." % (cl_.get("why", "?"), (": median %+.1f frames over %d cuts" % (cl_["median_frames"], cl_["n"])) if cl_.get("median_frames") is not None else ""))
    if hl_.get("frames") is not None:
        w("- **Lead of its KILL accents** (%s: %d of %d kills): a median **%.1f frames (%.0f ms)** before the drum attack (negative = after it; std %.0f ms) -> `hit_lead_frames = %d`, clamped to 0..3." % (
            hl_["source"], hl_["n"], hl_.get("kills", 0), hl_["median_frames"], hl_["median_ms"], hl_["std_ms"], hl_["frames"]))
    elif hl_:
        w("- Lead of its KILL accents (pop / muzzle flash of a kill) before the drum attack: **%s** -> `hit_lead_frames = null` (= not measured from kills: the draft keeps its default of 1 frame). Flash frames at cuts are cut evidence (they feed `cut_lead_frames`) and are never used for the kill lead." % hl_.get("note", hl_.get("why", "?")))
    kb = r.get("kills")
    if kb:
        krate = r["adopt"]["kills"]["per_s"]
        w("- **Kills** (kill feed rows, %d; the row appears about 8 frames after the shot): %s from the first cut to the fade, median gap %.2f s%s%s." % (
            kb["count"], ("%.2f per second" % krate) if krate is not None else "per second not measured (fewer than 5 cuts or a window under 1 s)",
            kb.get("gap_s_median", 0.0), (" = %.1f lattice steps" % kb["gap_steps_median"]) if kb.get("gap_steps_median") is not None else "",
            ("; on the lattice every %d steps (concentration %.2f, chance %.2f)" % (kb["lock_steps"], kb["lock_R"], kb["lock_chance"])) if kb.get("lock_R") is not None else ""))
        npop = sum(1 for k_ in kb["kills"] if k_["pop_frame"] is not None)
        w("  %d of them have a luma pop (flash) within 25 frames before the row." % npop)
    elif r.get("kills_note"):
        w("- Kills: not read (%s)." % r["kills_note"])
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
        w("- Slow motion (motion under 60 %% of the clips' typical speed for 5+ frames: the drafter's own SLOW_BELOW, one definition): **%.0f %% of the frames**%s. Freezes (identical frames): %.1f %% of the frames in %d runs, longest %d frames." % (
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
        w("- Intro: no hard cut for the first %.2f s%s: a slow opening, not the cut rhythm of the rest (any change of view inside it is a move of the camera or a soft transition; look at `start_3s.jpg`)." % (
            first, " (%d lattice steps = %d beats at the reference's tempo)" % (r["adopt"]["intro_steps"], S["intro_beats"]) if (r["adopt"].get("intro_steps") and S.get("intro_beats")) else (" (%d beats)" % S["intro_beats"] if S.get("intro_beats") else "")))
    else:
        w("- No intro: the first cut comes at %.2f s." % first)
    e = r["ending"]
    if e["kind"] == "cut":
        w("- Ending: **cut** (the last frames are as bright as the rest: final luma %.0f, base %.0f)." % (e["final_luma"], e["base_luma"]))
    elif e["kind"] == "fade to white":
        w("- Ending: **fade to white** from %.2f s." % e["start"])
    else:
        w("- Ending: **%s**: the fade runs **%.2f s** from %.2f s (a luma fade: the dark areas reach black %.2f s before the highlights), then **%.2f s of black** to the end (the %.2f s of gradual dimming of the last take before the fade are not part of it; final luma %.0f of %.0f)." % (
            e["kind"], e["fade_s"], e["start"], e["p10_to_p90_lag"] if e.get("p10_to_p90_lag") is not None else 0.0, e["black_s"], e["dim_s"], e["final_luma"], e["base_luma"]) if e["kind"] == "luma fade" else
            "- Ending: **%s**: the fade runs **%.2f s** from %.2f s, then **%.2f s of black** (gradual dimming before the fade: %.2f s; final luma %.0f of %.0f)." % (
            e["kind"], e["fade_s"], e["start"], e["black_s"], e["dim_s"], e["final_luma"], e["base_luma"]))
    w("")
    w("## 9. Images to read before designing")
    for p, cap in r["sheets"]:
        w("- `%s`: %s" % (p.replace("\\", "/"), cap))
    if not r["sheets"]:
        w("- (sheets skipped)")
    w("")
    w("## 10. What the draft takes from this (`ref_notes.json[\"adopt\"]`, version 2)")
    ad = r["adopt"]
    w("")
    w("`draft_ref_timeline.py` reads only this block; every position / length of the reference is in LATTICE STEPS of its own grid, `null` = not measured (the draft then uses its model default and says so).")
    w("")
    w("| key | value |")
    w("|---|---|")
    lt_ = ad["lattice"]
    w("| frame | %s |" % (ad["frame"] if ad["frame"] is not None else "null (square reference: the skill builds 16:9 or 9:16 only)"))
    w("| layout | %s |" % (ad.get("layout") if ad.get("layout") is not None else "null"))
    w("| same_song.offset_s | %s |" % ("%+.4f s (song time = reference time + this)" % ad["same_song"]["offset_s"] if ad["same_song"]["offset_s"] is not None else "null (the reference's sound is not the song)"))
    w("| lattice | %s |" % ("step %.4f s = %g beat of %.2f BPM, locked R %.2f, offset %s, residual %.0f ms" % (lt_["step_s"], lt_["step_beats_ref"], lt_["ref_bpm_read"], lt_["locked_R"],
                                                                                                       ("%+.2f frames" % lt_["offset_frames"]) if lt_["offset_frames"] is not None else "null", lt_["residual_ms"]) if lt_ else "null (not locked)"))
    w("| cut_gaps_steps | %s |" % (ad["cut_gaps_steps"] if ad["cut_gaps_steps"] is not None else "null"))
    w("| cut_rate_per_s | %s |" % ad["cut_rate_per_s"])
    w("| kills | %s |" % (ad["kills"] if ad["kills"] else "null"))
    w("| transitions | %s |" % (ad["transitions"] if ad["transitions"] is not None else "null (no cut kind was measured)"))
    w("| slow | %s |" % ad["slow"])
    w("| intro_steps | %s |" % ad["intro_steps"])
    w("| ending | %s |" % ad["ending"])
    w("| look | %s (nearest preset %s) |" % (ad["look"], ad["look_preset"]))
    w("| words | %s |" % (ad["words"] if ad["words"] else "null"))
    w("| cut_lead_frames | %s |" % ad["cut_lead_frames"])
    w("| cut_lead_note | %s |" % (ad.get("cut_lead_note") if ad.get("cut_lead_note") is not None else "null"))
    w("| hit_lead_frames | %s |" % ad["hit_lead_frames"])
    w("| hit_lead_note | %s |" % ad.get("hit_lead_note"))
    w("")
    w("## SUGGESTED SETTINGS for timeline.py")
    w("")
    w("A starting point from measurements; the user's words outrank it (SKILL.md, \"Edit options\").")
    w("")
    w("```python")
    if S["FRAME"]:
        fc = ""
        if lay["kind"] == "window":
            fc = ("      # the reference puts the gameplay in a window over a backdrop: that is what FRAME = \"vertical\" builds" if S["FRAME"] == "vertical" else
                  "      # the reference's gameplay sits in a window over a blurred backdrop, but its canvas is horizontal: FRAME = \"horizontal\" fills the frame, that window is NOT drafted")
        w("FRAME = %r%s" % (S["FRAME"], fc))
    else:
        w("FRAME = 'horizontal'   # square reference: the skill builds 1920x1080 or 1080x1920 only; the plan's own frame wins (the reference's is not adopted)")
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
    w("# ending: %s" % (("luma fade %.2f s then %.2f s of black -> LUMA_S, BLACK_S" % (e["fade_s"], e["black_s"])) if e["kind"] == "luma fade" else ("fade to black %.2f s then %.2f s of black" % (e["fade_s"], e["black_s"]) if e["kind"] == "fade to black" else e["kind"])))
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
    "Cuts are the first frame of a change of picture, found by thumbnail correlation (test reference, 2000 frames: 73 of the 74 cuts of an independent finder on the same frame, the 74th is the fade to black; 9 more that look real or are settling frames of a blur-in on the strip sheets: 6 real, 3 doubtful). The older rule missed 15 % and put 9 of 60 one to three frames late. Soft transitions that move BOTH clips (whips through, spins, dissolves) can still be missed or counted twice: read ref_sheets around a cut you rely on.",
    "The kind of a blur-in was right for 54 of the 57 cuts of the worked example (30 whips, 15 zoom bursts, 12 rolls as built). A weak blur-in inside a fast clip can read as hard, so the hard-cut share is an upper bound. The sign of a whip is not measurable.",
    "Text is found by letter shapes (no OCR): 66 of the 79 words of the worked example (84 %), 91 % of the finds inside a word's time; the words are never read and neither is whether the letters are see-through or solid: read `centre_crops.jpg` (a mistake made once on small tiles). Scenery (vents, stairs) gives a few false rows: a handful is not text. Letter height reads 10 to 30 % low on see-through letters.",
    "Slow motion is motion magnitude against the clips' own typical speed: a player standing still looks like slow motion.",
    "Colour, shake and zoom numbers are relative to the worked example and the footage's own colour and camera work move them; the LOOK is a first guess, to be checked on enlarged stills of the reference and of the first render.",
    "The reference's sound is used as it is: a reference whose audio is not the song (voice-over, other music) has another grid than your song's (unless it IS your song: `same_song`). Without sound the tempo is fitted to the cut times (half / double ambiguity) and no cut-to-beat offset can be read.",
    "cut_lead_frames is a median over the cuts, hit_lead_frames over the pops / muzzle flashes of the reference's KILLS (kill-feed rows), each whose lattice line carries a kick or snare attack (the half-height of the band envelope, bias-corrected: the skill's one definition); they are null when the leads scatter (under 55 % within 1.5 frames of the median) or when fewer than 8 cuts / 6 kill accents qualify (`hit_lead_note` gives the numbers). Flash frames at cuts never set the kill lead. The kill feed is read for 1920x1080 Valorant only, and its row appears about 8 frames after the shot (a constant lag, so the kill times are for rate, gaps and lock, not for placement).",
]

if __name__ == "__main__":
    main()
