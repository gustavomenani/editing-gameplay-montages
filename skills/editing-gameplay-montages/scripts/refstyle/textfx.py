"""Lyric words on screen, in the style of the reference: heavy condensed caps (Impact), letters popping in in
random order (one every 1-2 frames, white flash + colour split on the pop), metallic gradient fill, soft
glow, held while the word is sung, then a quick fade. Composited in linear light, before the transition
blur, so a whip blurs the word together with the footage.

Horizontal frame: caps of 250-280 px on the exact middle of the 1920x1080 frame. Vertical frame (timeline FRAME =
"vertical", frame.py): the same words on the exact middle of the 1080x1920 canvas, i.e. over the middle of the
gameplay window, caps at 0.62 of the horizontal ones and never wider than 940 px.

T.TEXT = [(beat_in, beat_out, "WORD", style)], style in STYLES.  draw(canvas, n, r) paints frame n in place."""
import math, os
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
import timeline as T

_FONTS = [os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "impact.ttf"),
          os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts", "impact.ttf")]      # Impact installed "for me only"
FONT = os.environ.get("IMPACT_FONT") or next((f for f in _FONTS if os.path.exists(f)), _FONTS[0])
if not os.path.exists(FONT):
    raise SystemExit(f"textfx.py: the Impact font is not at {FONT}. Install Impact, or set IMPACT_FONT to its .ttf path "
                     "(another heavy condensed font works but changes the look).")
import frame
W, H = frame.W, frame.H
GAMMA = 2.2
MAXW = frame.WORD_MAXW
STYLES = {
    # strength = how much of the word is laid over the picture; ov = share of it that is an overlay blend
    # (keeps the texture of the footage visible inside the letters) instead of flat colour.
    # The user about the first render, where the letters were 82-94 % opaque: "as letras estavam sem
    # transparencia alguma 100% solidas". In the reference the footage shows through the letters.
    "red":    dict(top=(255, 110, 96), mid=(238, 32, 40), bot=(120, 6, 16), glow=(255, 28, 34), glow_a=0.26, strength=0.80, ov=0.50, cap=280, cy=0.5, gloss=0.22),
    "gold":   dict(top=(255, 246, 190), mid=(250, 204, 92), bot=(176, 110, 36), glow=(255, 196, 90), glow_a=0.08, strength=0.66, ov=0.62, cap=250, cy=0.5, gloss=0.14),
    "silver": dict(top=(255, 255, 255), mid=(214, 222, 236), bot=(140, 150, 170), glow=(205, 222, 255), glow_a=0.07, strength=0.64, ov=0.62, cap=250, cy=0.5, gloss=0.12),
    "white":  dict(top=(255, 255, 255), mid=(250, 250, 250), bot=(222, 222, 230), glow=(255, 255, 255), glow_a=0.07, strength=0.62, ov=0.62, cap=250, cy=0.5, gloss=0.0),
}
for _st in STYLES.values():
    _st["cap"] = int(round(_st["cap"] * frame.CAP_K))             # vertical: 0.62 (the caps of cover.py are set after this, in its own frame)
PAD = 70                              # room around the word for glow / shadow
LP = 18                               # room around a letter for the colour split


def lin(c):
    return (np.asarray(c, np.float32) / 255.0) ** GAMMA


_f = ImageFont.truetype(FONT, 400)
_b = _f.getbbox("H")
CAPR = (_b[3] - _b[1]) / 400.0


def frame_of(beat):
    return int(round((beat - T.R0) * T.FPB))


def duck(r):
    """The word steps back while a shot fires, so the kill itself stays readable."""
    m = 0.0
    for k, lv, _ in T.KILLS:
        d = r - k
        if -0.16 < d < 0.28:
            m = max(m, T.ease((d + 0.16) / 0.06) * T.ease((0.28 - d) / 0.08))
    return 1.0 - 0.35 * m


