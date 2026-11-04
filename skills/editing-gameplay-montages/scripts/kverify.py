"""K check: is the shot frame K of every kill really the first frame of the shot? (ammo step / muzzle flash ON K, nothing on K-1)

K is the frame the edit puts on the beat; the viewer sees the shot on it. One frame off and the kill is 16.7 ms early or late
against the drum. K comes from the ammo counter of the HUD (mykills.py, kills_auto.py); when that finds nothing K is a guess
(feed row - 7 frames) and a guess is a frame off in 3 of 4 cases. This script measures K again on the pictures, whatever way K was found.

usage (from the project folder, scripts copied in):
  python kverify.py                          every kill of timeline.py (or of kills.json when there is no timeline)
  python kverify.py timeline.py              every kill of this timeline (K = the frame its time map gives the shot beat)
  python kverify.py plan.json                every {"clip","K"} of the plan (+ {"id": N} entries, resolved by kills.json)
  python kverify.py kills.json [--ids 3,4]   the kills of kills.json (all, or those ids)
  python kverify.py c08@1065 c03@173         single kills (clip@K)
  options: --game valorant|cs2|generic (profile in games/, default valorant), --no-sheets, --out PREFIX (default kv),
           --update (kills.json: write the result into it, see below), --strict (not measurable fails too)

Signals, per frame, on frames K-9..K+9 (frame index = clipio index; they are measured on pixels, never on the audio):
  ammo   mean absolute change of the ammo-counter box against the frame before, ANY digit colour (the counter turns red at low ammo:
         a white-pixel mask is blind there, and so was mykills.py). On = >= 5 and > 1.5x the frame before (measured: 13-58 at a real step,
         <= 3-5 on quiet frames). A gun that recoils behind the digits keeps the box moving for a few frames after the step: only the
         ONSET counts, the frames after it need not be quiet. Peak = >= 15, rising 1.15x and not under 0.9x the next frame (sprays).
  flash  newly bright pixels (> +50 and > 200) in the weapon region against the frame before. On = >= 0.23 % of the region and >= 3x
         the mean of the 4 frames before. Peak = >= 1.5x the frame before and not below the next.
  hud    white pixels in the HUD band around the counter: a camera cut / replay takes the HUD with it (0 after, >= 0.67 of before at
         every real shot of 87 measured).
The ammo step and the flash are on the SAME frame (frame by frame on 35 kills of 3 projects: 33 exact, 1 one frame early, 1 replay cut).

Verdict per kill (exit code 1 when any is suspect / corrected):
  verified          ammo ON, or flash ON, or (ammo peak AND flash peak) on K, and no contradicting signal on K-1 / K+1.
  CORRECT to K'     K has none of that and exactly one strong ammo step (>= 10) 1-3 frames away, with the flash on the same frame when
                    there is one: the corrected K' is printed (c08@1065: step 18.2 and the flash on K+1 -> 1066).
  suspect           the signals disagree or sit further away: read the sheet row (the offsets are printed).
  not measurable    the HUD vanishes on K (replay camera), or neither signal appears within +-8 frames (weapon hidden, counter off
                    screen): nothing to check, K rests on whoever chose it; read the sheet.

What "verified" does NOT say: that K is the shot that killed. In a spray every shot is a first frame of its own; picking the one the feed row
belongs to is mykills.py / kills_auto.py's job (the shot 5..12 frames before the row). Test on the 110 kills of three real projects: moved one
frame either way no K passes as verified (each is reported suspect or corrected back to the right frame); moved 2-3 frames in a fast spray, another shot of the spray may pass.
Exit code: 1 when any kill is suspect or CORRECTED (K changes), 0 otherwise (--strict: not measurable counts too).

Output: kv_NN.jpg (6 kills per sheet; per kill 7 tiles K-3..K+3: the crosshair / weapon area with the ammo counter pasted in the corner;
frame colour: green = ammo step, yellow = muzzle flash, cyan = both) and kv.json {"clip@K": {verdict, how, conf, K_sure, ammo, flash, ...}}.
--update (kills.json): K := the sure corrected K (the old one stays as "K_was"), but ONLY when its feed row still follows it inside the
profile's lag.feed_frames (cs2 3..20, generic 3..30: see --game): a K the tool itself would not accept as the shot of that row is not
written (the old K stays and a line says why). For a verified / corrected kill whose feed row (when there is one) is inside that window:
how = "ammo" | "flash", conf = "high" (both signals) | "medium", verified = true; a K measured elsewhere than the shot of its feed row (a
spray, or an earlier shot: kills.json c08#25 K=995 is a real shot, 27 frames before its row) keeps its old how (an entry without "how":
"ammo-loose" / "guess" from its conf); a suspect verdict turns a verified how into "ammo-loose". "kverify": the verdict, always.

The drafter refuses a kill whose kills.json entry has how "guess" or "ammo-loose" unless the plan entry says "k_checked": true
(say so after reading these sheets)."""
import argparse, json, os, sys
import numpy as np
import cv2
import clipio

