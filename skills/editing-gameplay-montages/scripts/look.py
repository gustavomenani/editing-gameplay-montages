"""The edit options ("the look") that both renderers read: how strong the vignette, saturation, contrast, grain, bloom,
camera shake, kill zoom, exposure flash and colour fringing are, whether the level-3 impact frames are on, and the colour grade.

timeline.py sets them with one optional dict, LOOK. Without it (or with {} or "padrao") the render is exactly what it was
before the options existed.

    LOOK = "intensa"                                   # a preset: "suave", "padrao" (= nothing changed), "intensa", "maxima", "modelo"
    LOOK = {"vignette": 1.6, "shake": 0}               # single options (multipliers of the default look)
    LOOK = {"preset": "intensa", "shake": 0.3, "grade": "cool"}      # a preset, then single options on top of it

Every number is a multiplier of what the renderer does by default: 1 = as before, 0 = off, 2 = clearly strong. Below 1 the
scale is linear; vignette, saturation, contrast and grain climb faster above 1 (UP_GAIN: 2 is 1 + (2 - 1) x gain, so the top of
the range is something a viewer sees, not a 15 % nudge). get() returns the scaled numbers, so a renderer just multiplies its own
amplitude by them. Exceptions: exposure is a multiplier of the light (1 = as before, 0.5..1.5); wide_glow is an amount (0 = none, the
default; 1 = a clear halo); intro_vignette follows vignette unless set (the reference style's intro takes have a stronger vignette).
The preset "modelo" is the look of the worked example's reference-style edit (brighter, saturated, a visible vignette, bloom and glow).
In the reference style the accents a timeline.py asks for with IMPACT / BUMPS follow these options: kill_zoom scales the radial burst
and the bump nudge, fringe the RGB split, flash the bump light, and impact False removes the inverted level-3 frame.
`python look.py` prints the table. render.py (house style) and refstyle/render.py (reference style) call get(T);
preflight.py calls problems(T), so a misspelled option or an out-of-range value stops the render with a sentence that says
what to write instead. Options a style has no use for are accepted and ignored there (the house style has no cinema bars
and no blur-in cut; each renderer uses the options that have an effect in its style)."""
import difflib, math, sys, unicodedata

# key -> (kind, lo, hi, what it changes). kind: "mult" (number lo..hi), "bool", "grade"
KEYS = {
    "vignette":   ("mult", 0.0, 2.0, "darkening of the corners (0 = none)"),
    "saturation": ("mult", 0.0, 2.0, "colour boost of the finished frame (0 = the footage's own colour, 2 = a lot more)"),
    "contrast":   ("mult", 0.0, 2.0, "strength of the S-shaped tone curve: deeper shadows, brighter highlights (0 = straight)"),
    "grain":      ("mult", 0.0, 2.0, "film grain on the backdrop (house) / on the picture (reference); above 1 it also reaches the gameplay window"),
    "bloom":      ("mult", 0.0, 2.0, "light spill from bright areas and kill flashes (house: bloom, streaks, halo around the window)"),
    "shake":      ("mult", 0.0, 2.0, "camera tremor after a kill (0 = steady camera)"),
    "kill_zoom":  ("mult", 0.0, 1.5, "the short eased zoom punch on kills and beats; capped at 1.5 so it stays an accent"),
    "flash":      ("mult", 0.0, 2.0, "exposure pop on kills and beats (0 = none)"),
    "fringe":     ("mult", 0.0, 2.0, "chromatic aberration: red/blue colour split at the edges (0 = none)"),
    "impact":     ("bool", None, None, "the hard inverted impact frame on level-3 kills (False = off; reference style: only when timeline.py sets IMPACT, which decides the levels)"),
    "grade":      ("grade", None, None, "colour grade: neutral, warm, cool, teal_orange, mono, vibrant"),
    "grade_amount": ("mult", 0.0, 2.0, "how strong the grade is (0.5 = a light touch, 1 = the grade, 2 = pushed; mono is a full black-and-white from 1)"),
    "bars":       ("bool", None, None, "cinema bars 2.39:1 (reference style, horizontal frame only; the house style never has them)"),
    "blur_in":    ("mult", 0.0, 2.0, "strength of the blur-in cut effect (reference style only)"),
    "exposure":   ("mult", 0.5, 1.5, "brightness of the picture before the colour work, in linear light (1 = as before; reference style only)"),
    "wide_glow":  ("mult", 0.0, 2.0, "a wide soft halo round the bright areas on top of the bloom (0 = none, the default; 1 = a clear halo; reference style only)"),
    "intro_vignette": ("mult", 0.0, 2.0, "darkening of the corners in the dreamy intro takes of the reference style (default: the same multiplier as vignette)"),
}
DEFAULTS = {"vignette": 1.0, "saturation": 1.0, "contrast": 1.0, "grain": 1.0, "bloom": 1.0, "shake": 1.0,
            "kill_zoom": 1.0, "flash": 1.0, "fringe": 1.0, "impact": True, "grade": "neutral", "grade_amount": 1.0, "bars": False, "blur_in": 1.0,
            "exposure": 1.0, "wide_glow": 0.0, "intro_vignette": None}      # intro_vignette None = follows vignette (get() fills it in)
