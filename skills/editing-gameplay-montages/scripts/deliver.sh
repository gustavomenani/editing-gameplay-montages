#!/bin/bash
# Upload copy made from the master: same picture at a bit rate that suits TikTok / Reels / Shorts
# (about 16 Mbps, 74 MB for 37 s), sound encoded once, straight from mix.wav.
# usage: bash deliver.sh master.mp4 out.mp4          (needs mix.wav from run.sh in the current folder)
#        ACCEPT=code[,code] bash deliver.sh ...      waives the gate's ERRORs of those codes only (written to LEIAME.md); python gate.py --codes lists them
# Always encode the upload copy from the master, never from an earlier upload copy.
# After the encode: peakguard.py (decoded peak) and then gate.py --sync-only on the upload copy (sound vs the song 0 ms, 1/60 s pts lattice, cuts,
# shot flashes): when either reports an ERROR the copy is renamed *.rejected.mp4 and this script fails, so nothing unverified is ever left under
# the name that gets uploaded.
# The copy is written under a temporary name and renamed when ffmpeg succeeds, so a failed or interrupted encode leaves no
# half file that "refusing to overwrite" would then protect.
set -e
PY=${PY:-./venv311/Scripts/python}
IN=${1:?usage: bash deliver.sh master.mp4 out.mp4}
OUT=${2:?usage: bash deliver.sh master.mp4 out.mp4}
fail() { echo "deliver.sh: $*" >&2; exit 1; }
[ -e "$OUT" ] && fail "refusing to overwrite $OUT: deliver each version under a new name (e.g. ${OUT%.mp4}_v2.mp4)"
[ -f "$IN" ] || fail "the master $IN does not exist in $(pwd). Render it first: bash run.sh $IN  (it takes minutes: about 3 frames per second)"
[ -f mix.wav ] || fail "mix.wav is not in $(pwd): it is written by run.sh (audio.py) next to the master; run this from the project folder, or run  $PY audio.py  to make it"
[ -d "$(dirname "$OUT")" ] || fail "the folder for $OUT does not exist: create it first"
"$PY" -c "pass" >/dev/null 2>&1 || fail "cannot run Python as PY=$PY: set PY to the project's venv, e.g. PY=\"\$PWD/venv311/Scripts/python.exe\" (pipeline.md Setup)"
if [ -n "${FF:-}" ] && [ ! -e "$FF" ]; then echo "deliver.sh: FF=$FF does not exist, looking for ffmpeg elsewhere" >&2; unset FF; fi
FF=$(FF=${FF:-} "$PY" ff.py | tr -d '\r') && [ -n "$FF" ] || fail "ffmpeg not found: install it (winget install Gyan.FFmpeg) or set FF to its full path"
# the delivery gate (gate.py): nothing is encoded while an ERROR is left; warnings print and pass. ACCEPT=code[,code] waives named codes only.
export FF
"$PY" gate.py "$IN" || fail "the delivery gate refused $IN (the errors are above, each with its fix). Fix them and render again; a problem the user accepts is waived per code: ACCEPT=<code> bash deliver.sh $IN $OUT (it is written to LEIAME.md)"
# A master older than timeline.py is refused BEFORE the encode: the copy is audited against the current timeline, so it would be rejected
# after the whole encode. gate.py keeps master-older a WARN (an mtime alone does not prove the picture changed); here the copy is measured
# anyway, so it is the refusal it becomes. Same 2 s tolerance as gate.py's check_file().
if ! "$PY" -c "import os, sys; sys.exit(0 if os.path.getmtime('timeline.py') <= os.path.getmtime(sys.argv[1]) + 2 else 1)" "$IN"; then
  fail "the master $IN is older than timeline.py (edited after it was rendered): the upload copy would be audited against the new timeline and rejected after the encode. Render the master again (bash run.sh $IN), then deliver"
fi
TMP="${OUT%.mp4}.tmp.mp4"                     # only a trailing .mp4: "${OUT%.*}" cuts at the last dot anywhere ("dir.v2/out" -> "dir.tmp.mp4", another folder)
REJ="${TMP%.tmp.mp4}.rejected.mp4"            # next to the copy, never next to a dot in a folder name
# the same sound chain as run.sh: from peakguard.py (volume 2.36 = 1.18 x 2, then ff.limiter(): alimiter ... latency=1, so the limiter's
# look-ahead does not delay the whole sound by 143 samples = 2.979 ms)
AF=$("$PY" peakguard.py --filter 2.36 0.82 | tr -d '\r' | tail -n 1)
case "$AF" in volume=*latency=1*) ;; *) fail "could not read the sound chain from peakguard.py: run  $PY peakguard.py --filter 2.36 0.82  to see why";; esac
"$FF" -v error -y -i "$IN" -i mix.wav -af "$AF" \
  -map 0:v -map 1:a -c:v libx264 -preset slow -crf 18 -maxrate 17M -bufsize 34M -g 60 \
  -vf "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv" -x264-params "aq-mode=3:aq-strength=0.9" -pix_fmt yuv420p \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  -c:a aac -b:a 320k -aac_pns 0 -aac_tns 0 -aac_is 0 -movflags +faststart -f mp4 "$TMP" \
  || { rm -f "$TMP"; fail "ffmpeg failed (its message is above); nothing was written under $OUT. Common causes: $IN is not a finished video (an interrupted render), or the disk is full"; }
mv "$TMP" "$OUT"
"$PY" peakguard.py "$OUT" 2.36 mix.wav || { mv -f "$OUT" "$REJ"; fail "the decoded sound of $OUT clips (above); the picture is fine. The copy was renamed $REJ, never left under the name that gets uploaded"; }
# the file that leaves is the UPLOAD COPY, whose picture was re-encoded and whose sound was made again from mix.wav: the sync audit runs on
# it too (audio vs the song, pts lattice, frame count, cuts, shot flashes), not only on the master. On an ERROR the copy is renamed
# *.rejected.mp4 (never left under the name that gets uploaded; kept to look at).
"$PY" gate.py --sync-only "$OUT" || { mv -f "$OUT" "$REJ"; fail "the sync audit of the upload copy failed (the errors are above); the copy was renamed $REJ and the master $IN is untouched"; }
echo "done $OUT"
