# Pitfalls: symptom, cause, fix

All of these happened while building the house example (house style) and the worked example (reference style). Where a cause was
measured, the measurement is given.

## Picture

| Symptom | Cause | Fix |
|---|---|---|
| "travado", "quedas de fps", motion hitches all through the video | Frames were extracted with `-ss` to half a frame before the target plus `fps=60`. The clips are 60 fps with about 1 ms of timestamp jitter, so each frame sat on the filter's rounding edge: of 12 consecutive frames only 8 were distinct. | Address frames by index: `clipio.frame_args` (`-copyts -ss`, `select='between(t,...)'` from the pts table, `-fps_mode passthrough`). Checked identical to `select='between(n,...)'`. |
| Slow motion freezes for a moment, then jumps | Interpolating between two identical frames gives identical in-betweens. Identical frames came from the extraction above, and from the recorder itself (2 in the house example). | `prep.py` rebuilds recorder duplicates from their real neighbours; `check_store.py` lists any left; `repair.py` fixes them. |
| "slow motion ta bem travadinho" | Slow motion made by repeating frames. | Sub-frame store by RIFE: 240 fps everywhere, 960 fps where the edit is slower than 0.7x. |
| A sped-up clip looks low-fps | Fast-forward by picking every n-th frame without blur. | Shutter integration over the sub-frames: each output frame averages the footage it spans. |
| Slow motion below about 0.2x pulses: a tiny stall at every real frame, then a hurry | RIFE (v4.25, ncnn) returns the first frame unchanged for a time step below about 0.08 and the second above 0.92, and only catches up by 0.25. In a 16x grid the sub-frames 15/16, 0 and 1/16 were identical (measured: step 0.01 against 0.7 elsewhere). `check.py` showed it as "motion stops for one frame" at source positions that are whole numbers. | `rifeutil.Tween` (used by prep, densify, repair since the worked example) does steps outside 0.2..0.8 in two stages through the 0.25 / 0.75 frame. A store built before that: `$PY fixends.py` (GPU), in the reference style then `$PY posmap.py`, then render again. The house example's store and master still have the dead zone (less visible at 0.28x). |
| Bullet time into a kill: the flash shows 2 frames after the beat | The eased time map reached the kill at 0.3 to 0.5x, so the first frames after K advanced half a frame each. | One anchor a frame before the kill at real time (`L` entries of the reference-style timeline add it). |
| Lyric letters look like solid stickers: "sem transparencia alguma 100% solidas" | Drawn 82-94 % opaque with a glow. The reference's opacity had been read from 240 px contact-sheet tiles. | Overlay blend at strength 0.62-0.80 (`textfx.py`). Compare enlarged crops of a still with the same crop of the reference before the first full render. |
| "no comeco aquele zoom ta mt feio" | Intro shots cropped 1.8 to 2.2x to hide the HUD: soft, upscaled gameplay. | Full frame. Gameplay is never enlarged, whatever the reference does. |
| "tem que centralizar a letra no meio da tela" | Caps centred at 45.5 % of the height (as in the reference) and the word centred by its advance widths. | Visible ink centred on W/2 (measured on the letter masks), cap height centred on H/2 (`cy=0.5`). |
| A plate or still looks zoomed although the edit has no zoom | It was rendered on a frame with a push-in or a kill punch. | For covers and comparisons render with the camera off (`cover_plates.py` replaces `render.cam`). |
| Smeared or doubled picture around a gunshot in slow motion | A muzzle flash and recoil cannot be interpolated (nothing to match between frames). | `tail()` keeps real time for 0.2 beat after the shot before slowing. |
| Spin or whip shows a few stepped copies of the window | Camera move sampled too coarsely. | Supersample the move: up to 40 sub-samples, 4 px of travel each. |
| Zoom-through reads as a dissolve | Cross-fade too long, zoom too weak. | Fade within 12 % of the length; outgoing clip zooms to 3.4x. |
| Bands in the dark blurred backdrop | 8-bit steps in a smooth gradient, made worse by the encoder. | Dither every pixel, fine grain outside the window, `aq-mode=3`. |
| Backdrop too bright or busy, picture glows | Backdrop level and bloom too high. | Backdrop at 11.5 %, bloom only above 0.62. |
| Black bars look wrong in slow motion | Letterbox drawn over a window with rounded corners. | Narrow the window itself (`bar_mask`). |
| "voce deixou um zoom no video todo" | Full-height crop shows a third of the game width. | Windowed layout showing two thirds; zoom only as an accent. |
| `check.py` reports a stalled frame at the very end | The picture is black there. | Already handled: frames darker than 12/255 are skipped. |
| `check.py`: frames 1-2 "identical", or a stall on the last frame before a hard cut | The opening fade is still black; the frame before a cut has transition frames as neighbours, which inflates their median. | False positives. The line names the beat: a fade or a cut explains it. A stall at a whole source position inside slow motion is real (dead zone, above). |
| The output file carries no colour tags, so players guess matrix and range | Conversion and tagging left to defaults. | `scale=in_range=tv:out_range=pc` on input; bt709 matrix, tv range and tags on output. |