HERE = os.path.dirname(os.path.abspath(__file__))
SPAN = 8             # offsets from K that are judged; one more frame is read each side, K-9..K+9
AMMO_MIN = 5.0       # box change at a step (measured 13-58) against quiet frames (<= 3-5)
AMMO_RATIO = 1.5     # a step is this many times the frame before
AMMO_PEAK = 15.0     # a spray step that does not rise 1.5x (the gun moves behind the digits): >= this, rising, not below the next frame
AMMO_STRONG = 10.0   # a step this strong, alone near K, is enough to correct K
FLASH_FLOOR = 0.0023 # share of the weapon region that turns bright on the first flash frame
FLASH_RATIO = 3.0    # ... and times the mean of the 4 frames before
FLASH_PEAK = 1.5
NEAR = 3             # a step this close to K (not on it) is a candidate for the corrected K
HUD_GONE = 0.25      # white pixels of the HUD band after a frame / before it: below this the HUD went away (replay camera)
FEED_LAG = (4, 12)   # frames from the shot to its feed row: FALLBACK only (Valorant's lag.feed_frames). main() passes the profile's
                     # own window to apply_update (cs2 3..20, generic 3..30): a kill whose row arrives late was refused with how = guess


def load_profile(game="valorant"):
    p = game if game.lower().endswith(".json") else os.path.join(HERE, "games", game + ".json")
    if not os.path.exists(p) and os.path.exists(os.path.join("games", os.path.basename(p))):
        p = os.path.join("games", os.path.basename(p))
    if not os.path.exists(p):
        sys.exit(f"kverify.py: no profile {p}: games/<game>.json is copied with the scripts (cp -r scripts/games .)")
    prof = json.load(open(p, encoding="utf-8"))
    prof["_name"] = os.path.splitext(os.path.basename(p))[0]
    return prof


# ---------------------------------------------------------------------------------------------- signals (shared with mykills.py)
def signals(fr, prof):
    """fr: (N, 1080, 1920, 3) RGB, consecutive frames -> {"ammo": (N,) | None, "flash": (N,), "hud": (N,) | None, "area": int}.
    ammo[j] = mean absolute change of the counter box between frame j-1 and j; flash[j] = pixels that turned bright in the weapon
    region; hud[j] = white pixels of the HUD band around the counter (both change series are 0 at j = 0)."""
    wx, wy, ww, wh = prof["weapon"]["region"]
    V = fr[:, wy:wy + wh, wx:wx + ww].max(3).astype(np.int16)
    flash = np.r_[0.0, ((V[1:] - V[:-1] > 50) & (V[1:] > 200)).sum((1, 2))].astype(float)
    ammo = hud = None
    if prof.get("ammo"):
        ax, ay, aw, ah = prof["ammo"]["region"]
        box = fr[:, ay:ay + ah, ax:ax + aw].astype(np.int16)
        ammo = np.r_[0.0, np.abs(box[1:] - box[:-1]).mean((1, 2, 3))]
        x0, y0 = max(0, ax - 82), max(0, ay - 18)                                  # the band: counter + reserve + bullets icon
        band = fr[:, y0:ay + ah + 20, x0:ax + aw + 56]
        hud = (band.min(3) > 205).sum((1, 2)).astype(float)
    return {"ammo": ammo, "flash": flash, "hud": hud, "area": ww * wh}


