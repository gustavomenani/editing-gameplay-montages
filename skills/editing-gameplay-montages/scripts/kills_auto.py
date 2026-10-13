"""Find your kills in any shooter: the kill-feed row that appears, the shot frame K behind it, and review sheets.

usage: python kills_auto.py valorant              every clip in src/
       python kills_auto.py cs2 c1 c3             only these clips
       python kills_auto.py generic c2            untuned fallback: feed top right, every row, no ammo
       python kills_auto.py valorant --regions c2 1500    draw the profile's regions on frame 1500 -> regions.jpg
       python kills_auto.py valorant c2 --drop 12,15      remove rejected ids from kills.json

<game> is games/<game>.json (or a path to a profile). Coordinates in a profile are in the 1920x1080 working frame
(src/ is 1920x1080, 60 fps, ingest.py). Frames are read through clipio, by index.

What it does for each clip
  1. KILL-FEED ROWS. The feed region is decoded once. A row is a band of about `row_h` pixels that, within a few
     frames, turns into something different from the frames before it AND then stays still (rows are static, the
     scene behind moves). That finds the row appearing even when the whole region changes, and a fade-in as well
     as a pop-in. With an `own` rule in the profile (colour tests, e.g. Valorant's lime accent + teal body, CS2's
     red outline) only the rows that pass are kept. Without one (generic) EVERY row is kept: teammates' and
     enemies' kills too; the sheets show which are yours.
  2. SHOT FRAME K. The gunshots of the clip's own audio (sudden rise of the high-frequency level) in the window
     where the shot must lie before the row (profile lag.feed_frames), refined on the picture: the muzzle flash
     (newly bright pixels in the profile's weapon region) and, if the profile has an ammo region, the frame where
     the ammo digits change (mykills.py's rule). Candidates are scored by how many of the three agree; the best wins.
     With several shots in the window (a spray) the one nearest the usual feed latency (lag.typical) is taken.
  3. OUTPUT.
       kills.json       {id: {clip, K, feed, conf, method, changes, ...}}: K = shot frame (flash visible on K, absent on
                        K-1), feed = first frame of the row appearing, conf = high | medium | low | guess,
                        method = the signals that agreed (ammo, flash, audio) or "feed-lag" for a pure guess,
                        changes = earlier shots (ammo/flash frames) in the 30 frames before K (flick.py reads it).
                        Runs replace the entries of the clips they process and keep the others.
       autokill_NN.jpg  review sheets, 5 kills per sheet. Per row: the feed at the event | weapon zoom K-1, K, K+1 |
                        full frames K-8, K, K+8. READ THEM. Confirm each row: it is a kill of yours, the flash is on
                        tile K and not on K-1. Wrong K: edit kills.json (or --drop the id). Rows with conf low or
                        guess need the closest look.

Reading the console: per clip the number of feed rows found, how many passed the own rule, then one line per kill:
  id, K, feed, feed-K lag, conf, signals, audio offset (frames after K; 1.4 to 3.3 is normal, it varies per recording).
A clip whose own sound is voice chat or music gives no audio support: K then rests on the picture alone.

Profile fields (games/valorant.json is the reference, "notes" says where every number comes from):
  feed.region [x,y,w,h]   where the rows live; feed.row_h  height of one row; feed.row_min_w  width of the shortest row;
  feed.align right|left   which edge the rows hug; feed.own  null or {"masks": [{"name","hue":[[lo,hi]],"s_min","v_min",
  "min_px"}]}: the row is yours when EVERY colour mask has at least min_px pixels inside the row band (OpenCV hue 0-179);
  weapon.region           where the muzzle flash shows (also the zoom tiles); ammo {"region","digit_min"} or null;
  lag.feed_frames [lo,hi] frames from K to the row appearing; lag.typical; lag.audio_frames [lo,hi] and
  lag.audio_typical: frames from the flash to the gunshot in the audio; validated false = nobody checked it on footage.

Calibrating a profile for a new game: --regions on a frame with a kill on screen; fix the rectangles; run on a clip
with known kills and read the sheets. Everything is measured, nothing is read from the profile as truth."""
import argparse, glob, json, os, subprocess, sys, time
import preflight
import numpy as np
import cv2
import clipio
from ff import FF

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 48000
VIDEO = (".mp4", ".mkv", ".mov", ".m4v", ".webm", ".avi")
LOOK = 12            # frames from "before the row" to "row finished": slide-in or fade-in is over by then
HOLD = 6             # frames the finished row must stay still
CHANGED = 40         # max-channel level change that counts as "a pixel changed"
STILL = 10           # ... and as "a pixel did not move"
AMMO_CHG = 0.10     # share of the digit pixels that must change at one frame for an ammo step (one digit changing: 0.1-0.25 (6 -> 5 on c18: ~0.12), noise 0.01)
AMMO_QUIET = 0.15   # ... and the 2 frames around it must be quieter than that (0.08 lost real steps whose neighbours flickered 0.08-0.15)
DUP_NCC = 0.9       # last resort: a row whose name+portrait correlates this much with an earlier row of the clip is that row again
ROW_LIFE = 300      # frames a row stays on screen (valid frames of the rows measured: up to 300 = 5 s)
KEEP_ROW = 600      # frames a row that vanished (flash, scroll) is remembered: a row stays on screen about 8 s, so it comes back as itself, not as a second kill
OWN_DELAY = 5       # frames after the band changed within which an own row's colours must show (a row appears at once)


def load_profile(game):
    p = game if game.lower().endswith(".json") else os.path.join(HERE, "games", game + ".json")
    if not os.path.exists(p):
        have = sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(HERE, "games", "*.json")))
        sys.exit(f"no profile {p}. Profiles available: {', '.join(have)}. Start from generic.json: copy it to games/<game>.json.")
    prof = json.load(open(p, encoding="utf-8"))
    prof["_name"] = os.path.splitext(os.path.basename(p))[0]
    return prof


# ---------------------------------------------------------------------------------------------- frames
def read(clip, a, b):
    """Frames a..b (inclusive) of the clip, uint8 (N, 1080, 1920, 3) RGB: the same pixels as clipio.read_frames(crop=False),
    but ffmpeg stops after the last frame (read_frames lets it decode the rest of the file: seconds per call).
    Windows sometimes refuses to start ffmpeg for a moment (PermissionError, 'Acesso negado'): tried again up to 5 times."""
    cmd = [FF, "-nostdin", "-v", "error"] + clipio.frame_args(clip, a, b, "scale=in_range=tv:out_range=pc,format=rgb24") + ["-frames:v", str(b - a + 1), "-f", "rawvideo", "-"]
    for attempt in range(5):
        try:
            raw = subprocess.run(cmd, capture_output=True).stdout
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(1.0 + attempt)
    arr = np.frombuffer(raw, np.uint8).reshape(-1, clipio.SH, clipio.SW, 3)
    assert len(arr) == b - a + 1, (clip, a, b, len(arr))
    return arr


