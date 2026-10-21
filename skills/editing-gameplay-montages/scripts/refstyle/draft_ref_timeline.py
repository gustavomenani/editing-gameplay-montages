"""Writes a correct first draft of a reference-style timeline.py (the style of timeline_ref_example.py, with the patterns of the
"model edit": model-edit.md) from measured inputs; you then read it, look at the stills and tweak it (reference-style.md). It does the
arithmetic that hand-written timelines get wrong: every take cut about `lead_frames` (14) before its first shot with the footage at real
time up to it, every kill on the MEASURED ATTACK of a drum hit, every cut on a line of the music's subdivision lattice, every picture event on
an exact output frame, bullet time into the drop (and into any kill marked "hit"), the luma fade on a calm last take, the numbering of
the music block, anchors inside the clips, speeds inside sane bounds, the model's accents (levels, blur-ins, bumps, booms, risers, sound
levels, look) and, when a reference video was analysed, every trait of it (ref_analyze.py: ref_notes.json "adopt" block).

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
   "cuts_on": "kills",                 # "kills" (default, the model: the cut sits on a line of the lattice about lead_frames before the kill)
                                       # or "bass": the cut sits on a kick and the take's first kill at least lead_frames after it.
                                       # Absent: the reference's suggestion (ref_notes.json suggested.CUTS_ON), else "kills"
   "lead_frames": 14,                  # optional, 10 .. 20: output frames from the cut to the take's first shot (real time); the SHOWN lead of a
                                       # kills-mode take is within lead_frames +- 2 (12..16), whole frames
   "cut_lead_frames": 1, "hit_lead_frames": 1,   # optional, 0 .. 3: frames a cut / a shot's flash is SHOWN before its musical moment (CUT_LEAD /
                                       # HIT_LEAD of the timeline; the reference's measured convention is 1 .. 2). Absent: the reference's, else 1 / 1
   "hit_grid": 2,                      # optional: 2 (kills on half beats) or 4 (quarter beats: syncopated, swung or 16th hits). Absent: 4 when
                                       # 20 % or more of the song's strong kicks / snares sit on a quarter that is not a half beat, else 2
   "frame": "vertical",                # default (the whole game in a window, TikTok/Reels/Shorts); or "horizontal". Absent: the reference's
   "max_speed": 1.0,                   # default: NOTHING plays faster than real time (the user: "do nada voce coloca o video muito rapido").
                                       # Only when the user asks for velocity / aceleracao: 1.6, or null (the old fast-forward behaviour)
   "length": 30,                       # seconds the user asked for; the draft lands within length_tolerance of it
   "length_tolerance": 0.10,           # optional, default 0.10 (a fraction of length)
   "look": "modelo",                   # optional: LOOK of timeline.py (a preset name or a dict, SKILL.md "Edit options"). Absent: the reference's
   "auto_bullet": true,                # optional, default true: where the drums thin out (a bar or so of weak kick and snare) and no kill is
                                       # marked "bullet": "hit", the draft puts a bullet time into the kill on the next strong hit; false: never
   "intro": {"beats": 12,              # optional intro: bullet-time kills ("kills") or slow ability shots ("shots") at full frame
                                       # (absent "beats": the reference's intro_steps, in whole bars, else a fifth of the video)
             "kills": [{"clip": "c02", "K": 640, "upto": 24}, ...],      # each: a 0.12-0.25x lead-in into this kill, then its death; the kill sits on
                                                                         # a measured attack ("at" + "silent": true pins it on the grid where the intro has no drum)
             "shots": [{"clip": "c22", "a": 6650, "b": 6700}, ...],      # the older form: source frames shown in slow motion
             "words": ["ARTIST", "TITLE"]},                              # red words over the intro (artist, title; only with "shots")
   "ref_notes": "ref_notes.json",      # optional (ref_analyze.py; default: ref_notes.json when it exists in the folder; false: ignore the reference).
                                       # Its "adopt" block drives the edit (see "The reference" below)
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
must land on, a multiple of 0.25, e.g. the last kill on the last sung word; it lands on the measured attack there, and where the music
has no hit it sounds on the pinned beat and the draft says so; intro kills take it too); "mute" (voice chat over it); "n" (source frames in
the blur-in; with max_speed it is a ceiling check, so leave it out); "k_checked": true (see "K" below).

K: a kill whose K is unverified is REFUSED (a frame off is 16.7 ms of desync): there is no kills.json, or no entry for it (looked up by "id", else clip and K,
also the K that kverify.py corrected), or the plan's K differs from the entry's, or its "how" is not "ammo" / "flash" ("ammo-loose", "guess", an old entry with
no "how"), or its "conf" is "low" / "guess". The rule is preflight.k_check, shared with draft_timeline.py. Run `kverify.py plan.json`, fix K from its verdict,
then write "k_checked": true on the plan entry (main and intro kills).

SYNC (the timing contract of timeline.py, SYNC = 2): every musical event is a MEASURED time converted with hit(t) = (t - BEAT0) / PER - M0
(beat_hits.measure_t: the attack of the drum hit, ONE definition for the whole skill) and written with 9 decimals: kills, bumps, booms, riser
ends, bullet kills, intro kills, and a kills-mode cut that falls on a hit. The timeline turns them into frames (vis(): the nearest output
frame, then CUT_LEAD / HIT_LEAD frames earlier for the picture; the sound stays on the exact musical beat), so a take's picture, its cut,
its flash and its sound are on exact frames / exact times. Lines of the song's grid (1/2, 1/4, 1/8 beat) are used only where the music has
no hit: a kills-mode cut between two hits, the start of a bullet time, the ending. The draft keeps a margin of 0.1 frame (the window the
hits were measured in differs a hair from the gate's) and checks the finished module on its SHOWN frames.

What it decides, from the music (beat_hits.py) and the clips' lengths (pts/):
  * every take: the cut's musical moment sits on a line of the subdivision lattice (the reference's step when it has one, else the
    coarsest of 1/2, 1/4, 1/8 beat that fits, 1/16 when none does; the measured attack on that line when there is one, within half a frame) chosen so that
    the SHOWN lead (whole frames from the cut's frame to the first shot's frame) is within lead_frames +- 2, and the footage runs at real
    time up to the shot; after the last shot of the take, real time for 8 frames, an ease, then ONE constant slow rate that lands on
    K + upto exactly at the next cut (a window that would need less than 0.15x slows to 0.15x until the body is down, then eases back to
    real time). The next cut is never before the death is shown (in whole frames): that sets the shortest gap between two kills,
    (lead + upto) / FPB beats;
    "bass": the cut sits on the attack of a kick instead (the kick nearest the lead window first, the first scan starts before the
    first kill so the kick before it exists) and the first kill on the first hit lead_frames or more after it;
  * kills on measured kicks, snares and loud hats (attack times); the speed between two kills of one take is at most max_speed and at least
    0.6x (one frame of margin for the rounding to frames); when no hit sits in that window the two kills become two takes (a cut), never a
    fast-forward;
  * clip lengths: an even spread toward the length asked, 0.5 to 7 beats; with a reference, each take's preferred length is drawn from the
    reference's cut-gap histogram (in lattice steps) and raised to the physical minimum (lead + death), every raise printed;
  * the drop kill ("bullet": true): a 3 to 6 beat lead-in at 0.5x .. 0.2x (preferred 4 beats) with a white flash-in, an 8-frame ease up to
    real time, push-in 5 %, a riser ending on the measured hit, a boom; a "hit" bullet: a 2 to 3 beat lead-in at 0.5x, the same flash, riser
    and boom, starting on a 1/4-beat line;
  * a bullet time where the drums thin out ("auto_bullet", only when no kill is marked "hit"): in the body (after the drop, before the last take) it
    looks for 1.5 beats or more where every half beat of kick / snare / hat falls under 25 % of the section's typical hit (the median hit; at most half
    the section's mean level), after a passage that is at least 0.3 louder and followed within 2 beats by a strong hit. The most pronounced one
    (the fall times its length up to a bar) becomes a "hit" bullet: the kill the draft places nearest after it is moved onto that strong hit
    ("at") and drafted again, at most one per 30 s of video. When it cannot fit, or the drums do not thin out, a note says why;
  * intro kills: each take a slow lead-in (0.12 to 0.25x, shutter 2.2, no push, gunshot heard) into a kill on a measured attack, then its death;
  * levels, blur-ins (zoom burst on level 2 / 3 and bullet takes, whips alternating direction, a roll about every fourth take, the opening
    fades in; with a reference: its shares of hard cuts / whips / zooms / rolls), push-in 3 % (5 % over a bullet time, none in the intro and
    the calm ending), IMPACT / ACC, BUMPS (light pulses on the strong hits that carry no kill, about one per 2.4 s, on their attack times),
    BOOMS (the drop and the last kill 0.26, the strongest snare 0.18, a "hit" bullet 0.20), KILL_THUMP, WHOOSH_BLUR, GAME_LEVEL, HEADROOM,
    RISERS into the drop and into each "hit" bullet, LOOK "modelo" (or the reference's);
  * the last take: calm, slow motion to LUMA_FADE and black after it, the music fading under it (FADE_OUT); R1, LUMA_FADE and FADE_OUT start on
    beat lines;
  * M0 / R0 / R1 / FADE_OUT / LUMA_FADE, intro words. R0 is exact: the first cut is shown on frame 0.

The reference (ref_notes.json "adopt", written by ref_analyze.py; precedence per trait: the plan's keys > the reference > the model edit):
  frame, look, cuts_on, the cut lattice (-> the lines the cuts sit on), cut_lead_frames / hit_lead_frames (-> CUT_LEAD / HIT_LEAD: the reference's
  cut before its beat), cut_gaps_steps (-> each take's preferred length), transitions (-> the shares of hard / whip / zoom / roll),
  slow share and rate (-> fall()'s real-time hold h and FALL_MIN), intro_steps (-> the intro's length in whole bars), ending (-> LUMA_S, BLACK_S),
  kills per second (a warning when the plan's rate is off by more than 25 %), cut rate (printed against the draft's, with the reason the standing
  rules prevent it), words (not applied: the user's size rule wins). The draft prints "reference followed / not followed (why)" for every trait,
  and refuses to write the file when ref_notes.json exists and none of its traits was used (a reference that changes nothing is not followed).

Systematic drift: when the measured attacks of the strong hits drift against the grid (more than 8 ms over the section, a significant slope:
the BPM is wrong) it refuses, with the fitted slope and the better BPM (music_grid.py).

It refuses, with the numbers, when the plan cannot fit: a hit missing on the drop or on the first kill, too few kicks for the takes,
a clip without enough footage before or after a kill, kills too close for a lead and a death, a length that the kills cannot fill.
The file is built from timeline_ref_example.py by replacing the blocks between its `# >>> draft:...` / `# <<< draft:...` markers.
Before writing it runs the built file: the preflight (SYNC 2, grid identities, exact frames, clips, anchors, music, MAX_SPEED: every frame at
most max_speed), the lead of every take in shown frames, every death shown, every kill on a measured attack, every cut on its lattice line /
a kick, speeds, and the frames each take asks of its clip (ranges.py)."""
import argparse, bisect, collections, hashlib, json, math, os, random, re, sys, types
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
TAIL_PIC, TAIL_DIFF = 1.22, (-0.34, 0.46)   # last take after its last kill: the ace's picture (the model: 1.22 s), then the fade and the black;
                                            # (min, max) = preferred + TAIL_DIFF; the model: 1.22 + 0.27 + 1.35 = 2.84 s, 2.5 .. 3.3 s
LUMA_S, BLACK_S = 0.27, 1.35        # seconds of the luma fade and of black after it
FADE_OUT_S = (2.15, 0.05)           # the music fades from R1 - 2.15 s to R1 - 0.05 s
VLO = 0.6               # slowest average speed between two kills of a take (slow motion between kills is fine); the fastest is max_speed
VHI_OLD = 1.7           # "max_speed": null (the old behaviour): the example's M entries ran 0.87 to 1.3x
JOIN_FRAMES = 6.0       # "bass" joins kills of one clip closer than this many beats of real time
BULLET = (3.0, 6.0, 4.0)        # lead-in beats of the drop bullet time: (min, max, preferred)
LEAD_SPEEDS = (0.50, 0.30, 0.20, 0.17)
BASS_LEAD_EXTRA = 1.5   # "bass": beats of real-time lead allowed beyond the lead window between the kick that carries the cut and the first kill
BULLET_HIT = (2.0, 3.0, 2.5)    # lead-in beats of a "hit" bullet: (min, max, preferred)
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
LEAD_WIN = 2           # frames either side of lead_frames the SHOWN lead of a kills-mode take may take (12..16 at 14)
MARGIN_F = 0.1         # frames of margin the solver keeps on every whole-frame rule (lead window, death, kill spacing): the hits are measured in
                       # a window that differs a hair from the one the gate measures in (sub-millisecond), and the frame of a beat is a rounding
SUBS = (2, 4)          # the lattices a kill may sit on: half beats, quarter beats
LADDER = (0.5, 0.25, 0.125, 0.0625)    # the lattices a kills-mode cut sits on, the coarsest that fits first (beats); 1/16 only where none of 1/2, 1/4, 1/8 has a line in the lead window (95.7 BPM: 1/8 beat = 4.7 frames, the window 4)
DRIFT_MS = 8.0         # a slope of the measured attacks against the grid over the section above this (and significant) is a wrong BPM
STRONG_ODD = 0.20      # share of the strong kicks / snares on a quarter that is not a half beat from which kills use the quarter-beat lattice
SLOW_BELOW = 0.6       # a frame slower than this is "slow motion" for the reference's slow share
H_DEFAULT = 8          # fall()'s real-time hold after a shot (frames), the template's default
KEYS = {"music", "bpm", "beat0", "drop_beat", "start_beat", "cuts_on", "lead_frames", "frame", "max_speed", "length", "length_tolerance", "look",
        "intro", "ref_notes", "kills", "auto_bullet", "cut_lead_frames", "hit_lead_frames", "hit_grid"}
SUM = "# draft_ref_timeline.py checksum (a changed file is never overwritten without --force): "


def die(errors, what="cannot draft this plan"):
    if isinstance(errors, str):
        errors = [errors]
    sys.exit("draft_ref_timeline.py %s:\n  - %s\nNothing was written. Fix plan.json (or the inputs) and run it again." % (what, "\n  - ".join(errors)))


def fnum(x, nd=4, keep=False):
    s = ("%.*f" % (nd, x)).rstrip("0").rstrip(".")
    s = "0" if s in ("-0", "") else s
    return s + ".0" if keep and "." not in s else s


def r9(x):
    """a beat as it is written into the file (9 decimals) and read back: the value every later computation of the draft uses"""
    return float("%.9f" % x)


def b9(x):
    """a musical beat for the file: 9 decimals (a hit time to 0.5 ns of a beat at 124 BPM), never fewer"""
    return fnum(x, 9, True)


def uq(b):
    """the solver's unit: the quarter beat nearest to beat b (a measured hit lies within half a lattice step of it)"""
    return int(round(b * 4.0))


