"""Montage renderer, reference style: full-frame gameplay, lyric words, hard cuts with a blur-in (whip / zoom
burst / roll + colour split + streak lines), smooth slow motion, luma fade.

Frame (FRAME in timeline.py, frame.py): "horizontal" (default) 1920x1080 with the gameplay filling the frame, or
"vertical" 1080x1920 for TikTok / Reels / Shorts: the whole 16:9 gameplay (nothing cropped, nothing enlarged) in a
1080x608 rounded window on the exact middle of the frame over a blurred backdrop of the same footage, as the house
style does. Cuts, slow motion, words and the luma fade are the same; the blur-in and the streaks act on the whole
canvas (window, backdrop and words together, as an editor applies them to the whole composition), the camera push,
kill punch and shake move the footage inside the window, which stays put.

Accents a timeline.py can ask for (all optional; absent = the render is exactly what it was): IMPACT (radial zoom-blur burst, RGB split,
light rays and one inverted monochrome frame on a kill, per level), ACC (punch / shake / exposure pop per level), BUMPS (a light flash and a
nudge on music hits without a kill), LUMA_IN (the opening reveals the bright areas first), a take's "white" keys (flash / burn to white).
LOOK scales them: kill_zoom the burst and the nudge, fringe the split, flash the bump light, impact False removes the inverted frame.
Vertical frame: what moves the footage acts inside the window (push, punch, shake, bump nudge and light, IMPACT burst and split); what
belongs to the whole composition acts on the whole canvas (blur-in, streaks and IMPACT rays, the inverted frame, flash / burn to white,
LUMA_IN, the fades).

Footage comes from the sub-frame store (real frames + RIFE in-betweens). Every output frame integrates the
footage over its shutter interval (exact time sampling + real motion blur), so nothing steps.
All compositing is done in linear light.

usage: python render.py n0 n1 out.mp4            frames n0..n1-1 as video (no sound)
       python render.py n0 n1 out.jpg [step]     stills for inspection (one frame: full size; several: contact sheet)"""
import os, sys, math, glob, json, subprocess
from collections import OrderedDict
import preflight
import numpy as np
import cv2
T = preflight.timeline()
import look as opts
LK = opts.get(T)                     # the edit options of timeline.py (LOOK); the defaults are the delivered look, byte for byte
import textfx
from ff import FF

import frame
W, H = frame.W, frame.H
SRC_W, SRC_H = 1920, 1080
KS = frame.KS                        # blur-in / streak distances in canvas widths (1.0 in the horizontal frame)
SHUTTER = 0.65                       # default footage shutter, fraction of the output frame interval (takes can override)
GAMMA = 2.2
DR = 1.0 / T.FPB                     # beats per output frame
LIN = ((np.arange(256) / 255.0) ** GAMMA).astype(np.float32)
SEGS = T.SEGS
C = np.array([W / 2.0, H / 2.0])
FRG, BLM, BI, KZ, VGN, FL, GR, SAT, GRADE = (LK[k] for k in ("fringe", "bloom", "blur_in", "kill_zoom", "vignette", "flash", "grain", "saturation", "grade"))
EXPO, WGLOW, VGI = LK["exposure"], LK["wide_glow"], LK["intro_vignette"]     # LOOK exposure (x the linear light, 1 = as before), wide_glow (0 = none), intro_vignette (follows vignette)
CA0 = 0.0011 * FRG                   # lens colour fringing towards the frame edges, always on (as in the reference)
CA_KILL = tuple(c * FRG for c in (0.0025, 0.0035, 0.006))                  # extra fringing on a kill, by level
_ACC = getattr(T, "ACC", {1: (0.016, 3.0, 0.28), 2: (0.026, 5.0, 0.42), 3: (0.045, 9.0, 0.80)})     # kill: zoom punch, shake px, exposure pop (timeline ACC replaces the table)
ACC = {lv: (a * KZ, s * LK["shake"], e * FL) for lv, (a, s, e) in _ACC.items()}    # LOOK kill_zoom, shake, flash (the slow push-in of a take is not scaled: no standing zoom)
# timeline IMPACT: extra accents on every kill, per kill level 1..3: radial (zoom) blur burst about the centre (the crosshair and the
# enemy stay sharp, the edges streak; x LOOK kill_zoom), RGB split px (x LOOK fringe), light rays, an inverted monochrome frame on the
# shot (only when LOOK impact is True). BUMPS [(beat, strength 0..1)]: a light flash (x LOOK flash) and a 1.2 % nudge (x LOOK kill_zoom)
# on music hits that carry no kill. LUMA_IN (beat a, beat b): the opening reveals the bright areas first instead of the plain fade-in.
# Segment key "white": eased keyframes [(beat, 0..1)] of a flash / burn to white. All absent = the render is exactly what it was.
IMPACT = None if getattr(T, "IMPACT", None) is None else dict(
    dict(frames=6, blur=(0.035, 0.06, 0.09), split=(5, 9, 14), rays=(False, True, True), invert=(False, False, True)), **T.IMPACT)
