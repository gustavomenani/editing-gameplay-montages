"""Rough preview of the edit in about a minute or two: no store, no interpolation, no effects.

usage (from the project folder, after ingest.py and mkpts.py, with a timeline.py that passes):
    $PY preview.py [out.mp4] [--scale 0.5] [--marks]

For every output frame the segment's time map gives a source position; the nearest REAL source frame is shown (no RIFE,
no shutter blur, so slow motion steps), in the frame of the style:
  house style      the gameplay window (1080x912 of the 1920x1080 source) over a dimmed, blurred backdrop;
                   an overlapping transition (whip, spin, zoom, dissolve, soft) is a plain cross-fade, the others hard cuts
  reference style  full frame (horizontal), or the 16:9 window over the backdrop when FRAME = "vertical" (frame.py); hard cuts
  both             the words of T.TEXT as plain centred text, a 'PREVIEW' label, the song from MUSIC_T0 with the fade-out
  --marks          the kill beats: a coloured border on the kill frame (and the 2 after it) and its frame number for a moment
Needs only timeline.py, clipio.py, ff.py, preflight.py, the clips in src/ and their pts/ tables: nothing from prep.py, so it
runs the moment `python timeline.py` passes. What it is for: cut places, order, lengths, which kill is on which frame, words
and sound, before the 15 to 60 minutes of prep.py. What it is NOT for: how the edit looks (zoom, shake, flash, colour, blur,
slow-motion smoothness, the game sound and the risers are not in it). Output 540p H.264 + AAC, 60 fps, N_FRAMES frames."""
import argparse, os, queue, subprocess, sys, tempfile, threading, time
import numpy as np
import preflight                                  # a clear message when this is not the project's Python
import cv2
import clipio
from ff import FF, FFPROBE

ap = argparse.ArgumentParser(description="rough preview of timeline.py (no store needed)")
ap.add_argument("out", nargs="?", default="preview.mp4", help="output file (default preview.mp4)")
ap.add_argument("--scale", type=float, default=0.5, help="size of the output relative to the 1080-wide edit (default 0.5 = 540p)")
ap.add_argument("--marks", action="store_true", help="coloured border + frame number on every kill frame")
args = ap.parse_args()
if not 0.15 <= args.scale <= 1.0:
    sys.exit(f"preview.py: --scale {args.scale} is outside 0.15 .. 1.0 (0.5 = 540 px wide, the default)")
if os.path.dirname(args.out) and not os.path.isdir(os.path.dirname(args.out)):
    sys.exit(f"preview.py: the folder for {args.out} does not exist: create it first")

T = preflight.timeline(music=True)
SEGS, N, FPS = T.SEGS, T.N_FRAMES, int(round(T.FPS))
REF = "view" in SEGS[0]                          # the reference style's S() has a `view`; the house style's has not
KILLS = getattr(T, "KILLS", [])
TEXT = getattr(T, "TEXT", [])
SHORT = []                                       # source ranges the decoder did not deliver in full

# ---------------------------------------------------------------- the frame of the style (full size, then scaled)
if REF:
    import frame
    W, H, VERT = frame.W, frame.H, frame.VERT
    WIN = (0, frame.WIN_Y, frame.WIN_W, frame.WIN_H, frame.WIN_R) if VERT else (0, 0, W, H, 0)
    STRIP = (656 / 1920, 1264 / 1920)                  # centre 9:16 strip of the footage that the backdrop is made of (render.py)
    CROP = None                                        # the whole 16:9 source frame
    MAXW, CAP_K, CAPS = frame.WORD_MAXW, frame.CAP_K, (frame.WORD_CAP_RED, frame.WORD_CAP)
else:
    W, H, VERT = 1080, 1920, True
    WIN = (0, 470, 1080, 912, 34)                      # render.py FG_Y, FG_H, rounded corners
    STRIP = (0.2625, 0.7375)                           # render.py: source x 656..1264 of the 320..1600 the window shows
    CROP = "crop=iw*2/3:ih:iw/6:0"                     # the window shows 1280 of the 1920 source px (render.py WIN_SRC_W)
    MAXW, CAP_K, CAPS = 756, 0.60, (226, 202)               # refstyle/frame.py's vertical values (the house style shows no words)

S = args.scale
CW, CH = int(round(W * S / 2)) * 2, int(round(H * S / 2)) * 2
wx, wy, ww, wh, wr = (int(round(v * S)) for v in WIN)
if VERT:
    ww, wh = CW, wh                                    # the window spans the whole width
else:
    ww, wh = CW, CH
