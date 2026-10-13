"""Montage renderer.

Footage comes from the sub-frame store (real frames + RIFE in-betweens, 240/960 fps). Every output
frame integrates the footage over its shutter interval (exact time sampling + real motion blur),
and the camera (zoom / shake / transition moves) is supersampled the same way, so nothing steps.
All compositing is done in linear light. The strength of vignette, saturation, contrast, grain, bloom, shake, kill zoom, flash,
colour fringe, impact frames and the colour grade comes from LOOK in timeline.py (look.py; without LOOK the look is the default one).

usage: python render.py n0 n1 out.mp4            frames n0..n1-1 as video (no sound)
       python render.py n0 n1 out.jpg [step]     stills for inspection (one frame: full size; several: contact sheet)"""
import os, sys, math, glob, subprocess
from collections import OrderedDict
import preflight
import numpy as np
import cv2
T = preflight.timeline()
from ff import FF
import look as LOOKS
LK = LOOKS.get(T)                    # the edit options of timeline.py (LOOK); 1.0 = the default look. bars / blur_in belong to the reference style
KZ, SHAKE, FLASH, FRINGE = LK["kill_zoom"], LK["shake"], LK["flash"], LK["fringe"]

W, H = 1080, 1920
FG_W, FG_H, FG_Y = 1080, 912, 470
SRC_W, SRC_H = 1344, 1080            # stored crop of the 1920x1080 source
WIN_SRC_W = 1280.0                   # source width visible in the window at zoom 1
KSRC = WIN_SRC_W / FG_W
SHUTTER = 0.65                       # footage shutter, fraction of the output frame interval
CAM_SHUTTER = 0.85                   # shutter used for camera / transition moves
GAMMA = 2.2
DR = 1.0 / T.FPB                     # beats per output frame
C_WIN = np.array([FG_W / 2, FG_Y + FG_H / 2])
LIN = ((np.arange(256) / 255.0) ** GAMMA).astype(np.float32)
SEGS = T.SEGS

ZOOM_A = {1: 0.12 * KZ, 2: 0.17 * KZ, 3: 0.21 * KZ}


# ---------------------------------------------------------------- footage
class Store:
    def __init__(self, cache=34):
        self.keys, self.cache, self.max = {}, OrderedDict(), cache

    def avail(self, clip):
        if clip not in self.keys:
            self.keys[clip] = np.array(sorted(int(os.path.basename(f)[:-4]) for f in glob.glob(f"store/{clip}/*.jpg")))
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
        keys = self.avail(clip)
        P0, P1 = p0 * 16.0, p1 * 16.0
        i0 = max(0, int(np.searchsorted(keys, P0, side="right")) - 1)
        i1 = min(len(keys) - 1, int(np.searchsorted(keys, P1, side="left")))
        ks = keys[i0:i1 + 1].astype(float)
        if len(ks) == 1:
            return self.frame(clip, ks[0])
        if len(ks) == 0 or np.diff(ks).max() > 4.01:
            sys.exit(f"render.py: the store has no complete footage of {clip} between source frames {p0:.1f} and {p1:.1f} "
                     f"({'nothing in store/' + clip + '/' if not len(keys) else 'a gap in the sub-frames'}). "
                     "Build what the timeline needs: python ranges.py && python prep.py ranges.json, then python check_store.py (it must report 0 missing).")
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
        for key, wj in zip(ks, w):
            if wj < 0.004:
                continue
            f = self.frame(clip, key)
            acc = f * np.float32(wj) if acc is None else cv2.scaleAdd(f, float(wj), acc)
        return acc