def evidence(sg):
    """Per frame index j of a signals() result: sets of the marks it carries
    "A" ammo onset, "a" ammo peak, "F" flash onset, "f" flash peak. -> list (N,) of str."""
    ad, new, floor = sg["ammo"], sg["flash"], FLASH_FLOOR * sg["area"]
    n = len(new)
    out = [""] * n
    # a flash lasts 2-3 frames, and its second frame passes the onset test again while the 4 frames before it still hold a quiet one:
    # the ONSET is the first frame of a run (kills_auto.rising_runs does the same)
    cand = [j >= 4 and new[j] >= floor and new[j] >= FLASH_RATIO * (new[j - 4:j].mean() + 1) and new[j] >= new[j - 1] for j in range(n)]
    for j in range(1, n - 1):
        s = ""
        if ad is not None:
            if ad[j] >= AMMO_MIN and ad[j] > AMMO_RATIO * ad[j - 1]:
                s += "A"
            elif ad[j] >= AMMO_PEAK and ad[j] > 1.15 * ad[j - 1] and ad[j] >= 0.9 * ad[j + 1]:
                s += "a"
        if cand[j]:
            s += "" if cand[j - 1] else "F"
        elif new[j] >= floor and new[j] >= FLASH_PEAK * new[j - 1] and new[j] >= new[j + 1]:
            s += "f"
        out[j] = s
    return out


# ---------------------------------------------------------------------------------------------- one kill
def measure(clip, K, prof):
    """Frames K-9..K+9 of the clip -> {"frames", "a" (first frame index), "ammo" / "flash" / "hud" {offset: value}, "marks" {offset: str}}."""
    n = clipio.n_frames(clip)
    a, b = max(0, K - SPAN - 1), min(n - 1, K + SPAN + 1)
    fr = clipio.read_frames(clip, a, b, crop=False)
    sg = signals(fr, prof)
    return dict(from_signals(sg, a, K), frames=fr, a=a)


def from_signals(sg, a, K):
    ev = evidence(sg)
    off = lambda arr, rnd=2: None if arr is None else {a + j - K: round(float(v), rnd) for j, v in enumerate(arr)}
    return {"ammo": off(sg["ammo"]), "flash": off(sg["flash"], 0), "hud": off(sg["hud"], 0), "marks": {a + j - K: s for j, s in enumerate(ev)}}


