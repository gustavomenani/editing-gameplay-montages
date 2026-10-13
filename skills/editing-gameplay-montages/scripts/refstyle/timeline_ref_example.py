"""The edit, expressed in beats of the music (the worked example: a 130 BPM trap song, ARTIST - TITLE). Every other script reads this file.

Style: copy of the user's reference (reference.mp4): horizontal 1920x1080, lyric words on screen,
hard cuts that land just before the beat with a 4-frame blur-in (whip / zoom burst / roll) while the footage
fast-forwards through the flick, the muzzle-flash frame sharp ON the beat, real time through the recoil,
then smooth slow motion, 2 frames of speed-up and the next cut. Ending: luma fade to black.

Timeline beat 0 = beat 31 of the track = the first 808 hit (track 14.77 s). The big drop is beat 32.
Source positions are frame indices of the clips (exact, 60 per second)."""
import math
import numpy as np

# ---------------------------------------------------------------- the music
# EVERYTHING IN THIS BLOCK BELONGS TO THIS SONG AND THIS VIDEO: set it for a new project (music_tempo.py, music_grid.py),
# including the extension of MUSIC, LUMA_FADE and the RISERS beats (a riser ends on a drop: here beats 0 and 32).
# >>> draft:music
MUSIC = "src/music.flac"
BPM, BEAT0 = 130.0, 0.4608          # measured with music_grid.py (-0.4 ms on 14..52 s)
M0 = 31                             # timeline beat 0 = this beat of the track
PER = 60.0 / BPM
FPS = 60
FPB = FPS * PER                     # output frames per beat (27.69)
R0, R1 = -16.0, 84.6                # first / last beat of the video (46.4 s)
FADE_OUT = (82.0, 84.6)             # the music fades over these beats
LUMA_FADE = (82.3, 83.2)            # the picture: dark areas go black first, highlights last (as in the reference)
CUTS_ON = "bass"                    # where cuts land: "bass" (kicks / 808s only, the default) or "kills" (with the kill
                                    # rhythm): the user's choice in the briefing; music_pulses.py checks it. The worked example's edit
                                    # below was cut with the kills ("kills"): its cut beats do not pass "bass".
FRAME = "horizontal"                # "horizontal" (1920x1080, the gameplay fills the frame; the worked example) or "vertical" (1080x1920 for
                                    # TikTok / Reels / Shorts: the whole 16:9 gameplay in a window over a blurred backdrop, same cuts,
                                    # slow motion, words and luma fade). Optional: without it, horizontal. Nothing else in this file depends on it.
MAX_SPEED = None                    # the worked example as delivered: no ceiling (the blur-in squeezes 16 source frames into 4 output frames, 5.8x; after the slow
                                    # motion the footage speeds up). A drafted edit writes MAX_SPEED = 1.0: nothing plays faster than real time
                                    # (pre() enters the take at real time, post() / fall() ease back from slow motion to real time, an M take's kills
                                    # keep their real-time distance or more); the user may ask for velocity: then e.g. 1.6, or None. preflight.py
                                    # lists every run of frames above MAX_SPEED * 1.02 as an error.
# <<< draft:music


def beat_time(r):
    """Where timeline beat r sits inside the track (seconds)."""
    return BEAT0 + (M0 + r) * PER


MUSIC_T0 = beat_time(R0)
N_FRAMES = int(round((R1 - R0) * FPB))
# >>> draft:sound
SWEEP = None
RISERS = [dict(a=-4.0, b=0.0, f0=350, f1=7000, curve=1.0, width=1.1, power=2.3, gain=0.10, cut=0.012, seed=1),
          dict(a=27.6, b=32.0, f0=300, f1=9000, curve=1.3, width=1.2, power=2.0, gain=0.17, cut=0.010, seed=2)]
