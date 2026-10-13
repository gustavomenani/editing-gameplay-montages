"""Which RIFE model interpolates THIS footage best? Objective test on real frames: rebuild frame j+1
from frames j and j+2 and compare with the real j+1, on triplets taken around the kills of
timeline.py (the two fastest and one typical triplet in the 32 frames around each kill).

usage: python rife_compare.py rife-v4.6 rife-v4.25 rife-v4.26      (folders under models/, see rifeutil.py)

Result on the house example (69 triplets, GTX 1650; mean absolute error, lower is better):
    rife-v4.25  8.715  (8.9 frames/s)   <- chosen        rife-v4.26-large  8.729  (7.0)
    rife-v4.26  8.741  (9.1)                             rife-v4.6         8.765  (11.0, the old default)
    rife-v4.18  8.809  (7.1)    rife-v4.25-heavy  8.839  (6.8)    rife-v4.22  9.006  (6.6)
    plain 50/50 blend of the neighbours: 10.477
The versions differ by 1 to 3 %: the model was never the cause of stutter. Errors are only comparable
within one run (they depend on which triplets are picked: this script gave 7.955 for rife-v4.25 on the
same clips with 66 slightly different triplets). Models come from
https://github.com/TNTwise/rife-ncnn-vulkan (folder models/)."""
import sys, time
import numpy as np
import timeline as T, clipio, rifeutil

trip = []
for k, lv, i in T.KILLS:
    c = T.SEGS[i]["clip"]
    K = int(round(float(T.SEGS[i]["map"](k)[0])))
    fr = clipio.read_frames(c, K - 26, K + 6)
    g = fr[:, ::8, ::8].astype(np.int16).mean(3)
    mo = np.abs(np.diff(g, axis=0)).mean((1, 2))
    order = np.argsort(mo[:-1] + mo[1:])
    for j in (order[-1], order[-4], order[len(order) // 2]):
        trip.append((c, K - 26 + int(j), fr[j].copy(), fr[j + 1].copy(), fr[j + 2].copy(), float(mo[j] + mo[j + 1])))
print("triplets", len(trip), flush=True)
mos = np.array([t[5] for t in trip])
fast = mos > np.percentile(mos, 66)
for model in sys.argv[1:]:
    r = rifeutil.load(model)
    t0 = time.time()
    errs = np.array([np.abs(r.process_cv2(a, b, 0.5).astype(np.int16) - gt.astype(np.int16)).mean() for c, j, a, gt, b, mo in trip])
    dt = (time.time() - t0) / len(trip)
    print("%-18s mean err %.3f | fast-motion third %.3f | slow two thirds %.3f | %.0f ms per frame (%.1f fps)" %
          (model, errs.mean(), errs[fast].mean(), errs[~fast].mean(), dt * 1000, 1 / dt), flush=True)
    del r
bl = np.array([np.abs(((a.astype(np.int16) + b) // 2) - gt).mean() for c, j, a, gt, b, mo in trip])
print("%-18s mean err %.3f  (plain 50/50 blend, no interpolation)" % ("blend", bl.mean()))
rifeutil.finish()