Lesson from the stutter: the first two explanations (interpolation quality, then missing
interpolation) were plausible, shipped, and wrong. The cause was found only by hashing extracted
frames (`-f framemd5`) against a by-index reference. Measure the simplest layer first.

The RIFE model was never the problem: seven versions differed by 1 to 3 % on real triplets
(`rife_compare.py`).

## Timing

| Symptom | Cause | Fix |
|---|---|---|
| Kills near the beat but not on it | The beat grid from spectral flux is only provisional (38 ms early on the house example); the old grid tool was also 39 to 116 ms off on trap 808s, lo-fi crackle and syncopated funk. | `music_grid.py` with the BPM it confirms; if it warns about a shifted grid, check the alternative BEAT0 against the first kick in `music_spec.py`. |
| A kill lands 3 to 4 frames late | The banner frame (or the sound) was put on the beat. The banner appears 3 to 4 frames after the shot (the kill-feed row at the top right: 5 to 12). | Put the muzzle-flash frame K on the beat (`kills_auto.py` sheets; Valorant alternatives: `kill_table.py` gallery, `mykills.py` for raw recordings). |
| Picture on the beat, gunshot audibly after it | The recordings' sound trails the picture by 1.4 to 3.3 frames, different for each kill. | `lag` per kill from `kill_lags.py`. |
| A kill feels unsupported | It sits on a beat with no kick or snare. | `music_pulses.py`; move it or drop it. |
| A word appears before it is sung: "sincronizar ao maximo as letras" | One cue per phrase, shown at the phrase start. | One word per cue on its sung start (`lyrics_sync.py`). |
| Every word of a line one word early: "as letras da tela nao estao sincronizadas com a musica" | Words placed from speech recognition's word times (up to 3.5 beats early) plus level rises of the voice, which then matched the wrong words. | CTC forced alignment of the confirmed words on the demucs vocal stem, two models (`lyrics_sync.py`); read `lyrics/sync_*.jpg` before rendering. |
| A word on screen is not what is sung | Speech recognition on rap over a beat (about half the lines had an error). | Confirm every line against a lyrics page with yes/no questions; unconfirmed lines get no text. If the typed words still differ from the singing, the two aligners disagree and `lyrics_sync.py` stops. |
| Words too big, covering the game: "ta muito grande tem que dar uma diminuida leve nela" | Caps 280 / 250 px at 1080p and a 9-letter word at 86 % of the width. | Caps 226 / 202 px, widest word 70 % of the width (`frame.py`); `text_test.py` prints the numbers. |
| An alignment model download stops, then "failed finding central directory" | torch hub kept the truncated file. | Delete it and fetch it with `curl -L -C - --speed-limit 200000 --speed-time 20` into `~/.cache/torch/hub/checkpoints/` (`lyrics_sync.py` prints the exact command). |
| Speech recognition loops on "ooooh ooooh" over a whole song | A long file with long instrumental parts. | Transcribe only the section's voice stem (`lyrics_sync.py --stem-only`, then `transcribe.py lyrics/vocals.wav ... --offset`). |
| A new video shows the previous song's words | The example timeline's intro words (`_T`) were left in, or an old `lyric_cues.json`, `lyrics.txt` or `lyrics/` was copied. | Never copy those from another project; `lyrics_sync.py` writes a new `lyric_cues.json`; replace `_T`; read the "words on screen" line that `$PY timeline.py` prints. |
| The feed row comes 2 or 20 frames after the only ammo change | Another bullet (spray) or another shooter made the kill. | `strip.py`; take the ammo change 5 to 12 frames before the row, or drop the kill. |
| `kill_table.py` suggests a wrong K | Point-blank shots and ability effects confuse the brightness test (3 of 22). | Always confirm on the gallery. |

## Sound