# <<< draft:sound
# the model edit's sound and accents (draft_ref_timeline.py writes them; every name is optional, absent = the plain render / mix):
#   IMPACT, ACC   kill accents per level 1..3 (render.py); BUMPS [(beat, 0..1)] light pulses on hits without a kill; LUMA_IN (beat a, beat b)
#   the opening reveals the bright areas first; BOOMS [dict(r=beat, gain=0.26)] sub drops; KILL_THUMP, WHOOSH_BLUR, GAME_LEVEL sound levels;
#   HEADROOM the level mix.wav is written at; FADE_IN seconds of fade-in of the song. Segment keys: white (flash keyframes), shot_from.
# >>> draft:fx
# <<< draft:fx

F = FPB
# >>> draft:cut
CUT = 0.15                          # a cut sits this many beats before its kill beat: 4 frames at 130 BPM (another tempo: about 4 / FPB)
PUSH = 0.035                        # slow push-in of a take (S(push=...) overrides it)
# <<< draft:cut


# ---------------------------------------------------------------- segments
def S(clip, a, kills=(), tin=("cut", 0.0), lag=2.0, view=(1.0, 0.0, 0.0), shutter=0.65, mute=False, voice=None,
      stretch=False, push=None, intro=False, calm=False, white=None, shot_from=None):
    """One continuous take.
    a       anchors [(beat, source frame)], eased (TimeMap); FPB source frames per beat is real time. An anchor may carry
            its speed as a third number, (beat, source frame, speed): the map then has exactly that speed there (1 = real time)
            instead of the smoothed one; post() uses it to ease between real time and slow motion without overshoot
    kills   [(beat, level)] 1 normal, 2 accent, 3 the two big ones; the source frame there is the muzzle-flash frame
    tin     how the take comes in: ("fade", 0) / ("cut", 0) / ("bwhip", 0, +1|-1) / ("bzoom", 0) / ("broll", 0, +1|-1)
            all are hard cuts; the b* kinds add a blur-in that decays over the first frames (render.py)
    lag     unused in this style (audio.py measures each gunshot itself); kept for the shared scripts
    view    (zoom, dx, dy): fixed crop of the source. Keep (1, 0, 0): the user rejects enlarged gameplay
    shutter footage shutter in output frames (the intro uses a long one: dreamy motion blur)
    push    slow push-in of the camera over the take (default PUSH)
    intro   True: an intro shot (slightly darker, softer colour, more bloom, no lean into the next cut)
    mute    True: no gunshot for this take's kills (a kill talked over on voice chat)
    calm    True: no zoom, punch or shake at all (the ending: the user asked for no zoom on the ace, only the fade)
    white   [(beat, 0..1)] eased keyframes of a flash / burn to white (flash() helper), or None
    shot_from (clip, K): use that kill's gunshot for this take's kills (a clip without a clean shot of its own), or None
    voice, stretch   unused in this style (house-style sound options); kept for the shared scripts"""
    lags = list(lag) if isinstance(lag, (list, tuple)) else [lag] * max(1, len(kills))
    assert len(lags) == max(1, len(kills))
    return dict(clip=clip, a=a, kills=list(kills), slow=None, skill=[], tin=tin, lag=lags, push=PUSH if push is None else push, bars=None,
                voice=voice, stretch=stretch, mute=mute, view=view, shutter=shutter, intro=intro, calm=calm, white=white, shot_from=shot_from)


SLOW_MAX = 1.6          # MAX_SPEED set: beats of slow motion after a shot; a longer take runs on at real time (opts: slow=..., slow=None = to the end)
RAMP = 8.0              # MAX_SPEED set: frames an ease between real time and slow motion takes


def pre(k, K, n=None, lb=None):
    """Blur-in of a take: the cut sits `lb` (default CUT) beats before the shot and the flash frame K on it.
    MAX_SPEED None (the worked example as delivered): `n` source frames (16, or the whole lead when it is longer) of the flick squeezed into the
    frames before the beat, the last frame at real time. MAX_SPEED set: the footage enters at MAX_SPEED (1.0 = real time: the take starts
    lb * FPB source frames before the flash: CUT * FPB = 4.15 in the example, LEAD_FRAMES in a drafted file); the blur-in is the
    picture's own (render.py), not compressed footage. An explicit `n` is honoured (and is an error in preflight.py when it makes the
    picture faster than MAX_SPEED)."""
    lb = CUT if lb is None else lb
    if n is None:
        n = max(16.0, lb * F) if MAX_SPEED is None else 1.0 + max(1.0, MAX_SPEED / 1.1) * (lb * F - 1.0)      # above 1.0 the node keeps the peak 8 % below the ceiling
    last = (k, K) if MAX_SPEED is None or MAX_SPEED > 1.0 else (k, K, MAX_SPEED)             # a ceiling of 1 or less: that speed exactly at the shot (pinned)
    return [(k - lb, K - n), (k - 1.0 / F, K - 1), last]


