"""Writes a correct first draft of a house-style timeline.py from measured inputs; you then read it, look at the stills
and tweak it (edit-design.md). It does the arithmetic that hand-written timelines get wrong: every kill on a measured
kick or snare ATTACK, every transition on a kick (CUTS_ON "bass") or with the kill rhythm ("kills"), the next kill at least
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
   "cut_lead_frames": 1,               # optional, 0..3: frames a cut is SHOWN before its musical moment (default: ref_notes.json
   "hit_lead_frames": 1,               #   "adopt" when there is one, else 1); hit_lead_frames: the same for a shot's flash and accents
   "kills": [                          # in the order they play; clip names are the keys of clips.json
     {"clip": "c10", "K": 5362, "level": 3},                   # K = muzzle-flash frame (kills.json / kill_table.py)
     {"clip": "c10", "K": 5474, "continuous": true},            # same take as the previous kill: one speed ramp between
     {"clip": "c18", "K": 1305, "level": 2},                    # finisher: slow motion after the shot
     {"clip": "c14", "K": 7794, "level": 3, "end_card": 7894}   # last kill; end_card = frame of the ACE banner (default K + 100)
   ]}
Per kill: "level" 1 (default for the middle ones), 2 (slow-motion finisher, ends its take), 3 (opening and last kill only:
default for them); "continuous" (needs the same clip, a later K, and level 1 on the kill before it); "lag" (frames the
gunshot trails the picture: normally leave it out, audio.py measures every kill's gunshot itself and stops on one it cannot
measure; type it only for such a kill after reading kill_lags.py's strip); "end_card" (last kill only);
"id" instead of "clip" and "K": {"id": 96} takes both from kills.json. EVERY kill's K must be verified on the picture: kills.json "how" "ammo" /
"flash" for an entry found by id (else by clip and K), and the plan's K equal to the entry's; no kills.json, no entry, a different K, "ammo-loose" /
'guess' are all refused unless the plan entry has "k_checked": true, set after looking at kverify.py's sheets (kverify.py plan.json).

What it decides, from the music (beat_hits.measure_t: every hit WITH ITS MEASURED ATTACK TIME) and the clips' lengths (pts/):
  * the first kill on the drop (beat -1) with `lead_in` beats of fast-forwarded lead-in and a riser, slow motion after it;
  * every other kill on a kick (low >= 0.5) or a snare (mid >= 0.6), spread so that the edit lasts `length`;
  * cuts between takes on kicks that carry no kill (CUTS_ON "bass") or on a 1/4-beat line of the song, at the measured
    attack on that line when there is one ("kills"), always at least 1.5 beats before the next kill, 0.5 beat of real time
    after a normal kill before the transition starts (both with two frames of margin: the rules are checked on the SHOWN frames);
  * speeds: lead-ins 1.0 to 1.5x (the longer the lead-in, the closer to real time), speed ramps between continuous
    kills 0.9 to 3.7x on average (peaks stay under 4.6x), slow motion 0.28x, bullet time 0.18x, nothing outside 0.15x .. 4.6x;
  * the last kill: on a bass re-entry after a break (no kick in the 3 beats before) it comes in as bullet time with the
    music low-passed (SWEEP) and a second riser; otherwise a normal lead-in. Then an end card that only fades to black;
  * transitions: whip / zoom / spin on a change of clip, in rotating directions; zcut inside one clip; dissolve into
    bullet time; soft into the end card;
  * R0 / R1 / FADE_OUT / M0, PULSES (every strong hit without a kill or transition), RISERS, SWEEP.

Timing (timeline.py SYNC = 2): every beat it writes is MUSICAL and exact to 9 decimals: a kill is hit(t) of the measured attack of its
kick / snare (not the half-beat grid time: a live drummer's hit is 5 to 25 ms off the grid), a "bass" cut is the kick's own attack, a
"kills" cut the attack on its 1/4-beat line (the grid line when nothing sounds there), R0 is the first hit minus the lead-in, R1 and
FADE_OUT are lines of the song's grid (an ending has no hit). timeline_example.py's loop after SEGS turns them into the frames that show
them (a cut CUT_LEAD frames, a shot HIT_LEAD frames before the nearest frame of its beat); the sound stays on the exact beat.

It refuses, with the numbers, when the inputs cannot fit: too few kicks or snares, a clip without enough footage before
or after a kill, a length that the kills cannot fill, two takes of one clip whose kills would show the same source frames
twice, and any plan key this style does not implement (a reference-style key is named, with the drafter that has it; an
unknown one gets a "did you mean" and the valid keys: a typo must not silently change the cut rhythm). The file is built from
timeline_example.py by replacing the blocks between its `# >>> draft:...` / `# <<< draft:...` markers (docstring, music block,
cut block, sound block, segments). Few kills for a long edit give long lead-ins and long slow motion: the statistics it prints
(against the house example with --compare) say so."""
import argparse, bisect, collections, difflib, hashlib, json, math, os, re, sys
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
FRAME_EPS = 2          # frames of margin on the spacing rules: they are measured in beats on the musical times, a cut and a shot each round to
                       # a frame and a transition to an even number of frames, and verify() checks them on the SHOWN frames of the built module
