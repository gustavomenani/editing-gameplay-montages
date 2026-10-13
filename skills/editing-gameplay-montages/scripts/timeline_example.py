"""The edit, expressed in beats of the music. THIS IS THE FILE TO REWRITE FOR A NEW VIDEO
(copy it to timeline.py); every other script reads it.

This one is the house example: a Valorant montage (7 clips, 22 kills, a 130 BPM song). Timeline beat 0 is
beat 64 of the track; the drop (bass re-entry after
the breakdown) is beat -1. Every kill sits on a kick or a snare that was measured on the track.
Source positions are frame indices of the clips (exact, 60 per second)."""
import math
import numpy as np

# ---------------------------------------------------------------- the music
# >>> draft:music   (draft_timeline.py rewrites everything between the draft markers; edit freely once it has run)
MUSIC = "src/music.flac"
BPM, BEAT0 = 130.0, 0.4608          # tempo, and the time of the track's first beat (music_grid.py measures BEAT0)
M0 = 64                             # timeline beat 0 = this beat of the track
PER = 60.0 / BPM
FPS = 60
FPB = FPS * PER                     # output frames per beat (27.69)
R0, R1 = -5.2, 75.2                 # first / last beat of the video
FADE_OUT = (72.4, 75.2)             # picture and music fade to black over these beats
CUTS_ON = "bass"                    # where transitions land: "bass" (kicks / 808s only, the default) or "kills" (with the
                                    # kill rhythm): the user's choice in the briefing; music_pulses.py checks it. The edit
                                    # below was cut with the kills ("kills"): its transition beats do not pass "bass".
# <<< draft:music


def beat_time(r):
    """Where timeline beat r sits inside the track (seconds)."""
    return BEAT0 + (M0 + r) * PER


MUSIC_T0 = beat_time(R0)            # where the video starts inside the track
N_FRAMES = int(round((R1 - R0) * FPB))
# >>> draft:sound
# sound design tied to this piece of music (audio.py); use None / [] to switch off
SWEEP = [(63.3, 18000), (65.0, 1000), (67.6, 620), (68.0, 620)]     # low-pass on the music: (beat, cutoff Hz)
RISERS = [dict(a=-5.0, b=-1.0, f0=350, f1=7000, curve=1.0, width=1.1, power=2.3, gain=0.13, cut=0.012, seed=1),
          dict(a=63.6, b=68.0, f0=300, f1=9000, curve=1.3, width=1.2, power=2.0, gain=0.20, cut=0.010, seed=2)]
# <<< draft:sound


# ---------------------------------------------------------------- the segments
def S(clip, a, kills=(), slow=None, skill=(), tin=("cut", 0.0), lag=2.0, push=(), bars=None, voice=None,
      stretch=False, mute=False):
    """One continuous take.
    clip    name of the file in src/ (without extension)
    a       anchors [(beat, source frame), ...], both strictly increasing. The speed between anchors is eased
            (see TimeMap); FPB source frames per beat is real time. Use lead() / tail() for the usual shapes.
    kills   [(beat, level)]: 1 normal, 2 slow-motion finisher (the zoom stays in), 3 the big ones (impact frame).
            The source frame at that beat must be the muzzle-flash frame of the kill.
    slow    (beat, beat) note for the editor only: where the take runs in slow motion (the anchors decide the speed)
    skill   [(beat, beat)] an ability is on screen: gentle zoom and a little colour fringing
    tin     transition INTO this segment: ("cut", 0) / ("fade", 0) plain; ("zcut", 0) hard cut hidden by a zoom;
            ("whip", beats, (dx, dy)) / ("spin", beats, (dx, dy)) / ("zoom", beats) / ("dissolve", beats) /
            ("soft", beats) overlap both clips for `beats`, centred on the first anchor of this segment
    lag     how many source frames the game sound trails the picture; one value, or one per kill
            (measured gunshot onset minus muzzle-flash frame, see kill_lags.py)
    push    [(beat, beat, amount)] slow push-in of the camera (slow motion)
    bars    (beat, beat) the window narrows to a wider frame and the backdrop dims (slow motion)
    voice   0..1: the clip's sound is people talking: keep their pitch and let it run on in real time
    stretch True: keep the pitch of the game sound where the speed is not 1 (voice lines)
    mute    True: no game sound (end card)"""
    lags = list(lag) if isinstance(lag, (list, tuple)) else [lag] * max(1, len(kills))
    assert len(lags) == max(1, len(kills))
    return dict(clip=clip, a=a, kills=list(kills), slow=slow, skill=list(skill), tin=tin, lag=lags,
                push=list(push), bars=bars, voice=voice, stretch=stretch, mute=mute)