def post(k, K, end, rate=0.16, hold=None, out=0.08, slow=SLOW_MAX):
    """After the shot: real time through the recoil (flash and recoil do not interpolate) until the kill is
    confirmed on the HUD (the feed row arrives 5 to 12 frames after the shot, usually 6 to 10), slow motion, speed-up.
    A half-beat clip has no room for slow motion: it runs on at about real time, like the reference's rapid series.
    hold is in beats: 0.3 beat = 8 frames at 130 BPM (another tempo: about 8 / FPB, and 5.5 / FPB for the short form).
    MAX_SPEED set: no speed-up above real time. The speed eases (RAMP frames, linear in speed) from real time down to `rate`;
    the slow motion lasts `slow` beats at most (None: to the end of the take) and eases back to real time when the take has
    half a beat or more left (the aftermath); a take that ends in slow motion simply cuts. `out` is not used."""
    if hold is None:
        hold = 0.3 if end - k >= 0.8 else 0.2
    rem = end - (k + hold)
    if rem <= 0.02:
        return [(end, K + (end - k) * F)]
    if MAX_SPEED is not None:
        v = min(1.0, MAX_SPEED)
        a = [(k + hold, K + hold * F * v, v)]
        if rem < 0.45:
            a.append((end, a[-1][1] + rem * F * 0.9 * v))
            return a
        rd = min(RAMP / F, 0.4 * rem)
        a.append((a[-1][0] + rd, a[-1][1] + rd * F * (v + rate) / 2, rate))
        ru = RAMP / F
        if slow is not None and end - a[-1][0] - slow - ru >= 0.5:
            a.append((a[-1][0] + slow, a[-1][1] + slow * F * rate, rate))
            a.append((a[-1][0] + ru, a[-1][1] + ru * F * (v + rate) / 2, v))
            a.append((end, a[-1][1] + (end - a[-1][0]) * F * v, v))
        else:
            a.append((end, a[-1][1] + (end - a[-1][0]) * F * rate, rate))
        return a
    a = [(k + hold, K + hold * F)]
    if rem < 0.45:
        a.append((end, a[-1][1] + rem * F * 0.9))
        return a
    a.append((end - out, a[-1][1] + (rem - out) * F * rate))
    a.append((end, a[-1][1] + out * F * 1.3))
    return a


FALL_RAMP = 5.0         # fall(): frames an ease between real time and the slow rate takes
FALL_MIN = 0.15         # fall(): slowest constant rate; a longer window slows to this until the body is down, then eases back to real time