# ---------------------------------------------------------------- camera
def cam(i, u):
    """Zoom / offset / roll of the virtual camera over segment i at beat u."""
    s = SEGS[i]
    z = ox = oy = th = 0.0
    for k, lv in s["kills"]:
        A, a = ZOOM_A[lv], 0.7
        d = u - k
        if d < 0:
            x = (d + a) / a
            if x > 0:
                z += A * x * x                                  # accelerate into the hit
        elif lv == 1:
            x = d / 1.3
            z += A * (0.5 + 0.5 * math.cos(math.pi * min(1.0, x)))   # ease back out
        else:
            z += A                                              # finishers stay in
    for a, b, amt in s["push"]:
        if u > a:
            z += amt * T.ease((u - a) / (b - a))
    for a, b in s["skill"]:
        if a < u < b:
            z += 0.06 * math.sin(math.pi * (u - a) / (b - a)) ** 2
    if i == 0:
        z += 0.10 * (1 - T.ease((u - T.R0) / 1.6))
    if s["tin"][0] == "zcut" and u < s["r0"] + 0.4:
        z += 0.18 * (1 - max(0.0, (u - s["r0"]) / 0.4)) ** 3
    if i + 1 < len(SEGS) and SEGS[i + 1]["tin"][0] == "zcut" and u > s["r1"] - 0.3:
        z += 0.22 * min(1.0, (u - (s["r1"] - 0.3)) / 0.3) ** 3
    # accents that depend only on the music position
    for k, lv, _ in T.KILLS:
        d = u - k
        if 0 <= d < 2.5:
            att = 1 - math.exp(-d / 0.03)
            env = att * math.exp(-d / 0.22)
            amp = (5.0, 8.0, 12.0)[lv - 1] * SHAKE
            ox += amp * env * math.sin(2 * math.pi * 2.7 * d + 1.7 * k)
            oy += 0.7 * amp * env * math.cos(2 * math.pi * 3.3 * d + 2.3 * k)
            th += (0.25, 0.4, 0.7)[lv - 1] * SHAKE * env * math.sin(2 * math.pi * 2.2 * d + k)
            z += 0.02 * KZ * T.punch(d)
    for k, wt in T.PULSES:
        z += 0.012 * KZ * wt * T.punch(u - k)
    return 1.0 + min(z, 0.60), ox, oy, th


def look(i, r, n):
    """Per-frame scalars for segment i: exposure pop, chromatic aberration, saturation, bars, impact."""
    expo, ca, sat, bars, imp = 1.0, 0.0006 * FRINGE, 1.0, 0.0, 0.0
    for k, lv, _ in T.KILLS:
        d = r - k
        if d >= -0.02:
            d = max(d, 0.0)
            expo += (0.55, 0.9, 1.5)[lv - 1] * FLASH * math.exp(-d / 0.10)
            ca += (0.0035, 0.005, 0.008)[lv - 1] * FRINGE * math.exp(-d / 0.25)
        if lv == 3 and LK["impact"]:
            df = n - int(round((k - T.R0) * T.FPB))
            imp = max(imp, {0: 1.0, 1: 0.5}.get(df, 0.0))
    for k, wt in T.PULSES:
        d = r - k
        if d >= 0:
            expo += 0.12 * FLASH * wt * math.exp(-d / 0.12)
    for a, b in SEGS[i]["skill"]:
        if a < r < b:
            ca += 0.002 * FRINGE * math.sin(math.pi * (r - a) / (b - a))
    if SEGS[i]["bars"]:
        a, b = SEGS[i]["bars"]
        if a < r < b:
            bars = T.ease((r - a) / 0.35) * T.ease((b - r) / 0.35)
            sat = 1.0 - 0.14 * bars
    return expo, ca, sat, bars, imp