KEYS = {"music", "bpm", "beat0", "drop_beat", "cuts_on", "length", "length_tolerance", "lead_in", "final",
        "cut_lead_frames", "hit_lead_frames", "kills"}                      # every key this drafter implements (plan.json)
KILL_KEYS = {"clip", "K", "id", "level", "continuous", "lag", "end_card", "k_checked"}       # every key of a kill entry
REF_ONLY = {"intro": "an intro", "auto_bullet": "an automatic bullet time where the drums thin out", "ref_notes": "a reference video's measured traits (ref_notes.json)",
            "frame": 'a "frame" (vertical / horizontal)', "look": "a look preset", "max_speed": "a speed ceiling", "hit_grid": "a hit grid",
            "bullet": "bullet time / a drop bullet", "with_previous": 'joining kills into one take ("continuous" in the house style)', "at": "pinning a kill on a beat"}
# plan keys of the REFERENCE style (draft_ref_timeline.py): this style has no such feature, so they are refused instead of silently ignored (a typo
# in a key the drafter reads would otherwise change the whole cut rhythm with no message)


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
    for k in P:
        if k in REF_ONLY:
            E.append('"%s" is a reference-style feature the house style does not have (%s); draft_ref_timeline.py is the drafter that implements it '
                     '(scripts/refstyle/). Drop it, or plan this edit in the reference style' % (k, REF_ONLY[k]))
        elif k not in KEYS:
            near = difflib.get_close_matches(k, sorted(KEYS), n=1, cutoff=0.6)
            E.append('plan.json has an unknown key "%s"%s (valid: %s)' % (k, '; did you mean "%s"?' % near[0] if near else "", ", ".join(sorted(KEYS))))
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
    kills, db, unverified = [], preflight.kills_db(), []
    for i, k in enumerate(ks):
        tag = "kill #%d" % (i + 1)
        for key in k:
            if key in REF_ONLY:
                E.append('%s: "%s" is a reference-style feature the house style does not have (%s); draft_ref_timeline.py is the drafter that implements '
                         'it (scripts/refstyle/). Drop it, or plan this edit in the reference style' % (tag, key, REF_ONLY[key]))
            elif key not in KILL_KEYS:
                near = difflib.get_close_matches(key, sorted(KILL_KEYS), n=1, cutoff=0.6)
                E.append('%s has an unknown key "%s"%s (valid per kill: %s)' % (tag, key, '; did you mean "%s"?' % near[0] if near else "",
                                                                                ", ".join(sorted(KILL_KEYS))))
        if "id" in k:                                  # {"id": 96}: clip and K default to the kills.json entry
            e = db.get(str(k["id"]))
            if not e:
                E.append("%s: kills.json has no entry %r%s" % (tag, k["id"], "" if db else " (no readable kills.json in this folder)"))
                continue
            k = dict(k, clip=k.get("clip", e["clip"]), K=k.get("K", e["K"]))
        if "clip" not in k or "K" not in k:
            E.append('%s needs "clip" and "K" (or an "id" of kills.json)' % tag)
            continue
        why_k = preflight.k_check(db, dict(clip=k["clip"], K=int(k["K"]), **({"id": k["id"]} if "id" in k else {})))     # the plan's own K, id or not
        if why_k and not k.get("k_checked"):
            unverified.append("%s (%s K=%s: %s)" % (tag, k["clip"], k["K"], why_k))
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
        kills.append(dict(i=i, clip=k["clip"], K=K, n=n, level=lv, cont=cont, lag=(float(k["lag"]) if "lag" in k else None),
                          card=k.get("end_card"), has_lag="lag" in k))
    if unverified:
        E.append("%d kill(s) with a K that is not verified on the picture (a frame off is 16.7 ms of desync): %s. %s" % (
            len(unverified), "; ".join(unverified[:8]) + (" ..." if len(unverified) > 8 else ""), preflight.K_HELP))
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
    return (T, 0.0) if T <= hi + 1e-9 else (pref, round(T - pref, 9))