WIN_VF = (CROP + "," if CROP else "") + f"scale={ww}:{wh}:flags=area:in_range=tv:out_range=pc,format=rgb24"
STRIP_X = (int(round(STRIP[0] * ww)), int(round(STRIP[1] * ww)))


def rounded_mask(w, h, r):
    """Boolean (h, w, 1): True inside the rounded rectangle."""
    if r <= 0:
        return np.ones((h, w, 1), bool)
    m = np.zeros((h * 4, w * 4), np.uint8)
    R = r * 4
    cv2.rectangle(m, (R, 0), (w * 4 - 1 - R, h * 4 - 1), 255, -1)
    cv2.rectangle(m, (0, R), (w * 4 - 1, h * 4 - 1 - R), 255, -1)
    for cx, cy in ((R, R), (w * 4 - 1 - R, R), (R, h * 4 - 1 - R), (w * 4 - 1 - R, h * 4 - 1 - R)):
        cv2.circle(m, (cx, cy), R, 255, -1)
    return (cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA) > 127)[:, :, None]


MASK = rounded_mask(ww, wh, wr) if VERT else None
BG_DIM = 0.115 ** (1 / 2.2)                            # the backdrop is 0.115 of the footage in linear light


# ---------------------------------------------------------------- footage: one sequential decode per segment range
class Reader:
    """Source frames a..b of a clip, decoded by one ffmpeg process into small RGB arrays; a thread keeps a few in a queue so the
    decoder works while the previous frames are composed. get(i) returns frame i (i never goes backwards)."""

    def __init__(self, clip, a, b):
        self.clip, self.a, self.b, self.idx, self.cur = clip, a, b, a - 1, None
        self.err = tempfile.TemporaryFile()
        cmd = [FF, "-v", "error", "-nostdin"] + clipio.frame_args(clip, a, b, WIN_VF) + ["-frames:v", str(b - a + 1), "-f", "rawvideo", "-"]
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=self.err)
        self.q = queue.Queue(maxsize=40)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        size = ww * wh * 3
        try:
            while True:
                buf = self.p.stdout.read(size)
                if len(buf) < size:
                    break
                self.q.put(np.frombuffer(buf, np.uint8).reshape(wh, ww, 3))
        except (OSError, ValueError):                  # the pipe was closed under us: the reader was shut down
            pass
        finally:
            self.q.put(None)

    def get(self, i):
        while self.idx < i:
            f = self.q.get()
            if f is None:
                self.q.put(None)                       # stays at the end for the next call
                break
            self.cur, self.idx = f, self.idx + 1
        if self.cur is None:
            self.err.seek(0)
            sys.exit(f"preview.py: ffmpeg gave no frame of {clipio.path(self.clip)} (frames {self.a}..{self.b}): "
                     + self.err.read().decode("utf-8", "replace")[-400:])
        return self.cur

    def close(self):
        if self.p.poll() is None:
            self.p.kill()
        self.p.wait()
        self.p.stdout.close()
        self.err.close()
        if self.idx < self.b:                           # the decoder ended early: the last frame stays on screen
            SHORT.append(f"{self.clip}: frames {self.idx + 1}..{self.b} were not decoded")


# ---------------------------------------------------------------- the plan: what every output frame shows
def ease(x):
    return T.ease(x)


plan, lo, hi = [], {}, {}
for n in range(N):
    r = T.frame_beat(n)
    a, b, p, tin = T.active(r)
    layers = []
    for i in ([a] if b is None else [a, b]):
        nc = clipio.n_frames(SEGS[i]["clip"])
        f = int(min(max(round(float(SEGS[i]["map"](r)[0])), 0), nc - 1))       # the nearest real frame, inside the clip
        layers.append((i, f))
        lo[i], hi[i] = min(lo.get(i, f), f), max(hi.get(i, f), f)
    plan.append((layers, ease(p) if b is not None else 0.0))
last_use = {i: max(n for n, (ly, _) in enumerate(plan) if any(j == i for j, _ in ly)) for i in lo}
src_frames = sum(hi[i] - lo[i] + 1 for i in lo)


# ---------------------------------------------------------------- composing a frame
def window_canvas(win):
    """Source window image -> canvas of the style (a new array)."""
    if not VERT:
        return win.copy()
    tiny = cv2.resize(win[:, STRIP_X[0]:STRIP_X[1]], (27, 48), interpolation=cv2.INTER_AREA)
    bg = cv2.convertScaleAbs(cv2.resize(tiny, (CW, CH), interpolation=cv2.INTER_CUBIC), alpha=BG_DIM)
    np.copyto(bg[wy:wy + wh], win, where=MASK)
    return bg