def trans(kind, p, dr):
    """Geometry of an overlapping transition at progress p: for the outgoing (A) and incoming (B) clip
    -> (zoom multiplier, alpha, (tx, ty, rot_deg, scale)) and an exposure factor."""
    ident = (0.0, 0.0, 0.0, 1.0)
    if kind == "whip":
        e = T.ease5(p)
        dx, dy = dr
        DX, DY = (W + 80) * dx, 1560 * dy
        bell = math.sin(math.pi * p)
        sc = 1 + 0.035 * bell
        return ((1.0, 1.0, (-DX * e, -DY * e, 3.5 * e * (dx + dy), sc)),
                (1.0, 1.0, (DX * (1 - e), DY * (1 - e), -3.5 * (1 - e) * (dx + dy), sc)), 1 + 0.25 * bell ** 2)
    if kind == "spin":
        a = p ** 2.2
        b = (1 - p) ** 2.2
        return ((1.0, 1 - T.ease((p - 0.38) / 0.22), (0.0, 0.0, 75 * a, 1 + 1.0 * a)),
                (1.0, T.ease((p - 0.40) / 0.22), (0.0, 0.0, -75 * b, 1 + 1.0 * b)), 1 + 0.5 * math.sin(math.pi * p) ** 3)
    if kind == "zoom":                                        # punch through the middle of one clip into the next
        za = 1 + 2.4 * min(1.0, p / 0.52) ** 2.6
        zb = 1 + 1.7 * min(1.0, (1 - p) / 0.52) ** 2.6
        return ((za, 1 - T.ease((p - 0.44) / 0.12), ident),
                (zb, T.ease((p - 0.44) / 0.12), ident), 1 + 0.8 * math.sin(math.pi * p) ** 4)
    e = T.ease(p)                                             # dissolve / soft
    return ((1.0, 1.0, ident), (1.0, e, ident), 1.0)


# ---------------------------------------------------------------- compositing helpers
def rot(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s], [s, c]])


def rounded_mask(w, h, r):
    m = np.zeros((h * 4, w * 4), np.uint8)
    cv2.rectangle(m, (r * 4, 0), (w * 4 - r * 4, h * 4), 255, -1)
    cv2.rectangle(m, (0, r * 4), (w * 4, h * 4 - r * 4), 255, -1)
    for cx, cy in ((r * 4, r * 4), (w * 4 - r * 4, r * 4), (r * 4, h * 4 - r * 4), (w * 4 - r * 4, h * 4 - r * 4)):
        cv2.circle(m, (cx, cy), r * 4, 255, -1)
    return cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0


MASK = rounded_mask(FG_W, FG_H, 34)
_BAR_MASKS = {}


def bar_mask(hb):
    """Window mask shortened by hb rows at the top and bottom, corners still rounded."""
    if hb not in _BAR_MASKS:
        m = np.zeros((FG_H, FG_W), np.float32)
        m[hb:FG_H - hb] = rounded_mask(FG_W, FG_H - 2 * hb, 34)
        _BAR_MASKS[hb] = m
    return _BAR_MASKS[hb]


_inner = cv2.erode(MASK, np.ones((5, 5), np.uint8))
STROKE = np.zeros((H, W), np.float32)
STROKE[FG_Y:FG_Y + FG_H] = cv2.GaussianBlur(MASK - _inner, (0, 0), 1.2)
GLOW = np.zeros((H, W), np.float32)
GLOW[FG_Y:FG_Y + FG_H] = MASK
GLOW = np.clip(cv2.GaussianBlur(GLOW, (0, 0), 26) - GLOW, 0, 1)        # halo outside the window
SHADOW = np.zeros((H, W), np.float32)
SHADOW[FG_Y + 12:FG_Y + FG_H + 40] = 1.0
SHADOW = cv2.GaussianBlur(SHADOW, (0, 0), 40) * 0.62
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
VR = 1.0 + 0.03 * max(0.0, LK["vignette"] - 1)           # a strong vignette also reaches a little further in (the window's corners sit well inside the canvas)
VIG = np.maximum(1.0 - 0.30 * LK["vignette"] * np.clip(((xx - W / 2) / (W * 0.80 / VR)) ** 2 + ((yy - H / 2) / (H * 0.72 / VR)) ** 2, 0, 1) ** 1.3, 0.0)
VIG = VIG[:, :, None].astype(np.float32)
del yy, xx
# linear -> display curve with a gentle S-shaped contrast, as a 4096-entry table
_x = np.linspace(0, 1, 4096)
_g = _x ** (1 / GAMMA)
_g = np.clip(_g + 0.030 * LK["contrast"] * np.sin(2 * math.pi * (_g - 0.5)), 0, 1)   # mild S-curve: deeper shadows, brighter highlights
OUT_LUT = (_g * 255).astype(np.float32)
# dither for every pixel (no banding in the smooth backdrop) plus a fine grain outside the gameplay window
_rng = np.random.default_rng(11)
_outside = np.ones((H, W), np.float32)
_outside[FG_Y:FG_Y + FG_H] = 1 - MASK
if LK["grain"] > 1:                    # above the default the grain also reaches onto the gameplay window (0.2 of the backdrop's per unit above 1)
    _outside[FG_Y:FG_Y + FG_H] += MASK * np.float32(0.2 * (LK["grain"] - 1))