class Cue:
    def __init__(self, j):
        self.a, self.b, self.word, style = T.TEXT[j]
        st = self.st = STYLES[style]
        nxt = T.TEXT[j + 1][0] if j + 1 < len(T.TEXT) else 1e9
        self.fade = min(0.36, max(0.08, nxt - self.b - 0.02))      # gone before the next word pops in
        self.n_in = frame_of(self.a)
        self.built = False
        rng = np.random.default_rng(1000 + j)
        letters = [i for i, ch in enumerate(self.word) if ch != " "]
        order = rng.permutation(len(letters))
        step = min(1.0, 3.0 / max(1, len(letters)))      # the whole word is there within 3 frames of its onset
        self.appear = {letters[q]: self.n_in + int(round(order[q] * step)) for q in range(len(letters))}
        self.n_settled = self.n_in + int(round((len(letters) - 1) * step)) + 3
        self.n_end = frame_of(self.b + self.fade) + 1

    def build(self):
        st, word = self.st, self.word
        size = st["cap"] / CAPR
        for _ in range(2):
            font = ImageFont.truetype(FONT, int(round(size)))
            track = st.get("track", 0.018) * size          # letter spacing (the cover's subtitle uses a wide one)
            xs, x = [], 0.0
            for ch in word:
                xs.append(x)
                x += font.getlength(ch) + track
            tot = x - track
            if tot <= MAXW:
                break
            size *= MAXW / tot
        cap = CAPR * size
        self.hb = hb = int(cap * 1.55) + 2 * PAD
        self.y0 = int(round(st["cy"] * H - cap / 2 - 0.42 * cap)) - PAD          # top of the band on the canvas
        base = PAD + 0.42 * cap + cap                                              # baseline inside the band
        x0 = W / 2 - tot / 2
        # vertical gradient over the cap height, with a glossy band in the upper third
        yy = (np.arange(hb, dtype=np.float32) - (base - cap)) / cap
        t = np.clip(yy, 0, 1)[:, None]
        top, mid, bot = (np.asarray(st[c], np.float32) / 255.0 for c in ("top", "mid", "bot"))      # display values
        g = np.where(t < 0.48, top + (mid - top) * (t / 0.48), mid + (bot - mid) * ((t - 0.48) / 0.52)).astype(np.float32)
        gloss = st["gloss"] * np.exp(-((yy - 0.30) / 0.11) ** 2)[:, None] * (yy[:, None] < 0.47)
        self.grad = np.clip(g + gloss.astype(np.float32), 0, 1.2)[:, None, :]      # (hb, 1, 3)
        self.tiles = {}
        full = np.zeros((hb, W), np.float32)
        for i, ch in enumerate(word):
            if ch == " ":
                continue
            wt = int(math.ceil(font.getlength(ch))) + 2 * LP
            im = Image.new("L", (wt, hb), 0)
            ImageDraw.Draw(im).text((LP, base), ch, font=font, fill=255, anchor="ls")
            m = np.asarray(im, np.float32) / 255.0
            xt = int(round(x0 + xs[i])) - LP
            # bevel: a light rim on the upper edges, a darker one on the lower edges
            up = np.zeros_like(m); up[3:] = m[:-3]
            dn = np.zeros_like(m); dn[:-3] = m[3:]
            hi = np.clip(m - up, 0, 1)[:, :, None] * 0.22
            lo = np.clip(m - dn, 0, 1)[:, :, None] * 0.30
            col = np.clip(self.grad + hi, 0, 1.3) * (1 - lo)
            self.tiles[i] = (xt, m, (col * m[:, :, None]).astype(np.float32))
        # the user: "tem que centralizar a letra no meio da tela": the visible ink is centred exactly on W/2
        # (advance widths carry side bearings) and the caps on H/2 (cy above)
        lo = min(xt + int(np.argmax(m.max(0) > 0.5)) for xt, m, _ in self.tiles.values())
        hi = max(xt + m.shape[1] - 1 - int(np.argmax(m.max(0)[::-1] > 0.5)) for xt, m, _ in self.tiles.values())
        dx = int(round(W / 2.0 - (lo + hi + 1) / 2.0))
        self.tiles = {i: (xt + dx, m, c) for i, (xt, m, c) in self.tiles.items()}
        self.ink = (lo + dx, hi + dx)
        for xt, m, _ in self.tiles.values():
            wt = m.shape[1]
            a0, a1 = max(0, xt), min(W, xt + wt)
            full[:, a0:a1] = np.maximum(full[:, a0:a1], m[:, a0 - xt:a1 - xt])
        self.glow = np.clip(cv2.GaussianBlur(full, (0, 0), 16) - 0.55 * full, 0, 1)      # mostly outside the letters
        sh = np.zeros_like(full); sh[7:] = full[:-7]
        self.shadow = np.clip(cv2.GaussianBlur(sh, (0, 0), 9) - 0.0, 0, 1)
        self.glowcol = lin(st["glow"])
        self.nlet = len(self.tiles)
        self.settled = None
        self.built = True

    def layer(self, n):
        """(alpha per channel, premultiplied colour, share of letters visible) for frame n."""
        if n >= self.n_settled and self.settled is not None:
            return self.settled
        a3 = np.zeros((self.hb, W, 3), np.float32)
        c3 = np.zeros((self.hb, W, 3), np.float32)
        vis = 0
        for i, (xt, m, colm) in self.tiles.items():
            age = n - self.appear[i]
            if age < 0:
                continue
            vis += 1
            fl = {0: 1.0, 1: 0.6, 2: 0.25}.get(age, 0.0)
            wt = m.shape[1]
            a0, a1 = max(0, xt), min(W, xt + wt)
            sl = slice(a0 - xt, a1 - xt)
            if fl > 0:
                dx = int(round(9 * fl))
                colf = colm * (1 - fl) + m[:, :, None] * fl * 1.15            # flash towards white
                for c, s in enumerate((dx, 0, -dx)):
                    mm = np.roll(m, s, axis=1) if s else m
                    cc = np.roll(colf[:, :, c], s, axis=1) if s else colf[:, :, c]
                    a3[:, a0:a1, c] = np.maximum(a3[:, a0:a1, c], mm[:, sl])
                    c3[:, a0:a1, c] = np.maximum(c3[:, a0:a1, c], cc[:, sl])
            else:
                a3[:, a0:a1] = np.maximum(a3[:, a0:a1], m[:, sl, None])
                c3[:, a0:a1] = np.maximum(c3[:, a0:a1], colm[:, sl])
        out = (a3, c3, vis / max(1, self.nlet))
        if n >= self.n_settled:
            self.settled = out
        return out


