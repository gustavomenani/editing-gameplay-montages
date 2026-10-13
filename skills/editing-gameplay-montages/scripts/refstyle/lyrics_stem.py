"""The isolated voice of the part of the song the edit uses, for the lyric alignment (lyrics_ctc_align.py).

Cuts song seconds T0..T1 with ffmpeg and separates them with demucs (htdemucs, two stems: vocals). Only the section is
separated: a 31 s section took 20 s on a desktop CPU once the model was cached.

Runs in the SEPARATION venv (torch, torchaudio, demucs, soundfile: requirements_sep.txt; pipeline.md "Setup"), not in venv311:
  ./venv_sep/Scripts/python lyrics_stem.py src/music.flac T0 T1 [--out lyrics]
Writes <out>/vocals.wav (44.1 kHz stereo, float32) and <out>/stem.json {"song", "size", "t0", "t1", "model"}: T0 is the song time
of the stem's first sample, which every later step needs. The cut and demucs' own output are not kept.
The first run downloads the htdemucs weights (about 80 MB, Hugging Face hub cache); if that stops, run it again.
lyrics_sync.py runs this step for you and skips it when <out>/stem.json already matches."""
import argparse
import json
import os
import random
import subprocess
import sys
import time

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("song")
ap.add_argument("t0", type=float, help="song time (s) where the section starts")
ap.add_argument("t1", type=float, help="song time (s) where the section ends")
ap.add_argument("--out", default="lyrics")
ap.add_argument("--model", default="htdemucs")
a = ap.parse_args()
if not a.t1 > a.t0 >= 0:
    sys.exit("lyrics_stem.py: need 0 <= T0 < T1 (got %g, %g)." % (a.t0, a.t1))
if not os.path.isfile(a.song):
    sys.exit("lyrics_stem.py: the song %s does not exist." % a.song)

try:
    import numpy as np
    import soundfile
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
except ImportError as e:
    sys.exit("lyrics_stem.py: %s. This script needs the separation venv (torch, torchaudio, demucs, soundfile): run it as "
             "./venv_sep/Scripts/python lyrics_stem.py ... ; setup: pipeline.md \"Setup\" (requirements_sep.txt)." % e)
from ff import FF

os.makedirs(a.out, exist_ok=True)
t_start = time.time()
r = subprocess.run([FF, "-v", "error", "-ss", repr(a.t0), "-t", repr(a.t1 - a.t0), "-i", a.song, "-map", "0:a:0",
                    "-ac", "2", "-ar", "44100", "-f", "f32le", "-"], capture_output=True)
if r.returncode or not r.stdout:
    sys.exit("lyrics_stem.py: ffmpeg could not cut %s (%g-%g s): %s" % (a.song, a.t0, a.t1, r.stderr.decode(errors="replace").strip()[-300:]))
sr = 44100
x = np.frombuffer(r.stdout, np.float32).reshape(-1, 2)
if len(x) < sr:
    sys.exit("lyrics_stem.py: less than a second of audio between %g and %g s: the song is shorter than T0?" % (a.t0, a.t1))
print("cut %.2f s of %s from %.3f s (%.0f s)" % (len(x) / sr, a.song, a.t0, time.time() - t_start), flush=True)

try:
    model = get_model(a.model)
except Exception as e:                      # download stopped, no network
    sys.exit("lyrics_stem.py: the demucs weights of %s could not be loaded (%s: %s). The first run downloads them "
             "(about 80 MB, Hugging Face hub, into ~/.cache/huggingface): check the network and run again"
             "." % (a.model, type(e).__name__, e))
model.eval()
if "vocals" not in model.sources:
    sys.exit("lyrics_stem.py: model %s has no vocals source (%s)." % (a.model, model.sources))
wav = torch.from_numpy(x.T.copy())          # (channels, samples)
ref = wav.mean(0)
mean, std = ref.mean(), ref.std()
wav = (wav - mean) / (std + 1e-8)
torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))
random.seed(0)                             # demucs' shifts=1 picks a random time shift: the same section gives the same stem
with torch.inference_mode():
    out = apply_model(model, wav[None], shifts=1, split=True, overlap=0.25, progress=False, device="cpu")[0]
vocals = out[model.sources.index("vocals")] * (std + 1e-8) + mean
vocals = vocals.numpy().T
peak = float(np.abs(vocals).max())
if peak > 1.0:
    vocals = vocals / peak
soundfile.write(os.path.join(a.out, "vocals.wav"), vocals, sr, subtype="FLOAT")
json.dump({"song": a.song, "size": os.path.getsize(a.song), "t0": a.t0, "t1": a.t1, "model": a.model},
          open(os.path.join(a.out, "stem.json"), "w"), indent=1)
print("voice of %g..%g s -> %s/vocals.wav (%s, %.0f s)" % (a.t0, a.t1, a.out, a.model, time.time() - t_start))
