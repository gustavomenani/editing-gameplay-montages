"""Writes a correct first draft of a reference-style timeline.py (the style of timeline_ref_example.py, with the patterns of the
"model edit": model-edit.md) from measured inputs; you then read it, look at the stills and tweak it (reference-style.md). It does the
arithmetic that hand-written timelines get wrong: every take cut `lead_frames` (14) before its first shot with the footage at real
time up to it, every kill on a measured hit, the death of every enemy shown before the next cut, bullet time into the drop (and
into any kill marked "hit"), the luma fade on a calm last take, the numbering of the music block, anchors inside the clips, speeds
inside sane bounds, and the model's accents (levels, blur-ins, bumps, booms, risers, sound levels, look).

usage (from the project folder: scripts/ + scripts/refstyle/ copied in, after ingest.py and mkpts.py, with a plan.json):
    $PY draft_ref_timeline.py plan.json                  -> timeline.py, plus an explanation of every take
    $PY draft_ref_timeline.py plan.json -o draft.py      -> another file (a timeline.py that you edited is never
                                                            overwritten without --force)
    $PY draft_ref_timeline.py plan.json --compare model.py     statistics next to another timeline (any timeline.py)

plan.json:
  {"music": "src/music.flac",          # default src/music.*
   "bpm": 130, "beat0": 0.4608,        # from music_grid.py
   "drop_beat": 63,                    # TRACK beat of the drop (music_tempo.py lists the re-entries)
   "start_beat": 31,                   # optional: TRACK beat of the first kill (a hit): M0 = start_beat, so the stretch
                                       # between it and the drop is section A and the bullet time is the breakdown before the
                                       # drop. Absent: M0 = drop_beat (the first kill lands on the drop)
   "cuts_on": "kills",                 # "kills" (default, the model: the cut sits lead_frames before the kill) or "bass": the cut sits on
                                       # a kick and the take's first kill at least lead_frames after it
   "lead_frames": 14,                  # optional, 10 .. 20: output frames from the cut to the take's first shot (real time)
   "frame": "vertical",                # default (the whole game in a window, TikTok/Reels/Shorts); or "horizontal"
   "max_speed": 1.0,                   # default: NOTHING plays faster than real time (the user: "do nada voce coloca o video muito rapido").
                                       # Only when the user asks for velocity / aceleracao: 1.6, or null (the old fast-forward behaviour)
   "length": 30,                       # seconds the user asked for; the draft lands within length_tolerance of it
   "length_tolerance": 0.10,           # optional, default 0.10 (a fraction of length)
   "look": "modelo",                   # optional: LOOK of timeline.py (a preset name or a dict, SKILL.md "Edit options"); default "modelo"
   "auto_bullet": true,                # optional, default true: where the drums thin out (a bar or so of weak kick and snare) and no kill is
                                       # marked "bullet": "hit", the draft puts a bullet time into the kill on the next strong hit; false: never
   "intro": {"beats": 12,              # optional intro: bullet-time kills ("kills") or slow ability shots ("shots") at full frame
             "kills": [{"clip": "c02", "K": 640, "upto": 24}, ...],      # each: a 0.12-0.25x lead-in into this kill, then its death
             "shots": [{"clip": "c22", "a": 6650, "b": 6700}, ...],      # the older form: source frames shown in slow motion
             "words": ["ARTIST", "TITLE"]},                              # red words over the intro (artist, title; only with "shots")
   "ref_notes": "ref_notes.json",      # optional (ref_analyze.py): its "pacing" hint (typical clip length in beats) steers the lengths
   "kills": [                          # in the order they play; clip names are the keys of clips.json
     {"clip": "c04", "K": 862, "upto": 24, "level": 2},        # K = muzzle-flash frame (mykills.py / kills.json); upto = frames from K
                                                               # until the body is down (deathstrip.py); default 24, with a note
     {"clip": "c03", "K": 181},
     {"clip": "c03", "K": 199, "with_previous": true},         # same take as the kill before it (an M entry), same clip, later K
     {"clip": "c09", "K": 7385, "level": 3, "bullet": true},   # an L entry: bullet time into this kill, which fires on the drop (one)
     {"clip": "c07", "K": 4185, "bullet": "hit"},              # bullet time (2 to 3 beats, white flash-in, riser, boom) into this kill on
                                                               # a strong hit; any number of them
     {"id": 96},                                               # clip and K from kills.json
     {"clip": "c01", "K": 6198, "level": 3, "mute": true}      # the LAST kill ends the video: calm take, then the luma fade
   ]}
Per kill: "level" 1, 2, 3 (default: 3 on the drop kill, the strongest snare of the body and the last kill; 2 on the first kills after the
drop, on backbeat snares and on "hit" bullets; 1 elsewhere; for an M take the level of its last kill counts); "with_previous" true / false
(kills of one clip closer than a lead plus a death are one take by themselves; "bass" also joins kills at most 6 beats apart in real time;
say false to keep them apart where they fit); "bullet" true (the drop kill) or "hit"; "upto"; "at" (optional: the timeline beat the kill
must land on, a multiple of 0.5, e.g. the last kill on the last sung word; off a measured hit it only warns; intro kills take it too);
"mute" (voice chat over it); "n" (source frames in the blur-in; with max_speed it is a ceiling check, so leave it out).

What it decides, from the music (beat_hits.py: the measure of music_pulses.py) and the clips' lengths (pts/):
  * every take: the cut sits lead_frames (14: the enemy is on screen before he dies) before the take's first shot and the footage runs
    at real time up to it; after the last shot of the take, real time for 8 frames, an ease, then ONE constant slow rate that lands on
    K + upto exactly at the next cut (a window that would need less than 0.15x slows to 0.15x until the body is down, then eases back to
    real time). The next cut is never before the death is shown: that sets the shortest gap between two kills, (lead + upto) / FPB beats;
    "bass": the cut sits on a kick instead and the first kill on the first hit lead_frames or more after it;
  * kills on measured kicks, snares and loud hats; the speed between two kills of one take is at most max_speed and at least 0.6x; when no
    hit sits in that window the two kills become two takes (a cut), never a fast-forward;
  * clip lengths: an even spread toward the length asked, 0.5 to 7 beats; the reference's pacing hint is the length the draft prefers;
  * the drop kill ("bullet": true): a 3 to 6 beat lead-in at 0.5x .. 0.2x (preferred 4 beats) with a white flash-in, an 8-frame ease up to
    real time, push-in 5 %, a riser, a boom; a "hit" bullet: a 2 to 3 beat lead-in at 0.5x, the same flash, riser and boom;
  * a bullet time where the drums thin out ("auto_bullet", only when no kill is marked "hit"): in the body (after the drop, before the last take) it
    looks for 1.5 beats or more where every half beat of kick / snare / hat falls under 25 % of the section's typical hit (the median hit; at most half
    the section's mean level), after a passage that is at least 0.3 louder and followed within 2 beats by a strong hit. The most pronounced one
    (the fall times its length up to a bar) becomes a "hit" bullet: the kill the draft places nearest after it is moved onto that strong hit
    ("at") and drafted again, at most one per 30 s of video. When it cannot fit, or the drums do not thin out, a note says why;
  * intro kills: each take a slow lead-in (0.12 to 0.25x, shutter 2.2, no push, gunshot heard) into a kill on a measured hit, then its death;
  * levels, blur-ins (zoom burst on level 2 / 3 and bullet takes, whips alternating direction, a roll about every fourth take, the opening
    fades in), push-in 3 % (5 % over a bullet time, none in the intro and the calm ending), IMPACT / ACC, BUMPS (light pulses on the strong
    hits that carry no kill, about one per 2.4 s), BOOMS (the drop and the last kill 0.26, the strongest snare 0.18, a "hit" bullet 0.20),
    KILL_THUMP, WHOOSH_BLUR, GAME_LEVEL, HEADROOM, RISERS into the drop and into each "hit" bullet, LOOK "modelo";
  * the last take: calm, slow motion to LUMA_FADE and 1.35 s of black after it, the music fading under it (FADE_OUT);
  * M0 / R0 / R1 / FADE_OUT / LUMA_FADE, intro words.

It refuses, with the numbers, when the plan cannot fit: a hit missing on the drop or on the first kill, too few kicks for the takes,
a clip without enough footage before or after a kill, kills too close for a lead and a death, a length that the kills cannot fill.
The file is built from timeline_ref_example.py by replacing the blocks between its `# >>> draft:...` / `# <<< draft:...` markers.
Before writing it runs the built file: the preflight (clips, anchors, music, MAX_SPEED: every frame at most max_speed), the
music_pulses.py checks (kills on hits, cuts on kicks in "bass"), speeds, the lead of every take, every death shown, and the frames each
take asks of its clip (ranges.py)."""
import argparse, bisect, collections, hashlib, json, math, os, re, sys, types
import numpy as np
import preflight                                  # a clear message when this is not the project's Python
import clipio
import beat_hits

MARGIN = 6              # frames of safety inside a clip (shutter, blur-in)
PRE_N = 16              # "max_speed": null: source frames squeezed into the blur-in (the old behaviour)
RAMP_FRAMES = 8.0       # frames of an ease between real time and slow motion (timeline_ref_example.py: RAMP)
KICK, SNARE, HAT = 0.5, 0.6, 0.65           # strength of a hit that may carry a cut / a kill (music_pulses.py flags < 0.4 / 0.25)
CUT_LOW = 0.4           # what music_pulses.py wants of a cut in "bass"
GAP_KILLS = 0.5         # beats between two kills of one take
LEN_MAX = 7.0           # longest take before the last one
TAIL_S = (2.5, 3.3, 2.84)   # last take after its last kill: (min, max, preferred) SECONDS (the model: the ace, 1.22 s of picture, the fade, 1.35 s of black)
LUMA_S, BLACK_S = 0.27, 1.35        # seconds of the luma fade and of black after it
FADE_OUT_S = (2.15, 0.05)           # the music fades from R1 - 2.15 s to R1 - 0.05 s
VLO = 0.6               # slowest average speed between two kills of a take (slow motion between kills is fine); the fastest is max_speed
VHI_OLD = 1.7           # "max_speed": null (the old behaviour): the example's M entries ran 0.87 to 1.3x
JOIN_FRAMES = 6.0       # "bass" joins kills of one clip closer than this many beats of real time
BULLET = (3.0, 6.0, 4.0)        # lead-in beats of the drop bullet time: (min, max, preferred)
LEAD_SPEEDS = (0.50, 0.30, 0.20, 0.17)
BASS_LEAD_EXTRA = 1.5   # "bass": beats of real-time lead allowed beyond lead_frames between the kick that carries the cut and the first kill
HIT_LEAD = (2.0, 3.0, 2.5)      # lead-in beats of a "hit" bullet: (min, max, preferred)
HIT_SPEEDS = (0.50, 0.40)
INTRO_V = (0.20, 0.17, 0.14, 0.12)      # an intro kill's lead-in speed: the first that the clip has the footage for
INTRO_LEAD_MIN = 2.0            # beats of lead-in an intro kill needs at least
INTRO_H = 6                     # real-time frames after an intro kill's shot
SHUTTER = (2.6, 2.4, 2.2)
UPTO_DEFAULT = 24       # frames from the shot until the body is down, when the plan does not say (the model measured 21 to 28)
STRONG = 0.9            # a hit this strong (0..1) may carry a "hit" bullet and is preferred for kills
SN2 = 0.9               # unclipped snare / clap strength (beat_hits' mid: body and crack both arriving) from which a kill is a backbeat snare (level 2)
LV2_SHARE = 0.25        # at most this share of the takes at level 2 (the model: 5 of 21): level 2 everywhere is no accent; the strongest snares keep it
BUMP_MIN, BUMP_PER_S, BUMP_GAP = 0.7, 0.42, 1.0     # unclipped strength floor (beat_hits' scale: a kick is 0.5 at its weakest, 1.5 at its strongest), bumps per second at most (13 in 31 s), beats between two bumps
THIN_WEAK = 0.35       # a half beat whose drum hit is under this share of the section's typical hit (the median hit) is weak (ghost notes
                       # of a live drummer read 0.29-0.34 on beat_hits' onset measure)
THIN_MIN = 3           # weak half beats in a row that make a thin-out (1.5 beats)
THIN_REL = 0.5         # ... at no more than this share of the section's mean level
THIN_FALL = 0.3        # ... after a passage at least this much louder (0..1 of a typical hit, the 2 beats before)
THIN_NEXT = 2.0        # beats after the thin-out within which a strong hit must come to land the bullet-time kill on
THIN_PER_S = 30.0      # at most one automatic bullet time per this many seconds of video
AUTO_ROOM = 8.0        # beats a strong hit must lie before the last take's kill to carry an automatic bullet time: the last two bars
                       # belong to the ending (the model: the ace kill by kill over the last line), a bullet time there breaks its rhythm
AUTO_SHIFT = 3.0       # beats the drafted kill may lie after that strong hit (it is moved onto it)
AUTO_TRIES = 4         # drafts tried with a bullet time before the plain draft is kept
KEYS = {"music", "bpm", "beat0", "drop_beat", "start_beat", "cuts_on", "lead_frames", "frame", "max_speed", "length", "length_tolerance", "look",
        "intro", "ref_notes", "kills", "auto_bullet"}
SUM = "# draft_ref_timeline.py checksum (a changed file is never overwritten without --force): "


