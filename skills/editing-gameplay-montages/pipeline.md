# Pipeline reference

Everything runs from one project folder with the scripts copied into it (they import each other and
`timeline.py` from the current directory). Shell: Git Bash (the Bash tool). `PY=./venv311/Scripts/python`.
Each Bash call is a fresh shell: start every command with `cd "$P" && PY=./venv311/Scripts/python &&`
(written out, since `$P` is gone too). If a shell refuses the relative path ("command not found"), use the
absolute one, `PY="$PWD/venv311/Scripts/python.exe"`, and export it: `run.sh` and `deliver.sh` read `$PY`.

## Project layout

```
<project>/
  clips.json            short name -> original file            you write it
  src/                  c1.mp4 / c1.mkv ... music.flac          ingest.py (links, or converted working copies; a lossy song is decoded once to music.flac)
  src/ingest.json       per clip: original size, fps, method     ingest.py
  pts/c1.csv ...        presentation time of every frame        mkpts.py
  banners.json          banner frame of every kill              you, from find_kills.py
  kills.json            kill frame K (+ feed frame, confidence)  kills_auto.py (Valorant alternatives: kill_table.py, mykills.py; each rewrites it)
  timeline.py           THE EDIT                                you, from timeline_example.py
  ranges.json           footage the edit needs                  ranges.py
  hits.json             the song's measured drum hits           music_hits.py (t = attack time, r = hit(t), band)
  store/<clip>/<key>.jpg  real frames + in-betweens             prep.py, densify.py, repair.py
  models/rife-v4.25/    interpolation network                   copied from the skill
  venv311/              Python 3.11                             uv
  part_N.mp4, video.mp4, mix.wav, stem_*.wav, master.mp4        run.sh
```

Where to put it: next to the user's clips as `<clips folder>/_editor/` (same drive, so `src/` costs no
space, and the project survives the session). If that folder already holds another video's project,
use `_editor_<name>/`; never mix two videos in one project folder. `store/` takes 0.4 MB per sub-frame: about 7 GB for a
37 s edit. Tell the user it is there and that it can be deleted (it rebuilds in about 30 minutes).
`src/` holds hard links for sources already in the working format: while they exist, deleting the original
clips frees no disk space. Say so in the report and in `LEIAME.md`; do not remove `src/` yourself (once the
user has deleted an original, the link is the last copy of that clip). `ingest.py` recreates the links
instantly while the originals exist. A converted working copy (`.mkv`, x264 crf 9 + FLAC) is a new, large
file: put its size in the disk report.