# ---------------------------------------------------------------------------------------------- feed rows
def stream(clip, x, y, w, h):
    """Every frame of the clip, cropped to the region, RGB (colour conversion identical to clipio.read_frames)."""
    fix = clipio.colour_fix(clip)                                   # untagged recordings: decode as bt709, as clipio does
    vf = (fix + "," if fix else "") + f"crop={w}:{h}:{x}:{y},scale=in_range=tv:out_range=pc,format=rgb24"
    cmd = [FF, "-nostdin", "-v", "error", "-i", clipio.path(clip), "-map", "0:v:0", "-vf", vf, "-fps_mode", "passthrough", "-f", "rawvideo", "-"]
    for attempt in range(5):
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=w * h * 3 * 8)
            break
        except PermissionError:                                      # Windows refuses to start ffmpeg now and then: try again
            if attempt == 4:
                raise
            time.sleep(1.0 + attempt)
    size = w * h * 3
    while True:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    p.wait()


def mask_of(hsv, m):
    """Boolean mask of one colour rule of the profile ({"hue": [[lo, hi]], "s_min", "v_min", "v_max"}) inside an HSV image."""
    hh, ss, vv = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    hm = np.zeros(hh.shape, bool)
    for lo, hi in m["hue"]:
        hm |= (hh >= lo) & (hh <= hi)
    return hm & (ss >= m.get("s_min", 0)) & (vv >= m.get("v_min", 0)) & (vv <= m.get("v_max", 255))


def color_counts(rgb, own):
    """Pixels per colour mask of the profile's own rule inside rgb (h, w, 3)."""
    hsv = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2HSV)
    return {m["name"]: int(mask_of(hsv, m).sum()) for m in own["masks"]}


def own_row_ok(rgb, own, align="right"):
    """Is this crop (a feed row band, as wide as the feed region) a row of the player's own kill? -> (ok, counts).
    Every colour mask needs its min_px; with own["order"] = [killer colour, victim colour] the victim colour must outnumber the
    killer colour in the last own["order_tail"] (90) columns of the row, at the edge the rows hug (Valorant: your team's teal killer
    on the left, the enemy's red victim at the right edge; a row of YOUR DEATH has the enemy killer in red on the left and YOU, teal,
    at the right edge, and is not a kill). The tail, not a centroid: a reddish wall behind the row must not change the verdict."""
    hsv = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2HSV)
    ms = {m["name"]: mask_of(hsv, m) for m in own["masks"]}
    cnt = {n: int(m.sum()) for n, m in ms.items()}
    ok = all(cnt[m["name"]] >= m["min_px"] for m in own["masks"])
    if ok and own.get("order"):
        t = own.get("order_tail", 90)
        sl = slice(-t, None) if align == "right" else slice(0, t)
        killer, victim = (int(ms[n][:, sl].sum()) for n in own["order"])
        ok = victim > killer
    return ok, cnt


def line_runs(mask):
    """[(a, b)) of consecutive True lines."""
    idx = np.flatnonzero(np.diff(np.r_[0, mask.astype(np.int8), 0]))
    return list(zip(idx[::2], idx[1::2]))


