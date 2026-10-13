"""The lyric words in one command: the song and the confirmed words of the section -> lyric_cues.json, with the proof.

  $PY lyrics_sync.py [lyrics.txt] [options]          (run in the project folder; $PY = the project venv, venv311)

Steps (each is a script that can be run alone; this one only chains them and skips what is already done):
  1. lyrics_stem.py       separates the voice of song seconds T0..T1 with demucs     -> lyrics/vocals.wav, lyrics/stem.json
  2. lyrics_ctc_align.py  aligns the typed words on it with two CTC models           -> lyrics/align_mms.json, align_en.json
  3. cues_from_alignment.py  the cues from the mean of the models, refined on the stem -> lyric_cues.json (+ a table)
  4. lyric_sync_sheet.py  the sheet that shows whether each word starts on its syllable -> lyrics/sync_1.jpg ...
Steps 1 and 2 run in the separation venv (torch, torchaudio, demucs, soundfile; requirements_sep.txt, pipeline.md "Setup"),
3 and 4 in this Python. The section is the video's own part of the song, timeline.py R0..R1, unless --t0 / --t1 say
otherwise: lyrics.txt must hold EVERY word sung between T0 and T1 (a word half cut at the start is fine; a sung line
missing from the text drags its neighbours off their syllables), so start the section where the voice is silent when you can.

options:
  lyrics.txt        the confirmed words (default lyrics.txt; format: lyrics_words.py)
  --t0 S --t1 S     song seconds of the section (default: the timeline's R0 and R1)
  --stem-only       only step 1 (a vocal stem for transcribe.py, to read the words before they are confirmed)
  --models mms,en   the alignment models (default both; `mms` alone for a song that is not in English)
  --red=A:B         beat range whose cues are red (repeatable; `--red=none`; write the = : a range starts with a minus sign);
                    default: the intro, before beat -0.5
  --last-end BEAT   the last cue ends at most here;  --adv BEATS  how early a cue appears (default 0.04)
  --sep PYTHON      the separation venv's python (default $VENV_SEP, else ./venv_sep/Scripts/python[.exe])
  --redo            run steps 1 and 2 again even when their files are up to date
  --force           write the cues even when the two models disagree by over 0.35 s on a word (words that do not match)"""
import argparse
import json
import os
import subprocess
import sys
import time

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("words", nargs="?", default="lyrics.txt")
ap.add_argument("--t0", type=float)
ap.add_argument("--t1", type=float)
ap.add_argument("--stem-only", action="store_true")
ap.add_argument("--models", default="mms,en")
ap.add_argument("--red", action="append")
ap.add_argument("--last-end")
ap.add_argument("--adv")
ap.add_argument("--sep")
ap.add_argument("--redo", action="store_true")
ap.add_argument("--force", action="store_true")
a = ap.parse_args()
D = "lyrics"

import timeline as T  # noqa: E402  (MUSIC, R0, R1, beat_time)

t0 = a.t0 if a.t0 is not None else T.beat_time(T.R0)
t1 = a.t1 if a.t1 is not None else T.beat_time(T.R1)
t0 = max(0.0, t0)
if not t1 > t0:
    sys.exit("lyrics_sync.py: the section is empty (T0 %g, T1 %g)." % (t0, t1))
if not os.path.isfile(T.MUSIC):
    sys.exit("lyrics_sync.py: the song %s (timeline.py MUSIC) does not exist here." % T.MUSIC)
if not a.stem_only:
    if not os.path.isfile(a.words):
        sys.exit("lyrics_sync.py: %s is missing. Write the confirmed words of the section there, one line per sung line "
                 "(lyrics_words.py describes the format; reference-style.md \"Lyric words\": where the words come from)." % a.words)
    import lyrics_words
    words = lyrics_words.parse(a.words)

exe = ".exe" if os.name == "nt" else ""
sep = a.sep or os.environ.get("VENV_SEP") or os.path.join("venv_sep", "Scripts" if os.name == "nt" else "bin", "python" + exe)
if not os.path.isfile(sep):
    sys.exit("lyrics_sync.py: the separation venv is not at %s. Make it once (about 0.6 GB with CPU torch; Python 3.11):\n"
             "  uv venv --python 3.11 venv_sep\n"
             "  uv pip install --python %s -r requirements_sep.txt\n"
             "or point --sep / $VENV_SEP at an existing one (torch, torchaudio, demucs, soundfile)."
             % (sep, os.path.join("venv_sep", "Scripts", "python" + exe)))


def run(cmd, what):
    t_start = time.time()
    print("\n== %s" % what, flush=True)
    if subprocess.run(cmd).returncode:
        sys.exit("lyrics_sync.py: step '%s' failed (see above)." % what)
    print("== %s: %.0f s" % (what, time.time() - t_start), flush=True)


stem_json, vocals = os.path.join(D, "stem.json"), os.path.join(D, "vocals.wav")
want = {"song": T.MUSIC, "size": os.path.getsize(T.MUSIC), "t0": t0, "t1": t1}
have = {}
if os.path.isfile(stem_json) and os.path.isfile(vocals):
    have = json.load(open(stem_json))
if not a.redo and all(have.get(k) == v for k, v in want.items()):
    print("voice stem of %.2f..%.2f s is up to date (%s)" % (t0, t1, vocals))
else:
    run([sep, "lyrics_stem.py", T.MUSIC, repr(t0), repr(t1), "--out", D], "voice stem %.2f..%.2f s (demucs)" % (t0, t1))
if a.stem_only:
    sys.exit(0)

models = [m.strip() for m in a.models.split(",") if m.strip()]
aligns = [os.path.join(D, "align_%s.json" % m) for m in models]


def aligned_for_these_words(p):
    """the alignment file exists, is newer than the stem and holds exactly the typed words"""
    if not (os.path.isfile(p) and os.path.getmtime(p) > os.path.getmtime(vocals)):
        return False
    return [w["w"] for w in json.load(open(p, encoding="utf-8"))] == [w["sung"] for w in words]


fresh = all(aligned_for_these_words(p) for p in aligns)
if fresh and not a.redo:
    print("alignments %s are up to date" % ", ".join(aligns))
else:
    run([sep, "lyrics_ctc_align.py", vocals, repr(t0), a.words, "--out", D, "--models", ",".join(models)],
        "CTC alignment of %d words (%s)" % (len(words), "+".join(models)))

cmd = [sys.executable, "cues_from_alignment.py", a.words, vocals, repr(t0)] + aligns
for r in a.red or []:
    cmd += ["--red=" + r]
if a.last_end:
    cmd += ["--last-end=" + a.last_end]
if a.adv:
    cmd += ["--adv", a.adv]
if a.force:
    cmd += ["--force"]
run(cmd, "cues -> lyric_cues.json")
run([sys.executable, "lyric_sync_sheet.py", vocals, repr(t0)] + aligns + ["--out", os.path.join(D, "sync")], "sync sheet")
print("\nnext: read lyrics/sync_*.jpg (every red line on the left edge of its syllable), then $PY timeline.py and a few stills")
