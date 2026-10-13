"""Where each lyric word is sung: CTC forced alignment of the KNOWN (confirmed) lyrics on the isolated vocal stem.
This is the word timing to trust. Words placed from whisper's word times plus level rises of the stem went wrong once:
whisper ran up to 3.5 beats early in places, the rises got matched to the wrong words, and most lines showed every word
one word EARLY, which the viewer noticed at once. Two independent aligners (the two models below) agreed within 20-80 ms
on most words; cues_from_alignment.py averages them and refines each start on the stem.

Runs in the SEPARATION venv (torch + torchaudio CPU, soundfile: requirements_sep.txt; pipeline.md "Setup"):
  ./venv_sep/Scripts/python lyrics_ctc_align.py lyrics/vocals.wav T0 lyrics.txt [--out lyrics] [--models mms,en]
  T0       song time of the stem's first sample (lyrics_stem.py writes it to lyrics/stem.json)
  lyrics.txt  the confirmed words of the section, every sung word, in order (lyrics_words.py: the format)
  --models mms: torchaudio MMS_FA, the multilingual wav2vec2 trained for alignment (any language, 1.2 GB);
           en: WAV2VEC2_ASR_LARGE_LV60K_960H (English letters only, 1.2 GB). Default both. For a song that is not in
           English use `--models mms` (the English model reads other languages badly); one alignment still works,
           without the second opinion.
Writes <out>/align_<model>.json: [{"w", "s", "e", "score"}] per word in song seconds (20 ms frames). "w" is the sung form.
A score is a probability of the model's own: right words can score 0.1 where the singer slurs; it is not a pass mark.
CTC puts the spike of a vowel-initial word late inside the vowel ("I" after a silence: 0.5 beat late): after a silence
cues_from_alignment.py takes the first level rise of the stem instead.
The model download (1.2 GB per model, torch hub cache) stalled at 32 % once and torch.hub kept the truncated file ("failed
finding central directory"): this script prints the exact resume command when a model does not load."""
import argparse
import json
import os
import sys
import time

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("stem")
ap.add_argument("t0", type=float)
ap.add_argument("words", help="lyrics.txt")
ap.add_argument("--out", default="lyrics")
ap.add_argument("--models", default="mms,en")
a = ap.parse_args()

try:
    import numpy as np
    import soundfile
    import torch
    import torchaudio
    import torchaudio.functional as AF
except ImportError as e:
    sys.exit("lyrics_ctc_align.py: %s. This script needs the separation venv (torch, torchaudio, soundfile): run it as "
             "./venv_sep/Scripts/python lyrics_ctc_align.py ... ; setup: pipeline.md \"Setup\" (requirements_sep.txt)." % e)
import lyrics_words

KINDS = {"mms": ("MMS_FA", "https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt", "model.pt"),
         "en": ("WAV2VEC2_ASR_LARGE_LV60K_960H",
                "https://download.pytorch.org/torchaudio/models/wav2vec2_fairseq_large_lv60k_asr_ls960.pth",
                "wav2vec2_fairseq_large_lv60k_asr_ls960.pth")}
kinds = [k.strip() for k in a.models.split(",") if k.strip()]
for k in kinds:
    if k not in KINDS:
        sys.exit("lyrics_ctc_align.py: --models takes mms and/or en (got '%s')." % k)
if not os.path.isfile(a.stem):
    sys.exit("lyrics_ctc_align.py: the stem %s is missing: run lyrics_stem.py first." % a.stem)
words = [w["sung"] for w in lyrics_words.parse(a.words)]
x, sr = soundfile.read(a.stem, dtype="float32")
x = x.mean(1) if x.ndim > 1 else x
os.makedirs(a.out, exist_ok=True)
CACHE = os.path.join(torch.hub.get_dir(), "checkpoints")


def load(kind, bundle, **kw):
    """The model, with a readable failure when its download is missing or truncated."""
    name, url, fname = KINDS[kind]
    path = os.path.join(CACHE, fname)
    if not os.path.isfile(path):
        print("first use of %s: downloading %s (1.2 GB) into %s ..." % (kind, fname, CACHE), flush=True)
    try:
        return bundle.get_model(**kw)
    except Exception as e:
        sys.exit("lyrics_ctc_align.py: model '%s' (%s) did not load: %s: %s\n"
                 "A stalled download leaves a truncated file that torch.hub keeps. Delete %s, then fetch it with resume "
                 "(repeat the curl line until it ends) and run this again:\n  curl -L -C - --speed-limit 200000 "
                 "--speed-time 20 -o \"%s.part\" %s\n  mv \"%s.part\" \"%s\""
                 % (kind, name, type(e).__name__, str(e)[:200], path, path, url, path, path))