# ------------------------------------------------------------------------------------------------ the reference
class Ref:
    """ref_notes.json and what the draft did with each trait of its "adopt" block: rows of (followed | not followed, trait, text)."""
    def __init__(self, path, adopt, doc, off=None):
        self.path, self.a, self.doc, self.off = path, adopt or {}, doc or {}, off
        self.rows, self.used = [], set()
        self.base = None

    def freeze(self):
        """what the plan-level traits (apply_reference) decided: every draft pass starts from it (the auto-bullet pass drafts again)"""
        self.base = (list(self.rows), set(self.used))

    def revert(self, trait, why):
        """a plan-level trait that made the plan unplaceable: the draft goes on without it, saying why"""
        rows, used = self.base
        self.base = ([("not followed", t, why) if (t == trait and st == "followed") else (st, t, tx) for st, t, tx in rows], used - {trait})

    def reset(self):
        if self.base:
            self.rows, self.used = list(self.base[0]), set(self.base[1])

    def took(self, trait, text):
        self.rows.append(("followed", trait, text))
        self.used.add(trait)

    def skipped(self, trait, why):
        self.rows.append(("not followed", trait, why))

    def report(self):
        if self.off:
            return ["reference: %s" % self.off]
        out = ["reference %s: %d of %d traits followed" % (self.path, len(self.used), len(self.rows))]
        out += ["  %-12s %-13s %s" % (t, st, tx) for st, t, tx in self.rows]
        return out


def user_step(a, per):
    """the subdivision of the USER's beat that the reference's cut lattice corresponds to: the one (1/8 .. 2 beats) whose duration in seconds is
    nearest, in log2, to lattice.step_s; for a reference with the same song the steps are the song's own beats (step_beats_ref)"""
    lat = a.get("lattice") or {}
    cands = (0.125, 0.25, 0.5, 1.0, 2.0)
    same = (a.get("same_song") or {}).get("offset_s")
    if same is not None and lat.get("step_beats_ref"):
        sb = float(lat["step_beats_ref"])
        return min(cands, key=lambda c: abs(math.log2(c / sb))), "same song: the song's own %g beat" % sb
    ss = lat.get("step_s")
    if isinstance(ss, (int, float)) and ss > 0:
        c = min(cands, key=lambda c: abs(math.log2(c * per / ss)))
        return c, "%.0f ms steps = %g of a beat here (%.0f ms)" % (ss * 1000, c, c * per * 1000)
    return None, None


