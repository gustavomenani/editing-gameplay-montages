#!/bin/bash
# Upload copy made from the master: same picture at a bit rate that suits TikTok / Reels / Shorts
# (up to 22 Mbps: 124 MB for 46 s of 1920x1080), sound encoded once, straight from mix.wav.
# usage: bash deliver.sh master.mp4 out.mp4          (needs mix.wav from run.sh in the current folder)
#        ACCEPT=code[,code] bash deliver.sh ...      waives the gate's ERRORs of those codes only (written to LEIAME.md); python gate.py --codes lists them
# Always encode the upload copy from the master, never from an earlier upload copy.
# The copy is written under a temporary name and renamed when ffmpeg succeeds, so a failed or interrupted encode leaves no
# half file that "refusing to overwrite" would then protect.
set -e
PY=${PY:-./venv311/Scripts/python}
IN=${1:?usage: bash deliver.sh master.mp4 out.mp4}
OUT=${2:?usage: bash deliver.sh master.mp4 out.mp4}
fail() { echo "deliver.sh: $*" >&2; exit 1; }
[ -e "$OUT" ] && fail "refusing to overwrite $OUT: deliver each version under a new name (e.g. ${OUT%.*}_v2.mp4)"
[ -f "$IN" ] || fail "the master $IN does not exist in $(pwd). Render it first: bash run.sh $IN  (it takes minutes: about 3 frames per second)"
[ -f mix.wav ] || fail "mix.wav is not in $(pwd): it is written by run.sh (audio.py) next to the master; run this from the project folder, or run  $PY audio.py  to make it"
[ -d "$(dirname "$OUT")" ] || fail "the folder for $OUT does not exist: create it first"
"$PY" -c "pass" >/dev/null 2>&1 || fail "cannot run Python as PY=$PY: set PY to the project's venv, e.g. PY=\"\$PWD/venv311/Scripts/python.exe\" (pipeline.md Setup)"
if [ -n "${FF:-}" ] && [ ! -e "$FF" ]; then echo "deliver.sh: FF=$FF does not exist, looking for ffmpeg elsewhere" >&2; unset FF; fi
FF=$(FF=${FF:-} "$PY" ff.py | tr -d '\r') && [ -n "$FF" ] || fail "ffmpeg not found: install it (winget install Gyan.FFmpeg) or set FF to its full path"
# the delivery gate (gate.py): nothing is encoded while an ERROR is left; warnings print and pass. ACCEPT=code[,code] waives named codes only.
export FF
"$PY" gate.py "$IN" || fail "the delivery gate refused $IN (the errors are above, each with its fix). Fix them and render again; a problem the user accepts is waived per code: ACCEPT=<code> bash deliver.sh $IN $OUT (it is written to LEIAME.md)"
TMP="${OUT%.*}.tmp.mp4"
# the same sound chain as run.sh: audio.master_chain() (make-up gain 1.18 / HEADROOM, optional band limit, limiter, optional trim)
AF=$("$PY" -c "import audio; print(audio.master_chain())" | tr -d '\r' | tail -n 1)
case "$AF" in volume=*) ;; *) fail "could not read the sound chain from audio.py (audio.master_chain()): run  $PY -c 'import audio; print(audio.master_chain())'  to see why";; esac
"$FF" -v error -y -i "$IN" -i mix.wav -af "$AF" \
  -map 0:v -map 1:a -c:v libx264 -preset slow -crf 17 -maxrate 22M -bufsize 44M -g 60 \
  -vf "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv" -x264-params "aq-mode=3:aq-strength=0.9" -pix_fmt yuv420p \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  -c:a aac -b:a 320k -aac_pns 0 -aac_tns 0 -aac_is 0 -movflags +faststart -f mp4 "$TMP" \
  || { rm -f "$TMP"; fail "ffmpeg failed (its message is above); nothing was written under $OUT. Common causes: $IN is not a finished video (an interrupted render), or the disk is full"; }
mv "$TMP" "$OUT"
"$PY" peakguard.py "$OUT" chain mix.wav || fail "the decoded sound of $OUT clips (above); the picture is fine"
echo "done $OUT"
