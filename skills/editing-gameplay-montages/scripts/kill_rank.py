"""Which kills are worth a take? One table of every kill of every clip with a score and the reasons, a "best N for X seconds"
suggestion, and the checks a timeline must pass before it is delivered.

usage: python kill_rank.py                       rank kills.json (kills_auto.py output); writes kill_rank.json + kill_rank.jpg
       python kill_rank.py --seconds 20          also suggest the kills for a 20 s montage (default 1.2 s per kill; --per-kill S)
       python kill_rank.py --n 12                the 12 best kills
       python kill_rank.py --check               check the kills the timeline.py uses (problems(), exit 1 on an ERROR)
       python kill_rank.py --no-dupes            skip the duplicate-footage test (dupes.py, minutes on a big folder; dupes.json is reused)

Reads kills.json (+ rows_other.json, dupes.json when they exist) and the clips in src/. Needs: python kills_auto.py <game> first.

Score (points; every term is measured, the reasons are printed with the number)
  multi-kill   +2 per extra kill in a run (kills of one clip less than 5 s apart), at most 2 extra: double 2, triple or more 4; the last kill
               of a run is the one the others lead to (+1)
  flick        camera travel in the 12 frames before the shot (flick.py's net12): 0..1 point, 600 px = 1
  headshot     +2.5   the feed row carries the headshot icon (kills_auto.py: headshot score >= 0.6; Valorant)
  one-tap      +1     no other shot in the 24 frames before K
  audio        +0.5   the gunshot of the clip's own sound is there at K + 0..5 frames, at least 4x the level around it
  confidence   high +1.5, medium 0, low -1, guess -2 (K without a shot signal: +-3 frames)
Weights: set on the kills the worked example kept (62 of 123 ranked kills) and checked on another accepted edit (25 kills, not used for
the fit). Share of the kills with the feature that the edit used: conf high 69% vs 23% without; headshot 58% vs 26%; run of 2+ 57% vs 35%
(a run of 3+ adds nothing: 49% vs 49%); flick 150+ px only 11% vs 52% (the camera swings of spawn and rotation are not the flicks users keep).
  hidden       the target is covered at the shot (ability wall, smoke): score -10, never suggested
  duplicates   the same footage in two files (dupes.py: full recording + its trim, identical copies): only the kill of the
               LONGER recording is listed; the other is "dup of ..." and not ranked

Checks for a finished timeline (problems / --check), each item {severity, code, where, message, fix}:
  ERROR hidden           a kill of the timeline has the target covered (kills.json hidden)
  ERROR not-yours        the feed row after that K is a teammate's / enemy's row or a row where you died (rows_other.json)
  ERROR duplicate        two takes show the same source moment (same clip K+-2, or two files of the same footage)
  ERROR wrong-shot       K is not the killing shot: kills.json has a high-confidence kill 2+ frames away from K (medium: 4+ frames; low/guess: WARN)
  ERROR k-after-row      K lies 2-12 frames after the feed row of a kill of that clip (the row follows the killing shot, never precedes it)
  WARN  unverified       no kill row follows K within 14 frames (kill not detected, or K set by hand): look at it
  WARN  weak-shot        the matching kills.json entry has no shot signal (guess/low): K is +-3 frames
"""
import argparse, glob, json, os, sys, time
import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
STREAK_S = 5.0                 # kills of one clip closer than this belong to one run
FPS = 60.0
NAMES = {2: "double", 3: "triple", 4: "quad"}
FLICK_FULL = 600.0             # net12 (px of the 1920 frame) worth the full 3 points
CONF = {"high": 1.5, "medium": 0.0, "low": -1.0, "guess": -2.0}
FLICK_MAX = 1.0                # points of a full flick: the flick measure did NOT separate the kills the user kept (see Weights)
CLASS = {"high": "high", "medium": "medium", "low": "low", "guess": "guess",           # kills.json of other tools (mykills.py, kill_table.py): ammo / ammo-loose / guess
         "ammo": "high", "ammo-loose": "medium"}
HS_MIN = 0.6
ROW_LAG = (2, 16)              # frames from K to its feed row that still count as "this row belongs to this shot"