| Symptom | Cause | Fix |
|---|---|---|
| Distortion on kicks; decoded peak +3 dBFS although the limiter stops at 0.82 | ffmpeg's native AAC encoder (noise substitution and friends) overshoots on limited transients. Three deliveries shipped like this; with PNS/TNS/IS off it can still overshoot by about 1.5 dB on some songs. | `-aac_pns 0 -aac_tns 0 -aac_is 0`, 320k, and `peakguard.py` at the end of `run.sh` / `deliver.sh` (re-encodes the audio with a lower ceiling until the decoded peak is below -0.5 dBFS); `check.py` prints the decoded peak. |
| Voices sound like chipmunks or slowed tape | Speech resampled along the speed ramp. | `voice=` or `stretch=True` (pitch-preserving stretch). |
| Game sound pitched far down in slow motion | Sound resampled along with the picture (0.28x). | Fade the game sound out by speed; music and effects carry slow motion. |
| Reference-style edit: game sound would be chopped and pitched all the time | The takes are fast-forward or slow motion almost throughout. | One gunshot per kill at natural pitch on the beat (`refstyle/audio.py`); silent where the clip has no clean shot. |
| `mix.wav` clips although every stem is below 1 | Resampling a loud 44.1 kHz master to 48 kHz peaks at 1.24; louder gunshots, thumps and booms add more (1.26 at 0.8 on the model edit). | Write the mix at `HEADROOM` (0.8 by default, 0.5 for loud shots and sub effects) and apply `volume = 1.18 / HEADROOM` before the limiter (`audio.master_chain()`, used by refstyle `run.sh`, `deliver.sh`, `peakguard.py ... chain`). |
| No gunshot onsets found in one clip | Its sound track is voice chat, not game sound. | House style: `voice=0.8`, typical `lag`, sync by the picture. Reference style: `mute=True` on every take of that clip (do not wait for `audio.py` to find nothing), and on a single talked-over kill in a clean clip. |
| Peaks flattened although the final file is below 0 dBFS | The mix exceeded full scale (1.29) and was written to a 16-bit file before the limiter: 0.05 % of the house example's samples, runs up to 0.4 ms, 49 dB below the mix. | Write the files with headroom (`HEADROOM = 0.5` in audio.py) and restore the level in front of the limiter (house `run.sh`: `volume=2.36`; the reference style: `HEADROOM` in timeline.py and `audio.master_chain()`, see above). |
| Low-pitched game sound after a slow-motion finisher | `tail()` ramps back to 0.75x, where the game sound is audible again; an overlapping transition stretches that. | Cut right after the tail, or `out_rate=0.3`. |
| A gunshot 30 ms off the beat in a `stretch=True` segment | The pitch-preserving stretch moves transients when the speed at the kill is not 1. | Keep real time around the kill (`lead()` does) or drop `stretch`. |

## Shell and tools on Windows

