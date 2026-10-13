"""Speech recognition (faster-whisper) to READ the words of a song section: the first step when nobody has pasted the lyrics.
It is not the timing: whisper's word times ran up to 3.5 beats early in places and put whole lines one word early; the
words and their times come from lyrics_sync.py (CTC alignment of the CONFIRMED words on the vocal stem). Use this output to
find which lines the section holds, then confirm every line against a lyrics page (reference-style.md, "Lyric words") and
write the confirmed words to lyrics.txt.

usage: transcribe.py <audio> <out.json> [model] [--t0 S] [--t1 S] [--offset S] [--lang CODE] [--prompt TEXT]
  audio     best the isolated voice, lyrics/vocals.wav (`lyrics_sync.py --stem-only`); the song file works too
  model     default large-v3 (CPU, int8; the 3 GB model downloads on first use)
  --t0/--t1 recognise only these seconds of the audio (clip_timestamps). Do this for a song: on a whole 218 s rock song
            large-v3 looped into "ooooh ooooh ..." for the entire track and took 28 minutes; a 60 s window took under one
  --offset  added to every printed and saved time: the song time of the audio's first sample (lyrics/stem.json "t0")
  --lang    language code (default: LANG below)
  --prompt  initial_prompt: artist, title, genre (default: PROMPT below)
Set LANG and PROMPT in this file for the song, or pass the flags.
Runs in its own venv with faster-whisper (pipeline.md, "Setup"), not venv311; ff.py must be in the current folder (audio is
decoded with ffmpeg to 16 kHz mono).
Output: <out.json> = [{"s", "e", "text", "words": [{"w", "s", "e", "p"}], "avg_logprob", "no_speech"}, ...] per segment,
times in seconds (+ offset); "p" = word probability (a low value marks a doubtful word). One line per segment is printed.
The words are NOT reliable on rap over a beat: about half the lines had an error."""
import argparse
import json
import subprocess
import sys

try:
    from faster_whisper import WhisperModel
except ImportError:
    sys.exit("transcribe.py: faster-whisper is not installed in this Python. Run it with the speech-recognition venv "
             "(pipeline.md, \"Setup\": ./venv_asr/Scripts/python transcribe.py ...), not with venv311.")
import numpy as np

from ff import FF

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("audio")
ap.add_argument("out")
ap.add_argument("model", nargs="?", default="large-v3")
ap.add_argument("--t0", type=float, default=0.0)
ap.add_argument("--t1", type=float)
ap.add_argument("--offset", type=float, default=0.0)
ap.add_argument("--lang")
ap.add_argument("--prompt")
a = ap.parse_args()

LANG = "pt"                                   # set per song (or --lang)
PROMPT = ""                                   # set per song (or --prompt), e.g. "Letra de trap brasileiro: <artista> - <música>."
LANG = a.lang or LANG
PROMPT = a.prompt if a.prompt is not None else PROMPT

model = WhisperModel(a.model, device="cpu", compute_type="int8", cpu_threads=10)
kw = dict(language=LANG, beam_size=5, word_timestamps=True, vad_filter=False,
          condition_on_previous_text=True, temperature=[0.0, 0.2, 0.4],
          initial_prompt=PROMPT or None)
if a.t1:
    kw["clip_timestamps"] = [a.t0, a.t1]
elif a.t0:
    kw["clip_timestamps"] = [a.t0]
# decode with ffmpeg ourselves (the bundled PyAV loader is incompatible with this faster-whisper)
raw = subprocess.run([FF, "-v", "error", "-i", a.audio, "-map", "0:a:0", "-ac", "1", "-ar", "16000",
                      "-f", "f32le", "-"], capture_output=True).stdout
if not raw:
    sys.exit("transcribe.py: ffmpeg decoded nothing from %s." % a.audio)
audio = np.frombuffer(raw, np.float32)
segments, info = model.transcribe(audio, **kw)
res, o = [], a.offset
for s in segments:
    words = [{"w": w.word, "s": round(w.start + o, 3), "e": round(w.end + o, 3), "p": round(w.probability, 3)}
             for w in (s.words or [])]
    res.append({"s": round(s.start + o, 3), "e": round(s.end + o, 3), "text": s.text, "words": words,
                "avg_logprob": round(s.avg_logprob, 3), "no_speech": round(s.no_speech_prob, 3)})
    print(f"[{s.start + o:7.2f} - {s.end + o:7.2f}] {s.text}", flush=True)
json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved", a.out)
print("next: confirm the lines against a lyrics page, write them to lyrics.txt (one line per sung line) and run lyrics_sync.py")