class Planner:
    def __init__(self, P, kills, rows, att, att4, R0, window, final_mode):
        """rows / att: beat_hits.measure_t on the half-beat lattice (att.bands[b][band] = the attack TIME of the hit on row b); att4: the same on
        the 1/4-beat lattice (only read for CUTS_ON "kills": the attack near a cut line). Every beat the planner decides with is the MUSICAL one:
        hit(t) of the attack, to 9 decimals; the lattice beat is only the key of the row."""
        self.P, self.kills, self.N = P, kills, len(kills)
        self.per = 60.0 / P["bpm"]
        self.F = 60 * self.per
        self.eps = FRAME_EPS / self.F                    # margin of the spacing rules (see FRAME_EPS)
        self.lead_min = LEAD_MIN + self.eps
        self.bass = P["cuts_on"] == "bass"
        self.R0, self.window = R0, window
        self.low = {r[0]: r[1] for r in rows}
        self.mid = {r[0]: r[2] for r in rows}
        beats = sorted(self.low)
        self.hit = lambda t: round((t - P["beat0"]) / self.per - P["M0"], 9)
        self.kt, self.ct = {}, {}                        # lattice beat -> musical beat of the hit that carries a kill / a bass cut there
        for b in beats:
            tb = att.bands.get(b, {})
            if self.low[b] >= KILL_LOW and "low" in tb:
                self.kt[b] = self.hit(tb["low"])
            elif self.mid[b] >= KILL_MID and "mid" in tb:
                self.kt[b] = self.hit(tb["mid"])
            if self.low[b] >= CUT_LOW and "low" in tb:
                self.ct[b] = self.hit(tb["low"])
        self.kp = [b for b in beats if -1.0 <= b <= window - 6.0 and b in self.kt]
        self.kicks = sorted(self.ct)
        self.tl = self.tr = None
        if not self.bass:                                # every measured attack (any band), to put a cut on the one that sounds on its line
            ev = sorted((t, rise) for t, band, rise in att4.all)
            self.tl, self.tr = np.array([e[0] for e in ev]), np.array([e[1] for e in ev])
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
        if not self.lead_min - 1e-9 <= L <= LEAD_MAX + 1e-9:
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

    def line_beat(self, c):
        """-> (musical beat, measured): the 1/4-beat line c of the song's grid carries a cut; a measured attack of any band within half a frame
        of the line is its moment (the strongest one), and the grid line itself where nothing sounds there."""
        tl = self.P["beat0"] + (self.P["M0"] + c) * self.per
        i = int(np.searchsorted(self.tl, tl - 0.5 / 60 - 1e-9))
        best = None
        while i < len(self.tl) and self.tl[i] <= tl + 0.5 / 60 + 1e-9:
            if best is None or self.tr[i] > best[1]:
                best = (float(self.tl[i]), float(self.tr[i]))
            i += 1
        return (self.hit(best[0]), True) if best else (round(c, 9), False)

    def cut_candidates(self, lo, hi):
        """-> [(lattice key, musical beat, measured)] of the places a cut may sit with its musical beat in lo .. hi: the kicks (bass) or
        the 1/4-beat lines (kills)"""
        if hi < lo - 1e-9:
            return []
        if self.bass:
            return [(c, self.ct[c], True) for c in self.kicks if lo - 1e-9 <= self.ct[c] <= hi + 1e-9]
        out = []
        for j in range(int(math.ceil(lo * 4 - 0.5)), int(math.floor(hi * 4 + 0.5)) + 1):
            c = j / 4.0
            m, meas = self.line_beat(c)
            if lo - 1e-9 <= m <= hi + 1e-9:
                out.append((c, m, meas))
        return out

    def snap(self, x, lo, hi):
        """A line of the song's grid (1/2, then 1/4, then 1/8 beat) nearest x inside lo .. hi: R1 and FADE_OUT have no hit to sit on."""
        for st in (0.5, 0.25, 0.125):
            a, b = int(math.ceil(lo / st - 1e-9)), int(math.floor(hi / st + 1e-9))
            if a <= b:
                return min(max(int(round(x / st)), a), b) * st
        return round(0.5 * (lo + hi), 9)

    def max_after(self, kill, final=False):
        return 6.0 + (SOFT if final else 0.7) / 2 if kill["level"] == 1 else (TAIL_FINAL if final else TAIL)[kill["level"]][1] + RUN_MAX

    # -- one pair of consecutive kills
    def pair(self, ia, pa, pb):
        """-> (cost, detail) or None. Between kill ia (on row pa) and kill ia + 1 (on row pb); beats are the musical ones."""
        a, b = self.kills[ia], self.kills[ia + 1]
        F = self.F
        ka, kb = self.kt[pa], self.kt[pb]
        g = kb - ka
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
        for cl, c, meas in self.cut_candidates(ka + 0.5 + max(dh, 0.3) + self.eps, min(ka + self.max_after(a), kb - self.lead_min)):
            T, L = round(c - ka, 9), round(kb - c, 9)
            e = self.end_option(a, T, d)
            if e is None:
                continue
            l = self.lead_option(b["K"], L, d, bullet)
            if l is None:
                continue
            cost = e[0] + l[0] - (0.15 if meas and not self.bass else 0.0)       # kills mode: a line where something sounds beats a bare grid line
            if best is None or cost < best[0]:
                best = (cost, dict(type="cut", c=c, cl=cl, T=T, L=L, f=l[1], end=e[3], kind=kind, bullet=bullet, d=d, meas=meas))
        return best

    def terminal(self, p, R1_t, R1_lo, R1_hi):
        """The last kill on row p: the end of its take (the cut to the end card) and R1. -> (cost, detail) or None"""
        k = self.kills[-1]
        F = self.F
        kp_ = self.kt[p]
        out = None
        for cl, e, meas in self.cut_candidates(kp_ + 0.5 + SOFT / 2 + self.eps, kp_ + self.max_after(k, True)):
            T = round(e - kp_, 9)
            en = self.end_option(k, T, SOFT, final=True)
            if en is None:
                continue
            lo, hi = max(e + CARD[0], R1_lo), min(e + CARD[1], R1_hi)
            if lo > hi + 1e-9:
                continue
            R1 = self.snap(min(max(R1_t, lo), hi), lo, hi)
            card_f = (R1 - e + SOFT / 2) * F * 0.31
            E0 = k["card"] if k["card"] is not None else min(k["K"] + 100, k["n"] - 1 - MARGIN - card_f)
            if E0 < k["K"] + en[1] + 3 or E0 + card_f > k["n"] - 1 - MARGIN:
                continue
            cost = en[0] + 0.05 * (R1 - R1_t) ** 2 + 0.1 * (R1 - e - 4.6) ** 2
            if out is None or cost < out[0]:
                out = (cost, dict(e=e, el=cl, T=T, end=en[3], R1=R1, E0=int(E0), card_f=card_f))
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