UP_GAIN = {"vignette": 3.5, "saturation": 2.5, "contrast": 2.5, "grain": 2.5, "intro_vignette": 3.5}      # above 1: 1 + (k - 1) x gain (applied in get())
GRADES = ("neutral", "warm", "cool", "teal_orange", "mono", "vibrant")
PRESETS = {
    "suave":   {"vignette": 0.5, "saturation": 0.5, "contrast": 0.5, "grain": 0.5, "bloom": 0.6, "shake": 0.4, "kill_zoom": 0.5,
                "flash": 0.45, "fringe": 0.4, "blur_in": 0.6},
    "padrao":  {},
    "intensa": {"vignette": 1.5, "saturation": 1.5, "contrast": 1.5, "grain": 1.5, "bloom": 1.5, "shake": 1.5, "kill_zoom": 1.3,
                "flash": 1.5, "fringe": 1.6, "blur_in": 1.5},
    "maxima":  {"vignette": 2.0, "saturation": 1.8, "contrast": 1.8, "grain": 1.8, "bloom": 2.0, "shake": 2.0, "kill_zoom": 1.5,
                "flash": 2.0, "fringe": 2.0, "blur_in": 2.0},
    # the look of the worked example (reference style): brighter, more saturated, a visible vignette, a firmer S-curve, bloom and a wide
    # glow. Measured on the worked example's own frames (horizontal): mean luma, HSV saturation and corner/centre brightness within a few %
    "modelo":  {"exposure": 1.10, "saturation": 1.24, "vignette": 1.31, "intro_vignette": 1.06, "contrast": 1.2, "bloom": 1.22, "wide_glow": 1.0},
}
ALIASES = {"glow": "bloom"}                       # the reference style calls the bloom "glow"
# words a user is likely to write -> the key / grade / preset they mean (only used for "did you mean")
KEY_HINTS = {"vinheta": "vignette", "saturacao": "saturation", "saturaçao": "saturation", "cor": "grade", "contraste": "contrast",
             "granulado": "grain", "graos": "grain", "grao": "grain", "ruido": "grain", "brilho": "bloom", "luz": "bloom",
             "tremor": "shake", "tremida": "shake", "zoom": "kill_zoom", "killzoom": "kill_zoom", "clarao": "flash",
             "aberracao": "fringe", "aberracao_cromatica": "fringe", "chromatic": "fringe", "impacto": "impact",
             "barras": "bars", "tarjas": "bars", "desfoque": "blur_in", "blurin": "blur_in", "blur": "blur_in",
             "vignete": "vignette", "vigniette": "vignette", "saturaction": "saturation", "saturacion": "saturation",
             "look": "preset", "estilo": "preset", "intensidade": "grade_amount", "forca": "grade_amount", "grade_strength": "grade_amount",
             "amount": "grade_amount"}
GRADE_HINTS = {"quente": "warm", "frio": "cool", "fria": "cool", "teal": "teal_orange", "tealorange": "teal_orange",
               "teal_laranja": "teal_orange", "cinema": "teal_orange", "pb": "mono", "p&b": "mono", "preto_e_branco": "mono",
               "bw": "mono", "cinza": "mono", "neutro": "neutral", "normal": "neutral", "none": "neutral", "vibrante": "vibrant",
               "vivid": "vibrant"}
PRESET_HINTS = {"padrão": "padrao", "default": "padrao", "normal": "padrao", "max": "maxima", "máxima": "maxima", "maximo": "maxima",
                "forte": "intensa", "intenso": "intensa", "soft": "suave", "leve": "suave", "fraca": "suave"}
CAP_WHY = {"kill_zoom": "a kill zoom above 1.5 stops being a short accent and starts to enlarge the gameplay"}

_printed = set()


