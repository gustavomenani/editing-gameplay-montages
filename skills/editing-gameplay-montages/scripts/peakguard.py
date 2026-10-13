"""Keep the DECODED audio peak of a finished mp4 below full scale.

The limiter in run.sh / deliver.sh stops the mix at 0.82, but the AAC encoder can still overshoot on some
transients (measured: a decoded peak of +0.035 dBFS on one test edit, -1.2 dBFS on another). This script
decodes the mp4's audio, and when its peak is above TARGET it encodes the audio again from mix.wav with a
lower limiter ceiling (the picture is copied, not re-encoded), up to 4 tries.

usage: python peakguard.py <video.mp4> <volume|chain> [mix.wav]      (run.sh and deliver.sh call it after the mux)
The volume is the one the caller applies to mix.wav (house 2.36). "chain" (reference style): the filter chain of the
project's audio.py, audio.master_chain(limit) = make-up gain 1.18 / HEADROOM, optional band limit, limiter, optional trim;
run from the project folder, where audio.py and timeline.py are."""
import os, subprocess, sys
import numpy as np
from ff import FF

TARGET = -0.5          # dBFS: the decoded sample peak must stay below this
LIMIT = 0.82           # the limiter ceiling run.sh / deliver.sh start from


def decoded_peak(path):
    raw = subprocess.run([FF, "-v", "error", "-i", path, "-map", "0:a:0", "-f", "f32le", "-ac", "2", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    if not len(x):
        sys.exit(f"peakguard.py: no audio decoded from {path}")
    return 20 * np.log10(max(float(np.abs(x).max()), 1e-9))


def filters(volume, limit):
    """The -af chain that makes the delivered sound from mix.wav, with the limiter ceiling `limit`."""
    if volume == "chain":
        import audio                                        # the reference style: HEADROOM / MASTER_LOWPASS / MASTER_TRIM_DB of timeline.py
        return audio.master_chain(limit)
    return f"volume={float(volume)},alimiter=limit={limit:.4f}:attack=3:release=60:level=disabled"


def remux(path, volume, mix, limit):
    tmp = path[:-4] + ".peak.tmp.mp4"
    r = subprocess.run([FF, "-v", "error", "-y", "-i", path, "-i", mix,
                        "-af", filters(volume, limit),
                        "-map", "0:v", "-map", "1:a", "-map_metadata", "0", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
                        "-aac_pns", "0", "-aac_tns", "0", "-aac_is", "0", "-movflags", "+faststart", tmp])
    if r.returncode != 0 or not os.path.exists(tmp):
        if os.path.exists(tmp):
            os.remove(tmp)
        sys.exit(f"peakguard.py: ffmpeg failed while encoding the audio again; {path} is unchanged")
    os.replace(tmp, path)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    path, volume = sys.argv[1], sys.argv[2]
    mix = sys.argv[3] if len(sys.argv) > 3 else "mix.wav"
    for f in (path, mix):
        if not os.path.exists(f):
            sys.exit(f"peakguard.py: {f} not found")
    peak, limit = decoded_peak(path), LIMIT
    print(f"peakguard: {path} decoded peak {peak:+.2f} dBFS (limit {limit})")
    tries = 0
    while peak > TARGET and tries < 4:
        limit *= 10 ** ((TARGET - peak - 0.3) / 20)         # lower the ceiling by the overshoot plus a margin
        remux(path, volume, mix, limit)
        peak, tries = decoded_peak(path), tries + 1
        print(f"peakguard: audio encoded again with limit {limit:.3f} -> decoded peak {peak:+.2f} dBFS")
    if peak > TARGET:
        sys.exit(f"peakguard.py: the decoded peak is still {peak:+.2f} dBFS after {tries} tries: lower the game or effect "
                 "levels (audio.py; in the reference style GAME_LEVEL, KILL_THUMP and the BOOMS gains in timeline.py) and render the sound again")