def fb(x):
    """A musical beat as written into timeline.py: 9 decimals (an exact decimal, so a take's last anchor equals the next take's first one)."""
    return fnum(x, 9)


def end_part(kill, pa, spec):
    """text of the anchors that end a take after `kill` whose hit is at musical beat pa"""
    K = kill["K"]
    if spec[0] == "hold":
        return "[(%s, %d + %s * F)]" % (fb(pa + spec[1]), K, fb(spec[1]))
    if spec[0] == "holdx":
        T = spec[1]
        return "[(%s, %d + 1.0 * F), (%s, %d + %s * F)]" % (fb(pa + 1.0), K, fb(pa + T), K, fnum(1.0 + (T - 1.0) * EXT))
    _, Tt, out_rate, run_t = spec
    txt = "tail(%s, %d, %s, hold=%s, out_rate=%s)" % (fb(pa), K, fb(Tt), fnum(TAIL_HOLD), fnum(out_rate))
    if run_t > 0:
        mid = Tt - TAIL_HOLD - 0.4
        frames = TAIL_HOLD + mid * SLOW + 0.4 * out_rate + run_t
        txt += " + [(%s, %d + %s * F)]" % (fb(pa + Tt + run_t), K, fnum(frames))
    return txt


def build(P, kills, pl, pos, term, R0):
    """-> (segments [(text, explanation lines)], final_bullet). pos = the lattice row of each kill; pl.kt[row] its musical beat."""
    N, F = len(kills), pl.F
    det = {i: pl.pair(i - 1, pos[i - 1], pos[i])[1] for i in range(1, N)}
    kb = [pl.kt[p] for p in pos]                                  # the musical beat of every kill (the measured attack, 9 decimals)
    takes, cur = [], [0]
    for i in range(1, N):
        if det[i]["type"] == "cut":
            takes.append(cur)
            cur = [i]
        else:
            cur.append(i)
    takes.append(cur)

    def hit(b):                                                   # what carries the kill on row b, and how far the attack is from the grid
        what = ("kick low %.2f" % pl.low[b]) if pl.low.get(b, 0.0) >= KILL_LOW else ("snare mid %.2f" % pl.mid.get(b, 0.0))
        return "%s, attack %+.1f ms from the grid" % (what, (pl.kt[b] - b) * pl.per * 1000) if b in pl.kt else what

    def cut_hit(d):                                               # what a cut sits on
        if pl.bass:
            return "kick low %.2f, attack %+.1f ms from the grid" % (pl.low[d["cl"]], (d["c"] - d["cl"]) * pl.per * 1000)
        return ("on the attack at the 1/4-beat line %s (%+.1f ms from it)" % (fnum(d["cl"]), (d["c"] - d["cl"]) * pl.per * 1000)) if d["meas"] else \
            ("on the 1/4-beat line %s of the grid (nothing sounds there)" % fnum(d["cl"]))
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
            parts.append("lead(%s, %d, %s, fast=%s)" % (fb(kb[0]), k0["K"], fb(P["lead_in"]), fnum(f0)))
            tin, start = ("fade", 0.0), R0
            lines.append("opening: the best kill on the drop (track beat %d = beat %s, %s); %s beats of lead-in at %.2fx under a riser" % (
                P["drop_beat"], fb(kb[0]), hit(pos[0]), fnum(P["lead_in"]), f0))
        else:
            d0 = det[i0]
            start, tin = d0["c"], d0["kind"]
            why_cut = ("on %s without a kill" % cut_hit(d0)) if pl.bass else ("free, with the kill rhythm, %s" % cut_hit(d0))
            if d0["bullet"]:
                parts.append("bullet(%s, %d, %s)" % (fb(kb[i0]), k0["K"], fb(d0["L"])))
                lines.append("cut centre at beat %s, %s: %s into the bullet time of the last kill (%s beats of slow motion that arrive at real speed)" % (
                    fb(d0["c"]), why_cut, kind_name(tin), fnum(d0["L"])))
            else:
                parts.append("lead(%s, %d, %s, fast=%s)" % (fb(kb[i0]), k0["K"], fb(d0["L"]), fnum(d0["f"])))
                lines.append("cut centre at beat %s, %s: %s into clip %s; the kill comes %s beats later (lead-in at %.2fx)" % (
                    fb(d0["c"]), why_cut, kind_name(tin), k0["clip"], fnum(d0["L"]), d0["f"]))
        for j in idx:
            if j != i0:
                dj = det[j]
                ka, Ka, kbj, Kb = kb[j - 1], kills[j - 1]["K"], kb[j], kills[j]["K"]
                if dj["mode"] == "full":
                    h = dj["h"]
                    parts.append("[(%s, %d + %s * F), (%s, %d - %s * F), (%s, %d)]" % (
                        fb(ka + h), Ka, fnum(h), fb(kbj - SETTLE), Kb, fnum(SETTLE), fb(kbj), Kb))
                    lines.append("continuous: real time for %s beat after kill %d, then %.2fx until half a beat before kill %d" % (
                        fnum(h), j, dj["sm"], j + 1))
                else:
                    parts.append("[(%s, %d)]" % (fb(kbj), Kb))
                    lines.append("continuous: %.2fx straight from kill %d to kill %d (%s beats apart)" % (dj["sd"], j, j + 1, fnum(kbj - ka)))
            lines.append("kill %d on beat %s: %s (level %d)" % (j + 1, fb(kb[j]), hit(pos[j]), kills[j]["level"]))
        if t + 1 < len(takes):
            end_spec, end_beat = det[takes[t + 1][0]]["end"], det[takes[t + 1][0]]["c"]
        else:
            end_spec, end_beat = term["end"], term["e"]
        parts.append(end_part(kl, kb[il], end_spec))
        extra = {}
        if end_spec[0] == "tail":
            Tt, run_t = end_spec[1], end_spec[3]
            extra["slow"] = "(%s, %s)" % (fb(kb[il]), fb(kb[il] + Tt))
            extra["push"] = "[(%s, %s, %s)]" % (fb(kb[il]), fb(kb[il] + Tt - 0.2), "0.12" if kl["level"] == 3 else ("0.10" if Tt > 2 else "0.07"))
            extra["bars"] = "(%s, %s)" % (fb(kb[il] + TAIL_HOLD - 0.1), fb(kb[il] + Tt - 0.4))
            lines.append("after the shot: real time %s beat (recoil, flash), %s beats of %.2fx slow motion%s" % (
                fnum(TAIL_HOLD), fnum(Tt - TAIL_HOLD), SLOW, (", then %s beats of real time to the cut" % fnum(run_t)) if run_t else
                (", back to %.2fx for the cut" % end_spec[2])))
        elif end_spec[0] == "hold":
            lines.append("after the last kill: %s beat%s of real time before the cut (the banner is seen)" % (fnum(end_spec[1]), "" if end_spec[1] == 1 else "s"))
        else:
            lines.append("after the last kill: real time for 1 beat, then %.2fx to the cut at beat %s" % (EXT, fb(end_beat)))
        lines.append("take ends at beat %s%s" % (fb(end_beat), (", kick low %.2f" % pl.low[det[takes[t + 1][0]]["cl"]]) if pl.bass and t + 1 < len(takes) else ""))
        lags = [kills[j]["lag"] for j in idx]
        lag_txt = None if all(x is None for x in lags) else (
            fnum(lags[0], 2, True) if len(lags) == 1 else "[" + ", ".join("None" if x is None else fnum(x, 2, True) for x in lags) + "]")
        ktxt = "[" + ", ".join("(%s, %d)" % (fb(kb[j]), kills[j]["level"]) for j in idx) + "]"
        text = '    S("%s", %s,\n      kills=%s' % (k0["clip"], " +\n      ".join(parts), ktxt)
        if "slow" in extra:
            text += ", slow=%s" % extra["slow"]
        text += ", tin=%s" % tin_text(tin)
        if lag_txt is not None:
            text += ", lag=%s" % lag_txt
        if "push" in extra:
            text += ",\n      push=%s, bars=%s" % (extra["push"], extra["bars"])
        text += "),"
        segs.append((text, ["segment %d (%s): beats %s .. %s" % (len(segs), k0["clip"], fb(start), fb(end_beat))] + lines))
    kl = kills[-1]
    e, R1, E0 = term["e"], term["R1"], term["E0"]
    segs.append(('    S("%s", [(%s, %d), (%s, %d + %s * F * 0.31)], tin=("soft", %s), mute=True),' % (
        kl["clip"], fb(e), E0, fb(R1), E0, fb(R1 - e), fnum(SOFT)),
        ["segment %d (%s): end card, beats %s .. %s: no zoom, it only fades to black with the music (banner frame %d, %s)" % (
            len(segs), kl["clip"], fb(e), fb(R1), E0, "from the plan" if kl["card"] is not None else "K + 100, or the last footage of the clip")]))
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
    segs, F = ns["SEGS"], ns["FPB"]
    v = []
    for k in range(ns["N_FRAMES"]):
        r = ns["frame_beat"](k)
        v.append(float(segs[ns["active"](r)[0]]["map"](r)[1]))
    v = np.array(v)
    return dict(slow=float((v < 0.85).mean()), real=float(((v >= 0.85) & (v <= 1.25)).mean()), fast=float((v > 1.25).mean()),
                vmin=float(v.min()), vmax=float(v.max()))


