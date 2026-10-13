"""Frame geometry of the reference style, read from `FRAME` in timeline.py by render.py, textfx.py, check.py,
cover.py and cover_plates.py (one place, so they cannot disagree).

  FRAME = "horizontal"   1920x1080, the gameplay fills the frame (default; what the worked example is)
  FRAME = "vertical"     1080x1920 for TikTok / Reels / Shorts: the whole 16:9 gameplay in a window across the full
                         width (1080x608, centred on the frame, rounded corners) over a blurred backdrop of the same
                         footage, as the house style does. Nothing is cropped or enlarged: the user's rule.

Values for the vertical frame are decided here and nowhere else:
  WIN_*     the gameplay window; its centre is the exact centre of the frame, so the lyric words sit on the exact
            middle of the screen over the middle of the gameplay (the user's rule, unchanged)
  CAP_K     lyric caps are 0.62 of the horizontal ones (a 250 px cap would be 41 % of the window's height; 0.62 keeps it a quarter, as in the horizontal frame)
  WORD_MAXW widest word: 940 px, 70 px inside each side of the 1080 canvas
  KS        scale of the blur-in / streak distances, in canvas widths"""
import sys

FRAMES = ("horizontal", "vertical")


def use(name):
    """Set the geometry (module globals). Called once at import from timeline.py; text_test.py may force one."""
    if name not in FRAMES:
        sys.exit(f"timeline.py: FRAME = {name!r} is not valid: it must be exactly \"horizontal\" (1920x1080, the default) "
                 "or \"vertical\" (1080x1920, the gameplay in a window over a blurred backdrop)")
    g = globals()
    g["FRAME"] = name
    g["VERT"] = v = name == "vertical"
    g["W"], g["H"] = (1080, 1920) if v else (1920, 1080)
    g["WIN_W"], g["WIN_H"] = (1080, 608) if v else (1920, 1080)          # the 16:9 gameplay: 1080 x 607.5
    g["WIN_Y"] = (g["H"] - g["WIN_H"]) // 2
    g["WIN_R"] = 24                                                      # corner radius of the window (vertical)
    g["CAP_K"] = 0.62 if v else 1.0
    g["WORD_MAXW"] = 940 if v else 1760
    g["KS"] = g["W"] / 1920.0
    g["WORD_BAND"] = (g["WIN_Y"], g["WIN_Y"] + g["WIN_H"])              # rows the words and the motion checks live in


def _timeline_frame():
    try:
        import timeline as T
    except Exception:                                                     # the caller reports a broken timeline itself
        return "horizontal"
    return getattr(T, "FRAME", "horizontal")


use(_timeline_frame())
