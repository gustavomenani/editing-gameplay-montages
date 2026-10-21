"""Where each lyric word is sung: CTC forced alignment of the KNOWN (confirmed) lyrics on the isolated vocal stem.
This is the word timing to trust. Words placed from whisper's word times plus level rises of the stem went wrong once:
whisper ran up to 3.5 beats early in places, the rises got matched to the wrong words, and most lines showed every word
one word EARLY, which the viewer noticed at once. Two independent aligners (the two models below) agreed within 20-80 ms
on most words; cues_from_alignment.py combines them and puts each word on the sung attack measured on the stem.

Runs in the SEPARATION venv (torch + torchaudio CPU, soundfile: requirements_sep.txt; pipeline.md "Setup"):
  ./venv_sep/Scripts/python lyrics_ctc_align.py lyrics/vocals.wav T0 lyrics.txt [--out lyrics] [--models mms,en] [--shifts 8]
  T0       song time of the stem's first sample (lyrics_stem.py writes it to lyrics/stem.json)
  lyrics.txt  the confirmed words of the section, every sung word, in order (lyrics_words.py: the format)
  --models mms: torchaudio MMS_FA, the multilingual wav2vec2 trained for alignment (any language, 1.2 GB);
           en: WAV2VEC2_ASR_LARGE_LV60K_960H (English letters only, 1.2 GB). Default both. For a song that is not in
           English use `--models mms` (the English model reads other languages badly); one alignment still works,
           without the second opinion.
  --shifts N  align the stem N times, each time moved by 20/N ms (default 8: 0, 2.5 ... 17.5 ms; N must divide 320)
Writes <out>/align_<model>.json: [{"w", "s", "e", "score", "d", "s_runs"}] per word in song seconds. "w" is the sung form.

Time scale (measured). The model's frames come every EXACTLY 320 samples of its 16 kHz input
= 20.000 ms (conv stack 10/5, 3/2 x4, 2/2 x2; frame k hears samples 320k .. 320k+400). Dividing the stem length by the
frame count, as this script once did, gives 20.003-20.016 ms and adds up to +20 ms of drift to the words at the end of a
40 s stem; the stride is now the constant 320 samples and the frame count is checked against it. A time is the START
of a frame (k * 20 ms; the frame's centre is 12.5 ms later; the spike a CTC path puts into a token is anywhere in it).
Times of ONE run are multiples of 20 ms, so a stem cut 5 ms later moved a word by a whole frame (stems 5 ms apart moved
cues by up to 171 ms). Every run is therefore made --shifts times with the stem moved by 20/N ms (zeros in front at
16 kHz, exact), the shift is subtracted again and "s" / "e" are the MEDIAN over the runs (sub-frame resolution,
reproducible to a few ms); "s_runs" are the N start times and "d" their spread (max - min, seconds): a word whose runs
fall apart (>= 40 ms) sits on two readings of the voice and cues_from_alignment.py flags it.
A score is a probability of the model's own: right words can score 0.1 where the singer slurs; it is not a pass mark.
CTC puts the spike of a vowel-initial word late inside the vowel ("I" after a silence: 0.5 beat late) and the label of a
consonant-initial word early: the model times are only a PRIOR, cues_from_alignment.py moves each word to the sung
attack measured on the stem (lyrics_attack.py).
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
ap.add_argument("--shifts", type=int, default=8)
a = ap.parse_args()

HOP, FIELD = 320, 400            # samples at 16 kHz: the stride of the wav2vec2 conv stack and the samples one frame hears
if a.shifts < 1 or HOP % a.shifts:
    sys.exit("lyrics_ctc_align.py: --shifts must divide %d (1, 2, 4, 5, 8, ...; default 8), got %d." % (HOP, a.shifts))
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
STEP = HOP // a.shifts                                   # samples (16 kHz) between the shifted runs: 40 = 2.5 ms for 8 runs


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


def emissions(model, wav):
    """The model's frame scores of one 16 kHz wave; the frame count must follow the exact 320-sample stride."""
    with torch.inference_mode():
        em = model(wav)[0]
    want = (wav.size(1) - FIELD) // HOP + 1
    if em.size(1) != want:
        sys.exit("lyrics_ctc_align.py: the model gave %d frames for %d samples, the 320-sample stride says %d: this model "
                 "does not have the geometry the word times are computed with." % (em.size(1), wav.size(1), want))
    return em


