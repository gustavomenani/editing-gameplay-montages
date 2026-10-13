"""Lyric text on a flat background: the first cue of every style in timeline.TEXT at three ages (to judge the
look and the letter reveal without footage).

usage: python text_test.py              -> text_test.jpg for the frame the timeline chooses (FRAME in timeline.py)
       python text_test.py vertical     -> the 1080x1920 sample (also before the timeline says FRAME = "vertical")
       python text_test.py horizontal   -> the 1920x1080 sample
one row per style; label = cue start beat and frames since it started. Vertical: the background has the gameplay
window (the lighter band across the middle, where the words sit) and one more row with the widest word of the
timeline, to check that it fits inside the 1080 px canvas."""
import sys
import frame
for _a in sys.argv[1:]:
    if _a not in frame.FRAMES:
        sys.exit("text_test.py: the only argument is 'vertical' or 'horizontal' (the frame to show); without it the timeline's FRAME is used")
    frame.use(_a)
import numpy as np, cv2
import timeline as T, textfx
W, H = frame.W, frame.H
TW, TH = (360, 640) if frame.VERT else (640, 360)


def fr(beat, off=0):
    n = textfx.frame_of(beat) + off
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    xx = np.linspace(0, 1, W, dtype=np.float32)[None, :, None]
    can = np.zeros((H, W, 3), np.float32) + 0.05 + 0.25 * xx * np.array([0.9, 0.6, 0.4], np.float32) + 0.2 * yy * np.array([0.2, 0.5, 0.9], np.float32)
    if frame.VERT:                                                    # the gameplay window: lighter, so the words are judged on it
        can[frame.WIN_Y:frame.WIN_Y + frame.WIN_H] *= 1.9
        can[frame.WIN_Y - 1:frame.WIN_Y + 1] = 1.0
        can[frame.WIN_Y + frame.WIN_H - 1:frame.WIN_Y + frame.WIN_H + 1] = 1.0
    textfx.draw(can, n, T.frame_beat(n))
    d = (np.clip(can, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    t = cv2.resize(d, (TW, TH), interpolation=cv2.INTER_AREA)
    cv2.putText(t, "beat %.2f %+d" % (beat, off), (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
    return t


if not T.TEXT:
    sys.exit("text_test.py: timeline.TEXT is empty (no intro words in _T, no lyric_cues.json): nothing to show. An edit without words is allowed.")
rows, seen = [], set()
for a, b, w, st in T.TEXT:
    if st in seen:
        continue
    seen.add(st)
    last = max(1, int((b - a) * T.FPB) - 2)             # stay inside the cue
    rows.append([fr(a, 1), fr(a, min(4, last)), fr(a, min(20, last))])
if frame.VERT:
    a, b, w, st = max(T.TEXT, key=lambda c: len(c[2]))
    last = max(1, int((b - a) * T.FPB) - 2)
    rows.append([fr(a, 1), fr(a, min(4, last)), fr(a, min(20, last))])
    cv2.putText(rows[-1][0], "widest word: %s" % w, (6, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
cv2.imwrite("text_test.jpg", cv2.cvtColor(np.vstack([np.hstack(r) for r in rows]), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
print("text_test.jpg: %s frame, %d styles (%s)%s" % (frame.FRAME, len(seen), ", ".join(sorted(seen)), " + the widest word" if frame.VERT else ""))