CUES = [Cue(j) for j in range(len(T.TEXT))]


def draw(canvas, n, r):
    """Paint the words that are on screen at frame n (beat r) onto the linear-light canvas, in place."""
    for cue in CUES:
        if n < cue.n_in or n > cue.n_end:
            if cue.built and n > cue.n_end + 2:
                cue.tiles, cue.settled, cue.built = {}, None, False      # free the memory once the word is gone
            continue
        if not cue.built:
            cue.build()
        f = 1.0 - T.ease((r - cue.b) / cue.fade)
        f *= duck(r)
        if f <= 0.004:
            continue
        a3, c3, share = cue.layer(n)
        st = cue.st
        y0, y1 = cue.y0, cue.y0 + cue.hb
        ya, yb = max(0, y0), min(H, y1)
        reg = canvas[ya:yb]
        sl = slice(ya - y0, yb - y0)
        a3, c3 = a3[sl], c3[sl]
        reg *= (1 - cue.shadow[sl, :, None] * np.float32(0.12 * f * share))
        # translucent letters, as in the reference: mostly an overlay blend (the footage keeps its texture inside
        # the letters, dark things in front stay dark) plus some flat colour so the word still reads on dark scenes
        base = np.clip(reg, 0, 1) ** np.float32(1 / GAMMA)                 # display values
        t = np.clip(c3 / np.maximum(a3, 1e-3), 0, 1)                        # letter colour, un-premultiplied
        ov = np.where(base < 0.5, 2 * base * t, 1 - 2 * (1 - base) * (1 - t))
        mix = ov * np.float32(st["ov"]) + t * np.float32(1 - st["ov"])
        out = base + a3 * np.float32(st["strength"] * f) * (mix - base)
        reg[:] = np.clip(out, 0, 1) ** np.float32(GAMMA)
        reg += cue.glow[sl, :, None] * (cue.glowcol * np.float32(st["glow_a"] * f * share))