def judge(m):
    """Verdict from measure(): {"verdict": verified | correct | suspect | unmeasurable, "how", "conf", "K_off" (corrected K - K; 0 = none), "why"}."""
    mk, am, hud = m["marks"], m["ammo"] or {}, m["hud"]
    inr = lambda o: mk.get(o, "")
    on = lambda o, c: c in inr(o)
    fmt = lambda offs: ", ".join("K%+d" % o for o in offs) or "-"
    A = [o for o in range(-SPAN, SPAN + 1) if on(o, "A")]
    F = [o for o in range(-SPAN, SPAN + 1) if on(o, "F")]
    if hud is not None:                                           # replay / camera cut: the HUD is gone after K (or appears on it)
        pre = min((hud.get(o, 0) for o in (-3, -2, -1)))
        post = min((hud.get(o, 0) for o in (0, 1, 2)))
        if pre >= 100 and post < HUD_GONE * pre:
            return {"verdict": "unmeasurable", "how": None, "conf": None, "K_off": 0,
                    "why": "the HUD disappears on K (%d -> %d white pixels): a replay / camera cut, not a shot" % (pre, post)}
        if post >= 100 and pre < HUD_GONE * post:
            return {"verdict": "unmeasurable", "how": None, "conf": None, "K_off": 0,
                    "why": "the HUD appears on K (%d -> %d white pixels): a camera cut, not a shot" % (pre, post)}
    here = inr(0)
    ammo_on, flash_on = "A" in here, "F" in here
    weak_both = ("a" in here) and ("f" in here)
    if ammo_on or flash_on or weak_both:
        fl = m["flash"]
        for o in (-1, 1):                                         # a comparable signal on the frame before / after: K is not the first frame
            if (on(o, "A") and am.get(o, 0) >= max(AMMO_STRONG, 0.5 * am.get(0, 0))) or (on(o, "F") and fl.get(o, 0) >= 0.5 * fl.get(0, 0)):
                sig = "ammo step %.1f" % am[o] if on(o, "A") and am.get(o, 0) >= max(AMMO_STRONG, 0.5 * am.get(0, 0)) else "muzzle flash"
                return {"verdict": "suspect", "how": None, "conf": None, "K_off": 0,
                        "why": "%s on K but %s on K%+d" % ("ammo step" if ammo_on else "muzzle flash" if flash_on else "ammo and flash peaks", sig, o)}
        if ammo_on:
            how, conf = "ammo", "high" if (flash_on or "f" in here) else "medium"
            why = "ammo step %.1f on K%s" % (am[0], " + muzzle flash" if flash_on else " (+ flash peak)" if "f" in here else "")
        elif flash_on:
            how, conf = "flash", "high" if "a" in here else "medium"
            why = "muzzle flash on K%s" % (" + ammo peak" if "a" in here else " (the counter shows no step: hidden or not stepping)")
        else:
            how, conf, why = "flash", "medium", "ammo peak %.1f and flash peak on K (spray: weak signals, both agree)" % am.get(0, 0)
        return {"verdict": "verified", "how": how, "conf": conf, "K_off": 0, "why": why}
    near = [o for o in A if o != 0 and abs(o) <= NEAR and am.get(o, 0) >= AMMO_STRONG]
    anyA = [o for o in A if abs(o) <= NEAR]
    if len(near) == 1 and len(anyA) == 1:
        d = near[0]
        fl_near = [o for o in range(-NEAR - 1, NEAR + 2) if "F" in inr(o) or "f" in inr(o)]
        if not fl_near or fl_near == [d]:
            return {"verdict": "correct", "how": "ammo", "conf": "high" if fl_near else "medium", "K_off": d,
                    "why": "the ammo step (%.1f) is on K%+d%s, nothing on K" % (am[d], d, " together with the muzzle flash" if fl_near else "")}
    anym = [o for o in range(-SPAN, SPAN + 1) if inr(o)]
    if anym:
        return {"verdict": "suspect", "how": None, "conf": None, "K_off": 0,
                "why": "nothing on K; ammo step at %s, flash at %s (weak: %s)" % (fmt(A), fmt(F), fmt([o for o in anym if o not in A and o not in F]))}
    return {"verdict": "unmeasurable", "how": None, "conf": None, "K_off": 0,
            "why": "no ammo step and no muzzle flash within +-%d frames (weapon hidden or counter off screen)" % SPAN}


# ---------------------------------------------------------------------------------------------- sheets
def lab(t, s, y=0, col=(255, 255, 0), scale=0.5):
    (w, h), base = cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    cv2.rectangle(t, (0, y), (w + 8, y + h + base + 4), (0, 0, 0), -1)
    cv2.putText(t, s, (4, y + h + 2), cv2.FONT_HERSHEY_SIMPLEX, scale, col, 1, cv2.LINE_AA)


