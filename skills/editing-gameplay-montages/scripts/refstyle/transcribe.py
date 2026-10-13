"""Word-level transcription of the song (default Portuguese) with faster-whisper.

usage: transcribe.py <audio> <out.json> [model] [t_end] [--lang CODE] [--prompt TEXT] [--lyrics lyrics.txt]
  model   default large-v3 (CPU, int8)
  t_end   seconds: recognise only the first t_end seconds of the song (clip_timestamps [0, t_end]); default the whole song
  --lang    language code (default: LANG below)
  --prompt  initial_prompt: artist, title, genre (default: PROMPT below)
  --lyrics  a second pass once lyrics.txt exists: its first lines (about 600 characters, cut at a line end) are added to
            the initial_prompt, which helps whisper spell the song's words as typed. Compare with the pass without it:
            run lyrics_lines.py on both and keep the recognition with fewer LOW lines (a prompt can also make whisper
            repeat the lyrics where nothing is sung)
Set LANG and PROMPT in this file for the song, or pass the flags.
Runs in its own venv with faster-whisper (pipeline.md, "Setup"); ff.py must be in the current folder (audio is decoded
with ffmpeg to 16 kHz mono).
Output: <out.json> = [{"s", "e", "text", "words": [{"w", "s", "e", "p"}], "avg_logprob", "no_speech"}, ...] per segment,
times in seconds of the audio file; "p" = word probability (a low value marks a doubtful word). One line per segment is
printed. The words are NOT reliable on rap over a beat (reference-style.md, "Lyric words"): confirm them first, put the
confirmed lines in lyrics.txt and run lyrics_lines.py, which aligns them to this file."""
import argparse
import json
import sys

try:
    from faster_whisper import WhisperModel
except ImportError:
    sys.exit("transcribe.py: faster-whisper is not installed in this Python. Run it with the speech-recognition venv "
             "(pipeline.md, \"Setup\": ./venv_asr/Scripts/python transcribe.py ...), not with venv311.")

_ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
_ap.add_argument("audio")
_ap.add_argument("out")
_ap.add_argument("model", nargs="?", default="large-v3")
_ap.add_argument("t_end", nargs="?", type=float, default=None)
_ap.add_argument("--lang")
_ap.add_argument("--prompt")
_ap.add_argument("--lyrics")
_a = _ap.parse_args()
src, out, model_name, t_end = _a.audio, _a.out, _a.model, _a.t_end

LANG = "pt"                                   # set per song (or --lang)
PROMPT = ""                                   # set per song (or --prompt), e.g. "Letra de trap brasileiro: <artista> - <música>."
LANG = _a.lang or LANG
PROMPT = _a.prompt if _a.prompt is not None else PROMPT
if _a.lyrics:
    _lines = [ln.strip() for ln in open(_a.lyrics, encoding="utf-8-sig").read().splitlines()
              if ln.strip() and not ln.lstrip().startswith(("#", "["))]
    _txt = ""
    for _ln in _lines:
        if len(_txt) + len(_ln) > 600:
            break
        _txt += _ln + "\n"
    PROMPT = (PROMPT + "\n" + _txt).strip()
model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=10)
kw = dict(language=LANG, beam_size=5, word_timestamps=True, vad_filter=False,
          condition_on_previous_text=True, temperature=[0.0, 0.2, 0.4],
          initial_prompt=PROMPT or None)
if t_end:
    kw["clip_timestamps"] = [0.0, t_end]
# decode with ffmpeg ourselves (the bundled PyAV loader is incompatible with this faster-whisper)
import subprocess  # noqa: E402

import numpy as np  # noqa: E402

from ff import FF  # noqa: E402

raw = subprocess.run([FF, "-v", "error", "-i", src, "-map", "0:a:0", "-ac", "1", "-ar", "16000",
                      "-f", "f32le", "-"], capture_output=True).stdout
audio = np.frombuffer(raw, np.float32)
segments, info = model.transcribe(audio, **kw)
res = []
for s in segments:
    words = [{"w": w.word, "s": round(w.start, 3), "e": round(w.end, 3), "p": round(w.probability, 3)}
             for w in (s.words or [])]
    res.append({"s": round(s.start, 3), "e": round(s.end, 3), "text": s.text, "words": words,
                "avg_logprob": round(s.avg_logprob, 3), "no_speech": round(s.no_speech_prob, 3)})
    print(f"[{s.start:7.2f} - {s.end:7.2f}] {s.text}", flush=True)
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved", out)
print("next: confirm the lines against a lyrics page, write them to lyrics.txt (one line per sung line) and run lyrics_lines.py")