NOISE = [(_rng.uniform(-0.5, 0.5, (H, W)).astype(np.float32)
          + _rng.normal(0, 1.25 * LK["grain"], (H, W)).astype(np.float32) * _outside)[:, :, None] for _ in range(10)]


def warp(S, z, ox, oy, th, ca, tx, ty, phi, sw, roi):
    """Source image -> canvas (or the window rows only when roi). Chromatic aberration by per-channel zoom."""
    out_h, y_off = (FG_H, FG_Y) if roi else (H, 0)
    R = rot(th - phi)
    c = C_WIN + np.array([tx, ty]) - np.array([0, y_off])
    sc = np.array([SRC_W / 2 + ox, SRC_H / 2 + oy])
    chans = []
    for ci, dz in enumerate((1 + ca, 1.0, 1 - ca)):
        A = (KSRC / (z * dz * sw)) * R
        M = np.hstack([A, (sc - A @ c)[:, None]]).astype(np.float64)
        chans.append(cv2.warpAffine(S[:, :, ci], M, (W, out_h), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                                    borderMode=cv2.BORDER_REFLECT_101))
    return cv2.merge(chans)


def warp_mask(tx, ty, phi, sw):
    B = rot(-phi) / sw
    c = C_WIN + np.array([tx, ty])
    M = np.hstack([B, (np.array([FG_W / 2, FG_H / 2]) - B @ c)[:, None]]).astype(np.float64)
    return cv2.warpAffine(MASK, M, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_CONSTANT)


SAT_FIN = 1.0 + 0.16 * min(LK["saturation"], 1.0) + 0.22 * max(0.0, LK["saturation"] - 1)    # colour boost of the finished frame (linear light): 1.16 by default