def sheet_row(K, m, res, prof, tag):
    """7 tiles K-3..K+3 (crosshair / weapon area, the ammo counter pasted bottom left) under a verdict line."""
    fr, a = m["frames"], m["a"]
    ax, ay, aw, ah = prof["ammo"]["region"] if prof.get("ammo") else (0, 0, 0, 0)
    tiles = []
    for off in range(-3, 4):
        f = fr[min(max(K + off - a, 0), len(fr) - 1)]
        t = np.ascontiguousarray(cv2.resize(f[330:780, 760:1560], (320, 180), interpolation=cv2.INTER_AREA))
        if ah:
            z = f[max(0, ay - 6):ay + ah + 6, max(0, ax - 40):ax + aw + 40]
            z = cv2.resize(z, (150, int(150 * z.shape[0] / z.shape[1])), interpolation=cv2.INTER_AREA)
            t[180 - z.shape[0]:, :z.shape[1]] = z
        mk = m["marks"].get(off, "")
        isa, isf = "A" in mk, "F" in mk
        col = (0, 255, 255) if isa and isf else (0, 255, 0) if isa else (255, 255, 0) if isf else None
        if col:
            cv2.rectangle(t, (0, 0), (319, 179), col, 4)
        info = "K%+d" % off if off else "K"
        if m["ammo"] is not None:
            info += "  ammo %.1f" % m["ammo"].get(off, 0)
        info += "  fl %d" % m["flash"].get(off, 0)
        lab(t, info, 0, (0, 255, 0) if off == 0 else (255, 255, 0))
        tiles.append(t)
    row = np.hstack(tiles)
    head = np.zeros((26, row.shape[1], 3), np.uint8)
    colr = {"verified": (0, 255, 0), "correct": (255, 160, 0), "suspect": (255, 60, 60), "unmeasurable": (200, 200, 200)}[res["verdict"]]
    lab(head, "%s %s   %s%s" % (tag, res["verdict"].upper(), res["why"], "   -> K %d" % (K + res["K_off"]) if res["K_off"] else ""), 0, colr, 0.6)
    return np.vstack([head, row])


# ---------------------------------------------------------------------------------------------- inputs
def kills_from_timeline(path):
    import importlib.util
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    spec = importlib.util.spec_from_file_location("kv_timeline", path)
    T = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(T)
    sync = getattr(T, "SYNC", 0)
    if not isinstance(sync, (int, float)) or sync < 2:          # a timeline of the old contract has other kill beats: refuse, never check them
        import preflight
        sys.exit("kverify.py: " + preflight.sync_update_message(sync))
    out = []
    for i, s in enumerate(T.SEGS):
        for k, lv in s.get("kills", []):
            K = float(s["map"](k)[0])
            if abs(K - round(K)) > 1e-3:
                print("note: take %d (%s): the kill at beat %.3f maps to source frame %.3f, not a whole frame: checking frame %d" % (i, s["clip"], k, K, round(K)))
            out.append({"clip": s["clip"], "K": int(round(K)), "where": "take %d" % i})
    return out


def kills_from_json(path, ids, kills_json):
    """kills.json ({id: {clip, K, ...}}) or any json holding {"clip", "K"} dicts (plan.json) and {"id": N} dicts (-> kills.json)."""
    d = json.load(open(path, encoding="utf-8-sig"))
    out = []
    if isinstance(d, dict) and d and all(isinstance(v, dict) and "clip" in v and "K" in v for v in d.values()):
        for i, e in d.items():
            if ids is None or i in ids:
                out.append({"clip": e["clip"], "K": int(e["K"]), "id": i, "where": "kills.json #%s" % i})
        return out

    def walk(o, trail):
        if isinstance(o, dict):
            if "clip" in o and "K" in o:
                out.append({"clip": o["clip"], "K": int(o["K"]), "where": trail})
            elif "id" in o and not isinstance(o["id"], (dict, list)) and kills_json is not None and str(o["id"]) in kills_json:
                e = kills_json[str(o["id"])]
                out.append({"clip": e["clip"], "K": int(o.get("K", e["K"])), "id": str(o["id"]), "where": trail + " (id %s)" % o["id"]})
            for k, v in o.items():
                walk(v, trail + "/" + k)
        elif isinstance(o, list):
            for q, v in enumerate(o):
                walk(v, "%s[%d]" % (trail, q))
    walk(d, os.path.basename(path))
    return out