F = FPB


def lead(k, K, beats, fast=1.6, settle=0.5):
    """Cut in `beats` before a kill at beat k / source frame K: fast-forward first, real time for the last half beat."""
    if beats <= settle:
        return [(k - beats, K - beats * F), (k, K)]
    return [(k - beats, K - settle * F - (beats - settle) * F * fast), (k - settle, K - settle * F), (k, K)]


def tail(k, K, beats, rate=0.28, hold=0.2, out=0.4, out_rate=0.75):
    """Finisher: real time through the recoil, then slow motion, then speeding up into the next clip."""
    a = [(k + hold, K + hold * F)]
    mid = beats - hold - out
    a.append((k + hold + mid, a[-1][1] + mid * F * rate))
    a.append((k + beats, a[-1][1] + out * F * out_rate))
    return a


def bullet(k, K, beats, rate=0.18):
    """Bullet time INTO a kill that arrives at real speed (the rule of SKILL.md: "a slow lead-in reaches the kill at real
    speed"): `beats` of slow motion at `rate`, easing up through 0.3x and 0.55x, and an anchor one frame before the kill
    at real time. Frames of footage needed: (beats - 1) * rate * F + 0.36 * F + 1. Use beats >= 3.5."""
    return [(k - beats, K - (beats - 1.0) * F * rate - 0.7 * F * 0.30 - (0.3 - 1 / F) * F * 0.55 - 1),
            (k - 1.0, K - 0.7 * F * 0.30 - (0.3 - 1 / F) * F * 0.55 - 1),
            (k - 0.3, K - (0.3 - 1 / F) * F * 0.55 - 1),
            (k - 1 / F, K - 1), (k, K)]