def die(errors, what="cannot draft this plan"):
    if isinstance(errors, str):
        errors = [errors]
    sys.exit("draft_ref_timeline.py %s:\n  - %s\nNothing was written. Fix plan.json (or the inputs) and run it again." % (what, "\n  - ".join(errors)))


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
        if k not in KEYS:
            E.append('plan.json has an unknown key "%s" (known: %s)' % (k, ", ".join(sorted(KEYS))))
    P.setdefault("cuts_on", "kills")
    P.setdefault("frame", "vertical")
    P.setdefault("max_speed", 1.0)
    P.setdefault("length_tolerance", 0.10)
    P.setdefault("look", "modelo")
    P.setdefault("lead_frames", 14)
    P.setdefault("auto_bullet", True)
    if not isinstance(P["auto_bullet"], bool):
        E.append('"auto_bullet" must be true (the default) or false, not %r' % (P["auto_bullet"],))
    if P["cuts_on"] not in ("bass", "kills"):
        E.append('"cuts_on" must be exactly "bass" or "kills", not %r' % (P["cuts_on"],))
    if P["frame"] not in ("horizontal", "vertical"):
        E.append('"frame" must be exactly "horizontal" or "vertical", not %r' % (P["frame"],))
    lf = P["lead_frames"]
    if isinstance(lf, bool) or not isinstance(lf, (int, float)) or not 10 <= lf <= 20:
        E.append('"lead_frames" must be a number from 10 to 20 (output frames from the cut to the take\'s first shot; the model: 14), not %r' % (lf,))
    ms = P["max_speed"]
    if ms is not None and (isinstance(ms, bool) or not isinstance(ms, (int, float)) or not 0.5 <= ms <= 4.0):
        E.append('"max_speed" must be a number from 0.5 to 4 (1.0 = nothing plays faster than real time, the default; 1.6 when the user asks for velocity) '
                 'or null (no ceiling: the footage fast-forwards through the blur-in), not %r' % (ms,))
    music = P.get("music")
    if not music:
        import glob
        hits = sorted(glob.glob("src/music.*"))
        music = hits[0].replace("\\", "/") if hits else "src/music.flac"
    P["music"] = music
    if not os.path.isfile(music):
        E.append("the song %s does not exist: run ingest.py (clips.json key \"music\") or set \"music\" in plan.json" % music)
    if not (P["bpm"] > 0 and P["beat0"] >= 0 and P["length"] >= 8):
        E.append("bpm must be > 0, beat0 >= 0 and length >= 8 seconds")
    P["drop_beat"] = int(round(P["drop_beat"]))
    P["start_beat"] = int(round(P["start_beat"])) if P.get("start_beat") is not None else None
    # the reference's pacing hint (ref_analyze.py): the typical clip length in beats
    P["hint"] = None
    notes = P.get("ref_notes") or ("ref_notes.json" if os.path.isfile("ref_notes.json") else None)
    if notes:
        try:
            pc = (json.load(open(notes, encoding="utf-8-sig")).get("pacing") or {})
            h = pc.get("clip_beats", pc.get("typical_clip_beats"))
            if isinstance(h, (int, float)) and h > 0:
                P["hint"] = float(h)
        except (OSError, ValueError, AttributeError) as e:
            E.append("%s cannot be read (%s)" % (notes, e))
    ks = P["kills"]
    if not isinstance(ks, list) or len(ks) < 2:
        E.append("a draft needs at least 2 kills (a first one and the last one, which ends the video)")
        die(E)
    kills, nb = [], 0
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
                print("note: %s (kills.json %s) has confidence %r: look at its flash frame (strip.py) before trusting it" % (tag, k["id"], e["conf"]))
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
        lv = k.get("level")
        if lv is not None and lv not in (1, 2, 3):
            E.append("%s: level must be 1, 2 or 3" % tag)
        bl = k.get("bullet", False)
        if bl not in (True, False, "hit"):
            E.append('%s: "bullet" must be true (the drop kill), "hit" (a bullet time into a strong hit) or absent, not %r' % (tag, bl))
        lkind = "drop" if bl is True else "hit" if bl == "hit" else None
        nb += lkind == "drop"
        up = k.get("upto")
        if up is not None and (isinstance(up, bool) or not isinstance(up, (int, float)) or not 6 <= up <= 90):
            E.append('%s: "upto" is the number of source frames from the shot until the body is down (6 to 90; deathstrip.py shows it), not %r' % (tag, up))
        at = k.get("at")
        if at is not None and (isinstance(at, bool) or not isinstance(at, (int, float)) or abs(at * 2 - round(at * 2)) > 1e-9):
            E.append('%s: "at" is the timeline beat the kill lands on, a multiple of 0.5 (beat 0 = the first landing / the drop), not %r' % (tag, at))
        wp = k.get("with_previous")
        if wp and i == 0:
            E.append("kill #1 cannot be joined to a kill before it")
        if wp and kills:
            p = kills[-1]
            if p["clip"] != k["clip"]:
                E.append("%s is joined to kill #%d but they are in different clips (%s, %s)" % (tag, i, p["clip"], k["clip"]))
            elif K <= p["K"]:
                E.append("%s is joined to the kill before it but its K = %d is not after K = %d: a take plays forward" % (tag, K, p["K"]))
            if p["bullet"] or lkind:
                E.append("%s: a bullet-time kill is a take of its own (no with_previous on it, or on the kill after it)" % tag)
        npl = k.get("n")
        if npl is not None and ms is not None:
            sq = (float(npl) - 1.0) / (P["lead_frames"] - 1.0)
            if sq > ms * 1.02:
                E.append('%s: "n": %s squeezes %s source frames into the %g frames of the lead = %.1fx, above "max_speed": %g. Leave "n" out '
                         '(the take enters at real time) or raise "max_speed" only when the user asked for velocity' % (tag, npl, npl, P["lead_frames"], sq, ms))
        kills.append(dict(i=i, clip=k["clip"], K=K, n=n, level=lv, wp=wp, bullet=bool(lkind), lkind=lkind, mute=bool(k.get("mute", False)), at=at,
                          pre_n=int(npl) if npl is not None else None, upto=int(up) if up is not None else UPTO_DEFAULT, upto_given=up is not None))
    if nb > 1:
        E.append('only one kill may be "bullet": true (the one on the drop), %d are; use "bullet": "hit" for the others' % nb)
    if E:
        die(E)
    return P, kills


def load_intro(P):
    """-> (beats or None, shots, kills, words)"""
    it = P.get("intro")
    if not it:
        return None, [], [], []
    E = []
    shots, ikills = [], []
    for j, s in enumerate(it.get("shots", [])):
        try:
            n = clipio.n_frames(s["clip"])
            a, b = int(s["a"]), int(s["b"])
        except (KeyError, ValueError, FileNotFoundError) as e:
            E.append("intro shot #%d: %s" % (j + 1, e))
            continue
        if not MARGIN <= a < b <= n - 1 - MARGIN:
            E.append("intro shot #%d (%s %d..%d): the range must lie inside the clip (frames %d..%d, a margin of %d frames kept) and a < b" % (
                j + 1, s["clip"], a, b, MARGIN, n - 1 - MARGIN, MARGIN))
        shots.append(dict(clip=s["clip"], a=a, b=b, n=n))
    for j, s in enumerate(it.get("kills", [])):
        try:
            n = clipio.n_frames(s["clip"])
            K = int(s["K"])
        except (KeyError, ValueError, FileNotFoundError) as e:
            E.append("intro kill #%d: %s" % (j + 1, e))
            continue
        up = s.get("upto")
        if up is not None and (isinstance(up, bool) or not isinstance(up, (int, float)) or not 6 <= up <= 90):
            E.append('intro kill #%d: "upto" is the number of source frames from the shot until the body is down (6 to 90), not %r' % (j + 1, up))
            continue
        if not MARGIN <= K <= n - 1:
            E.append("intro kill #%d (%s K=%d): K must lie inside the clip (frames %d..%d)" % (j + 1, s["clip"], K, MARGIN, n - 1))
        at = s.get("at")
        if at is not None and (isinstance(at, bool) or not isinstance(at, (int, float)) or abs(at * 2 - round(at * 2)) > 1e-9):
            E.append('intro kill #%d: "at" is the timeline beat the kill lands on, a multiple of 0.5, not %r' % (j + 1, at))
        ikills.append(dict(clip=s["clip"], K=K, n=n, at=at, upto=int(up) if up is not None else UPTO_DEFAULT, upto_given=up is not None))
    if shots and ikills:
        E.append('the intro has both "shots" and "kills": use one of them (kills: bullet-time lead-ins into kills; shots: slow ability shots)')
    if E:
        die(E)
    words = [str(w).upper() for w in it.get("words", [])]
    if it.get("beats") is not None and not 2 <= it["beats"] <= 24:
        die('intro "beats" must be between 2 and 24')
    return it.get("beats"), shots, ikills, words


# ------------------------------------------------------------------------------------------------ time and anchors
class Tempo:
    def __init__(self, bpm, max_speed=None, lead_frames=14.0):
        self.bpm, self.per = bpm, 60.0 / bpm
        self.F = 60 * self.per
        self.sc = bpm / 130.0                       # the constants of the example are frames at 130 BPM
        self.lead_frames = float(lead_frames)
        self.lead_b = self.lead_frames / self.F     # beats from the cut to the first shot
        self.hold, self.hold_short, self.thr, self.out = 0.3 * self.sc, 0.2 * self.sc, 0.8 * self.sc, 0.08 * self.sc
        self.max_speed = max_speed                  # None: the old behaviour (fast-forward through the blur-in, speed-ups)
        self.post_fn = None                         # the post() / fall() of the file being built (set_helpers): one source of truth
        self.fall_fn = None
        self.tail = tuple(x / self.per for x in TAIL_S)     # last take after its last kill: (min, max, preferred) beats
        self.final_rate = 0.12 if max_speed is None else 0.10      # the last take's slow motion (the model: about 0.08x under the fade; 0.12x keeps the old fast-forward mode inside the speed limits)

    def pre_src(self, lead_frames, npl=None):
        """source frames the take runs before its first shot (the template's pre())"""
        if npl is not None:
            return float(npl)
        if self.max_speed is None:
            return max(float(PRE_N), lead_frames)
        return 1.0 + max(1.0, self.max_speed / 1.1) * (lead_frames - 1.0)

    def post(self, k, K, end, rate=0.16):
        """max_speed None: the example's post() with its beat constants scaled (draft:post block of the file)"""
        F = self.F
        hold = (self.hold if end - k >= self.thr else self.hold_short)
        rem = end - (k + hold)
        if rem <= 0.02:
            return [(end, K + (end - k) * F)]
        a = [(k + hold, K + hold * F)]
        if rem < 0.45:
            a.append((end, a[-1][1] + rem * F * 0.9))
            return a
        a.append((end - self.out, a[-1][1] + (rem - self.out) * F * rate))
        a.append((end, a[-1][1] + self.out * F * 1.3))
        return a

    def after_final(self, k, K, end, rate, n_frames):
        """The last take after its last shot (slow motion to the end): -> does the clip have the footage"""
        room = n_frames - 1 - MARGIN
        if self.max_speed is not None:
            return self.post_fn(k, K, end, rate, slow=None)[-1][1] <= room
        return self.post(k, K, end, rate)[-1][1] <= room

    def fall_after(self, k, K, end, upto, n_frames, h=8):
        """What follows the last shot of an ordinary take (the file's own fall()): -> does the clip have the footage"""
        try:
            a = self.fall_fn(k, K, end, upto, h)
        except AssertionError:
            return False
        return a[-1][1] <= n_frames - 1 - MARGIN

    def lead(self, S, D, K, speeds=LEAD_SPEEDS, fracs=None):
        """bullet-time lead-in anchors from beat S to the kill at beat D (frame K): -> [(beat, frame)] without the final real-time frame, which
        the example's L entry adds itself. The last anchor is (beat, frame, speed) and starts an 8-frame (RAMP) linear ease from the lead's
        last speed up to real time at the shot (max_speed set; max_speed None: the one-frame snap of the old behaviour).
        fracs None: knots at 0.35 and 0.70 of the lead and one beat before the shot (the drop's lead-in, speeds[j] per stretch);
        fracs (f1, ...): knots at those fractions of the lead, len(fracs) + 1 stretches at speeds[j]"""
        F, Lb = self.F, D - S
        bs = [S]
        if fracs is None:
            for x in (S + 0.35 * Lb, S + 0.70 * Lb, D - 1.0):
                if x - bs[-1] >= 0.4 and D - x >= 0.9:
                    bs.append(round(x, 3))
        else:
            for f in fracs:
                bs.append(round(S + f * Lb, 3))
        f = [None] * len(bs)
        vs = speeds[len(bs) - 1]
        if self.max_speed is None:
            f[-1] = (K - 1) - vs * (F - 1)                          # last segment runs at the slowest speed up to the frame before the kill
        else:
            rd = RAMP_FRAMES / F
            Dp, vr = D - rd, min(1.0, self.max_speed)
            Kp = K - rd * F * (vs + vr) / 2
            f[-1] = Kp - vs * (Dp - bs[-1]) * F
        for j in range(len(bs) - 2, -1, -1):
            f[j] = f[j + 1] - speeds[j] * (bs[j + 1] - bs[j]) * F
        out = [(b, round(x, 1)) for b, x in zip(bs, f)]
        if self.max_speed is not None:
            out.append((round(Dp, 3), round(Kp, 1), vs))
        return out


# ------------------------------------------------------------------------------------------------ the planner
class Hits:
    def __init__(self, rows, raw=None):
        self.low, self.mid, self.high = {}, {}, {}
        for b, lo, mi, hi in rows:
            u = int(round(b * 2))
            self.low[u], self.mid[u], self.high[u] = lo, mi, hi
        self.raw = {int(round(b * 2)): (lo, mi, hi) for b, lo, mi, hi in raw} if raw else {}       # unclipped strengths (levels, bumps)
        self.kicks = sorted(u for u, v in self.low.items() if v >= KICK)
        self.kills = sorted(u for u in self.low if self.can_kill(u))

    def kick(self, u):
        return self.low.get(u, 0) >= KICK

    def can_kill(self, u):
        return self.low.get(u, 0) >= KICK or self.mid.get(u, 0) >= SNARE or self.high.get(u, 0) >= HAT

    def strength(self, u):
        return max(self.low.get(u, 0), self.mid.get(u, 0))

    def score(self, u):
        return max(self.low.get(u, 0), self.mid.get(u, 0), self.high.get(u, 0))

    def snare(self, u):
        """unclipped snare / clap strength (beat_hits' mid) of a hit that is not a kick (0 on a kick); a hat has none"""
        lo, mi, hi = self.raw.get(u, (0.0, 0.0, 0.0))
        return 0.0 if self.low.get(u, 0) >= KICK else mi

    def describe(self, u):
        lo, mi, hi = self.low.get(u, 0), self.mid.get(u, 0), self.high.get(u, 0)
        if lo >= KICK:
            return "kick %.2f" % lo
        if mi >= SNARE:
            return "snare %.2f" % mi
        if hi >= HAT:
            return "hat %.2f" % hi
        return "low %.2f mid %.2f high %.2f" % (lo, mi, hi)