def load_reference(P, E):
    notes = P.get("ref_notes")
    if notes is False:
        return Ref(None, None, None, 'plan.json says "ref_notes": false: the reference is ignored')
    if not notes:
        notes = "ref_notes.json" if os.path.isfile("ref_notes.json") else None
    if not notes:
        return None
    if not os.path.isfile(notes):
        E.append("ref_notes %s does not exist" % notes)
        return None
    try:
        doc = json.load(open(notes, encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        E.append("%s cannot be read (%s)" % (notes, e))
        return None
    ad = doc.get("adopt")
    ref = Ref(notes, ad if isinstance(ad, dict) else None, doc)
    if not isinstance(ad, dict):
        ref.skipped("adopt", 'ref_notes.json has no "adopt" block (written by ref_analyze.py of this skill version: run it again on the reference)')
    return ref


def apply_reference(P, E):
    """Reads the reference's traits that the plan itself decides (frame, look, cuts_on, lattice, leads, ending), with the precedence plan > reference
    > model; the traits that need the takes (gaps, transitions, slow, intro) are applied later. Sets P["ref"]."""
    ref = P["ref"] = load_reference(P, E)
    given = P["_given"]
    P.update(cut_lead=1, hit_lead=1, luma_s=LUMA_S, black_s=BLACK_S, ladder=list(LADDER), step=None)
    for key, trait in (("cut_lead_frames", "cut_lead"), ("hit_lead_frames", "hit_lead")):
        if key in given:
            v = P[key]
            if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 3:
                E.append('"%s" must be a whole number of frames from 0 to 3, not %r' % (key, v))
            else:
                P[trait] = v
                P[trait + "_why"] = 'plan.json "%s"' % key
    if ref is None or ref.off or not ref.a:
        if ref is not None and not ref.off and "cuts_on" not in given:
            sug = (ref.doc.get("suggested") or {}).get("CUTS_ON")
            if sug in ("bass", "kills"):
                P["cuts_on"] = sug
                ref.took("cuts_on", "suggested CUTS_ON %r" % sug)
        if ref is not None:
            ref.freeze()
        return ref
    a, per = ref.a, 60.0 / P["bpm"]
    if "frame" in given:
        ref.skipped("frame", 'plan.json sets "frame": %r (the plan wins)' % P["frame"])
    elif a.get("frame") in ("horizontal", "vertical"):
        P["frame"] = a["frame"]
        ref.took("frame", "%s (the reference's orientation)" % a["frame"])
    else:
        ref.skipped("frame", "the reference gave none: %s (the model default)" % P["frame"])
    lk = a.get("look")
    if "look" in given:
        ref.skipped("look", "plan.json sets \"look\" (the plan wins)")
    elif isinstance(lk, dict) and lk:
        P["look"] = dict(lk)
        ref.took("look", "LOOK %s (the reference's measured colour / vignette / fringe)" % json.dumps(lk, sort_keys=True))
    else:
        ref.skipped("look", "the reference gave none: LOOK %r (the model default)" % (P["look"],))
    if "cuts_on" in given:
        ref.skipped("cuts_on", 'plan.json sets "cuts_on": %r (the plan wins)' % P["cuts_on"])
    else:
        sug = (ref.doc.get("suggested") or {}).get("CUTS_ON")
        if sug in ("bass", "kills"):
            P["cuts_on"] = sug
            ref.took("cuts_on", "suggested CUTS_ON %r (cuts on kicks only when 65 %% of the reference's cuts are)" % sug)
        else:
            ref.skipped("cuts_on", 'the reference gave none: "kills" (the model default)')
    step, why = user_step(a, per)
    lat = a.get("lattice") or {}
    if step is None:
        ref.skipped("lattice", "the reference has no locked cut lattice: cuts sit on the coarsest of 1/2, 1/4, 1/8 beat that fits the lead window")
    else:
        P["step"] = step
        P["ladder"] = [step] + [x for x in LADDER if x != step]
        ref.took("lattice", "cuts on lines of %g beat first (%s; locked R %s, residual %s ms), the coarsest of 1/2, 1/4, 1/8 where %g does not fit the lead window" % (
            step, why, lat.get("locked_R", "?"), lat.get("residual_ms", "?"), step))
    for key, trait, what in (("cut_lead_frames", "cut_lead", "cut"), ("hit_lead_frames", "hit_lead", "kill flash")):
        v = a.get(key)
        if key in given:
            ref.skipped(trait, 'plan.json sets "%s": %d (the plan wins)' % (key, P[trait]))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            P[trait] = int(max(0, min(3, round(v))))
            P[trait + "_why"] = "the reference's (%s frames measured)" % v
            ref.took(trait, "%s %d frame(s) before its musical moment (the reference: %s)" % (what, P[trait], v))
        elif key == "cut_lead_frames" and isinstance(lat.get("offset_frames"), (int, float)):
            P[trait] = int(max(0, min(3, round(-lat["offset_frames"]))))
            P[trait + "_why"] = "the reference's (lattice offset %+.2f frames)" % lat["offset_frames"]
            ref.took(trait, "%s %d frame(s) before its line (from the lattice offset %+.2f frames)" % (what, P[trait], lat["offset_frames"]))
        else:
            note = a.get(key.replace("_frames", "_note"))
            ref.skipped(trait, "the reference gave none (not measurable%s): %d frame (the model's convention)" % ((": " + note) if note else "", P[trait]))
    en = a.get("ending") or {}
    fs, bs = en.get("fade_s"), en.get("black_s")
    if isinstance(fs, (int, float)) and isinstance(bs, (int, float)) and 0.05 <= fs <= 1.5 and 0.2 <= bs <= 4.0:
        P["luma_s"], P["black_s"] = float(fs), float(bs)
        ref.took("ending", "luma fade %.2f s, black %.2f s (the reference's)" % (fs, bs))
    else:
        ref.skipped("ending", "the reference gave no usable fade / black (%r): %.2f s / %.2f s (the model)" % (en or None, LUMA_S, BLACK_S))
    sl = a.get("slow") or {}
    if isinstance(sl.get("rate"), (int, float)) and 0 < sl["rate"] < 1:
        P["fall_min"] = min(0.3, max(0.06, float(sl["rate"])))              # fall()'s slowest constant rate: the reference's slow-motion rate
    if isinstance(a.get("words"), dict):
        ref.skipped("words", "cap height / position not applied: the user's size rule wins (caps 21 / 19 %, centre); the sung words come from lyric_cues.json")
    ref.freeze()
    return ref


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
    P["_given"] = set(P)
    P.setdefault("cuts_on", "kills")
    P.setdefault("frame", "vertical")
    P.setdefault("max_speed", 1.0)
    P.setdefault("length_tolerance", 0.10)
    P.setdefault("look", "modelo")
    P.setdefault("lead_frames", 14)
    P.setdefault("auto_bullet", True)
    P.setdefault("hit_grid", None)
    if not isinstance(P["auto_bullet"], bool):
        E.append('"auto_bullet" must be true (the default) or false, not %r' % (P["auto_bullet"],))
    if P["hit_grid"] not in (None, 2, 4):
        E.append('"hit_grid" must be 2 (kills on half beats), 4 (quarter beats) or absent (automatic), not %r' % (P["hit_grid"],))
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
    else:
        P["bpm"], P["beat0"] = round(float(P["bpm"]), 6), round(float(P["beat0"]), 6)      # the file prints them with 6 decimals: the draft computes with what it prints
    P["drop_beat"] = int(round(P["drop_beat"]))
    P["start_beat"] = int(round(P["start_beat"])) if P.get("start_beat") is not None else None
    if E:
        die(E)
    apply_reference(P, E)                                # frame, look, cuts_on, lattice, CUT_LEAD / HIT_LEAD, ending: plan > reference > model
    ks = P["kills"]
    if not isinstance(ks, list) or len(ks) < 2:
        E.append("a draft needs at least 2 kills (a first one and the last one, which ends the video)")
        die(E)
    db = preflight.kills_db()
    kills, nb = [], 0
    unverified = []
    for i, k in enumerate(ks):
        tag = "kill #%d" % (i + 1)
        entry = None
        if "id" in k:                                  # {"id": 96}: clip and K from kills.json
            if not db:
                E.append("%s: \"id\" needs kills.json in this folder" % tag)
                continue
            entry = db.get(str(k["id"]))
            if not entry:
                E.append("%s: kills.json has no entry %r" % (tag, k["id"]))
                continue
            k = dict(k, clip=k.get("clip", entry["clip"]), K=k.get("K", entry["K"]))
        if "clip" not in k or "K" not in k:
            E.append('%s needs "clip" and "K" (or an "id" of kills.json)' % tag)
            continue
        why_k = preflight.k_check(db, k)
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
        if at is not None and (isinstance(at, bool) or not isinstance(at, (int, float)) or abs(at * 4 - round(at * 4)) > 1e-9):
            E.append('%s: "at" is the timeline beat the kill lands on, a multiple of 0.25 (beat 0 = the first landing / the drop), not %r' % (tag, at))
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
    if unverified:
        E.append("%d kill(s) with an unverified K (a K one frame off is 16.7 ms of desync between the shot and the drum): %s. To fix: %s; or use the K that kverify prints" % (
            len(unverified), "; ".join(unverified[:8]) + (" ..." if len(unverified) > 8 else ""), preflight.K_HELP))
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
    db = preflight.kills_db()
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
        why_k = preflight.k_check(db, dict(clip=s["clip"], K=K, id=s.get("id")))
        if why_k and not s.get("k_checked"):
            E.append("intro kill #%d (%s K=%d): %s. To fix: %s (on the intro kill)" % (j + 1, s["clip"], K, why_k, preflight.K_HELP))
        at = s.get("at")
        if at is not None and (isinstance(at, bool) or not isinstance(at, (int, float)) or abs(at * 4 - round(at * 4)) > 1e-9):
            E.append('intro kill #%d: "at" is the timeline beat the kill lands on, a multiple of 0.25, not %r' % (j + 1, at))
        if s.get("silent") and at is None:
            E.append('intro kill #%d: "silent": true pins the kill on the grid where the intro has no drum, so it needs "at"' % (j + 1))
        ikills.append(dict(clip=s["clip"], K=K, n=n, at=at, silent=bool(s.get("silent")), upto=int(up) if up is not None else UPTO_DEFAULT, upto_given=up is not None))
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
    def __init__(self, bpm, max_speed=None, lead_frames=14.0, cut_lead=1, hit_lead=1, luma_s=LUMA_S, black_s=BLACK_S):
        self.bpm, self.per = bpm, 60.0 / bpm
        self.F = 60 * self.per
        self.sc = bpm / 130.0                       # the constants of the example are frames at 130 BPM
        self.lead_frames = float(lead_frames)
        self.lead_b = self.lead_frames / self.F     # beats from the cut to the first shot (nominal: the lead window is centred on it)
        self.cl, self.hl = int(cut_lead), int(hit_lead)
        # the SHOWN lead of a take = nearest_frame(first hit) - HIT_LEAD - (nearest_frame(cut moment) - CUT_LEAD) is an integer number of frames in
        # {floor(d), ceil(d)} + CUT_LEAD - HIT_LEAD, d = frames between the two MUSICAL moments: a d inside the window shrunk by MARGIN_F puts it in
        # lead_frames +- LEAD_WIN whatever the rounding does. The death needs the next cut's frame at least `upto` frames after the shot's frame: the
        # same arithmetic gives d >= upto + CUT_LEAD - HIT_LEAD (+ the margin).
        self.sh = self.cl - self.hl
        self.d_lo = (self.lead_frames - LEAD_WIN - self.sh + MARGIN_F) / self.F
        self.d_hi = (self.lead_frames + LEAD_WIN - self.sh - MARGIN_F) / self.F
        self.d_target = (self.lead_frames - self.sh) / self.F
        self.scan_pre = BASS_LEAD_EXTRA + self.lead_b + 1.0     # beats before R0 the hits are measured from (the kick / line before the first kill)
        self.hold, self.hold_short, self.thr, self.out = 0.3 * self.sc, 0.2 * self.sc, 0.8 * self.sc, 0.08 * self.sc
        self.max_speed = max_speed                  # None: the old behaviour (fast-forward through the blur-in, speed-ups)
        self.post_fn = None                         # the post() / fall() of the file being built (set_helpers): one source of truth
        self.fall_fn = None
        pref = TAIL_PIC + luma_s + black_s          # seconds: the ace's picture, the fade, the black
        self.tail = tuple(x / self.per for x in (pref + TAIL_DIFF[0], pref + TAIL_DIFF[1], pref))     # last take after its last kill: (min, max, preferred) beats
        self.final_rate = 0.12 if max_speed is None else 0.10      # the last take's slow motion (the model: about 0.08x under the fade; 0.12x keeps the old fast-forward mode inside the speed limits)

    def death_b(self, upto):
        """beats between a take's last kill (musical) and the next cut's musical moment so that the death is shown to K + upto in whole frames"""
        return (upto + self.sh + MARGIN_F) / self.F

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
    """The drum hits of a stretch of the song, measured (beat_hits.measure_t): strengths on the quarter-beat lattice (u = quarter beats) and, for
    every row with an attack, the attack's time as a TIMELINE beat (the musical beat an event is written at). `sub` (2 or 4) is the lattice kills
    and bumps may sit on: every second quarter (half beats) or every quarter."""
    def __init__(self, rows, att, raw, sub, F, hitf):
        self.sub, self.step, self.F = sub, 4 // sub, F
        self.low, self.mid, self.high = {}, {}, {}
        for b, lo, mi, hi in rows:
            u = uq(b)
            self.low[u], self.mid[u], self.high[u] = lo, mi, hi
        self.raw = {uq(b): (lo, mi, hi) for b, lo, mi, hi in raw} if raw else {}       # unclipped strengths (levels, bumps)
        self.att, self.mb, self.bands, self.adopted = {}, {}, {}, set()
        ab = getattr(att, "bands", None) or {}
        for b, (t, band) in att.items():
            u = uq(b)
            self.att[u] = (t, band)
            self.mb[u] = r9(hitf(t))                                                      # the musical beat of the row's strongest attack
            self.bands[u] = {k: r9(hitf(v)) for k, v in (ab.get(b) or {band: t}).items()}  # every band's attack of the row (a kick under a snare)
        al = getattr(att, "all", None) or []                                         # every attack of the window (weak ones too): what a cut may sit on
        self.all_b = sorted(set([r9(hitf(t)) for t, band, rise in al] + list(self.mb.values())))
        self.kicks = sorted((u for u, v in self.low.items() if v >= KICK and u in self.att), key=self.kick_beat)
        self.kills = sorted((u for u in self.low if u % self.step == 0 and self.can_kill(u)), key=self.beat)
        self.kill_b = [self.beat(u) for u in self.kills]

    def beat(self, u):
        """the musical beat of the hit on lattice row u: its measured attack; the grid beat where the row has none"""
        return self.mb.get(u, u / 4.0)

    def kick_beat(self, u):
        """the attack of the kick (low band) on row u (a snare on the same row has its own time)"""
        return self.bands.get(u, {}).get("low", self.beat(u))

    def near_attack(self, b, tol):
        """the measured attack (any band, any strength) nearest to beat b within tol beats, or None"""
        i = bisect.bisect_left(self.all_b, b - tol)
        best = None
        while i < len(self.all_b) and self.all_b[i] <= b + tol:
            if best is None or abs(self.all_b[i] - b) < abs(best - b):
                best = self.all_b[i]
            i += 1
        return best

    def cutbeat(self, line):
        """the musical moment of a cut on the lattice line `line` (beats): the measured attack (any band) within half a frame of the line, else the grid
        line itself"""
        a = self.near_attack(line, 0.5 / self.F)
        return a if a is not None else r9(line)

    def adopt_attack(self, u, tol):
        """a row without a strength of its own (the drop: a crash, a riser's end, a kick the thresholds do not call one) takes the nearest measured attack (any band,
        any strength) within tol beats of its lattice point as its hit; False when there is none"""
        if u in self.att:
            return True
        a = self.near_attack(u / 4.0, tol)
        if a is None:
            return False
        self.mb[u] = a
        self.att[u] = (None, "any")
        self.bands[u] = {"any": a}
        self.adopted.add(u)
        return True

    def dt_ms(self, u, per):
        return (self.beat(u) - u / 4.0) * per * 1000.0

    def kick(self, u):
        return self.low.get(u, 0) >= KICK and u in self.att

    def has_hit(self, u):
        return u in self.att

    def can_kill(self, u):
        return u in self.att and (self.low.get(u, 0) >= KICK or self.mid.get(u, 0) >= SNARE or self.high.get(u, 0) >= HAT)

    def strength(self, u):
        return max(self.low.get(u, 0), self.mid.get(u, 0))

    def score(self, u):
        return max(self.low.get(u, 0), self.mid.get(u, 0), self.high.get(u, 0))

    def snare(self, u):
        """unclipped snare / clap strength (beat_hits' mid: body and crack both arriving) of a hit that is not a kick (0 on a kick); a hat has none"""
        lo, mi, hi = self.raw.get(u, (0.0, 0.0, 0.0))
        return 0.0 if self.low.get(u, 0) >= KICK else mi

    def describe(self, u, per=None):
        lo, mi, hi = self.low.get(u, 0), self.mid.get(u, 0), self.high.get(u, 0)
        if u not in self.att:
            s = "no attack on the lattice there (low %.2f mid %.2f high %.2f)" % (lo, mi, hi)
        elif lo >= KICK:
            s = "kick %.2f" % lo
        elif mi >= SNARE:
            s = "snare %.2f" % mi
        elif hi >= HAT:
            s = "hat %.2f" % hi
        else:
            s = "low %.2f mid %.2f high %.2f" % (lo, mi, hi)
        if per is not None and u in self.att:
            s += ", attack %+.1f ms from the grid" % self.dt_ms(u, per)
        return s


def strong_odd_share(H4):
    """share of the strong kicks / snares (STRONG) of a quarter-beat measure that sit on a quarter that is not a half beat"""
    us = [u for u in H4.att if max(H4.low.get(u, 0), H4.mid.get(u, 0)) >= STRONG]
    return (sum(1 for u in us if u % 2) / len(us) if us else 0.0), len(us)


def drift_problem(rows, att, hitf, per, bpm, r0, r1):
    """-> a sentence when the grid of `bpm` does not fit the measured attacks of the strong kicks / snares (the BPM is wrong: the attacks drift against the grid
    by more than DRIFT_MS ms over the section), else None. The attacks (rows / att = beat_hits.measure_t on the quarter-beat lattice with every attack filed,
    tol = 1: a drifting song's late hits too) are fitted by the phase coherence R(p) = |mean exp(2 pi i t / (p / 4))| of a quarter-beat lattice of period p, p
    within +-1.5 % of the plan's: the tempo with the highest R against the plan's own. It refuses when the better tempo makes the grid drift by DRIFT_MS ms or more
    over the section and R rises by 0.12 or more (a constant grid of a steady song is its own maximum: no refusal)."""
    ts = [att[b][0] for b, lo, mi, hi in rows if r0 <= b <= r1 and b in att and (lo >= KICK or mi >= SNARE)]
    if len(ts) < 10:
        return None
    t = np.array(sorted(ts))
    span = float(t.max() - t.min()) / per                                            # beats

    def R(p):
        return float(abs(np.exp(2j * np.pi * t / (p / 4.0)).mean()))
    ps = per * (1.0 + np.arange(-0.015, 0.015 + 1e-9, 0.0001))
    rs = np.array([R(p) for p in ps])
    p_best = float(ps[int(np.argmax(rs))])
    r_grid, r_best = R(per), float(rs.max())
    drift_ms = abs(p_best - per) * span * 1000.0
    if drift_ms >= DRIFT_MS and r_best - r_grid >= 0.12:
        return ("the measured attacks of the %d strong kicks / snares fit a tempo of %.2f BPM (phase coherence %.2f) much better than the plan's %g BPM (%.2f): the attacks "
                "drift against the grid by %+.2f ms per beat (%+.0f ms over the %.0f beats of the section). Placing on this grid would put the cuts' lattice lines, the "
                "lead window and the hit candidates off the music: run music_grid.py with %.2f (and its BEAT0) and set \"bpm\" / \"beat0\" in plan.json" % (
                    len(t), 60.0 / p_best, r_best, bpm, r_grid, (p_best - per) * 1000.0, (p_best - per) * span * 1000.0, span, 60.0 / p_best))
    return None


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
    """Places the takes. Every kill is a MEASURED hit (Hits.beat(u): the attack's musical beat), every cut a line of the lattice (or the attack on it, or a
    kick's attack in "bass"); the solver's rules are in beats of those musical moments with a margin of MARGIN_F frames wherever the rounding to output
    frames can bite (Tempo: lead window, death, kill spacing); verify() then checks the finished module on its shown frames."""
    def __init__(self, P, T, takes, hits, D, bass, lprefs=None, ladder=LADDER):
        self.P, self.T, self.takes, self.H, self.D = P, T, takes, hits, D
        self.bass, self.lprefs, self.ladder = bass, lprefs, list(ladder)
        self.vhi = P["max_speed"] if P["max_speed"] is not None else VHI_OLD      # fastest average speed between two kills of a take
        self.R1_lo = self.R1_hi = self.R1_t = 0.0
        self.explore = False
        self.nf = {t.clip: clipio.n_frames(t.clip) for t in takes}
        self.cache = {}
        self.fail_j = None                              # solve() failed placing this take (0-based): which take blocked the plan

    # ---- footage
    def after_ok(self, tk, last, end, final=False):
        """does the clip have the footage that follows the take's last shot (the death, or the slow ending)? `last` is the kill's musical beat, `end` the
        next cut's musical moment (the last take: R1)"""
        T = self.T
        k = last - T.hl / T.F                                     # the beats the picture shows them on (a frame of room on the cut)
        e = end if final else end - T.cl / T.F + 1.0 / T.F
        key = (tk.clip, tk.Ks[-1], round(k, 3), round(e, 3), tk.upto, final)
        if key not in self.cache:
            if final:
                self.cache[key] = T.after_final(k, tk.Ks[-1], e, T.final_rate, self.nf[tk.clip])
            else:
                self.cache[key] = T.fall_after(k, tk.Ks[-1], e, tk.upto, self.nf[tk.clip])
        return self.cache[key]

    def lead_anchors(self, tk, S, h):
        if tk.lkind == "drop":
            return self.T.lead(S, h, tk.Ks[0])
        return self.T.lead(S, h, tk.Ks[0], HIT_SPEEDS, (0.55,))

    def pre_ok(self, tk, S, h):
        """does the clip have the footage before the take's first kill (the lead-in, or the real-time lead; a frame of room for the rounding)"""
        if tk.kind == "L":
            return self.lead_anchors(tk, S, h)[0][1] >= MARGIN
        return tk.Ks[0] - self.T.pre_src((h - S) * self.T.F + 1.0, tk.pre_n) >= MARGIN

    def kill_bonus(self, u, lv):
        return 0.6 * (lv - 1) * (1 - self.H.strength(u)) if lv > 1 else 0.0

    # ---- one take placed at a head u (quarter beats): the options for its kills
    def head_beat(self, tk, u):
        """musical beat of the take's first kill for head u (for the drop bullet the head is the START of the lead-in: the kill is on the drop)"""
        return self.H.beat(4 * self.D) if tk.lkind == "drop" else self.H.beat(u)

    def options(self, j, u):
        tk = self.takes[j]
        H = self.H
        lv = tk.level or (3 if tk.lkind == "drop" or j == len(self.takes) - 1 else 2 if tk.lkind == "hit" else 1)
        if tk.lkind == "drop":
            return [dict(tails=(), last=H.beat(4 * self.D), cost=0.0)]
        h = H.beat(u)
        w = 0.25 * (1 - H.score(u))                            # a stronger hit is preferred
        if tk.kind in ("K", "L"):
            return [dict(tails=(), last=h, cost=w + self.kill_bonus(u, lv))]
        out = {}
        F = self.T.F
        kb, ku = H.kill_b, H.kills

        def rec(i, prevb, tails, cost):
            if i == len(tk.Ks):
                last = tails[-1]
                c = cost + self.kill_bonus(uq(last), lv)
                if last not in out or c < out[last]["cost"]:
                    out[last] = dict(tails=tuple(tails), last=last, cost=c)
                return
            dF = tk.Ks[i] - tk.Ks[i - 1]
            lo = prevb + max(GAP_KILLS, (dF / self.vhi + 1.0) / F)         # one frame of margin: the shown frames of the two kills differ by floor(d) or ceil(d)
            hi = prevb + (dF / VLO - 1.0) / F
            if tk.at[i] is None:
                pool = ((kb[x], ku[x]) for x in range(bisect.bisect_left(kb, lo - 1e-9), len(kb)))
            else:
                x = uq(tk.at[i])
                pool = [(H.beat(x), x)]
            for b, x in pool:
                if b < lo - 1e-9:
                    continue
                if b > hi + 1e-9:
                    break
                v = dF / ((b - prevb) * F)
                rec(i + 1, b, tails + [b], cost + 2.0 * abs(math.log(v)) + 0.1 * (1 - H.score(x)))
        rec(1, h, [], w)
        return list(out.values())

    def heads(self, j):
        """candidate heads (quarter beats) of take j: the first kill's row (the drop bullet: the start of its lead-in), nearest beat first"""
        tk, H = self.takes[j], self.H
        if tk.lkind == "drop":
            if self.bass:
                return [u for u in H.kicks if BULLET[0] <= self.D - H.kick_beat(u) <= BULLET[1]]
            lo = int(math.ceil((self.D - BULLET[1]) * 2 - 1e-9)) * 2
            hi = int(math.floor((self.D - BULLET[0]) * 2 + 1e-9)) * 2
            return list(range(lo, hi + 1, 2))                  # half-beat lines
        if tk.at[0] is not None:
            return [uq(tk.at[0])]
        if tk.lkind == "hit":
            strong = [u for u in H.kills if H.score(u) >= STRONG]
            return strong or list(H.kills)
        return list(H.kills)

    def start_of(self, j, u, dprev):
        """(musical beat, how) where take j starts (its cut's musical moment) when its head is u and the take before it needs the picture until the cut
        is at beat dprev (the death shown, in whole frames); how = ("line", beat) or ("kick", u) (re-evaluated on the final measure); None when there is
        no such start.
          kills mode  : the coarsest lattice (the reference's step first, then 1/2, 1/4, 1/8 beat) with a line whose musical moment (the attack on it
                        within half a frame, else the line) puts the first hit d beats later with the SHOWN lead inside lead_frames +- LEAD_WIN; the line
                        nearest lead_frames wins
          "bass"      : the attack of the kick nearest before the lead window (up to BASS_LEAD_EXTRA beats further back)
          "hit" bullet: the next 1/4-beat line after h - 2.5 beats (and after dprev), at its attack when it has one
          drop bullet : a half-beat line (the head), or a kick"""
        tk, T, H = self.takes[j], self.T, self.H
        h = self.head_beat(tk, u)
        if tk.lkind == "drop":
            if self.bass:
                m = H.kick_beat(u)
                return (m, ("kick", u)) if m >= dprev - 1e-9 else None
            m = H.cutbeat(u / 4.0)
            return (m, ("line", u / 4.0)) if m >= dprev - 1e-9 else None
        if tk.lkind == "hit":
            lo, hi = max(h - BULLET_HIT[1], dprev), h - BULLET_HIT[0]
            if self.bass:
                ks = [(H.kick_beat(c), c) for c in H.kicks if lo - 1e-9 <= H.kick_beat(c) <= hi + 1e-9]
                if not ks:
                    return None
                b, c = min(ks, key=lambda x: (abs((h - x[0]) - BULLET_HIT[2]), -x[0]))
                return b, ("kick", c)
            n0 = int(math.ceil(max(h - BULLET_HIT[2], dprev) * 4 - 1e-9))
            for n in range(n0, n0 + 3):                        # the attack on a line may lie half a frame before it: the next line when it breaks dprev
                m = H.cutbeat(n / 4.0)
                if m < dprev - 1e-9:
                    continue
                return (m, ("line", n / 4.0)) if m <= hi + 1e-9 else None
            return None
        if self.bass:
            for c in reversed(H.kicks):                        # latest kick first: the nearest one before the first hit that leaves the lead
                b = H.kick_beat(c)
                if h - b >= T.d_lo - 1e-12:
                    if h - b > T.d_hi + BASS_LEAD_EXTRA:
                        return None
                    return (b, ("kick", c)) if b >= dprev - 1e-9 else None
            return None
        for step in self.ladder:
            best = None
            n0 = int(math.ceil((h - T.d_hi) / step - 1e-9)) - 1
            n1 = int(math.floor((h - T.d_lo) / step + 1e-9)) + 1
            for n in range(n0, n1 + 1):
                m = H.cutbeat(n * step)
                d = h - m
                if d < T.d_lo - 1e-12 or d > T.d_hi + 1e-12 or m < dprev - 1e-9:
                    continue
                c = abs(d - T.d_target)
                if best is None or c < best[0]:
                    best = (c, m, n * step)
            if best:
                return best[1], ("line", best[2])
        return None

    def why_not(self, j, cand, layer):
        """the sentence of why_not1 and the reasons the candidates were turned down"""
        s = self.why_not1(j, cand, layer)
        rej = getattr(self, "rej", None)
        if rej:
            s += " [candidates turned down: %s]" % "; ".join("%d: %s" % (n, r) for r, n in rej.most_common(4))
        return s

    def why_not1(self, j, cand, layer):
        """one sentence with the numbers: why take j (0-based) has no place after the takes before it"""
        tk, prev = self.takes[j], self.takes[j - 1]
        T, H = self.T, self.H
        F = T.F
        name = "take %d (%s K=%s, %s)" % (j + 1, tk.clip, tk.Ks, tk.kind)
        dd = T.death_b(prev.upto)
        ends = [last + dd for (u0, last) in layer]
        lasts = [last for (u0, last) in layer]
        t0s = [v[0] for v in (self.start0.get((u0, last)) for (u0, last) in layer) if v is not None] or [0.0]
        dmin = min(ends)
        what = "kill-able hit (kick, snare or loud hat with a measured attack)"
        need = ("the take before it (%s K=%s) keeps its last kill until beat %s at the earliest, and the death needs %d frames = %.2f beats on screen after it, so "
                "the next cut is at beat %s or later" % (prev.clip, prev.Ks[-1], fnum(min(lasts), 1), prev.upto, prev.upto / F, fnum(dmin, 2)))
        if tk.lkind == "drop":
            reach = [u for u in cand if u / 4.0 >= dmin - 1e-9]
            return ("%s (bullet time into the drop at beat %g): its lead-in of %g to %g beats must start on %s at beat %s or later, but %s: use fewer kills "
                    "before the drop, kills with a shorter death (\"upto\"), or start_beat earlier" % (
                        name, self.D, BULLET[0], BULLET[1], "a kick" if self.bass else "a beat", " / ".join(fnum(u / 4.0, 2) for u in reach[:8]) or "none", need))
        if tk.kind == "M" and not any(self.options(j, u) for u in cand):
            d = [b - a for a, b in zip(tk.Ks, tk.Ks[1:])]
            return ("%s: its kills are %s frames apart = %s beats at real time, and one take plays them at %.2f to %.2fx, so each later kill needs a hit %s beats "
                    "after the one before it. No hit in reach has one. Give the later kill a take of its own (\"with_previous\": false), or pick kills nearer to a hit" % (
                        name, ", ".join(str(x) for x in d), ", ".join("%.2f" % (x / F) for x in d), VLO, self.vhi,
                        " / ".join("%.2f to %.2f" % (max(GAP_KILLS, (x / self.vhi + 1) / F), (x / VLO - 1) / F) for x in d)))
        first = dmin + (BULLET_HIT[0] if tk.lkind == "hit" else T.d_lo)
        def reach_len(u):
            s = self.start_of(j, u, dmin)
            return (s[0] if s is not None else 1e9) - min(t0s)
        reach = [u for u in cand if H.beat(u) >= first - 1e-9 and reach_len(u) <= LEN_MAX + (self.D - min(t0s) if prev.lkind == "drop" else 0.0) + 1e-9]
        if not reach and first > min(t0s) + LEN_MAX:
            return ("take %d (%s K=%s) is too long: the take before it starts at beat %s and its last kill falls at beat %s, but %s: its first kill is at beat %s at the "
                    "earliest, %g frames (%.2f beats) after its cut, so the take would run beyond %g beats. Its kills are %s frames apart: split it "
                    "into two takes (\"with_previous\": false on the later kill) or leave a kill out" % (
                        j, prev.clip, prev.Ks, fnum(min(t0s), 2), fnum(min(lasts), 1), need, fnum(first, 2), T.lead_frames, T.lead_b, LEN_MAX,
                        ", ".join(str(b - a) for a, b in zip(prev.Ks, prev.Ks[1:])) or "-"))
        lst = " ".join(fnum(H.beat(u), 2) for u in reach[:14]) or "none"
        if not reach:
            if self.bass:
                kb = [H.kick_beat(c) for c in H.kicks if min(t0s) < H.kick_beat(c)]
                return ("%s has no kick to cut on: CUTS_ON \"bass\" cuts on the attack of a kick at least %.1f frames (%.2f beat, the lead window) and at most %.2f beats "
                        "before its first kill, and %s; the kicks after beat %s are at %s: no %s fits there. Use \"cuts_on\": \"kills\", or kills on other hits" % (
                            name, T.lead_frames - LEAD_WIN, T.d_lo, T.d_hi + BASS_LEAD_EXTRA, need, fnum(min(t0s), 1),
                            " ".join(fnum(x, 1) for x in kb[:14]) or "none", what))
            return ("%s has no %s to start on: %s, and its first kill must follow its cut by %.1f to %.1f frames (%.2f to %.2f beats) so it needs a %s at beat %s or "
                    "later (within %g beats of the previous cut): there is none" % (
                        name, what, need, T.lead_frames - LEAD_WIN, T.lead_frames + LEAD_WIN, T.d_lo, T.d_hi, what, fnum(first, 1), LEN_MAX))
        return ("%s cannot follow take %d: none of the %s within reach (beats %s) leaves the footage the take before it needs after its last kill "
                "(clip %s has %d frames after frame %d, it needs %d + the slow motion)" % (name, j, what, lst, prev.clip, self.nf[prev.clip] - 1 - prev.Ks[-1], prev.Ks[-1], prev.upto))

    def solve(self, first):
        """forward DP over the takes; `first` = the head u of take 0. -> ((cost, chain, R1, t_first), None) or (None, reason);
        with self.explore: ((lowest R1, highest R1) reachable, None) whatever the window"""
        takes, T, H = self.takes, self.T, self.H
        n = len(takes)
        F = T.F
        self.start0 = {}
        layer = {}
        st0 = self.start_of(0, first, -1e9)
        if st0 is not None and self.pre_ok(takes[0], st0[0], self.head_beat(takes[0], first)):
            for o in self.options(0, first):
                layer[(first, o["last"])] = (o["cost"], None, o["tails"], st0)
                self.start0[(first, o["last"])] = st0
        if not layer:
            return None, "take 1 (%s K=%s) has no placement at beat %s (%s)" % (takes[0].clip, takes[0].Ks, fnum(self.head_beat(takes[0], first), 2),
                                                                              "not enough footage before its first kill" if st0 is not None else
                                                                              ("no cut position before it: " + ("the song has no kick in the lead window before it" if self.bass else
                                                                               "no line of the lattice puts it %g to %g frames after the cut" % (T.lead_frames - LEAD_WIN, T.lead_frames + LEAD_WIN))))
        layers = [layer]
        t_first = st0[0]
        beats_avail = self.R1_hi - t_first
        lbar = max(0.75, (beats_avail * 0.97 - T.tail[2]) / max(1, n - 1)) if n > 1 else 1.0
        cands = [self.heads(j) for j in range(n)]
        for j in range(1, n):
            tk, prev_tk = takes[j], takes[j - 1]
            lp = self.lprefs[j - 1] if self.lprefs else None            # the reference's preferred length of the take before this cut
            lpref = lp or lbar
            short_ok = lp is not None and lp < 1.0
            nxt = {}
            self.rej = collections.Counter()                              # why candidates of THIS take were turned down (named in the refusal)
            for (u0, last), (c0, _, tails0, t0) in layers[-1].items():
                dprev = last + T.death_b(prev_tk.upto)                   # the take before it needs the picture until its enemy is down
                for u in cands[j]:
                    h = self.head_beat(tk, u)
                    if h < dprev - 1e-9:
                        self.rej["its first kill comes before the take before it is over"] += 1
                        continue
                    st = self.start_of(j, u, dprev)
                    if st is None:
                        self.rej["no cut position puts it the lead before the hit (%s)" % ("a kick" if self.bass else "a line of the lattice")] += 1
                        continue
                    s = st[0]
                    L = s - t0[0]
                    room = LEN_MAX + (self.D - t0[0] if prev_tk.lkind == "drop" else 0.0)
                    if L > room + 0.3:
                        self.rej["the take before it would run past %g beats" % LEN_MAX] += 1
                        break
                    if L > room + 1e-9:
                        self.rej["the take before it would run past %g beats" % LEN_MAX] += 1
                        continue
                    if L < 0.5 - 1e-9:
                        self.rej["the take before it would be under half a beat"] += 1
                        continue
                    if not self.after_ok(prev_tk, last, s):
                        self.rej["the clip of the take before it has no footage left for its death"] += 1
                        continue
                    if not self.pre_ok(tk, s, h):
                        self.rej["its clip has no footage before the shot"] += 1
                        continue
                    if h > self.R1_hi - T.tail[0]:
                        self.rej["it would leave the last take no room before the longest video allowed"] += 1
                        break
                    pen = (3.0 if lp is not None else 1.0) * ((L - lpref) / lpref) ** 2 + (0.3 if L < 0.99 and not short_ok else 0.0)     # the reference's rhythm weighs triple
                    if tk.lkind == "drop":
                        pen += 0.05 * ((self.D - s) - BULLET[2]) ** 2
                    elif tk.lkind == "hit":              # the drums thin out where a bullet time belongs: fewer strong kicks inside its lead-in
                        pen += 0.15 * sum(1 for x in H.kicks if s <= H.kick_beat(x) < h)
                    elif self.bass:                      # "bass": the nearer the kick before the first kill, the shorter the real-time lead
                        pen += 0.2 * ((h - s) - T.lead_b)
                    for o in self.options(j, u):
                        key = (u, o["last"])
                        c = c0 + pen + o["cost"]
                        if key not in nxt or c < nxt[key][0]:
                            nxt[key] = (c, (u0, last), o["tails"], st)
                            self.start0[key] = st
            if not nxt:
                self.fail_j = j
                return None, self.why_not(j, cands[j], list(layers[-1].keys()))
            layers.append(nxt)
        # the last take: calm, then the luma fade; R1 on the quarter-beat grid
        best, feas = None, []
        tk = takes[-1]
        for (u, last), (c, _, _, _) in layers[-1].items():
            for r in range(int(math.ceil((last + T.tail[0]) * 4)), int((last + T.tail[1]) * 4) + 1):
                R1 = r / 4.0
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
                tk.clip, tk.Ks, fnum(self.R1_lo, 1), fnum(self.R1_hi, 1), T.tail[0] * T.per, T.tail[1] * T.per,
                fnum(min(f for f in feas), 1) if feas else "?", fnum(max(feas), 1) if feas else "?"))
        cost, key, R1 = best
        chain = []
        for j in range(n - 1, -1, -1):
            c, prevk, tails, st = layers[j][key]
            chain.append(dict(u=key[0], last=key[1], tails=tails, start=st))
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
    return ("LEAD_FRAMES = %s                    # centre of the lead window: the SHOWN lead of a take (its cut's frame to its first shot's frame) is within +-%d frames of it\n"
            "CUT = LEAD_FRAMES / F               # the same in beats (about 0.48 beat at 124 BPM); a drafted take carries its own lb (cut moment -> first hit)\n"
            "CUT_LEAD = %d                        # frames a cut is SHOWN before its musical moment (vis()): %s\n"
            "HIT_LEAD = %d                        # frames a shot's flash and accents, a bump, a white flash-in and a word are SHOWN before their hit: %s\n"
            "PUSH = 0.03                         # slow push-in of a take (5 %% over a bullet time, none in the intro and the calm ending)\n") % (
        fnum(float(P["lead_frames"]), 2), LEAD_WIN, P["cut_lead"], P.get("cut_lead_why", "the model's convention (the reference: 1.3 to 1.9 frames)"),
        P["hit_lead"], P.get("hit_lead_why", "the model's convention (the reference: 1 frame)"))