The numbers in this skill come from two finished edits (not included: they hold the author's footage):
- the house example: house style, vertical, 37 s, 22 kills (`scripts/timeline_example.py` is its timeline);
- the worked example: reference style, horizontal, lyric words, 46 s, 62 kills (`scripts/refstyle/timeline_ref_example.py`). Its extra files:
  `detections.json`, `detect/`, `kills.json`, `lyric_cues.json`, `posmap.json`, `cover/`. A project with lyric words also
  holds `lyrics.txt` (the confirmed words) and `lyrics/` (voice stem, alignments, sync sheets).

## Setup

```bash
SK=~/.claude/skills/editing-gameplay-montages
P="/c/Users/<you>/Videos/<clips folder>/_editor"    # one project folder per video (_editor_<name> if _editor is taken)
mkdir -p "$P" && cd "$P"
cp "$SK"/scripts/*.* . && cp -r "$SK"/scripts/games "$SK"/models .     # *.* = files only (a bare * also hits the refstyle folder and cp fails); games/ = kill-finder profiles
# THE DEFAULT STYLE (reference style, with or without a reference video): its render.py, audio.py, check.py, clipio.py,
# densify.py, run.sh, deliver.sh replace the house ones on purpose (one project folder is one style):
cp "$SK"/scripts/refstyle/*.* . && ([ -e timeline.py ] || cp timeline_ref_example.py timeline.py)   # FRAME = "vertical" is the default (draft_ref_timeline.py writes it). `[ -e ] ||` is not decoration: this block is also what an old project runs to take the new scripts, and an unconditional cp would replace the user's whole edit. The same guard on the house line below, and on every `cp ... timeline.py` in this skill
# house style ONLY on the user's request ("estilo house"), instead of the line above:
#   [ -e timeline.py ] || cp timeline_example.py timeline.py
uv venv --python 3.11 venv311                       # 3.11: the RIFE binding has no wheels for 3.14
uv pip install --python venv311/Scripts/python.exe -r requirements.txt
export PY=./venv311/Scripts/python                  # export: run.sh and deliver.sh read $PY from the environment
$PY doctor.py          # checks everything before the first ingest: packages, ffmpeg, the model, a real RIFE call on the GPU,
                       # Impact, disk, write permission, OneDrive / accents in the path. Ends with PRONTO (exit 0) or FALTA: ... (exit 1)
# lyric words only: two more venvs, neither is venv311.
# separation + alignment (lyrics_sync.py calls it itself): Python 3.11, CPU torch, about 0.6 GB. Tested: torch 2.14.1+cpu,
# torchaudio 2.11.0+cpu, demucs 4.1.0, soundfile 0.14.0, numpy 2.4.6 (requirements_sep.txt). First use downloads two
# alignment models (1.2 GB each, torch hub cache) and the demucs weights (81 MB, Hugging Face cache).
uv venv --python 3.11 venv_sep && uv pip install --python venv_sep/Scripts/python.exe -r requirements_sep.txt
# speech recognition, only to READ the words of a song nobody pasted lyrics for (transcribe.py): Python 3.14 +
# faster-whisper 1.2.1; large-v3 took 44 s for a 31 s voice stem on the CPU, its 3 GB download happens on first use.
#   uv venv --python 3.14 venv_asr && uv pip install --python venv_asr/Scripts/python.exe faster-whisper numpy
```

`clips.json` (forward slashes, or doubled backslashes; UTF-8 with or without BOM, UTF-16 and ANSI files are all
read; the short names become file names: no `/ \ : * ? " < > |`, not `ingest`, not a Windows device name):

```json
{"c1": "C:/Users/<you>/Videos/valorant/clip1.mp4",
 "music": "C:/Users/<you>/Videos/valorant/01 - Artist - Song.flac"}
```

`$PY ingest.py && $PY mkpts.py`. `ingest.py` brings every source into the working format that everything
downstream assumes: 1920x1080, 60 fps constant, frame n at t0 + n/60 on the original clock. A source already
in that format (1920x1080, the recorder's rate within 0.5 fps of 60) is hard-linked untouched, and so is a
1080p60 recording with dropped frames: its frame indices stay the original's (the Valorant raw-recording tools
rely on that), `mkpts.py` lists the gaps and `clipio.py` follows the real time table across them. Anything
else (1440p, 4K, 720p, 4:3 stretched, 21:9, 120 / 144 / 165 / 240 fps, 30 fps, variable frame rate) becomes a
converted `src/<name>.mkv`; the Valorant raw-recording tools read the original file, so for a converted clip find
the kills with `kills_auto.py`, which reads `src/`. In between: the same picture in another container (.ts, .flv,
.wmv) or with audio that starts late in the file is remuxed to `src/<name>.mkv` in under a second (picture and
frame indices untouched, audio realigned). HDR (PQ/HLG) is tone mapped to SDR (approximately). A vertical clip
is padded between black bars (it looks small: say so); a phone clip rotated in its metadata is turned upright.
A recording whose first or last seconds do not decode gets a WARNING. One bad entry does not stop the others:
the run ends with the entries that failed and exit code 1. Long conversions print a progress line every 20 s:

- Size: narrower than 16:9 (4:3, 16:10: CS2 "stretched") is stretched to 16:9, which is what the player saw;
  wider (21:9, 32:9) is cropped at the centre; `--aspect stretch|crop|pad` overrides.
- Time: a source frame within 1.5 ms of the wanted instant is used unchanged (120 / 240 fps are exact picks).
  Otherwise `--exact` (default for clips up to 90 s) interpolates the two frames around the instant with RIFE
  at the exact fraction; `--fast` (default for longer raw recordings) takes the nearest frame, at most half a
  source frame off (3.5 ms at 144 fps). Below 60 fps it always interpolates: a repeated frame is a stutter.
  Once the timeline uses a `fast` clip, upgrade it with `$PY ingest.py --exact --only c3`, delete `store/c3`
  and run `mkpts.py`, `prep.py` and `densify.py` again: the frame grid is the same, so K values and anchors stay.
- Sound: the clip's FIRST audio track as FLAC (OBS track 1 = the game or the mix; mic and Discord tracks are
  listed and ignored), aligned so that frame n and its sound belong together (measured: 0.0 ms on forced
  conversions, late audio, late video, 1440p144; 2 ms on 59.94 fps). A clip without sound gets a warning.
- Song: flac, wav and aiff are linked as they are (`src/music.flac` / `.wav`). Any other file (m4a, aac, mp3, ogg, opus ... or a song inside a video container) is decoded ONCE to `src/music.flac`: a full decode from sample 0 in 24 bit (ffmpeg's s32 FLAC holds 24 bits; the container's priming applied, which is what every tool decodes), `MUSIC` in timeline.py points to it, and the line prints the sample count of the source's decode against the flac's. Why: ffmpeg's `-ss` before `-i` inside AAC / mp3 lands 8 to 40 ms off the sample, a flac seeks exactly, and every cue, hit and cut is a time of that one file. (Measured on a 9.6 M-sample m4a: same count, lag 0; about 750 samples where the AAC decode overshoots full scale are held at 1.0.)

Measured on a GTX 1650 against a real 1080p60 recording: forced conversion of the same clip 41 to 45 dB per
frame (x264 rounding only); 120 fps source, 0 interpolations; 144 fps and 2560x1440 built from 60 fps,
motion evenness as the original (no repeated frame, no extra jumps); 30 fps: no repeated frame, but every
other frame is invented (25.9 dB on average against a real 60 fps recording, weak on fast flicks), so ask for
60 fps or more. Speed (GTX 1650): 25 to 37 frames per second when frames are only picked (2 min of 4K60 in about
5 min), 9 to 12 with `--exact` on 144 fps, 8 to 12 for 30 fps, about 5 for 50 fps: run it in the background.

`mkpts.py` then reports frame rate, jitter and gaps of the working copies (gaps: frames the recorder dropped).

ffmpeg is found by `ff.py`: `$FF`, then PATH, then the winget install
(`%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*`). Install with `winget install Gyan.FFmpeg`;
a shell opened before the install does not have it on PATH, which is why `ff.py` looks it up.

Machine these numbers come from: Windows 11, Ryzen 5 5500 (6 cores), 16 GB RAM, GTX 1650 4 GB.