def fall(k, K, end, upto, h=8):
    """After the shot the take shows the enemy's whole death: `upto` = source frames after the shot until the body is down (or the
    last frame before the camera turns away), measured on deathstrip.py sheets. Real time for h frames (recoil and flash), an ease
    (FALL_RAMP frames, linear in speed), then ONE constant slow rate that lands on K + upto exactly at the end of the take.
    When the window would need a rate below FALL_MIN the slow motion stops at FALL_MIN as soon as the body is down and eases back to
    real time (never above MAX_SPEED). The speeds are pinned (third number of an anchor): no overshoot of the interpolation."""
    v = 1.0 if MAX_SPEED is None else min(1.0, MAX_SPEED)
    A = (end - k) * F                                      # output frames after the shot
    assert A >= upto / v - 0.5, ("the take ends %.1f frames after the shot: the death needs %d" % (A, upto), k, K)
    if A <= upto / v + 0.5:                                # no room for slow motion: real time to the cut, the body lands on it
        return [(end, K + A * v, v)]
    h = max(0.0, min(float(h), upto / v - 1.0))
    a = [(k + h / F, K + h * v, v)] if h >= 1.0 else []
    D, W = upto - h * v, A - h                             # source frames still to show, output frames left
    R = min(FALL_RAMP, W / 3.0)
    if D <= R * (v + FALL_MIN) / 2.0 + 1.0:                # almost nothing left to show: one plain slow stretch
        return a + [(end, K + upto)]
    r = (D - R * v / 2.0) / (W - R / 2.0)                  # the constant rate that lands on K + upto at the end
    t = k + (h + R) / F
    if r >= FALL_MIN:
        return a + [(t, K + h * v + R * (v + r) / 2.0, r), (end, K + upto, r)]
    m = FALL_MIN                                           # too slow: stop at m once the body is down, then back to real time
    S = (D - R * (v + m) / 2.0) / m                        # output frames of the constant slow stretch
    Wr = W - R - S                                         # output frames left after it
    if Wr < 3.0:
        return a + [(t, K + h * v + R * (v + r) / 2.0, r), (end, K + upto, r)]
    a += [(t, K + h * v + R * (v + m) / 2.0, m), (t + S / F, K + upto, m)]
    R2 = min(FALL_RAMP, Wr / 2.0)
    a.append((a[-1][0] + R2 / F, K + upto + R2 * (m + v) / 2.0, v))
    a.append((end, a[-1][1] + (Wr - R2) * v, v))
    return a


def flash(b, w=0.36, frames=8.0):
    """A white flash-in at beat b (the take opens washed out and clears over `frames` output frames). 0.36 at most:
    0.6-0.9 read as a white blot."""
    return [(b, w), (b + frames / F, 0.0)]


# >>> draft:post
# <<< draft:post