# plain words: one RGBA image per cue, centred on the exact middle of the canvas
STYLE_RGB = {"red": (238, 32, 40), "gold": (250, 204, 92), "silver": (214, 222, 236), "white": (255, 255, 255)}


def find_font():
    for f in (os.environ.get("IMPACT_FONT"), os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "impact.ttf"),
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts", "impact.ttf"),
              os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "arialbd.ttf"),
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if f and os.path.exists(f):
            return f
    return None


class Words:
    def __init__(self):
        from PIL import Image, ImageDraw, ImageFont
        self.Image, self.Draw, self.Font = Image, ImageDraw, ImageFont
        self.font_file = find_font()
        if self.font_file is None and TEXT:
            print("preview.py: no Impact / Arial font found: the words use PIL's small default font")
        self.cache = {}
        self.cues = [(int(round((a - T.R0) * T.FPB)), int(round((b - T.R0) * T.FPB)), w, st) for a, b, w, st in TEXT]

    def image(self, j):
        if j not in self.cache:
            _, _, word, st = self.cues[j]
            cap = (CAPS[0] if st == "red" else CAPS[1]) * CAP_K * S
            size = cap / 0.79                                      # Impact: capital height = 0.79 of the font size
            while True:
                font = self.Font.truetype(self.font_file, max(8, int(round(size)))) if self.font_file else self.Font.load_default()
                box = self.Draw.Draw(self.Image.new("L", (1, 1))).textbbox((0, 0), word, font=font, stroke_width=max(1, int(round(3 * S))))
                if (box[2] - box[0]) <= MAXW * S or size < 12 or not self.font_file:
                    break
                size *= MAXW * S / (box[2] - box[0]) * 0.99
            im = self.Image.new("L", (box[2] - box[0] + 4, box[3] - box[1] + 4), 0)
            self.Draw.Draw(im).text((2 - box[0], 2 - box[1]), word, font=font, fill=255, stroke_width=max(1, int(round(3 * S))), stroke_fill=128)
            m = np.asarray(im, np.float32) / 255.0                 # 1 = letter, 0.5 = outline
            rgb = np.array(STYLE_RGB.get(st, (255, 255, 255)), np.float32)
            alpha = np.clip(m * 2, 0, 1) * 0.92                    # letters and outline
            col = np.where((m > 0.75)[:, :, None], rgb, np.float32(0))
            self.cache[j] = (col, alpha[:, :, None])
        return self.cache[j]

    def draw(self, img, n):
        for j, (n0, n1, _, _) in enumerate(self.cues):
            if n0 <= n < n1:
                col, al = self.image(j)
                h, w = col.shape[:2]
                y0, x0 = CH // 2 - h // 2, CW // 2 - w // 2          # the exact middle of the screen
                y0c, x0c = max(0, y0), max(0, x0)
                y1c, x1c = min(CH, y0 + h), min(CW, x0 + w)
                if y1c <= y0c or x1c <= x0c:
                    continue
                c, a = col[y0c - y0:y1c - y0, x0c - x0:x1c - x0], al[y0c - y0:y1c - y0, x0c - x0:x1c - x0]
                reg = img[y0c:y1c, x0c:x1c].astype(np.float32)
                img[y0c:y1c, x0c:x1c] = np.clip(reg * (1 - a) + c * a, 0, 255).astype(np.uint8)


WORDS = Words() if TEXT else None
KILL_N = sorted((int(round((k - T.R0) * T.FPB)), lv) for k, lv, _ in KILLS)
TXT_SC = max(0.5, 1.2 * S)                    # size of the labels (cv2 Hershey scale)


def put_text(img, text, x, y, scale=TXT_SC, col=(255, 255, 255)):
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, col, 2, cv2.LINE_AA)


def picture_fade(n, r):
    """Display-space brightness factor: the opening and the ending of the picture."""
    f = 1.0
    first = SEGS[0]["tin"][0]
    if REF:
        if first == "fade":
            f *= ease((r - SEGS[0]["r0"]) / 0.9)
        L0, L1 = getattr(T, "LUMA_FADE", None) or T.FADE_OUT
        f *= 1.0 - ease((r - L0) / (L1 - L0))
    else:
        f *= min(1.0, (r - T.R0) / 0.25)
        f *= 1.0 - ease((r - T.FADE_OUT[0]) / (T.FADE_OUT[1] - T.FADE_OUT[0] - 0.1))
    return max(0.0, f)


