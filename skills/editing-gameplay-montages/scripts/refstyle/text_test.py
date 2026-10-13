"""Lyric text on a flat background: the first cue of every style in timeline.TEXT at three ages (to judge the
look and the letter reveal without footage), and the numbers of the user's rule for words (on the exact middle of the
screen, big enough to read, never covering the picture).

usage: python text_test.py              -> text_test.jpg for the frame the timeline chooses (FRAME in timeline.py)
       python text_test.py vertical     -> the 1080x1920 sample (also before the timeline says FRAME = "vertical")
       python text_test.py horizontal   -> the 1920x1080 sample
one row per style, then one row with the widest word of the timeline (to check that it stays within 70 % of the width);
label = cue start beat and frames since it started. Vertical: the background has the gameplay window (the lighter band
across the middle, where the words sit).
Printed per row, measured on the rendered letters of the third tile (the ink, not the glow): capital height in px and as a
share of the frame height (vertical: also of the window height), ink width as a share of the frame width (vertical: of the
window width, the same), and the offset of the ink's bounding box centre from the frame centre (accents and descenders
excepted, the capitals are what is centred): at most 2 px."""
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


def canvas(flat=False):
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    xx = np.linspace(0, 1, W, dtype=np.float32)[None, :, None]
    if flat:
        return np.zeros((H, W, 3), np.float32)
    can = np.zeros((H, W, 3), np.float32) + 0.05 + 0.25 * xx * np.array([0.9, 0.6, 0.4], np.float32) + 0.2 * yy * np.array([0.2, 0.5, 0.9], np.float32)
    if frame.VERT:                                                    # the gameplay window: lighter, so the words are judged on it
        can[frame.WIN_Y:frame.WIN_Y + frame.WIN_H] *= 1.9
        can[frame.WIN_Y - 1:frame.WIN_Y + 1] = 1.0
        can[frame.WIN_Y + frame.WIN_H - 1:frame.WIN_Y + frame.WIN_H + 1] = 1.0
    return can


def fr(beat, off=0):
    n = textfx.frame_of(beat) + off
    can = canvas()
    textfx.draw(can, n, T.frame_beat(n))
    d = (np.clip(can, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    t = cv2.resize(d, (TW, TH), interpolation=cv2.INTER_AREA)
    cv2.putText(t, "beat %.2f %+d" % (beat, off), (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
    return t


def measure(j):
    """Ink of cue j (letters only, no glow or shadow), settled: (x0, x1, top, bottom, cue), frame pixels, inclusive. top / bottom
    are the rows of the capitals' bulk (rows with a quarter of the busiest row's ink or more): a tilde above or a Q's tail below
    would move the whole box, not the centre that is set."""
    cue = textfx.CUES[j]
    if not cue.built:
        cue.build()
    mask = cue.layer(cue.n_settled)[0].max(2) > 0.5
    xs = np.where(mask.any(0))[0]
    rows = mask.sum(1)
    ys = np.where(rows >= 0.25 * rows.max())[0]
    return xs[0], xs[-1], ys[0] + cue.y0, ys[-1] + cue.y0, cue


def report(j, label):
    x0, x1, y0, y1, cue = measure(j)
    cap = cue.cap                                                     # the capital height the word was built with (a long word is built smaller)
    line = "%-8s %-18s cap %3d px = %4.1f %% of H" % (label, cue.word[:18], round(cap), 100.0 * cap / H)
    if frame.VERT:
        line += " = %4.1f %% of the window" % (100.0 * cap / frame.WIN_H)
    line += " | ink %4d px = %4.1f %% of W | centre dx %+.1f dy %+.1f" % (x1 - x0 + 1, 100.0 * (x1 - x0 + 1) / W, (x0 + x1 + 1) / 2.0 - W / 2.0, (y0 + y1 + 1) / 2.0 - H / 2.0)
    print(line)


if not T.TEXT:
    sys.exit("text_test.py: timeline.TEXT is empty (no intro words in _T, no lyric_cues.json): nothing to show. An edit without words is allowed.")
rows, seen = [], set()
for j, (a, b, w, st) in enumerate(T.TEXT):
    if st in seen:
        continue
    seen.add(st)
    last = max(1, int((b - a) * T.FPB) - 2)             # stay inside the cue
    rows.append([fr(a, 1), fr(a, min(4, last)), fr(a, min(20, last))])
    report(j, st)
j = max(range(len(T.TEXT)), key=lambda q: len(T.TEXT[q][2]))
a, b, w, st = T.TEXT[j]
last = max(1, int((b - a) * T.FPB) - 2)
rows.append([fr(a, 1), fr(a, min(4, last)), fr(a, min(20, last))])
cv2.putText(rows[-1][0], "widest word: %s" % w, (6, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
report(j, "widest")
cv2.imwrite("text_test.jpg", cv2.cvtColor(np.vstack([np.hstack(r) for r in rows]), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
print("text_test.jpg: %s frame, %d styles (%s) + the widest word" % (frame.FRAME, len(seen), ", ".join(sorted(seen))))