BUMPS = getattr(T, "BUMPS", [])
LUMA_IN = getattr(T, "LUMA_IN", None)
BARS = bool(LK["bars"]) and not frame.VERT                                  # cinema bars 2.39:1: horizontal frame only
BAR_H = int(round((frame.H - frame.W / 2.39) / 2))                          # 138 px at the top and the bottom of 1920x1080
BLUR_IN = 5                          # frames a blur-in lasts
if not os.path.exists("posmap.json"):
    sys.exit("posmap.json is missing: run  python posmap.py  first (it also works while prep.py is still building the store)")
POSMAP = json.load(open("posmap.json"))        # measured position of every stored sixteenth (posmap.py)
CUTF = [int(math.ceil((s["r0"] - T.R0) * T.FPB - 1e-6)) for s in SEGS]          # first output frame of every take
KILLF = [[int(math.ceil((k - T.R0) * T.FPB - 1e-6)) for k, lv in s["kills"]] for s in SEGS]   # first output frame at / after every shot


# ---------------------------------------------------------------- footage
class Store:
    def __init__(self, cache=40):
        self.keys, self.cache, self.max = {}, OrderedDict(), cache

    def avail(self, clip):
        """(positions in sixteenths of a frame, store keys), sorted by position. RIFE does not put a sub-frame
        where its time step says (dead zone at both ends, see rifeutil.Tween), so posmap.json (posmap.py)
        holds the measured position of every sixteenth, for the old grid and for the grid fixends.py rebuilt."""
        if clip not in self.keys:
            ks = sorted(int(os.path.basename(f)[:-4]) for f in glob.glob(f"store/{clip}/*.jpg"))
            fixed = set(POSMAP["fixed"].get(clip, []))
            pos, key = [], []
            for k in ks:
                j, s_ = divmod(k, 16)
                p = float(s_) if s_ == 0 else POSMAP["tables"]["fixed" if j in fixed else "old"][s_]
                if p >= 0:
                    pos.append(j * 16 + p)
                    key.append(k)
            o = np.argsort(pos)
            self.keys[clip] = (np.array(pos)[o], np.array(key)[o])
        return self.keys[clip]

    def frame(self, clip, key):
        k = (clip, int(key))
        if k in self.cache:
            self.cache.move_to_end(k)
            return self.cache[k]
        f = f"store/{clip}/{int(key):08d}.jpg"
        if not os.path.exists(f):
            sys.exit(f"render.py: {f} is not in the store: python ranges.py && python prep.py ranges.json builds what the timeline needs "
                     "(check with python check_store.py)")
        data = np.fromfile(f, np.uint8)
        if len(data) < 4 or data[-2] != 0xFF or data[-1] != 0xD9:     # a cut-off JPEG still decodes, with a grey bottom
            sys.exit(f"render.py: {f} is cut off ({len(data)} bytes; a script stopped while writing it, or a full disk). "
                     "python check_store.py --delete removes the damaged files, python prep.py ranges.json rebuilds them.")
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        lin = LIN[img[:, :, ::-1]]                           # RGB, linear light, float32
        self.cache[k] = lin
        if len(self.cache) > self.max:
            self.cache.popitem(last=False)
        return lin

    def sample(self, clip, p0, p1):
        """Footage averaged over the source-frame interval [p0, p1] (box shutter over the
        piecewise-linear interpolation of the stored sub-frames)."""
        keys, names = self.avail(clip)
        P0, P1 = p0 * 16.0, p1 * 16.0
        i0 = max(0, int(np.searchsorted(keys, P0, side="right")) - 1)
        i1 = min(len(keys) - 1, int(np.searchsorted(keys, P1, side="left")))
        ks = keys[i0:i1 + 1].astype(float)
        nm = names[i0:i1 + 1]
        if len(ks) == 1:
            return self.frame(clip, nm[0])
        if len(ks) == 0 or np.diff(ks).max() > 4.75:
            sys.exit(f"render.py: the store has no complete footage of {clip} between source frames {p0:.1f} and {p1:.1f} "
                     f"({'nothing in store/' + clip + '/' if not len(keys) else 'a gap in the sub-frames'}). "
                     "Build what the timeline needs: python ranges.py && python prep.py ranges.json && python posmap.py, then python check_store.py (it must report 0 missing).")
        w = np.zeros(len(ks))
        if P1 - P0 < 1e-3:
            x = min(max((P0 + P1) / 2, ks[0]), ks[-1])
            j = min(len(ks) - 2, int(np.searchsorted(ks, x, side="right")) - 1)
            f = (x - ks[j]) / (ks[j + 1] - ks[j])
            w[j], w[j + 1] = 1 - f, f
        else:
            for j in range(len(ks) - 1):
                xa, xb = ks[j], ks[j + 1]
                a, b = max(P0, xa), min(P1, xb)
                if b <= a:
                    continue
                L = xb - xa
                w[j] += ((xb - a) ** 2 - (xb - b) ** 2) / (2 * L)
                w[j + 1] += ((b - xa) ** 2 - (a - xa) ** 2) / (2 * L)
        w /= w.sum()
        acc = None
        for key, wj in zip(nm, w):
            if wj < 0.004:
                continue
            f = self.frame(clip, key)
            acc = f * np.float32(wj) if acc is None else cv2.scaleAdd(f, float(wj), acc)
        return acc