class Take:
    def __init__(self, kills):
        self.kills = kills
        self.clip = kills[0]["clip"]
        self.Ks = [k["K"] for k in kills]
        self.n = kills[0]["n"]
        self.bullet = kills[0]["bullet"]
        self.lkind = kills[0]["lkind"]                  # None, "drop" (on the drop) or "hit" (into a strong hit)
        self.kind = "L" if self.bullet else ("M" if len(kills) > 1 else "K")
        self.pre_n = kills[0]["pre_n"]                  # source frames the plan squeezes into the blur-in (None: the take enters at real time)
        self.level = kills[-1]["level"]
        self.mute = any(k["mute"] for k in kills)
        self.upto = kills[-1]["upto"]                   # frames from the take's last shot until the body is down
        self.at = [k["at"] for k in kills]              # the plan's pinned beat of each kill (None: free)


def group_takes(P, kills, T):
    takes, notes = [], []
    cur = [kills[0]]
    F = T.F
    for k in kills[1:]:
        p = cur[-1]
        join = k["wp"]
        d = k["K"] - p["K"]
        if join is None and not k["bullet"] and not p["bullet"] and k["clip"] == p["clip"] and 0 < d:
            if d <= T.lead_frames + p["upto"] + 2.0:
                join = True
                notes.append("kills #%d and #%d (%s %d, %d) are %d frames apart in one clip: a take needs %g frames of lead and %d of death between two shots, "
                             "so they are one take (\"with_previous\": false would need them %d frames apart)" % (
                                 p["i"] + 1, k["i"] + 1, k["clip"], p["K"], k["K"], d, T.lead_frames, p["upto"], int(T.lead_frames + p["upto"] + 3)))
            elif P["cuts_on"] == "bass" and d <= JOIN_FRAMES * F:
                join = True
                notes.append("kills #%d and #%d (%s %d, %d) are %.1f beats apart in one clip: one take (CUTS_ON \"bass\" needs a kick for each cut; "
                             "\"with_previous\": false keeps them apart)" % (p["i"] + 1, k["i"] + 1, k["clip"], p["K"], k["K"], d / F))
        if join:
            cur.append(k)
        else:
            takes.append(Take(cur))
            cur = [k]
    takes.append(Take(cur))
    return takes, notes


class Solver:
    def __init__(self, P, T, takes, hits, D, bass, hint):
        self.P, self.T, self.takes, self.H, self.D = P, T, takes, hits, D
        self.bass, self.hint = bass, hint
        self.vhi = P["max_speed"] if P["max_speed"] is not None else VHI_OLD      # fastest average speed between two kills of a take
        self.R1_lo = self.R1_hi = self.R1_t = 0.0
        self.explore = False
        self.nf = {t.clip: clipio.n_frames(t.clip) for t in takes}
        self.cache = {}
        self.fail_j = None                              # solve() failed placing this take (0-based): which take blocked the plan

    # ---- footage
    def after_ok(self, tk, last, end, final=False):
        """does the clip have the footage that follows the take's last shot (the death, or the slow ending)"""
        key = (tk.clip, tk.Ks[-1], round(last, 3), round(end, 3), tk.upto, final)
        if key not in self.cache:
            if final:
                self.cache[key] = self.T.after_final(last, tk.Ks[-1], end, self.T.final_rate, self.nf[tk.clip])
            else:
                self.cache[key] = self.T.fall_after(last, tk.Ks[-1], end, tk.upto, self.nf[tk.clip])
        return self.cache[key]

    def lead_anchors(self, tk, S, h):
        if tk.lkind == "drop":
            return self.T.lead(S, h, tk.Ks[0])
        return self.T.lead(S, h, tk.Ks[0], HIT_SPEEDS, (0.55,))

    def pre_ok(self, tk, S, h):
        """does the clip have the footage before the take's first kill (the lead-in, or the real-time lead)"""
        if tk.kind == "L":
            return self.lead_anchors(tk, S, h)[0][1] >= MARGIN
        return tk.Ks[0] - self.T.pre_src((h - S) * self.T.F, tk.pre_n) >= MARGIN

    def kill_bonus(self, u, lv):
        return 0.6 * (lv - 1) * (1 - self.H.strength(u)) if lv > 1 else 0.0

    # ---- one take placed at a head u (half beats): the options for its kills
    def head_beat(self, tk, u):
        """beat of the take's first kill for head u (for the drop bullet the head is the START of the lead-in)"""
        return float(self.D) if tk.lkind == "drop" else u / 2.0

    def options(self, j, u):
        tk = self.takes[j]
        lv = tk.level or (3 if tk.lkind == "drop" or j == len(self.takes) - 1 else 2 if tk.lkind == "hit" else 1)
        if tk.lkind == "drop":
            return [dict(tails=(), last=float(self.D), cost=0.0)]
        h = u / 2.0
        w = 0.25 * (1 - self.H.score(u))                       # a stronger hit is preferred
        if tk.kind in ("K", "L"):
            return [dict(tails=(), last=h, cost=w + self.kill_bonus(u, lv))]
        out = {}
        F = self.T.F
        kh = self.H.kills

        def rec(i, prevb, tails, cost):
            if i == len(tk.Ks):
                last = tails[-1]
                c = cost + self.kill_bonus(int(round(last * 2)), lv)
                if last not in out or c < out[last]["cost"]:
                    out[last] = dict(tails=tuple(tails), last=last, cost=c)
                return
            dF = tk.Ks[i] - tk.Ks[i - 1]
            lo, hi = prevb + max(GAP_KILLS, dF / F / self.vhi), prevb + dF / F / VLO
            a = bisect.bisect_left(kh, int(math.ceil(lo * 2 - 1e-9)))
            pool = kh[a:] if tk.at[i] is None else [int(round(tk.at[i] * 2))]
            for x in pool:
                b = x / 2.0
                if b < lo - 1e-9:
                    continue
                if b > hi + 1e-9:
                    break
                v = dF / ((b - prevb) * F)
                rec(i + 1, b, tails + [b], cost + 2.0 * abs(math.log(v)) + 0.1 * (1 - self.H.score(x)))
        rec(1, h, [], w)
        return list(out.values())

    def heads(self, j):
        """candidate heads (half beats) of take j: the first kill's beat (the drop bullet: the start of its lead-in)"""
        tk = self.takes[j]
        if tk.lkind == "drop":
            if self.bass:
                return [u for u in self.H.kicks if BULLET[0] <= self.D - u / 2.0 <= BULLET[1]]
            return list(range(int(math.ceil((self.D - BULLET[1]) * 2)), int((self.D - BULLET[0]) * 2) + 1))
        if tk.at[0] is not None:
            return [int(round(tk.at[0] * 2))]
        if tk.lkind == "hit":
            strong = [u for u in self.H.kills if self.H.score(u) >= STRONG]
            return strong or self.H.kills
        return self.H.kills

    def start_of(self, j, u, dprev):
        """beat where take j starts (its cut) when its head is u and the take before it needs the picture until beat dprev (the end of the
        death); None when there is no such start"""
        tk, T = self.takes[j], self.T
        h = u / 2.0
        if tk.lkind == "drop":
            return h if h >= dprev - 1e-9 else None
        if tk.lkind == "hit":
            lo, hi = max(h - HIT_LEAD[1], dprev), h - HIT_LEAD[0]
            if self.bass:
                ks = [c / 2.0 for c in self.H.kicks if lo - 1e-9 <= c / 2.0 <= hi + 1e-9]
                return min(ks, key=lambda c: (abs((h - c) - HIT_LEAD[2]), -c)) if ks else None
            s = max(h - HIT_LEAD[2], dprev)
            s = math.ceil(s * 1000 - 1e-6) / 1000.0
            return s if s <= hi + 1e-9 else None
        lim = h - T.lead_b + 1e-9
        if self.bass:
            kicks = self.H.kicks
            i = bisect.bisect_right(kicks, int(math.floor(lim * 2 + 1e-9))) - 1
            if i < 0:
                return None
            c = kicks[i] / 2.0
            if h - c > T.lead_b + BASS_LEAD_EXTRA + 1e-9:       # the nearest kick is too far back: a long real-time lead is dull, this hit is not for this take
                return None
            return c if c >= dprev - 1e-9 else None
        s = h - T.lead_b
        return s if s >= dprev - 1e-9 else None

    def why_not(self, j, cand, layer):
        """one sentence with the numbers: why take j (0-based) has no place after the takes before it"""
        tk, prev = self.takes[j], self.takes[j - 1]
        T = self.T
        F = T.F
        name = "take %d (%s K=%s, %s)" % (j + 1, tk.clip, tk.Ks, tk.kind)
        ends = [last + prev.upto / F for (u0, last) in layer]
        lasts = [last for (u0, last) in layer]
        t0s = [v for v in (self.start0.get((u0, last)) for (u0, last) in layer) if v is not None] or [0.0]
        dmin = min(ends)
        what = "kill-able hit (kick, snare or loud hat)"
        need = ("the take before it (%s K=%s) keeps its last kill until beat %s at the earliest, and the death needs %d frames = %.2f beats on screen after it, so "
                "the next cut is at beat %s or later" % (prev.clip, prev.Ks[-1], fnum(min(lasts), 1), prev.upto, prev.upto / F, fnum(dmin, 2)))
        if tk.lkind == "drop":
            reach = [u for u in cand if u / 2.0 >= dmin - 1e-9]
            return ("%s (bullet time into the drop at beat %g): its lead-in of %g to %g beats must start on %s at beat %s or later, but %s: use fewer kills "
                    "before the drop, kills with a shorter death (\"upto\"), or start_beat earlier" % (
                        name, self.D, BULLET[0], BULLET[1], "a kick" if self.bass else "a beat", " / ".join(fnum(u / 2.0, 1) for u in reach[:8]) or "none", need))
        if tk.kind == "M" and not any(self.options(j, u) for u in cand):
            d = [b - a for a, b in zip(tk.Ks, tk.Ks[1:])]
            return ("%s: its kills are %s frames apart = %s beats at real time, and one take plays them at %.2f to %.2fx, so each later kill needs a hit %s beats "
                    "after the one before it. No hit in reach has one. Give the later kill a take of its own (\"with_previous\": false), or pick kills nearer to a hit" % (
                        name, ", ".join(str(x) for x in d), ", ".join("%.2f" % (x / F) for x in d), VLO, self.vhi,
                        " / ".join("%.2f to %.2f" % (max(GAP_KILLS, x / F / self.vhi), x / F / VLO) for x in d)))
        first = dmin + (HIT_LEAD[0] if tk.lkind == "hit" else T.lead_b)
        def reach_len(u):
            s = self.start_of(j, u, dmin)
            return (s if s is not None else 1e9) - min(t0s)
        reach = [u for u in cand if u / 2.0 >= first - 1e-9 and reach_len(u) <= LEN_MAX + (self.D - min(t0s) if prev.lkind == "drop" else 0.0) + 1e-9]
        if not reach and first > min(t0s) + LEN_MAX:
            return ("take %d (%s K=%s) is too long: the take before it starts at beat %s and its last kill falls at beat %s, but %s: its first kill is at beat %s at the "
                    "earliest, %g frames (%.2f beats) after its cut, so the take would run beyond %g beats. Its kills are %s frames apart: split it "
                    "into two takes (\"with_previous\": false on the later kill) or leave a kill out" % (
                        j, prev.clip, prev.Ks, fnum(min(t0s), 2), fnum(min(lasts), 1), need, fnum(first, 2), T.lead_frames, T.lead_b, LEN_MAX,
                        ", ".join(str(b - a) for a, b in zip(prev.Ks, prev.Ks[1:])) or "-"))
        lst = " ".join(fnum(u / 2.0, 1) for u in reach[:14]) or "none"
        if not reach:
            return ("%s has no %s to start on: %s, and its first kill must follow its cut by %g frames (%.2f beats) at least, so it needs a %s at beat %s or later "
                    "(within %g beats of the previous cut): there is none" % (name, what, need, T.lead_frames, T.lead_b, what, fnum(first, 1), LEN_MAX))
        return ("%s cannot follow take %d: of the %ss within reach (%s) none leaves the footage the take before it needs after its last kill "
                "(clip %s has %d frames after frame %d, it needs %d + the slow motion)" % (name, j, what, lst, prev.clip, self.nf[prev.clip] - 1 - prev.Ks[-1], prev.Ks[-1], prev.upto))

    def solve(self, first):
        """forward DP over the takes; `first` = the head u of take 0. -> ((cost, chain, R1, t_first), None) or (None, reason);
        with self.explore: ((lowest R1, highest R1) reachable, None) whatever the window"""
        takes, T, H = self.takes, self.T, self.H
        n = len(takes)
        F = T.F
        self.start0 = {}
        layer = {}
        s0 = self.start_of(0, first, -1e9)
        if s0 is not None and self.pre_ok(takes[0], s0, self.head_beat(takes[0], first)):
            for o in self.options(0, first):
                layer[(first, o["last"])] = (o["cost"], None, o["tails"], s0)
                self.start0[(first, o["last"])] = s0
        if not layer:
            return None, "take 1 (%s K=%s) has no placement at beat %g (%s)" % (takes[0].clip, takes[0].Ks, first / 2.0,
                                                                              "not enough footage before its first kill" if s0 is not None else "no cut position before it")
        layers = [layer]
        t_first = s0
        beats_avail = self.R1_hi - t_first
        lbar = max(0.75, (beats_avail * 0.97 - T.tail[2]) / max(1, n - 1)) if n > 1 else 1.0
        lpref = self.hint if self.hint else lbar
        cands = [self.heads(j) for j in range(n)]
        for j in range(1, n):
            tk, prev_tk = takes[j], takes[j - 1]
            nxt = {}
            for (u0, last), (c0, _, tails0, t0) in layers[-1].items():
                dprev = last + prev_tk.upto / F                  # the take before it needs the picture until its enemy is down
                for u in cands[j]:
                    h = self.head_beat(tk, u)
                    if h < dprev + (HIT_LEAD[0] if tk.lkind == "hit" else T.lead_b if tk.lkind != "drop" else 0.0) - 1e-9:
                        continue
                    s = self.start_of(j, u, dprev)
                    if s is None:
                        continue
                    L = s - t0
                    if L > LEN_MAX + (self.D - t0 if prev_tk.lkind == "drop" else 0.0) + 1e-9:
                        break
                    if L < 0.5 - 1e-9:
                        continue
                    if not self.after_ok(prev_tk, last, s):
                        continue
                    if not self.pre_ok(tk, s, h):
                        continue
                    if h > self.R1_hi - T.tail[0]:
                        break
                    pen = ((L - lpref) / lpref) ** 2 + (0.3 if L < 0.99 and not (self.hint and self.hint <= 0.5) else 0.0)
                    if tk.lkind == "drop":
                        pen += 0.05 * ((self.D - s) - BULLET[2]) ** 2
                    elif tk.lkind == "hit":              # the drums thin out where a bullet time belongs: fewer strong kicks inside its lead-in
                        pen += 0.15 * sum(1 for x in H.kicks if s <= x / 2.0 < h)
                    else:                                # "bass": the nearer the kick before the first kill, the shorter the real-time lead
                        pen += 0.2 * ((h - s) - T.lead_b)
                    for o in self.options(j, u):
                        key = (u, o["last"])
                        c = c0 + pen + o["cost"]
                        if key not in nxt or c < nxt[key][0]:
                            nxt[key] = (c, (u0, last), o["tails"], s)
                            self.start0[key] = s
            if not nxt:
                self.fail_j = j
                return None, self.why_not(j, cands[j], list(layers[-1].keys()))
            layers.append(nxt)
        # the last take: calm, then the luma fade; R1 on the 0.1 grid
        best, feas = None, []
        tk = takes[-1]
        for (u, last), (c, _, _, _) in layers[-1].items():
            for r in range(int(math.ceil((last + T.tail[0]) * 10)), int((last + T.tail[1]) * 10) + 1):
                R1 = r / 10.0
                if not self.after_ok(tk, last, R1, True):
                    continue
                feas.append(R1)
                if not self.R1_lo - 1e-9 <= R1 <= self.R1_hi + 1e-9:
                    continue
                tail = R1 - last
                cost = c + ((tail - T.tail[2]) / T.tail[2]) ** 2 + 0.08 * (R1 - self.R1_t) ** 2
                if best is None or cost < best[0]:
                    best = (cost, (u, last), R1)
        if self.explore:
            return ((min(feas), max(feas)) if feas else None), None
        if best is None:
            self.fail_j = n
            return None, ("the last take (%s K=%s) cannot reach an R1 inside %s .. %s with a %.1f to %.1f s calm ending (the takes before it end between beat %s and %s)" % (
                tk.clip, tk.Ks, fnum(self.R1_lo, 1), fnum(self.R1_hi, 1), TAIL_S[0], TAIL_S[1],
                fnum(min(f for f in feas), 1) if feas else "?", fnum(max(feas), 1) if feas else "?"))
        cost, key, R1 = best
        chain = []
        for j in range(n - 1, -1, -1):
            c, prevk, tails, s = layers[j][key]
            chain.append(dict(u=key[0], last=key[1], tails=tails, start=s))
            key = prevk
        chain.reverse()
        return (cost, chain, R1, t_first), None