def scan_rows(clip, prof, trace=None):
    """Rows of the kill feed found BY COLOUR and followed over time: [{onset, y0, y1, own, why, counts, n}] (y in frame pixels,
    onset = the first frame the finished row is there: killer colour, victim colour and the own-kill accent all present).
    Used by profiles whose feed.own has "band" (Valorant). A row is a band of lines where every colour of own["band"] has pixels;
    it is YOURS when every colour of own["masks"] has its min_px and own["order"] holds (see own_row_ok). A row is followed from
    frame to frame (same place, or the same picture somewhere else: the feed scrolls up when the top row expires), so a row that
    moves or flickers is never counted twice. Rows already there when the clip starts are not events.
    trace receives (frame, y0, y1, why) for every other-player row (own=False), why = "death" | "other player"."""
    trace = [] if trace is None else trace
    feed = prof["feed"]
    fx, fy, fw, fh = feed["region"]
    own = feed["own"]
    row_h, min_w = feed["row_h"], feed["row_min_w"]
    specs = {m["name"]: m for m in own["masks"]}
    band_names, line_px = own["band"], own.get("band_line_px", 20)
    lo_h, hi_h = int(0.8 * row_h), int(1.25 * row_h)
    FPW, FPH, FPX = 32, 24, 48          # a row is told from the others by the victim's portrait (the last 48 px): names and colours look alike
    tracks, live, n = [], [], 0

    def band_runs(ms):
        ok = np.ones(fh, bool)
        for nm in band_names:
            ok &= ms[nm].sum(1) >= line_px
        runs = []
        for a, b in line_runs(ok):
            if runs and a - runs[-1][1] <= 3:                     # text and icons break the colour for a line or two
                runs[-1] = (runs[-1][0], b)
            else:
                runs.append((a, b))
        return [(a, b) for a, b in runs if lo_h <= b - a <= hi_h]

    for i, f in enumerate(stream(clip, fx, fy, fw, fh)):
        n = i + 1
        if i % 60 == 0:
            live = [t for t in live if i - t["last"] <= KEEP_ROW]
        hsv = cv2.cvtColor(f, cv2.COLOR_RGB2HSV)
        ms = {nm: mask_of(hsv, m) for nm, m in specs.items()}
        for a, b in band_runs(ms):
            sl = slice(max(0, a - 2), min(fh, b + 2))
            ok, cnt = own_row_ok(f[sl], own, feed.get("align", "right"))
            cols = np.flatnonzero(np.logical_or.reduce([ms[nm][sl] for nm in band_names]).any(0))
            if len(cols) == 0 or cols.max() - cols.min() + 1 < min_w:
                continue
            struct = all(cnt[nm] >= specs[nm]["min_px"] for nm in band_names)          # killer and victim colours both there
            if not struct:
                continue                                                                   # a flat bar still fading in, or scenery
            why = None
            if not ok:
                lime_ok = all(cnt[m["name"]] >= m["min_px"] for m in own["masks"])
                why = "death" if lime_ok else "other player"
            g = cv2.resize(cv2.cvtColor(np.ascontiguousarray(f[a:b, -FPX:]), cv2.COLOR_RGB2GRAY), (FPW, FPH), interpolation=cv2.INTER_AREA).astype(np.float32)
            g = (g - g.mean()) / (g.std() + 1e-3)
            big = cv2.resize(cv2.cvtColor(np.ascontiguousarray(f[a:b, -170:]), cv2.COLOR_RGB2GRAY), (96, 16), interpolation=cv2.INTER_AREA).astype(np.float32)
            big = (big - big.mean()) / (big.std() + 1e-3)                  # victim's name + portrait: tells a row that came back from another row
            best, bs = None, 0.0
            for t in live:
                if i - t["last"] > KEEP_ROW:
                    continue
                ncc = max(float((t["fp"] * g).mean()), float((t["fp0"] * g).mean()))
                near = abs(a - t["a"]) <= 8 and ((i - t["last"] <= 2 and ncc >= 0.3) or i - t.get("onset_own", t["onset"]) < ROW_LIFE)   # in its slot, before it can have expired: the same row       # an old row fading out changes its look, it is still that row
                if (near or ncc >= 0.8) and ncc > bs:
                    best, bs = t, ncc
            if best is None and any(
                    i - t["last"] <= 45 and t["a"] > a + 8 and max(float((t["fp"] * g).mean()), float((t["fp0"] * g).mean()), float((t["big"] * big).mean())) >= 0.5 for t in live):
                trace.append((i, fy + a, fy + b, "above existing rows"))   # the feed only grows downwards: a row that looks like one below it is that row, moved up (scrolled)
                continue
            if best is None:
                tracks.append({"onset": i, "a": a, "b": b, "fp": g, "last": i, "n": 1, "own": bool(ok), "why": why, "counts": cnt, "y0": fy + a, "y1": fy + b, "big": big, "fp0": g})
                live.append(tracks[-1])
            else:
                best.update(a=a, b=b, fp=g, last=i, n=best["n"] + 1)
                if ok and not best["own"] and best["why"] == "other player":        # the bar fading in had no accent yet: now the row is complete
                    best.update(own=True, why=None, counts=cnt, onset_own=i, y0=fy + a, y1=fy + b, big=big, fp0=g)
                elif best["n"] <= 3:                                # the first frames of a row decide where it is and what it is
                    best.update(y0=fy + a, y1=fy + b)
    if n != clipio.n_frames(clip):
        print(f"  WARNING {clip}: decoded {n} frames but pts/{clip}.csv has {clipio.n_frames(clip)}: frame indices may be off")
    events, seen = [], []
    for t in sorted(tracks, key=lambda t: t.get("onset_own", t["onset"])):
        if t["onset"] < 3 or t["n"] < 8:                          # there when the clip started / flicker of scenery
            continue
        if t["own"]:                                              # the same row again (it flickered out and back, e.g. under a flash): not a second kill
            o = t.get("onset_own", t["onset"])
            trace.append((o, t["y0"], t["y1"], "ncc", [round(float((q * t["big"]).mean()), 2) for p, q in seen if o - p < 900]))
            if any(o - p < 900 and float((q * t["big"]).mean()) >= DUP_NCC for p, q in seen):
                trace.append((o, t["y0"], t["y1"], "same row again"))
                continue
            seen.append((o, t["big"]))
        ev = {"onset": int(t.get("onset_own", t["onset"])), "y0": int(t["y0"]), "y1": int(t["y1"]), "own": t["own"], "why": t["why"], "counts": t["counts"], "n": int(t["n"])}
        if t["own"]:
            ev["t_own"] = ev["onset"]
        else:
            trace.append((ev["onset"], ev["y0"], ev["y1"], t["why"]))
        events.append(ev)
    return events


def scan_feed(clip, prof, trace=None):
    """Feed rows of a clip (see scan_rows / scan_feed_diff): colour tracking when the profile has own.band, else change detection."""
    own = prof["feed"].get("own")
    if own and own.get("band"):
        return scan_rows(clip, prof, trace)
    return scan_feed_diff(clip, prof, trace)