Two settings that depend on the PC:
- GPU: `rifeutil.load()` uses Vulkan device `RIFE_GPU` (environment variable, default 0). On a PC with two GPUs
  (integrated and dedicated) the dedicated one may not be 0: `export RIFE_GPU=1` before `prep.py` / `densify.py`, and
  check with the GPU command under "Handling jobs on the user's PC" that the 3D load is on the dedicated GPU. Without a
  usable Vulkan GPU (no or old driver, remote session, virtual machine) it stops with a message. `RIFE_GPU=-1` runs
  RIFE on the CPU: it works but is about 15 times slower (measured 2.4 s per sub-frame on a 12-thread CPU against
  0.17 s on a GTX 1650: a 30 s edit takes 10 to 17 hours; `prep.py` is resumable). Say so before starting it.
- CPU threads: `render.py` gives OpenCV `CVT` threads (environment variable, default 4) in each of the three
  processes `run.sh` starts (both styles): `CVT=2 bash run.sh master.mp4` on a 4-core CPU.
- Lyric font (reference style): `textfx.py` uses Impact from the Windows font folder, or `IMPACT_FONT` (path to a
  .ttf); it stops with that message when the font is missing.

## Scripts

| Script | What it does | Call |
|---|---|---|
| `ingest.py` | working copies in `src/` (any size and frame rate -> 1920x1080 60 fps), `src/ingest.json` | `$PY ingest.py`, `--only c3 --exact` to upgrade a `fast` clip |
| `mkpts.py` | frame time tables, source warnings | `$PY mkpts.py` |
| `peek.py` | contact sheet of real frames (how you watch a clip) | `$PY peek.py c3 0 1320 30` overview, `$PY peek.py c3 268 300` every frame |
| `kills_auto.py` | ANY game: kill-feed rows tracked by colour (own rows only: teammates' rows and your deaths go to `rows_other.json`; a row seen again, scrolled or faded is not a new kill) -> K = the shot that killed (last ammo step before the row, muzzle flash, gunshot) -> `kills.json` (+ `hidden`, `headshot`, `no_shot`, `conf`) + review sheets `autokill_NN.jpg`; profiles in `games/` (`valorant`, `cs2` not yet checked on footage, `generic`). About 35 s per 1.2 GB clip | `$PY kills_auto.py valorant`, `$PY kills_auto.py cs2 c1 c3`, `$PY kills_auto.py cs2 --regions c1 1500` to check a profile's rectangles on a frame |
| `dupes.py` | the same footage in several files (a full recording and its trims, identical copies, a re-encoded trim through its sound) with the offset -> `dupes.json`; not found: a downscaled copy, a trim without sound. 42 files in 2.5 min | `$PY dupes.py` (the project's clips) or `$PY dupes.py --dir <folder>` |
| `kill_rank.py` | every kill scored with its reasons (headshot, run of 2+, clean shot, one-tap, flick, visibility), duplicates dropped, best set for X s, contact sheets `kill_rank_*.jpg`; `--check` verifies the kills `timeline.py` uses (ERROR hidden / not-yours / duplicate / wrong-shot / k-after-row) | `$PY kill_rank.py --seconds 20`; `$PY kill_rank.py --check` (about 3 min for 26 clips) |
| `find_kills.py` | kill-banner sheets + candidate frames (Valorant HUD) | `$PY find_kills.py c3` or `c1 82 97` (seconds) |
| `kill_table.py` | per kill: frame K for the beat, gunshot, lag, gallery | `$PY kill_table.py` (reads `banners.json`; an entry `[banner, K]` fixes K by hand) |
| `cadence.py` | duplicated frames / real pauses in a source clip | `$PY cadence.py c1 5290 5725`, add `--detail` on a short range |
| `music_tempo.py` | BPM with its half / double alternative and the evidence, fit strength, the tempo again in every 30 s window (`tempo steady?`: windows more than 0.3 % apart = a live drummer or a tempo change, so one BPM / BEAT0 is true only near the part measured) and the beat phase of the strong attacks in 10 s windows (`beat phase steady?`: scatter above 10 ms = a drummer who swings around the tempo), provisional phase, loud sections, kick pattern, every drop. A WEAK fit (under 2.5x: strong off-beats of a band, a syncopated groove, no clear pattern) is printed as a `WEAK:` warning with the best fit and the tables, exit 0, as long as both steadiness checks pass; WEAK AND not steady (or under 30 s to judge) = `NO TEMPO`, no beat tables, exit 1 | `$PY music_tempo.py` |
| `music_grid.py` | every drum attack of the stretch measured with the skill's one attack definition, then: the TEMPO CROSS-CHECK (scans +-1.5 % of the BPM given; a BPM that another tempo fits 1.3x better is REFUSED: it names the better one, prints no BEAT0, exit 1); `BEAT0` on the sixteenth lines the strong hits sit on (a move above 1/16 beat announced, shifted-grid alternatives printed); a tempo correction only from 60 s of track; the VERDICT over all strong hits (median, MAD, share beyond 8.3 ms, the worst hit): above 5 % it prints `constant grid NOT adequate: place on hits.json times` and the events go on the hits' own times | `$PY music_grid.py 130 0.423 27 72` |
| `music_hits.py` | `hits.json`: every hit of the section with its attack time `t` (track seconds), `r = hit(t)` (timeline beat, 9 decimals), band (`low` kick / 808, `mid` snare / clap, `high` hat), strengths, per-band times `tl` / `tm` / `th`, and `dt_ms` to the grid line (orientation only); plus a table. For hand-written timelines, the gate and the drafters' explanations | `$PY music_hits.py [R0 R1]`; `--all`, `--sub 4`, `-o`; `--music --bpm --beat0 --m0 --r0 --r1` without a timeline |
| `music_spec.py` | spectrogram labelled in timeline beats, with a triangle on every measured attack (red kick, green snare, blue hat) | `$PY music_spec.py [r0 r1]` |
| `music_pulses.py` | kick / snare / hat strength on every half beat (`beat_hits.measure_t`, so it prints what the drafters use) and the PLACEMENT CHECK: every kill (`T.HITS`), every `"bass"` cut (against a kick of strength 0.4 or more), every bump and boom against the measured attacks, in ms and frames; more than 8.3 ms (half a frame) off = FAIL, exit 1. Needs SYNC 2 | `$PY music_pulses.py` |
| `draft_timeline.py` | writes a correct first draft of a house-style `timeline.py` from `plan.json` (BPM, BEAT0, the drop's track beat, `cuts_on`, length, the kills in order with level / `continuous`; `cut_lead_frames` / `hit_lead_frames`; `lag` only for a kill `audio.py` cannot measure): every kill on a kick / snare ATTACK, a bass cut on the kick's attack, a kills-mode cut on the attack of its 1/4-beat line (the grid line when nothing sounds), R1 / FADE_OUT on beat lines, all written as musical beats with 9 decimals; explains every segment, refuses with numbers when the plan cannot fit or a K is unverified (edit-design.md, "Drafting the timeline") | `$PY draft_timeline.py plan.json [-o timeline.py] [--force] [--compare timeline_example.py]` |
| `beat_hits.py` | the shared measure (both drafters, `music_pulses.py`, `music_hits.py`, `music_grid.py`, the gate): `measure_t` returns the strengths on the 1/2 or 1/4 beat lattice AND `att` = {lattice beat: (attack time, band)} for every row backed by a real attack within 50 ms of the lattice point (a hit 40 ms from the beat can no longer pass as one). Kick = the onset of 30..140 Hz (a bass guitar that keeps the band loud does not count), snare / clap = body (160..1500 Hz) and crack (1.5..8 kHz) arriving together, hat = the bright energy. ONE attack definition: the half height of the band's linear envelope across its steepest 6 ms rise, minus a per-band bias measured on synthetic truth (kick with a 2 / 3 / 5 ms ramp -0.3 / +0.6 / +1.5 ms mean, max 2.0 / 2.4 / 3.3; snare and hat within 0.5 ms; a click-less 808 reads about 4 ms late with a 3 ms scatter: the limit of that sound). `measure()` is kept for old callers | imported |
| `preview.py` | rough preview of the whole edit in about half a minute, BEFORE `prep.py` (no store needed): the nearest real source frame for every output frame (no interpolation, no effects, slow motion steps frame by frame), the style's framing, hard cuts (an overlapping house transition is a cross-fade), the words as plain text, the song, a "PREVIEW" label; `--marks` frames every kill. Cuts and kill marks sit on the same frames as the real render (`take_of(n)`, the shown kill beat), words start `HIT_LEAD` frames early, and the audio is sliced by sample count (no `-ss` before `-i`: within 0.02 ms of the song for flac, mp3 and m4a) | `$PY preview.py [preview.mp4] [--scale 0.5] [--marks]` |
| `refstyle/ref_analyze.py` | reference style: everything the reference video does, measured (layout, every cut on the lattice of its own grid with the offset in frames, the frames its cuts and kill flashes come before the drum attack, its kills from the kill feed, transition kinds, speed, words, colour, ending), plus SUGGESTED SETTINGS and the `adopt` block of `ref_notes.json` that the drafter follows (reference-style.md, "Reading the reference") | `$PY ref_analyze.py "$REF" --music src/music.flac` |
| `refstyle/draft_ref_timeline.py` | reference style: first-draft `timeline.py` from `plan.json` (entries, music block, the `draft:cut` block with `CUT`, `CUT_LEAD`, `HIT_LEAD`, intro words, luma fade); every kill / bump / boom / riser end on a measured attack, kills-mode cuts on lattice lines with a SHOWN lead of 12 to 16 frames, the reference's `adopt` block followed (plan > reference > model), `reference followed / not followed` block, K and BPM-drift refusals; reference-style.md, "Drafting the entry list" | `$PY draft_ref_timeline.py plan.json [-o draft.py] [--force] [--compare timeline_ref_example.py]` |
| `refstyle/lyrics_sync.py` | lyric words in one command: demucs voice stem of the section (`lyrics_stem.py`: sample-exact cut, at least 9 s separated because demucs delays shorter inputs by up to 3.2 ms), CTC alignment of the confirmed words in `lyrics.txt` by two models (`lyrics_ctc_align.py`, in `venv_sep`: the frame stride is exactly 320 samples = 20.000 ms, each model runs 8 times with the stem moved by 2.5 ms steps and the median is kept), each word moved onto its sung ATTACK (`cues_from_alignment.py`, `lyrics_attack.py`; CTC is only a prior) -> `lyric_cues.json` + `lyrics/cue_audit.json` (the flags), `lyrics/sync_N.jpg` and zoom panels (`lyric_sync_sheet.py --zoom flagged\|all\|WORD,WORD`), and the numeric audit `lyrics_audit.py` (exit 1 beyond 25 ms of a confident attack with no flag); it refuses a MUSIC that is not lossless and a timeline without SYNC 2; about 50 s for a 31 s section, cached re-runs in seconds (reference-style.md, "Lyric words") | `$PY lyrics_sync.py [--stem-only] [--t0 S --t1 S] [--models mms] [--red=A:B] [--last-end BEAT] [--adv 0]` |
| `timeline.py` | the edit; run it to print and self-check (it runs `preflight.py` first) | `$PY timeline.py` |
| `preflight.py` | checks timeline.py and lists EVERY problem at once: `SYNC = 2` (an older timeline is refused with the update message), the grid identities (FPS, PER, FPB, MUSIC_T0, N_FRAMES), every cut and shot on a whole frame, `HITS` present with one musical hit per kill shown on `vis(hit, HIT_LEAD)` and inside its take, clips missing from `src/`, anchors that do not increase, kills outside their segment or clip, a misspelled `CUTS_ON`, a song shorter than the edit, malformed `BUMPS`, `BOOMS`, `LUMA_IN`, `ACC`, `IMPACT`, sound levels or segment `white` / `shot_from`. `ranges.py`, `check_store.py`, `densify.py`, `render.py`, `audio.py`, `check.py`, `kill_lags.py` and `run.sh` run it themselves | `$PY preflight.py` |
| `deathstrip.py` | when each enemy visibly dies: per kill 1:1 crops around the crosshair at K-8, K, K+4 ... K+52 and the kill feed at K+4 ... K+20; tiles the timeline shows are green, the rest red; prints per kill how many frames after the shot the edit shows and a WARNING when that is less than the entry's `upto`. `upto` for plan.json = frames from K until the body is down | `$PY deathstrip.py ds.jpg` (every kill of timeline.py, two per sheet), `$PY deathstrip.py ds.jpg c01@862 c04@303` (candidates), `--fine` (K to K+30 every second frame, wider crop) |
| `ranges.py` | footage needed by the timeline -> `ranges.json` (both layers of a house-style overlapping transition, from `T.active`) | `$PY ranges.py` |
| `prep.py` | builds the sub-frame store with RIFE (resumable) | `$PY prep.py ranges.json` |
| `densify.py` | more in-betweens where the picture moves fast | `$PY densify.py run 12 28`; `plan 12 28` only prints. Both take the two thresholds (output pixels of travel per frame that trigger 8x and 16x) |
| `repair.py` | rebuilds a duplicated source frame in the store | `$PY repair.py c3:125` |
| `fixends.py` | rebuilds the sub-frames next to every real frame in a store built without `rifeutil.Tween` (RIFE dead zone, see pitfalls.md); a store built by the bundled `prep.py` does not need it | `$PY fixends.py` |
| `posmap.py` | measures where every stored sixteenth really sits (`posmap.json`, read by the refstyle `render.py`) | `$PY posmap.py` after any change of the store |
| `check_store.py` | store covers the timeline (both layers of a house transition: `T.active`); the grid is fine enough where a take plays slower than 0.7x ("too coarse": a 4x store there renders a double-exposed slow motion); no run of duplicated real frames (a freeze); no damaged (cut-off) JPEG. Exit code 1 when footage is missing, too coarse, duplicated or a file is damaged | `$PY check_store.py`; `--delete` removes damaged files (then `prep.py ranges.json` rebuilds them) |
| `render.py` | frames -> video part, or stills | `$PY render.py 0 742 part.mp4`, `$PY render.py 116 117 k.jpg`, `$PY render.py 100 140 s.jpg 4` |
| `kill_lags.py` | gunshot onset relative to K for every kill, to the sample (`measure()`: house `audio.py` calls it per kill; clips are decoded on the file's clock) | `$PY kill_lags.py` |
| `audio.py` | `mix.wav` + stems, and where each shot lands; `audio_report.json` per kill (the musical beat, the shown beat, the placement state, the onset in ms) | `$PY audio.py` |
| `mix_spec.py` | spectrogram of mix and stems in beats | `$PY mix_spec.py -5.2 5 59 72` |
| `run.sh` | 3 parallel parts + sound + mux -> master. Refuses to start when the venv, the timeline or the store is not ready; when one part fails it stops the others and shows the end of its log; gives each part its exact `duration` in the concat list and then runs `ff.py pts video.mp4 N A B` (every video pts step must be exactly 1/60 s and the count N, else it names the join); ends with `peakguard.py`; the last line gives the render speed | `bash run.sh master.mp4` (the mux applies `volume=2.36` in the house `run.sh`; `scripts/refstyle/run.sh` takes its chain from `audio.master_chain()`, `volume = 1.18 / HEADROOM`: see "How the sound is made (audio.py)") |
| `check.py` | smoothness, kill strips, overview, loudness, and per kill the MEASURED flash frame (ok / EARLY / LATE / spread / not measurable against the shot frame); refuses a timeline without SYNC 2 | `$PY check.py master.mp4 --sheets` |
| `deliver.sh` | runs `gate.py` (refuses on any ERROR), then the upload copy from the master, then `peakguard.py`, then `gate.py --sync-only` on the upload copy (an ERROR renames it `*.rejected.mp4` and fails) | `bash deliver.sh master.mp4 out.mp4`; `ACCEPT=<code> bash deliver.sh ...` waives one accepted problem, never one of the sync codes (house: crf 18, max 17 Mbps; `scripts/refstyle/deliver.sh`: crf 17, max 22 Mbps, and the same `audio.master_chain()` as its `run.sh`) |
| `gate.py` | the delivery gate: SYNC 2 timeline, file against timeline, the master's `timeline_sha1` stamp, picture (frozen, stalls, kill sync), sound (peak, loudness), `audio_report.json`, `kill_rank.py`, `kverify.py` (with the game's profile), lyrics, and the independent sync audit (`syncaudit.py`); ERROR refuses, WARN passes; every item that could not be measured is a WARN, never a pass; a waived code goes to LEIAME.md (verification.md, "The delivery gate") | called by `deliver.sh`; by hand `$PY gate.py master.mp4 [--json] [--no-pixels] [--table] [--deep] [--accept CODE]` (15 s to 2 min); `$PY gate.py --sync-only FILE` audits one file (the upload copy) without the master; `--codes` lists every code |
| `syncaudit.py` | the audit of the FINISHED file, read from the output only: pts lattice, the decoded audio against the real song (lag in samples and drift), gunshot onsets against the musical hits, accent frames, the muzzle flash found by matching the source's flash image, cut frames, words, the song's grid phase; prints the table (expected frame / measured frame / ms) and the findings (verification.md, "Sync audit") | `$PY syncaudit.py master.mp4 [--deep]`; usually through `gate.py` |
| `kverify.py` | re-measures K of every kill on the pictures (ammo-counter step in any digit colour, muzzle-flash start, replay cut): verified / CORRECT / SUSPECT / not measurable, sheets `kv_NN.jpg`, `kv.json`; `--update` writes the verdict into `kills.json` (`how`, `conf`, `verified`, `K_was`); `--game NAME` picks the profile in `games/` (default `valorant`); exit 1 on a suspect or corrected kill, and on a timeline without SYNC 2 | `$PY kverify.py [timeline.py\|plan.json\|kills.json [--ids 3,4]\|clip@K] [--game NAME]` |
| `peakguard.py` | decodes the finished file's audio; if its peak is above -0.5 dBFS (the AAC encoder overshoots the limiter on some songs) it encodes the audio again from `mix.wav` with a lower limiter ceiling, picture copied; the limiter is `alimiter ... latency=1` like `run.sh` and `deliver.sh` (without it the look-ahead delays the whole sound by 143 samples = 2.979 ms) | called by `run.sh` and `deliver.sh`; by hand `$PY peakguard.py out.mp4 2.36` (house) or `$PY peakguard.py out.mp4 chain mix.wav` (reference style: `audio.master_chain()`); `--filter VOLUME [LIMIT]` prints the chain |
| `look.py` | the edit options (`LOOK` in timeline.py): defaults, presets suave / padrao / intensa / maxima / modelo (the model edit's look, the drafter's default), colour grades; both renderers read it, `preflight.py` checks it | `$PY look.py` prints every option with its range |
| `rife_compare.py` | objective comparison of RIFE models | `$PY rife_compare.py rife-v4.25 rife-v4.26`: only `rife-v4.25` ships; download any other version from github.com/TNTwise/rife-ncnn-vulkan (folder `models/`) into `models/<name>/` (it must hold `flownet.bin`; the name must keep the version) |

`scripts/refstyle/` holds the files that replace or extend these for the reference style (its README.md
lists them): renderer, lyric text, kill finding in raw recordings, word alignment, per-kill gunshots, cover.

Each script starts with a docstring that explains its output and how to read it. Shared modules:
`ff.py` (finds ffmpeg and ffprobe), `clipio.py` (frame access by index), `rifeutil.py` (loads the
interpolation model, checks the GPU, writes store files safely), `preflight.py` (timeline and environment checks).
A prep, densify or repair that is stopped (Ctrl+C, a crash, a full disk) leaves no half-written file: run the same
command again and it builds only what is missing.

## What costs time

| Step | Time | Notes |
|---|---|---|
| `prep.py`, `densify.py` | 6 to 10 sub-frames per second on an idle GTX 1650; about 2.5 to 4 while something else uses the GPU; 0.4 on the CPU (`RIFE_GPU=-1`) | about 30 min and 7 GB for the whole 37 s house edit; the 32.6 s vertical default edit took 45 min of `prep.py` and 29 min of `densify.py` at about 2.5 per second, 8.2 GB; only missing files are built; `ranges.py` prints the GPU and CPU estimate for the current timeline |
| `render.py` | 0.3 to 5 s per frame | slow motion and transitions are the slow frames; a log line every 25 frames (reference style: every 100) |
| `run.sh` | 12 to 16 min for 2226 frames (house), 15 min for 2786 (reference horizontal), 12 min for 1958 (vertical default, 2.9 fps), 5 min for 510; a 3 s test edit rendered at 1.7 to 3.0 frames per second | uses the whole CPU; always in the background. Short edits cost more per frame. The last line prints the speed of the user's PC |
| `peek.py` | 1.3 s per tile when stepping | a one-per-second overview of a 17 s clip takes 25 s |
| `audio.py`, `deliver.sh` | 5 s, 1 min | |
| `check.py` | 1 min | decodes the whole video |
| `syncaudit.py`, `gate.py --sync-only` | about 1 min for a 45 s edit; `--deep` 1 to 2 min more | decodes the file and the clips' flash frames; `deliver.sh` runs it on the upload copy |
| reference style, 1920x1080 | prep 6.9 sub-frames/s, 0.55 MB each; 46 s = 23,500 files, 13 GB, about 55 min; render 15 min | with a game running on the PC: interpolation 8x slower, render 35 min at BelowNormal priority |

Start `prep.py` in the background as soon as the anchors are roughly right and keep working (sound,
stills of finished ranges; in the reference style run `$PY posmap.py` once before the first still, it works
on a partial store). Poll with short commands; never block on one long wait. `ranges.py` prints the size
and time to expect for the store (it knows the wider reference-style frames).

## What to re-run after a change

| Changed | Re-run |
|---|---|
| anchors, kills, segments | `timeline.py`, `ranges.py`, `prep.py`, `densify.py`, `check_store.py`, stills, `run.sh` |
| `lag`, `voice`, `SWEEP`, `RISERS`, mix levels | `audio.py`, then only the mux command of `run.sh` and `$PY peakguard.py master.mp4 2.36` (reference style: `$PY peakguard.py master.mp4 chain mix.wav`) |
| `BPM`, `BEAT0`, `M0` (the song's grid) | `music_hits.py`, draft again (every event is a measured time converted with the grid: a new grid moves them all), then everything under "anchors, kills, segments" |
| effect values in `render.py`, `LOOK`, `FRAME` (reference style), transitions, `PULSES`, `bars`, `push` | stills, `run.sh` (the store does not change) |
| one third of the video | `$PY render.py A B part_1.mp4`, then the concat and mux commands of `run.sh` (parts split at N/3 and 2N/3) |
| upload bit rate | `deliver.sh` |
| the store itself (`prep.py`, `densify.py`, `fixends.py`, `repair.py`) | reference style: `posmap.py`; then `check_store.py`, stills, `run.sh` |
| lyric cues (`lyric_cues.json`, `T.TEXT`), `textfx.py` | stills of a few words, `run.sh` |

## Handling jobs on the user's PC

All of these were run as written, in Git Bash. A PowerShell `$` is written `\$` there (bash would expand
`$_` and `$PID` itself).

```bash
# long job: start it with run_in_background and a log. The harness tells you when the command exits: read the log then.
$PY prep.py ranges.json > prep.log 2>&1 ; tail -3 prep.log
#   a finished job ends with:  prep.py "total NNNs" | densify.py "done N" | fixends.py "done: rebuilt N sub-frames" | run.sh, deliver.sh "done <file>"
#   run.sh without "done": a render part failed (its traceback is in part_N.log) and the other two parts may still be
#   running: list them and stop them by ID before starting again
#   a job you cannot be notified about: wait in a background command, never in the foreground (cut after 10 min):
#   until grep -q "^total\|^done\|Traceback\|Error" prep.log; do sleep 10; done; tail -2 prep.log

# is a game using the GPU? Tens of percent on a process that is not mine = a game (idle desktop: under 5 %)
powershell -NoProfile -Command "(Get-Counter '\GPU Engine(*engtype_3D)\Utilization Percentage').CounterSamples | Sort-Object CookedValue -Descending | Select-Object -First 3 | ForEach-Object { \$id = [int](\$_.InstanceName -replace '^pid_(\d+)_.*', '\$1'); '{0,5:N1} %  {1}  (pid {2})' -f \$_.CookedValue, (Get-Process -Id \$id -ErrorAction SilentlyContinue).ProcessName, \$id }"

# what is running. Other sessions run their own python on the user's PC (seen: another project's tests);
# mine have this project's scripts in the command line (render.py, prep.py, densify.py, fixends.py, part_N.mp4)
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -match 'python|ffmpeg' } | Select-Object ProcessId, Name, CommandLine | Format-List | Out-String -Width 300"

# stop a job: TaskStop on its background task, list again, then stop what is left BY ID. Never by a
# command-line pattern (it also matches the shell that carries the command) and never by name (other sessions).
# The venv python is a launcher: each job shows as two python.exe with the same arguments, stop both.
powershell -NoProfile -Command "Stop-Process -Id 1234, 5678 -Force"

# a game is only detected and the render must go on: lower the priority of my render processes
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -match 'python|ffmpeg' -and \$_.CommandLine -match 'render\.py|part_\d\.mp4' } | ForEach-Object { (Get-Process -Id \$_.ProcessId).PriorityClass = 'BelowNormal' }"

# after stopping a job that writes the store (prep, densify, fixends, repair write the files in place): the newest
# files must end with FF D9. This removes the truncated ones; then $PY prep.py ranges.json and
# $PY densify.py run 12 28 (each builds only what is missing), and after them the stopped job if it was fixends.py or repair.py
$PY -c "import glob,os;[(print('removed incomplete',f),os.remove(f)) for f in sorted(glob.glob('store/*/*.jpg'),key=os.path.getmtime)[-40:] if open(f,'rb').read()[-2:]!=b'\xff\xd9']"
```

Do not delete `store/`, `src/`, masters or earlier versions yourself: report their sizes and where they are.
Deleting is the user's call.

## How the picture is made (render.py)

The house `render.py`; `scripts/refstyle/render.py` shares the store, time map and shutter integration but has no
window or backdrop and a different set of effects (reference-style.md, "The style and how it is built").

- **Store**: `store/<clip>/<key>.jpg`, key = frame index x 16 + sixteenths, JPEG quality 95 4:4:4, the
  1344x1080 middle of the 1920x1080 frame (reference style: the whole 1920x1080 frame). A 4x grid (240 fps) everywhere, 16x (960 fps) where the edit
  runs slower than 0.7x, and 8x or 16x where the picture travels more than 12 or 28 output pixels per frame.
- **Time**: `timeline.TimeMap` is a monotone cubic through the anchors (beat -> source frame), so every
  speed change is eased. `lead()` and `tail()` build the usual shapes.
- **Timing (SYNC 2)**: the beat axis is linear: output frame n shows beat `frame_beat(n) = R0 + n / FPB`. A cut or shot is built
  on `vis(beat, lead)`, an exact output frame, and the take on screen at frame n is `take_of(n)` (a frame index, no float
  compare). Every accent of a shot (zoom punch, shake, exposure pop, fringe, impact frames, backdrop pulse) is a function of
  the whole frames since the shot frame: it starts there at its peak (instant attack, then the same ring-down as before; the
  house style's pre-kill zoom build-up peaks there too). Reference style: the frames just before and on the shot frame are
  read at their exact source position with no shutter blend, so the muzzle flash is whole on the shot frame and absent on
  the one before.
- **Shutter integration**: an output frame is the average of the stored sub-frames over its shutter
  interval (`SHUTTER = 0.65` of the frame time, box filter over the piecewise-linear interpolation).
  This gives exact time sampling at any speed and physically right motion blur. It is the reason the
  video does not judder.
- **Camera**: `cam()` returns zoom, offset and roll (kill zooms, shake, pushes, cuts with zoom; in the reference style
  `cam(n)` and `look(n)` take the output frame number, in the house style a beat).
  Camera and transition moves are supersampled the same way: up to 40 sub-samples, at most 4 px of
  travel each (`CAM_SHUTTER = 0.85`), so a whip or spin smears instead of stepping.
- **Compositing** in linear light (gamma 2.2): blurred backdrop, window with rounded mask, stroke, halo
  and shadow, bloom and streaks, saturation, vignette, S-curve, then dither and grain (without them the
  smooth backdrop bands after encoding).
- **Encode**: x264 `-preset slow -crf 14 -g 60 aq-mode=3`, bt709 tags, light unsharp. Source frames are
  converted `tv -> pc` range on the way in and back on the way out.

Since October 2026 `prep.py`, `densify.py` and `repair.py` interpolate through `rifeutil.Tween` (no time
step near 0 or 1, see pitfalls.md), so a store rebuilt today differs slightly from the one behind the house
example's master.

`render.py` is deterministic: the same store and timeline give the same bytes. The master's picture is
bit-reproducible; the upload copy is not (x264 with a bit-rate cap and threads differs run to run by
about 0.1 %, harmless).

The scripts that load RIFE (`prep.py`, `densify.py`, `repair.py`, `rife_compare.py`) end with
`rifeutil.finish()`: without it the process crashes while unloading (exit code 139) after the work is
done. Any new script that calls `rifeutil.load()` must end the same way.

## How the sound is made (audio.py)

House style. The reference style's `scripts/refstyle/audio.py` places one gunshot per kill at natural pitch (a swish on
blur-in cuts only with `WHOOSH_BLUR`, centred on the cut's musical beat `s["m0"]`) and writes the mix at 0.8 (reference-style.md, "Sound").

- **Music**: cut at `T.MUSIC_T0`, optional low-pass sweep (`T.SWEEP`), fade out over `T.FADE_OUT`. The mix is exactly
  `N_FRAMES / FPS` long (the picture's length).
- **Game sound**: follows the same time maps as the picture. The gunshot's `lag` is MEASURED per kill
  (`kill_lags.measure`, to the sample) and corrected for the offset between the flash frame and the musical hit,
  so the shot sounds on the hit itself; a typed `S(lag=...)` is accepted only when the clip is silent around the
  kill or it agrees with the measurement within 0.25 frame. It fades out between 0.7x and 0.25x and between 1.3x
  and 1.8x (no pitched-down or chipmunk sound); kills of level 2 and 3 stay audible. `voice=` and `stretch=True`
  use a pitch-preserving stretch (WSOLA) instead of resampling. A causal 70 Hz high-pass (no pre-ring) so it
  does not fight the bass.
- **Effects**: risers from `T.RISERS`, a whoosh on every whip, spin and zoom transition (panned with
  the whip direction, centred on the cut's musical beat `s["m0"]`).
- **Mix**: `0.84 * music + 0.60 * game + effects`, all three faded out over `T.FADE_OUT`. The mix peaks
  above full scale (1.29 in the house example: a loud master plus shots), so `mix.wav` and the stems are written at
  half level; `run.sh` gives the level back (house: `volume=2.36` = 1.18 x 2; the reference style writes at
  `HEADROOM`, 0.8 unless timeline.py sets it, 0.5 in a drafted model-style edit, and its `run.sh`, `deliver.sh` and
  `peakguard.py ... chain` all use `audio.master_chain()` = `volume = 1.18 / HEADROOM`), limits at 0.82 (`alimiter ... latency=1`: without `latency=1` the limiter's look-ahead would delay the whole sound by 143 samples = 2.979 ms), and encodes
  AAC 320k with PNS, TNS and intensity stereo off. Result: -8.5 LUFS, decoded peak -0.7 dBFS (house example). The
  AAC encoder can still overshoot the limiter on some songs (measured +0.035 dBFS on one test edit): `peakguard.py`,
  at the end of `run.sh` and `deliver.sh`, decodes the result and encodes the audio again with a lower ceiling
  until the decoded peak is below -0.5 dBFS (test: -0.34 -> -1.48 dBFS in one pass).
  (the house example itself was mixed through a full-level 16-bit file: same loudness and peak, but 0.05 % of its
  samples were flattened for up to 0.4 ms before the limiter.)

## Other games, other formats

- Kill detection for any game: `kills_auto.py` with a profile in `games/` (SKILL.md, step 3). The Valorant-only tools
  (`find_kills.py`, `kill_table.py`: the banner badge at x 935, y 841, 50x50; `refstyle/detect_kills.py`, `mykills.py`:
  kill feed and ammo counter of the raw file) stay for Valorant 1080p60 recordings linked by `ingest.py`.
- Horizontal full-frame output: use `scripts/refstyle/` (render.py, check.py and clipio.py are already adapted).
