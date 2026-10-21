#!/bin/bash
# Full render: three parallel parts, then sound, then mux -> a high-quality master (crf 14).
# usage: bash run.sh master.mp4          (12 to 16 minutes for 37 s of video on a 6-core CPU; run it in the background)
# Python: $PY, default ./venv311/Scripts/python.  ffmpeg: $FF, default found by ff.py.
# Measured speed (12-thread PC, other programs running): 3.0 output frames per second with the three parts together, so a 30 s
# edit (1800 frames) takes about 10 minutes plus 1 minute for the sound; the last line says how fast the PC was.
# Before it starts, it checks everything that would waste the render (Python packages, timeline.py, song, ffmpeg, a store
# that does not hold every frame). When a part fails it stops the other parts and shows the end of that part's log.
set -e
PY=${PY:-./venv311/Scripts/python}
OUT=${1:?usage: bash run.sh master.mp4}
fail() { echo "run.sh: $*" >&2; exit 1; }
tail_log() { echo "---- last lines of $1:" >&2; tail -n 12 "$1" >&2; echo "----" >&2; }

[ -f timeline.py ] || fail "timeline.py not found in $(pwd): run this from the project folder (the one the scripts were copied into)"
"$PY" -c "pass" >/dev/null 2>&1 || fail "cannot run Python as PY=$PY. Create the venv first (pipeline.md Setup: uv venv --python 3.11 venv311 && uv pip install --python venv311/Scripts/python.exe -r requirements.txt), or set PY to its full path: PY=\"\$PWD/venv311/Scripts/python.exe\""
[ -d "$(dirname "$OUT")" ] || fail "the folder for $OUT does not exist: create it first"
if [ -n "${FF:-}" ] && [ ! -e "$FF" ]; then echo "run.sh: FF=$FF does not exist, looking for ffmpeg elsewhere" >&2; unset FF; fi
FF=$(FF=${FF:-} "$PY" ff.py | tr -d '\r') && [ -n "$FF" ] || fail "ffmpeg not found: install it (winget install Gyan.FFmpeg) or set FF to its full path"
export FF
"$PY" preflight.py > /dev/null || fail "the project is not ready to render (the message above says what to fix)"
"$PY" check_store.py || fail "the store does not hold every frame the timeline needs (above): python ranges.py && python prep.py ranges.json, then python check_store.py"
TL_SHA=$("$PY" -c "import hashlib; print(hashlib.sha1(open('timeline.py', 'rb').read()).hexdigest())" | tr -d '\r')   # stamped into the master: gate.py refuses a master rendered from another timeline.py

N=$("$PY" -c "import preflight; print(preflight.timeline().N_FRAMES)" | tr -d '\r')
A=$((N/3)); B=$((2*N/3))
export CVT=${CVT:-4}                 # OpenCV threads per render process (three run at once)
rm -f part_0.mp4 part_1.mp4 part_2.mp4 video.mp4 "$OUT.tmp.mp4"      # no part of an earlier or failed run can end up in this master (mix.wav stays: audio.py rewrites it, and deliver.sh of the previous master needs it)
T0=$SECONDS
S=(0 $A $B); E=($A $B $N); PID=()
for i in 0 1 2; do
  "$PY" render.py ${S[$i]} ${E[$i]} part_$i.mp4 > part_$i.log 2>&1 &
  PID[$i]=$!
done
left=3
while [ $left -gt 0 ]; do
  for i in 0 1 2; do
    p=${PID[$i]}
    if [ -n "$p" ] && ! kill -0 $p 2>/dev/null; then
      rc=0; wait $p || rc=$?
      PID[$i]=""; left=$((left-1))
      if [ $rc -ne 0 ]; then
        for q in 0 1 2; do [ -n "${PID[$q]}" ] && kill ${PID[$q]} 2>/dev/null || true; done
        tail_log part_$i.log
        fail "render part $i (frames ${S[$i]}..${E[$i]}) failed with exit code $rc, the other parts were stopped. The log above says why; a store problem is fixed with python ranges.py && python prep.py ranges.json && python check_store.py"
      fi
    fi
  done
  sleep 2
done
T1=$SECONDS
for i in 0 1 2; do [ -s part_$i.mp4 ] || { tail_log part_$i.log; fail "part_$i.mp4 was not written"; }; done
# parts.txt gives every part its EXACT duration (frames / 60 s): the mp4 muxer stores a part's duration in whole milliseconds and
# sometimes rounds it down (a part of 554 frames = 9.2333 s stored as 9.233 s), and the concat demuxer starts the next part at the
# stored duration, so the next part started 0.33 ms (5 ticks) early and every later frame was early against the sound.
"$PY" -c "S=[0,$A,$B]; E=[$A,$B,$N]; open('parts.txt','w').write(''.join(\"file 'part_%d.mp4'\nduration %.9f\n\" % (i, (E[i]-S[i])/60) for i in range(3)))" || fail "could not write parts.txt"
"$FF" -v error -y -f concat -safe 0 -i parts.txt -c copy video.mp4 || fail "joining the three parts failed (ffmpeg's message is above)"
# the picture's time lattice: every video pts step exactly 1/60 s and N frames, or the render stops here, naming the join
"$PY" ff.py pts video.mp4 "$N" "$A" "$B" || fail "the joined video.mp4 does not have exactly $N frames 1/60 s apart (above: the step and the join it sits on). Render again; if it repeats, run  $FF -i part_0.mp4  and look at each part's duration"
"$PY" audio.py > audio.log 2>&1 || { tail_log audio.log; fail "audio.py failed: the log above says why (the song must cover the video: python preflight.py checks it)"; }
# volume=2.36: mix.wav is written at half level (headroom, see audio.py), 2.36 = 1.18 x 2, then the limiter. The chain comes from
# peakguard.py (ff.limiter(): alimiter ... latency=1, because the limiter's 3 ms look-ahead otherwise delays the whole sound by 143 samples).
# -aac_pns 0 etc.: ffmpeg's AAC encoder otherwise overshoots the limiter by up to 3 dB on kick transients (clipping)
AF=$("$PY" peakguard.py --filter 2.36 0.82 | tr -d '\r' | tail -n 1)
case "$AF" in volume=*latency=1*) ;; *) fail "could not read the sound chain from peakguard.py: run  $PY peakguard.py --filter 2.36 0.82  to see why";; esac
# written under a temporary name: a mux that fails never leaves a half file under the master's name
"$FF" -v error -y -i video.mp4 -i mix.wav -af "$AF" \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 320k -aac_pns 0 -aac_tns 0 -aac_is 0 -metadata comment="timeline_sha1=$TL_SHA" -movflags +faststart -f mp4 "$OUT.tmp.mp4" \
  || { rm -f "$OUT.tmp.mp4"; fail "adding the sound failed (ffmpeg's message is above); video.mp4 and mix.wav are intact, repeat the last ffmpeg line of run.sh"; }
mv -f "$OUT.tmp.mp4" "$OUT"
"$PY" peakguard.py "$OUT" 2.36 mix.wav || fail "the decoded sound of $OUT clips (above); the picture is fine"
FPS=$("$PY" -c "print('%.1f' % ($N / max(1, $((T1-T0)))))" | tr -d '\r')
echo "done $OUT: $N frames rendered in $((T1-T0)) s ($FPS frames per second with the three parts together), sound and mux $((SECONDS-T1)) s"
