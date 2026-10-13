"""Writes a correct first draft of a house-style timeline.py from measured inputs; you then read it, look at the stills
and tweak it (edit-design.md). It does the arithmetic that hand-written timelines get wrong: every kill on a measured
kick or snare, every transition on a kick (CUTS_ON "bass") or with the kill rhythm ("kills"), the next kill at least
1.5 beats after a transition centre, lead() / tail() shapes, the bullet time that reaches the last kill at real speed,
the numbering of the music block, anchors inside the clips, speeds inside sane bounds.

usage (from the project folder, after ingest.py and mkpts.py, with a plan.json):
    $PY draft_timeline.py plan.json                  -> timeline.py, plus an explanation of every segment
    $PY draft_timeline.py plan.json -o draft.py      -> another file (a timeline.py that you edited is never
                                                        overwritten without --force)
    $PY draft_timeline.py plan.json --compare timeline_example.py    statistics of the draft next to another timeline

plan.json:
  {"music": "src/music.flac",          # default src/music.*
   "bpm": 130, "beat0": 0.4613,        # from music_grid.py
   "drop_beat": 63,                    # TRACK beat of the drop / section start (music_tempo.py lists them): the first kill
                                       # lands on it, M0 = drop_beat + 1 (the drop is timeline beat -1)
   "cuts_on": "bass",                  # "bass" (default) or "kills": the briefing's choice
   "length": 24,                       # seconds the user asked for; the draft lands within length_tolerance of it
   "length_tolerance": 0.10,           # optional, default 0.10 (a fraction of length)
   "lead_in": 4.2,                     # optional: beats of lead-in before the first kill (the riser runs over it)
   "final": "auto",                    # optional: "auto" | "bullet" | "tail": how the last kill is played (see below)
   "kills": [                          # in the order they play; clip names are the keys of clips.json
     {"clip": "c10", "K": 5362, "level": 3},                   # K = muzzle-flash frame (kills.json / kill_table.py)
     {"clip": "c10", "K": 5474, "continuous": true},            # same take as the previous kill: one speed ramp between
     {"clip": "c18", "K": 1305, "level": 2},                    # finisher: slow motion after the shot
     {"clip": "c14", "K": 7794, "level": 3, "end_card": 7894}   # last kill; end_card = frame of the ACE banner (default K + 100)
   ]}
Per kill: "level" 1 (default for the middle ones), 2 (slow-motion finisher, ends its take), 3 (opening and last kill only:
default for them); "continuous" (needs the same clip, a later K, and level 1 on the kill before it); "lag" (frames the
gunshot trails the picture, kill_lags.py measures it; default 2.0, a placeholder); "end_card" (last kill only);
"id" instead of "clip" and "K": {"id": 96} takes both from kills.json (a 'guess' / 'ammo-loose' kill is reported).

What it decides, from the music (beat_hits.py: the measure of music_pulses.py) and the clips' lengths (pts/):
  * the first kill on the drop (beat -1) with `lead_in` beats of fast-forwarded lead-in and a riser, slow motion after it;
  * every other kill on a kick (low >= 0.5) or a snare (mid >= 0.6), spread so that the edit lasts `length`;
  * cuts between takes on kicks that carry no kill (CUTS_ON "bass") or free (0.1 beat grid, "kills"), always at least
    1.5 beats before the next kill, 0.5 beat of real time after a normal kill before the transition starts;
  * speeds: lead-ins 1.0 to 1.5x (the longer the lead-in, the closer to real time), speed ramps between continuous
    kills 0.9 to 3.7x on average (peaks stay under 4.6x), slow motion 0.28x, bullet time 0.18x, nothing outside 0.15x .. 4.6x;
  * the last kill: on a bass re-entry after a break (no kick in the 3 beats before) it comes in as bullet time with the
    music low-passed (SWEEP) and a second riser; otherwise a normal lead-in. Then an end card that only fades to black;
  * transitions: whip / zoom / spin on a change of clip, in rotating directions; zcut inside one clip; dissolve into
    bullet time; soft into the end card;
  * R0 / R1 / FADE_OUT / M0, PULSES (every strong hit without a kill or transition), RISERS, SWEEP.

It refuses, with the numbers, when the inputs cannot fit: too few kicks or snares, a clip without enough footage before
or after a kill, a length that the kills cannot fill. The file is built from timeline_example.py by replacing the blocks
between its `# >>> draft:...` / `# <<< draft:...` markers (docstring, music block, sound block, segments). The `lag` values
are placeholders until kill_lags.py has measured them. Few kills for a long edit give long lead-ins and long slow motion:
the statistics it prints (against the house example with --compare) say so."""
import argparse, bisect, collections, hashlib, json, math, os, re, sys
import numpy as np
import preflight                                  # a clear message when this is not the project's Python
import clipio
import beat_hits

SETTLE = 0.5            # lead(): real time for the last half beat before a kill
MARGIN = 6              # frames of safety inside a clip (shutter, transition overlap)
LEAD_MIN, LEAD_MAX, LEAD_PREF = 1.5, 8.0, 2.2
EXT = 1.25              # speed of the fast-forward that fills a long post-kill stretch
SLOW = 0.28             # tail(): slow-motion speed
BULLET = 0.18           # bullet(): slow-motion speed
KILL_LOW, KILL_MID = 0.5, 0.6          # a hit may carry a kill (music_pulses.py flags < 0.25 / 0.4)
CUT_LOW = 0.5                          # a hit may carry a transition in "bass" (music_pulses.py wants >= 0.4)
TAIL_HOLD = 0.25        # real time after the shot before slowing
TAIL = {2: (1.5, 3.4, 2.2), 3: (2.4, 3.6, 2.8)}      # (min, max, preferred) beats of a finisher's slow tail
TAIL_FINAL = {2: (1.5, 3.4, 2.2), 3: (2.2, 3.6, 2.6)}
RUN_MAX = 3.0           # real time after a finisher's tail, when the next kick is further away than the tail's maximum
CARD = (3.5, 6.5)       # beats of the end card after the final transition's centre
SOFT = 1.2
ROT = [("whip", 0.7, (1, 0)), ("zoom", 0.6), ("whip", 0.7, (-1, 0)), ("spin", 0.8, (1, 0)), ("whip", 0.7, (0, -1)),
       ("zoom", 0.7), ("whip", 0.7, (0, 1)), ("whip", 0.7, (-1, 0))]
MAXGAP = 16.0


def die(errors, what="cannot draft this plan"):
    if isinstance(errors, str):
        errors = [errors]
    sys.exit("draft_timeline.py %s:\n  - %s\nNothing was written. Fix plan.json (or the inputs) and run it again." % (what, "\n  - ".join(errors)))


def fnum(x, nd=4, keep=False):
    s = ("%.*f" % (nd, x)).rstrip("0").rstrip(".")
    s = "0" if s in ("-0", "") else s
    return s + ".0" if keep and "." not in s else s