# ---------------------------------------------------------------- camera
def cam(i, u):
    """Zoom / offset (source px) / roll (deg) of the virtual camera over take i at beat u."""
    s = SEGS[i]
    vz, vx, vy = s["view"]
    if s.get("calm"):
        return vz, vx, vy, 0.0
    z = s["push"] * min(1.0, max(0.0, (u - s["r0"]) / max(1e-6, s["r1"] - s["r0"])))     # slow push-in over the take
    ox = oy = th = 0.0
    for k, lv in s["kills"]:
        d = u - k
        if 0 <= d < 2.5:
            A, amp, _ = ACC[lv]
            env = (1 - math.exp(-d / 0.03)) * math.exp(-d / 0.22)                         # damped, never random
            ox += amp * env * math.sin(2 * math.pi * 2.7 * d + 1.7 * k)
            oy += 0.7 * amp * env * math.cos(2 * math.pi * 3.3 * d + 2.3 * k)
            th += 0.05 * amp * env * math.sin(2 * math.pi * 2.2 * d + k)
            z += A * T.punch(d, 0.05, 0.35)
    for b, st in BUMPS:                                                    # a music hit without a kill: a 1.2 % nudge (LOOK kill_zoom)
        d = u - b
        if 0 <= d < 1.0:
            z += 0.012 * KZ * st * T.punch(d, 0.03, 0.16)
    return vz * (1.0 + z), vx + ox, vy + oy, th


def look(i, r):
    """Exposure pop and extra colour fringing from the kills of take i."""
    expo, ca = 1.0, CA0
    for k, lv in SEGS[i]["kills"]:
        d = r - k
        if d >= -0.02:
            d = max(d, 0.0)
            expo += ACC[lv][2] * math.exp(-d / 0.10)
            ca += CA_KILL[lv - 1] * math.exp(-d / 0.25)
    for b, st in BUMPS:                                                    # ... and a flash of light (calm takes too; LOOK flash, fringe)
        d = r - b
        if -0.01 <= d < 1.0:
            d = max(d, 0.0)
            expo += 0.22 * FL * st * math.exp(-d / 0.07)
            ca += 0.0018 * FRG * st * math.exp(-d / 0.12)
    return expo, ca


def rot(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s], [s, c]])


def warp(S, z, ox, oy, th, ca):
    """Source image -> canvas. Colour fringing by per-channel zoom (grows towards the edges)."""
    R = rot(th)
    sc = np.array([SRC_W / 2 + ox, SRC_H / 2 + oy])
    chans = []
    for ci, dz in enumerate((1 + ca, 1.0, 1 - ca)):
        A = (1.0 / (z * dz)) * R
        M = np.hstack([A, (sc - A @ C)[:, None]]).astype(np.float64)
        chans.append(cv2.warpAffine(S[:, :, ci], M, (W, H), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                                    borderMode=cv2.BORDER_REFLECT_101))
    return cv2.merge(chans)


def affine(img, zoom=1.0, deg=0.0, dx=0.0, dy=0.0, interp=cv2.INTER_LINEAR):
    """Zoom / rotate about the centre and shift a finished frame or window (reflecting borders)."""
    h, w = img.shape[:2]
    c = np.array([w / 2.0, h / 2.0])
    A = rot(deg) / zoom
    M = np.hstack([A, (c - A @ (c + np.array([dx, dy])))[:, None]]).astype(np.float64)
    return cv2.warpAffine(img, M, (w, h), flags=interp | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REFLECT_101)


def split_rgb(img, px):
    """Red and blue pushed apart horizontally by px pixels."""
    px = int(round(px))
    if px < 1:
        return img
    out = img.copy()
    out[:, px:, 0] = img[:, :-px, 0]
    out[:, :-px, 2] = img[:, px:, 2]
    return out