# the edit as a list of entries; each take ends where the next one starts
#   ("shot", start, clip, src_a, src_b, opts)                      no kill (intro)
#   ("K", kill_beat, clip, K, opts)                                one kill, reference anatomy
#   ("M", [(beat, K), ...], clip, opts)                            several kills in one continuous take
#   ("L", start, lead_anchors, kill_beat, clip, K, opts)           custom lead-in (bullet time) into a kill
# options: upto=frames, h=frames  after the last shot the take shows the death (fall(): real time for h frames, one slow rate that lands
#   on K + upto at the cut) instead of post(); lb=beats  K / M: the cut sits lb beats before the first shot (default CUT); lvs=(2, 2)  M: a level
#   per kill; white=flash(b)  a white flash-in; shot_from=(clip, K)  another kill's gunshot; lv, tin, rate, post, slow, n, end, push, ...
# >>> draft:entries
E = [
    # ---- intro: slow, blurred, FULL FRAME, red words. The first render cropped the HUD away with a 1.8-2.2x zoom
    #      and the user answered "no comeco aquele zoom ta mt feio": no crop, no push, no zoom burst here.
    ("shot", -16.0, "c22", 6650, 6700, dict(shutter=2.6, tin=("fade", 0.0), intro=True, mute=True, push=0.0)),
    ("shot", -10.0, "c22", 6765, 6803, dict(shutter=2.6, tin=("bwhip", 0.0, 1), intro=True, mute=True, push=0.0)),
    ("shot", -4.0, "c12", 3306, 3346, dict(shutter=2.2, tin=("bwhip", 0.0, -1), intro=True, mute=True, push=0.0)),
    # ---- A: first drop, sparse 808s (0, 2, 4, 4.5, 6.5, 8, 12.5, 14, 15, 16, 20.5, 22.5, 24)
    ("K", 0.0, "c04", 862, dict(lv=2, n=14, tin=("bwhip", 0.0, 1))),
    # the point-blank kill on Raze that sat here (c04 frame 1203) is out: the user called it "muito feia"
    ("K", 2.0, "c04", 303, dict(tin=("bwhip", 0.0, -1))),
    ("M", [(4.0, 181), (4.5, 199)], "c03", dict(tin=("broll", 0.0, -1))),
    ("M", [(6.5, 1886), (8.0, 1922)], "c05", dict(tin=("bwhip", 0.0, -1), end=10.0)),
    ("L", 10.0, [(10.0, 7586), (11.0, 7604)], 12.5, "c15", 7618, dict(tin=("bzoom", 0.0))),
    ("M", [(14.0, 3902), (15.0, 3931), (16.0, 3964)], "c02", dict(tin=("bwhip", 0.0, 1), end=17.9)),
    ("L", 17.9, [(17.9, 3254), (19.5, 3278)], 20.5, "c12", 3293, dict(post=[(20.7, 3298.5), (21.35, 3309.0)], tin=("broll", 0.0, 1))),
    ("L", 21.35, [(21.35, 186)], 22.5, "c13", 218, dict(rate=0.2, tin=("bwhip", 0.0, -1))),
    ("K", 24.0, "c09", 7112, dict(tin=("bzoom", 0.0), end=26.0)),
    # ---- B: breakdown, bullet time into the biggest flick, which fires on the big drop
    ("L", 26.0, [(26.0, 7322), (28.0, 7352), (30.0, 7368), (31.0, 7379.5)], 32.0, "c09", 7385, dict(lv=3, rate=0.14, tin=("bwhip", 0.0, 1), push=0.10)),
    # ---- C: hats on every half beat, kicks on 37 40 45 47 48 53 54.5 56 59.5
    ("K", 33.5, "c09", 7578, {}),
    ("K", 34.0, "c08", 2530, {}),
    ("K", 34.5, "c08", 2952, {}),
    ("K", 35.5, "c08", 3584, {}),
    ("K", 36.5, "c08", 2688, {}),
    ("K", 37.0, "c17", 3374, dict(lv=2)),
    ("K", 38.0, "c17", 1090, {}),
    ("K", 38.5, "c17", 3533, {}),
    ("K", 39.5, "c18", 1305, {}),
    ("K", 40.0, "c18", 3205, dict(lv=2)),
    ("K", 41.0, "c18", 408, {}),
    ("K", 42.0, "c06", 6635, {}),
    ("K", 43.0, "c06", 6701, {}),
    ("K", 44.0, "c06", 7555, {}),
    ("K", 45.0, "c06", 7606, dict(lv=2)),
    ("K", 46.0, "c16", 4202, {}),
    ("K", 46.5, "c16", 6920, {}),
    ("K", 47.0, "c16", 4033, dict(lv=2)),
    ("K", 48.0, "c04", 335, dict(lv=2)),
    ("K", 50.0, "c19", 3312, {}),
    ("K", 51.0, "c19", 3881, {}),
    ("K", 52.0, "c19", 4571, {}),
    ("K", 53.0, "c10", 5362, dict(lv=2, mute=True)),
    ("K", 54.0, "c10", 5474, dict(mute=True)),
    ("M", [(54.5, 5612), (56.0, 5679)], "c10", dict(lv=2, mute=True)),
    ("K", 57.0, "c07", 2803, {}),
    ("K", 57.5, "c07", 2929, {}),
    ("M", [(58.0, 4185), (59.5, 4225)], "c07", dict(lv=2, end=61.85, rate=0.13, push=0.08)),
    # ---- D: quiet bars, kicks on 62 and 63
    ("K", 62.0, "c07", 4841, dict(lv=2)),
    ("K", 63.0, "c05", 2602, {}),
    # ---- E: kicks on 64 69 72 77 78 79 80
    ("K", 64.0, "c11", 5720, dict(lv=2)),
    ("K", 65.0, "c25", 105, {}),
    ("K", 66.0, "c20", 3520, {}),
    ("K", 66.5, "c20", 3650, {}),
    ("K", 67.0, "c15", 1876, {}),
    ("K", 68.0, "c14", 5324, {}),
    ("K", 69.0, "c02", 4659, dict(lv=2, post=[(69.2, 4664.5), (70.4, 4700.0), (71.77, 4719.0), (71.85, 4721.7)])),
    ("K", 72.0, "c14", 7794, dict(lv=2)),
    ("K", 73.0, "c21", 462, {}),
    ("K", 74.0, "c15", 1445, {}),
    ("K", 75.0, "c19", 3798, {}),
    # ---- the sheriff ace on five consecutive beats; the last two kills are one take (26 frames apart)
    ("K", 76.0, "c01", 4613, dict(lv=2, tin=("bzoom", 0.0))),
    ("K", 77.0, "c01", 5200, dict(lv=2, tin=("bwhip", 0.0, 1))),
    ("K", 78.0, "c01", 5779, dict(lv=2, tin=("bwhip", 0.0, -1))),
    ("M", [(79.0, 6172), (80.0, 6198)], "c01", dict(lv=3, tin=("bzoom", 0.0), rate=0.12, push=0.0, calm=True)),
]
# <<< draft:entries