# ---------------------------------------------------------------------------------------------- features
def flick_net(clip, K):
    """Camera travel (px of the 1920 frame, straight-line) over the 12 frames before the shot: phase correlation of the world
    region, the same measure as refstyle/flick.py (net12)."""
    import kills_auto
    a = max(0, K - 14)
    fr = kills_auto.read(clip, a, K)
    g = np.stack([cv2.cvtColor(cv2.resize(f, (640, 360), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY) for f in fr]).astype(np.float64)
    x0, x1, y0, y1 = 150, 470, 60, 230
    win = cv2.createHanningWindow((x1 - x0, y1 - y0), cv2.CV_64F)
    sh = np.zeros((len(g), 2))
    for j in range(1, len(g)):
        (dx, dy), r = cv2.phaseCorrelate(g[j - 1, y0:y1, x0:x1], g[j, y0:y1, x0:x1], win)
        if r >= 0.03:
            sh[j] = (dx * 3, dy * 3)
    return float(np.hypot(*sh[max(1, len(g) - 12):].sum(0)))


def streaks(kills):
    """{id: (run length, position in run (1-based), seconds covered by the run)} from the K of kills of the same clip."""
    by = {}
    for i, k in kills.items():
        by.setdefault(k["clip"], []).append((k["K"], i))
    out = {}
    for c, ks in by.items():
        ks.sort()
        run = [ks[0]]
        for q in ks[1:] + [None]:
            if q is not None and (q[0] - run[-1][0]) / FPS < STREAK_S:
                run.append(q)
                continue
            for pos, (K, i) in enumerate(run, 1):
                out[i] = (len(run), pos, (run[-1][0] - run[0][0]) / FPS)
            run = [q] if q is not None else []
    return out


def score(k, run, flick):
    """-> (score, [reasons]) of one kill dict k with its run (n, pos, seconds) and flick travel (px or None)."""
    pts, why = 0.0, []
    n, pos, sec = run
    if n >= 2:
        pts += 2.0 * min(2, n - 1) + (1.0 if pos == n else 0.0)
        why.append(f"{NAMES.get(n, 'ace' if n >= 5 else str(n) + ' kills')} (kill {pos} of {n} in {sec:.1f} s)")
    if flick is not None:
        f = min(FLICK_MAX, FLICK_MAX * flick / FLICK_FULL)
        pts += f
        if f >= 0.5:
            why.append(f"flick {flick:.0f} px")
    if k.get("headshot", 0) >= HS_MIN:
        pts += 2.5
        why.append("headshot")
    if not [c for c in k.get("changes", []) if k["K"] - 24 <= c < k["K"]]:
        pts += 1.0
        why.append("one-tap")
    if k.get("audio_after_K") is not None and (k.get("audio_strength") or 0) >= 4.0:
        pts += 0.5
        why.append("clean gunshot")
    cls = CLASS.get(k.get("conf"), "low")
    pts += CONF[cls]
    if cls in ("low", "guess"):
        why.append(f"K {cls}")
    if k.get("no_shot"):
        pts -= 1.0
        why.append("no shot of yours before the row")
    vis = k.get("visible", {})
    if k.get("hidden"):
        pts -= 10.0
        why.append("HIDDEN (target covered)")
    elif vis.get("covered", 0) >= 1:
        pts -= 1.0
        why.append(f"partly covered ({vis['covered']} of 13 frames)")
    return round(pts, 2), why


# ---------------------------------------------------------------------------------------------- duplicates
def load_dupes(path="dupes.json"):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None


def dedupe(kills, pairs, tol=6):
    """Drop the kills of duplicate footage: -> (kept {id: kill}, [{"id", "dup_of", "clip", "K", "kept_clip", "kept_K"}]).
    A kill of clip B inside the part B shares with A (the longer recording) is the kill of A at the mapped frame; it is dropped
    when A has a kill within `tol` frames of it (else it is kept: A's detector missed it), and an identical copy keeps the first name."""
    import clipio, dupes
    if not pairs:
        return dict(kills), []
    mapping = dupes.groups(pairs)
    kept, dropped = {}, []
    for i, k in sorted(kills.items(), key=lambda q: q[1]["clip"]):
        a, f = dupes.frame_map(k["clip"], k["K"], mapping, clipio.pts)
        if a != k["clip"]:
            twin = [j for j, o in kills.items() if o["clip"] == a and abs(o["K"] - f) <= tol]
            if twin:
                dropped.append({"id": i, "clip": k["clip"], "K": k["K"], "dup_of": twin[0], "kept_clip": a, "kept_K": kills[twin[0]]["K"]})
                continue
        kept[i] = k
    return kept, dropped


# ---------------------------------------------------------------------------------------------- table
def rank(kills, pairs=None, with_flick=True, say=print):
    kept, dropped = dedupe(kills, pairs)
    run = streaks(kept)
    rows = []
    t0 = time.time()
    for n, (i, k) in enumerate(sorted(kept.items(), key=lambda q: (q[1]["clip"], q[1]["K"]))):
        fl = None
        if with_flick and not k.get("hidden"):
            try:
                fl = flick_net(k["clip"], k["K"])
            except (AssertionError, FileNotFoundError, ValueError) as e:
                say(f"  flick of kill {i} ({k['clip']} K={k['K']}) not measured: {str(e)[:80]}")
        sc, why = score(k, run[i], fl)
        rows.append({"id": i, "clip": k["clip"], "K": k["K"], "score": sc, "reasons": why, "conf": CLASS.get(k.get("conf"), "low"), "hidden": bool(k.get("hidden")),
                     "run": list(run[i][:2]), "flick": None if fl is None else round(fl), "headshot": k.get("headshot"),
                     "one_tap": "one-tap" in why})
        if with_flick and n and n % 25 == 0:
            say(f"  {n}/{len(kept)} kills measured ({time.time() - t0:.0f} s)")
    rows.sort(key=lambda r: -r["score"])
    for p, r in enumerate(rows, 1):
        r["rank"] = p
    return rows, dropped


def suggest(rows, n=None, seconds=None, per_kill=1.2, max_per_clip=None):
    """Best kills for a montage: n kills, or as many as fit `seconds` at `per_kill` seconds each. Hidden kills are never taken; a run of
    kills (double ... ace) is taken whole or not at all while it fits; at most max_per_clip kills of one clip when given."""
    if n is None:
        n = max(1, int((seconds or 20.0) / per_kill))
    ok = [r for r in rows if not r["hidden"] and r["conf"] != "guess"]
    picked, per = [], {}
    for r in ok:
        if len(picked) >= n:
            break
        if r in picked or (max_per_clip and per.get(r["clip"], 0) >= max_per_clip):
            continue
        group = [r]
        if r["run"][0] >= 2:                                           # the rest of its run: neighbours in the same clip, same run length
            group = [q for q in ok if q["clip"] == r["clip"] and q["run"][0] == r["run"][0] and abs(q["K"] - r["K"]) / FPS < STREAK_S * r["run"][0]]
            group = [q for q in group if q not in picked]
            if len(picked) + len(group) > n:
                group = [r]
        for q in group:
            picked.append(q)
            per[q["clip"]] = per.get(q["clip"], 0) + 1
    return picked[:n]


def print_table(rows, dropped, top=None):
    print("rank  id    clip  K       score  kill")
    for r in rows[:top]:
        print("%4d  %-5s %-5s %-7d %5.1f  %s" % (r["rank"], r["id"], r["clip"], r["K"], r["score"], ", ".join(r["reasons"]) or "-"))
    for d in dropped:
        print("  dup  %-5s %-5s %-7d        same footage as %s K=%d (kill %s): not ranked" % (d["id"], d["clip"], d["K"], d["kept_clip"], d["kept_K"], d["dup_of"]))


def contact_sheet(rows, kills, path, per=6):
    """kill_rank.jpg: one row per pick: centre crop at K-6, K, K+8 and the feed at K+12; header = rank, id, score, reasons."""
    import clipio, kills_auto
    sheets = []
    for r in rows:
        k = kills[r["id"]]
        K, c = k["K"], k["clip"]
        n = clipio.n_frames(c)
        tiles = []
        for off in (-6, 0, 8):
            f = min(max(K + off, 0), n - 1)
            fr = kills_auto.read(c, f, f)[0]
            t = cv2.resize(fr[324:756, 576:1344], (320, 180), interpolation=cv2.INTER_AREA)
            cv2.putText(t, "K%+d" % off if off else "K", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1, cv2.LINE_AA)
            tiles.append(t)
        f = min(K + 12, n - 1)
        fr = kills_auto.read(c, f, f)[0]
        tiles.append(cv2.resize(fr[84:300, 1300:1916], (320, 180), interpolation=cv2.INTER_AREA))
        head = np.zeros((26, 1280, 3), np.uint8)
        text = "#%d  id %s  %s K=%d  score %.1f  %s" % (r["rank"], r["id"], c, K, r["score"], ", ".join(r["reasons"]))
        cv2.putText(head, text[:120], (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        sheets.append(np.vstack([head, np.hstack(tiles)]))
    if not sheets:
        return []
    names = []
    for s in range(0, len(sheets), per):
        name = path if len(sheets) <= per else path.replace(".jpg", "_%d.jpg" % (s // per + 1))
        cv2.imwrite(name, cv2.cvtColor(np.vstack(sheets[s:s + per]), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])
        names.append(name)
    return names


# ---------------------------------------------------------------------------------------------- checks for a timeline
def used_from_timeline(T):
    """[(clip, K frame (int), beat, level)] of every kill of a timeline module (segments: s["kills"] = [(beat, level)], s["map"](beat)[0] = source frame)."""
    out = []
    for s in T.SEGS:
        for beat, lv in s.get("kills", []):
            out.append((s["clip"], int(round(float(s["map"](beat)[0]))), float(beat), lv))
    return out


def _item(sev, code, where, msg, fix):
    return {"severity": sev, "code": code, "where": where, "message": msg, "fix": fix}


def problems(kills, used, rows_other=None, pairs=None, pts_of=None):
    """Problems of the kills a timeline uses -> list of {severity, code, where, message, fix} (ERROR or WARN); empty = clean.
    kills: kills.json as a dict; used: [(clip, K, ...)] (used_from_timeline); rows_other: rows_other.json (rows that are not your kills,
    {clip: [{"onset", "why"}]}) or None; pairs: dupes.json (list) or None; pts_of: clipio.pts (needed with pairs).
    Rules in the module docstring."""
    out = []
    by = {}
    for i, k in kills.items():
        by.setdefault(k["clip"], []).append((i, k))
    mapping = None
    if pairs and pts_of:
        import dupes
        mapping = dupes.groups(pairs)
    seen = []
    for u in used:
        c, K = u[0], int(u[1])
        where = f"{c} K={K}" + (f" (beat {u[2]:g})" if len(u) > 2 else "")
        near = [(i, k) for i, k in by.get(c, []) if ROW_LAG[0] <= k.get("feed", k["K"] + 8) - K <= ROW_LAG[1] + 4
                and ROW_LAG[0] <= k.get("feed", k["K"] + 8) - k["K"] <= ROW_LAG[1] + 4]      # the rows that can belong to a shot at K (and whose own K is a plausible shot for them: an old entry with a 27 frame lag is not evidence)
        near.sort(key=lambda q: abs(q[1]["K"] - K))
        # same moment used twice (same clip, or the same footage in two files)
        canon = (c, K)
        if mapping:
            import dupes
            canon = dupes.frame_map(c, K, mapping, pts_of)
        for w, (c2, f2) in seen:
            if c2 == canon[0] and abs(f2 - canon[1]) <= 2:
                out.append(_item("ERROR", "duplicate", where, f"the same source moment is already used at {w}" + ("" if c2 == c else f" (same footage: {c} is a copy/trim of {c2})"),
                                 "use another kill, or drop this take"))
                break
        seen.append((where, canon))
        late = [(i, k) for i, k in by.get(c, []) if -12 <= k.get("feed", K + 99) - K <= -2]
        if not near and late:
            i, k = min(late, key=lambda q: abs(q[1]["feed"] - K))
            out.append(_item("ERROR", "k-after-row", where, f"K is {K - k['feed']} frames AFTER the feed row of your kill (kills.json id {i}: row at {k['feed']}, shot at {k['K']}): "
                             "the row appears after the killing shot, so a shot after it is the next shot, not the one that killed",
                             f"set K to {k['K']} (look at the frames {k['K'] - 2}..{k['feed']} to be sure)"))
            continue
        if not near:
            rows = [o for o in (rows_other or {}).get(c, []) if K + ROW_LAG[0] <= o["onset"] <= K + ROW_LAG[1] + 4]
            if rows:
                why = "a row where you died" if rows[0]["why"] == "death" else "a teammate's or an enemy's row"
                out.append(_item("ERROR", "not-yours", where, f"the feed row {rows[0]['onset'] - K} frames after K is {why}, not your kill", "remove this take, or set K to your own kill"))
            else:
                out.append(_item("WARN", "unverified", where, "no kill row of yours appears within 14 frames after K (kills_auto.py did not find this kill, or K was set by hand)",
                                 "look at the frames K-6..K+14 (python kill_rank.py --check writes nothing; use kills_auto.py sheets) or take a detected kill"))
            continue
        i, k = near[0]
        d = K - k["K"]
        cls = CLASS.get(k.get("conf"), "low")
        if k.get("hidden"):
            out.append(_item("ERROR", "hidden", where, f"the target is covered at the shot (kills.json id {i}: ability wall / smoke / full-screen colour over the aim area)",
                             "use another kill, or end the take before it"))
        if abs(d) >= 2:
            sev = "ERROR" if cls == "high" or (cls == "medium" and abs(d) >= 4) else "WARN"      # medium = flash+audio only: a knife / ability kill can be 3 frames off
            out.append(_item(sev, "wrong-shot", where, f"K is {abs(d)} frames {'after' if d > 0 else 'before'} the killing shot of kills.json id {i} (K={k['K']}, {k.get('conf', '?')}, "
                                                        f"{k.get('method', 'no method recorded')}; its feed row appears at {k.get('feed', '?')})", f"set K to {k['K']}, unless you checked frame by frame that {K} is the shot that killed"))
        elif cls in ("guess", "low"):
            out.append(_item("WARN", "weak-shot", where, f"kills.json id {i} has no reliable shot signal ({k.get('conf', '?')}): K is +-3 frames"
                             + (" and no bullet was fired for its feed row (ability / knife kill, or not a gun kill)" if k.get("no_shot") else ""), "look at the frames around K"))
    return out


def check_timeline(T, kills_path="kills.json", rows_path="rows_other.json", dupes_path="dupes.json"):
    """problems() for the timeline module T with the files of the project folder. Missing kills.json -> one WARN (nothing can be checked)."""
    used = used_from_timeline(T)
    if not os.path.exists(kills_path):
        return [_item("WARN", "no-kills", "kills.json", f"{kills_path} is missing: the kills of the timeline cannot be verified", "python kills_auto.py <game>")]
    kills = json.load(open(kills_path, encoding="utf-8-sig"))
    rows = json.load(open(rows_path, encoding="utf-8")) if os.path.exists(rows_path) else None
    pairs = load_dupes(dupes_path)
    import clipio
    return problems(kills, used, rows, pairs, clipio.pts)


def format_problems(ps):
    return "\n".join("  %s %-10s %s: %s\n        fix: %s" % (p["severity"], p["code"], p["where"], p["message"], p["fix"]) for p in ps)


# ---------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="rank the kills of kills.json; suggest the best N for X seconds; check a timeline's kills")
    ap.add_argument("--kills", default="kills.json")
    ap.add_argument("--n", type=int, help="suggest this many kills")
    ap.add_argument("--seconds", type=float, help="suggest as many kills as fit this many seconds")
    ap.add_argument("--per-kill", type=float, default=1.2, help="seconds one kill takes in the montage (default 1.2)")
    ap.add_argument("--max-per-clip", type=int)
    ap.add_argument("--top", type=int, default=40, help="rows of the table to print (default 40; all are in kill_rank.json)")
    ap.add_argument("--no-dupes", action="store_true")
    ap.add_argument("--no-flick", action="store_true")
    ap.add_argument("--check", action="store_true", help="check the kills timeline.py uses; exit 1 on an ERROR")
    ap.add_argument("--out", default="kill_rank.json")
    args = ap.parse_args()
    if args.check:
        import preflight
        T = preflight.timeline()
        ps = check_timeline(T)
        print(format_problems(ps) or "kill_rank: every kill of timeline.py checks out")
        sys.exit(1 if any(p["severity"] == "ERROR" for p in ps) else 0)
    if not os.path.exists(args.kills):
        sys.exit(f"kill_rank.py: {args.kills} not found in {os.getcwd()}: run  python kills_auto.py <game>  first")
    kills = json.load(open(args.kills, encoding="utf-8-sig"))
    if not kills:
        sys.exit(f"kill_rank.py: {args.kills} has no kills")
    t0 = time.time()
    pairs = None
    if not args.no_dupes:
        clips = sorted({k["clip"] for k in kills.values()})
        pairs = load_dupes()
        if pairs is None and len(clips) > 1:
            import dupes
            print(f"looking for duplicate footage in {len(clips)} clips (dupes.py) ...", flush=True)
            pairs = dupes.find([(c, glob.glob(f"src/{glob.escape(c)}.*")[0]) for c in clips])
            json.dump(pairs, open("dupes.json", "w", encoding="utf-8"), indent=1)
            dupes.report(pairs)
    rows, dropped = rank(kills, pairs, with_flick=not args.no_flick)
    print_table(rows, dropped, args.top)
    res = {"kills": rows, "duplicates_dropped": dropped}
    if args.n or args.seconds:
        pick = suggest(rows, args.n, args.seconds, args.per_kill, args.max_per_clip)
        res["suggest"] = {"n": len(pick), "seconds": round(len(pick) * args.per_kill, 1), "ids": [r["id"] for r in pick]}
        print("\nbest %d kills for %.0f s (%.1f s each): ids %s" % (len(pick), len(pick) * args.per_kill, args.per_kill, ", ".join(r["id"] for r in pick)))
        sheet = contact_sheet(pick, kills, "kill_rank.jpg")
    else:
        sheet = contact_sheet(rows[:12], kills, "kill_rank.jpg")
    json.dump(res, open(args.out, "w", encoding="utf-8"), indent=1)
    print(f"\n{args.out}: {len(rows)} kills ranked, {len(dropped)} duplicates dropped; contact sheet {', '.join(sheet)} ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