def scan_feed_diff(clip, prof, trace=None):
    """Rows appearing in the feed region: [{onset, y0, y1, own, counts}] (y in frame pixels, onset = frame index).
    trace: a list that receives (frame, y0, y1, reason, ...) for every candidate band that was thrown out (diagnostics)."""
    trace = [] if trace is None else trace
    fx, fy, fw, fh = prof["feed"]["region"]
    row_h, min_w = prof["feed"]["row_h"], prof["feed"]["row_min_w"]
    right = prof["feed"].get("align", "right") == "right"
    own = prof["feed"].get("own")
    look = prof["feed"].get("settle_frames", LOOK)
    cw = max(8, min_w // 2)
    lo_h, hi_h = max(4, int(0.6 * row_h / 2)), int(1.6 * row_h / 2) + 1
    full, small, still = {}, {}, {}
    state = {"runs": [], "events": [], "last": -1}

    def get(k):
        return min(k, state["last"])

    def process(j):
        pre, post = small[j - 2], small[get(j + look)]
        cov = (np.abs(post - pre).max(2) > CHANGED).mean(1)
        calm = np.mean([still[k] for k in range(get(j + look) - 2, get(j + look + HOLD) + 1)], axis=0)
        for a, b in line_runs((cov >= 0.5) & (calm >= 0.85)):       # changed AND now still: lines of a finished row, even
            if not lo_h <= b - a <= hi_h:                            # when the whole scene behind it moved
                continue
            for r in state["runs"]:                      # same band as a run that is still open?
                ov = min(b, r["b"]) - max(a, r["a"])
                if ov >= 0.5 * min(b - a, r["b"] - r["a"]) and j - r["j1"] <= 3:
                    r["j1"], r["a"], r["b"] = j, a, b
                    break
            else:
                state["runs"].append({"j0": j, "j1": j, "a": a, "b": b})

    def finish(r, newest):
        a, b, j = r["a"], r["b"], r["j1"]
        pre = small[j - 2]
        rows = slice(max(0, 2 * a - 2), 2 * b + 2)
        tex = lambda s: float(np.abs(s[:, 1:] - s[:, :-1]).max(2).mean())
        t_pre, t_post = tex(pre[a:b]), tex(small[get(j + look)][a:b])
        if not own and t_post < 0.8 * t_pre:
            trace.append((j, fy + 2 * a, fy + 2 * b, "flatter", round(t_pre, 1), round(t_post, 1)))
            return                                                  # no own rule: a band that got flatter is a row going away
        if own and all(color_counts(full[max(0, r["j0"] - 2)][rows], own)[m["name"]] >= m["min_px"] for m in own["masks"]):
            trace.append((j, fy + 2 * a, fy + 2 * b, "own row there before"))
            return                                                  # an own row was already there before the change: it is leaving
        pitch, rw = prof["feed"].get("row_pitch", row_h), 2 * cw
        x0 = fw - rw if right else 0
        pre_f, post_f = full[max(0, r["j0"] - 2)][:, x0:x0 + rw].astype(np.int16), full[get(j + look)][:, x0:x0 + rw].astype(np.int16)
        y0f, y1f = 2 * a, 2 * b
        for s in range(pitch - 3, pitch + 4):                       # the rows above this one expired and the feed scrolled up:
            if y1f + s <= pre_f.shape[0] and (np.abs(post_f[y0f:y1f] - pre_f[y0f + s:y1f + s]).max(2) > CHANGED).mean() < 0.3:
                trace.append((j, fy + y0f, fy + y1f, "scrolled up"))     # this band now shows what the band one pitch below showed
                return
        onset = j
        for t in range(j - 1, min(newest, j + look) + 1):          # first frame where the band no longer looks like before
            if (np.abs(small[t][a:b] - pre[a:b]).max(2) > CHANGED).mean() >= 0.4:
                onset = t
                break
        ev = {"onset": int(onset), "y0": int(fy + 2 * a), "y1": int(fy + 2 * b), "own": None, "counts": None}
        if own:
            best, first = None, None
            for t in range(onset + 1, min(newest, onset + 26) + 1):
                cnt = color_counts(full[t][rows], own)
                ok = all(cnt[m["name"]] >= m["min_px"] for m in own["masks"])
                if ok and first is None:
                    first = t
                score = sum(min(1.0, cnt[m["name"]] / m["min_px"]) for m in own["masks"])
                if best is None or (ok, score) > (best[0], best[1]):
                    best = (ok, score, cnt, t)
            if best:
                ev["own"], ev["counts"], ev["t_own"] = bool(best[0]), best[2], int(best[3])
                if first is not None and first - onset > OWN_DELAY:     # the colours came much later than the band changed: a camera
                    trace.append((j, fy + y0f, fy + y1f, "own colours late"))   # move settling above a row that appears later (found as itself)
                    return
        state["events"].append(ev)

    def flush(newest, final=False):
        keep = []
        for r in state["runs"]:
            if final or newest - look - HOLD - r["j1"] > 3:
                finish(r, newest)
            else:
                keep.append(r)
        state["runs"] = keep

    n = 0
    for i, f in enumerate(stream(clip, fx, fy, fw, fh)):
        n = i + 1
        state["last"] = i
        full[i] = f
        s = cv2.resize(f, (fw // 2, fh // 2), interpolation=cv2.INTER_AREA).astype(np.int16)
        s = s[:, -cw:] if right else s[:, :cw]
        small[i] = s
        still[i] = (np.abs(s - small[i - 1]).max(2) <= STILL).mean(1) if i else np.ones(s.shape[0])
        j = i - (look + HOLD)
        if j >= 2:
            process(j)
        flush(i)
        for k in [k for k in small if k < i - 80]:
            full.pop(k, None), small.pop(k), still.pop(k)
    last = state["last"]
    for j in range(max(2, last - (look + HOLD) + 1), last - 1):      # the tail: the "row finished" frame is clamped to the end
        process(j)
    flush(last, final=True)
    if n != clipio.n_frames(clip):
        print(f"  WARNING {clip}: decoded {n} frames but pts/{clip}.csv has {clipio.n_frames(clip)}: frame indices may be off")
    events = []
    for e in sorted(state["events"], key=lambda e: e["onset"]):      # one row seen twice (two bands, same frame): keep the first
        if not events or e["onset"] - events[-1]["onset"] > 2:
            events.append(e)
        elif (e["own"], sum((e["counts"] or {}).values())) > (events[-1]["own"], sum((events[-1]["counts"] or {}).values())):
            events[-1] = e
    return events


# ---------------------------------------------------------------------------------------------- audio
def audio_onsets(clip):
    """Gunshot-like onsets of the clip's own audio: [(frame (float), strength)]. A sudden rise of the level of the
    highs (first difference), 2 ms bins, against the 24 ms before it."""
    raw = subprocess.run([FF, "-v", "error", "-i", clipio.path(clip), "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    if len(x) < SR:
        return []
    hp = np.diff(x, prepend=0.0)
    nb = len(hp) // 96
    e = np.sqrt((hp[:nb * 96].reshape(nb, 96) ** 2).mean(1)) + 1e-6
    csum = np.r_[0, np.cumsum(e)]
    base = np.empty(nb)
    base[12:] = (csum[12:nb] - csum[0:nb - 12]) / 12          # mean of the 12 bins before bin j
    base[:12] = e[:12].mean()
    peak = np.maximum.reduce([e[k:nb - 3 + k] for k in range(4)])
    peak = np.r_[peak, np.full(3, e[-1])]
    floor = np.percentile(e, 30)
    hit = (peak > 2.4 * base) & (peak > 4 * floor) & (e > 1.6 * base)
    out, last = [], -100
    p = clipio.pts(clip)
    for j in np.flatnonzero(hit):
        if j - last < 10:                                     # one onset per 20 ms
            continue
        last = j
        t = (j + 0.5) * 96 / SR
        out.append((float(np.interp(t, p, np.arange(len(p)))), float(peak[j] / base[j])))
    return out


# ---------------------------------------------------------------------------------------------- shot frame
def rising_runs(score, floor, ratio):
    """Frames where a series jumps: at least `floor` and `ratio` times the mean of the 4 frames before it."""
    out = []
    for k in range(4, len(score)):
        if score[k] >= floor and score[k] >= ratio * (score[k - 4:k].mean() + 1) and score[k] >= score[k - 1]:
            if not out or k - out[-1] > 1:
                out.append(k)
    return out


def shot_signals(clip, a, b, prof):
    """Picture signals on frames a..b: {'flash': [frames], 'ammo': [frames]} (absolute frame indices)."""
    fr = read(clip, a, b)
    wx, wy, ww, wh = prof["weapon"]["region"]
    V = fr[:, wy:wy + wh, wx:wx + ww].max(3).astype(np.int16)
    new = np.r_[0, ((V[1:] - V[:-1] > 50) & (V[1:] > 200)).sum((1, 2))].astype(float)
    flash = [a + k for k in rising_runs(new, 0.0023 * ww * wh, 3.0)]
    ammo, readable = [], []
    if prof.get("ammo"):
        ax, ay, aw, ah = prof["ammo"]["region"]
        masks = [fr[i, ay:ay + ah, ax:ax + aw].min(axis=2) > prof["ammo"].get("digit_min", 205) for i in range(len(fr))]
        chg = np.zeros(len(fr))
        for i in range(1, len(fr)):
            chg[i] = (masks[i] ^ masks[i - 1]).sum() / max((masks[i] | masks[i - 1]).sum(), 40)
        # one digit changing (13 -> 12) moves only about 0.2 of the digit pixels: the threshold must catch it (c02 4659: 0.23)
        ammo = [a + i for i in range(3, len(fr) - 3)
                if chg[i] > AMMO_CHG and max(chg[i + 1], chg[i + 2], chg[i - 1], chg[i - 2]) < AMMO_QUIET and masks[i].sum() > 60]
        readable = [a + i for i in range(len(fr)) if masks[i].sum() > 60 and chg[i] < AMMO_QUIET]   # digits there and steady (a muzzle flash washing over them: not readable)
    return {"flash": flash, "ammo": ammo, "readable": readable}


def find_shot(clip, ev, prof, onsets):
    """K for one feed event: THE SHOT THAT KILLED, i.e. the last shot fired before the row appeared (the row follows the killing
    shot by lag.likely frames, 6 to 10 on the footage), never the first shot of a burst. Returns the dict that goes to kills.json.
    Candidates: ammo-counter changes, muzzle flashes (a flash that follows another candidate within 4 frames is the same shot's
    echo), gunshots in the audio. Of the candidates inside the likely lag range the LATEST wins; without one, the latest inside
    the wide range lag.feed_frames; a candidate without picture signal (audio only) only when no picture candidate exists;
    nothing at all: K = feed - lag.typical, conf guess."""
    lag = prof["lag"]
    feed = ev["onset"]
    lo, hi = lag["feed_frames"]
    llo, lhi = lag.get("likely", [lo, hi])
    typical = lag["typical"]
    alo, ahi = lag["audio_frames"]
    atyp = lag["audio_typical"]
    n = clipio.n_frames(clip)
    a = max(0, feed - lag.get("long", hi + 8) - 6)
    b = min(n - 1, feed - lo + 3)
    sig = shot_signals(clip, a, b, prof)
    aud = [(o, s) for o, s in onsets if a <= o <= b + ahi + 1]
    pool = {}
    for kind in ("ammo", "flash"):
        for f in sig[kind]:
            for g in pool:                                     # merge candidates within one frame
                if abs(g - f) <= 1:
                    pool[g].append((kind, f))
                    break
            else:
                pool[f] = [(kind, f)]
    cands = []
    for g, items in sorted(pool.items()):
        kinds = {k for k, _ in items}
        pic = min((f for k, f in items if k == "ammo"), default=min(f for _, f in items))
        sup = [(o - pic, s) for o, s in aud if alo <= o - pic <= ahi]
        near = min(sup, key=lambda q: abs(q[0] - atyp)) if sup else None
        cands.append({"f": int(pic), "kinds": sorted(kinds), "audio": None if near is None else near[0], "astr": None if near is None else near[1]})
    cands = [c for i, c in enumerate(cands) if not (c["kinds"] == ["flash"] and any(0 < c["f"] - p["f"] <= 4 for p in cands[:i]))]
    # A shot spends a bullet. When the counter shows digits on both sides of a candidate and does not step there, it is not a shot: the
    # death highlight of the enemy, the feed row sliding in, an ability flash and a muzzle-flash echo all light the weapon area too.
    rd = set(sig.get("readable", []))
    cands = [c for c in cands if "ammo" in c["kinds"] or not all(f in rd for f in range(c["f"] - 3, c["f"] + 4))]
    no_shot = False
    best, long_lag = None, lag.get("long", hi + 8)
    for r0, r1, strong in ((llo, lhi, False), (lo, hi, False), (hi + 1, long_lag, True)):
        inside = [c for c in cands if feed - r1 <= c["f"] <= feed - r0 and (not strong or {"ammo", "flash"} <= set(c["kinds"]))]
        if inside:                                  # (the last range: a shot 13 to 20 frames before the row is taken only when ammo AND flash show it)
            best = max(inside, key=lambda c: c["f"])
            break
    all_shots = sorted({f for kind in ("ammo", "flash") for f in sig[kind]})
    if best:
        method = "+".join(best["kinds"] + (["audio"] if best["audio"] is not None else []))
        nk = len(best["kinds"]) + (best["audio"] is not None)
        L = feed - best["f"]
        conf = "high" if ("ammo" in best["kinds"] and nk >= 2 or nk == 3) and llo <= L <= lhi else "medium" if nk >= 2 or ("ammo" in best["kinds"] and llo <= L <= lhi) else "low"
        K, au, astr = best["f"], best["audio"], best["astr"]
    else:
        gk = feed - typical
        no_shot = bool(rd) and all(f in rd for f in range(gk - 6, gk + 7))      # the counter is steady all around: no bullet was fired for this row
        near = [(o, s) for o, s in aud if gk - 3 <= o - atyp <= gk + 3]
        astr = None
        if near:                                    # a gunshot is where the row says the shot was: support, but its frame is +-3 (the lag to the row is steadier)
            astr = max(near, key=lambda q: q[1])[1]
            K, au, method, conf = gk, atyp, "feed-lag+audio", "low"
        else:
            K, au, method, conf = gk, None, "feed-lag", "guess"
    res = {"K": int(K), "feed": int(feed), "conf": conf, "method": method,
            "audio_after_K": None if au is None else round(float(au), 2), "audio_strength": None if astr is None else round(float(astr), 1),
            "changes": [int(f) for f in all_shots if K - 30 <= f < K]}
    if not best and no_shot:
        res["no_shot"] = True               # a row of yours with no shot of yours in the lag window while the counter is readable: ability/knife kill, or not a gun kill
    return res


# ---------------------------------------------------------------------------------------------- sheets
def label(img, text, x, y, scale=1.0, color=(0, 255, 255)):
    (w, h), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    cv2.rectangle(img, (x, y), (x + w + 8, y + h + base + 6), (0, 0, 0), -1)
    cv2.putText(img, text, (x + 4, y + h + 3), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)


TW, TH = 320, 180


def fit(rgb, tw, th):
    h, w = rgb.shape[:2]
    s = min(tw / w, th / h)
    im = cv2.resize(rgb, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    out = np.zeros((th, tw, 3), np.uint8)
    out[:im.shape[0], :im.shape[1]] = im
    return out


def review_row(kid, k, ev, prof):
    c, K = k["clip"], k["K"]
    n = clipio.n_frames(c)
    a, b = max(0, K - 8), min(n - 1, K + 8)
    fr = read(c, a, b)
    at = lambda f: fr[min(max(f, a), b) - a]
    fx, fy, fw, fh = prof["feed"]["region"]
    y0 = max(fy, ev["y0"] - int(0.6 * prof["feed"]["row_h"]))
    y1 = min(fy + fh, ev["y1"] + int(0.6 * prof["feed"]["row_h"]))
    feed_tile = np.zeros((TH, 480, 3), np.uint8)
    for q, (off, name) in enumerate(((-3, "feed before"), (10, "feed +10"))):
        f = min(n - 1, max(0, ev["onset"] + off))
        crop = fit(read(c, f, f)[0][y0:y1, fx:fx + fw], 480, 88)
        label(crop, name, 0, 0, 0.7)
        feed_tile[q * 90:q * 90 + 88] = crop
    tiles = [feed_tile]
    wx, wy, ww, wh = prof["weapon"]["region"]
    for off in (-1, 0, 1):
        t = fit(at(K + off)[wy:wy + wh, wx:wx + ww], TW, TH)
        label(t, "K%+d" % off if off else "K", 0, TH - 34, 1.0, (0, 255, 255) if off else (0, 255, 0))
        tiles.append(t)
    for off in (-8, 0, 8):
        t = fit(at(K + off), TW, TH)
        label(t, "K%+d" % off if off else "K", 0, TH - 34, 1.0)
        tiles.append(t)
    row = np.hstack(tiles)
    own = {None: "all rows", True: "own", False: "NOT own"}[ev.get("own")]
    head = np.zeros((34, row.shape[1], 3), np.uint8)
    flags = ("  HIDDEN: target covered" if k.get("hidden") else "") + ("  HEADSHOT" if k.get("headshot", 0) >= prof.get("headshot", {}).get("min_score", 0.6) else "")
    label(head, "#%s  %s  K=%d  feed=%d  %s  %s  (%s)%s" % (kid, c, K, k["feed"], k["conf"].upper(), k["method"], own, flags), 0, 0, 1.0,
          (0, 0, 255) if k.get("hidden") else (0, 255, 255))
    return cv2.cvtColor(np.vstack([head, row]), cv2.COLOR_RGB2BGR)


def write_sheets(rows, per=5):
    for f in glob.glob("autokill_*.jpg"):
        os.remove(f)
    names = []
    for s in range(0, len(rows), per):
        name = "autokill_%02d.jpg" % (s // per + 1)
        cv2.imwrite(name, np.vstack(rows[s:s + per]), [cv2.IMWRITE_JPEG_QUALITY, 88])
        names.append(name)
    return names


# ---------------------------------------------------------------------------------------------- regions
def draw_regions(prof, clip, frame):
    fr = read(clip, frame, frame)[0].copy()
    big = fr.copy()
    f = prof["feed"]
    x, y, w, h = f["region"]
    cv2.rectangle(big, (x, y), (x + w - 1, y + h - 1), (255, 255, 0), 3)
    y_first, pitch = f.get("first_row_y", y), f.get("row_pitch", f["row_h"])
    mw = f["row_min_w"]
    xx = x + w - mw if f.get("align", "right") == "right" else x
    k = 0
    while y_first + pitch * k + f["row_h"] <= y + h:        # one slot per row: the rows must sit in these slots
        ys = y_first + pitch * k
        cv2.rectangle(big, (xx, ys), (xx + mw - 1, ys + f["row_h"] - 1), (255, 128, 0), 2 if k == 0 else 1)
        k += 1
    wx, wy, ww, wh = prof["weapon"]["region"]
    cv2.rectangle(big, (wx, wy), (wx + ww - 1, wy + wh - 1), (0, 255, 255), 3)
    parts = [("feed", prof["feed"]["region"], (255, 255, 0)), ("weapon", prof["weapon"]["region"], (0, 255, 255))]
    if prof.get("ammo"):
        ax, ay, aw, ah = prof["ammo"]["region"]
        cv2.rectangle(big, (ax, ay), (ax + aw - 1, ay + ah - 1), (0, 255, 0), 3)
        parts.append(("ammo", prof["ammo"]["region"], (0, 255, 0)))
    big = cv2.cvtColor(cv2.resize(big, (1600, 900), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2BGR)
    for name, (rx, ry, rw, rh), col in parts:
        label(big, name, int(rx * 1600 / 1920), max(0, int(ry * 900 / 1080) - 30), 0.9, (col[2], col[1], col[0]))
    label(big, "%s  %s frame %d  validated=%s  (orange = one row slot, as wide as the shortest row)" % (
        prof["_name"], clip, frame, prof.get("validated")), 0, 0, 0.9)
    crops = []
    for name, (rx, ry, rw, rh), col in parts:
        if name == "weapon":
            continue
        cr = fit(fr[ry:ry + rh, rx:rx + rw], 500, 250 if name == "feed" else 120)
        cr = cv2.cvtColor(cr, cv2.COLOR_RGB2BGR)
        label(cr, name + " region, zoomed", 0, 0, 0.8)
        crops.append(cr)
    strip = np.zeros((max(c.shape[0] for c in crops), 1600, 3), np.uint8)
    x0 = 0
    for cr in crops:
        strip[:cr.shape[0], x0:x0 + cr.shape[1]] = cr
        x0 += cr.shape[1] + 10
    cv2.imwrite("regions.jpg", np.vstack([big, strip]), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("regions.jpg written: %s frame %d. Check: the YELLOW feed box holds every row with room to spare; each ORANGE slot "
          "sits on a row (same top edge, no wider than the row); the CYAN weapon box holds the muzzle flash; the GREEN ammo "
          "box holds the digits and nothing else." % (clip, frame))


# ---------------------------------------------------------------------------------------------- main
def clip_names():
    names = sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob("src/*") if f.lower().endswith(VIDEO))
    return names


def check_clip(clip):
    """The clip must exist in src/ and have its time table; otherwise say which of the two is missing."""
    if not glob.glob(f"src/{clip}.*"):
        have = clip_names()
        sys.exit(f"kills_auto.py: no clip {clip!r} in src/. Clips there: {', '.join(have) or 'none (run python ingest.py first)'}. "
                 "Give the short names (c1, c2 ...), not file names or paths.")
    if not os.path.exists(f"pts/{clip}.csv"):
        sys.exit(f"kills_auto.py: pts/{clip}.csv is missing: run  python mkpts.py {clip}  first")


def row_headshot(clip, ev, prof):
    """Score 0..1 of the headshot icon in a feed row (normalised cross-correlation of the white pixels left of the victim's colour
    with the icon template of the profile); None when the profile has no template or the row cannot be read. A headshot row of
    Valorant scores 0.9+, a body-shot row (the weapon icon sits there instead) 0.3."""
    hs, own = prof.get("headshot"), prof["feed"].get("own")
    if not hs or not own:
        return None
    path = os.path.join(HERE, "games", hs["template"])
    tm = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if tm is None:
        return None
    fx, fy, fw, fh = prof["feed"]["region"]
    f = min(clipio.n_frames(clip) - 1, ev["onset"] + 10)
    band = read(clip, f, f)[0][max(0, ev["y0"] - 4):ev["y0"] + 38, fx:fx + fw]
    specs = {m["name"]: m for m in own["masks"]}
    hsv = cv2.cvtColor(np.ascontiguousarray(band), cv2.COLOR_RGB2HSV)
    frac = mask_of(hsv, specs[hs["anchor"]])[4:38].mean(0)
    runs = line_runs(frac >= 0.5)
    if not runs:
        return None
    a = max(runs, key=lambda r: r[1] - r[0])[0]
    white = (band.min(2) >= hs.get("white_min", 190)).astype(np.float32)[:, max(0, a - 80):a + 6]
    t = tm.astype(np.float32) / 255
    if white.shape[0] < t.shape[0] or white.shape[1] < t.shape[1]:
        return None
    return round(float(cv2.matchTemplate(white, t, cv2.TM_CCOEFF_NORMED).max()), 2)


def visibility(clip, K, prof):
    """Can the viewer see the target? Around the crosshair (box prof.visible.box, centred on the frame) the picture must show detail:
    on each frame K-6..K+6 the grey-level spread and the edge strength of the box are measured; a frame is COVERED when both are far
    below any normal scene (an ability wall or smoke over the whole screen, a flash-blind, a full-screen colour: Valorant's teal wall
    gives std 1.7 / edge 3 against 14+ / 11+ in every normal scene measured). hidden = at least `min_frames` of the 13 are covered.
    -> {"covered": n, "std": median, "edge": median, "hidden": bool}"""
    v = prof.get("visible", {})
    bx, by, bw, bh = v.get("box", [700, 380, 520, 320])
    std_max, edge_max, min_frames = v.get("std_max", 8.0), v.get("edge_max", 6.0), v.get("min_frames", 5)
    n = clipio.n_frames(clip)
    a, b = max(0, K - 6), min(n - 1, K + 6)
    fr = read(clip, a, b)[:, by:by + bh, bx:bx + bw]
    stds, edges = [], []
    for im in fr:
        g = cv2.cvtColor(np.ascontiguousarray(im), cv2.COLOR_RGB2GRAY).astype(np.float32)
        gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
        stds.append(float(g.std()))
        edges.append(float(np.hypot(gx, gy).mean()))
    stds, edges = np.array(stds), np.array(edges)
    covered = int(((stds < std_max) & (edges < edge_max)).sum())
    return {"covered": covered, "std": round(float(np.median(stds)), 1), "edge": round(float(np.median(edges)), 1), "hidden": covered >= min_frames}


CONF_RANK = {"high": 3, "medium": 2, "low": 1, "guess": 0}


def one_row_per_shot(kills):
    """kills: [kill dict] of one clip. A shot kills once: two rows whose K lie 2 frames apart or less are the same kill seen twice (a row
    that flickered, or sits in two feed slots while it scrolls): the one with the better confidence stays (ties: the earlier row).
    -> (kept, dropped)."""
    kept, dropped = [], []
    for k in sorted(kills, key=lambda k: k["feed"]):
        twin = next((q for q in kept if abs(q["K"] - k["K"]) <= 2), None)
        if twin is None:
            kept.append(k)
        elif CONF_RANK[k["conf"]] > CONF_RANK[twin["conf"]]:
            kept[kept.index(twin)] = k
            dropped.append(twin)
        else:
            dropped.append(k)
    return sorted(kept, key=lambda k: k["feed"]), dropped


def analyze(clip, prof, verbose=True):
    """All own-kill (or, without an own rule, all) feed events of a clip with their shot frames -> ([(event, kill dict)], [other rows]).
    other rows = feed rows the own rule dropped: [{"onset", "why"}] (why = "death" | "other player"; only profiles that track rows by colour)."""
    check_clip(clip)
    rows = scan_feed(clip, prof)
    keep = [e for e in rows if e["own"] is not False]
    other = [{"onset": e["onset"], "why": e.get("why") or "other player"} for e in rows if e["own"] is False]
    if verbose:
        why = {}
        for o in other:
            why[o["why"]] = why.get(o["why"], 0) + 1
        print(f"{clip}: {len(rows)} feed rows appeared, {len(keep)} kept" + (" (own rule dropped %d: %s)" % (len(other), ", ".join(f"{v} {k}" for k, v in sorted(why.items())) or "-")
                                                                           if prof["feed"].get("own") else " (no own rule: every row)"), flush=True)
        if not keep:
            fx, fy, fw, fh = prof["feed"]["region"]
            if not rows:
                print(f"  NO KILLS in {clip}: nothing ever appeared in the feed region (x {fx}..{fx + fw}, y {fy}..{fy + fh}). This is what a menu, lobby, "
                      f"replay without the HUD, or a recording of another game / another resolution looks like. If you know the clip has kills: "
                      f"python kills_auto.py {prof['_name']} --regions {clip} <a frame with a kill on screen> and check that the yellow box holds the kill feed.", flush=True)
            else:
                print(f"  NO OWN KILLS in {clip}: {len(rows)} rows appeared in the feed but none passed the 'own kill' colour rule of profile "
                      f"{prof['_name']} (only other players' kills in this clip, or your HUD colours differ from the profile). If you know you got kills here: "
                      f"use the generic profile, which keeps every row (python kills_auto.py generic {clip}), or check the colours with --regions.", flush=True)
    onsets = audio_onsets(clip)
    out = []
    shots = [find_shot(clip, ev, prof, onsets) | {"clip": clip, "_ev": ev} for ev in keep]
    _, same = one_row_per_shot(shots)
    if same and verbose:
        print(f"  {len(same)} row(s) share the shot of another row (K within 2 frames): dropped (feed {', '.join(str(k['feed']) for k in same)})", flush=True)
    gone = {id(k) for k in same}
    for k in shots:
        if id(k) in gone:
            continue
        ev = k.pop("_ev")
        k["row_y"] = int(ev["y0"])
        hs = row_headshot(clip, ev, prof)
        if hs is not None:
            k["headshot"] = hs
        vis = visibility(clip, k["K"], prof)
        k["visible"] = {"covered": vis["covered"], "std": vis["std"], "edge": vis["edge"]}
        if vis["hidden"]:
            k["hidden"] = True
        out.append((ev, k))
        if verbose:
            au = k["audio_after_K"]
            print("  K=%-6d feed=%-6d lag %-3d %-6s %-18s audio %-5s %s%s" % (k["K"], k["feed"], k["feed"] - k["K"], k["conf"], k["method"],
                                                                              "-" if au is None else "%+.1f" % au,
                                                                              "" if hs is None else ("HS " if hs >= prof["headshot"].get("min_score", 0.6) else "body "),
                                                                              "HIDDEN (target covered)" if vis["hidden"] else ""), flush=True)
    return out, other


class Parser(argparse.ArgumentParser):
    def error(self, message):
        have = sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(HERE, "games", "*.json")))
        if message.startswith("the following arguments are required"):
            message = "no game given"
        sys.exit(f"kills_auto.py: {message}\n\n"
                 f"It needs the GAME first (one of: {', '.join(have)}), then optionally clip names:\n"
                 "  python kills_auto.py valorant            every clip in src/\n"
                 "  python kills_auto.py cs2 c1 c3           only these clips\n"
                 "  python kills_auto.py valorant --regions c1 1500   draw the profile's regions on frame 1500 of c1 -> regions.jpg\n"
                 "  python kills_auto.py valorant --drop 12,15        remove wrong ids from kills.json\n"
                 "Another game: python kills_auto.py generic c1 (untuned, lists every feed row).")


def main():
    ap = Parser(description="find your kills: feed rows, shot frames, review sheets", add_help=True)
    ap.add_argument("game", help="profile name in games/ (valorant, cs2, generic) or a path to a profile json")
    ap.add_argument("clips", nargs="*", help="clip names in src/ (default: all)")
    ap.add_argument("--regions", nargs=2, metavar=("CLIP", "FRAME"), help="draw the profile's regions on one frame -> regions.jpg")
    ap.add_argument("--drop", help="ids to remove from kills.json (comma separated), then exit")
    ap.add_argument("--no-sheets", action="store_true")
    args = ap.parse_args()
    prof = load_profile(args.game)
    if not prof.get("validated"):
        print(f"NOTE: profile '{prof['_name']}' is not validated on footage ({prof.get('notes', '')[:160]}...): check it with --regions first.")
    if args.regions:
        clip = args.regions[0]
        check_clip(clip)
        try:
            frame = int(args.regions[1])
        except ValueError:
            sys.exit(f"kills_auto.py: --regions wants a clip and a frame NUMBER, got {args.regions[1]!r}: e.g. --regions {clip} 1500 "
                     f"(a frame where a kill is on screen; python peek.py {clip} 0 99999 60 shows the clip at one tile per second)")
        n = clipio.n_frames(clip)
        if not 0 <= frame < n:
            sys.exit(f"kills_auto.py: frame {frame} is outside {clip}, which has frames 0..{n - 1} ({n / 60:.1f} s): pick a frame inside it")
        draw_regions(prof, clip, frame)
        return
    if args.drop:
        if not os.path.exists("kills.json"):
            sys.exit("kills_auto.py: --drop works on kills.json, which does not exist here: run  python kills_auto.py <game>  first")
        kills = json.load(open("kills.json", encoding="utf-8"))
        for i in args.drop.split(","):
            print("dropped", i, kills.pop(i.strip(), "(not there: ids are the keys of kills.json)"))
        json.dump(kills, open("kills.json", "w"), indent=1)
        return
    clips = args.clips or clip_names()
    if not clips:
        sys.exit("kills_auto.py: src/ has no video clips: put the recordings in clips.json and run  python ingest.py && python mkpts.py  first")
    for c in clips:
        check_clip(c)
    kills = json.load(open("kills.json", encoding="utf-8")) if os.path.exists("kills.json") else {}
    old = dict(kills)
    kills = {i: k for i, k in kills.items() if k.get("clip") not in clips}
    nxt = max([int(i) for i in kills] + [-1]) + 1
    sheets, evs = [], []
    other = json.load(open("rows_other.json", encoding="utf-8")) if os.path.exists("rows_other.json") else {}
    for c in clips:
        found, other[c] = analyze(c, prof)
        for ev, k in found:
            kills[str(nxt)] = k
            evs.append((str(nxt), k, ev))
            nxt += 1
    replaced = sum(1 for k in old.values() if k.get("clip") in clips)
    if replaced:
        import shutil
        shutil.copyfile("kills.json", "kills.json.bak")           # the entries of these clips are replaced: keep hand-corrected K values recoverable
    json.dump(dict(sorted(kills.items(), key=lambda q: int(q[0]))), open("kills.json", "w", encoding="utf-8"), indent=1)
    print(f"kills.json: {len(kills)} kills ({len(evs)} from this run)" + (f"; {replaced} earlier entries of these clips were replaced (hand-corrected K values included): "
                                                                           "the previous file is kept as kills.json.bak" if replaced else ""))
    json.dump(other, open("rows_other.json", "w", encoding="utf-8"), indent=0)
    dropped = [o for c in clips for o in other.get(c, [])]
    if prof["feed"].get("own"):
        print("rows of other players / your deaths dropped: %d teammates' or enemies' rows, %d rows where you died (rows_other.json)"
              % (sum(o["why"] == "other player" for o in dropped), sum(o["why"] == "death" for o in dropped)))
    hid = [i for i, k, _ in evs if k.get("hidden")]
    gue = [i for i, k, _ in evs if k["conf"] == "guess"]
    if hid:
        print(f"CHECK: {len(hid)} kill(s) with the target covered at the shot (hidden: nothing to see; do not build a take on them): ids {', '.join(hid)}")
    nos = [i for i, k, _ in evs if k.get("no_shot")]
    if nos:
        print(f"CHECK: {len(nos)} row(s) of yours with no shot of yours before them while the ammo counter was steady (ability / knife kill, or not a gun kill): ids {', '.join(nos)}")
    if gue:
        print(f"CHECK: {len(gue)} kill(s) without any shot evidence (K = feed - {prof['lag']['typical']}, +-3 frames): ids {', '.join(gue)}: read their sheets before using them")
    if not evs:
        print(f"WARNING: no kills found in {', '.join(clips)}: nothing to review and no sheets were written (see the line for each clip above).")
    if not args.no_sheets and evs:
        rows = [review_row(kid, k, ev, prof) for kid, k, ev in evs]
        print("sheets:", ", ".join(write_sheets(rows)), "- 5 kills each: feed | weapon K-1, K, K+1 | full K-8, K, K+8")
    if not prof["feed"].get("own"):
        print("NOTE: this profile has no own-kill rule: every kill-feed row is listed, teammates' and enemies' kills included. Delete the rows that are not yours (--drop).")


if __name__ == "__main__":
    main()