POST_BLK = ("_post_130 = post\n\n\n"
            "def post(k, K, end, rate=0.16, hold=None, out=None, slow=SLOW_MAX):\n"
            '    """post() with its beat constants (0.3 / 0.2 beat of real time, 0.08 beat of speed-up) scaled to this tempo."""\n'
            "    SC = BPM / 130.0\n"
            "    if hold is None:\n"
            "        hold = (0.3 if end - k >= 0.8 * SC else 0.2) * SC\n"
            "    return _post_130(k, K, end, rate, hold, 0.08 * SC if out is None else out, slow)\n\n\n")


def post_block(P):
    """the draft:post block: post() scaled to the tempo, and the reference's slow-motion rate as fall()'s slowest constant rate (FALL_MIN)"""
    fm = P.get("fall_min")
    head = ("FALL_MIN = %s                       # the slowest constant rate of fall(): the reference's slow-motion rate (adopt.slow.rate)\n\n\n" % fnum(fm, 3)) if fm else ""
    return head + POST_BLK


def qline(x, q=4.0):
    """the beat line (1/q beat) nearest to x"""
    return math.floor(x * q + 0.5) / q


def bpm_text(P):
    return "%.1f" % P["bpm"] if float(P["bpm"]) == int(P["bpm"]) else fnum(float(P["bpm"]), 6)