def stats(ns, rows=None, att=None):
    segs = ns["SEGS"]
    kinds = collections.Counter(x["tin"][0] for x in segs[1:])
    beats = ns["R1"] - ns["R0"]
    dur = beats * ns["PER"]
    nk = len(ns["KILLS"])
    out = dict(seconds=dur, segments=len(segs), kills=nk, kills_per_beat=nk / beats, kills_per_10s=nk / dur * 10,
               transitions=sum(kinds.values()), kinds=dict(kinds), **speed_shares(ns))
    if rows is not None:
        by = {r[0]: r for r in rows}
        out["transitions_on_kick"] = sum(1 for x in segs[1:] if round(x.get("m0", x["r0"]) * 2) / 2 in by and by[round(x.get("m0", x["r0"]) * 2) / 2][1] >= 0.4)
    return out


def print_stats(title, st):
    print("%-20s %5.1f s  %2d segments  %2d kills (%.2f per beat, %.1f per 10 s)  speed: real %3.0f%%  fast %3.0f%%  slow %3.0f%%  "
          "(%.2fx .. %.2fx)  transitions %d (%s)%s" % (
              title, st["seconds"], st["segments"], st["kills"], st["kills_per_beat"], st["kills_per_10s"], st["real"] * 100,
              st["fast"] * 100, st["slow"] * 100, st["vmin"], st["vmax"], st["transitions"],
              ", ".join("%d %s" % (v, k) for k, v in sorted(st["kinds"].items())),
              (", %d on a kick" % st["transitions_on_kick"]) if "transitions_on_kick" in st else ""))