def render_frame(n, store):
    r = T.frame_beat(n)
    a, b, p, tin = T.active(r)
    layers = [a] if b is None else [a, b]
    h = SHUTTER * DR / 2
    src, tiny, looks = {}, {}, {}
    for i in layers:
        mp = SEGS[i]["map"]
        p0, p1 = float(mp(r - h)[0]), float(mp(r + h)[0])
        S = store.sample(SEGS[i]["clip"], p0, p1)
        expo, ca, sat, bars, imp = looks[i] = look(i, r, n)
        if sat != 1.0 or imp > 0:
            S = S.copy()
            lum = (0.2126 * S[:, :, 0] + 0.7152 * S[:, :, 1] + 0.0722 * S[:, :, 2])[:, :, None]
            if sat != 1.0:
                S = lum + (S - lum) * np.float32(sat)
            if imp > 0:                                        # impact frame: hard inverted monochrome
                g = np.clip((lum - 0.03) / 0.30, 0, 1)
                g = 1 - g * g * (3 - 2 * g)
                S = S * np.float32(1 - imp) + np.repeat(g, 3, axis=2) * np.float32(imp)
        src[i] = S
        tiny[i] = cv2.resize(S[:, 368:976], (27, 48), interpolation=cv2.INTER_AREA)

    # backdrop: heavily blurred copy of the footage, reacting to the beat
    kind = tin[0] if b is not None else None
    e_bg = T.ease5(p) if b is not None else 0.0
    t_bg = tiny[a] if b is None else tiny[a] * np.float32(1 - e_bg) + tiny[b] * np.float32(e_bg)
    pulse = glow = streak = 0.0
    for k, lv, _ in T.KILLS:
        d = r - k
        if d >= 0:
            pulse += (0.5, 0.8, 1.2)[lv - 1] * math.exp(-d / 0.35)
            glow += (0.5, 0.8, 1.3)[lv - 1] * math.exp(-d / 0.40)
            streak += (0.10, 0.22, 0.40)[lv - 1] * math.exp(-d / 0.30)
    for k, wt in T.PULSES:
        d = r - k
        if d >= 0:
            pulse += 0.30 * wt * math.exp(-d / 0.30)
            glow += 0.35 * wt * math.exp(-d / 0.30)
    slow_dim = 1.0
    for i in layers:
        if SEGS[i]["bars"] and SEGS[i]["bars"][0] < r < SEGS[i]["bars"][1]:
            slow_dim = 1 - 0.30 * looks[i][3]
    bg = cv2.resize(np.maximum(t_bg, 0), (W, H), interpolation=cv2.INTER_CUBIC)
    np.maximum(bg, 0, out=bg)
    bg *= np.float32(0.115 * slow_dim * (1 + pulse))

    # how many camera sub-samples does this frame need? (displacement of a window corner across the shutter)
    hc = CAM_SHUTTER * DR / 2

    def geom(i, u):
        z, ox, oy, th = cam(i, u)
        zm, al, wt_ = 1.0, 1.0, (0.0, 0.0, 0.0, 1.0)
        if b is not None:
            pu = min(1.0, max(0.0, (u - (SEGS[b]["r0"] - tin[1] / 2)) / tin[1]))
            ta, tb, _ = trans(kind, pu, tin[2] if len(tin) > 2 else (0, 0))
            zm, al, wt_ = ta if i == a else tb
        return z * zm, ox, oy, th, al, wt_

    disp = 0.0
    for i in layers:
        g0, g1 = geom(i, r - hc), geom(i, r + hc)
        dz = abs(g1[0] / g0[0] - 1) * 640
        dt = math.hypot(g1[5][0] - g0[5][0], g1[5][1] - g0[5][1]) + abs(g1[5][2] - g0[5][2]) * 11 + abs(g1[5][3] / g0[5][3] - 1) * 640
        ds = math.hypot(g1[1] - g0[1], g1[2] - g0[2]) / KSRC + abs(g1[3] - g0[3]) * 11
        disp = max(disp, dz + dt + ds)
    K = int(min(40, max(1, math.ceil(disp / 4.0))))

    moving = b is not None and kind in ("whip", "spin")
    barred = False
    acc = np.zeros((H, W, 3), np.float32)
    win_cover = 0.0
    for j in range(K):
        u = r + ((j + 0.5) / K - 0.5) * 2 * hc if K > 1 else r
        canvas = bg.copy()
        sh_k = 1.0
        if moving:
            sh_k = 0.0
        canvas *= (1 - SHADOW * sh_k)[:, :, None]
        for i in layers:
            z, ox, oy, th, al, (tx, ty, phi, sw) = geom(i, u)
            if al <= 0.003:
                continue
            expo, ca, sat, bars, imp = looks[i]
            if moving:
                img = warp(src[i], z, ox, oy, th, ca, tx, ty, phi, sw, roi=False)
                m = warp_mask(tx, ty, phi, sw) * np.float32(al)
                if expo != 1.0:
                    img *= np.float32(expo)
                canvas += (img - canvas) * m[:, :, None]
            else:
                img = warp(src[i], z, ox, oy, th, ca, 0, 0, 0, 1.0, roi=True)
                if expo != 1.0:
                    img *= np.float32(expo)
                mk = bar_mask(int(round(66 * bars))) if bars > 0.01 else MASK   # slow motion: the window narrows to a wider frame
                barred = barred or bars > 0.01
                m = mk if al >= 0.999 else mk * np.float32(al)
                roi = canvas[FG_Y:FG_Y + FG_H]
                roi += (img - roi) * m[:, :, None]
        acc += canvas
    canvas = acc if K == 1 else acc * np.float32(1.0 / K)

    # transition exposure, window stroke + halo, bloom and horizontal light streaks (light spills onto the backdrop)
    if b is not None:
        canvas *= np.float32(trans(kind, p, tin[2] if len(tin) > 2 else (0, 0))[2])
    if not moving and not barred:
        canvas += (STROKE * np.float32(0.055 + 0.10 * min(glow, 1.5)))[:, :, None]
        canvas += (GLOW * np.float32(0.05 * min(glow, 2.0) * LK["bloom"]))[:, :, None] * np.maximum(t_bg.mean((0, 1)) * 6, 0.25).astype(np.float32)
    if LK["bloom"] > 0:
        small = cv2.resize(canvas, (W // 8, H // 8), interpolation=cv2.INTER_AREA)
        bright = np.maximum(small - 0.62, 0)
        bloom = cv2.GaussianBlur(bright, (0, 0), 7)
        canvas += cv2.resize(bloom, (W, H), interpolation=cv2.INTER_LINEAR) * np.float32((0.07 + 0.20 * min(glow, 1.5)) * LK["bloom"])
        if streak > 0.01:
            st = cv2.GaussianBlur(bright, (0, 0), sigmaX=30, sigmaY=1.4)
            canvas += cv2.resize(st, (W, H), interpolation=cv2.INTER_LINEAR) * np.float32(0.55 * min(streak, 0.5) * LK["bloom"])

    # finishing: saturation, grade, vignette, fades, display transfer
    if SAT_FIN != 1.0:
        lum = (0.2126 * canvas[:, :, 0] + 0.7152 * canvas[:, :, 1] + 0.0722 * canvas[:, :, 2])[:, :, None]
        canvas = lum + (canvas - lum) * np.float32(SAT_FIN)
    if LK["grade"] != "neutral":
        canvas = LOOKS.grade_rgb(canvas, LK["grade"], LK["grade_amount"])
    canvas *= VIG
    fade = min(1.0, (r - T.R0) / 0.25) * (1 - T.ease((r - T.FADE_OUT[0]) / (T.FADE_OUT[1] - T.FADE_OUT[0] - 0.1)))
    if fade < 0.999:
        canvas *= np.float32(max(0.0, fade) ** GAMMA)
    idx = np.clip(canvas * 4095.0, 0, 4095).astype(np.uint16)
    disp = OUT_LUT[idx]
    disp += NOISE[(n * 7) % len(NOISE)] * np.float32(min(1.0, max(0.0, fade) * 4))
    return np.clip(disp + 0.5, 0, 255).astype(np.uint8)


def encoder(path):
    return subprocess.Popen(
        [FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(T.FPS), "-i", "-",
         "-vf", "unsharp=5:5:0.30:5:5:0.0,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv",
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
        frames = [render_frame(n, store) for n in range(n0, n1, step)]
        cols = min(len(frames), 10)
        rows = (len(frames) + cols - 1) // cols
        sc = 0.25 if len(frames) > 1 else 1.0
        tw, th_ = int(W * sc), int(H * sc)
        sheet = np.zeros((rows * th_, cols * tw, 3), np.uint8)
        for q, f in enumerate(frames):
            t = cv2.resize(f, (tw, th_), interpolation=cv2.INTER_AREA)
            if len(frames) > 1:                                    # label each tile with its frame number
                cv2.rectangle(t, (0, 0), (64, 22), (0, 0, 0), -1)
                cv2.putText(t, str(n0 + q * step), (4, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
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
                if (n - n0) % 25 == 0:
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