def blur_in(img, kind, q, seed):
    """The first frames after a cut: the new clip arrives through a whip, a zoom burst or a roll.
    q = frames since the cut. Works on the finished frame, so the lyric word blurs with the footage. Distances
    scale with the canvas width (KS: 1.0 horizontal, 0.5625 vertical); zoom and roll are relative, so they do not."""
    w = (1.0 - q / float(BLUR_IN)) ** 2
    wb = w * BI                                   # LOOK blur_in: how far the effect goes
    nb = max(1.0, BI)                             # more samples when the smear is longer, so no ghost steps show
    if kind[0] == "bwhip":
        d = kind[2]
        L = int(260 * KS * wb) | 1
        img = affine(img, 1.0 + 0.05 * wb, 0.0, d * 330 * KS * wb ** 1.25, 0.0)
        if L > 2:
            img = cv2.blur(img, (L, 1), borderType=cv2.BORDER_REFLECT_101)
        img = split_rgb(img, 20 * KS * wb * FRG)
    elif kind[0] == "bzoom":
        n = int(round(14 * nb)) if w > 0.05 else 1
        acc = np.zeros_like(img)
        for j in range(n):
            acc += affine(img, 1.0 + 0.22 * wb + 0.30 * wb * (j / max(1, n - 1)))
        img = acc * np.float32(1.0 / n)
        r, g, b = cv2.split(img)
        img = cv2.merge([affine(r, 1 + 0.016 * wb * FRG), g, affine(b, 1 - 0.016 * wb * FRG)])
    elif kind[0] == "broll":
        d = kind[2]
        n = int(round(12 * nb)) if w > 0.05 else 1
        acc = np.zeros_like(img)
        for j in range(n):
            acc += affine(img, 1.0 + 0.32 * wb, d * (10.0 * wb + 3.0 * wb * (j / max(1, n - 1) - 0.5)))
        img = acc * np.float32(1.0 / n)
        L = int(70 * KS * wb) | 1
        if L > 2:
            img = cv2.blur(img, (L, 1), borderType=cv2.BORDER_REFLECT_101)
        img = split_rgb(img, 14 * KS * wb * FRG)
    return img


# rows the whip streaks are drawn in: the whole frame; vertical: the gameplay window and a margin around it (the rest is backdrop)
SB0, SBH = (frame.WIN_Y - 90, frame.WIN_H + 180) if frame.VERT else (0, H)


def streaks(img, kind, q, seed):
    """Thin light streaks left behind by the transition; they linger a few frames while fading."""
    life = 9.0
    if q >= life or kind[0] not in ("bwhip", "bzoom"):
        return img
    a = (1.0 - q / life) ** 1.6
    rng = np.random.default_rng(seed)
    lay = np.zeros((H, W), np.float32)
    if kind[0] == "bwhip":
        d = kind[2]
        for _ in range(7):
            y = int(SB0 + rng.uniform(0.08, 0.92) * SBH)
            ln = rng.uniform(260 * KS, 900 * KS)
            x = rng.uniform(-200 * KS, W) - d * (q * rng.uniform(90 * KS, 170 * KS))
            cv2.line(lay, (int(x), y), (int(x + ln), y), float(rng.uniform(0.5, 1.0)), 1 if rng.random() < 0.6 else 2, cv2.LINE_AA)
        lay = cv2.blur(lay, (41, 1))
    else:
        for _ in range(11):
            ang = rng.uniform(0, 2 * math.pi)
            r0 = rng.uniform(140 * KS, 320 * KS) + q * 26 * KS
            r1 = r0 + rng.uniform(220 * KS, 620 * KS)
            p0 = (int(W / 2 + r0 * math.cos(ang)), int(H / 2 + r0 * math.sin(ang)))
            p1 = (int(W / 2 + r1 * math.cos(ang)), int(H / 2 + r1 * math.sin(ang)))
            cv2.line(lay, p0, p1, float(rng.uniform(0.45, 1.0)), 1 if rng.random() < 0.7 else 2, cv2.LINE_AA)
        lay = cv2.GaussianBlur(lay, (0, 0), 0.8)
    img += lay[:, :, None] * (np.array([0.85, 0.97, 1.0], np.float32) * np.float32(0.62 * a * BI))
    return img


# ---------------------------------------------------------------- the model edit's accents (timeline IMPACT, segment "white")
def key_at(keys, r):
    """Value of eased keyframes [(beat, value), ...] at beat r (held before the first and after the last); 0 without keys."""
    if not keys:
        return 0.0
    if r <= keys[0][0]:
        return keys[0][1]
    for (a, va), (b, vb) in zip(keys, keys[1:]):
        if r < b:
            return va + (vb - va) * T.ease((r - a) / (b - a))
    return keys[-1][1]


def burn(img, w):
    """Flash / burn to white by amount w (0..1): exposure climbs, then everything clips towards white. Acts on the whole canvas
    (vertical: window, backdrop and halo together, like a fade)."""
    x = img * np.float32(1.0 + 5.0 * w * w)
    return x + (1.0 - x) * np.float32(w ** 1.3)