def music_block(P, bpm_txt, M0, D, F, R0, R1, last=None):
    ms = P["max_speed"]
    per = 60.0 / P["bpm"]
    luma_s, black_s = P["luma_s"], P["black_s"]
    # the ending's events start on beat lines (1/4 beat): the music's fade and the picture's luma fade are read against the music
    f0 = qline(R1 - FADE_OUT_S[0] / per)
    if last is not None:
        f0 = max(f0, math.ceil((last + 0.5 / per) * 4 - 1e-9) / 4.0)       # never before the last kill's first half second
    l0 = qline(R1 - (black_s + luma_s) / per)
    l1 = min(l0 + luma_s / per, R1 - 0.05 / per)
    return ('MUSIC = "%s"\n'
            "BPM, BEAT0 = %s, %s          # tempo, and the time of the track's first beat (music_grid.py measures BEAT0)\n"
            "M0 = %d                             # timeline beat 0 = this beat of the track = the first landing (the drop is track beat %d = beat %s)\n"
            "PER = 60.0 / BPM\n"
            "FPS = 60\n"
            "FPB = FPS * PER                     # output frames per beat (%.2f)\n"
            "R0, R1 = %s, %s                 # first / last beat of the video (%.1f s): the first cut is shown on frame 0\n"
            "FADE_OUT = (%s, %s)             # the music fades over these beats (under the slow motion and the black)\n"
            "LUMA_FADE = (%s, %s)            # the picture: dark areas go black first, highlights last, on the calm last take; then %.2f s of black\n"
            'CUTS_ON = "%s"                    # where cuts land: "kills" (the cut sits before the kill) or "bass" (on a kick): the user\'s choice in the briefing\n'
            'FRAME = "%s"                # "horizontal" (1920x1080) or "vertical" (1080x1920: the gameplay in a window over a blurred backdrop)\n'
            "MAX_SPEED = %s                    # %s\n") % (
        P["music"], bpm_txt, fnum(P["beat0"], 6), M0, P["drop_beat"], fnum(D), F, b9(R0), b9(R1), (R1 - R0) * per,
        b9(f0), b9(R1 - 0.05 / per), b9(l0), b9(l1), (R1 - l1) * per,
        P["cuts_on"], P["frame"],
        "None" if ms is None else fnum(ms, 3, True),
        "no ceiling: the old fast-forward through the blur-in and after the slow motion (the user asked for velocity)" if ms is None else
        "nothing plays faster than real time (the user: \"do nada voce coloca o video muito rapido\"); 1.6 or None only when the user asks for velocity; preflight.py checks it")


def set_helpers(tpl, P, T, M0, D):
    """The take helpers (pre, post, fall, lead-in arithmetic) of the file being built, executed from the template with this plan's music, cut
    and post blocks and no entries: Tempo asks the file's own post() and fall() how much footage a take needs, so there is one of each."""
    src = tpl
    for name, blk in (("music", music_block(P, bpm_text(P), M0, D, T.F, 0.0, 1.0)), ("sound", "SWEEP = None\nRISERS = []\n"), ("cut", cut_block(P)),
                      ("post", post_block(P)), ("entries", "E = []\n"), ("words", "_T = []\n")):
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
    """BUMPS: the strongest hits (kick or snare, unclipped strength >= BUMP_MIN, with a measured attack, on the kill lattice) without a kill within 0.3
    beat, none in the calm last take or after the luma fade, at most BUMP_PER_S per second (the model: 13 in 31 s) and BUMP_GAP beats apart. Each is
    written at its attack's musical beat. -> [(beat, strength 0..1)]"""
    cand = []
    for u, (lo, mi, hi) in sorted(H.raw.items()):
        if u % H.step or u not in H.att:
            continue
        b, st = H.beat(u), max(lo, mi)
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
def body_slow_share(ns):
    """share of the frames below SLOW_BELOW x in the body: not the intro, not the calm last take (the reference's slow share is measured there)"""
    seg, v = preflight.frame_speeds(types.SimpleNamespace(**ns))
    segs = ns["SEGS"]
    body = np.array([not s.get("intro") and i != len(segs) - 1 for i, s in enumerate(segs)])
    m = body[seg]
    return float((v[m] < SLOW_BELOW).mean()) if m.any() else 0.0


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
        cuts = [uq(s.get("m0", s["r0"])) for s in segs[1:]]
        out["cuts"] = len(cuts)
        out["cuts_on_kick"] = sum(1 for u in cuts if hits.low.get(u, 0) >= CUT_LOW)
        hb = [m for m, _, _ in (ns.get("HITS") or ns["KILLS"])]
        ku = [uq(m) for m in hb]
        out["on_hit"] = sum(1 for m, u in zip(hb, ku) if u in hits.mb and abs(m - hits.mb[u]) <= 0.5 / F + 1e-9)
        out["max_dt"] = max([abs(m - u / 4.0) * ns["PER"] * 1000 for m, u in zip(hb, ku)] or [0.0])
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
        print(pad + "lead (shown frames from the cut to the first shot, K / M takes): median %.1f, min %.1f, max %.1f; frames shown after the last shot: median %.1f, min %.1f" % (
            np.median(ld), ld.min(), ld.max(), np.median(st["shown"]), min(st["shown"])))
    if st["deaths"][1]:
        print(pad + "deaths shown (frames after the shot >= upto): %d of %d" % st["deaths"])
    extra = []
    if "cuts" in st:
        extra.append("cuts on a kick: %d of %d" % (st["cuts_on_kick"], st["cuts"]))
        extra.append("kills on a measured attack %d of %d (kick %d, snare %d, hat %d; farthest from the grid %.1f ms)" % (
            st["on_hit"], st["kills"], st["kill_on"]["kick"], st["kill_on"]["snare"], st["kill_on"]["hat"], st["max_dt"]))
    extra.append("levels " + " ".join("%d:%d" % (k, v) for k, v in sorted(st["levels"].items())))
    print(pad + "; ".join(extra))
    print(pad + "blur-ins: " + ", ".join("%d %s" % (v, k) for k, v in sorted(st["kinds"].items())) +
          ("; whips +1: %d, -1: %d" % (st["whips"].get(1, 0), st["whips"].get(-1, 0)) if st["whips"] else "") +
          "; bumps %d, booms %d, risers %d" % (st["bumps"], st["booms"], st["risers"]))


def verify(ns, H, cuts_on, lead_frames, pins=(), ladder=LADDER):
    """Independent check of the finished module, on its SHOWN frames and its MUSICAL hits: preflight (SYNC 2, grid identities, exact frames), then
      * every kill's hit (musical beat) is a measured attack (within half a frame of one, as music_pulses.py / the gate check it; `pins` = the beats the
        plan pinned where the music has none), shown on vis(hit, HIT_LEAD); the shot plays at 0.5 .. 2.5x
      * the SHOWN lead (whole frames from the cut's frame to the first shot's frame) of every K / M take is inside lead_frames +- LEAD_WIN ("kills")
        or at least its low end ("bass")
      * every death is shown: whole frames from the last shot to the next cut >= upto, and the source frames shown after the shot >= upto
      * the kills of an M take play at VLO .. max_speed on the shown frames; speeds, footage (ranges.py), take lengths
      * every cut's musical moment sits within half a frame of a line of the lattice or of a measured attack ("kills"), of a kick's attack ("bass")
    -> (errors, warnings)"""
    errs, warns = [], []
    T = types.SimpleNamespace(**ns)
    errs += preflight.check(T, music=True)
    if errs:
        return errs, warns
    segs, F, R0 = ns["SEGS"], ns["FPB"], ns["R0"]
    vis, HL = ns["vis"], ns["HIT_LEAD"]
    half = 0.5 / F + 1e-9
    SHUT = float(re.search(r"^SHUTTER = ([0-9.]+)", open("render.py", encoding="utf-8").read(), re.M).group(1)) if os.path.isfile("render.py") else 0.65
    prev_kind = None
    E = ns["E"]
    vhi = ns.get("MAX_SPEED") or VHI_OLD
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
        for (k, lv), m in zip(s["kills"], s["hits"]):
            u = uq(m)
            if abs(k - vis(m, HL)) > 1e-9:
                errs.append("take %d: the shot is shown at beat %.9f, not on vis(hit %.9f, HIT_LEAD)" % (i, k, m))
            on_attack = H.near_attack(m, half) is not None                      # the gate's rule: within half a frame of a measured attack
            if not on_attack:
                if m in pins:
                    warns.append("the kill at beat %.6f is pinned by the plan where the music has no measured attack of a kick / snare / hat (%s): its gunshot sounds on the "
                                 "pinned beat; music_pulses.py will list it" % (m, H.describe(u)))
                else:
                    errs.append("the kill at beat %.6f is not on a measured attack (nearest lattice row %.2f: %s)%s" % (
                        m, u / 4.0, H.describe(u), "; an intro kill needs a drum hit (or \"at\" with \"silent\": true)" if s.get("intro") else ""))
            elif not (H.can_kill(u) or s.get("intro") or u in H.adopted):
                warns.append("the kill at beat %.6f sits on a measured attack, but over the gate's window (R0 .. R1) it reads weaker than the drafter admits (%s)" % (m, H.describe(u, ns["PER"])))
            kv = float(s["map"](k)[1])
            if not 0.5 <= kv <= 2.5:
                errs.append("take %d: the shot at beat %g plays at %.2fx: its flash would show late" % (i, k, kv))
            elif not 0.6 <= kv <= max(1.6, ns.get("MAX_SPEED") or 0):
                warns.append("take %d: the shot at beat %g plays at %.2fx (the example prints the same note): look at its stills" % (i, k, kv))
        for (k1, _), (k2, _) in zip(s["kills"], s["kills"][1:]):                  # the kills of one take: speed on the shown frames
            g = round((k2 - k1) * F)
            sp = float(s["map"](k2)[0] - s["map"](k1)[0]) / max(g, 1)
            if sp < VLO - 0.01 or sp > vhi + 0.01:
                errs.append("take %d: its kills at beats %.3f and %.3f are %d frames apart on screen and play at %.2fx (allowed %.1f to %.1f)" % (i, k1, k2, g, sp, VLO, vhi))
        e = E[i]
        if e[0] in ("K", "M"):                           # the enemy is on screen before he dies: the lead, in whole shown frames
            lead = int(round((s["kills"][0][0] - s["r0"]) * F))
            lo, hi = lead_frames - LEAD_WIN, lead_frames + LEAD_WIN
            if lead < lo - 1e-9 or (cuts_on == "kills" and lead > hi + 1e-9):
                errs.append("take %d (%s) has a shown lead of %d frames from its cut to its first shot (lead_frames = %g: %s%d frames); musical moments: cut beat %.9f, first hit beat %.9f = %.3f frames apart" % (
                    i, s["clip"], lead, lead_frames, "%d .. " % lo if cuts_on == "kills" else "at least ", hi if cuts_on == "kills" else lo, s["m0"], s["hits"][0], (s["hits"][0] - s["m0"]) * F))
        up = e[-1].get("upto") if isinstance(e[-1], dict) else None
        if up and s["kills"]:                            # every death shown
            kl = s["kills"][-1][0]
            A = int(round((s["r1"] - kl) * F))
            if A < up:
                errs.append("take %d (%s): %d frames from the last shot to the next cut but the death needs upto = %d" % (i, s["clip"], A, up))
            Kl = float(s["map"](kl)[0])
            got = float(s["map"](s["r1"])[0]) - Kl
            if got < up - 0.75:
                errs.append("take %d (%s K=%d): the take ends %.1f frames after the shot but the death needs upto = %d" % (i, s["clip"], round(Kl), got, up))
        if i:
            m0 = s["m0"]
            u = uq(m0)
            if cuts_on == "bass":
                if H.low.get(u, 0) < CUT_LOW or abs(m0 - H.kick_beat(u)) > half:
                    errs.append("the cut into take %d at beat %.6f is not on the attack of a kick (low %.2f, %s)" % (i, m0, H.low.get(u, 0), H.describe(u)))
            else:
                on_line = any(abs(m0 - round(m0 / st) * st) <= half for st in ladder)
                on_hit = H.near_attack(m0, half) is not None
                if not (on_line or on_hit):
                    errs.append("the cut into take %d: its musical moment, beat %.6f, is %.1f ms from the nearest line of the lattice (%s beat) and on no measured attack" % (
                        i, m0, min(abs(m0 - round(m0 / st) * st) for st in ladder) * ns["PER"] * 1000, " / ".join(fnum(x, 3) for x in ladder)))
            kind = s["tin"]
            if prev_kind == kind and kind[0] != "cut":
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
            snare[j] = H.snare(tk.last_u)
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
            return H.score(takes[j].last_u)   # proportion instead of falling to 3 of 24
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


def tin_quotas(shares, n):
    """the reference's transition shares (hard / whip / zoom / roll) as whole counts over n takes (largest remainder), or None"""
    kinds = ("hard", "whip", "zoom", "roll")
    raw = {k: max(0.0, float(shares.get(k) or 0.0)) for k in kinds}
    tot = sum(raw.values())
    if tot <= 0 or n <= 0:
        return None
    raw = {k: v / tot * n for k, v in raw.items()}
    q = {k: int(math.floor(v)) for k, v in raw.items()}
    for k in sorted(kinds, key=lambda k: -(raw[k] - q[k]))[:n - sum(q.values())]:
        q[k] += 1
    return q


def assign_tins(ent, takes, shares=None):
    """blur-in of every entry: the first fades in; the intro has soft whips only; the body takes:
      * without a reference: a zoom burst on level 2 / 3 and bullet takes, whips alternating direction, a roll about every fourth take, never the same twice
      * with the reference's transition shares: the shares as counts (largest remainder) over the body takes: a zoom burst goes to the high-level takes
        first (the model's rule breaks ties), then each take gets the kind with the most left of its quota, never two zooms in a row; `hard` is a cut
        without blur
    -> (tins, counts of the body kinds)"""
    body = [i for i, e in enumerate(ent) if i > 0 and e["kind"] == "take"]
    quota = tin_quotas(shares, len(body)) if shares else None
    hi = {i: (ent[i]["tk"].lv >= 2 or ent[i]["tk"].kind == "L") for i in body}
    hi_left = sum(hi.values())
    tins, wd, rd, nb = [], 1, 1, 0
    count = collections.Counter()
    for i, e in enumerate(ent):
        if i == 0:
            kind = ("fade", 0.0)
        elif e["kind"] in ("shot", "ikill"):
            kind = ("bwhip", 0.0, wd)
            wd = -wd
        else:
            tk = e["tk"]
            nb += 1
            if quota is None:
                if tk.lv >= 2 or tk.kind == "L":
                    kind = ("bzoom", 0.0)
                elif nb % 4 == 3:
                    kind = ("broll", 0.0, rd)
                    rd = -rd
                else:
                    kind = ("bwhip", 0.0, wd)
                    wd = -wd
            else:
                prev = tins[-1][0] if tins else None
                hi_left -= hi[i]
                kinds = [k for k in ("whip", "roll", "hard", "zoom") if quota[k] > 0]
                allowed = [k for k in kinds if not (k == "zoom" and prev == "bzoom")]
                if hi[i] and "zoom" in allowed:
                    pick = "zoom"
                else:
                    cand = [k for k in allowed if k != "zoom" or quota["zoom"] > hi_left] or allowed or ["whip"]
                    pick = max(cand, key=lambda k: quota.get(k, 0))
                if quota.get(pick, 0) > 0:
                    quota[pick] -= 1
                kind = {"hard": ("cut", 0.0), "zoom": ("bzoom", 0.0), "whip": ("bwhip", 0.0, wd), "roll": ("broll", 0.0, rd)}[pick]
                if pick == "whip":
                    wd = -wd
                elif pick == "roll":
                    rd = -rd
            count[{"cut": "hard", "bzoom": "zoom", "bwhip": "whip", "broll": "roll"}[kind[0]]] += 1
        if i and kind[0] != "cut" and tins[-1][0] == kind[0] == "bzoom":
            kind = ("bwhip", 0.0, wd)
            wd = -wd
        if i and kind[0] != "cut" and tins[-1] == kind:
            kind = ("bwhip", 0.0, -kind[2]) if kind[0] == "bwhip" else ("bwhip", 0.0, wd)
        tins.append(kind)
    return tins, count