def apply_update(kj, results, feed_lag=FEED_LAG):
    """Write the verdicts into the kills.json dict (see the module docstring); -> number of entries touched.
    feed_lag: (lo, hi) frames from the shot to its feed row, from the game profile's lag.feed_frames (main passes it; the
    default is Valorant's window). A CORRECTED K is written only when the row still follows it inside that window: moving K
    to a frame the tool itself would not accept as the shot of the row (the correction found another shot, or the row
    belongs to a later shot) used to leave the entry with how = guess while its K pointed at a frame kverify rejects."""
    n = 0
    lo, hi = feed_lag
    for i, e in kj.items():
        r = results.get("%s@%d" % (e["clip"], int(e["K"])))
        if r is None:
            continue
        if r["K_sure"] is not None:
            new = r["K_sure"]
            lag = None if e.get("feed") is None else e["feed"] - new
            if lag is None or lo <= lag <= hi:
                e["K_was"], e["K"] = e["K"], new
            else:                                                # the corrected frame would put the row outside the lag window: not the shot of that row
                print("  kills.json #%s (%s): K kept at %d, not moved to %d: its feed row would sit %d frames after it, outside %d..%d"
                      % (i, e["clip"], e["K"], new, lag, lo, hi))
        e["kverify"] = r["verdict"]
        lag = None if e.get("feed") is None else e["feed"] - e["K"]
        if "how" not in e:                                       # an entry of an older tool: its conf says what it was
            e["how"] = e.get("conf") if e.get("conf") in ("ammo-loose", "guess") else "guess"
            e["verified"] = False
        if r["verdict"] in ("verified", "correct") and (lag is None or lo <= lag <= hi):
            e["how"], e["conf"], e["verified"] = r["how"], r["conf"], True
        elif r["verdict"] == "suspect":                          # the signals do not support K: whatever claimed it is verified is wrong
            if e["how"] in ("ammo", "flash"):
                e["how"], e["conf"] = "ammo-loose", "low"
            e["verified"] = False
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description="check that K is the first frame of the shot (ammo step / muzzle flash on K, none on K-1)")
    ap.add_argument("inputs", nargs="*", help="timeline.py | plan.json | kills.json | clip@K (default: timeline.py, else kills.json)")
    ap.add_argument("--ids", help="kills.json ids (comma separated)")
    ap.add_argument("--game", default="valorant")
    ap.add_argument("--no-sheets", action="store_true")
    ap.add_argument("--out", default="kv", help="prefix of kv_NN.jpg and kv.json")
    ap.add_argument("--update", action="store_true", help="write the result into kills.json")
    ap.add_argument("--strict", action="store_true", help="not measurable fails too")
    args = ap.parse_args()
    prof = load_profile(args.game)
    ins = args.inputs or (["timeline.py"] if os.path.exists("timeline.py") else ["kills.json"] if os.path.exists("kills.json") else [])
    if not ins:
        sys.exit("kverify.py: nothing to check: give timeline.py, plan.json, kills.json or clip@K (none of timeline.py / kills.json is in this folder)")
    kj = json.load(open("kills.json", encoding="utf-8-sig")) if os.path.exists("kills.json") else None
    ids = set(x.strip() for x in args.ids.split(",")) if args.ids else None
    items = []
    for x in ins:
        if "@" in x and not os.path.exists(x):
            c, k = x.split("@")
            items.append({"clip": c, "K": int(k), "where": x})
        elif x.endswith(".py"):
            items += kills_from_timeline(x)
        elif x.endswith(".json"):
            items += kills_from_json(x, ids, kj)
        else:
            sys.exit(f"kverify.py: {x!r} is none of timeline.py, *.json, clip@K")
    if args.update and not (kj is not None and any("id" in it for it in items)):
        sys.exit("kverify.py: --update works on kills.json entries: give kills.json (or a plan with {\"id\": N} entries)")
    uniq = {}
    for it in items:
        uniq.setdefault((it["clip"], it["K"]), []).append(it)
    print("kverify: %d kills (%d distinct clip@K), profile %s" % (len(items), len(uniq), prof["_name"]), flush=True)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)      # --out may name a new folder (cv2.imwrite fails silently there)
    results, rows, sheet = {}, [], 0
    counts = {"verified": 0, "correct": 0, "suspect": 0, "unmeasurable": 0}

    def flush_rows():
        nonlocal rows, sheet
        if rows and not args.no_sheets:
            sheet += 1
            cv2.imwrite("%s_%02d.jpg" % (args.out, sheet), cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 86])
        rows = []
    for (clip, K), its in sorted(uniq.items()):
        m = None
        if not 0 <= K < clipio.n_frames(clip):
            res = {"verdict": "suspect", "how": None, "conf": None, "K_off": 0, "why": "frame %d is outside the clip (%d frames)" % (K, clipio.n_frames(clip))}
        else:
            m = measure(clip, K, prof)
            res = judge(m)
        counts[res["verdict"]] += 1
        tag = "%s@%d" % (clip, K)
        word = {"verified": "verified", "correct": "CORRECT", "suspect": "SUSPECT", "unmeasurable": "not measurable"}[res["verdict"]]
        print("%-12s %-14s %s%s   [%s]" % (tag, word, res["why"], "  ->  K = %d" % (K + res["K_off"]) if res["K_off"] else "",
                                          ", ".join(i["where"] for i in its)), flush=True)
        results[tag] = {"clip": clip, "K": K, "verdict": res["verdict"], "how": res["how"], "conf": res["conf"],
                        "K_sure": K + res["K_off"] if res["K_off"] else None, "why": res["why"], "where": [i["where"] for i in its]}
        if m is not None:
            results[tag].update({"ammo": None if m["ammo"] is None else {str(o): v for o, v in m["ammo"].items() if abs(o) <= 4},
                                 "flash": {str(o): v for o, v in m["flash"].items() if abs(o) <= 4},
                                 "marks": {str(o): s for o, s in m["marks"].items() if s and abs(o) <= SPAN}})
            if not args.no_sheets:
                rows.append(sheet_row(K, m, res, prof, tag))
                if len(rows) == 6:
                    flush_rows()
    flush_rows()
    json.dump(results, open(args.out + ".json", "w", encoding="utf-8"), indent=1)
    print("\n%d verified, %d corrected, %d suspect, %d not measurable%s -> %s.json" % (
        counts["verified"], counts["correct"], counts["suspect"], counts["unmeasurable"],
        "; sheets %s_01..%s_%02d.jpg" % (args.out, args.out, sheet) if sheet else "", args.out))
    if args.update:
        n_up = apply_update(kj, results, prof["lag"]["feed_frames"])
        json.dump(kj, open("kills.json", "w", encoding="utf-8"), indent=1)
        print("kills.json updated: %d entries (K corrected where the verdict is CORRECT and its feed row stays inside the profile's lag "
              "window %d..%d; K_was keeps the old one, a line says where a correction was refused)" % ((n_up,) + tuple(prof["lag"]["feed_frames"])))
    sys.exit(1 if counts["suspect"] + counts["correct"] + (counts["unmeasurable"] if args.strict else 0) else 0)


if __name__ == "__main__":
    main()