def split_unplaceable(takes, P, T, H, D, bass):
    """-> (takes, notes). An M take plays its kills at an average speed between VLO and max_speed, so each later kill needs a hit (kick,
    snare or loud hat) at least its real-time distance after the one before it. When no head gives such a chain anywhere in the song
    window the take is split before the first kill that has no place: the later kills become a take of their own (a cut). That is the
    only alternative to fast-forwarding, which this style never does."""
    F = T.F
    vhi = P["max_speed"] if P["max_speed"] is not None else VHI_OLD

    def feasible(ks):
        tk = Take(ks)
        if tk.kind != "M":
            return True
        S = Solver(P, T, [tk], H, D, bass, None)
        return any(S.options(0, u) for u in H.kills)

    def split(ks, why):
        if feasible(ks):
            return [Take(ks)]
        for i in range(len(ks) - 1, 0, -1):
            if feasible(ks[:i]):
                a, b = ks[i - 1], ks[i]
                d = (b["K"] - a["K"]) / F
                why.append("kills #%d and #%d (%s %d, %d) are %.2f beats apart at real time and no hit that can carry a kill follows a hit by %.2f to %.2f beats "
                           "(a take plays its kills at %.2f to %.2fx, never faster): two takes, the later one cut in %s" % (
                               a["i"] + 1, b["i"] + 1, a["clip"], a["K"], b["K"], d, max(GAP_KILLS, d / vhi), d / VLO, VLO, vhi,
                               "on a kick (CUTS_ON \"bass\")" if bass else "a lead before its kill"))
                return [Take(ks[:i])] + split(ks[i:], why)
        raise AssertionError("a single kill is always placeable")

    out, notes = [], []
    for tk in takes:
        out += split(tk.kills, notes) if tk.kind == "M" else [tk]
    return out, notes


def cut_block(P):
    return ("LEAD_FRAMES = %s                    # output frames from a take's cut to its first shot (real time: the enemy is on screen before he dies)\n"
            "CUT = LEAD_FRAMES / F               # the same in beats (about 0.48 beat at 124 BPM)\n"
            "PUSH = 0.03                         # slow push-in of a take (5 %% over a bullet time, none in the intro and the calm ending)\n") % fnum(float(P["lead_frames"]), 2)


POST_BLK = ("_post_130 = post\n\n\n"
            "def post(k, K, end, rate=0.16, hold=None, out=None, slow=SLOW_MAX):\n"
            '    """post() with its beat constants (0.3 / 0.2 beat of real time, 0.08 beat of speed-up) scaled to this tempo."""\n'
            "    SC = BPM / 130.0\n"
            "    if hold is None:\n"
            "        hold = (0.3 if end - k >= 0.8 * SC else 0.2) * SC\n"
            "    return _post_130(k, K, end, rate, hold, 0.08 * SC if out is None else out, slow)\n\n\n")


def music_block(P, bpm_txt, M0, D, F, R0, R1, last=None):
    ms = P["max_speed"]
    per = 60.0 / P["bpm"]
    f0 = R1 - FADE_OUT_S[0] / per
    if last is not None:
        f0 = max(f0, last + 0.5 / per)                  # never before the last kill's first half second
    return ('MUSIC = "%s"\n'
            "BPM, BEAT0 = %s, %s          # tempo, and the time of the track's first beat (music_grid.py measures BEAT0)\n"
            "M0 = %d                             # timeline beat 0 = this beat of the track = the first landing (the drop is track beat %d = beat %s)\n"
            "PER = 60.0 / BPM\n"
            "FPS = 60\n"
            "FPB = FPS * PER                     # output frames per beat (%.2f)\n"
            "R0, R1 = %s, %s                 # first / last beat of the video (%.1f s)\n"
            "FADE_OUT = (%s, %s)             # the music fades over these beats (under the slow motion and the black)\n"
            "LUMA_FADE = (%s, %s)            # the picture: dark areas go black first, highlights last, on the calm last take; then %.2f s of black\n"
            'CUTS_ON = "%s"                    # where cuts land: "kills" (the cut sits before the kill) or "bass" (on a kick): the user\'s choice in the briefing\n'
            'FRAME = "%s"                # "horizontal" (1920x1080) or "vertical" (1080x1920: the gameplay in a window over a blurred backdrop)\n'
            "MAX_SPEED = %s                    # %s\n") % (
        P["music"], bpm_txt, fnum(P["beat0"]), M0, P["drop_beat"], fnum(D), F, fnum(R0, 4, True), fnum(R1, 4, True), (R1 - R0) * per,
        fnum(f0, 4, True), fnum(R1 - 0.05 / per, 4, True), fnum(R1 - (BLACK_S + LUMA_S) / per, 4, True), fnum(R1 - BLACK_S / per, 4, True), BLACK_S,
        P["cuts_on"], P["frame"],
        "None" if ms is None else fnum(ms, 3, True),
        "no ceiling: the old fast-forward through the blur-in and after the slow motion (the user asked for velocity)" if ms is None else
        "nothing plays faster than real time (the user: \"do nada voce coloca o video muito rapido\"); 1.6 or None only when the user asks for velocity; preflight.py checks it")


def set_helpers(tpl, P, T, M0, D):
    """The take helpers (pre, post, fall, lead-in arithmetic) of the file being built, executed from the template with this plan's music, cut
    and post blocks and no entries: Tempo asks the file's own post() and fall() how much footage a take needs, so there is one of each."""
    bpm_txt = "%.1f" % P["bpm"] if float(P["bpm"]) == int(P["bpm"]) else fnum(float(P["bpm"]))
    src = tpl
    for name, blk in (("music", music_block(P, bpm_txt, M0, D, T.F, 0.0, 1.0)), ("sound", "SWEEP = None\nRISERS = []\n"), ("cut", cut_block(P)),
                      ("post", POST_BLK), ("entries", "E = []\n"), ("words", "_T = []\n")):
        src = replace_block(src, name, blk)
    ns = exec_timeline(src, "helpers")
    T.post_fn, T.fall_fn = ns["post"], ns["fall"]


# ------------------------------------------------------------------------------------------------ building the file
def tin_text(kind):
    if kind[0] in ("bwhip", "broll"):
        return '("%s", 0.0, %d)' % (kind[0], kind[2])
    return '("%s", 0.0)' % kind[0]


def opts_text(o):
    return "dict(%s)" % ", ".join("%s=%s" % (k, v) for k, v in o) if o else "{}"


def replace_block(src, name, new):
    pat = re.compile(r"(^# >>> draft:%s[^\n]*\n)(.*?)(^# <<< draft:%s[^\n]*\n)" % (name, name), re.S | re.M)
    if not pat.search(src):
        die("timeline_ref_example.py has no `# >>> draft:%s` ... `# <<< draft:%s` markers (an old copy?): take scripts/refstyle/*.* again" % (name, name),
            "cannot build the file")
    return pat.sub(lambda m: m.group(1) + new + m.group(3), src, count=1)


def untouched_draft(text):
    """True for a file this script wrote and nobody edited since (its last line is the checksum of the rest)."""
    i = text.rfind(SUM)
    return i > 0 and text[i + len(SUM):].strip() == hashlib.sha1(text[:i].encode("utf-8")).hexdigest()


def exec_timeline(src, name="draft"):
    ns = {"__name__": name}
    exec(compile(src, name, "exec"), ns)
    return ns


def pick_bumps(H, kill_beats, R0, luma0, calm0, seconds):
    """BUMPS: the strongest hits (kick or snare, unclipped strength >= BUMP_MIN) without a kill within 0.3 beat, none in the calm last take or
    after the luma fade, at most BUMP_PER_S per second (the model: 13 in 31 s) and BUMP_GAP beats apart. -> [(beat, strength 0..1)]"""
    cand = []
    for u, (lo, mi, hi) in sorted(H.raw.items()):
        b, st = u / 2.0, max(lo, mi)
        if st >= BUMP_MIN and R0 + 0.4 < b < min(luma0, calm0) and all(abs(b - k) > 0.3 for k in kill_beats):
            cand.append((st, b))
    cand.sort(reverse=True)
    chosen = []
    for st, b in cand:
        if len(chosen) >= int(round(BUMP_PER_S * seconds)):
            break
        if all(abs(b - c) >= BUMP_GAP for _, c in chosen):
            chosen.append((st, b))
    if not chosen:
        return []
    lo, hi = min(s for s, _ in chosen), max(s for s, _ in chosen)
    return [(b, round(0.25 + 0.65 * ((s - lo) / (hi - lo) if hi > lo else 1.0), 2)) for s, b in sorted(chosen, key=lambda x: x[1])]


# ------------------------------------------------------------------------------------------------ statistics and checks
def stats(ns, hits=None):
    segs = ns["SEGS"]
    F = ns["FPB"]
    v = preflight.frame_speeds(types.SimpleNamespace(**ns))[1]            # the speed every output frame plays at (source frames per output frame)
    lens = [s["r1"] - s["r0"] for s in segs if not s.get("intro")]
    kinds = collections.Counter(s["tin"][0] for s in segs[1:])
    out = dict(seconds=(ns["R1"] - ns["R0"]) * ns["PER"], takes=len(segs), kills=len(ns["KILLS"]), lens=lens,
               slow=float((v < 0.85).mean()), slow06=float((v < 0.6).mean()), real=float(((v >= 0.85) & (v <= 1.02)).mean()), fast=float((v > 1.02).mean()),
               vmin=float(v.min()), vmax=float(v.max()), kinds=dict(kinds), max_speed=ns.get("MAX_SPEED"))
    out["kills_per_10s"] = out["kills"] / out["seconds"] * 10
    out["whips"] = collections.Counter(s["tin"][2] for s in segs[1:] if s["tin"][0] == "bwhip" and len(s["tin"]) > 2)
    kb = [k for k, _, _ in ns["KILLS"]]
    out["gaps"] = list(np.diff(kb))
    out["levels"] = dict(collections.Counter(lv for _, lv, _ in ns["KILLS"]))
    leads, shown = [], []
    E = ns.get("E") or []
    deaths = [0, 0]
    for i, s in enumerate(segs):
        if not s["kills"]:
            continue
        k0, kl = s["kills"][0][0], s["kills"][-1][0]
        e = E[i] if i < len(E) else None
        if not s.get("intro") and e is not None and e[0] in ("K", "M"):
            leads.append((k0 - s["r0"]) * F)
        shown.append(float(s["map"](s["r1"])[0] - s["map"](kl)[0]))
        up = e[-1].get("upto") if e is not None and isinstance(e[-1], dict) else None
        if up:
            deaths[1] += 1
            deaths[0] += shown[-1] >= up - 0.75
    out["leads"], out["shown"], out["deaths"] = leads, shown, tuple(deaths)
    out["bumps"], out["booms"], out["risers"] = len(ns.get("BUMPS", [])), len(ns.get("BOOMS", [])), len(ns.get("RISERS", []))
    if hits is not None:
        cuts = [int(round(s["r0"] * 2)) for s in segs[1:]]
        out["cuts"] = len(cuts)
        out["cuts_on_kick"] = sum(1 for u in cuts if hits.low.get(u, 0) >= CUT_LOW)
        ku = [int(round(k * 2)) for k, _, _ in ns["KILLS"]]
        out["on_grid"] = sum(1 for k in kb if abs(k - round(k * 2) / 2.0) <= 0.3)
        out["kill_on"] = dict(kick=sum(1 for u in ku if hits.low.get(u, 0) >= KICK),
                              snare=sum(1 for u in ku if hits.low.get(u, 0) < KICK and hits.mid.get(u, 0) >= SNARE),
                              hat=sum(1 for u in ku if hits.low.get(u, 0) < KICK and hits.mid.get(u, 0) < SNARE and hits.high.get(u, 0) >= 0.5))
        out["kill_hit"] = sum(1 for u in ku if hits.can_kill(u))
    return out