def shifted(wav, k):
    """The wave moved k * STEP samples later (zeros in front): the sub-frame runs."""
    return torch.nn.functional.pad(wav, (k * STEP, 0))


def run_mms(wav16):
    bundle = torchaudio.pipelines.MMS_FA
    check_alphabet("mms", set(bundle.get_dict(star=None)))
    model = load("mms", bundle, with_star=False)
    tok, aligner = bundle.get_tokenizer(), bundle.get_aligner()
    runs = []
    for k in range(a.shifts):
        em = emissions(model, shifted(wav16, k))
        try:
            spans = aligner(em[0], tok(words))
        except (RuntimeError, ValueError) as e:
            explain(e, sum(map(len, words)), len(x) / sr)
        runs.append([(sp[0].start, sp[-1].end, float(np.mean([t.score for t in sp]))) for sp in spans])
    return runs


def run_en(wav16):
    bundle = torchaudio.pipelines.WAV2VEC2_ASR_LARGE_LV60K_960H
    labels = bundle.get_labels()
    check_alphabet("en", set(labels))
    idx = {c: i for i, c in enumerate(labels)}
    model = load("en", bundle)
    seq = "|".join(w.upper() for w in words)
    runs = []
    for k in range(a.shifts):
        em = torch.log_softmax(emissions(model, shifted(wav16, k)), dim=-1)
        try:
            ali, sc = AF.forced_align(em, torch.tensor([[idx[c] for c in seq]], dtype=torch.int32), blank=0)
        except (RuntimeError, ValueError) as e:
            explain(e, len(seq), len(x) / sr)
        spans = AF.merge_tokens(ali[0], sc[0].exp())
        res, cur = [], []
        for sp in spans + [None]:
            if sp is None or labels[sp.token] == "|":
                if cur:
                    res.append((cur[0].start, cur[-1].end, float(np.mean([t.score for t in cur]))))
                    cur = []
                continue
            cur.append(sp)
        if len(res) != len(words):
            sys.exit("lyrics_ctc_align.py: the English model returned %d words for %d typed: run with --models mms." % (len(res), len(words)))
        runs.append(res)
    return runs


torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))
for kind in kinds:
    t_start = time.time()
    bundle = torchaudio.pipelines.MMS_FA if kind == "mms" else torchaudio.pipelines.WAV2VEC2_ASR_LARGE_LV60K_960H
    if bundle.sample_rate != 16000:
        sys.exit("lyrics_ctc_align.py: the model wants %d Hz audio; the 320-sample stride is 20 ms only at 16 kHz." % bundle.sample_rate)
    wav16 = AF.resample(torch.from_numpy(x)[None], sr, bundle.sample_rate)       # zero-phase: 0.000 ms delay (measured)
    runs = run_mms(wav16) if kind == "mms" else run_en(wav16)
    out = []
    for i, w in enumerate(words):
        # run k heard the stem moved k*STEP samples later: its frame times are k*STEP/16000 too late
        s_runs = [a.t0 + (r[i][0] * HOP - k * STEP) / 16000.0 for k, r in enumerate(runs)]
        e_runs = [a.t0 + (r[i][1] * HOP - k * STEP) / 16000.0 for k, r in enumerate(runs)]
        out.append(dict(w=w, s=round(float(np.median(s_runs)), 4), e=round(float(np.median(e_runs)), 4),
                        score=round(float(np.mean([r[i][2] for r in runs])), 3), d=round(max(s_runs) - min(s_runs), 4),
                        s_runs=[round(v, 4) for v in s_runs]))
    path = os.path.join(a.out, "align_%s.json" % kind)
    json.dump(out, open(path, "w", encoding="utf-8"), indent=1)
    unstable = [o["w"] for o in out if o["d"] >= 0.04]
    print("%s: %d words, %d runs (%.0f s) -> %s; first %s %.3f s, last %s %.3f s%s"
          % (kind, len(out), a.shifts, time.time() - t_start, path, out[0]["w"], out[0]["s"], out[-1]["w"], out[-1]["s"],
             "; runs apart by >= 40 ms: " + ", ".join(unstable) if unstable else ""))