def verify(ns, rows, att, cuts_on):
    """Independent check of the finished module against the rules of edit-design.md, measured on its TimeMaps and on the SHOWN frames
    (s["kills"], s["r0"]: exact frames; s["hits"], s["m0"]: the musical beats the sound sits on). -> (errors, warnings, kills shown
    twice): the last is a plan problem the caller refuses with its own message (not a bug in the build)."""
    errs, warns, ov = [], [], []
    segs = ns["SEGS"]
    F, nf = ns["FPB"], ns["nearest_frame"]
    by = {r[0]: r for r in rows}
    tt = np.array(sorted(t for t, b, rs in att.all))          # every measured attack of the window: a kill / bass cut must sit on one
    t_of = lambda r: ns["BEAT0"] + (ns["M0"] + r) * ns["PER"]
    on_attack = lambda r: len(tt) and float(np.abs(tt - t_of(r)).min()) < 0.0006
    first_no, no = {}, 0                                      # the plan's kill number of each segment's first kill (one take's kills are consecutive)
    for j, s_ in enumerate(segs):
        first_no[j] = no + 1 if s_["kills"] else None
        no += len(s_["kills"])
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
        for (k, lv), m in zip(s["kills"], s["hits"]):
            kv = float(s["map"](k)[1])
            if abs(kv - 1) > 0.15:
                warns.append("segment %d: the kill at beat %g is reached at %.2fx, not at real speed" % (i, m, kv))
            b = by.get(round(m * 2) / 2)
            if b is None or (b[1] < 0.25 and b[2] < 0.4):
                errs.append("kill at beat %g is not on a kick or a snare" % m)
            elif not on_attack(m):
                errs.append("kill at beat %g is on no measured attack (the beat is not hit(t) of a drum attack)" % m)
            if nf(m) - ns["HIT_LEAD"] != nf(k):
                errs.append("kill at beat %g is not shown HIT_LEAD frames before its hit" % m)
        if i:
            first = min((nf(k) for k, _ in s["kills"]), default=None)
            cut_f = nf(s["r0"])
            if first is not None and (first - cut_f) / F < 1.5 - 1e-9:
                errs.append("segment %d: the first kill is shown %.2f beats after the transition centre (needs 1.5)" % (i, (first - cut_f) / F))
            prev = segs[i - 1]
            if prev["kills"] and prev["kills"][-1][1] == 1:
                after = (cut_f - s["tn"] // 2 - nf(prev["kills"][-1][0])) / F
                if after < 0.5 - 1e-9:
                    errs.append("segment %d: only %.2f beats of real time between the kill before it and the transition" % (i, after))
            if cuts_on == "bass":
                u = round(s["m0"] * 2) / 2
                tl = att.bands.get(u, {}).get("low")
                if tl is None or abs((tl - ns["BEAT0"]) / ns["PER"] - ns["M0"] - s["m0"]) > 1e-6 or u not in by or by[u][1] < 0.4:
                    errs.append("the transition into segment %d at beat %g is not on a kick's attack" % (i, s["m0"]))
            if prev["kills"] and s["kills"] and s["clip"] == prev["clip"]:      # one clip cut twice: the kill must not be a frame already shown
                shown_to = float(prev["map"](prev["x1"])[0])                     # the last source frame the take before it shows (its run-out included)
                kill_src = float(s["map"](s["kills"][0][0])[0])                 # the source frame of this take's first kill
                if kill_src < shown_to + 1 - 1e-6:
                    pno = first_no[i] - 1
                    ov.append("kills #%d (%s K=%d) and #%d (%s K=%d) are two takes of one clip, but the first shows %s up to source frame %.1f and the "
                                "second's kill is at frame %d: the picture would jump back inside the clip and show that kill twice. Mark kill #%d "
                                "\"continuous\": true so both are one take (if their Ks and the speed ramp allow it), or use another kill whose source frames "
                                "start after frame %.0f" % (
                                    pno, prev["clip"], int(round(float(prev["map"](prev["kills"][-1][0])[0]))), first_no[i], s["clip"], int(round(kill_src)),
                                    prev["clip"], shown_to, int(round(kill_src)), first_no[i], shown_to))
    return errs, warns, ov


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


def lead_frames(P):
    """-> ({"CUT_LEAD": n, "HIT_LEAD": n}, [what each came from]). Precedence per trait: the user's words (plan.json) > the reference
    (ref_notes.json "adopt": cut_lead_frames / hit_lead_frames, what its cuts and kill flashes show before the beat) > 1 frame (the
    measured convention of the user's reference edit: a picture one frame ahead of its sound reads as in sync)."""
    adopt = {}
    if os.path.isfile("ref_notes.json"):
        try:
            adopt = (json.load(open("ref_notes.json", encoding="utf-8-sig")).get("adopt") or {})
        except (OSError, ValueError):
            adopt = {}
    out, why = {}, []
    for key, name in (("cut_lead_frames", "CUT_LEAD"), ("hit_lead_frames", "HIT_LEAD")):
        if key in P:
            v, src = P[key], "plan.json"
        elif adopt.get(key) is not None:
            v, src = adopt[key], "ref_notes.json (the reference)"
        else:
            v, src = 1, "the default 1 frame" + (" (ref_notes.json could not measure it)" if "adopt" in adopt or key in adopt else "")
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 3:
            die('%s = %r must be a whole number of frames 0..3' % (key, v), "cannot read the plan")
        out[name] = v
        why.append("%s = %d from %s" % (name, v, src))
    return out, why


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("plan")
    ap.add_argument("-o", "--out", default="timeline.py")
    ap.add_argument("--force", action="store_true", help="overwrite -o even if it holds your own edits")
    ap.add_argument("--example", default="timeline_example.py", help="the template with the draft markers")
    ap.add_argument("--compare", default=None, help="another timeline .py to print statistics for (e.g. timeline_example.py)")
    args = ap.parse_args()
    P, kills = load_plan(args.plan)
    LEADS, lead_why = lead_frames(P)
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
    P["M0"] = M0
    R0 = round(-1.0 - P["lead_in"], 1)           # while planning: the nominal start (the final R0 is the first hit minus the lead-in, below)
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
        rows, att = beat_hits.measure_t(m, P["bpm"], P["beat0"], M0, R0, window)
        att4 = beat_hits.measure_t(m, P["bpm"], P["beat0"], M0, R0, window, sub=4)[1] if P["cuts_on"] == "kills" else None
        pl = Planner(P, kills, rows, att, att4, R0, window, P["final"] if not kills[-1]["cont"] else "tail")
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
            rows2, att2 = beat_hits.measure_t(m, P["bpm"], P["beat0"], M0, R0, wide)
            att42 = beat_hits.measure_t(m, P["bpm"], P["beat0"], M0, R0, wide, sub=4)[1] if P["cuts_on"] == "kills" else None
            pl2 = Planner(P, kills, rows2, att2, att42, R0, wide, pl.final_mode)
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
            chosen = (pl, rows, att, p_last, term)
            break
        window = R1_lo = R1_hi = R1
    if chosen is None:
        die("the measured hits changed between passes; run again with a slightly different length")
    pl, rows, att, p_last, term = chosen
    pos = pl.backtrack(p_last)
    kb = [pl.kt[p] for p in pos]                                    # the musical beat of every kill
    R1 = term["R1"]
    R0 = round(kb[0] - P["lead_in"], 9)                              # the video starts where the first take's lead-in starts: a musical beat, not the 0.1 grid
    if bt(R0) < 0:
        die("the first hit (beat %s) minus a %s-beat lead-in puts the video %.3f s before the start of the song: choose a later drop or a shorter lead_in" % (
            fb(kb[0]), fnum(P["lead_in"]), -bt(R0)))
    FADE_OUT = (pl.snap(R1 - 2.8, R1 - 3.3, R1 - 2.3), R1)           # the ramps start on a line of the song's grid (an ending has no hit)
    segs, final_bullet = build(P, kills, pl, pos, term, R0)

    bpm_txt = fnum(float(P["bpm"]), 9, True)
    music_blk = (
        'MUSIC = "%s"\n'
        "BPM, BEAT0 = %s, %s          # tempo, and the time of the track's first beat (music_grid.py measures BEAT0)\n"
        "M0 = %d                             # timeline beat 0 = this beat of the track (the drop, track beat %d, is beat -1)\n"
        "PER = 60.0 / BPM\n"
        "FPS = 60\n"
        "FPB = FPS * PER                     # output frames per beat (%.2f)\n"
        "R0, R1 = %s, %s                 # first / last beat of the video\n"
        "FADE_OUT = (%s, %s)             # picture and music fade to black over these beats\n"
        "MAX_SPEED = None                    # no ceiling (the blur-ins fast-forward); 1.0 = nothing plays faster than real time. State it, do not omit it\n"
        'CUTS_ON = "%s"                    # where transitions land: "bass" (kicks / 808s only, the default) or "kills" (with the\n'
        "                                    # kill rhythm): the user's choice in the briefing; music_pulses.py checks it.\n") % (
        P["music"], bpm_txt, fnum(P["beat0"], 9), M0, P["drop_beat"], F, fnum(R0, 9, True), fnum(R1, 9, True),
        fnum(FADE_OUT[0], 9, True), fnum(FADE_OUT[1], 9, True), P["cuts_on"])
    cut_blk = ("CUT_LEAD = %d                        # frames a cut / transition centre is shown BEFORE its musical moment (vis()); the reference: 1.3 to 1.9 frames\n"
               "HIT_LEAD = %d                        # frames a shot's muzzle flash and accents and a pulse are shown before their hit\n") % (
        LEADS["CUT_LEAD"], LEADS["HIT_LEAD"])
    riser1 = "dict(a=%s, b=%s, f0=350, f1=7000, curve=1.0, width=1.1, power=2.3, gain=0.13, cut=0.012, seed=1)" % (
        fnum(R0 + 0.2, 9, True), fb(kb[0]))
    if final_bullet:
        kf = kb[-1]
        sweep = "[(%s, 18000), (%s, 1000), (%s, 620), (%s, 620)]" % (fb(kf - 4.7), fb(kf - 3.0), fb(kf - 0.4), fb(kf))
        riser2 = ",\n          dict(a=%s, b=%s, f0=300, f1=9000, curve=1.3, width=1.2, power=2.0, gain=0.20, cut=0.010, seed=2)" % (
            fb(kf - 4.4), fb(kf))
    else:
        sweep, riser2 = "[]", ""
    sound_blk = ("# sound design tied to this piece of music (audio.py); use None / [] to switch off\n"
                 "SWEEP = %s     # low-pass on the music: (beat, cutoff Hz)\n"
                 "RISERS = [%s%s]\n") % (sweep, riser1, riser2)
    segs_txt = "SEGS = [\n" + "\n".join(
        "".join("    # %s\n" % l for l in ex if not l.startswith("take ends")) + text for text, ex in segs) + "\n]\n"
    doc = ('"""The edit, expressed in beats of the music: drafted by draft_timeline.py from %s (plan %s), to be read and\n'
           "tweaked, not trusted blindly. %d kills, %.0f s, CUTS_ON \"%s\", timeline beat 0 = beat %d of the track.\n"
           "Every beat in SEGS is MUSICAL (the measured attack of a hit, 9 decimals); the loop after SEGS shows them on exact frames.\n"
           'Source positions are frame indices of the clips (exact, 60 per second)."""') % (
        os.path.basename(args.plan), hashlib.sha1(open(args.plan, "rb").read()).hexdigest()[:8], len(kills), (R1 - R0) * per, P["cuts_on"], M0)
    src = re.sub(r'\A""".*?"""', lambda mm: doc, tpl, count=1, flags=re.S)
    src = replace_block(src, "music", music_blk)
    src = replace_block(src, "cut", cut_blk)
    src = replace_block(src, "sound", sound_blk)
    src = replace_block(src, "segs", segs_txt + "PULSES = []\n")
    ns = exec_timeline(src)
    # PULSES: the strong hits that carry neither a kill nor a transition (weight 0.5 .. 0.9)
    kbm = [m_ for m_, _, _ in ns["HITS"]]
    ctr = [s["m0"] for s in ns["SEGS"][1:]]
    pulses = []
    for r in rows:
        tb = att.bands.get(r[0], {})
        t = tb.get("low") if (r[1] >= r[2] and "low" in tb) else tb.get("mid")
        if t is None:
            continue
        b, s = ns["hit"](t), max(r[1], r[2])                         # a pulse sits on its measured attack, not on the half beat
        if not R0 <= b <= R1 or s < 0.6 or any(abs(b - x) < 0.5 for x in kbm) or any(abs(b - x) < 0.3 for x in ctr):
            continue
        if final_bullet and kb[-1] - 4.7 < b < kb[-1]:
            continue
        pulses.append((round(b, 9), round(min(0.9, max(0.5, 0.5 + 0.4 * (s - 0.6) / 0.4)), 1)))
    lines, cur = [], "PULSES = ["
    items = ["(%s, %s)" % (fb(b), fnum(w, 1)) for b, w in pulses]
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
    errs, warns, ov = verify(ns, rows, att, P["cuts_on"])
    if ov:
        die(ov, "cannot place these kills without showing one twice")
    if errs:
        die(errs, "built a draft that fails its own check (a bug, or inputs it cannot handle)")
    open(args.out, "w", encoding="utf-8", newline="\n").write(src + SUM + hashlib.sha1(src.encode("utf-8")).hexdigest() + "\n")

    print("music: %s  %s BPM  BEAT0 %s  drop at track beat %d -> M0 %d (the drop is beat -1); R0 %s, R1 %s = %.1f s (asked %.0f s); CUTS_ON = %r" % (
        P["music"], bpm_txt, fnum(P["beat0"], 9), P["drop_beat"], M0, fb(R0), fb(R1), (R1 - R0) * per, P["length"], P["cuts_on"]))
    print("lead: %s; %s" % (lead_why[0], lead_why[1]))
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
        print("note: no lag is typed: audio.py measures every gunshot's own lag (kill_lags.py shows the strips); a kill it cannot measure stops it, then read the strip and type S(lag=...)")
    st = stats(ns, rows, att)
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
    print("next: $PY timeline.py (must pass), $PY music_pulses.py (none / none), $PY ranges.py, $PY audio.py (measures every lag and prints where each gunshot lands)")


if __name__ == "__main__":
    main()
