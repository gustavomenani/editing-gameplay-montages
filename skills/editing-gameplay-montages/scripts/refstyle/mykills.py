"""Kill table for this project: the frame K to put on the beat for every detected kill.

Kills were found on the kill feed (detections.json: file + time the feed row appears). The shot frame K is the frame where the
HUD ammo counter steps (it does so on the frame of the shot) and the muzzle flash starts; the feed row shows up 6-8 frames later (5..12
accepted). The step is found on ANY digit colour (the counter turns red at low ammo: a white-pixel mask saw nothing there, K fell back to
"feed - 8" and was a frame early in 60 % of those kills) by kverify.py, the same code that checks a finished timeline. The gallery lets
the editor confirm K: the muzzle flash / recoil must start on the tile "+0" and be absent on "-1".

usage: python mykills.py [id,id,...]     -> kills.json  {id: {clip, K, feed, how, conf, verified, ...}},  gal_NN.jpg (7 kills per sheet)
Row layout: full frame at K-12, K-6, K-2 | zoom on the weapon at K-1, K, K+1 | full frame at K, K+4, K+10

kills.json fields (the drafters read them):
  how        "ammo"        ammo step on K and no contradicting signal on K-1 / K+1, the feed row 5..12 frames after K   VERIFIED
             "flash"       muzzle flash starts on K (the counter shows no step)                                          VERIFIED
             "ammo-loose"  a step / flash exists but the feed row is not 5..12 frames after it, or a signal on K+-1     unverified
             "guess"       nothing found: K = feed - 7 (the median lag; was 8, right in 8 % of the cases)               unverified
  conf       "high" (ammo step AND flash on K) | "medium" (one of them) | "low" (ammo-loose) | "guess"
  verified   true for how ammo / flash. An unverified K needs a look (strip.py, python kverify.py kills.json --ids N) before it goes
             into a plan; "k_checked": true in the plan entry says you did (the drafter refuses it otherwise).
  changes    every ammo step / flash start of the 40 frames before the feed row (flick.py reads it)"""
import json, os, sys
import numpy as np
import cv2
import clipio
import kverify

CL = json.load(open("clips.json", encoding="utf-8-sig"))
F2C = {os.path.basename(p): c for c, p in CL.items()}
DET = json.load(open("detections.json"))
BAD = set()         # set per project: detection ids rejected on the review sheets
only = set(int(x) for x in sys.argv[1].split(",")) if len(sys.argv) > 1 else None
PROF = kverify.load_profile("valorant")
TYPICAL_LAG = 7     # frames from the shot to its feed row: median of 25 kills measured frame by frame (6: 5x, 7: 15x, 8: 2x, 9-11: 1x each)
out = json.load(open("kills.json")) if os.path.exists("kills.json") else {}
_auto = [i for i, v in out.items() if "method" in v]          # entries of kills_auto.py (another layout, numbered from 0 like these)
for i in _auto:
    del out[i]
if _auto:
    print("kills.json held %d entries written by kills_auto.py: dropped, they are not detection ids of this project" % len(_auto))
_old = [i for i, v in out.items() if "how" not in v]          # written by an older mykills.py (conf ammo / ammo-loose / guess, white-digit rule)
for i in _old:                                                # NOT measured by the new detector: unverified until it has been (same as kverify.py --update)
    out[i]["how"] = out[i].get("conf") if out[i].get("conf") in ("ammo-loose", "guess") else "guess"
    out[i]["conf"] = {"ammo-loose": "low"}.get(out[i]["how"], "guess")
    out[i]["verified"] = False
if _old:
    print("%d older entries of kills.json (not in this run) are kept as UNVERIFIED (how %s): run mykills.py without ids, or kverify.py kills.json --update, to measure them" % (len(_old), "guess / ammo-loose"))
rows, sheet, missing = [], 0, set()
order = sorted([k for k in DET if k["id"] not in BAD and (only is None or k["id"] in only)],
               key=lambda k: (list(only).index(k["id"]) if only and False else k["id"]))
if only:
    ids = [int(x) for x in sys.argv[1].split(",")]
    order.sort(key=lambda k: ids.index(k["id"]))