def impact_burst(img, i, n):
    """IMPACT radial (zoom) blur burst and RGB split of the kills of take i at output frame n. The burst is an average of the
    frame zoomed about the centre (outermost copy +IMPACT["blur"][level-1], x LOOK kill_zoom) over IMPACT["frames"] frames, so the
    crosshair and the enemy there stay sharp while the edges streak outwards; the split (x LOOK fringe) pulls red and blue apart.
    Calm takes get the split only: no zoom on the ace. `img` is the whole frame (horizontal) or the gameplay window (vertical:
    like the punch and the shake, the burst moves the footage and the window stays put; split distances scale with KS)."""
    s = SEGS[i]
    L = IMPACT["frames"]
    for (k, lv), nk in zip(s["kills"], KILLF[i]):
        q = n - nk
        if q < 0 or q >= L:
            continue
        w = (1.0 - q / float(L)) ** 2
        a = IMPACT["blur"][lv - 1] * w * KZ
        if a > 0.004 and not s.get("calm"):
            m = 10
            acc = np.zeros_like(img)
            for j in range(m):
                acc += affine(img, 1.0 + a * j / (m - 1))
            img = acc * np.float32(1.0 / m)
        img = split_rgb(img, IMPACT["split"][lv - 1] * w * FRG * KS)
    return img


def impact_rays(img, i, n):
    """IMPACT light rays (the zoom-burst streaks, 9 frames, on the whole canvas as for a blur-in) and the inverted frame:
    returns (img, invert), invert = n is the shot frame of a kill whose level asks for the inverted monochrome frame and
    LOOK impact is True (render_frame applies it on the display values, on the whole canvas)."""
    inv = False
    for (k, lv), nk in zip(SEGS[i]["kills"], KILLF[i]):
        q = n - nk
        if q < 0 or q >= 9:
            continue
        if IMPACT["rays"][lv - 1]:
            img = streaks(img, ("bzoom",), q, 101 + nk)
        if q == 0 and IMPACT["invert"][lv - 1] and LK["impact"]:
            inv = True
    return img, inv


# ---------------------------------------------------------------- finishing
if not frame.VERT:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    _v = np.clip(((xx - W / 2) / (W * 0.74)) ** 2 + ((yy - H / 2) / (H * 0.80)) ** 2, 0, 1) ** 1.3
    VIG = (1.0 - 0.20 * VGN * _v)[:, :, None].astype(np.float32)
    VIG_INTRO = (1.0 - 0.46 * VGI * _v)[:, :, None].astype(np.float32)
    del yy, xx, _v
_x = np.linspace(0, 1, 4096)
_g = _x ** (1 / GAMMA)
_g = np.clip(_g + 0.040 * LK["contrast"] * np.sin(2 * math.pi * (_g - 0.5)), 0, 1)             # S-curve (LOOK contrast): deeper shadows, brighter highlights
OUT_LUT = (_g * 255).astype(np.float32)
_rng = np.random.default_rng(11)
if not frame.VERT:
    NOISE = [_rng.uniform(-0.5, 0.5, (H, W)).astype(np.float32)[:, :, None] for _ in range(8)]      # the dither (no visible grain by default)
    if GR > 1:                                                           # LOOK grain above 1: fine film grain (a separate generator keeps the dither as it was)
        _rg = np.random.default_rng(12)
        NOISE = [nz + _rg.normal(0, 3.0 * (GR - 1), (H, W)).astype(np.float32)[:, :, None] for nz in NOISE]


# ---------------------------------------------------------------- vertical frame: gameplay window over a blurred backdrop
# The layout is the house style's (render.py of the house style: full-width rounded window, backdrop = the footage's
# centre strip blurred to 27x48 and dimmed, soft shadow, hairline stroke and halo that light up on a kill), with the
# whole 16:9 frame in the window: 1080 px of footage width is 1920 px of source at 0.5625, so no crop, no zoom.
def rounded_mask(w, h, r):
    m = np.zeros((h * 4, w * 4), np.uint8)
    cv2.rectangle(m, (r * 4, 0), (w * 4 - r * 4, h * 4), 255, -1)
    cv2.rectangle(m, (0, r * 4), (w * 4, h * 4 - r * 4), 255, -1)
    for cx, cy in ((r * 4, r * 4), (w * 4 - r * 4, r * 4), (r * 4, h * 4 - r * 4), (w * 4 - r * 4, h * 4 - r * 4)):
        cv2.circle(m, (cx, cy), r * 4, 255, -1)
    return cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0