_FX = [("bwhip", 0.0, 1), ("bzoom", 0.0), ("bwhip", 0.0, -1), ("broll", 0.0, 1), ("bwhip", 0.0, 1), ("bzoom", 0.0),
       ("bwhip", 0.0, -1), ("broll", 0.0, -1)]


def _start(e):
    if e[0] == "shot":
        return e[1]
    if e[0] == "K":
        return e[1] - e[-1].get("lb", CUT)
    if e[0] == "M":
        return e[1][0][0] - e[-1].get("lb", CUT)
    return e[1]


SEGS = []
for _i, _e in enumerate(E):
    _o = dict(_e[-1])
    _nxt = _start(E[_i + 1]) if _i + 1 < len(E) else R1
    _end = _o.pop("end", _nxt)
    assert abs(_end - _nxt) < 1e-9 or _i + 1 == len(E), ("entry %d: 'end' must equal the start of the next take" % _i, _end, _nxt)
    _lv, _n, _rate, _lb = _o.pop("lv", 1), _o.pop("n", None), _o.pop("rate", 0.16), _o.pop("lb", CUT)
    _lvs = _o.pop("lvs", None)                       # M entries: a level per kill (default: 1 ..., then lv on the last)
    _post, _slow = _o.pop("post", None), _o.pop("slow", SLOW_MAX)
    _upto, _h = _o.pop("upto", None), _o.pop("h", 8)
    _pin = (MAX_SPEED,) if MAX_SPEED is not None and MAX_SPEED <= 1.0 else ()      # a ceiling of 1 or less: every kill of an M take plays at it exactly (pinned)
    _o.setdefault("tin", _FX[_i % len(_FX)])

    def _after(k, K):                                # what follows the take's last shot: the plan's anchors, the death (fall) or the reference's post()
        if _post:
            return _post
        return fall(k, K, _end, _upto, _h) if _upto else post(k, K, _end, _rate, slow=_slow)
    if _e[0] == "shot":
        _a, _k = [(_e[1], float(_e[3])), (_end, float(_e[4]))], []
    elif _e[0] == "K":
        _k = [(_e[1], _lv)]
        _a = pre(_e[1], _e[3], _n, _lb) + _after(_e[1], _e[3])
    elif _e[0] == "M":
        _ks = _e[1]
        _k = list(zip([b for b, _ in _ks], _lvs)) if _lvs else [(b, 1) for b, _ in _ks[:-1]] + [(_ks[-1][0], _lv)]
        _a = pre(_ks[0][0], _ks[0][1], _n, _lb) + [(b, float(q)) + _pin for b, q in _ks[1:]] + _after(_ks[-1][0], _ks[-1][1])
    else:
        _k = [(_e[3], _lv)]
        _lead = [(a[0], float(a[1])) + tuple(float(x) for x in a[2:]) for a in _e[2]]        # (beat, frame) or (beat, frame, speed)
        if MAX_SPEED is None:
            if _lead[-1][0] < _e[3] - 2.0 / F:          # bullet time snaps to real time on the last frame, so the flash is on the beat
                _lead.append((_e[3] - 1.0 / F, _e[5] - 1.0))
            _a = _lead + [(_e[3], float(_e[5]))]
        else:                                            # the lead-in eases up to real time over RAMP frames (draft_ref_timeline.py writes its last anchor)
            _a = _lead + [(_e[3], float(_e[5]), min(1.0, MAX_SPEED))]
        _a += _after(_e[3], _e[5])
    SEGS.append(S(_e[2] if _e[0] in ("shot", "K", "M") else _e[4], _a, kills=_k, **_o))