for k in order:
    c = F2C.get(k["file"])
    if c is None:
        missing.add(k["file"])
        continue
    p = clipio.pts(c)
    fi = int(np.argmin(np.abs(p - k["t"])))       # frame where the feed row is first complete
    a, b = max(0, fi - 40), min(len(p) - 1, fi + 14)
    fr = clipio.read_frames(c, a, b, crop=False)
    sg = kverify.signals(fr, PROF)
    ev = kverify.evidence(sg)                     # per frame: A ammo step (any digit colour), F muzzle-flash start, a / f weaker peaks
    fl = fi - a
    # a shot = the counter steps AND the flash starts on the same frame: both clean (4), one of them a weaker peak (3); a step alone >= 10 (2)
    # or weaker (1); a flash start alone (0). The marks: A / a ammo step / peak, F / f flash start / peak. A spray's gun jitter makes lone
    # steps and peaks everywhere and the follow-up shot of a spray often shows A + f: the clean pair (AF) is the shot, measured on 6 kills
    # whose true shot (lag 7-10) lost to a follow-up at lag 4-6 when both ranked 3.
    def rank(i):
        m, ad = ev[i], sg["ammo"][i] if sg["ammo"] is not None else 0.0
        if "A" in m and "F" in m:
            return 4
        return 3 if (("A" in m or "a" in m) and ("F" in m or "f" in m)) else 2 if "A" in m and ad >= 10 else 1 if "A" in m else 0
    cands = [i for i in range(1, len(fr) - 1) if "A" in ev[i] or "F" in ev[i] or ("a" in ev[i] and "f" in ev[i])]
    rk = {i: rank(i) for i in cands}
    shots = cands
    if any(rk[i] >= 1 for i in cands if 2 <= fl - i <= 30):
        # The counter steps somewhere in the window: the shot is one of its steps. A bright start without a step is not a shot
        # (the enemy's outline lighting up at the crosshair gave a "flash" 14 frames after the real shot, #11 of the ghost clip).
        # Flash-only starts count only when the counter never steps in the window (hidden, or a weapon without one).
        shots = [i for i in cands if rk[i] >= 1]
    kl, how = None, "guess"
    # Order of preference: a strong shot (step >= 10 or a flash) at the usual lag (5..12 frames before the row); a CLEAN pair (step + flash)
    # at any lag 2..30 (a kill whose row comes late: slow bullet, damage after the shot) -> "ammo-loose"; a weak step at the usual lag;
    # anything else at any lag; a flash start alone last. Inside a pool: the best evidence, then the lag nearest the median, then the later shot.
    for lo, hi, h, r in ((5, 12, "ammo", 2), (2, 30, "ammo-loose", 3), (5, 12, "ammo", 1), (2, 30, "ammo-loose", 1), (5, 12, "ammo", 0), (2, 30, "ammo-loose", 0)):
        pool = [i for i in shots if lo <= fl - i <= hi and rk[i] >= r]
        if pool and kl is None:
            kl, how = max(pool, key=lambda i: (rk[i], -abs((fl - i) - TYPICAL_LAG), i)), h
    if kl is None:
        kl = max(0, fl - TYPICAL_LAG)
    K = a + kl
    res = kverify.judge(kverify.from_signals(sg, a, K))
    conf, note = "guess", ""
    if how == "ammo":
        if res["verdict"] == "verified":                     # the same test kverify.py applies to a timeline: signal ON K, none on K-1
            how, conf = res["how"], res["conf"]
        else:
            how, conf, note = "ammo-loose", "low", "  (kverify: %s)" % res["why"]
    elif how == "ammo-loose":
        conf = "low"
    out[str(k["id"])] = {"clip": c, "K": int(K), "feed": int(fi), "how": how, "conf": conf, "verified": how in ("flash", "ammo"), "file": k["file"],
                         "changes": [int(a + i) for i in cands]}
    print("#%-3d %s K=%d (feed %d, lag %d) %s/%s  shots at K%s%s" % (
        k["id"], c, K, fi, fi - K, how, conf, [int(a + i - K) for i in cands], note), flush=True)

    def full(off):
        j = min(max(kl + off, 0), len(fr) - 1)
        t = cv2.resize(fr[j], (320, 180), interpolation=cv2.INTER_AREA)
        return lab(t, "%+d" % off)

    def zoom(off):
        j = min(max(kl + off, 0), len(fr) - 1)
        t = cv2.resize(fr[j][330:780, 760:1560], (320, 180), interpolation=cv2.INTER_AREA)
        return lab(t, "zoom %+d" % off)

    def lab(t, s):
        t = np.ascontiguousarray(t)
        cv2.rectangle(t, (0, 160), (86, 180), (0, 0, 0), -1)
        cv2.putText(t, s, (3, 175), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        return t

    row = np.hstack([full(-12), full(-6), full(-2), zoom(-1), zoom(0), zoom(1), full(0), full(4), full(10)])
    s = "#%d %s K=%d %s/%s" % (k["id"], c, K, how, conf)
    cv2.rectangle(row, (0, 0), (len(s) * 11 + 8, 22), (0, 0, 0), -1)
    cv2.putText(row, s, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 2)
    rows.append(row)
    if len(rows) == 7:
        sheet += 1
        cv2.imwrite("gal_%02d.jpg" % sheet, cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 86])
        rows = []
if rows:
    sheet += 1
    cv2.imwrite("gal_%02d.jpg" % sheet, cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 86])
json.dump(out, open("kills.json", "w"), indent=1)
print("kills.json: %d kills; sheets gal_01..gal_%02d.jpg" % (len(out), sheet))
if missing:
    print("NOT in clips.json, so their kills were skipped (add them, run ingest.py and mkpts.py, then this again):")
    for f in sorted(missing):
        print("   ", f)