def layout_intro_kills(ik, H, R0, t1, bass, T):
    """-> [dict(start, kill, end, ...)]: each intro kill gets an equal stretch of [R0, t1]; its kill sits on a MEASURED attack (a drum hit; "at" with
    "silent": true pins it on the grid where the intro has none) about 0.6 of the way, with INTRO_LEAD_MIN beats of lead-in before it and its death
    (upto frames + a few) after it. The first stretch opens on frame 0 (its cut, shown on frame 0, is at R0 + CUT_LEAD frames); the others start on
    a half-beat line (at its attack when it has one) or, in "bass", on a kick's attack."""
    n, F = len(ik), T.F
    bounds = [r9(R0 + T.cl / F)]
    for j in range(1, n):
        x = R0 + j * (t1 - R0) / n
        if bass:
            ks = [H.kick_beat(u) for u in H.kicks if bounds[-1] + 3.0 <= H.kick_beat(u) <= t1 - 3.0]
            if ks:
                x = min(ks, key=lambda b: abs(b - x))
        else:
            x = H.cutbeat(round(x * 2) / 2.0)
        bounds.append(x)
    bounds.append(t1)
    out, errs = [], []
    for j, k in enumerate(ik):
        s, e = bounds[j], bounds[j + 1]
        lo, hi = s + INTRO_LEAD_MIN, e - (k["upto"] + 4.0 + T.sh) / F
        hits = [u for u in H.att if u % H.step == 0 and lo - 1e-9 <= H.beat(u) <= hi + 1e-9]
        on_hit = True
        if k.get("at") is not None:
            u = uq(k["at"])
            if u in H.att and abs(H.beat(u) - k["at"]) <= 0.25 and lo - 1e-9 <= H.beat(u) <= hi + 1e-9:
                pool = [u]
            elif k.get("silent") and lo - 1e-9 <= k["at"] <= hi + 1e-9:
                pool, on_hit = [u], False
            else:
                pool = []
                errs.append("intro kill #%d (%s K=%d): \"at\": %g has no measured attack there (%s) or lies outside its stretch (the kill must fall in beats %s .. %s); the stretch has "
                            "attacks at %s. Pin one of them, or add \"silent\": true to sound it on the grid" % (
                                j + 1, k["clip"], k["K"], k["at"], H.describe(u), fnum(lo, 1), fnum(hi, 1), " ".join(fnum(H.beat(x), 2) for x in sorted(hits, key=H.beat)[:10]) or "none"))
                continue
        else:
            pool = hits
        if not pool:
            errs.append("intro kill #%d (%s K=%d): its stretch of the intro is beats %s .. %s (%.1f beats); it needs %g beats of lead-in and %d frames (%.2f beats) of death after "
                        "the shot, so its kill must fall in beats %s .. %s, and no drum attack (kick, snare, hat) is measured there. A longer intro (\"beats\"), fewer intro kills, "
                        "a smaller \"upto\", or pin the kill with \"at\" and \"silent\": true (it then sounds on the grid, with nothing in the music)" % (
                            j + 1, k["clip"], k["K"], fnum(s, 1), fnum(e, 1), e - s, INTRO_LEAD_MIN, k["upto"] + 4, (k["upto"] + 4.0) / F, fnum(lo, 1), fnum(hi, 1)))
            continue
        tgt = s + 0.6 * (e - s)
        u = min(pool, key=lambda x: abs(H.beat(x) - tgt) + (0.0 if H.score(x) >= STRONG else 1.5 if H.can_kill(x) else 3.0))
        out.append(dict(k, start=s, kill=H.beat(u) if on_hit else r9(k["at"]), kill_u=u, end=e, on_hit=on_hit))
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
    raw = {u // 2: v for u, v in H.raw.items() if u % 2 == 0}      # the thin-out is read on half beats (the solver's unit is the quarter beat)
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
        lands = [x / 2.0 for x in range(e + 1, e + 2 + int(THIN_NEXT * 2)) if 2 * x in H.att and H.score(2 * x) >= STRONG]
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
                    fnum(s["a"]), fnum(s["e"]), round(s["pct"]), round(100 * s["before"]), H.describe(uq(h)).split()[0], fnum(h)))))
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


# ------------------------------------------------------------------------------------------------ the reference: gaps, slow motion
def ref_gaps(takes, T, step, hist, vhi, seed):
    """-> (lprefs, raises): lprefs[j] = the preferred length in beats of take j (its cut to the next cut), or None where the reference does not decide it
    (a bullet-time take, the last take). The reference's cut_gaps_steps histogram (gap in lattice steps -> count) is drawn from deterministically
    (stratified inverse CDF, shuffled by the plan's hash: the shares of the histogram hold exactly) and each draw is RAISED to the take's physical
    minimum: the lead, the shots' real-time spacing and the death shown. raises = one sentence per raised take."""
    keys = sorted((int(k), float(v)) for k, v in hist.items() if float(v) > 0)
    n = len(takes)
    if not keys or n < 2:
        return None, []
    steps, w = [k for k, _ in keys], np.array([v for _, v in keys])
    cum = np.cumsum(w) / w.sum()
    draws = [steps[min(int(np.searchsorted(cum, (i + 0.5) / (n - 1))), len(steps) - 1)] for i in range(n - 1)]
    random.Random(seed).shuffle(draws)
    F = T.F
    out, raises = [], []
    for j, tk in enumerate(takes):
        if j == n - 1 or tk.kind == "L":
            out.append(None)
            continue
        want = draws[j] * step
        spacing = (tk.Ks[-1] - tk.Ks[0]) / vhi
        need = (T.lead_frames + spacing + tk.upto + T.sh) / F
        if want < need:
            raises.append("take %d: the reference asks %d step%s = %.2f beats; the minimum is %.2f beats (%g frames of lead%s + %d frames of death)" % (
                j + 1, draws[j], "" if draws[j] == 1 else "s", want, need, T.lead_frames, (" + %.0f frames between its kills" % spacing) if spacing else "", tk.upto))
        out.append(max(want, need))
    return out, raises