# ------------------------------------------------------------------------------------------------ the plan
def load_plan(path):
    try:
        P = json.load(open(path, encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        die("%s cannot be read as JSON (%s)" % (path, e), "cannot read the plan")
    E = []
    for key in ("bpm", "beat0", "drop_beat", "length", "kills"):
        if key not in P:
            E.append('plan.json has no "%s"' % key)
    if E:
        die(E)
    P.setdefault("cuts_on", "bass")
    P.setdefault("length_tolerance", 0.10)
    P.setdefault("lead_in", 4.2)
    P.setdefault("final", "auto")
    if P["cuts_on"] not in ("bass", "kills"):
        E.append('"cuts_on" must be exactly "bass" or "kills", not %r' % (P["cuts_on"],))
    if P["final"] not in ("auto", "bullet", "tail"):
        E.append('"final" must be "auto", "bullet" or "tail", not %r' % (P["final"],))
    music = P.get("music")
    if not music:
        import glob
        hits = sorted(glob.glob("src/music.*"))
        music = hits[0].replace("\\", "/") if hits else "src/music.flac"
    P["music"] = music
    if not os.path.isfile(music):
        E.append("the song %s does not exist: run ingest.py (clips.json key \"music\") or set \"music\" in plan.json" % music)
    if not (P["bpm"] > 0 and P["beat0"] >= 0 and P["length"] >= 8 and 3.0 <= P["lead_in"] <= 8.0):
        E.append("bpm must be > 0, beat0 >= 0, length >= 8 seconds and lead_in between 3 and 8 beats")
    ks = P["kills"]
    if not isinstance(ks, list) or len(ks) < 2:
        E.append("a draft needs at least 2 kills (the opening one on the drop and the last one)")
        die(E)
    kills = []
    for i, k in enumerate(ks):
        tag = "kill #%d" % (i + 1)
        if "id" in k:                                  # {"id": 96}: clip and K from kills.json
            try:
                e = json.load(open("kills.json", encoding="utf-8-sig")).get(str(k["id"]))
            except (OSError, ValueError) as ex:
                E.append("%s: \"id\" needs kills.json in this folder (%s)" % (tag, ex))
                continue
            if not e:
                E.append("%s: kills.json has no entry %r" % (tag, k["id"]))
                continue
            k = dict(k, clip=k.get("clip", e["clip"]), K=k.get("K", e["K"]))
            if e.get("conf") in ("guess", "ammo-loose"):
                print("note: %s (kills.json %s) has confidence %r: look at its flash frame before trusting it" % (tag, k["id"], e["conf"]))
        if "clip" not in k or "K" not in k:
            E.append('%s needs "clip" and "K" (or an "id" of kills.json)' % tag)
            continue
        try:
            n = clipio.n_frames(k["clip"])
        except FileNotFoundError as e:
            E.append("%s: %s" % (tag, e))
            continue
        K = int(k["K"])
        if not 0 <= K <= n - 1:
            E.append("%s: K = %d is outside clip %s (frames 0..%d)" % (tag, K, k["clip"], n - 1))
        last = i == len(ks) - 1
        cont = bool(k.get("continuous", False))
        lv = k.get("level")
        if lv is None:
            nxt_cont = i + 1 < len(ks) and bool(ks[i + 1].get("continuous", False))
            lv = 3 if (i == 0 or last) and not nxt_cont else 1
        if lv not in (1, 2, 3):
            E.append("%s: level must be 1, 2 or 3" % tag)
        if lv == 3 and not (i == 0 or last):
            E.append("%s: level 3 (impact frame) is for the opening and the last kill only (edit-design.md); use 2 for a finisher" % tag)
        if i == 0 and cont:
            E.append("kill #1 cannot be continuous: it has no kill before it")
        if cont and kills:
            p = kills[-1]
            if p["clip"] != k["clip"]:
                E.append("%s is continuous with kill #%d but they are in different clips (%s, %s)" % (tag, i, p["clip"], k["clip"]))
            elif K <= p["K"]:
                E.append("%s is continuous with the kill before it but its K = %d is not after K = %d: a take plays forward; "
                         "reorder the kills or drop the flag" % (tag, K, p["K"]))
            if p["level"] != 1:
                E.append("%s is continuous but the kill before it is level %d: a level 2 / 3 finisher ends its take (the zoom "
                         "stays in); give that kill level 1 or drop the flag" % (tag, p["level"]))
        if "end_card" in k and not last:
            E.append('%s: "end_card" belongs to the last kill' % tag)
        kills.append(dict(i=i, clip=k["clip"], K=K, n=n, level=lv, cont=cont, lag=float(k.get("lag", 2.0)),
                          card=k.get("end_card"), has_lag="lag" in k))
    if E:
        die(E)
    return P, kills


# ------------------------------------------------------------------------------------------------ the planner
def lead_fasts(L):
    """Fast-forward speeds to try for a lead-in of L beats: the longer, the nearer to real time."""
    f = round(max(1.15, 1.5 - 0.14 * max(0.0, L - 2.5)), 2)
    return [f] + [x for x in (1.35, 1.2, 1.0) if x < f]


def tail_len(lv, T, final):
    """(slow tail beats, real-time run-out beats) for a finisher whose take ends T beats after the shot, or None"""
    lo, hi, pref = (TAIL_FINAL if final else TAIL)[lv]
    if T < lo - 1e-9 or T > hi + RUN_MAX + 1e-9:
        return None
    return (T, 0.0) if T <= hi + 1e-9 else (pref, round(T - pref, 4))


class Planner:
    def __init__(self, P, kills, rows, R0, window, final_mode):
        self.P, self.kills, self.N = P, kills, len(kills)
        self.per = 60.0 / P["bpm"]
        self.F = 60 * self.per
        self.bass = P["cuts_on"] == "bass"
        self.R0, self.window = R0, window
        self.low = {r[0]: r[1] for r in rows}
        self.mid = {r[0]: r[2] for r in rows}
        beats = sorted(self.low)
        self.kp = [b for b in beats if -1.0 <= b <= window - 6.0 and (self.low[b] >= KILL_LOW or self.mid[b] >= KILL_MID)]
        self.kicks = [b for b in beats if self.low[b] >= CUT_LOW]
        self.final_mode = final_mode
        self.kinds = self._kinds()

    # -- music helpers
    def st(self, p):
        return max(self.low.get(p, 0.0), self.mid.get(p, 0.0))

    def reentry(self, p):
        """a bass re-entry: a kick at p and no kick in the three beats before it"""
        if self.low.get(p, 0.0) < KILL_LOW:
            return False
        return not any(self.low.get(p - 0.5 * j, 0.0) >= 0.4 for j in range(1, 7))

    def bullet_ok(self, p):
        return self.final_mode != "tail" and not self.kills[-1]["cont"] and self.reentry(p)

    def kill_cost(self, p):
        return 0.8 * (1.0 - self.st(p))

    # -- transition kinds (decided before the positions: they depend on the clips only)
    def _kinds(self):
        kinds, j = {}, 0
        for i in range(1, self.N):
            if self.kills[i]["cont"]:
                continue
            if self.kills[i]["clip"] == self.kills[i - 1]["clip"]:
                kinds[i] = ("zcut", 0.0)
            else:
                kinds[i] = ROT[j % len(ROT)]
                j += 1
        return kinds

    def kind_into(self, i, bullet):
        return ("dissolve", 0.5) if i == self.N - 1 and bullet else self.kinds[i]

    # -- footage arithmetic and costs
    def lead_option(self, K, L, d, bullet=False, fasts=None):
        """lead-in of L beats into a kill at frame K after a transition of length d: -> (cost, fast) or None"""
        F = self.F
        if bullet:
            if not 4.5 <= L <= LEAD_MAX + 1e-9:
                return None
            need = (L - 1) * F * BULLET + 0.36 * F + 1 + d / 2 * F * BULLET
            return (0.35 * (L - 5.5) ** 2, None) if K - need >= MARGIN else None
        if not LEAD_MIN - 1e-9 <= L <= LEAD_MAX + 1e-9:
            return None
        for f in fasts or lead_fasts(L):
            need = SETTLE * F + (L - SETTLE) * F * f + d / 2 * F * f
            if K - need >= MARGIN:
                return 0.35 * (L - LEAD_PREF) ** 2 + (0.8 * (L - 4.5) ** 2 if L > 4.5 else 0.0), f
        return None

    def end_option(self, kill, T, d, final=False):
        """The take ends T beats after `kill`, a transition of length d centred there.
        -> (cost, frames from K to the end anchor, frames needed in all, spec) or None"""
        F, lv = self.F, kill["level"]
        dh = d / 2
        if lv == 1:
            x = T - dh
            if T < 0.5 + max(dh, 0.3) - 1e-9 or x > 6.0 + 1e-9:
                return None
            cost = (x - 1.0) ** 2 if x <= 1.5 else 0.25 + 0.3 * (x - 1.5) ** 2
            if T <= 1.5 + dh + 1e-9:
                run, tot, spec = T * F, T * F + dh * F, ("hold", T)
            else:
                run = 1.0 * F + (T - 1.0) * F * EXT
                tot, spec = run + dh * F * EXT, ("holdx", T)
        else:
            tl = tail_len(lv, T, final)
            if tl is None:
                return None
            Tt, run_t = tl
            out = 0.4
            out_rate = 0.75 if (run_t > 0 or d == 0) else 0.3
            mid = Tt - TAIL_HOLD - out
            run = (TAIL_HOLD + mid * SLOW + out * out_rate + run_t) * F
            tot = run + dh * F * (1.0 if run_t > 0 else out_rate)
            pref = (TAIL_FINAL if final else TAIL)[lv][2]
            cost = 0.35 * (Tt - pref) ** 2 + ((0.3 + 0.12 * run_t * run_t) if run_t > 0 else 0.0)
            spec = ("tail", Tt, out_rate, run_t)
        if kill["K"] + tot > kill["n"] - 1 - MARGIN:
            return None
        return cost, run, tot, spec

    def cut_candidates(self, lo, hi):
        if hi < lo - 1e-9:
            return []
        if self.bass:
            a, b = bisect.bisect_left(self.kicks, lo - 1e-9), bisect.bisect_right(self.kicks, hi + 1e-9)
            return self.kicks[a:b]
        return [j / 10.0 for j in range(int(math.ceil(lo * 10 - 1e-6)), int(math.floor(hi * 10 + 1e-6)) + 1)]

    def max_after(self, kill, final=False):
        return 6.0 + (SOFT if final else 0.7) / 2 if kill["level"] == 1 else (TAIL_FINAL if final else TAIL)[kill["level"]][1] + RUN_MAX

    # -- one pair of consecutive kills
    def pair(self, ia, pa, pb):
        """-> (cost, detail) or None. Between kill ia (at beat pa) and kill ia + 1 (at pb)."""
        a, b = self.kills[ia], self.kills[ia + 1]
        F = self.F
        g = pb - pa
        if b["cont"]:
            D = b["K"] - a["K"]
            best = None
            for h in (1.0, 0.5):
                mb = g - h - SETTLE
                mf = D - (h + SETTLE) * F
                if mb < 0.5 - 1e-9 or mf <= 0:
                    continue
                sm = mf / (mb * F)
                if 0.9 <= sm <= 3.7:
                    cost = 2.5 * math.log(sm / 1.2) ** 2 + (0.3 if h < 1 else 0.0)
                    if best is None or cost < best[0]:
                        best = (cost, dict(type="cont", mode="full", h=h, sm=sm))
            sd = D / (g * F) if g > 0 else 0
            if g <= 2.0 + 1e-9 and 0.78 <= sd <= 1.3:           # close kills: one constant speed; further apart they reach the kill at real speed
                cost = 4 * math.log(sd) ** 2 + 0.2
                if best is None or cost < best[0]:
                    best = (cost, dict(type="cont", mode="direct", sd=sd))
            return best
        bullet = ia + 1 == self.N - 1 and self.bullet_ok(pb)
        kind = self.kind_into(ia + 1, bullet)
        d = kind[1] if kind[0] != "zcut" else 0.0
        dh = d / 2
        best = None
        for c in self.cut_candidates(pa + 0.5 + max(dh, 0.3), min(pa + self.max_after(a), pb - LEAD_MIN)):
            T, L = c - pa, pb - c
            e = self.end_option(a, T, d)
            if e is None:
                continue
            l = self.lead_option(b["K"], L, d, bullet)
            if l is None:
                continue
            cost = e[0] + l[0]
            if best is None or cost < best[0]:
                best = (cost, dict(type="cut", c=c, T=T, L=L, f=l[1], end=e[3], kind=kind, bullet=bullet, d=d))
        return best

    def terminal(self, p, R1_t, R1_lo, R1_hi):
        """The last kill at p: the end of its take (the cut to the end card) and R1. -> (cost, detail) or None"""
        k = self.kills[-1]
        F = self.F
        out = None
        for e in self.cut_candidates(p + 0.5 + SOFT / 2, p + self.max_after(k, True)):
            T = e - p
            en = self.end_option(k, T, SOFT, final=True)
            if en is None:
                continue
            lo, hi = max(e + CARD[0], R1_lo), min(e + CARD[1], R1_hi)
            if lo > hi + 1e-9:
                continue
            R1 = min(max(round(min(max(R1_t, lo), hi), 1), lo), hi)
            card_f = (R1 - e + SOFT / 2) * F * 0.31
            E0 = k["card"] if k["card"] is not None else min(k["K"] + 100, k["n"] - 1 - MARGIN - card_f)
            if E0 < k["K"] + en[1] + 3 or E0 + card_f > k["n"] - 1 - MARGIN:
                continue
            cost = en[0] + 0.05 * (R1 - R1_t) ** 2 + 0.1 * (R1 - e - 4.6) ** 2
            if out is None or cost < out[0]:
                out = (cost, dict(e=e, T=T, end=en[3], R1=R1, E0=int(E0), card_f=card_f))
        return out

    # -- the search: dp[i][p] = (cost, previous position) with kill i on beat p
    def run(self):
        N = self.N
        dp = [dict() for _ in range(N)]
        if -1.0 in self.kp:
            dp[0][-1.0] = (self.kill_cost(-1.0), None)
        for i in range(1, N):
            for pa, (ca, _) in dp[i - 1].items():
                for pb in self.kp:
                    if pb <= pa or pb - pa > MAXGAP:
                        continue
                    br = i == N - 1 and self.bullet_ok(pb)
                    if i == N - 1 and self.final_mode == "bullet" and not br:
                        continue
                    r = self.pair(i - 1, pa, pb)
                    if r is None:
                        continue
                    cost = ca + r[0] + self.kill_cost(pb) - (1.5 if br else 0.0)
                    if pb not in dp[i] or cost < dp[i][pb][0]:
                        dp[i][pb] = (cost, pa)
        self.dp = dp

    def pick(self, R1_t, R1_lo, R1_hi):
        best = None
        for p, (c, _) in self.dp[-1].items():
            t = self.terminal(p, R1_t, R1_lo, R1_hi)
            if t is not None and (best is None or c + t[0] < best[0]):
                best = (c + t[0], p, t[1])
        return best

    def reach(self):
        """(shortest, longest) R1 any placement of the kills allows"""
        lo = hi = None
        for p in self.dp[-1]:
            t = self.terminal(p, 0, self.R0, self.window)
            if t is None:
                continue
            e = t[1]["e"]
            lo = e + CARD[0] if lo is None else min(lo, e + CARD[0])
            hi = min(e + CARD[1], self.window) if hi is None else max(hi, min(e + CARD[1], self.window))
        return lo, hi

    def backtrack(self, p_last):
        pos = [p_last]
        for i in range(self.N - 1, 0, -1):
            pos.append(self.dp[i][pos[-1]][1])
        pos.reverse()
        return pos


# ------------------------------------------------------------------------------------------------ writing
def tin_text(kind):
    n = kind[0]
    if n in ("zcut", "cut", "fade"):
        return '("%s", 0.0)' % n
    if n in ("whip", "spin"):
        return '("%s", %s, (%d, %d))' % (n, fnum(kind[1]), kind[2][0], kind[2][1])
    return '("%s", %s)' % (n, fnum(kind[1]))


def kind_name(kind):
    if kind[0] in ("whip", "spin"):
        return "%s %s" % (kind[0], {(1, 0): "from the right", (-1, 0): "from the left", (0, -1): "from the top", (0, 1): "from the bottom"}[kind[2]])
    return kind[0]


def end_part(kill, pa, spec):
    """text of the anchors that end a take after `kill` at beat pa"""
    K = kill["K"]
    if spec[0] == "hold":
        return "[(%s, %d + %s * F)]" % (fnum(pa + spec[1]), K, fnum(spec[1]))
    if spec[0] == "holdx":
        T = spec[1]
        return "[(%s, %d + 1.0 * F), (%s, %d + %s * F)]" % (fnum(pa + 1.0), K, fnum(pa + T), K, fnum(1.0 + (T - 1.0) * EXT))
    _, Tt, out_rate, run_t = spec
    txt = "tail(%s, %d, %s, hold=%s, out_rate=%s)" % (fnum(pa), K, fnum(Tt), fnum(TAIL_HOLD), fnum(out_rate))
    if run_t > 0:
        mid = Tt - TAIL_HOLD - 0.4
        frames = TAIL_HOLD + mid * SLOW + 0.4 * out_rate + run_t
        txt += " + [(%s, %d + %s * F)]" % (fnum(pa + Tt + run_t), K, fnum(frames))
    return txt


def build(P, kills, pl, pos, term, R0):
    """-> (segments [(text, explanation lines)], final_bullet)"""
    N, F = len(kills), pl.F
    det = {i: pl.pair(i - 1, pos[i - 1], pos[i])[1] for i in range(1, N)}
    takes, cur = [], [0]
    for i in range(1, N):
        if det[i]["type"] == "cut":
            takes.append(cur)
            cur = [i]
        else:
            cur.append(i)
    takes.append(cur)
    hit = lambda b: ("kick low %.2f" % pl.low[b]) if pl.low.get(b, 0.0) >= KILL_LOW else ("snare mid %.2f" % pl.mid.get(b, 0.0))
    segs = []
    final_bullet = det[N - 1]["type"] == "cut" and det[N - 1]["bullet"]
    for t, idx in enumerate(takes):
        i0, il = idx[0], idx[-1]
        k0, kl = kills[i0], kills[il]
        parts, lines = [], []
        if t == 0:
            f0 = next((f for f in (1.3, 1.15, 1.0) if pl.lead_option(k0["K"], P["lead_in"], 0.0, fasts=(f,)) is not None), None)
            if f0 is None:
                die("kill #1 (%s K=%d) has too little footage before it for a %s-beat lead-in" % (k0["clip"], k0["K"], fnum(P["lead_in"])))
            parts.append("lead(%s, %d, %s, fast=%s)" % (fnum(pos[0]), k0["K"], fnum(P["lead_in"]), fnum(f0)))
            tin, start = ("fade", 0.0), R0
            lines.append("opening: the best kill on the drop (track beat %d = beat %s, %s); %s beats of lead-in at %.2fx under a riser" % (
                P["drop_beat"], fnum(pos[0]), hit(pos[0]), fnum(P["lead_in"]), f0))
        else:
            d0 = det[i0]
            start, tin = d0["c"], d0["kind"]
            why_cut = ("on %s without a kill" % hit(d0["c"])) if pl.bass else "free, with the kill rhythm"
            if d0["bullet"]:
                parts.append("bullet(%s, %d, %s)" % (fnum(pos[i0]), k0["K"], fnum(d0["L"])))
                lines.append("cut centre at beat %s, %s: %s into the bullet time of the last kill (%s beats of slow motion that arrive at real speed)" % (
                    fnum(d0["c"]), why_cut, kind_name(tin), fnum(d0["L"])))
            else:
                parts.append("lead(%s, %d, %s, fast=%s)" % (fnum(pos[i0]), k0["K"], fnum(d0["L"]), fnum(d0["f"])))
                lines.append("cut centre at beat %s, %s: %s into clip %s; the kill comes %s beats later (lead-in at %.2fx)" % (
                    fnum(d0["c"]), why_cut, kind_name(tin), k0["clip"], fnum(d0["L"]), d0["f"]))
        for j in idx:
            if j != i0:
                dj = det[j]
                ka, Ka, kb, Kb = pos[j - 1], kills[j - 1]["K"], pos[j], kills[j]["K"]
                if dj["mode"] == "full":
                    h = dj["h"]
                    parts.append("[(%s, %d + %s * F), (%s, %d - %s * F), (%s, %d)]" % (
                        fnum(ka + h), Ka, fnum(h), fnum(kb - SETTLE), Kb, fnum(SETTLE), fnum(kb), Kb))
                    lines.append("continuous: real time for %s beat after kill %d, then %.2fx until half a beat before kill %d" % (
                        fnum(h), j, dj["sm"], j + 1))
                else:
                    parts.append("[(%s, %d)]" % (fnum(kb), Kb))
                    lines.append("continuous: %.2fx straight from kill %d to kill %d (%s beats apart)" % (dj["sd"], j, j + 1, fnum(kb - ka)))
            lines.append("kill %d on beat %s: %s (level %d)" % (j + 1, fnum(pos[j]), hit(pos[j]), kills[j]["level"]))
        if t + 1 < len(takes):
            end_spec, end_beat = det[takes[t + 1][0]]["end"], det[takes[t + 1][0]]["c"]
        else:
            end_spec, end_beat = term["end"], term["e"]
        parts.append(end_part(kl, pos[il], end_spec))
        extra = {}
        if end_spec[0] == "tail":
            Tt, run_t = end_spec[1], end_spec[3]
            extra["slow"] = "(%s, %s)" % (fnum(pos[il]), fnum(pos[il] + Tt))
            extra["push"] = "[(%s, %s, %s)]" % (fnum(pos[il]), fnum(pos[il] + Tt - 0.2), "0.12" if kl["level"] == 3 else ("0.10" if Tt > 2 else "0.07"))
            extra["bars"] = "(%s, %s)" % (fnum(pos[il] + TAIL_HOLD - 0.1), fnum(pos[il] + Tt - 0.4))
            lines.append("after the shot: real time %s beat (recoil, flash), %s beats of %.2fx slow motion%s" % (
                fnum(TAIL_HOLD), fnum(Tt - TAIL_HOLD), SLOW, (", then %s beats of real time to the cut" % fnum(run_t)) if run_t else
                (", back to %.2fx for the cut" % end_spec[2])))
        elif end_spec[0] == "hold":
            lines.append("after the last kill: %s beat%s of real time before the cut (the banner is seen)" % (fnum(end_spec[1]), "" if end_spec[1] == 1 else "s"))
        else:
            lines.append("after the last kill: real time for 1 beat, then %.2fx to the cut at beat %s" % (EXT, fnum(end_beat)))
        lines.append("take ends at beat %s%s" % (fnum(end_beat), (", " + hit(end_beat)) if pl.bass else ""))
        lags = [kills[j]["lag"] for j in idx]
        lag_txt = fnum(lags[0], 2, True) if len(lags) == 1 else "[" + ", ".join(fnum(x, 2, True) for x in lags) + "]"
        ktxt = "[" + ", ".join("(%s, %d)" % (fnum(pos[j]), kills[j]["level"]) for j in idx) + "]"
        text = '    S("%s", %s,\n      kills=%s' % (k0["clip"], " +\n      ".join(parts), ktxt)
        if "slow" in extra:
            text += ", slow=%s" % extra["slow"]
        text += ", tin=%s, lag=%s" % (tin_text(tin), lag_txt)
        if "push" in extra:
            text += ",\n      push=%s, bars=%s" % (extra["push"], extra["bars"])
        text += "),"
        segs.append((text, ["segment %d (%s): beats %s .. %s" % (len(segs), k0["clip"], fnum(start), fnum(end_beat))] + lines))
    kl = kills[-1]
    e, R1, E0 = term["e"], term["R1"], term["E0"]
    segs.append(('    S("%s", [(%s, %d), (%s, %d + %s * F * 0.31)], tin=("soft", %s), lag=1.5, mute=True),' % (
        kl["clip"], fnum(e), E0, fnum(R1), E0, fnum(R1 - e), fnum(SOFT)),
        ["segment %d (%s): end card, beats %s .. %s: no zoom, it only fades to black with the music (banner frame %d, %s)" % (
            len(segs), kl["clip"], fnum(e), fnum(R1), E0, "from the plan" if kl["card"] is not None else "K + 100, or the last footage of the clip")]))
    return segs, final_bullet


def replace_block(src, name, new):
    pat = re.compile(r"(^# >>> draft:%s[^\n]*\n)(.*?)(^# <<< draft:%s[^\n]*\n)" % (name, name), re.S | re.M)
    if not pat.search(src):
        die("timeline_example.py has no `# >>> draft:%s` ... `# <<< draft:%s` markers (an old copy?): take all of scripts/*.* again" % (name, name),
            "cannot build the file")
    return pat.sub(lambda m: m.group(1) + new + m.group(3), src, count=1)


SUM = "# draft_timeline.py checksum (a changed file is never overwritten without --force): "


def untouched_draft(text):
    """True for a file this script wrote and nobody edited since (its last line is the checksum of the rest)."""
    i = text.rfind(SUM)
    return i > 0 and text[i + len(SUM):].strip() == hashlib.sha1(text[:i].encode("utf-8")).hexdigest()


def exec_timeline(src, name="draft"):
    ns = {"__name__": name}
    exec(compile(src, name, "exec"), ns)
    return ns


# ------------------------------------------------------------------------------------------------ statistics and checks
def speed_shares(ns):
    segs, R0, F = ns["SEGS"], ns["R0"], ns["FPB"]
    v = []
    for k in range(ns["N_FRAMES"]):
        r = R0 + k / F
        i = next((j for j, s in enumerate(segs) if r < s["r1"]), len(segs) - 1)
        v.append(float(segs[i]["map"](r)[1]))
    v = np.array(v)
    return dict(slow=float((v < 0.85).mean()), real=float(((v >= 0.85) & (v <= 1.25)).mean()), fast=float((v > 1.25).mean()),
                vmin=float(v.min()), vmax=float(v.max()))


def stats(ns, rows=None):
    segs = ns["SEGS"]
    kinds = collections.Counter(x["tin"][0] for x in segs[1:])
    beats = ns["R1"] - ns["R0"]
    dur = beats * ns["PER"]
    nk = len(ns["KILLS"])
    out = dict(seconds=dur, segments=len(segs), kills=nk, kills_per_beat=nk / beats, kills_per_10s=nk / dur * 10,
               transitions=sum(kinds.values()), kinds=dict(kinds), **speed_shares(ns))
    if rows is not None:
        by = {r[0]: r for r in rows}
        out["transitions_on_kick"] = sum(1 for x in segs[1:] if round(x["r0"] * 2) / 2 in by and by[round(x["r0"] * 2) / 2][1] >= 0.4)
    return out


def print_stats(title, st):
    print("%-20s %5.1f s  %2d segments  %2d kills (%.2f per beat, %.1f per 10 s)  speed: real %3.0f%%  fast %3.0f%%  slow %3.0f%%  "
          "(%.2fx .. %.2fx)  transitions %d (%s)%s" % (
              title, st["seconds"], st["segments"], st["kills"], st["kills_per_beat"], st["kills_per_10s"], st["real"] * 100,
              st["fast"] * 100, st["slow"] * 100, st["vmin"], st["vmax"], st["transitions"],
              ", ".join("%d %s" % (v, k) for k, v in sorted(st["kinds"].items())),
              (", %d on a kick" % st["transitions_on_kick"]) if "transitions_on_kick" in st else ""))


def verify(ns, rows, cuts_on):
    """Independent check of the finished module against the rules of edit-design.md, measured on its TimeMaps."""
    errs, warns = [], []
    segs = ns["SEGS"]
    by = {r[0]: r for r in rows}
    for i, s in enumerate(segs):
        if i and abs(s["r0"] - segs[i - 1]["r1"]) > 1e-9:
            errs.append("segment %d does not start where segment %d ends" % (i, i - 1))
        p, v = s["map"](np.linspace(s["x0"], s["x1"], 600))
        if not np.all(np.diff(p) > 0):
            errs.append("segment %d: the time map does not move forward" % i)
        n = clipio.n_frames(s["clip"])
        if p.min() < 3 or p.max() > n - 4:
            errs.append("segment %d (%s): frames %.1f .. %.1f leave the clip (0..%d)" % (i, s["clip"], p.min(), p.max(), n - 1))
        if v.max() > 4.6 or v.min() < 0.15:
            errs.append("segment %d: speed %.2f .. %.2f outside 0.15 .. 4.6" % (i, v.min(), v.max()))
        for k, lv in s["kills"]:
            kv = float(s["map"](k)[1])
            if abs(kv - 1) > 0.15:
                warns.append("segment %d: the kill at beat %g is reached at %.2fx, not at real speed" % (i, k, kv))
            b = by.get(k)
            if b is None or (b[1] < 0.25 and b[2] < 0.4):
                errs.append("kill at beat %g is not on a kick or a snare" % k)
        if i:
            first = min((k for k, _ in s["kills"]), default=None)
            if first is not None and first - s["r0"] < 1.5 - 1e-9:
                errs.append("segment %d: the first kill is %.2f beats after the transition centre (needs 1.5)" % (i, first - s["r0"]))
            prev = segs[i - 1]
            if prev["kills"] and prev["kills"][-1][1] == 1:
                after = s["r0"] - s["tin"][1] / 2 - prev["kills"][-1][0]
                if after < 0.5 - 1e-9:
                    errs.append("segment %d: only %.2f beats of real time between the kill before it and the transition" % (i, after))
            if cuts_on == "bass":
                half = round(s["r0"] * 2) / 2
                if abs(half - s["r0"]) > 1e-9 or half not in by or by[half][1] < 0.4:
                    errs.append("the transition into segment %d at beat %g is not on a kick" % (i, s["r0"]))
    return errs, warns


# ------------------------------------------------------------------------------------------------ main
def footage_problems(P, kills, F):
    E = []
    for i, k in enumerate(kills):
        tag = "kill #%d (%s K=%d, a clip of %d frames = %.1f s)" % (i + 1, k["clip"], k["K"], k["n"], k["n"] / 60)
        if not k["cont"]:
            beats = P["lead_in"] if i == 0 else LEAD_MIN
            need = int(math.ceil(SETTLE * F + (beats - SETTLE) * F + (0 if i == 0 else 0.35 * F) + MARGIN))
            if k["K"] < need:
                E.append("%s has only %d frames (%.2f s) of footage before the kill; a %s-beat lead-in needs about %d (%.2f s): "
                         "use a clip with more footage before the kill, or another kill" % (tag, k["K"], k["K"] / 60, fnum(beats), need, need / 60))
        last = i == len(kills) - 1
        if last:
            need = ((TAIL_HOLD + 0.4 + 0.5) * F if k["level"] > 1 else 1.0 * F) + MARGIN + (CARD[0] + SOFT / 2) * F * 0.31 + 3 + 8
        else:
            need = 0.85 * F + MARGIN if k["level"] == 1 else TAIL[k["level"]][0] * F + MARGIN
        have = k["n"] - 1 - k["K"]
        if have < need:
            E.append("%s has only %d frames (%.2f s) of footage after the kill; its %s needs about %d (%.2f s): use a clip with more footage after it" % (
                tag, have, have / 60, "tail and end card" if last else "aftermath", need, need / 60))
    return E


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("plan")
    ap.add_argument("-o", "--out", default="timeline.py")
    ap.add_argument("--force", action="store_true", help="overwrite -o even if it holds your own edits")
    ap.add_argument("--example", default="timeline_example.py", help="the template with the draft markers")
    ap.add_argument("--compare", default=None, help="another timeline .py to print statistics for (e.g. timeline_example.py)")
    args = ap.parse_args()
    P, kills = load_plan(args.plan)
    if not os.path.isfile(args.example):
        die("%s not found: run this from the project folder (scripts/*.* copied into it)" % args.example)
    tpl = open(args.example, encoding="utf-8").read()
    if "def bullet(" not in tpl:
        die("%s has no bullet(): take all of scripts/*.* again" % args.example)
    if os.path.exists(args.out) and not args.force:
        cur = open(args.out, encoding="utf-8").read()
        if cur != tpl and not untouched_draft(cur):
            die("%s exists and is neither the untouched example nor an untouched draft (it holds your edits): pick another name with -o, "
                "or --force to replace it" % args.out, "will not overwrite your timeline")

    per = 60.0 / P["bpm"]
    F = 60 * per
    M0 = int(round(P["drop_beat"])) + 1
    R0 = round(-1.0 - P["lead_in"], 1)
    bt = lambda r: P["beat0"] + (M0 + r) * per
    m = beat_hits.decode(P["music"])
    dur = len(m) / beat_hits.SR
    E = footage_problems(P, kills, F)
    if bt(R0) < 0:
        E.append("the drop at track beat %d is too early for a %s-beat lead-in: the video would start %.2f s before the song "
                 "(choose a later drop or a shorter lead_in)" % (P["drop_beat"], fnum(P["lead_in"]), -bt(R0)))
    rmax = math.floor(((dur - P["beat0"]) / per - M0 - 0.1) * 10) / 10
    L_t = P["length"] / per
    R1_t, tol = R0 + L_t, P["length_tolerance"]
    R1_lo, R1_hi = R0 + L_t * (1 - tol), min(R0 + L_t * (1 + tol), rmax)
    if R1_hi < R1_lo - 1e-9:
        E.append("the song has %.1f s left after the drop (track beat %d, %.1f s into a %.1f s song) but the edit needs %.0f s +-%d%%: "
                 "choose an earlier drop or a shorter length" % (dur - bt(-1), P["drop_beat"], bt(-1), dur, P["length"], round(tol * 100)))
    if E:
        die(E)
    for i in range(1, len(kills)):
        a, b = kills[i - 1], kills[i]
        if not b["cont"] and a["clip"] == b["clip"] and 0 < b["K"] - a["K"] < 360:
            print("note: kills #%d and #%d are only %.1f s apart in clip %s but are separate takes: mark #%d \"continuous\" to keep them one take" % (
                i, i + 1, (b["K"] - a["K"]) / 60, a["clip"], i + 1))

    window, chosen = R1_hi, None
    for attempt in range(4):          # plan on the measured hits of exactly the window the final R1 gives (music_pulses.py's)
        rows = beat_hits.measure(m, P["bpm"], P["beat0"], M0, R0, window)
        pl = Planner(P, kills, rows, R0, window, P["final"] if not kills[-1]["cont"] else "tail")
        if -1.0 not in pl.kp:
            r = {x[0]: x for x in rows}[-1.0]
            die("the drop (track beat %d = timeline beat -1) carries no kick or snare: low %.2f, mid %.2f (a kill needs low >= %.1f or mid >= %.1f). "
                "Check BPM / BEAT0 with music_grid.py, or pick the track beat of the kick that lands the drop (music_tempo.py lists the re-entries)" % (
                    P["drop_beat"], r[1], r[2], KILL_LOW, KILL_MID))
        if len(pl.kp) < len(kills):
            die("only %d kicks / snares in beats %g .. %g for %d kills" % (len(pl.kp), R0, window, len(kills)))
        if pl.bass:
            need_cuts = 1 + sum(1 for k in kills[1:] if not k["cont"])
            have = [b for b in pl.kicks if b > 0.5]
            if len(have) < need_cuts:
                die("CUTS_ON \"bass\" needs a kick for each of the %d transitions (every change of take, and the end card), but beats %g .. %g hold only %d "
                    "kicks (low >= %.1f) after the drop. Use fewer takes (mark kills \"continuous\"), a longer section, or \"cuts_on\": \"kills\"" % (
                        need_cuts, R0, window, len(have), CUT_LOW))
        pl.run()
        stuck = next((i for i in range(len(kills)) if not pl.dp[i]), None)
        if stuck is not None:
            a, b = kills[stuck - 1], kills[stuck]
            why = ("kill #%d (%s K=%d) cannot be placed after kill #%d: " % (stuck + 1, b["clip"], b["K"], stuck))
            if b["cont"]:
                why += ("it is continuous, so the ramp between them must run at 0.9x .. 3.7x on beats that carry a kick or a snare; "
                        "K %d -> %d is %d frames = %.1f beats at real time" % (a["K"], b["K"], b["K"] - a["K"], (b["K"] - a["K"]) / F))
            else:
                Lfoot = max([x / 10 for x in range(15, 81) if pl.lead_option(b["K"], x / 10, 0.7) is not None] or [0])
                why += ("no %s fits between them: it needs 0.85 .. %g beats of aftermath after kill #%d, then %s 1.5 .. %g beats before kill #%d%s"
                        % ("kick (low >= %.1f)" % CUT_LOW if pl.bass else "cut", 6.0 if kills[stuck - 1]["level"] == 1 else 6.4, stuck,
                           "the cut on a kick," if pl.bass else "the cut,", min(LEAD_MAX, Lfoot) if Lfoot else 0, stuck + 1,
                           (" (its clip has %d frames = %.1f s before it, which allows a lead-in of at most %.1f beats)" % (b["K"], b["K"] / 60, Lfoot))
                           if Lfoot < LEAD_MAX else ""))
                why += (". Beats %s .. %s (the length asked, +-%d%%) leave room for the kills only up to beat %s, and every take needs "
                        "about 3 to 9 beats: ask for more seconds, mark close kills \"continuous\", or use fewer takes" % (
                            fnum(R0, 1), fnum(window, 1), round(tol * 100), fnum(window - 6, 1)))
            die(why, "cannot place the kills")
        pk = pl.pick(R1_t, R1_lo, window)
        if pk is None:
            wide = min(rmax, R0 + L_t * 2)         # what the kills could reach at all, for the message
            rows2 = beat_hits.measure(m, P["bpm"], P["beat0"], M0, R0, wide)
            pl2 = Planner(P, kills, rows2, R0, wide, pl.final_mode)
            pl2.run()
            lo, hi = pl2.reach()
            if lo is None:
                die("the last kill (%s K=%d) cannot get its tail and end card on a %s inside its clip" % (
                    kills[-1]["clip"], kills[-1]["K"], "kick" if pl.bass else "beat"), "cannot place the kills")
            s_lo, s_hi = (lo - R0) * per, (hi - R0) * per
            die("these %d kills cannot make %.0f s (+-%d%%) under the spacing rules: they make %.1f to %.1f s. %s" % (
                len(kills), P["length"], round(tol * 100), s_lo, s_hi,
                ("Add kills (or a longer lead_in), or ask for about %.0f s." % s_hi) if s_hi < P["length"] * (1 - tol) else
                ("Use fewer kills, or ask for about %.0f s." % s_lo)), "cannot fit the length")
        total, p_last, term = pk
        R1 = term["R1"]
        if abs(R1 - window) < 1e-9:
            chosen = (pl, rows, p_last, term)
            break
        window = R1_lo = R1_hi = R1
    if chosen is None:
        die("the measured hits changed between passes; run again with a slightly different length")
    pl, rows, p_last, term = chosen
    pos = pl.backtrack(p_last)
    R1 = term["R1"]
    FADE_OUT = (round(R1 - 2.8, 1), R1)
    segs, final_bullet = build(P, kills, pl, pos, term, R0)

    bpm_txt = "%.1f" % P["bpm"] if float(P["bpm"]) == int(P["bpm"]) else fnum(float(P["bpm"]))
    music_blk = (
        'MUSIC = "%s"\n'
        "BPM, BEAT0 = %s, %s          # tempo, and the time of the track's first beat (music_grid.py measures BEAT0)\n"
        "M0 = %d                             # timeline beat 0 = this beat of the track (the drop, track beat %d, is beat -1)\n"
        "PER = 60.0 / BPM\n"
        "FPS = 60\n"
        "FPB = FPS * PER                     # output frames per beat (%.2f)\n"
        "R0, R1 = %s, %s                 # first / last beat of the video\n"
        "FADE_OUT = (%s, %s)             # picture and music fade to black over these beats\n"
        'CUTS_ON = "%s"                    # where transitions land: "bass" (kicks / 808s only, the default) or "kills" (with the\n'
        "                                    # kill rhythm): the user's choice in the briefing; music_pulses.py checks it.\n") % (
        P["music"], bpm_txt, fnum(P["beat0"]), M0, P["drop_beat"], F, fnum(R0, 4, True), fnum(R1, 4, True),
        fnum(FADE_OUT[0], 4, True), fnum(FADE_OUT[1], 4, True), P["cuts_on"])
    riser1 = "dict(a=%s, b=%s, f0=350, f1=7000, curve=1.0, width=1.1, power=2.3, gain=0.13, cut=0.012, seed=1)" % (
        fnum(R0 + 0.2, 4, True), fnum(pos[0], 4, True))
    if final_bullet:
        kf = pos[-1]
        sweep = "[(%s, 18000), (%s, 1000), (%s, 620), (%s, 620)]" % (fnum(kf - 4.7), fnum(kf - 3.0), fnum(kf - 0.4), fnum(kf))
        riser2 = ",\n          dict(a=%s, b=%s, f0=300, f1=9000, curve=1.3, width=1.2, power=2.0, gain=0.20, cut=0.010, seed=2)" % (
            fnum(kf - 4.4), fnum(kf))
    else:
        sweep, riser2 = "[]", ""
    sound_blk = ("# sound design tied to this piece of music (audio.py); use None / [] to switch off\n"
                 "SWEEP = %s     # low-pass on the music: (beat, cutoff Hz)\n"
                 "RISERS = [%s%s]\n") % (sweep, riser1, riser2)
    segs_txt = "SEGS = [\n" + "\n".join(
        "".join("    # %s\n" % l for l in ex if not l.startswith("take ends")) + text for text, ex in segs) + "\n]\n" \
        'KILLS = [(k, lv, i) for i, s in enumerate(SEGS) for k, lv in s["kills"]]\n'
    doc = ('"""The edit, expressed in beats of the music: drafted by draft_timeline.py from %s (plan %s), to be read and\n'
           "tweaked, not trusted blindly. %d kills, %.0f s, CUTS_ON \"%s\", timeline beat 0 = beat %d of the track.\n"
           'Source positions are frame indices of the clips (exact, 60 per second)."""') % (
        os.path.basename(args.plan), hashlib.sha1(open(args.plan, "rb").read()).hexdigest()[:8], len(kills), (R1 - R0) * per, P["cuts_on"], M0)
    src = re.sub(r'\A""".*?"""', lambda mm: doc, tpl, count=1, flags=re.S)
    src = replace_block(src, "music", music_blk)
    src = replace_block(src, "sound", sound_blk)
    src = replace_block(src, "segs", segs_txt + "PULSES = []\n")
    ns = exec_timeline(src)
    # PULSES: the strong hits that carry neither a kill nor a transition (weight 0.5 .. 0.9)
    kb = [k for k, _, _ in ns["KILLS"]]
    ctr = [s["r0"] for s in ns["SEGS"][1:]]
    pulses = []
    for r in rows:
        b, s = r[0], max(r[1], r[2])
        if not R0 <= b <= R1 or s < 0.6 or any(abs(b - x) < 0.5 for x in kb) or any(abs(b - x) < 0.3 for x in ctr):
            continue
        if final_bullet and pos[-1] - 4.7 < b < pos[-1]:
            continue
        pulses.append((b, round(min(0.9, max(0.5, 0.5 + 0.4 * (s - 0.6) / 0.4)), 1)))
    lines, cur = [], "PULSES = ["
    items = ["(%s, %s)" % (fnum(b), fnum(w, 1)) for b, w in pulses]
    for j, it in enumerate(items):
        piece = it + ("," if j + 1 < len(items) else "")
        if len(cur) + len(piece) + 1 > 118:
            lines.append(cur.rstrip())
            cur = "          "
        cur += piece + " "
    lines.append(cur.rstrip() + "]" if items else "PULSES = []")
    src = replace_block(src, "segs", segs_txt + "# accents without a kill: (beat, weight): the strong kicks / snares that carry neither a kill nor a transition\n"
                        + "\n".join(lines) + "\n")
    ns = exec_timeline(src)
    errs, warns = verify(ns, rows, P["cuts_on"])
    if errs:
        die(errs, "built a draft that fails its own check (a bug, or inputs it cannot handle)")
    open(args.out, "w", encoding="utf-8", newline="\n").write(src + SUM + hashlib.sha1(src.encode("utf-8")).hexdigest() + "\n")

    print("music: %s  %s BPM  BEAT0 %s  drop at track beat %d -> M0 %d (the drop is beat -1); R0 %s, R1 %s = %.1f s (asked %.0f s); CUTS_ON = %r" % (
        P["music"], bpm_txt, fnum(P["beat0"]), P["drop_beat"], M0, fnum(R0), fnum(R1), (R1 - R0) * per, P["length"], P["cuts_on"]))
    print("hits in the window: %d that can carry a kill (kick low >= %.1f or snare mid >= %.1f), %d kicks that can carry a transition" % (
        len(pl.kp), KILL_LOW, KILL_MID, len(pl.kicks)))
    for _, ex in segs:
        print("\n".join((l if j == 0 else "    " + l) for j, l in enumerate(ex)))
    print("last kill: " + ("bullet time on a bass re-entry (no kick in the 3 beats before it): SWEEP and a second riser added" if final_bullet else
                           "continuous with the kill before it, so a normal lead-in" if kills[-1]["cont"] else
                           "a normal lead-in (%s)" % ("final = \"tail\"" if P["final"] == "tail" else "no bass re-entry within reach")))
    print("PULSES: %d strong hits without a kill or transition" % len(pulses))
    for w in warns:
        print("note:", w)
    if not all(k["has_lag"] for k in kills):
        print("note: every lag is the placeholder 2.0 frames: run kill_lags.py after ranges.py / prep.py and put its values in")
    st = stats(ns, rows)
    print("wrote %s: %d segments, %d frames, %.2f s, music from %.3f s" % (args.out, len(ns["SEGS"]), ns["N_FRAMES"], (R1 - R0) * per, ns["MUSIC_T0"]))
    print_stats("draft", st)
    if args.compare and os.path.isfile(args.compare):
        cns = exec_timeline(open(args.compare, encoding="utf-8").read(), "compare")
        crows = None
        if cns["MUSIC"] == P["music"]:
            try:
                crows = beat_hits.measure(m, cns["BPM"], cns["BEAT0"], cns["M0"], cns["R0"], cns["R1"])
            except SystemExit:
                pass
        print_stats(os.path.basename(args.compare), stats(cns, crows))
    if st["kills_per_10s"] < 3.5:
        print("note: %.1f kills per 10 s (house example: 5.9): a sparse edit gets long lead-ins, long slow motion and long stretches of real time; "
              "add kills (about %d for %.0f s at the house example's pace) or ask for fewer seconds" % (
                  st["kills_per_10s"], int(math.ceil(5.9 * P["length"] / 10)), P["length"]))
    print("next: $PY timeline.py (must pass), $PY music_pulses.py (none / none), $PY ranges.py; then kill_lags.py for each lag")


if __name__ == "__main__":
    main()
