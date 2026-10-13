"""How big is the flick before each kill? Camera travel (phase correlation of the world region) over the
frames before the shot frame K, plus whether it was a single tap (no other shot in the 30 frames before).

usage: python flick.py      -> flick.json and a ranking.   Reads kills.json + KFIX below (hand-verified K)."""
import json
import numpy as np
import cv2
import clipio

KFIX = {}           # set per project: {detection id: hand-verified K}
SKIP = set()        # set per project: detection ids to leave out
K = json.load(open("kills.json"))
SW, SH = 640, 360
RX0, RX1, RY0, RY1 = 150, 470, 60, 230
win = cv2.createHanningWindow((RX1 - RX0, RY1 - RY0), cv2.CV_64F)
out = {}
for sid, k in K.items():
    i = int(sid)
    if i in SKIP:
        continue
    c = k["clip"]
    kk = KFIX.get(i, k["K"])
    a = max(0, kk - 30)
    fr = clipio.read_frames(c, a, kk + 12, crop=False)
    g = np.stack([cv2.cvtColor(cv2.resize(f, (SW, SH), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY) for f in fr]).astype(np.float64)
    n = len(g)
    sh = np.zeros((n, 2))
    ok = np.zeros(n, bool)
    for j in range(1, n):
        (dx, dy), r = cv2.phaseCorrelate(g[j - 1, RY0:RY1, RX0:RX1], g[j, RY0:RY1, RX0:RX1], win)
        sh[j] = (dx * 3, dy * 3)
        ok[j] = r >= 0.03
    sh[~ok] = 0
    kl = kk - a

    def net(f0, f1):
        s = sh[max(1, kl + f0 + 1):kl + f1 + 1].sum(0)
        return float(np.hypot(*s))

    def path(f0, f1):
        return float(np.hypot(sh[max(1, kl + f0 + 1):kl + f1 + 1, 0], sh[max(1, kl + f0 + 1):kl + f1 + 1, 1]).sum())

    mag = np.hypot(sh[:, 0], sh[:, 1])
    # first frame of the flick: last frame before K where the camera was nearly still for 2 frames
    start = None
    for j in range(kl, 2, -1):
        if mag[j] < 2.0 and mag[j - 1] < 2.0:
            start = j - kl
            break
    # brightness of the frame (very dark or very bright = less pretty), ammo changes before K = not a single tap
    taps = [x - kk for x in k.get("changes", []) if -30 <= x - kk < 0]
    out[sid] = {"clip": c, "K": kk, "net6": round(net(-6, 0), 1), "net12": round(net(-12, 0), 1), "net20": round(net(-20, 0), 1),
                "path12": round(path(-12, 0), 1), "peak": round(float(mag[max(1, kl - 12):kl + 1].max()), 1),
                "after8": round(path(0, 8), 1), "flick_start": start, "prev_shots": taps,
                "mag": [round(float(x), 1) for x in mag[max(1, kl - 20):kl + 9]]}
json.dump(out, open("flick.json", "w"), indent=0)
print("id  clip     K  net6 net12 net20 path12 peak after8 start prev_shots")
for sid, o in sorted(out.items(), key=lambda q: -q[1]["net12"]):
    print("#%-3s %s %5d %5.0f %5.0f %5.0f %6.0f %5.0f %6.0f %5s %s" % (
        sid, o["clip"], o["K"], o["net6"], o["net12"], o["net20"], o["path12"], o["peak"], o["after8"], o["flick_start"], o["prev_shots"]))