# >>> draft:segs
SEGS = [
    # Jett dash into the point-blank sheriff kill, landing on the drop; slow motion once the flash clears
    S("c2", [(-5.2, 1115.5 - 0.9 * F), (-4.3, 1115.5), (-1, 1203), (-0.6, 1213.8), (1.2, 1227.8), (1.8, 1239.4)],
      kills=[(-1, 3)], slow=(-1, 1.8), skill=[(-4.7, -3.3)], tin=("fade", 0.0), lag=-0.4,
      push=[(-1, 1.6, 0.12)], bars=(-0.7, 1.35)),
    # Bind, one continuous take: kill on the kick, dash on the snare, kill on the next downbeat
    S("c3", lead(4, 130, 2.2, fast=1.25) + [(4.2, 135.5), (4.96, 211.5), (5.6, 233), (6.5, 274.2), (7, 288),
                                            (7.9, 288 + 0.9 * F)],
      kills=[(4, 1), (7, 1)], skill=[(4.9, 5.7)], tin=("zoom", 0.7), lag=[2.75, 2.88]),
    S("c3", lead(9, 552, 1.1) + [(10.4, 552 + 1.4 * F)], kills=[(9, 1)], tin=("zcut", 0.0), lag=3.15),
    S("c3", lead(12, 1184, 1.6) + tail(12, 1184, 1.5), kills=[(12, 2)], slow=(12, 13.5), tin=("zcut", 0.0), lag=2.25,
      push=[(12, 13.4, 0.07)], bars=(12.1, 13.1)),
    # Phoenix: one tap, then one continuous take: kill, fireball, two kills through the fire
    S("c4", lead(15, 302, 1.5) + [(16.1, 302 + 1.1 * F)], kills=[(15, 1)], tin=("whip", 0.7, (1, 0)), lag=1.75),
    S("c4", lead(17, 575, 0.9) + [(17.3, 583.3), (18.5, 626.2), (19.4, 651.1), (20.5, 754.2), (21, 768), (23, 838)]
      + tail(23, 838, 2.0),
      kills=[(17, 1), (21, 1), (23, 2)], slow=(23, 25), skill=[(18.5, 19.5)], tin=("zcut", 0.0), lag=[1.4, 1.75, 1.45], stretch=True,
      push=[(23, 24.8, 0.10)], bars=(23.1, 24.5)),
    # Jett out of her own smoke
    S("c2", lead(26.5, 862, 1.5) + [(27.3, 862 + 0.8 * F)], kills=[(26.5, 1)], tin=("whip", 0.7, (-1, 0)), lag=2.05),
    # Reyna: three kills on three consecutive bass hits, then dismiss
    S("c7", [(27.3, 79 - 1.7 * F), (29, 79), (29.5, 79 + 0.5 * F)], kills=[(29, 1)], tin=("spin", 0.8, (1, 0)), lag=2.8),
    S("c7", [(29.5, 472 - 0.5 * F), (30, 472), (31, 498), (32, 534), (33, 556), (34, 586.5)], kills=[(30, 1), (31, 1)],
      skill=[(31.7, 34)], tin=("zcut", 0.0), lag=[2.55, 2.0]),
    # Vandal 4K
    S("c1", lead(36, 5362, 2.0) + [(39, 5474), (44, 5612), (46, 5679)] + tail(46, 5679, 3.2),
      kills=[(36, 1), (39, 1), (44, 1), (46, 2)], slow=(46, 49.2), tin=("whip", 0.7, (0, -1)), lag=2.5, voice=0.8,
      push=[(46, 49.0, 0.10)], bars=(46.1, 48.8)),
    # the ace: two kills, dash, two more, then bullet time into the last one on the bass re-entry
    S("c5", [(49.2, 103 - 2.8 * F), (52, 103), (55, 229), (56.5, 229 + 1.5 * F * 0.97)], kills=[(52, 1), (55, 1)],
      skill=[(55.5, 56.6)], tin=("whip", 0.7, (-1, 0)), lag=[1.95, 2.6]),
    S("c6", lead(58.5, 165, 2.0, fast=1.3) + [(60, 205), (61.5, 205 + 1.5 * F)], kills=[(58.5, 1), (60, 1)],
      tin=("zoom", 0.6), lag=[1.7, 2.7]),
    S("c6", [(61.5, 765), (64, 801), (67.8, 818.5), (68, 821), (68.25, 825.5), (70.2, 840.6), (70.6, 844.5)],
      kills=[(68, 3)], slow=(63.2, 70.6), tin=("dissolve", 0.5), lag=1.6,
      push=[(63.2, 68, 0.20), (68, 70.4, 0.08)], bars=(63.4, 70.3)),
    # the ACE banner: no zoom, it only fades to black with the music
    S("c6", [(70.6, 922), (75.2, 962)], tin=("soft", 1.2), lag=1.5, mute=True),
]
KILLS = [(k, lv, i) for i, s in enumerate(SEGS) for k, lv in s["kills"]]
# accents without a kill: (beat, weight). Snares fall every 4 beats from beat 1, kicks were measured on the track
# (music_pulses.py). They drive the backdrop pulse, a small zoom punch and an exposure pop.
PULSES = [(-4.3, 0.7), (1, 0.6), (5, 0.8), (13, 0.6), (14, 0.7), (19, 0.5), (20, 0.8), (21.5, 0.7), (25, 0.8),
          (33, 0.6), (37, 0.6), (41, 0.6), (45, 0.8), (47, 0.9), (49, 0.7), (53, 0.6), (53.5, 0.7), (57, 0.6),
          (61, 0.8), (62, 0.8), (63, 0.5), (69, 0.6), (69.5, 0.7), (71, 0.8), (73, 0.5)]
# <<< draft:segs