def _norm(s):
    """lower case, no accents, spaces and dashes -> underscore."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().strip().lower()
    return s.replace(" ", "_").replace("-", "_")


def _mean(word, valid, hints):
    w = _norm(word)
    hit = hints.get(w) or hints.get(str(word).strip().lower())
    if hit is None:
        close = difflib.get_close_matches(w, list(valid), 1, 0.55)
        hit = close[0] if close else None
    return f"; did you mean \"{hit}\"?" if hit else ""


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _resolve(raw):
    """-> (look dict, errors, clamps). errors: the LOOK cannot be read (unknown name, wrong type). clamps: [(key, given, used, message)]
    for numbers outside the allowed range (the look still gets a usable value)."""
    errors, clamps = [], []
    look = dict(DEFAULTS)
    if raw is None:
        raw = {}
    if isinstance(raw, str):
        raw = {"preset": raw}
    if not isinstance(raw, dict):
        return look, [f"LOOK must be a preset name (\"suave\", \"padrao\", \"intensa\", \"maxima\", \"modelo\") or a dict like {{\"vignette\": 1.5}}, "
                      f"not {type(raw).__name__}"], clamps
    if "preset" in raw:
        p = raw["preset"]
        name = _norm(p) if isinstance(p, str) else None
        if name in PRESETS:
            look.update(PRESETS[name])
        else:
            errors.append(f"LOOK preset {p!r} does not exist: the presets are {', '.join(repr(x) for x in PRESETS)}"
                          + (_mean(p, PRESETS, PRESET_HINTS) if isinstance(p, str) else ""))
    seen = {}
    for k, v in raw.items():
        if k == "preset":
            continue
        key = ALIASES.get(k, k)
        if key not in KEYS:
            mean = _mean(k, list(KEYS) + list(ALIASES), KEY_HINTS)
            errors.append(f"LOOK has an unknown option {k!r}" + (mean or f"; the options are {', '.join(KEYS)}"))
            continue
        if key in seen:
            errors.append(f"LOOK sets {key!r} twice ({seen[key]!r} and {k!r} mean the same option)")
            continue
        seen[key] = k
        kind, lo, hi, _ = KEYS[key]
        if kind == "mult":
            if not _num(v):
                errors.append(f"LOOK[{k!r}] = {v!r} must be a number from {lo:g} to {hi:g} (1 = as before, 0 = off)")
                continue
            used = min(hi, max(lo, float(v)))
            if used != v:
                why = CAP_WHY.get(key, f"the allowed range is {lo:g} to {hi:g}")
                clamps.append((key, v, used, f"LOOK[{k!r}] = {v:g} is out of range ({lo:g}..{hi:g}): {why}; use {used:g} or {'more' if v < lo else 'less'}"))
            look[key] = used
        elif kind == "bool":
            if not isinstance(v, bool):
                errors.append(f"LOOK[{k!r}] = {v!r} must be True or False")
                continue
            look[key] = v
        else:
            g = _norm(v) if isinstance(v, str) else None
            if g not in GRADES:
                errors.append(f"LOOK['grade'] = {v!r} is not a grade: the grades are {', '.join(repr(x) for x in GRADES)}"
                              + (_mean(v, GRADES, GRADE_HINTS) if isinstance(v, str) else ""))
                continue
            look[key] = g
    return look, errors, clamps


def problems(T):
    """Readable problems of T.LOOK (for preflight.py): unknown option (with did-you-mean), wrong type, unknown grade or preset,
    number out of range. [] when it is fine or absent."""
    _, errors, clamps = _resolve(getattr(T, "LOOK", {}))
    return errors + [c[3] for c in clamps]


_STATE = {"grade_amount": 1.0}                       # what the last get() saw, for grade_rgb(img, name) without an amount


def get(T):
    """The merged look of the timeline module T: DEFAULTS, then the preset, then the single options; every key present.
    vignette, saturation, contrast and grain come back already steepened above 1 (UP_GAIN). A number out of range is clamped
    and the clamp is printed (once); an unreadable LOOK stops with the same sentences preflight.py gives."""
    look, errors, clamps = _resolve(getattr(T, "LOOK", {}))
    if errors:
        sys.exit("timeline.py LOOK has %d problem%s:\n  - %s" % (len(errors), "" if len(errors) == 1 else "s", "\n  - ".join(errors)))
    for _, _, _, msg in clamps:
        if msg not in _printed:
            _printed.add(msg)
            print("look: " + msg, flush=True)
    if look["intro_vignette"] is None:
        look["intro_vignette"] = look["vignette"]
    for k, g in UP_GAIN.items():
        if look[k] > 1:
            look[k] = 1 + (look[k] - 1) * g
    _STATE["grade_amount"] = look["grade_amount"]
    return look


# ---------------------------------------------------------------- colour grades
GAMMA = 2.2                                          # the renderers' display gamma, used to weight shadows / highlights
# warm / cool: linear-light channel gains at grade_amount 1 (display-referred about -20 % on the suppressed channel). None exceeds
# 1, so a grade cannot clip a highlight that was not clipped before; the price is a darker frame (3 to 7 display levels).
GRADE_GAIN = {"warm": (1.0, 0.88, 0.60), "cool": (0.66, 0.84, 1.0)}
TEAL_SHADOW, TEAL_LIGHT = (-0.55, 0.05, 0.15), (0.0, -0.12, -0.50)    # teal_orange: gain offsets in the shadows / in the lights and skin
VIBRANT = 1.4                                        # vibrant: boost of the least saturated pixels at grade_amount 1
_LUT = {}                                            # teal_orange: per-channel gain for 4096 linear-luma levels, by amount


def _teal_lut(amount):
    if amount not in _LUT:
        import numpy as np
        ld = np.linspace(0, 1, 4096) ** (1 / GAMMA)                     # display-referred luma
        s = (np.clip(1 - ld / 0.50, 0, 1) ** 1.1)[:, None]               # shadows: R down, G / B up
        h = (np.clip((ld - 0.20) / 0.35, 0, 1) * (1 - 0.5 * np.clip((ld - 0.80) / 0.20, 0, 1)))[:, None]   # lights and skin: G down, B down; whites a little less
        gain = np.maximum(1 + s * np.array(TEAL_SHADOW) + h * np.array(TEAL_LIGHT), 0.05)
        _LUT[amount] = (gain ** amount).astype(np.float32)
    return _LUT[amount]


def grade_rgb(img, name, amount=None):
    """Colour grade of a linear-light float32 RGB image (H, W, 3), done in place; returns img. "neutral" returns it untouched.
    amount = grade_amount (0..2); None = the one of the last get(). warm / cool: channel gains. teal_orange: shadows towards teal,
    lights and skin towards orange (weights from display-referred luma). mono: luminance only (a full black-and-white from amount 1).
    vibrant: a saturation boost that favours muted colours and leaves saturated ones alone. Gains are applied as gain ** amount.
    Call it after the saturation boost and before vignette / tone curve. About 10-70 ms per 1080x1920 frame."""
    if name == "neutral":
        return img
    if name not in GRADES:
        raise ValueError(f"unknown grade {name!r}: {', '.join(GRADES)}")
    if amount is None:
        amount = _STATE["grade_amount"]
    if amount <= 0:
        return img
    import numpy as np, cv2
    if name in GRADE_GAIN:
        img *= np.array(GRADE_GAIN[name], np.float32) ** np.float32(amount)
        return img
    lum = cv2.transform(np.ascontiguousarray(img), np.array([[0.2126, 0.7152, 0.0722]], np.float32))[:, :, None]
    if name == "mono":
        if amount >= 1:
            img[:] = lum
        else:
            img *= np.float32(1 - amount)
            img += lum * np.float32(amount)
    elif name == "teal_orange":
        img *= _teal_lut(float(amount))[(np.clip(lum[:, :, 0], 0, 1) * 4095).astype(np.int32)]
    else:                                                                # vibrant: the factor is computed at 1/4 size (it is smooth)
        small = cv2.resize(img, (img.shape[1] // 4, img.shape[0] // 4), interpolation=cv2.INTER_AREA)
        mx, mn = small.max(axis=2), small.min(axis=2)
        cur = np.clip((mx - mn) / np.maximum(mx, 1e-4), 0, 1)
        ls = cv2.transform(small, np.array([[0.2126, 0.7152, 0.0722]], np.float32))
        room = (1 - ls) / np.maximum(mx - ls, 1e-4)                     # the boost that would just bring the brightest channel to 1
        f = np.minimum(1 + VIBRANT * amount * (1 - cur) ** 2, np.maximum(room, 1.0)).astype(np.float32)
        f = cv2.resize(f, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LINEAR)[:, :, None]
        img -= lum
        img *= f
        img += lum
    return img


def table():
    rows = [f"{'option':<15} {'range':<10} {'default':<10} what it changes"]
    for k, (kind, lo, hi, doc) in KEYS.items():
        rng = f"{lo:g}..{hi:g}" if kind == "mult" else ("True/False" if kind == "bool" else "name")
        dflt = "=vignette" if DEFAULTS[k] is None else str(DEFAULTS[k])
        rows.append(f"{k:<15} {rng:<10} {dflt:<10} {doc}")
    rows.append("")
    rows.append("above 1 these climb faster: " + ", ".join(f"{k} 2 -> {1 + g:g}x" for k, g in UP_GAIN.items())
                + " of the default amplitude (1 + (k - 1) x gain); 1 and below are linear")
    for n, p in PRESETS.items():
        rows.append(f"preset {n:<8} " + (", ".join(f"{k} {v:g}" for k, v in p.items()) or "(nothing changed)"))
    return "\n".join(rows)


if __name__ == "__main__":
    for n, p in PRESETS.items():                                  # the presets themselves must be valid
        _, e, c = _resolve({"preset": n})
        assert not e and not c, (n, e, c)
    print(table())