def print_stats(title, st):
    d = collections.Counter()
    for L in st["lens"]:
        d["<=0.75" if L <= 0.75 else "1" if L <= 1.5 else "2" if L <= 2.5 else "3-4" if L <= 4.5 else ">4.5"] += 1
    order = ["<=0.75", "1", "2", "3-4", ">4.5"]
    pad = "%22s " % ""
    print("%-22s %5.1f s  %2d takes  %2d kills (%.1f per 10 s)  speed per frame: slow(<0.85x) %3.0f%%  below 0.6x %3.0f%%  real %3.0f%%  faster than real %3.0f%%  (%.2fx .. %.2fx%s)" % (
        title, st["seconds"], st["takes"], st["kills"], st["kills_per_10s"], st["slow"] * 100, st["slow06"] * 100, st["real"] * 100, st["fast"] * 100, st["vmin"], st["vmax"],
        "; MAX_SPEED %g" % st["max_speed"] if st.get("max_speed") is not None else "; no MAX_SPEED"))
    print(pad + "take length in beats (intro excluded): median %.2f, %s" % (
        float(np.median(st["lens"])) if st["lens"] else 0, "  ".join("%s: %d" % (k, d[k]) for k in order if d[k])))
    if st["gaps"]:
        g = np.array(st["gaps"])
        print(pad + "kill gaps in beats: median %.2f, min %.2f, max %.2f" % (np.median(g), g.min(), g.max()))
    if st["leads"]:
        ld = np.array(st["leads"])
        print(pad + "lead (frames from the cut to the first shot, K / M takes): median %.1f, min %.1f, max %.1f; frames shown after the last shot: median %.1f, min %.1f" % (
            np.median(ld), ld.min(), ld.max(), np.median(st["shown"]), min(st["shown"])))
    if st["deaths"][1]:
        print(pad + "deaths shown (frames after the shot >= upto): %d of %d" % st["deaths"])
    extra = []
    if "cuts" in st:
        extra.append("cuts on a kick: %d of %d" % (st["cuts_on_kick"], st["cuts"]))
        extra.append("kills on a hit %d of %d (kick %d, snare %d, hat %d)" % (st["kill_hit"], st["kills"], st["kill_on"]["kick"], st["kill_on"]["snare"], st["kill_on"]["hat"]))
    extra.append("levels " + " ".join("%d:%d" % (k, v) for k, v in sorted(st["levels"].items())))
    print(pad + "; ".join(extra))
    print(pad + "blur-ins: " + ", ".join("%d %s" % (v, k) for k, v in sorted(st["kinds"].items())) +
          ("; whips +1: %d, -1: %d" % (st["whips"].get(1, 0), st["whips"].get(-1, 0)) if st["whips"] else "") +
          "; bumps %d, booms %d, risers %d" % (st["bumps"], st["booms"], st["risers"]))


def verify(ns, rows_hits, cuts_on, lead_frames, pins=()):
    """Independent check of the finished module: preflight, then the music_pulses.py rules, speeds, the lead of every take, every death shown
    and the footage each take asks of its clip (ranges.py), all measured on the module's own TimeMaps. -> (errors, warnings)"""
    errs, warns = [], []
    T = types.SimpleNamespace(**ns)
    errs += preflight.check(T, music=True)
    if errs:
        return errs, warns
    H = rows_hits
    segs, F, R0 = ns["SEGS"], ns["FPB"], ns["R0"]
    SHUT = float(re.search(r"^SHUTTER = ([0-9.]+)", open("render.py", encoding="utf-8").read(), re.M).group(1)) if os.path.isfile("render.py") else 0.65
    prev_kind = None
    E = ns["E"]
    for i, s in enumerate(segs):
        p, v = s["map"](np.linspace(s["r0"], s["r1"], 600))
        if not np.all(np.diff(p) > 0):
            errs.append("take %d: the time map does not move forward" % i)
        if (v.max() > 6.0 and ns.get("MAX_SPEED") is None) or v.min() < 0.03:     # the worked example runs 0.036x .. 5.85x (the 16-frame blur-in squeeze is 5.8x)
            errs.append("take %d (%s): speed %.3f .. %.2f outside 0.03 .. 6.0" % (i, s["clip"], v.min(), v.max()))
        if s["r1"] - s["r0"] < 0.5 - 1e-6:
            errs.append("take %d is only %.2f beats long" % (i, s["r1"] - s["r0"]))
        # footage with the shutter, as ranges.py asks for it
        n = clipio.n_frames(s["clip"])
        hh = s.get("shutter", SHUT) / F / 2
        rs = np.arange(max(R0, s["r0"]), s["r1"], 1.0 / F)
        if len(rs):
            p0, p1 = s["map"](rs - hh)[0], s["map"](rs + hh)[0]
            if p0.min() < 0 or p1.max() > n - 1:
                errs.append("take %d (%s): frames %.1f .. %.1f leave the clip (0..%d)" % (i, s["clip"], p0.min(), p1.max(), n - 1))
        for k, lv in s["kills"]:
            u = int(round(k * 2))
            if abs(k - u / 2.0) > 1e-9 or not H.can_kill(u):
                (warns if s.get("intro") or k in pins else errs).append("the kill at beat %g is not on a kick, snare or loud hat (%s)%s" % (
                    k, H.describe(u), ": the intro is too quiet for a measured hit there, the kill sits on the beat grid" if s.get("intro") else
                    ": the plan pins it there (\"at\"); music_pulses.py will list it" if k in pins else ""))
            kv = float(s["map"](k)[1])
            if not 0.5 <= kv <= 2.5:
                errs.append("take %d: the shot at beat %g plays at %.2fx: its flash would show late" % (i, k, kv))
            elif not 0.6 <= kv <= max(1.6, ns.get("MAX_SPEED") or 0):
                warns.append("take %d: the shot at beat %g plays at %.2fx (the example prints the same note): look at its stills" % (i, k, kv))
        e = E[i]
        if e[0] in ("K", "M"):                           # the enemy is on screen before he dies: the lead
            lead = (s["kills"][0][0] - s["r0"]) * F
            if lead < lead_frames - 0.05:
                errs.append("take %d (%s) has a lead of %.1f frames from its cut to its first shot (lead_frames = %g)" % (i, s["clip"], lead, lead_frames))
        up = e[-1].get("upto") if isinstance(e[-1], dict) else None
        if up and s["kills"]:                            # every death shown
            Kl = float(s["map"](s["kills"][-1][0])[0])
            got = float(s["map"](s["r1"])[0]) - Kl
            if got < up - 0.75:
                errs.append("take %d (%s K=%d): the take ends %.1f frames after the shot but the death needs upto = %d" % (i, s["clip"], round(Kl), got, up))
        if i:
            u = int(round(s["r0"] * 2))
            if cuts_on == "bass" and H.low.get(u, 0) < CUT_LOW:
                errs.append("the cut into take %d at beat %g is not on a kick (low %.2f)" % (i, s["r0"], H.low.get(u, 0)))
            kind = s["tin"]
            if prev_kind == kind:
                errs.append("take %d has the same blur-in as take %d (%s)" % (i, i - 1, kind[0]))
            prev_kind = kind
        else:
            prev_kind = s["tin"]
    last = segs[-1]
    if not last.get("calm"):
        errs.append("the last take is not calm")
    f0, f1 = ns["LUMA_FADE"]
    if not (last["r0"] < f0 < f1 <= ns["R1"] + 1e-9):
        errs.append("LUMA_FADE %s does not lie inside the last take (beats %g .. %g)" % (ns["LUMA_FADE"], last["r0"], ns["R1"]))
    for a, b, w, st in ns["TEXT"]:
        if b <= a + 0.2:
            errs.append("word %s is on screen too briefly" % w)
    return errs, warns


# ------------------------------------------------------------------------------------------------ levels, blur-ins
def assign_levels(takes, H, ib, n):
    """level of every take: the plan's, else 3 on the drop kill, the strongest snare of the body and the last kill; 2 on the first two takes
    after the drop, on the strongest backbeat snares (level 2 on at most LV2_SHARE of the takes in all) and on "hit" bullets; 1 elsewhere.
    Sets tk.lv and tk.first_after_drop. -> the take index of the
    strongest snare (or None)"""
    snare = {}
    for j, tk in enumerate(takes):
        if tk.level is None and tk.kind != "L" and j != n - 1:
            snare[j] = H.snare(int(round(tk.last * 2)))
    best = max(snare, key=snare.get) if snare and max(snare.values()) >= SN2 else None
    after, nk = set(), 0                                    # the takes holding the first two kills after the drop
    for j in range((ib if ib is not None else -1) + 1, n - 1):
        if nk >= 2:
            break
        after.add(j)
        nk += len(takes[j].Ks)
    fixed2 = sum(1 for j, tk in enumerate(takes) if tk.level is None and j != best and (tk.lkind == "hit" or (j in after and tk.lkind != "drop" and j != n - 1)))
    room = max(0, int(round(LV2_SHARE * n)) - fixed2)       # backbeat snares that may still get level 2, the strongest first
    snares2 = set(sorted((j for j, v in snare.items() if v >= SN2 and j != best and j not in after), key=lambda j: -snare[j])[:room])
    if len(snares2) < room:                                 # few kills on real snares / claps (a trap beat whose kills sit on 808s and
        def _hit(j):                                        # hats): the strongest other hits fill the share, so the accents keep the model's
            return H.score(int(round(takes[j].last * 2)))   # proportion instead of falling to 3 of 24
        rest = sorted((j for j in snare if j not in snares2 and j != best and j not in after and _hit(j) >= STRONG), key=lambda j: -_hit(j))
        snares2 |= set(rest[:room - len(snares2)])
    for j, tk in enumerate(takes):
        tk.first_after_drop = j in after
        lv = tk.level
        if lv is None:
            if tk.lkind == "drop" or j == n - 1:
                lv = 3
            elif tk.lkind == "hit":
                lv = 2
            elif j == best:
                lv = 3
            elif tk.first_after_drop or j in snares2:
                lv = 2
            else:
                lv = 1
        tk.lv = lv
    return best


def assign_tins(ent, takes):
    """blur-in of every entry: the first fades in; the intro has soft whips only; a zoom burst on level 2 / 3 and bullet takes; whips alternating
    direction on the others, a roll about every fourth take; never the same twice in a row"""
    tins, wd, rd, body = [], 1, 1, 0
    for i, e in enumerate(ent):
        if i == 0:
            kind = ("fade", 0.0)
        elif e["kind"] in ("shot", "ikill"):
            kind = ("bwhip", 0.0, wd)
            wd = -wd
        else:
            tk = e["tk"]
            body += 1
            if tk.lv >= 2 or tk.kind == "L":
                kind = ("bzoom", 0.0)
            elif body % 4 == 3:
                kind = ("broll", 0.0, rd)
                rd = -rd
            else:
                kind = ("bwhip", 0.0, wd)
                wd = -wd
        if i and tins[-1][0] == kind[0] == "bzoom":
            kind = ("bwhip", 0.0, wd)
            wd = -wd
        if i and tins[-1] == kind:
            kind = ("bwhip", 0.0, -kind[2]) if kind[0] == "bwhip" else ("bwhip", 0.0, wd)
        tins.append(kind)
    return tins


def layout_intro_kills(ik, H, R0, t1, bass, T):
    """-> [dict(start, kill, end, v, ...)]: each intro kill gets an equal stretch of [R0, t1]; its kill sits on a measured hit about 0.6 of the way, with
    INTRO_LEAD_MIN beats of lead-in before it and its death (upto frames + a few) after it"""
    n, F = len(ik), T.F
    bounds = [R0]
    for j in range(1, n):
        x = R0 + j * (t1 - R0) / n
        if bass:
            ks = [u / 2.0 for u in H.kicks if bounds[-1] + 3.0 <= u / 2.0 <= t1 - 3.0]
            if ks:
                x = min(ks, key=lambda b: abs(b - x))
        else:
            x = round(x * 2) / 2.0
        bounds.append(x)
    bounds.append(t1)
    out, errs = [], []
    for j, k in enumerate(ik):
        s, e = bounds[j], bounds[j + 1]
        lo, hi = s + INTRO_LEAD_MIN, e - (k["upto"] + 4.0) / F
        pool = [x / 2.0 for x in range(int(math.ceil(lo * 2 - 1e-9)), int(math.floor(hi * 2 + 1e-9)) + 1)]       # the intro is often quiet: any half beat, a hit first
        if k.get("at") is not None:
            pool = [k["at"]] if lo - 1e-9 <= k["at"] <= hi + 1e-9 else []
        if not pool:
            errs.append("intro kill #%d (%s K=%d): its stretch of the intro is beats %s .. %s (%.1f beats); it needs %g beats of lead-in and %d frames (%.2f beats) of death after "
                        "the shot, so its kill must fall in beats %s .. %s, and no hit that can carry a kill sits there. A longer intro (\"beats\"), fewer intro kills, or a "
                        "smaller \"upto\"" % (j + 1, k["clip"], k["K"], fnum(s, 1), fnum(e, 1), e - s, INTRO_LEAD_MIN, k["upto"] + 4, (k["upto"] + 4.0) / F, fnum(lo, 1), fnum(hi, 1)))
            continue
        tgt = s + 0.6 * (e - s)
        h = min(pool, key=lambda b: abs(b - tgt) + (0.0 if H.score(int(round(b * 2))) >= STRONG else 1.5 if H.can_kill(int(round(b * 2))) else 3.0))
        out.append(dict(k, start=s, kill=h, end=e, on_hit=H.can_kill(int(round(h * 2)))))
    if errs:
        die(errs, "cannot place the intro kills")
    return out