def compose(n, readers):
    layers, e = plan[n]
    imgs = [window_canvas(readers[i].get(f)) for i, f in layers]          # always new arrays: the reader's frames are shared
    img = imgs[0] if len(imgs) == 1 else cv2.addWeighted(imgs[0], 1.0 - e, imgs[1], e, 0)
    if WORDS:
        WORDS.draw(img, n)
    (tw, th), _ = cv2.getTextSize("PREVIEW", cv2.FONT_HERSHEY_SIMPLEX, TXT_SC, 1)
    if args.marks:                                           # a coloured border on the kill frame and the 2 after it; the picture itself is not touched
        for kn, lv in KILL_N:
            d = n - kn
            if 0 <= d < 3:
                cv2.rectangle(img, (0, 0), (CW - 1, CH - 1), {1: (255, 220, 0), 2: (255, 140, 0), 3: (255, 0, 0)}[lv],
                              (3, 4, 5)[lv - 1] * max(1, int(round(S * 2))))
            if 0 <= d < 18:
                put_text(img, f"KILL L{lv}  frame {kn}", 8, th + 8, col=(255, 230, 80))
    put_text(img, "PREVIEW", CW - tw - 8, th + 8)
    f = picture_fade(n, T.frame_beat(n))
    if f < 0.999:
        img = cv2.convertScaleAbs(img, alpha=f)
    return img


# ---------------------------------------------------------------- the song, cut at MUSIC_T0, with the fade-out
def encoder(out):
    dur = N / FPS
    fo0, fo1 = (T.FADE_OUT[0] - T.R0) * T.PER, (T.FADE_OUT[1] - T.R0) * T.PER
    return subprocess.Popen(
        [FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{CW}x{CH}", "-r", str(FPS), "-i", "-",
         "-ss", f"{T.MUSIC_T0:.4f}", "-t", f"{dur:.4f}", "-i", T.MUSIC, "-map", "0:v", "-map", "1:a:0",
         "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv",
         "-af", f"afade=t=out:st={fo0:.4f}:d={fo1 - fo0:.4f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-g", "60", "-colorspace", "bt709", "-color_primaries", "bt709",
         "-color_trc", "bt709", "-color_range", "tv", "-c:a", "aac", "-b:a", "128k", "-aac_pns", "0", "-aac_tns", "0", "-aac_is", "0",
         "-movflags", "+faststart", "-t", f"{dur:.4f}", out], stdin=subprocess.PIPE)


def main():
    t_start = time.time()
    enc = encoder(args.out)
    readers, opened = {}, 0
    n = 0
    try:
        for n in range(N):
            ahead = min(n + 45, N - 1)                                          # start decoding the next take while this one is composed
            while opened <= ahead:
                for i, _ in plan[opened][0]:
                    if i not in readers:
                        readers[i] = Reader(SEGS[i]["clip"], lo[i], hi[i])
                opened += 1
            enc.stdin.write(compose(n, readers).tobytes())
            for i in [i for i in readers if last_use[i] == n]:
                readers.pop(i).close()
            if n % 300 == 0:
                print(f"{args.out}: frame {n}/{N}  ({time.time() - t_start:.0f} s)", flush=True)
        enc.stdin.close()
    except OSError:
        enc.wait()
        sys.exit(f"preview.py: ffmpeg stopped while it was receiving frame {n} (its own message is above this one): "
                 f"a full disk, an output path ffmpeg cannot write, or {T.MUSIC} that it cannot read.")
    except BaseException:
        enc.kill()
        enc.wait()
        if os.path.exists(args.out):
            os.remove(args.out)
        raise
    finally:
        for rd in readers.values():
            rd.close()
    if enc.wait() != 0:
        sys.exit("preview.py: ffmpeg failed while finishing the file (its message is above this one).")
    dt = time.time() - t_start
    for s in SHORT:
        print("preview.py: warning:", s)
    info = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,duration,nb_frames", "-of", "csv=p=0", args.out],
                          capture_output=True, text=True).stdout.split()
    print(f"done {args.out}: {N} frames {CW}x{CH} {FPS} fps in {dt:.0f} s ({N / FPS / dt:.2f}x real time); "
          f"{src_frames} source frames decoded in {len(lo)} ranges; ffprobe (video, audio): {' | '.join(info)}")
    print("this is a rough preview: real source frames only (no interpolation), no zoom / shake / flash / colour / blur, "
          "song only (no game sound, no risers). Judge cuts, order, lengths, kill frames, words and music with it; the look comes from the render.")


if __name__ == "__main__":
    main()