KILLS = [(k, lv, i) for i, s in enumerate(SEGS) for k, lv in s["kills"]]
PULSES = []

# ---------------------------------------------------------------- lyric words on screen: (beat in, beat out, text, style)
# only lines checked against the published lyrics; one word (or one tight group) at a time, each on its sung start
# (lyrics_sync.py: CTC alignment of the confirmed words on the voice stem -> lyric_cues.json), staying while it is sung;
# the user on an early version: "tentar sincronizar ao maximo as letras da tela"
import json as _json
# THESE WORDS BELONG TO THIS SONG. A new project: replace _T (artist and title over the intro, or nothing) and let
# lyrics_sync.py write a new lyric_cues.json. Until then a project shows only _T.
# >>> draft:words
_T = [(-15.0, -12.0, "ARTIST", "red"), (-9.5, -6.5, "TITLE", "red"),
      (-4.0, -3.0, "YEAH", "red"), (-2.78, -2.1, "YEAH", "red"), (-1.97, -1.2, "YEAH", "red")]
# <<< draft:words
import os as _os
if _os.path.exists("lyric_cues.json"):          # written by lyrics_sync.py (which imports this file: hence the test)
    _T += [tuple(c) for c in _json.load(open("lyric_cues.json", encoding="utf-8"))]
WORD_HOLD_MAX = 4.0                             # beats a sung word may stay (a long held note); lyrics_sync.py ends each cue
                                                # when the next word starts or the voice stops
TEXT = []
for _j, (_a0, _b0, _w, _st) in enumerate(_T):
    if _b0 is None:                                   # stays until shortly before the next word, so they never overlap
        _gap = _T[_j + 1][0] - _a0
        _b0 = _T[_j + 1][0] - (0.30 if _gap >= 0.9 else 0.15)
    if _a0 > -1.5:                                    # -1.5: where this song's intro words end; they may stay longer
        _b0 = min(_b0, _a0 + WORD_HOLD_MAX)
    TEXT.append((_a0, _b0, _w, _st))


class TimeMap:
    """Monotone cubic (PCHIP) beat -> source-frame map: every speed change is eased.
    An anchor (beat, frame, speed) pins the speed there (1 = real time): ease-ins between real time and slow motion without overshoot.
    Outside the anchors it keeps running at the end speed."""

    def __init__(self, anchors):
        self.x = np.array([a[0] for a in anchors], float)
        self.y = np.array([a[1] for a in anchors], float)
        h, d = np.diff(self.x), np.diff(self.y) / np.diff(self.x)
        m = np.zeros(len(self.x))
        m[0], m[-1] = d[0], d[-1]
        for i in range(1, len(self.x) - 1):
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
        for i, a in enumerate(anchors):
            if len(a) > 2:                        # pinned speed, capped at 3x the smaller neighbouring secant (the monotone limit: never backwards)
                m[i] = min(a[2] * FPB, 3.0 * min(d[max(i - 1, 0)], d[min(i, len(d) - 1)]))
        self.m = m

    def __call__(self, r):
        r = np.asarray(r, float)
        rc = np.clip(r, self.x[0], self.x[-1])
        i = np.clip(np.searchsorted(self.x, rc, side="right") - 1, 0, len(self.x) - 2)
        h = self.x[i + 1] - self.x[i]
        u = (rc - self.x[i]) / h
        y0, y1, m0, m1 = self.y[i], self.y[i + 1], self.m[i] * h, self.m[i + 1] * h
        p = (2 * u**3 - 3 * u**2 + 1) * y0 + (u**3 - 2 * u**2 + u) * m0 + (-2 * u**3 + 3 * u**2) * y1 + (u**3 - u**2) * m1
        dp = ((6 * u**2 - 6 * u) * y0 + (3 * u**2 - 4 * u + 1) * m0 + (-6 * u**2 + 6 * u) * y1 + (3 * u**2 - 2 * u) * m1) / h
        lo, hi = r < self.x[0], r > self.x[-1]
        p = np.where(lo, self.y[0] + self.m[0] * (r - self.x[0]), np.where(hi, self.y[-1] + self.m[-1] * (r - self.x[-1]), p))
        dp = np.where(lo, self.m[0], np.where(hi, self.m[-1], dp))
        return p, dp / FPB                # source frame, playback speed (1 = real time)