def hits_text(H, per):
    return "%d kicks (low >= %.1f), %d rows that can carry a kill on the %s lattice" % (len(H.kicks), KICK, len(H.kills), "half-beat" if H.sub == 2 else "quarter-beat")


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
    if "SYNC = 2" not in tpl or "def vis(" not in tpl:
        die("%s is not a SYNC = 2 template (no `SYNC = 2` / vis()): take scripts/refstyle/timeline_ref_example.py of this skill version" % args.example)
    if os.path.exists(args.out) and not args.force:
        cur = open(args.out, encoding="utf-8").read()
        if cur != tpl and not untouched_draft(cur):
            die("%s exists and is neither the untouched example nor an untouched draft (it holds your edits): pick another name with -o, "
                "or --force to replace it" % args.out, "will not overwrite your timeline")
    ref = P["ref"]
    if ref is not None:
        ref.reset()
    T = Tempo(P["bpm"], P["max_speed"], P["lead_frames"], P["cut_lead"], P["hit_lead"], P["luma_s"], P["black_s"])
    F, per = T.F, T.per
    bass = P["cuts_on"] == "bass"
    ladder = P["ladder"]
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
    hitf = lambda t: (t - P["beat0"]) / per - M0
    m = beat_hits.decode(P["music"])
    dur = len(m) / beat_hits.SR
    rmax = math.floor(((dur - P["beat0"]) / per - M0 - 0.1) * 10) / 10
    vhi = P["max_speed"] if P["max_speed"] is not None else VHI_OLD
    sub_state = {"sub": P["hit_grid"], "why": 'plan.json "hit_grid"' if P["hit_grid"] else None}
    meas_cache = {}

    def hits_for(r0, r1, raw=False):
        """the hits of beats r0 .. r1 (measure_t on the quarter-beat lattice) as a Hits on the kill lattice of this song (half beats, or quarter beats
        when the strong hits are syncopated)"""
        r0 = math.floor(r0 / 8.0) * 8.0         # the window starts on a multiple of 8 beats: the planning pass and the final pass measure THE SAME window (the strengths and
                                                # the attack picked for a row depend on it by a few ms; a start that follows R0 would move them between the two)
        key = (round(r0, 6), round(r1, 6))
        if key not in meas_cache:
            meas_cache.clear()
            meas_cache[key] = beat_hits.measure_t(m, P["bpm"], P["beat0"], M0, r0, r1, False, 4)
        rows, att = meas_cache[key]
        rr = beat_hits.measure_t(m, P["bpm"], P["beat0"], M0, r0, r1, True, 4)[0] if raw else None
        if sub_state["sub"] is None:
            share, ns_ = strong_odd_share(Hits(rows, att, None, 4, F, hitf))
            sub_state["sub"] = 4 if ns_ >= 6 and share >= STRONG_ODD else 2
            sub_state["why"] = "%d of %d strong kicks / snares (%.0f %%) sit on a quarter that is not a half beat%s" % (
                round(share * ns_), ns_, share * 100, ": syncopated, kills use the quarter-beat lattice" if sub_state["sub"] == 4 else ": kills use the half-beat lattice")
        H = Hits(rows, att, rr, sub_state["sub"], F, hitf)
        if ib is not None:                                   # the drop kill: the attack nearest the drop within 50 ms, whatever its strength
            H.adopt_attack(4 * D, 0.05 / per)
        return H

    def drift_msg(r0, r1):
        """a sentence when the strong hits drift against the BPM's grid (every attack filed on its nearest quarter-beat row: a drifting song's late hits too)"""
        rows_w, att_w = beat_hits.measure_t(m, P["bpm"], P["beat0"], M0, r0 - T.scan_pre, r1, False, 4, 1.0)
        return drift_problem(rows_w, att_w, hitf, per, P["bpm"], r0, r1)

    # ---- an M take whose later kill has no hit at or after its real-time distance cannot be one take: it is split (a cut), never fast-forwarded
    H0 = hits_for(-T.scan_pre, min(rmax, P["length"] / per * (1 + P["length_tolerance"])))
    if ib is not None and 4 * D not in H0.att:
        near = H0.near_attack(float(D), 0.5)
        die("the drop kill lands on the drop (track beat %d = beat %g, %.3f s) but the song has no measured drum attack on that beat (%s%s): check drop_beat, BPM and BEAT0 "
            "with music_grid.py / music_tempo.py (the drop is where a kick or crash arrives)" % (
                P["drop_beat"], D, bt(D), H0.describe(4 * D, per),
                "; the nearest attack is %.0f ms away" % (abs(near - D) * per * 1000) if near is not None else "; no attack within half a beat"), "cannot place the drop kill")
    takes, split_notes = split_unplaceable(takes, P, T, H0, D, bass)
    join_notes += split_notes
    n = len(takes)
    ib = next((j for j, t in enumerate(takes) if t.lkind == "drop"), None)
    E = []
    # ---- footage before every take's first kill and the plan's own spacing
    for j, tk in enumerate(takes):
        if tk.kind != "L":
            lead = T.pre_src(T.lead_frames + LEAD_WIN + 1.0, tk.pre_n)
            if tk.Ks[0] - lead < MARGIN:
                E.append("take %d (%s K=%d, a clip of %d frames = %.1f s) has only %d frames of footage before its first kill: the take enters at "
                         "real time, so it starts up to %.1f source frames before the shot and the shutter needs %d more; use a kill with at least %d "
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
    if ref is not None and ref.a:
        isteps = ref.a.get("intro_steps")
        if not has_intro:
            ref.skipped("intro", "the plan has no intro: the video starts on its first take")
        elif intro_beats is not None:
            ref.skipped("intro", 'plan.json gives intro "beats": %g (the plan wins)' % intro_beats)
        elif isinstance(isteps, (int, float)) and isteps == 0:
            ref.skipped("intro", "the reference starts on its first cut (intro_steps 0) but the plan has an intro: the plan's intro length stays (a fifth of the video)")
        elif isinstance(isteps, (int, float)) and P["step"]:
            ib_ref = float(min(24, max(4, int(round(isteps * P["step"] / 4.0)) * 4)))
            intro_beats = ib_ref
            ref.took("intro", "%g steps of %g beat = %.1f beats, rounded to %g beats (whole bars)" % (isteps, P["step"], isteps * P["step"], ib_ref))
        else:
            ref.skipped("intro", "the reference gave no usable intro length (intro_steps %r, lattice step %r): a fifth of the video (the model)" % (isteps, P["step"]))
    if has_intro and intro_beats is None:
        intro_beats = float(min(16, max(4, int(round(L_t * 0.2 / 2.0) * 2))))
    if has_intro and intro_kills:
        need = len(intro_kills) * (INTRO_LEAD_MIN + (max(k["upto"] for k in intro_kills) + 4) / F + 0.4) + 4.0
        if intro_beats < need - 1e-9:
            intro_beats = float(max(intro_beats, 2 * math.ceil(need / 2.0)))
    I = float(intro_beats) if has_intro else 0.0
    tol = P["length_tolerance"]
    notes = list(join_notes)
    if intro_beats is not None and not has_intro:
        notes.append('"intro" has no shots or kills: the video starts on its first take')

    def r0_for(head0, t_first):
        """R0 EXACT: with an intro it lies I beats before the first landing (a beat line); without one the first cut is shown on frame 0, so R0 is the
        first cut's musical moment CUT_LEAD frames earlier"""
        return r9(head0 - I) if has_intro else r9(t_first - T.cl / F)

    def make_lprefs(tks):
        """the reference's cut-gap histogram -> a preferred length per take (ref_gaps)"""
        hist = (ref.a.get("cut_gaps_steps") if ref is not None and ref.a else None)
        if not hist or not P["step"]:
            return None, []
        return ref_gaps(tks, T, P["step"], hist, vhi, int(hashlib.sha1(open(args.plan, "rb").read()).hexdigest()[:8], 16))

    def plan_with(H, R1_lo, R1_hi, lprefs):
        S = Solver(P, T, takes, H, D, bass, lprefs, ladder)
        S.R1_lo, S.R1_hi = R1_lo, R1_hi
        cands = []
        if ib == 0:
            if 4 * D not in H.att:
                die("the drop kill is the first take and lands on the drop (track beat %d = beat %g) but the song has no measured drum attack on that beat (%s): "
                    "check drop_beat, BPM and BEAT0 (music_grid.py)" % (P["drop_beat"], D, H.describe(4 * D, per)))
            if bass and has_intro:                 # the cut into the bullet take is a transition: it needs a kick
                cands = [u for u in H.kicks if BULLET[0] <= D - H.kick_beat(u) <= BULLET[1]]
                cands.sort(key=lambda u: abs((D - H.kick_beat(u)) - BULLET[2]))
            else:
                cands = [uq(D - BULLET[2])]
            cands = [u for u in cands if S.pre_ok(takes[0], S.start_of(0, u, -1e9)[0] if S.start_of(0, u, -1e9) else 1e9, float(H.beat(4 * D)))]
        else:
            cands = [0]
        return H, S, cands

    def run(H, R1_lo, R1_hi, lprefs):
        H, S, cands = plan_with(H, R1_lo, R1_hi, lprefs)
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
                    return None, ["the first kill lands on beat 0 (track beat %d) but the song has no measured attack of a kick, snare or loud hat there: %s. Check BPM / BEAT0 with "
                                  "music_grid.py, or pick another start_beat (a kick)" % (M0, H.describe(0, per))]
            s0 = S.start_of(0, u0, -1e9)
            if s0 is None:
                return None, ["the first kill at beat %s needs a cut before it: %s. Pick start_beat so that %s, or use \"cuts_on\": \"%s\"" % (
                    fnum(H.beat(u0) if ib != 0 else 0.0, 2),
                    ("with CUTS_ON \"bass\" the attack of a kick %.0f to %.0f frames (%.2f to %.2f beat) earlier, and the song has none there (kicks at %s)" % (
                        T.lead_frames - LEAD_WIN, T.lead_frames + LEAD_WIN + BASS_LEAD_EXTRA * F, T.d_lo, T.d_hi + BASS_LEAD_EXTRA,
                        " ".join(fnum(H.kick_beat(c), 2) for c in H.kicks if -4 < H.kick_beat(c) < 1) or "none") if bass else
                     "no line of the %s beat lattice puts the first hit %g to %g frames after the cut (the hit is at beat %s)" % (
                        " / ".join(fnum(x, 3) for x in ladder), T.lead_frames - LEAD_WIN, T.lead_frames + LEAD_WIN, fnum(H.beat(u0), 3))),
                    "a kick precedes the first hit" if bass else "the first hit is %g to %g frames after a line" % (T.lead_frames - LEAD_WIN, T.lead_frames + LEAD_WIN),
                    "kills" if bass else "bass")]
            head0 = u0 / 4.0 if ib == 0 else 0.0
            S.R1_t = r0_for(head0, s0[0]) + L_t
            res, reason = S.solve(u0)
            if res is None:
                why.append(reason)
                fail_j.append(S.fail_j if S.fail_j is not None else 0)
                continue
            if best is None or res[0] < best[0][0]:
                best = (res, u0, r0_for(head0, s0[0]))
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
        H2, S2, cands = plan_with(hits_for(R0_guess - T.scan_pre, wide), -1e9, wide, None)
        S2.explore = True
        spans = [r for r in (S2.solve(u0)[0] for u0 in cands) if r]
        if not spans:
            return None
        return (min(s[0] for s in spans) - R0_guess) * per, (max(s[1] for s in spans) - R0_guess) * per

    R0_init = R0_guess
    fail_j = []                                  # index of the take that no cut could follow (Solver.solve), for the M splits below
    drift_done = False
    while True:
        window, chosen, fixed, R0_guess = R1_hi, None, None, R0_init
        lprefs, raises = make_lprefs(takes)
        for attempt in range(5):
            H = hits_for(R0_guess - T.scan_pre, window)
            if not drift_done:
                drift_done = True
                dp = drift_msg(R0_guess, window)
                if dp:
                    die(dp, "the grid does not fit the music (systematic drift)")
            fail_j.clear()
            best, why = run(H, fixed if fixed else R1_lo, fixed if fixed else R1_hi, lprefs)
            if best is None:
                break
            (res, u0, R0) = best
            cost, chain, R1, t_first = res
            if abs(R1 - window) < 1e-9 and abs(R0 - R0_guess) < 0.02:
                chosen = (H, chain, R1, R0, t_first)
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
            if ref is not None and ref.a and "ending" in ref.used and (P["luma_s"], P["black_s"]) != (LUMA_S, BLACK_S):
                ref.revert("ending", "the reference's ending (%.2f s fade + %.2f s black) leaves these takes no room in the %.0f s asked (the calm last take needs %.1f s with it, "
                           "%.1f s with the model's): the model's %.2f s + %.2f s; ask for more seconds to follow it" % (
                               P["luma_s"], P["black_s"], P["length"], (TAIL_PIC + P["luma_s"] + P["black_s"]), TAIL_PIC + LUMA_S + BLACK_S, LUMA_S, BLACK_S))
                P["luma_s"], P["black_s"] = LUMA_S, BLACK_S
                return draft(args, P, kills, find)
            report_fail(P, T, takes, H, ib, bass, why, tol, probe, R1_hi, per, drift_msg(R0_guess, window))
        die("the measured hits changed between passes; run again with a slightly different length")
    Hp, chain, R1, R0, t_first = chosen
    if ref is not None and ref.a:
        if lprefs is not None:
            ref.took("cut_gaps", "each take's preferred length drawn from the reference's cut-gap histogram (%d steps of %g beat), raised to the physical minimum for %d of %d takes" % (
                len(ref.a["cut_gaps_steps"]), P["step"], len(raises), sum(1 for x in lprefs if x is not None)))
        else:
            ref.skipped("cut_gaps", "the reference gave no cut-gap histogram (or no lattice step): the even spread toward the length asked (the model)")
    # the hits again over exactly the window the gate measures (R0 .. R1): every beat below is read from this measure
    H = hits_for(math.floor(R0 * 4) / 4.0 - 0.25, R1, raw=True)      # a quarter beat before R0: the lattice row of a cut's kick / attack may lie just before R0

    # ---- placement -> entries: musical beats (measured attacks), cuts on lattice lines / attacks
    for j, tk in enumerate(takes):
        c = chain[j]
        tk.head = H.beat(c["u"]) if tk.lkind != "drop" else H.beat(4 * D)
        tk.first = H.beat(4 * D) if tk.lkind == "drop" else H.beat(c["u"])      # the take's first kill: the attack's musical beat (9 decimals)
        tk.first_u = 4 * D if tk.lkind == "drop" else c["u"]
        tk.tails = [H.beat(uq(b)) for b in c["tails"]]
        tk.last = ([tk.first] + tk.tails)[-1]
        tk.last_u = uq(tk.last)
    # the cuts are placed again on THIS measure (the set of attacks, and so the attack a line snaps to, differs a few ms from the planning window's), with the
    # same rules and the death of the take before it taken from the final kill beats
    Sf = Solver(P, T, takes, H, D, bass, None, ladder)
    for j, tk in enumerate(takes):
        c = chain[j]
        dprev = -1e9 if j == 0 else takes[j - 1].last + T.death_b(takes[j - 1].upto)
        st = Sf.start_of(j, c["u"], dprev)
        if st is None:                                  # keep the planned line: verify() reports the rule it breaks on this measure
            how = c["start"][1]
            st = (H.kick_beat(how[1]) if how[0] == "kick" else H.cutbeat(how[1]), how)
        how = st[1]
        tk.start = st[0]                                # the cut's musical moment
        tk.line = how[1] if how[0] == "line" else None
        if tk.kind != "L":                              # the entry carries lb = first hit - cut moment (9 decimals); the template recomputes the moment from it
            tk.lb = r9(tk.first - tk.start)
            tk.start = tk.first - tk.lb
        else:
            tk.start = r9(tk.start)
    R0 = r0_for((chain[0]["u"] / 4.0 if ib == 0 else 0.0), takes[0].start)
    for j, tk in enumerate(takes):
        tk.end = takes[j + 1].start if j + 1 < n else R1
    best_snare = assign_levels(takes, H, ib, n)
    nf = lambda r: int(math.floor((r - R0) * T.F + 0.5))

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
        starts = [r9(R0 + T.cl / F)]                       # the opening cut is shown on frame 0
        if nsh > 1:
            ideal = [R0 + j * (t1 - R0) / nsh for j in range(1, nsh)]
            for x in ideal:
                if bass:
                    ks = [H.kick_beat(u) for u in H.kicks if R0 + 1.5 <= H.kick_beat(u) <= t1 - 1.5 and H.kick_beat(u) > starts[-1] + 1.5]
                    if ks:
                        starts.append(min(ks, key=lambda b: abs(b - x)))
                else:
                    starts.append(H.cutbeat(round(x * 2) / 2.0))
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
    shares = (ref.a.get("transitions") if ref is not None and ref.a else None)
    tins, tcount = assign_tins(ent, takes, shares)
    if ref is not None and ref.a:
        if shares and any(isinstance(shares.get(k), (int, float)) for k in ("hard", "whip", "zoom", "roll")):
            nbody = sum(tcount.values())
            ref.took("transitions", "body takes %s of %d (reference: %s); a zoom burst goes to the level 2 / 3 and bullet takes first" % (
                ", ".join("%d %s" % (tcount.get(k, 0), k) for k in ("hard", "whip", "zoom", "roll")), nbody,
                ", ".join("%.0f %% %s" % (100 * float(shares.get(k) or 0), k) for k in ("hard", "whip", "zoom", "roll"))) +
                ("; its flash / dip transitions (%s) are not drafted: their shares went to the four kinds above" % ", ".join(
                    "%.0f %% %s" % (100 * float(shares[k]), k) for k in ("flash", "dip") if isinstance(shares.get(k), (int, float)) and shares[k] > 0)
                 if any(isinstance(shares.get(k), (int, float)) and shares[k] > 0 for k in ("flash", "dip")) else ""))
        else:
            ref.skipped("transitions", "the reference gave no shares: the model's pattern (zoom on level 2 / 3, whips alternating, a roll about every fourth take)")
    SV = Solver(P, T, takes, H, D, bass, None, ladder)
    pins = {tk.first for tk in takes if tk.at[0] is not None and tk.first_u not in H.att}
    pins |= {b for tk in takes for a_, b in zip(tk.at[1:], tk.tails) if a_ is not None and uq(b) not in H.att}
    pins |= {ik["kill"] for ik in intro if ik["kind"] == "ikill" and not ik["on_hit"]}

    def assemble(h_slow):
        """-> dict(src, ns, lines, notes): the draft's source for a fall() hold of h_slow frames (the reference's slow share is searched over it)"""
        lines, risers, booms, anotes = [], [], [], []
        for i, e in enumerate(ent):
            tin = tins[i]
            if e["kind"] == "shot":
                o = [("shutter", fnum(e["shutter"], 1)), ("tin", tin_text(tin)), ("intro", "True"), ("mute", "True"), ("push", "0.0")]
                nxt_start = ent[i + 1]["start"] if ent[i + 1]["kind"] in ("shot", "ikill") else t1
                lines.append("    # intro shot: %.2fx slow motion over %.1f beats at full frame" % (e["v"], nxt_start - e["start"]))
                lines.append('    ("shot", %s, "%s", %d, %d, %s),' % (b9(e["start"]), e["clip"], e["a"], e["b"], opts_text(o)))
                continue
            if e["kind"] == "ikill":
                o = [("intro", "True"), ("push", "0.0"), ("shutter", "2.2"), ("tin", tin_text(tin)), ("upto", str(e["upto"])), ("h", str(INTRO_H))]
                lines.append("    # intro kill: bullet time at %.2fx over %.1f beats (%s) into the kill on the attack at beat %s (%s), then its death (upto %d frames)" % (
                    e["v"], e["kill"] - e["start"], "from the opening" if i == 0 else "after the take before", fnum(e["kill"], 6), H.describe(e["kill_u"], per) if e["on_hit"] else
                    "NO drum there: pinned on the grid by the plan", e["upto"]))
                lines.append('    ("L", %s, [%s], %s, "%s", %d, %s),' % (b9(e["start"]), lead_text(e["lead"], e["start"]), b9(e["kill"]), e["clip"], e["K"], opts_text(o)))
                continue
            tk, j = e["tk"], e["j"]
            final = j == n - 1
            Lt = tk.end - tk.start
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
                if h_slow != H_DEFAULT:
                    o.append(("h", str(int(max(1, min(h_slow, tk.upto - 1))))))
                if tk.kind == "L":
                    o.append(("push", "0.05"))
            if tk.kind != "L":
                o.append(("lb", b9(tk.lb)))
            if tk.kind == "L":
                o.append(("white", "flash(%s, 0.36, 8.0)" % b9(tk.start)))
            o.append(("tin", tin_text(tin)))
            if tk.mute:
                o.append(("mute", "True"))
            cut_on = H.describe(tk.first_u, per)
            win = (tk.end - tk.last) * F
            rate = (tk.upto - 8.0) / max(1.0, win - 8.0)
            tail = ("last take, calm; slow motion to the luma fade; " if final else
                    ("death upto %d frames in %.0f: slow %.2fx; " % (tk.upto, win, rate) if rate >= 0.15 else
                     "death upto %d frames in %.0f: slow 0.15x until the body is down, then back to real time; " % (tk.upto, win)) if win > tk.upto
                    else "death upto %d in %.0f frames: real time; " % (tk.upto, win))
            where = ("on the kick at beat %s" % b9(tk.start) if bass and tk.kind != "L" else
                     "on the %s beat line at beat %s%s" % (fnum(next((s_ for s_ in ladder if abs(tk.line / s_ - round(tk.line / s_)) < 1e-6), ladder[-1]), 3), fnum(tk.start, 6),
                                                              " (attack %+.1f ms)" % ((tk.start - tk.line) * per * 1000) if abs(tk.start - tk.line) > 1e-9 else "") if tk.line is not None else
                     "at beat %s" % fnum(tk.start, 6))
            if tk.kind == "L":
                ld = SV.lead_anchors(tk, tk.start, tk.first)
                if tk.lkind == "drop":
                    expl = ("bullet time into the kill on the drop (beat %s, %s): lead-in from beat %s (%s), %.1f beats at 0.5x .. 0.2x, a white flash-in, %s; %s%.1f beats long" % (
                        fnum(tk.first, 6), H.describe(4 * D, per), fnum(tk.start, 3), "on a kick" if bass else "on a beat line", tk.first - tk.start,
                        "an 8-frame ease up to real time, the shot at real time" if P["max_speed"] is not None else "then the shot at real time", tail, Lt))
                    risers.append(("drop", max(tk.start, R0 + 0.2), tk.first))
                    booms.append((tk.first, 0.26))
                else:
                    auto = tk.kills[0].get("auto_why")
                    expl = ("%s (%s): %.1f beats of lead-in at 0.5x .. 0.4x from beat %s (a 1/4-beat line), a white flash-in, a riser, a boom; %s%.1f beats long" % (
                        "bullet time (auto): " + auto if auto else "bullet time into the kill on the strong hit at beat %s" % fnum(tk.first, 6), cut_on, tk.first - tk.start, fnum(tk.start, 3), tail, Lt))
                    risers.append(("hit", tk.start, tk.first))
                    booms.append((tk.first, 0.20))
                    nk = sum(1 for x in H.kicks if tk.start <= H.kick_beat(x) < tk.first)
                    if auto:
                        anotes.append("take %d: bullet time added by itself, %s (\"auto_bullet\": false in the plan turns it off; %d kick(s) inside its %.1f-beat lead-in)" % (
                            j + 1, auto, nk, tk.first - tk.start))
                    elif nk >= 3:
                        anotes.append("take %d (bullet \"hit\" at beat %s): the drums do not thin out here (%d kicks inside its %.1f-beat lead-in); the model puts this where the "
                                      "kick and snare weaken" % (j + 1, fnum(tk.first, 3), nk, tk.first - tk.start))
                lines.append("    # take %d: %s" % (j + 1, expl))
                lines.append('    ("L", %s, [%s], %s, "%s", %d, %s),' % (b9(tk.start), lead_text(ld, tk.start), b9(tk.first), tk.clip, tk.Ks[0], opts_text(o)))
            elif tk.kind == "K":
                shown = nf(tk.first) - T.hl - (nf(tk.start) - T.cl) if i or has_intro else nf(tk.first) - T.hl
                lines.append("    # take %d: cut %s (%s), shown lead %d frames, shot on the attack at beat %s (%s)%s; %s%.1f beats long" % (
                    j + 1, where, "musical lead %.1f frames" % (tk.lb * F), shown, fnum(tk.first, 6), cut_on, " (best snare: level 3)" if j == best_snare else "", tail, Lt))
                lines.append('    ("K", %s, "%s", %d, %s),' % (b9(tk.first), tk.clip, tk.Ks[0], opts_text(o)))
            else:
                bs = [tk.first] + tk.tails
                lines.append("    # take %d: cut %s (musical lead %.1f frames); kills on %s; %s%.1f beats long" % (
                    j + 1, where, tk.lb * F, ", ".join("%s (%s)" % (fnum(b, 6), H.describe(uq(b), per)) for b in bs), tail, Lt))
                lines.append('    ("M", [%s], "%s", %s),' % (", ".join("(%s, %d)" % (b9(b), K) for b, K in zip(bs, tk.Ks)), tk.clip, opts_text(o)))
            if j == best_snare:
                booms.append((tk.last, 0.18))
            if final:
                booms.append((tk.last, 0.26))
        entries_txt = "E = [\n" + "\n".join(lines) + "\n]\n"

        # ---- music block, sound, effects, words
        music_blk = music_block(P, bpm_text(P), M0, D, F, R0, R1, takes[-1].last)
        music_blk += "LOOK = %r                          # edit options (SKILL.md, \"Edit options\"; look.py): %s\n" % (
            P["look"], "the reference's measured look" if "look" in (ref.used if ref else ()) else "the model edit's look")
        rs = []
        if ib != 0 and I >= 4.5:
            rs.append("dict(a=%s, b=%s, f0=350, f1=7000, curve=1.0, width=1.1, power=2.3, gain=0.10, cut=0.012, seed=1)" % (b9(max(-4.0, R0 + 0.2)), b9(takes[0].first)))
        for kind, a, b in risers:
            if kind == "drop":
                rs.append("dict(a=%s, b=%s, f0=350, f1=7500, curve=1.1, width=1.1, power=2.2, gain=0.09, cut=0.012, seed=1)" % (b9(a), b9(b)))
            else:
                rs.append("dict(a=%s, b=%s, f0=300, f1=7000, curve=1.2, width=1.0, power=2.3, gain=0.08, cut=0.012, seed=3)" % (b9(a), b9(b)))
        sound_blk = "SWEEP = None\nRISERS = [%s]\n" % (",\n          ".join(rs))
        kill_beats = [k for tk in takes for k in [tk.first] + tk.tails]
        luma0 = R1 - (P["black_s"] + P["luma_s"]) / per
        bumps = pick_bumps(H, kill_beats, R0, luma0, takes[-1].start, (R1 - R0) * per)
        fx = ["IMPACT = dict(frames=6, blur=(0.035, 0.06, 0.09), split=(5, 9, 14), rays=(False, True, True), invert=(False, False, True))",
              "ACC = {1: (0.020, 4.0, 0.32), 2: (0.032, 7.0, 0.50), 3: (0.045, 10.0, 0.85)}   # kill accents per level: punch / shake px / exposure pop"]
        bl = ["(%s, %s)" % (b9(b), fnum(s, 2, True)) for b, s in bumps]
        fx.append("BUMPS = [%s]      # a light pulse and a 1.2 %% nudge on the strong hits that carry no kill (%d), each on its attack" % (",\n         ".join(", ".join(bl[x:x + 4]) for x in range(0, len(bl), 4)), len(bumps)))
        if has_intro:
            fx.append("LUMA_IN = (%s, %s)             # the opening reveals the bright areas first (ends on a frame)" % (b9(R0), b9(R0 + round(0.35 * F) / F)))
        fx.append("BOOMS = [%s]" % ", ".join("dict(r=%s, gain=%s)" % (b9(b), fnum(g, 2, True)) for b, g in sorted(booms)))
        fx += ["KILL_THUMP = 0.18                   # a sub thump under every kill", "WHOOSH_BLUR = 0.07                  # a swish on every blur-in cut",
               "GAME_LEVEL = 0.95                   # the gunshots: a little louder than the house mix", "HEADROOM = 0.5                      # mix.wav level (gunshots, thumps and booms are hot)",
               "FADE_IN = 0.45                      # seconds of fade-in of the song"]
        fx_blk = "\n".join(fx) + "\n"
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
               "and tweaked, not trusted blindly. Reference style with the model edit's patterns: every take cut about %g frames before its first shot (on a lattice line),\n"
               "real time to the shot, the death shown in slow motion before the next cut, bullet time into the drop, a luma fade at the end. Every kill sits on the\n"
               "measured attack of its drum hit; every picture event is on an exact frame (SYNC = 2). Timeline beat 0 = beat %d of the track.\n"
               'Source positions are frame indices of the clips (exact, 60 per second)."""') % (
            hashlib.sha1(open(args.plan, "rb").read()).hexdigest()[:8], len(kills) + len(intro_kills), (R1 - R0) * per, P["cuts_on"], P["lead_frames"], M0)
        src = re.sub(r'\A""".*?"""', lambda mm: doc, tpl, count=1, flags=re.S)
        for name, blk in (("music", music_blk), ("sound", sound_blk), ("fx", fx_blk), ("cut", cut_block(P)), ("post", post_block(P)), ("entries", entries_txt), ("words", words_blk)):
            src = replace_block(src, name, blk)
        return dict(src=src, ns=exec_timeline(src), lines=lines, notes=anotes)

    # ---- the reference's slow-motion share: fall()'s real-time hold h (more real time before the death slow-down = fewer slow frames), FALL_MIN = its rate
    res = assemble(H_DEFAULT)
    slow = (ref.a.get("slow") if ref is not None and ref.a else None) or {}
    tgt = slow.get("share")
    if ref is not None and ref.a:
        if isinstance(tgt, (int, float)) and 0 <= tgt <= 1:
            tried = [(H_DEFAULT, body_slow_share(res["ns"]), res)]
            for hs in (1, 2, 4, 6, 10, 12, 14, 16, 18, 20, 24, 28, 34, 40, 60, 90):
                r_ = assemble(hs)
                if preflight.speed_problems(types.SimpleNamespace(**r_["ns"])):       # a hold whose ease overshoots MAX_SPEED in some take is no candidate
                    continue
                tried.append((hs, body_slow_share(r_["ns"]), r_))
                if tried[-1][1] < tgt * 0.5:
                    break
            hs, sh_, res = min(tried, key=lambda x: (abs(x[1] - tgt), x[0]))
            txt = "slow motion (frames below %.1fx) in the body: %.0f %% against the reference's %.0f %%, with fall() holding real time for %d frames after each shot%s" % (
                SLOW_BELOW, sh_ * 100, tgt * 100, hs, ", slowest rate %.3f (the reference's)" % P["fall_min"] if P.get("fall_min") else "")
            if abs(sh_ - tgt) <= 0.25 * tgt + 1e-9:
                ref.took("slow", txt)
            else:
                floor_ = min(x[1] for x in tried)
                ref.skipped("slow", txt + ": %s" % (
                    "the death of every enemy must be shown to K + upto (the standing rule), which keeps at least %.0f %% of the frames slow in these takes" % (floor_ * 100) if sh_ > tgt else
                    "even the shortest real-time hold leaves only %.0f %% slow (the plan's takes are short)" % (sh_ * 100)))
        else:
            ref.skipped("slow", "the reference gave no slow-motion share: the model's fall() (hold 8 frames%s)" % (", FALL_MIN %.3f" % P["fall_min"] if P.get("fall_min") else ""))
    ns, src = res["ns"], res["src"]
    notes += res["notes"]
    lines = res["lines"]

    # ---- run the built file before writing it
    errs, warns = verify(ns, H, P["cuts_on"], float(P["lead_frames"]), pins, ladder)
    seconds = (R1 - R0) * per
    # the reference's rates against the draft's
    if ref is not None and ref.a:
        ck = len(ns["SEGS"]) - 1
        kp = (ref.a.get("kills") or {}).get("per_s")
        if isinstance(kp, (int, float)) and kp > 0:
            mine = len(ns["KILLS"]) / seconds
            (ref.took if abs(mine - kp) <= 0.25 * kp else ref.skipped)("kills", "%.2f kills per second against the reference's %.2f%s" % (
                mine, kp, "" if abs(mine - kp) <= 0.25 * kp else " (outside +-25 %%: %s)" % ("add kills or ask for fewer seconds" if mine < kp else "use fewer kills or ask for more seconds")))
        cr = ref.a.get("cut_rate_per_s")
        if isinstance(cr, (int, float)) and cr > 0:
            mine = ck / seconds
            minlen = (T.lead_frames + min(tk.upto for tk in takes) + T.sh) / 60.0
            if abs(mine - cr) <= 0.25 * cr:
                ref.took("cut_rate", "%.2f cuts per second against the reference's %.2f" % (mine, cr))
            else:
                ref.skipped("cut_rate", "%.2f cuts per second against the reference's %.2f: every take needs a %g-frame lead and its enemy's death shown (at least %.2f s = %.2f cuts per second at most), "
                            "and no take without a kill" % (mine, cr, T.lead_frames, minlen, 1.0 / minlen))
    if ref is not None and not ref.off and not ref.used:
        if True:
            errs.append("ref_notes.json (%s) exists but none of its traits was used: %s. A reference that changes nothing is not followed: run ref_analyze.py again (the "
                        "\"adopt\" block), or say so with \"ref_notes\": false in plan.json" % (ref.path, "; ".join("%s: %s" % (t, x) for _, t, x in ref.rows) or "nothing in it"))
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
    print("music: %s  %s BPM  BEAT0 %s  first landing at track beat %d = M0 (drop at track beat %d = beat %s); R0 %s, R1 %s = %.1f s (asked %.0f s); CUTS_ON = %r, FRAME = %r, lead %g frames (cut %d / flash %d frames before their moment)" % (
        P["music"], bpm_text(P), fnum(P["beat0"], 6), M0, P["drop_beat"], fnum(D), fnum(R0, 6), fnum(R1, 2), seconds, P["length"], P["cuts_on"], P["frame"], P["lead_frames"], T.cl, T.hl))
    print("hits in the window: %s (%s); %d takes for %d kills" % (hits_text(H, per), sub_state["why"] or "kills use the half-beat lattice", n, len(kills)))
    for l in lines:
        print(l.strip() if l.lstrip().startswith("#") else "    " + l.strip())
    for t in notes:
        print("note:", t)
    for w in warns:
        print("note:", w)
    if ref is not None:
        if ref.a and P.get("step"):
            on = sum(1 for tk in takes[1:] if tk.line is not None and abs(tk.line / P["step"] - round(tk.line / P["step"])) < 1e-6)
            ref_lines = ["  (%d of %d cuts sit on a line of the reference's %g-beat lattice, the rest on the coarsest of 1/2, 1/4, 1/8 (1/16) beat that fits the lead window)" % (on, max(1, n - 1), P["step"])]
        else:
            ref_lines = []
        if ref.a and lprefs and raises:
            ref_lines += ["  gaps: " + r_ for r_ in raises[:12]] + (["  gaps: ... %d more raised to their physical minimum" % (len(raises) - 12)] if len(raises) > 12 else [])
        for l in ref.report():
            print(l)
        for l in ref_lines:
            print(l)
    else:
        print("reference: none (no ref_notes.json in this folder): the model edit's cut rhythm, transitions, slow motion, look and ending")
    st = stats(ns, H)
    print("wrote %s: %d takes, %d frames, %.2f s, music from %.3f s" % (args.out, len(ns["SEGS"]), ns["N_FRAMES"], seconds, ns["MUSIC_T0"]))
    print_stats("draft", st)
    if args.compare and os.path.isfile(args.compare):
        cns = exec_timeline(open(args.compare, encoding="utf-8").read(), "compare")
        ch = None
        if cns["MUSIC"] == P["music"]:
            try:
                rows_, att_ = beat_hits.measure_t(m, cns["BPM"], cns["BEAT0"], cns["M0"], cns["R0"], cns["R1"], False, 4)
                ch = Hits(rows_, att_, None, 2, cns["FPB"], lambda t: (t - cns["BEAT0"]) / cns["PER"] - cns["M0"])
            except SystemExit:
                pass
        print_stats(os.path.basename(args.compare), stats(cns, ch))
    print("next: $PY timeline.py (must pass), $PY music_pulses.py (none / none), $PY ranges.py, $PY deathstrip.py ds.jpg (every death on a green tile)")


def lead_text(lead, start):
    """lead-in anchors for an L entry: the first one sits on the start beat exactly as written in the entry (the template asserts it)"""
    parts = []
    for j, a in enumerate(lead):
        b = b9(start) if j == 0 else fnum(a[0], 6)
        parts.append("(%s)" % ", ".join([b, fnum(a[1], 1)] + [fnum(x, 2) for x in a[2:]]))
    return ", ".join(parts)


def report_fail(P, T, takes, H, ib, bass, why, tol, probe, R1_hi, per, drift=None):
    """Explain with numbers why no placement exists, then stop."""
    n = len(takes)
    msgs = ([drift] if drift else []) + list(dict.fromkeys(why))
    if bass:
        have = [H.kick_beat(u) for u in H.kicks if 0.5 < H.kick_beat(u) <= R1_hi - T.tail[0]]
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