| Trap | What to do |
|---|---|
| `python - <<EOF` (or any bare `python`) hangs forever in Git Bash: bare `python` is the Windows Store stub or 3.14 waiting on a console | Always `./venv311/Scripts/python`. Stop the stray `python.exe -` it leaves behind (by ID). |
| `Stop-Process` by command-line pattern ends your own shell (exit 255): the pattern text is part of your own command line | List the processes, then stop by ID (pipeline.md, "Handling jobs on the user's PC"). Not by name either: other sessions run python on the user's PC. |
| A patch applied from a heredoc leaves a literal `\n` in the file, or silently applies nothing: shell and Python escaping stack, and a syntax error at the end voids every edit before it | Write the patch script with the Write tool (or use Edit); `assert s.count(old) == 1` for each replacement. |
| JSON with accented words fails to load (`0xc3`): written or read with the Windows default encoding | `encoding="utf-8"` on every `open` of a text file. |
| A script imports `timeline.py`, and `timeline.py` loads the file that script produces: neither can run first | `timeline.py` loads optional files behind `os.path.exists`. |
| faster-whisper cannot open the song (`metadata_errors`): its bundled audio loader does not match on Python 3.14 | Decode with ffmpeg to 16 kHz float32 and pass the array (`transcribe.py` does). |
| A foreground wait is cut after 10 minutes (tool limit) | Start long jobs with `run_in_background`: the harness tells you when the command exits (pipeline.md, "Handling jobs on the user's PC"). |
| "The job has been slow for ten minutes": tool calls take seconds, much less time had passed than it felt | `date` and the process start time before diagnosing speed. |
| Interpolation at an eighth of its speed, GPU at 100 %: the user opened a game (CS2 took 84 % of the GPU) | Leave the game alone. If the user has said they are playing: stop every job ("Working with the user"). If the game is only detected: stop GPU work and run CPU work (a render) at BelowNormal priority. Commands: pipeline.md, "Handling jobs on the user's PC". |
| A job that writes the store is killed: a truncated JPEG "exists" and later runs skip it | Check that the newest files end with `FFD9` and delete those that do not (pipeline.md, "Handling jobs on the user's PC"). |
| ffmpeg installed by winget is not on PATH in a shell that was already open | `ff.py` finds it; or `export FF=...` |
| `textfx.py` stops with "the Impact font is not at ..." (so does `render.py` of the reference style, which imports it), or the spectrogram labels look different | Install Impact, or set `IMPACT_FONT` to another heavy condensed .ttf (changes the look). `music_spec.py` and `mix_spec.py` use Arial Bold (`C:/Windows/Fonts/arialbd.ttf`) and fall back to Pillow's default font |
| A script that loaded RIFE finishes its work and then dies with `Segmentation fault`, exit code 139 (or exit code 5 after an error message) | the Vulkan runtime crashes while the process unloads; `rifeutil.finish()` as the last statement, and `rifeutil.die(message)` for an error after the model is loaded, end the process cleanly with the right exit code (the bundled scripts do). A pipe (`| tail`) hides the exit code, which is how this went unnoticed at first |
| Python 3.14 is the default and has no RIFE wheels | `uv venv --python 3.11` |
| The RIFE binding ships no models and reads the version from the folder NAME | keep `models/rife-v4.25/`; more at github.com/TNTwise/rife-ncnn-vulkan (`models/`) |
| `$PY -c "..."` with nested or escaped quotes fails in Git Bash | write a file, or use `$PY - <<'EOF'` for throwaway code (the venv interpreter: bare `python` hangs, see above). Patches to files: Write or Edit, not a heredoc |
| `\,` inside a normal Python string (ffmpeg filter) warns and will break | write `\\,` |
| Windows programs write CRLF: `read` loops and `$(...)` values carry a `\r` | pipe through `tr -d '\r'` |
| `sed` patches break on `|`, quotes or multi-line text | patch with a small Python script: exact `replace` guarded by `assert s.count(old) == 1` |
| numpy `float32` in `json.dump` raises | `float(x)` or `round(float(x), 3)` |
| JSON written from PowerShell 5.1 starts with a BOM | read with `encoding="utf-8-sig"` (the scripts do) |
| A path passed inside a larger quoted argument is not converted for Windows programs | `cygpath -w` |
| `strings` and some GNU tools are missing in Git Bash | use Python |
| The upload copy differs between two identical encodes | x264 with a bit-rate cap and threads is not repeatable; compare masters |
| Hard links in `src/` keep the clip data alive after the user deletes the originals | say so in the report and in `LEIAME.md`; removing `src/` is the user's call (a link may be the last copy of a clip) |
| A script fails to read an image in a folder whose path has accents ("Vídeos", "João") | `cv2.imread` / `cv2.imwrite` cannot open a non-ASCII path; a relative ASCII path from the project folder works (what the scripts use: `store/...`). Never pass an absolute path to cv2; read with `np.fromfile` + `cv2.imdecode` (as `cover.py` does). `doctor.py` warns about it |
| The project is inside OneDrive: the PC slows down, files get duplicated or vanish while `prep.py` writes thousands of JPGs | put `_editor` outside OneDrive (or pause syncing); `doctor.py` warns about it |

## Working with the user

- "nao me faca perguntas beleza ? apenas faça o que voce decidir e achar melhor": what to make is asked once,
  in the briefing (SKILL.md); after it, choose and act, then report what was chosen. Never delete or
  overwrite anything of theirs, so that no confirmation is needed.
- A long blocking wait was interrupted once. Run renders and interpolation in the background and
  send a short line about progress.
- Deliver each version as a new file beside the clips (`_v2`, `_v3`, ...). Earlier versions stay.
- "tudo de skill e aprendizado que voce teve, eu quero que voce salve"; "TUDO QUE VOCE APRENDEU, arruma a nossa
  skill de edit": when a project teaches something reusable, update this skill and the memory before finishing.
- They open `_editor/master.mp4` before the delivery and comment on it. That is feedback like any other.
- "consegue renderizar dps ?vou jogar agora": stop renders and interpolation at once, say what is already
  delivered, resume on "pode renderizar" or when the game is closed.
- "arruma isso e JA ERA": after that one fix the edit is finished. Do not add changes they did not ask for.
- Nothing unrequested on screen: "tira esse valorant edit da tela".