if frame.VERT:
    WIN_W, WIN_H, WIN_Y = frame.WIN_W, frame.WIN_H, frame.WIN_Y
    KW = WIN_W / float(SRC_W)                               # source -> window scale (0.5625)
    CW = np.array([WIN_W / 2.0, WIN_H / 2.0])
    MASK = rounded_mask(WIN_W, WIN_H, frame.WIN_R)
    _rows = slice(WIN_Y, WIN_Y + WIN_H)
    _inner = cv2.erode(MASK, np.ones((5, 5), np.uint8))
    STROKE = np.zeros((H, W), np.float32)
    STROKE[_rows] = cv2.GaussianBlur(MASK - _inner, (0, 0), 1.2)
    GLOW = np.zeros((H, W), np.float32)
    GLOW[_rows] = MASK
    GLOW = np.clip(cv2.GaussianBlur(GLOW, (0, 0), 26) - GLOW, 0, 1)                    # halo outside the window
    _sh = np.zeros((H, W), np.float32)
    _sh[WIN_Y + 12:WIN_Y + WIN_H + 40] = 1.0
    UNSHADOW = (1 - cv2.GaussianBlur(_sh, (0, 0), 40) * 0.62)[:, :, None]              # the window's shadow on the backdrop
    yy, xx = np.mgrid[0:WIN_H, 0:WIN_W].astype(np.float32)
    _v = np.clip(((xx - WIN_W / 2) / (WIN_W * 0.74)) ** 2 + ((yy - WIN_H / 2) / (WIN_H * 0.80)) ** 2, 0, 1) ** 1.3
    VIGW = (1.0 - 0.20 * VGN * _v)[:, :, None].astype(np.float32)                      # the footage's own vignette, as in the horizontal frame
    VIGW_INTRO = (1.0 - 0.46 * VGI * _v)[:, :, None].astype(np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    VIG = (1.0 - 0.30 * VGN * np.clip(((xx - W / 2) / (W * 0.80)) ** 2 + ((yy - H / 2) / (H * 0.72)) ** 2, 0, 1) ** 1.3)[:, :, None].astype(np.float32)
    VIG_INTRO = VIG                                                                    # the canvas vignette (the backdrop's); the window has its own
    del yy, xx, _v, _inner, _sh
    _outside = np.ones((H, W), np.float32)
    _outside[_rows] = 1 - MASK
    # dither everywhere (the smooth backdrop would band) and a fine grain outside the window, as in the house style (LOOK grain: x GR outside,
    # above 1 also fine grain inside the window)
    _gs = _outside * GR + (1 - _outside) * (3.0 / 1.25 * max(GR - 1, 0))
    NOISE = [(_rng.uniform(-0.5, 0.5, (H, W)).astype(np.float32) + _rng.normal(0, 1.25, (H, W)).astype(np.float32) * _gs)[:, :, None]
             for _ in range(8)]
    del _outside


def warp_window(S, z, ox, oy, th, ca):
    """Source frame -> the 1080x608 window: the whole 16:9 frame (area-averaged down by 0.5625, so fine HUD
    lines do not alias), then the camera (push, punch, shake, roll) and the colour fringing on the window's content."""
    P = cv2.resize(S, (WIN_W, WIN_H), interpolation=cv2.INTER_AREA)
    R = rot(th)
    sc = np.array([WIN_W / 2.0 + ox * KW, WIN_H / 2.0 + oy * KW])
    chans = []
    for ci, dz in enumerate((1 + ca, 1.0, 1 - ca)):
        A = (1.0 / (z * dz)) * R
        M = np.hstack([A, (sc - A @ CW)[:, None]]).astype(np.float64)
        chans.append(cv2.warpAffine(P[:, :, ci], M, (WIN_W, WIN_H), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                                    borderMode=cv2.BORDER_REFLECT_101))
    return cv2.merge(chans)


def compose_vertical(S, s, r, z, ox, oy, th, ca, expo, i, n):
    """Backdrop + gameplay window (linear light), before the words and the transition. Inside the window (it stays put): the camera,
    the kill punch / shake, the exposure pop of kills and bumps, the IMPACT radial burst and RGB split; the backdrop only pulses on kills."""
    tiny = cv2.resize(S[:, 656:1264], (27, 48), interpolation=cv2.INTER_AREA)          # the centre 9:16 strip of the footage
    pulse = glow = 0.0
    for k, lv, _ in T.KILLS:                                                           # the backdrop and the halo light up on a kill
        d = r - k
        if d >= 0:
            pulse += (0.5, 0.8, 1.2)[lv - 1] * math.exp(-d / 0.35) * FL
            glow += (0.5, 0.8, 1.3)[lv - 1] * math.exp(-d / 0.40)
    bg = cv2.resize(np.maximum(tiny, 0), (W, H), interpolation=cv2.INTER_CUBIC)
    np.maximum(bg, 0, out=bg)
    bg *= np.float32(0.115 * (1 + pulse))
    canvas = bg * UNSHADOW
    win = warp_window(S, z, ox, oy, th, ca)
    if IMPACT:
        win = impact_burst(win, i, n)
    if expo != 1.0:
        win *= np.float32(expo)
    if s["intro"]:
        win *= np.float32(0.90)
    win *= VIGW_INTRO if s["intro"] else VIGW
    np.maximum(win, 0, out=win)
    roi = canvas[WIN_Y:WIN_Y + WIN_H]
    roi += (win - roi) * MASK[:, :, None]
    canvas += (STROKE * np.float32(0.055 + 0.10 * min(glow, 1.5) * BLM))[:, :, None]
    canvas += (GLOW * np.float32(0.05 * min(glow, 2.0) * BLM))[:, :, None] * np.maximum(tiny.mean((0, 1)) * 6, 0.25).astype(np.float32)
    return canvas


def render_frame(n, store):
    r = T.frame_beat(n)
    if r >= T.LUMA_FADE[1]:                                            # after the ending fade: black, no footage needed
        return np.zeros((H, W, 3), np.uint8)
    i = T.active(r)[0]
    s = SEGS[i]
    h = s["shutter"] * DR / 2
    mp = s["map"]
    S = store.sample(s["clip"], float(mp(r - h)[0]), float(mp(r + h)[0]))
    z, ox, oy, th = cam(i, r)
    expo, ca = look(i, r)
    expo *= EXPO                                                       # LOOK exposure (1 = as before)
    if frame.VERT:
        img = compose_vertical(S, s, r, z, ox, oy, th, ca, expo, i, n)
    else:
        img = warp(S, z, ox, oy, th, ca)
        if expo != 1.0:
            img *= np.float32(expo)
        if s["intro"]:
            img *= np.float32(0.90)
        np.maximum(img, 0, out=img)
    w = key_at(s.get("white"), r)                                      # flash / burn to white of the take (whole canvas)
    if w > 0.002:
        img = burn(img, w)

    textfx.draw(img, n, r)                                             # lyric words (under the transition blur)

    q = n - CUTF[i]                                                    # frames since this take came in
    kind = s["tin"]
    if kind[0] in ("bwhip", "bzoom", "broll") and BI > 0:
        if q < BLUR_IN:
            img = blur_in(img, kind, q, i)
        img = streaks(img, kind, q, 7 + i)
    if i + 1 < len(SEGS) and not s["intro"]:                          # the last 2 frames before a cut lean into it (not in the calm intro)
        left = CUTF[i + 1] - n
        if left in (1, 2) and (KZ > 0 or FRG > 0):
            e = (0.085 if left == 1 else 0.035) * KZ
            px = (5 if left == 1 else 2) * FRG
            if KZ > 0:
                acc = np.zeros_like(img)
                for j in range(6):
                    acc += affine(img, 1.0 + e * j / 5.0)
                img = acc * np.float32(1 / 6.0)
            img = split_rgb(img, px)
    inv = False
    if IMPACT:
        if not frame.VERT:
            img = impact_burst(img, i, n)                              # kill accents: radial burst + split (vertical: inside the window)
        img, inv = impact_rays(img, i, n)                              # light rays, inverted frame (the whole canvas)

    # bloom, wide glow, saturation, grade, vignette
    if BLM > 0 or WGLOW > 0:
        small = cv2.resize(img, (W // 8, H // 8), interpolation=cv2.INTER_AREA)
        if BLM > 0:
            bloom = cv2.GaussianBlur(np.maximum(small - 0.60, 0), (0, 0), 7)
            img += cv2.resize(bloom, (W, H), interpolation=cv2.INTER_LINEAR) * np.float32((0.16 if s["intro"] else 0.09) * BLM)
        if WGLOW > 0:                                                  # LOOK wide_glow: a wide soft halo round the bright areas
            wide = cv2.GaussianBlur(np.maximum(small - 0.40, 0), (0, 0), 17.5)
            img += cv2.resize(wide, (W, H), interpolation=cv2.INTER_LINEAR) * np.float32(0.05 * WGLOW)
    if SAT > 0:
        lum = (0.2126 * img[:, :, 0] + 0.7152 * img[:, :, 1] + 0.0722 * img[:, :, 2])[:, :, None]
        img = lum + (img - lum) * np.float32(1 + 0.10 * SAT if s["intro"] else 1 + 0.20 * SAT)
    if GRADE != "neutral":
        img = opts.grade_rgb(img, GRADE)
    img *= VIG_INTRO if s["intro"] else VIG
    if s["tin"][0] == "fade" and r < s["r0"] + 0.9 and LUMA_IN is None:    # the video opens from black
        img *= np.float32(T.ease((r - s["r0"]) / 0.9) ** GAMMA)
    idx = np.clip(img * 4095.0, 0, 4095).astype(np.uint16)
    disp = OUT_LUT[idx]
    if LUMA_IN is not None and r < LUMA_IN[1]:                         # opening: the bright areas come out of black first, the shadows last
        t = 1.0 - T.ease((r - LUMA_IN[0]) / (LUMA_IN[1] - LUMA_IN[0]))
        disp = (disp - np.float32(255.0 * 1.04 * t)) * np.float32(1.0 - 0.35 * t)
    if inv:                                                            # impact frame: one inverted monochrome frame on the shot (whole canvas)
        y = 0.299 * disp[:, :, 0] + 0.587 * disp[:, :, 1] + 0.114 * disp[:, :, 2]
        disp = np.repeat((255.0 - y)[:, :, None], 3, axis=2).astype(np.float32)
    # ending: luma fade (dark areas go black first, the bright HUD last), as in the reference
    lf = (r - T.LUMA_FADE[0]) / (T.LUMA_FADE[1] - T.LUMA_FADE[0])
    if lf > 0:
        if lf >= 1:
            return np.zeros((H, W, 3), np.uint8)
        t = T.ease(lf)
        disp = (disp - np.float32(255.0 * 1.04 * t)) * np.float32(1.0 - 0.35 * t)
    disp += NOISE[(n * 7) % len(NOISE)]
    out = np.clip(disp + 0.5, 0, 255).astype(np.uint8)
    if BARS:                                                           # cinema bars 2.39:1 over everything (the transitions move the picture, not the bars)
        out[:BAR_H] = 0
        out[H - BAR_H:] = 0
    return out


def encoder(path):
    return subprocess.Popen(
        [FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(T.FPS), "-i", "-",
         "-vf", "unsharp=5:5:0.55:5:5:0.0,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv",
         "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-g", "60", "-x264-params", "aq-mode=3:aq-strength=0.9", "-colorspace", "bt709", "-color_primaries", "bt709",
         "-color_trc", "bt709", "-color_range", "tv", path], stdin=subprocess.PIPE)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit("usage: python render.py n0 n1 out.mp4          frames n0..n1-1 as video (no sound)\n"
                 "       python render.py n0 n1 out.jpg [step]   stills for inspection\n"
                 f"n0 < n1 <= {T.N_FRAMES} (the frames of timeline.py); run.sh renders the whole video in three parts")
    try:
        n0, n1, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    except ValueError:
        sys.exit(f"render.py: n0 and n1 must be whole numbers (frame numbers), got {sys.argv[1]!r} {sys.argv[2]!r}")
    if not 0 <= n0 < n1 <= T.N_FRAMES:
        sys.exit(f"render.py: frames {n0}..{n1} are outside the video: timeline.py has {T.N_FRAMES} frames, so 0 <= n0 < n1 <= {T.N_FRAMES}")
    if os.path.dirname(out) and not os.path.isdir(os.path.dirname(out)):
        sys.exit(f"render.py: the folder for {out} does not exist: create it first")
    cv2.setNumThreads(int(os.environ.get("CVT", "4")))
    store = Store()
    if out.endswith(".jpg") or out.endswith(".png"):              # still(s) for inspection
        step = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        ns = list(range(n0, n1, step))
        frames = [render_frame(n, store) for n in ns]
        if len(frames) == 1:
            sheet = frames[0]
        else:
            cols = min(len(frames), 6)
            rows = (len(frames) + cols - 1) // cols
            tw, th_ = (270, 480) if frame.VERT else (480, 270)
            sheet = np.zeros((rows * th_, cols * tw, 3), np.uint8)
            for q, f in enumerate(frames):
                t = cv2.resize(f, (tw, th_), interpolation=cv2.INTER_AREA)
                cv2.rectangle(t, (0, 0), (150, 20), (0, 0, 0), -1)
                cv2.putText(t, "%d b%.2f" % (ns[q], T.frame_beat(ns[q])), (3, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                sheet[(q // cols) * th_:(q // cols + 1) * th_, (q % cols) * tw:(q % cols + 1) * tw] = t
        if not cv2.imwrite(out, cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90]):
            sys.exit(f"render.py: cannot write {out} (the folder is read-only, the disk is full, or the name is not valid)")
    else:
        import shutil, time
        t_start = time.time()
        enc = encoder(out)
        n = n0
        try:
            for n in range(n0, n1):
                enc.stdin.write(render_frame(n, store).tobytes())
                if (n - n0) % 100 == 0:
                    print(f"{out}: frame {n} ({n - n0}/{n1 - n0})", flush=True)
            enc.stdin.close()
        except OSError:                                          # ffmpeg ended while we were still sending frames
            enc.wait()
            free = shutil.disk_usage(os.path.dirname(os.path.abspath(out))).free / 2**30
            sys.exit(f"render.py: ffmpeg stopped while it was receiving frame {n} (its own message is above this one). The usual causes: "
                     f"a full disk ({free:.1f} GB free where {out} goes), an output path ffmpeg cannot write, or an ffmpeg build without libx264 "
                     f"(check: {FF} -hide_banner -encoders). Free the cause and run the same command again.")
        except BaseException:                                    # a missing store file (sys.exit above), Ctrl+C: no half-written part left behind
            enc.kill()
            enc.wait()
            if os.path.exists(out):
                os.remove(out)
            raise
        code = enc.wait()
        if code != 0:
            sys.exit(f"render.py: ffmpeg failed (exit code {code}) while finishing {out}: its message is above this one.")
        dt = time.time() - t_start
        print(f"done {out}: {n1 - n0} frames in {dt:.0f} s = {(n1 - n0) / dt:.2f} frames/s", flush=True)