class TimeMap:
    """Monotone cubic (PCHIP) beat -> source-frame map: every speed change is eased.
    Outside the anchors it keeps running at the end speed (needed while a transition overlaps)."""

    def __init__(self, anchors):
        self.x = np.array([a[0] for a in anchors], float)
        self.y = np.array([a[1] for a in anchors], float)
        h, d = np.diff(self.x), np.diff(self.y) / np.diff(self.x)
        m = np.zeros(len(self.x))
        m[0], m[-1] = d[0], d[-1]
        for i in range(1, len(self.x) - 1):
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
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
for _i, _s in enumerate(SEGS):          # on-screen range of each segment including transition overlap
    half_in = _s["tin"][1] / 2 if _s["tin"][0] in ("zoom", "whip", "spin", "dissolve", "soft") else 0.0
    nxt = SEGS[_i + 1]["tin"] if _i + 1 < len(SEGS) else ("cut", 0.0)
    half_out = nxt[1] / 2 if nxt[0] in ("zoom", "whip", "spin", "dissolve", "soft") else 0.0
    _s["x0"], _s["x1"] = _s["r0"] - half_in, _s["r1"] + half_out


def frame_beat(n):
    return R0 + n / FPB


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def ease5(x):
    x = min(1.0, max(0.0, x))
    return x * x * x * (x * (x * 6 - 15) + 10)


def punch(d, attack=0.07, release=0.55):
    """Fast smooth attack and a long soft release; peak normalised to ~1."""
    if d < 0:
        return 0.0
    return (1 - math.exp(-d / attack)) * math.exp(-d / release) / 0.674


def active(r):
    """Segments on screen at beat r: (a, None, 0, tin) or (a, b, p, tin_of_b) during an overlapping transition."""
    for j in range(1, len(SEGS)):
        kind, d = SEGS[j]["tin"][0], SEGS[j]["tin"][1]
        if d > 0 and abs(r - SEGS[j]["r0"]) < d / 2:
            return j - 1, j, (r - (SEGS[j]["r0"] - d / 2)) / d, SEGS[j]["tin"]
    for i, s in enumerate(SEGS):
        if r < s["r1"]:
            return i, None, 0.0, None
    return len(SEGS) - 1, None, 0.0, None


if __name__ == "__main__":          # python timeline.py: print the edit and check it for the usual mistakes
    import sys, preflight             # every problem at once: clips in src/, anchors, kills, CUTS_ON, song length
    preflight.require(sys.modules[__name__], music=True)
    print("frames", N_FRAMES, "duration %.2fs" % ((R1 - R0) * PER), "music from %.3fs" % MUSIC_T0)
    for i, s in enumerate(SEGS):
        rs = np.linspace(s["x0"], s["x1"], 400)
        p, v = s["map"](rs)
        print("%2d %s beats %6.2f..%6.2f  frames %7.1f..%7.1f  speed %.2f..%.2f  kills %s  in:%s" % (
            i, s["clip"], s["r0"], s["r1"], p.min(), p.max(), v.min(), v.max(), [k for k, _ in s["kills"]], s["tin"][0]))
        assert np.all(np.diff(p) > 0), "time map must move forward"
        assert np.all(np.diff([q[0] for q in s["a"]]) > 0), "segment %d: anchor beats must increase" % i
        if i:
            assert abs(s["r0"] - SEGS[i - 1]["r1"]) < 1e-9, "segment %d must start on the beat where segment %d ends" % (i, i - 1)
        for k, lv in s["kills"]:
            assert s["r0"] <= k <= s["r1"], "segment %d: kill at beat %g is outside the segment" % (i, k)
            if not any(abs(k - q[0]) < 1e-9 for q in s["a"]):
                print("   note: the kill at beat %g has no anchor of its own, so its frame is only interpolated" % k)
            if k - s["x0"] < s["tin"][1]:
                print("   note: the kill at beat %g falls inside or right after the transition into this segment" % k)
            kv = float(s["map"](k)[1])
            if kv < 0.8:                              # the house example's bullet time into the last kill arrives at 0.53x and was delivered so
                print("   note: the kill at beat %g is reached at %.2fx, so its flash builds over more than one frame; "
                      "an anchor one frame before it at real time, (k - 1/FPB, K - 1), puts it on the beat" % (k, kv))
    assert SEGS[0]["r0"] <= R0 + 1e-9, "the first anchor must be at or before R0"
    assert SEGS[-1]["r1"] >= R1 - 1e-9, "the last anchor must be at or after R1"
    assert R0 < FADE_OUT[0] < FADE_OUT[1] <= R1 + 1e-9, "FADE_OUT must lie inside the video"