for _i, _s in enumerate(SEGS):
    _s["map"] = TimeMap(_s["a"])
    _s["r0"], _s["r1"] = _s["a"][0][0], _s["a"][-1][0]
    _s["x0"], _s["x1"] = _s["r0"], _s["r1"]            # every transition is a hard cut: no overlap


def frame_beat(n):
    return R0 + n / FPB


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def ease5(x):
    x = min(1.0, max(0.0, x))
    return x * x * x * (x * (x * 6 - 15) + 10)


def punch(d, attack=0.07, release=0.55):
    if d < 0:
        return 0.0
    return (1 - math.exp(-d / attack)) * math.exp(-d / release) / 0.674


def active(r):
    """Segment on screen at beat r (same shape as the skill's function: (a, None, 0, None))."""
    for i, s in enumerate(SEGS):
        if r < s["r1"]:
            return i, None, 0.0, None
    return len(SEGS) - 1, None, 0.0, None


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # accented words print right in Git Bash; no word can stop the check
    import preflight                  # every problem at once: clips in src/, anchors, kills, CUTS_ON, song length
    preflight.require(_sys.modules[__name__], music=True)
    assert FRAME in ("horizontal", "vertical"), "FRAME = %r: it must be exactly \"horizontal\" or \"vertical\"" % (FRAME,)
    print("frames", N_FRAMES, "duration %.2fs" % ((R1 - R0) * PER), "music from %.3fs" % MUSIC_T0, "| takes", len(SEGS), "kills", len(KILLS), "| frame", FRAME)
    for i, s in enumerate(SEGS):
        rs = np.linspace(s["r0"], s["r1"], 400)
        p, v = s["map"](rs)
        print("%2d %s beats %6.2f..%6.2f  frames %7.1f..%7.1f  speed %.2f..%.2f  kills %s  in:%s" % (
            i, s["clip"], s["r0"], s["r1"], p.min(), p.max(), v.min(), v.max(), [k for k, _ in s["kills"]], s["tin"][0]))
        assert np.all(np.diff(p) > 0), "time map must move forward (take %d)" % i
        assert np.all(np.diff([q[0] for q in s["a"]]) > 0), "take %d: anchor beats must increase" % i
        if i:
            assert abs(s["r0"] - SEGS[i - 1]["r1"]) < 1e-9, "take %d must start where take %d ends" % (i, i - 1)
        for k, lv in s["kills"]:
            assert s["r0"] <= k <= s["r1"], "take %d: kill at beat %g is outside the take" % (i, k)
            assert any(abs(k - q[0]) < 1e-9 for q in s["a"]), "take %d: kill at beat %g has no anchor" % (i, k)
            kv = float(s["map"](k)[1])
            if not 0.8 <= kv <= 1.6:
                print("   note: the shot at beat %g plays at %.2fx: its flash will show late. Add an anchor one frame before it at real time" % (k, kv))
    assert SEGS[0]["r0"] <= R0 + 1e-9 and SEGS[-1]["r1"] >= R1 - 1e-9
    for a, b, w, st in TEXT:
        assert b > a + 0.2, ("word on screen too briefly", a, b, w)
    print("words on screen: %d cues%s%s" % (len(TEXT), ": " if TEXT else "", " ".join(w for a, b, w, st in TEXT[:12])),
          "..." if len(TEXT) > 12 else "", "| lyric_cues.json", "loaded" if _os.path.exists("lyric_cues.json") else "absent (only the words typed in _T)")