# ------------------------------------------------------------------------------------------------ drum thin-outs
def thin_outs(H, a, z):
    """Stretches of the body (beats a .. z) where the drums fall away: -> (stretches, R, typ), most pronounced first.
    The strength of a half beat is d = the loudest of kick / snare / hat in beat_hits' unclipped measure, read against the section:
    v = min(1, d / R) with R = the median d of the half beats that carry a hit (d >= KICK), typ = the mean v over the body. A stretch is
    THIN_MIN or more half beats in a row with v < THIN_WEAK that (1) sit at no more than THIN_REL of typ, (2) FALL from the 2 beats before them
    (those average THIN_FALL or more above the stretch: a part that is quiet throughout is no thin-out) and (3) are followed, within THIN_NEXT beats
    of their end, by a strong hit (STRONG) that can carry a kill. Rank: the fall, times the length in bars (at most one bar)."""
    raw = H.raw
    ua, uz = int(math.ceil(a * 2 - 1e-9)), int(math.floor(z * 2 + 1e-9))
    body = [u for u in range(ua, uz + 1) if u in raw]
    d = lambda u: max(raw[u])
    hits = [d(u) for u in body if d(u) >= KICK]
    if len(hits) < 8:
        return [], None, None
    R = float(np.median(hits))
    v = lambda u: min(1.0, d(u) / R)
    typ = sum(v(u) for u in body) / len(body)
    out = []
    u = ua
    while u <= uz:
        if u not in raw or v(u) >= THIN_WEAK:
            u += 1
            continue
        e = u
        while e + 1 in raw and v(e + 1) < THIN_WEAK:
            e += 1
        n = e - u + 1
        run_u, u = u, e + 1
        if n < THIN_MIN or e + 1 > uz:
            continue
        lv = sum(v(x) for x in range(run_u, e + 1)) / n
        pre = [v(x) for x in range(run_u - 4, run_u) if x in raw]
        lands = [x / 2.0 for x in range(e + 1, e + 2 + int(THIN_NEXT * 2)) if x in H.low and H.score(x) >= STRONG]
        if len(pre) < 2 or not lands or lv > THIN_REL * typ:
            continue
        before = sum(pre) / len(pre)
        if before - lv < THIN_FALL:
            continue
        out.append(dict(a=run_u / 2.0, e=(e + 1) / 2.0, n=n, level=lv, pct=100.0 * lv / typ, before=before, fall=before - lv,
                        rank=(before - lv) * min(n, 8) / 8.0, lands=lands))
    out.sort(key=lambda s: -s["rank"])
    return out, R, typ


def auto_bullets(takes, ib, D, H):
    """The thin-outs of the body as bullet-time candidates. -> (cands, note): cands = [dict(ki (index in the plan's kills of the kill that
    becomes the bullet), j (its take), h (the strong hit it lands on), s (the stretch), why)] best first; note says why there is none."""
    n = len(takes)
    last = takes[-1]
    a = takes[ib].end if ib is not None else max(D, takes[0].first) + 0.5
    z = last.start
    stretches, R, typ = thin_outs(H, a, z)
    where = "beats %s .. %s" % (fnum(a, 1), fnum(z, 1))
    if R is None:
        return [], "bullet time (auto): too few hits in %s to say where the drums thin out" % where
    if not stretches:
        return [], ("bullet time (auto): the drums do not thin out in %s (no stretch of %g beats or more with every half beat under %d %% of a typical hit "
                    "[median hit %.2f], at %d %% of the section or less, after a louder passage and before a strong hit): no mid bullet time" % (
                        where, THIN_MIN / 2.0, round(THIN_WEAK * 100), R, round(THIN_REL * 100)))
    free = [j for j in range((ib if ib is not None else -1) + 1, n - 1) if takes[j].kind == "K" and takes[j].lkind is None and takes[j].at[0] is None]
    cands, why_not = [], []
    for s in stretches:
        for h in s["lands"]:
            if h > last.first - AUTO_ROOM:
                why_not.append("the strong hit at beat %s is too near the last take (beat %s)" % (fnum(h), fnum(last.first)))
                continue
            js = [j for j in free if s["e"] - 0.5 <= takes[j].first <= h + AUTO_SHIFT]
            if not js:
                why_not.append("no single-kill take lands between beat %s and %s" % (fnum(s["e"] - 0.5, 1), fnum(h + AUTO_SHIFT, 1)))
                continue
            j = min(js, key=lambda x: takes[x].first)
            cands.append(dict(ki=takes[j].kills[0]["i"], j=j, h=h, s=s, why=(
                "the drums thin out over beats %s .. %s (drums at %d %% of the section's typical level, after 2 beats at %d %% of a typical hit), into the kill on the %s at beat %s" % (
                    fnum(s["a"]), fnum(s["e"]), round(s["pct"]), round(100 * s["before"]), H.describe(int(round(h * 2))).split()[0], fnum(h)))))
    if not cands:
        s = stretches[0]
        return [], ("bullet time (auto): the drums thin out over beats %s .. %s (drums at %d %% of the section) but no bullet time fits there: %s" % (
            fnum(s["a"]), fnum(s["e"]), round(s["pct"]), "; ".join(dict.fromkeys(why_not))))
    return cands, None


def spaced(cands, per):
    """the best candidates at least THIN_PER_S seconds apart (the list is ranked: a greedy pick)"""
    out = []
    for c in cands:
        if all(abs(c["h"] - o["h"]) * per >= THIN_PER_S for o in out):
            out.append(c)
    return out


# ------------------------------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("plan")
    ap.add_argument("-o", "--out", default="timeline.py")
    ap.add_argument("--force", action="store_true", help="overwrite -o even if it holds your own edits")
    ap.add_argument("--example", default="timeline_ref_example.py", help="the template with the draft markers")
    ap.add_argument("--compare", default=None, help="another timeline .py to print statistics for (e.g. the model edit's)")
    args = ap.parse_args()
    P, kills = load_plan(args.plan)
    draft(args, P, kills, P["auto_bullet"])