def check_alphabet(kind, alphabet):
    bad = {}
    for w in words:
        miss = sorted({c for c in (w if kind == "mms" else w.upper()) if c not in alphabet})
        if miss:
            bad[w] = miss
    if bad:
        sys.exit("lyrics_ctc_align.py: the %s model cannot read: %s. Write each word as it is sung, in letters "
                 "(numbers and symbols spelled out, 'two' not '2'); a letter the model lacks goes to its nearest one "
                 "with sung=SHOWN (lyrics_words.py)%s."
                 % (kind, "; ".join("'%s' (%s)" % (w, " ".join(m)) for w, m in list(bad.items())[:8]),
                    "; the English model reads a-z only: --models mms for another language" if kind == "en" else ""))


def explain(e, n_chars, seconds):
    sys.exit("lyrics_ctc_align.py: the words do not fit the audio (%s): %d letters in %.1f s of stem. lyrics.txt must hold "
             "exactly the words sung between T0 and T1 (a line from another part of the song, or a section cut too short)."
             % (str(e)[:160], n_chars, seconds))


def run_mms():
    bundle = torchaudio.pipelines.MMS_FA
    alphabet = set(bundle.get_dict(star=None))
    check_alphabet("mms", alphabet)
    wav = AF.resample(torch.from_numpy(x)[None], sr, bundle.sample_rate)
    model = load("mms", bundle, with_star=False)
    with torch.inference_mode():
        em, _ = model(wav)
    try:
        spans = bundle.get_aligner()(em[0], bundle.get_tokenizer()(words))
    except (RuntimeError, ValueError) as e:
        explain(e, sum(map(len, words)), len(x) / sr)
    sec = wav.size(1) / em.size(1) / bundle.sample_rate
    return [(w, sp[0].start * sec, sp[-1].end * sec, float(np.mean([t.score for t in sp]))) for w, sp in zip(words, spans)]


def run_en():
    bundle = torchaudio.pipelines.WAV2VEC2_ASR_LARGE_LV60K_960H
    labels = bundle.get_labels()
    check_alphabet("en", set(labels))
    idx = {c: i for i, c in enumerate(labels)}
    wav = AF.resample(torch.from_numpy(x)[None], sr, bundle.sample_rate)
    model = load("en", bundle)
    seq = "|".join(w.upper() for w in words)
    with torch.inference_mode():
        em, _ = model(wav)
        em = torch.log_softmax(em, dim=-1)
    try:
        ali, sc = AF.forced_align(em, torch.tensor([[idx[c] for c in seq]], dtype=torch.int32), blank=0)
    except (RuntimeError, ValueError) as e:
        explain(e, len(seq), len(x) / sr)
    spans = AF.merge_tokens(ali[0], sc[0].exp())
    sec = wav.size(1) / em.size(1) / bundle.sample_rate
    res, cur, wi = [], [], 0
    for sp in spans + [None]:
        if sp is None or labels[sp.token] == "|":
            if cur:
                res.append((words[wi], cur[0].start * sec, cur[-1].end * sec, float(np.mean([t.score for t in cur]))))
                wi += 1
                cur = []
            continue
        cur.append(sp)
    if len(res) != len(words):
        sys.exit("lyrics_ctc_align.py: the English model returned %d words for %d typed: run with --models mms." % (len(res), len(words)))
    return res


torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))
for kind in kinds:
    t_start = time.time()
    res = run_mms() if kind == "mms" else run_en()
    out = [dict(w=w, s=round(a.t0 + s, 3), e=round(a.t0 + e, 3), score=round(sc, 3)) for w, s, e, sc in res]
    path = os.path.join(a.out, "align_%s.json" % kind)
    json.dump(out, open(path, "w", encoding="utf-8"), indent=1)
    print("%s: %d words (%.0f s) -> %s; first %s %.2f s, last %s %.2f s"
          % (kind, len(out), time.time() - t_start, path, out[0]["w"], out[0]["s"], out[-1]["w"], out[-1]["s"]))