def draft(args, P, kills, find):
    """One draft of the plan. find: look for a drum thin-out and, when the plan has no "hit" bullet, draft again with a bullet time into it."""
    if not os.path.isfile(args.example):
        die("%s not found: run this from the project folder (scripts/*.* and scripts/refstyle/*.* copied into it)" % args.example)
    tpl = open(args.example, encoding="utf-8").read()
    if "# >>> draft:entries" not in tpl or "# >>> draft:fx" not in tpl:
        die("%s has no draft markers (or no draft:fx block): take scripts/refstyle/*.* again" % args.example)
    if os.path.exists(args.out) and not args.force:
        cur = open(args.out, encoding="utf-8").read()
        if cur != tpl and not untouched_draft(cur):
            die("%s exists and is neither the untouched example nor an untouched draft (it holds your edits): pick another name with -o, "
                "or --force to replace it" % args.out, "will not overwrite your timeline")
    T = Tempo(P["bpm"], P["max_speed"], P["lead_frames"])
    F, per = T.F, T.per
    bass = P["cuts_on"] == "bass"
    intro_beats, intro_shots, intro_kills, intro_words = load_intro(P)
    takes, join_notes = group_takes(P, kills, T)
    n = len(takes)
    ib = next((j for j, t in enumerate(takes) if t.lkind == "drop"), None)
    if takes[0].lkind == "hit":
        die('the first kill cannot be a "hit" bullet (its lead-in needs a take before it): put "bullet": "hit" on a later kill, or "bullet": true on the first')
    # ---- the numbering: M0 and the drop
    if ib == 0:
        M0 = P["drop_beat"]
        if P["start_beat"] not in (None, P["drop_beat"]):
            join_notes.append("the bullet-time kill comes first, so it lands on the drop and M0 = drop_beat (start_beat ignored)")
    else:
        M0 = P["start_beat"] if P["start_beat"] is not None else P["drop_beat"]
    D = P["drop_beat"] - M0
    if D < 0:
        die("start_beat %d is after the drop (track beat %d)" % (M0, P["drop_beat"]))
    if ib not in (None, 0) and D < BULLET[0] + 0.5:
        die("the bullet-time kill is take %d but the drop is only %d beats after the first kill: its %g-beat lead-in needs the drop at least "
            "%g beats after the first take; set start_beat earlier or put the bullet kill first" % (ib + 1, D, BULLET[0], BULLET[0] + 1))
    set_helpers(tpl, P, T, M0, D)
    bt = lambda r: P["beat0"] + (M0 + r) * per
    m = beat_hits.decode(P["music"])
    dur = len(m) / beat_hits.SR
    rmax = math.floor(((dur - P["beat0"]) / per - M0 - 0.1) * 10) / 10
    vhi = P["max_speed"] if P["max_speed"] is not None else VHI_OLD
    # ---- an M take whose later kill has no hit at or after its real-time distance cannot be one take: it is split (a cut), never fast-forwarded
    takes, split_notes = split_unplaceable(takes, P, T, Hits(beat_hits.measure(m, P["bpm"], P["beat0"], M0, 0.0, min(rmax, P["length"] / per * (1 + P["length_tolerance"])))),
                                           D, bass)
    join_notes += split_notes
    n = len(takes)
    ib = next((j for j, t in enumerate(takes) if t.lkind == "drop"), None)
    E = []
    # ---- footage before every take's first kill and the plan's own spacing
    for j, tk in enumerate(takes):
        if tk.kind != "L":
            lead = T.pre_src(T.lead_frames, tk.pre_n)
            if tk.Ks[0] - lead < MARGIN:
                E.append("take %d (%s K=%d, a clip of %d frames = %.1f s) has only %d frames of footage before its first kill: the take enters at "
                         "real time, so it starts %.1f source frames before the shot and the shutter needs %d more; use a kill with at least %d "
                         "frames before it (or the take cannot start)" % (j + 1, tk.clip, tk.Ks[0], tk.n, tk.n / 60, tk.Ks[0], lead, MARGIN, int(math.ceil(lead)) + MARGIN))
        for a, b in zip(tk.Ks, tk.Ks[1:]):
            if (b - a) / F / VLO > 40:
                E.append("take %d: kills at frames %d and %d of %s are %.1f beats apart in real time: too far for one take (%g to %gx), "
                         "give the second its own take" % (j + 1, a, b, tk.clip, (b - a) / F, VLO, vhi))
    for j, tk in enumerate(takes):
        if tk.lkind and tk.Ks[0] < 8:
            E.append("the bullet-time kill (%s K=%d) has too little footage before it" % (tk.clip, tk.Ks[0]))
    if E:
        die(E)

    # ---- intro layout
    has_intro = bool(intro_shots or intro_kills)
    if intro_words and not intro_shots:
        die('the intro words show over intro shots: add "shots" to "intro" (clip, a, b), or take the words out')
    L_t = P["length"] / per
    if has_intro and intro_beats is None:
        intro_beats = float(min(16, max(4, int(round(L_t * 0.2 / 2.0) * 2))))
        if intro_kills:
            need = len(intro_kills) * (INTRO_LEAD_MIN + (max(k["upto"] for k in intro_kills) + 4) / F + 0.4) + 4.0
            intro_beats = float(max(intro_beats, 2 * math.ceil(need / 2.0)))
    I = float(intro_beats) if has_intro else 0.0
    tol = P["length_tolerance"]
    hint = P["hint"]
    notes = list(join_notes)
    if intro_beats is not None and not has_intro:
        notes.append('"intro" has no shots or kills: the video starts on its first take')
    # R0: the intro lasts I beats before the first landing (the first take's first kill, or the start of the drop bullet's lead-in); without an
    # intro the video starts on the first take
    r0_for = lambda head0, t_first: round(head0 - I, 4) if has_intro else round(t_first, 4)

    def plan_with(rows, R1_lo, R1_hi, raw=None):
        H = Hits(rows, raw)
        S = Solver(P, T, takes, H, D, bass, hint)
        S.R1_lo, S.R1_hi = R1_lo, R1_hi
        cands = []
        if ib == 0:
            if bass and has_intro:                 # the cut into the bullet take is a transition: it needs a kick
                cands = [u for u in H.kicks if BULLET[0] <= D - u / 2.0 <= BULLET[1]]
                cands.sort(key=lambda u: abs((D - u / 2.0) - BULLET[2]))
            else:
                cands = [int(round((D - BULLET[2]) * 2))]
            cands = [u for u in cands if S.pre_ok(takes[0], u / 2.0, float(D))]
        else:
            cands = [0]
        return H, S, cands

    def run(rows, R1_lo, R1_hi):
        H, S, cands = plan_with(rows, R1_lo, R1_hi)
        why = []
        if not cands:
            if ib == 0:
                why.append("the bullet-time kill comes first and needs a lead-in of %g to %g beats ending on the drop (beat 0), %s" % (
                    BULLET[0], BULLET[1], ("and with an intro its start has to be a kick (CUTS_ON \"bass\"); the song has none in beats %g .. %g: "
                                           "drop the intro, use \"cuts_on\": \"kills\", or start_beat earlier so that kills come first" % (-BULLET[1], -BULLET[0]))
                    if bass and has_intro else "but the clip %s has too little footage before frame %d" % (takes[0].clip, takes[0].Ks[0])))
            return None, why
        best = None
        for u0 in cands:
            if ib != 0:
                if not H.can_kill(0):
                    return None, ["the first kill lands on beat 0 (track beat %d) but the song has no kick, snare or loud hat there: %s. Check BPM / BEAT0 with "
                                  "music_grid.py, or pick another start_beat (a kick)" % (M0, H.describe(0))]
            s0 = S.start_of(0, u0, -1e9)
            if s0 is None:
                return None, ["the first kill at beat %s needs a cut before it: with CUTS_ON \"bass\" a kick at least %g frames (%.2f beat) earlier, and the song has none "
                              "there. Pick start_beat so that a kick precedes the first hit, or use \"cuts_on\": \"kills\"" % (fnum(u0 / 2.0 if ib != 0 else 0.0, 1), T.lead_frames, T.lead_b)]
            head0 = u0 / 2.0 if ib == 0 else 0.0
            S.R1_t = r0_for(head0, s0) + L_t
            res, reason = S.solve(u0)
            if res is None:
                why.append(reason)
                fail_j.append(S.fail_j if S.fail_j is not None else 0)
                continue
            if best is None or res[0] < best[0][0]:
                best = (res, u0, r0_for(head0, s0))
        return (best, why) if best else (None, why)

    # first pass: the window the longest allowed R1 gives
    head_g = 0.0 if ib != 0 else D - BULLET[2]
    R0_guess = r0_for(head_g, -T.lead_b if ib != 0 else head_g)
    R1_lo, R1_hi = R0_guess + L_t * (1 - tol), min(R0_guess + L_t * (1 + tol), rmax)
    if bt(R0_guess) < 0.0:
        die("the first kill at track beat %d is too early for a %g-beat intro: the video would start %.2f s before the song (a later start_beat, "
            "or a shorter intro)" % (M0, I, -bt(R0_guess)))
    if R1_hi < R1_lo - 1e-9:
        die("track beat %d is at %.1f s of a %.1f s song, which leaves %.1f s (the first take's intro included) but the edit needs %.0f s +-%d%%: "
            "choose an earlier start_beat / drop_beat, or a shorter length" % (M0, bt(0), dur, max(0.0, dur - bt(R0_guess)), P["length"], round(tol * 100)))

    def probe():
        """lowest / highest R1 the takes can reach whatever length was asked (seconds), or None"""
        wide = min(rmax, R0_guess + L_t * 2.5)
        H2, S2, cands = plan_with(beat_hits.measure(m, P["bpm"], P["beat0"], M0, R0_guess, wide), -1e9, wide)
        S2.explore = True
        spans = [r for r in (S2.solve(u0)[0] for u0 in cands) if r]
        if not spans:
            return None
        return (min(s[0] for s in spans) - R0_guess) * per, (max(s[1] for s in spans) - R0_guess) * per

    R0_init = R0_guess
    fail_j = []                                  # index of the take that no cut could follow (Solver.solve), for the M splits below
    while True:
        window, chosen, fixed, R0_guess = R1_hi, None, None, R0_init
        for attempt in range(5):
            rows = beat_hits.measure(m, P["bpm"], P["beat0"], M0, R0_guess, window)
            fail_j.clear()
            best, why = run(rows, fixed if fixed else R1_lo, fixed if fixed else R1_hi)
            if best is None:
                break
            (res, u0, R0) = best
            cost, chain, R1, t_first = res
            if abs(R1 - window) < 1e-9 and abs(R0 - R0_guess) < 1e-9:
                chosen = (rows, chain, R1, R0, t_first)
                break
            R0_guess, window, fixed = R0, R1, R1
        if chosen is not None:
            break
        if best is None:
            # no placement: a take that plays two kills at their real-time distance or more can be what blocks it (a long take, a kill with no hit
            # near): split the M take nearest to where it failed, the later kill gets a cut of its own, and plan again. Never a fast-forward.
            fj = fail_j[0] if fail_j else 0
            ms = [x for x in sorted(range(n), key=lambda x: (abs(x - (fj - 1)), x)) if takes[x].kind == "M"]
            if ms:
                x = ms[0]
                tk = takes[x]
                a, b = tk.kills[-2], tk.kills[-1]
                notes.append("kills #%d and #%d (%s %d, %d) are %.2f beats apart at real time: kept in one take the later kill must land on a hit at least that "
                             "long after the first, and no placement of the whole edit allows it, so they are two takes (the later one cut in a lead before its kill)" % (
                                 a["i"] + 1, b["i"] + 1, a["clip"], a["K"], b["K"], (b["K"] - a["K"]) / F))
                takes = takes[:x] + [Take(tk.kills[:-1]), Take(tk.kills[-1:])] + takes[x + 1:]
                n = len(takes)
                ib = next((j for j, t in enumerate(takes) if t.lkind == "drop"), None)
                continue
            report_fail(P, T, takes, Hits(rows), ib, bass, why, tol, probe, R1_hi)
        die("the measured hits changed between passes; run again with a slightly different length")
    rows, chain, R1, R0, t_first = chosen
    raw_rows = beat_hits.measure(m, P["bpm"], P["beat0"], M0, R0, R1, raw=True)
    H = Hits(rows, raw_rows)

    # ---- placement -> entries
    for j, tk in enumerate(takes):
        c = chain[j]
        tk.head = c["u"] / 2.0
        tk.first = float(D) if tk.lkind == "drop" else tk.head          # the take's first kill
        tk.tails = list(c["tails"])
        tk.last = c["last"]
        tk.start = c["start"]
    for j, tk in enumerate(takes):
        tk.end = takes[j + 1].start if j + 1 < n else R1
    best_snare = assign_levels(takes, H, ib, n)

    # ---- where the drums thin out: a bullet time into the next strong hit (model-edit.md), unless the plan says otherwise
    if find:
        cands, anote = auto_bullets(takes, ib, D, H)
        own = [tk for tk in takes if tk.lkind == "hit"]
        if own:
            far = [c for c in cands if all(abs(tk.first - c["h"]) > 4.0 for tk in own)]
            if far:
                notes.append('bullet time (auto): %s; the plan has its own "hit" bullet (beat %s), so none was added' % (far[0]["why"], ", ".join(fnum(tk.first) for tk in own)))
        elif cands:
            queue, failed = list(cands), []
            for _ in range(AUTO_TRIES):
                picks = spaced(queue, per)
                if not picks:
                    break
                kills2 = [dict(k) for k in kills]
                for c in picks:
                    next(k for k in kills2 if k["i"] == c["ki"]).update(bullet=True, lkind="hit", at=c["h"], auto_why=c["why"])
                try:
                    return draft(args, P, kills2, False)
                except SystemExit as e:
                    why = [l.strip()[2:] for l in str(e.code).splitlines() if l.strip().startswith("- ")]
                    failed.append("%s: %s" % (picks[0]["why"], (why[0] if why else str(e.code))[:300]))
                    queue = [c for c in queue if c is not picks[0]]
            notes.append("bullet time (auto): not added, the draft cannot hold it. " + " | ".join(failed))
        else:
            notes.append(anote)

    # ---- intro entries
    t1 = takes[0].start
    intro = []
    if intro_shots:
        nsh = len(intro_shots)
        starts = [R0]
        if nsh > 1:
            ideal = [R0 + j * (t1 - R0) / nsh for j in range(1, nsh)]
            for x in ideal:
                if bass:
                    ks = [u / 2.0 for u in H.kicks if R0 + 1.5 <= u / 2.0 <= t1 - 1.5 and u / 2.0 > starts[-1] + 1.5]
                    if ks:
                        starts.append(min(ks, key=lambda b: abs(b - x)))
                else:
                    starts.append(round(x * 2) / 2.0)
        used = intro_shots[:len(starts)]
        if len(used) < nsh:
            notes.append("intro: %d of %d shots used: with CUTS_ON \"bass\" every cut sits on a kick and the song has none in beats %s .. %s, so the intro is %s" % (
                len(used), nsh, fnum(R0, 1), fnum(t1, 1), "one long shot" if len(used) == 1 else "%d shots" % len(used)))
        for j, sh in enumerate(used):
            s0 = starts[j]
            s1 = starts[j + 1] if j + 1 < len(starts) else t1
            a, b = sh["a"], sh["b"]
            v = (b - a) / ((s1 - s0) * F)
            if not 0.1 <= v <= 0.8:
                b2 = int(round(a + 0.24 * (s1 - s0) * F))
                if b2 > sh["n"] - 1 - MARGIN:
                    die("intro shot %s %d..%d plays at %.2fx over its %.1f beats (slow motion should be 0.1 to 0.8x) and the clip ends at frame %d, so the range cannot be "
                        "stretched to %d: give a shot with more footage after it, a shorter intro (\"beats\"), or more shots" % (
                            sh["clip"], a, b, v, s1 - s0, sh["n"] - 1, b2))
                notes.append("intro shot %s: range %d..%d would play at %.2fx over %.1f beats; extended to %d..%d (0.24x)" % (sh["clip"], a, b, v, s1 - s0, a, b2))
                b = b2
            intro.append(dict(kind="shot", clip=sh["clip"], start=s0, a=a, b=b, shutter=SHUTTER[j % len(SHUTTER)], v=(b - a) / ((s1 - s0) * F)))
    elif intro_kills:
        for ik in layout_intro_kills(intro_kills, H, R0, t1, bass, T):
            v_use, lead = None, None
            for v in INTRO_V:
                lead = T.lead(ik["start"], ik["kill"], ik["K"], (v,), ())
                if lead[0][1] >= MARGIN:
                    v_use = v
                    break
            if v_use is None:
                die("intro kill %s K=%d: its %.1f-beat lead-in at %.2fx asks for %.0f frames before the shot and the clip has %d: use a kill later in its clip, "
                    "a shorter intro stretch, or more intro kills" % (ik["clip"], ik["K"], ik["kill"] - ik["start"], INTRO_V[-1], ik["K"] - lead[0][1] + 0.0, ik["K"]))
            intro.append(dict(ik, kind="ikill", v=v_use, lead=lead))

    # ---- entries
    ent = []                              # each: dict(kind, ...)
    for sh in intro:
        ent.append(sh)
    for j, tk in enumerate(takes):
        ent.append(dict(kind="take", j=j, tk=tk))
    tins = assign_tins(ent, takes)
    lines = []
    SV = Solver(P, T, takes, H, D, bass, hint)
    risers, booms = [], []
    for i, e in enumerate(ent):
        tin = tins[i]
        if e["kind"] == "shot":
            o = [("shutter", fnum(e["shutter"], 1)), ("tin", tin_text(tin)), ("intro", "True"), ("mute", "True"), ("push", "0.0")]
            nxt_start = ent[i + 1]["start"] if ent[i + 1]["kind"] in ("shot", "ikill") else t1
            lines.append("    # intro shot: %.2fx slow motion over %.1f beats at full frame" % (e["v"], nxt_start - e["start"]))
            lines.append('    ("shot", %s, "%s", %d, %d, %s),' % (fnum(e["start"], 3, True), e["clip"], e["a"], e["b"], opts_text(o)))
            continue
        if e["kind"] == "ikill":
            o = [("intro", "True"), ("push", "0.0"), ("shutter", "2.2"), ("tin", tin_text(tin)), ("upto", str(e["upto"])), ("h", str(INTRO_H))]
            lines.append("    # intro kill: bullet time at %.2fx over %.1f beats (%s) into the kill on beat %s (%s), then its death (upto %d frames)" % (
                e["v"], e["kill"] - e["start"], "from the opening" if i == 0 else "after the take before", fnum(e["kill"]), H.describe(int(round(e["kill"] * 2))), e["upto"]))
            lines.append('    ("L", %s, [%s], %s, "%s", %d, %s),' % (
                fnum(e["start"], 3, True), ", ".join("(%s)" % ", ".join([fnum(a[0], 3), fnum(a[1], 1)] + [fnum(x, 2) for x in a[2:]]) for a in e["lead"]),
                fnum(e["kill"], 3, True), e["clip"], e["K"], opts_text(o)))
            continue
        tk, j = e["tk"], e["j"]
        final = j == n - 1
        Lt = tk.end - tk.start
        lb = tk.first - tk.start
        o = []
        if tk.lv != 1:
            o.append(("lv", str(tk.lv)))
        if tk.kind == "M":
            default = [1] * (len(tk.Ks) - 1) + [tk.lv]
            lvs = [tk.lv if tk.first_after_drop and tk.lv == 2 else 1] * (len(tk.Ks) - 1) + [tk.lv]
            if lvs != default:
                o.append(("lvs", "(%s)" % ", ".join(str(x) for x in lvs)))
        if tk.kind != "L" and ((tk.pre_n is not None) if P["max_speed"] is not None else tk.pre_n != PRE_N and tk.pre_n is not None):
            o.append(("n", str(tk.pre_n)))
        if final:
            o += [("rate", fnum(T.final_rate, 2)), ("slow", "None"), ("push", "0.0"), ("calm", "True")]
        else:
            o.append(("upto", str(tk.upto)))
            if tk.kind == "L":
                o.append(("push", "0.05"))
        if tk.kind != "L" and abs(lb - T.lead_b) > 1e-6:
            o.append(("lb", fnum(lb, 4)))
        if tk.kind == "L":
            o.append(("white", "flash(%s, 0.36, 8.0)" % fnum(tk.start, 3, True)))
        o.append(("tin", tin_text(tin)))
        if tk.mute:
            o.append(("mute", "True"))
        cut_on = H.describe(int(round(tk.first * 2)))
        win = (tk.end - tk.last) * F
        rate = (tk.upto - 8.0) / max(1.0, win - 8.0)
        tail = ("last take, calm; slow motion to the luma fade; " if final else
                ("death upto %d frames in %.0f: slow %.2fx; " % (tk.upto, win, rate) if rate >= 0.15 else
                 "death upto %d frames in %.0f: slow 0.15x until the body is down, then back to real time; " % (tk.upto, win)) if win > tk.upto
                else "death upto %d in %.0f frames: real time; " % (tk.upto, win))
        if tk.kind == "L":
            ld = SV.lead_anchors(tk, tk.start, tk.first)
            if tk.lkind == "drop":
                expl = ("bullet time into the kill on the drop (beat %s, %s): lead-in from beat %s (%s), %.1f beats at 0.5x .. 0.2x, a white flash-in, %s; %s%.1f beats long" % (
                    fnum(D), H.describe(2 * D), fnum(tk.start), "on a kick" if H.kick(int(round(tk.start * 2))) else "any beat: no kick needed", D - tk.start,
                    "an 8-frame ease up to real time, the shot at real time" if P["max_speed"] is not None else "then the shot at real time", tail, Lt))
                risers.append(("drop", max(tk.start, R0 + 0.2), tk.first))
                booms.append((tk.first, 0.26))
            else:
                auto = tk.kills[0].get("auto_why")
                expl = ("%s (%s): %.1f beats of lead-in at 0.5x .. 0.4x from beat %s, a white flash-in, a riser, a boom; %s%.1f beats long" % (
                    "bullet time (auto): " + auto if auto else "bullet time into the kill on the strong hit at beat %s" % fnum(tk.first), cut_on, tk.first - tk.start, fnum(tk.start), tail, Lt))
                risers.append(("hit", tk.start, tk.first))
                booms.append((tk.first, 0.20))
                nk = sum(1 for x in H.kicks if tk.start <= x / 2.0 < tk.first)
                if auto:
                    notes.append("take %d: bullet time added by itself, %s (\"auto_bullet\": false in the plan turns it off; %d kick(s) inside its %.1f-beat lead-in)" % (
                        j + 1, auto, nk, tk.first - tk.start))
                elif nk >= 3:
                    notes.append("take %d (bullet \"hit\" at beat %s): the drums do not thin out here (%d kicks inside its %.1f-beat lead-in); the model puts this where the "
                                 "kick and snare weaken" % (j + 1, fnum(tk.first), nk, tk.first - tk.start))
            lines.append("    # take %d: %s" % (j + 1, expl))
            lines.append('    ("L", %s, [%s], %s, "%s", %d, %s),' % (
                fnum(tk.start, 3, True), ", ".join("(%s)" % ", ".join([fnum(a[0], 3), fnum(a[1], 1)] + [fnum(x, 2) for x in a[2:]]) for a in ld), fnum(tk.first, 3, True), tk.clip, tk.Ks[0], opts_text(o)))
        elif tk.kind == "K":
            lines.append("    # take %d: cut %g frames (%s beat) before beat %s (%s)%s; %s%.1f beats long" % (
                j + 1, round(lb * F, 1), fnum(lb, 3), fnum(tk.first), cut_on, " (best snare: level 3)" if j == best_snare else "", tail, Lt))
            lines.append('    ("K", %s, "%s", %d, %s),' % (fnum(tk.first, 3, True), tk.clip, tk.Ks[0], opts_text(o)))
        else:
            bs = [tk.first] + tk.tails
            lines.append("    # take %d: cut %g frames (%s beat) before beat %s (%s); kills on %s; %s%.1f beats long" % (
                j + 1, round(lb * F, 1), fnum(lb, 3), fnum(tk.first), cut_on, ", ".join("%s (%s)" % (fnum(b), H.describe(int(round(b * 2)))) for b in bs[1:]), tail, Lt))
            lines.append('    ("M", [%s], "%s", %s),' % (", ".join("(%s, %d)" % (fnum(b, 3, True), K) for b, K in zip(bs, tk.Ks)), tk.clip, opts_text(o)))
        if j == best_snare:
            booms.append((tk.last, 0.18))
        if final:
            booms.append((tk.last, 0.26))
    entries_txt = "E = [\n" + "\n".join(lines) + "\n]\n"

    # ---- music block, sound, effects, words
    bpm_txt = "%.1f" % P["bpm"] if float(P["bpm"]) == int(P["bpm"]) else fnum(float(P["bpm"]))
    music_blk = music_block(P, bpm_txt, M0, D, F, R0, R1, takes[-1].last)
    music_blk += "LOOK = %r                          # edit options (SKILL.md, \"Edit options\"; look.py): the model edit's look\n" % (P["look"],)
    rs = []
    if ib != 0 and I >= 4.5:
        rs.append("dict(a=%s, b=0.0, f0=350, f1=7000, curve=1.0, width=1.1, power=2.3, gain=0.10, cut=0.012, seed=1)" % fnum(max(-4.0, R0 + 0.2), 4, True))
    for kind, a, b in risers:
        if kind == "drop":
            rs.append("dict(a=%s, b=%s, f0=350, f1=7500, curve=1.1, width=1.1, power=2.2, gain=0.09, cut=0.012, seed=1)" % (fnum(a, 4, True), fnum(b, 4, True)))
        else:
            rs.append("dict(a=%s, b=%s, f0=300, f1=7000, curve=1.2, width=1.0, power=2.3, gain=0.08, cut=0.012, seed=3)" % (fnum(a, 4, True), fnum(b, 4, True)))
    sound_blk = "SWEEP = None\nRISERS = [%s]\n" % (",\n          ".join(rs))
    kill_beats = [k for tk in takes for k in [tk.first] + tk.tails]
    luma0 = R1 - (BLACK_S + LUMA_S) / per
    bumps = pick_bumps(H, kill_beats, R0, luma0, takes[-1].start, (R1 - R0) * per)
    fx = ["IMPACT = dict(frames=6, blur=(0.035, 0.06, 0.09), split=(5, 9, 14), rays=(False, True, True), invert=(False, False, True))",
          "ACC = {1: (0.020, 4.0, 0.32), 2: (0.032, 7.0, 0.50), 3: (0.045, 10.0, 0.85)}   # kill accents per level: punch / shake px / exposure pop"]
    bl = ["(%s, %s)" % (fnum(b, 3, True), fnum(s, 2, True)) for b, s in bumps]
    fx.append("BUMPS = [%s]      # a light pulse and a 1.2 %% nudge on the strong hits that carry no kill (%d)" % (",\n         ".join(", ".join(bl[x:x + 4]) for x in range(0, len(bl), 4)), len(bumps)))
    if has_intro:
        fx.append("LUMA_IN = (%s, %s)             # the opening reveals the bright areas first" % (fnum(R0, 4, True), fnum(R0 + 0.35, 4, True)))
    fx.append("BOOMS = [%s]" % ", ".join("dict(r=%s, gain=%s)" % (fnum(b, 4, True), fnum(g, 2, True)) for b, g in sorted(booms)))
    fx += ["KILL_THUMP = 0.18                   # a sub thump under every kill", "WHOOSH_BLUR = 0.07                  # a swish on every blur-in cut",
           "GAME_LEVEL = 0.95                   # the gunshots: a little louder than the house mix", "HEADROOM = 0.5                      # mix.wav level (gunshots, thumps and booms are hot)",
           "FADE_IN = 0.45                      # seconds of fade-in of the song"]
    fx_blk = "\n".join(fx) + "\n"
    words_blk = ""
    if intro_words:
        W0, W1 = R0 + 1.0, (t1 - 1.0)
        need = 2.0 * len(intro_words)
        if W1 - W0 < need - 1e-9:
            die("the intro (beats %s .. %s) has room for %d word(s) of 2 beats, the plan has %d: a longer intro (\"beats\") or fewer words" % (
                fnum(R0, 1), fnum(t1, 1), int((W1 - W0) // 2), len(intro_words)))
        wl = min(3.0, (W1 - W0) / len(intro_words) - 0.3) if len(intro_words) > 1 else min(3.0, W1 - W0)
        wl = max(2.0, wl)
        cues = []
        for j, w in enumerate(intro_words):
            a0 = W0 + (j * (W1 - W0 - wl) / (len(intro_words) - 1) if len(intro_words) > 1 else 0.0)
            a0 = round(a0 * 2) / 2.0
            if a0 > -1.6:
                die("intro word %r would start at beat %s: words starting after beat -1.5 are capped at 1.1 beats by the timeline. A longer intro, or fewer words" % (w, fnum(a0, 1)))
            cues.append('(%s, %s, "%s", "red")' % (fnum(a0, 2, True), fnum(a0 + wl, 2, True), w))
        words_blk = "_T = [" + ", ".join(cues) + "]\n"
    else:
        words_blk = "_T = []\n"

    doc = ('"""The edit, expressed in beats of the music: drafted by draft_ref_timeline.py (plan %s, %d kills, %.0f s, CUTS_ON "%s"), to be read\n'
           "and tweaked, not trusted blindly. Reference style with the model edit's patterns: every take cut %g frames before its first shot, real time to the\n"
           "shot, the death shown in slow motion before the next cut, bullet time into the drop, a luma fade at the end. Timeline beat 0 = beat %d of the track.\n"
           'Source positions are frame indices of the clips (exact, 60 per second)."""') % (
        hashlib.sha1(open(args.plan, "rb").read()).hexdigest()[:8], len(kills) + len(intro_kills), (R1 - R0) * per, P["cuts_on"], P["lead_frames"], M0)
    src = re.sub(r'\A""".*?"""', lambda mm: doc, tpl, count=1, flags=re.S)
    for name, blk in (("music", music_blk), ("sound", sound_blk), ("fx", fx_blk), ("cut", cut_block(P)), ("post", POST_BLK), ("entries", entries_txt), ("words", words_blk)):
        src = replace_block(src, name, blk)

    # ---- run the built file before writing it
    ns = exec_timeline(src)
    pins = {float(a) for tk in takes for a in tk.at if a is not None}
    errs, warns = verify(ns, H, P["cuts_on"], float(P["lead_frames"]), pins)
    if errs:
        die(errs, "built a draft that fails its own check (a bug, or inputs it cannot handle)")
    open(args.out, "w", encoding="utf-8", newline="\n").write(src + SUM + hashlib.sha1(src.encode("utf-8")).hexdigest() + "\n")

    nodeath = [k["i"] + 1 for k in kills if not k["upto_given"]]
    nodeath_i = [j + 1 for j, k in enumerate(intro_kills) if not k["upto_given"]]
    if nodeath or nodeath_i:
        notes.append("%d kill(s) have no \"upto\" (kills %s%s): %d frames assumed from the shot until the body is down; measure it with `$PY deathstrip.py ds.jpg c01@K ...` "
                     "(the tiles show the body falling) and write it in the plan: a wrong value cuts a death short or holds a corpse" % (
                         len(nodeath) + len(nodeath_i), ", ".join("#%d" % x for x in nodeath[:12]) + (" ..." if len(nodeath) > 12 else ""),
                         ("; intro kills " + ", ".join("#%d" % x for x in nodeath_i)) if nodeath_i else "", UPTO_DEFAULT))
    print("music: %s  %s BPM  BEAT0 %s  first landing at track beat %d = M0 (drop at track beat %d = beat %s); R0 %s, R1 %s = %.1f s (asked %.0f s); CUTS_ON = %r, FRAME = %r, lead %g frames" % (
        P["music"], bpm_txt, fnum(P["beat0"]), M0, P["drop_beat"], fnum(D), fnum(R0, 2), fnum(R1, 2), (R1 - R0) * per, P["length"], P["cuts_on"], P["frame"], P["lead_frames"]))
    print("hits in the window: %d kicks (low >= %.1f), %d half beats that can carry a kill; %d takes for %d kills%s" % (
        len(H.kicks), KICK, len(H.kills), n, len(kills), (", pacing hint %.2f beats" % hint) if hint else ""))
    for l in lines:
        print(l.strip() if l.lstrip().startswith("#") else "    " + l.strip())
    for t in notes:
        print("note:", t)
    for w in warns:
        print("note:", w)
    st = stats(ns, H)
    print("wrote %s: %d takes, %d frames, %.2f s, music from %.3f s" % (args.out, len(ns["SEGS"]), ns["N_FRAMES"], (R1 - R0) * per, ns["MUSIC_T0"]))
    print_stats("draft", st)
    if args.compare and os.path.isfile(args.compare):
        cns = exec_timeline(open(args.compare, encoding="utf-8").read(), "compare")
        ch = None
        if cns["MUSIC"] == P["music"]:
            try:
                ch = Hits(beat_hits.measure(m, cns["BPM"], cns["BEAT0"], cns["M0"], cns["R0"], cns["R1"]))
            except SystemExit:
                pass
        print_stats(os.path.basename(args.compare), stats(cns, ch))
    if hint and np.median(st["lens"]) > 2.0 * hint:
        print("note: the takes run a median %.1f beats against the reference's %.2f: add kills (about %d for %.0f s at the reference's pace) or ask for fewer seconds" % (
            np.median(st["lens"]), hint, int(math.ceil((R1 - R0) / max(hint, 0.5))), P["length"]))
    print("next: $PY timeline.py (must pass), $PY music_pulses.py (none / none), $PY ranges.py, $PY deathstrip.py ds.jpg (every death on a green tile)")


def report_fail(P, T, takes, H, ib, bass, why, tol, probe, R1_hi):
    """Explain with numbers why no placement exists, then stop."""
    n = len(takes)
    msgs = list(dict.fromkeys(why))
    if bass:
        have = [u / 2.0 for u in H.kicks if 0.5 < u / 2.0 <= R1_hi - T.tail[0]]
        if len(have) < n - 1:
            msgs.append("CUTS_ON \"bass\" needs a kick for each of the %d cuts (every take after the first) but beats 0 .. %s hold only %d kicks (low >= %.1f, at %s): "
                        "mark kills of one clip \"with_previous\" (fewer takes), ask for more seconds, start the section earlier, or use \"cuts_on\": \"kills\"" % (
                            n - 1, fnum(R1_hi - T.tail[0], 1), len(have), KICK, " ".join(fnum(b, 1) for b in have[:24]) or "none"))
    span = probe()
    if span:
        lo, hi = span
        msgs.append("these %d takes (%d kills) can make a video of %.1f to %.1f s under the spacing rules (%.0f s asked, +-%d%% allowed): %s" % (
            n, sum(len(t.Ks) for t in takes), lo, hi, P["length"], round(tol * 100),
            ("add kills, or ask for about %.0f s" % hi) if hi < P["length"] * (1 - tol) else ("use fewer kills, or ask for about %.0f s" % lo)))
    die(msgs or ["no placement of the takes satisfies the spacing rules"], "cannot place the kills")


if __name__ == "__main__":
    main()
