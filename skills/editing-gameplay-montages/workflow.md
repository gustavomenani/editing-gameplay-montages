# Workflow, step by step

`PY=./venv311/Scripts/python`, in Git Bash, from the project folder `<clips folder>/_editor/`. Every Bash call is a fresh shell, so
begin each command with `cd "<project>" && export PY=./venv311/Scripts/python &&` (exported, because `run.sh` and `deliver.sh` read
`$PY` from the environment). Setup, the full script table and the timings are in
pipeline.md. The order below is the one that finds a bad decision early, when it costs a minute instead of a render.

## 1. Project

Copy the scripts into `_editor/`: `scripts/*.*` (files only), then `scripts/refstyle/*.*` over them for the default style, plus
`games/` and `models/`. The style is chosen once per project folder and never mixed (pipeline.md "Setup"). Then:

```
uv venv --python 3.11 venv311
uv pip install --python venv311/Scripts/python.exe -r requirements.txt
$PY doctor.py            # PRONTO, or FALTA: each item with its fix; AVISO does not stop you but goes in the report
```

`clips.json` (forward slashes; short names become file names): `{"c1": "C:/.../clip1.mp4", "music": "C:/.../song.flac"}`. Then
`$PY ingest.py && $PY mkpts.py`. `ingest.py` makes 1920x1080 60 fps working copies from anything (1440p, 4K, 4:3, 21:9, 30-240 fps,
HEVC/AV1, .ts, OBS multi-track, HDR, rotated phone clips) and exits 1 when an entry failed, naming it: read its last lines.

## 2. Reference video (when the folder has one: always)

```
$PY ref_analyze.py "$REF" --music src/music.flac
```

Then read `ref_notes.md` and every image in `ref_sheets/` (reference-style.md, "Reading the reference"). The `adopt` block of
`ref_notes.json` (cut lattice, how many frames its cuts and kill flashes come before the drum, cut gaps, transitions, slow motion,
intro, ending, kills per second) is what the drafter follows; plan keys only for what the user said. A reference with no traits
measured is a reference the draft cannot follow: say so instead of pretending.

## 3. Watch the clips and choose the kills

```
$PY dupes.py                       # the same footage in several files, with the offset -> dupes.json
$PY peek.py c1 0 99999 60          # one tile per second
$PY kills_auto.py valorant         # any game: profiles in games/ -> kills.json + autokill_NN.jpg
$PY kill_rank.py --seconds 30      # every kill scored, the best set for the length -> kill_rank_*.jpg
```

`kills.json` is `{id: {clip, K, feed, conf, method, how, verified}}`. K is ALWAYS the shot that killed: the last shot with an ammo step
before the feed row (which slides in 4 to 12 frames after it), never the first shot of a spray, never a flash without an ammo step
while the counter is steady. Only the `valorant` profile is measured on footage (26 clips: K exact in 62 of the 66 real kills of two
accepted edits, within 1 frame in 3); `cs2` comes from the game's HUD files and was never run on footage, `generic` picks the wrong
shot in sprays - check both on your own frames (`--regions` draws the rectangles) and read the review sheets.

The score orders the candidates, YOU choose by reading the stills and the user's words: never build a take on a kill marked `hidden`
(nothing visible at the aim), `no_shot`, or not the player's. When the folder has a full recording and its trims, `dupes.py` says so
and `kill_rank.py` drops the second copy.

## 3b. Verify every K on the pictures

```
$PY kverify.py plan.json           # verified / CORRECT / SUSPECT / not measurable + kv_NN.jpg sheets
$PY kverify.py kills.json --update # writes the verdict back ("how": ammo | flash)
```

A K one frame off is 16.7 ms of desync and a guessed K is wrong in 3 of 4 cases. The drafters refuse an unverified K: no kills.json,
no entry, a plan K different from the entry's, `how` not `ammo`/`flash`, or `"k_checked": true` after you read the sheets yourself.
`--game NAME` picks the profile (the gate takes it from `GAME` in timeline.py).

## 4. Music

```
$PY music_tempo.py                 # BPM + its half/double alternative, evidence, drops, steadiness
$PY music_grid.py 130 0.423 27 72  # never skip: it can REFUSE the BPM and prints BEAT0
$PY music_hits.py                  # hits.json: every hit with its attack time t, r = hit(t), band
$PY music_pulses.py                # the strengths on the half beats and the PLACEMENT CHECK
```

Read what they print. A WEAK fit is a warning with the drop table; `NO TEMPO` (WEAK and not steady) stops with exit 1. A refused BPM
names the better one: run it again with that BPM. `constant grid NOT adequate` (a live drummer, swing, a wandering tempo) means no kill,
cut, bump or boom goes on a grid beat: each goes on its hit's own time from `hits.json`. A song that is not flac/wav/aiff was decoded
once to `src/music.flac` by `ingest.py`, and every tool reads that (ffmpeg's seek is 8 to 40 ms off the sample in AAC/mp3).

Then fill the music block of `timeline.py` (`MUSIC`, `BPM`, `BEAT0`, `M0`, `R0`, `R1`, `FADE_OUT`, `CUTS_ON`, the `RISERS` beats, and
per style `SWEEP`/`PULSES` or `LUMA_FADE`). Choosing the section: edit-design.md "Music", valid for both styles. The example's
segments are still in the file at this point, so the stars `music_pulses.py` puts on kills are theirs: ignore them until step 5.

## 5. Write timeline.py

Measure first how long each death takes: `$PY deathstrip.py ds.jpg c01@862 c04@303 ...` (1:1 crops K-8 to K+52 and the kill feed;
`--fine` for every second frame up to K+30), and note per kill `upto` = frames from K until the body is down.

Write `plan.json`: the plays in order with `upto`, the drop kill `"bullet": true`, the pre-drop kills in `intro.kills` (model-edit.md
says where each part of the song goes; the bullet time where the drums thin out is found by the drafter, `"auto_bullet"`), then let the
drafter write the draft:

```
$PY draft_ref_timeline.py plan.json      # default style, with ref_notes.json from step 2
$PY draft_timeline.py plan.json          # house style
```

It refuses, with numbers: an unverified K, a BPM whose grid drifts against the hits, and a plan that cannot fit. Read its explanation
and statistics, compare them with model-edit.md section 9, then tweak by hand. It follows model-edit.md by default (14-frame leads,
deaths to `upto`, levels, blur-ins, bumps, booms, risers, the thin-out bullet time, `LOOK = "modelo"`), and with a reference it follows
the `adopt` block (precedence per trait: the plan's keys > the reference > the model edit) and prints `reference followed / not
followed (why)` for each trait.

Nothing of the example stays: its clips, frames, `SEGS`/`E`, `PULSES`, `RISERS`, `SWEEP`, `_T` and docstring are the author's. Never
run `ranges.py` or `prep.py` on the example's segments: they point at the author's clips and frames.

Then the two gates of the step:

```
$PY timeline.py            # must pass: exact frames, every take a frame of its own, preflight (all problems at once)
$PY music_pulses.py        # must end with no FAIL: every kill, cut, bump and boom within 8.3 ms of a measured attack
```

## 6. Preview while the heavy work runs

```
$PY preview.py ../<name>_previa.mp4
```

Half a minute horizontal, about a minute vertical, no store needed. Tell the user in one line where it is and that it is rough (no
effects, slow motion choppy on purpose): it shows the order, the cuts, the kills on the beat, the words and the music. Do not wait for
an answer; if they comment before the render, change the timeline then (only what they asked; `prep.py` builds only what is missing).

## 7. Footage (the GPU job)

```
$PY ranges.py && $PY prep.py ranges.json      # background: about 30 min and 7 GB for a 37 s edit
$PY densify.py run 12 28
$PY posmap.py                                 # reference style only: after any change of the store
$PY check_store.py                            # 0 missing, 0 too coarse, no duplicates
```

Start `prep.py` in the background as soon as the anchors are roughly right and keep working (sound, stills of finished ranges). Poll
with short commands; never block on a long wait (pipeline.md "Handling jobs on the user's PC"). A stopped prep/densify/repair leaves
no half file: run the same command again.

## 8. Stills before video

```
$PY render.py N N+1 look.jpg
```

On each kill, every transition, every slow-motion frame, the words, the first and last second. Read them. Stills can start while
`prep.py` still runs; reference style, after one `posmap.py`. Enlarged crops of your stills beside the same crops of the reference
BEFORE the first full render (verification.md).

## 9. Sound

```
$PY audio.py
```

It finds each gunshot's onset in the clip's own sound to the sample and puts it on its musical hit. Every sound sits on a musical beat,
the blur-in whooshes on the cut's beat. The mix is exactly as long as the picture and `mix peak` must be below 1.0. Read
`audio_report.json` before the render: only "measured" and "donor" gunshots are verified; "clip offset" and "edit median" are printed
in ms and warned about by the gate.

## 10. Render

```
bash run.sh master.mp4        # background, 12 to 16 min
```

It refuses to start when the venv, the timeline or the store is not ready, and stops the other parts when one fails.

## 11. Verify the file you cannot watch

```
$PY check.py master.mp4 --sheets     # per kill the MEASURED flash frame: ok / EARLY / LATE / not measurable
$PY syncaudit.py master.mp4          # independent audit of the finished file
```

`not measurable` is never a pass. Read `sync_*.jpg` (tile +0 is the shot frame) and `pv_*.jpg`, compare the numbers with model-edit.md
section 9, fix and repeat (verification.md).

## Special situations

| The folder / request is | Do |
|---|---|
| 2 or 3 clips only | target 10 to 15 s (a 30 s edit would stretch takes past what the footage carries) and say why; never repeat a play |
| one 40 minute raw recording | `ingest.py --fast` (the default above 90 s), find the kills with `kills_auto.py` (it reads `src/`), then upgrade only the chosen ranges to `--exact`: `ingest.py --exact --only c1`, delete `store/c1`, `mkpts.py`, `prep.py` again (the frame grid is the same, so K stays) |
| no song in the folder | ask for it once in the briefing (it is one of the six questions); without it there is no grid and no edit |
| several candidate songs | pick the one that gives the section the model needs (a break, a drop, a last sung word), name the choice and the discarded one in the report |
| a song already used in another edit | nothing special; say so if the user may not remember |
| a reference only as a link or a description | use the model edit's patterns; ask once for the file; never claim to have copied what you did not measure |
| a clip with no sound | its kills get `"mute": true` (or `ACCEPT=no-gunshot` if the user accepts a silent kill): the house `audio.py` stops on a shot it cannot measure, the reference style prints it as `silent` |
| a 60 second edit | about 60 kills, 15 to 25 GB of store and roughly twice the render of a 30 s one: say the numbers in the briefing instead of promising the usual 7 to 13 GB |
| VR / ultrawide footage | ingest crops 21:9 and 32:9 at the centre (or `--aspect pad`); VR is cropped like ultrawide: say what is lost |
| the user changes their mind mid-render | stop the heavy job by process id (pipeline.md "Handling jobs on the user's PC"), change only what they asked, `ranges.py`, `prep.py`, then render again; never let two renders share the folder |
| a second version after feedback | feedback.md's table first, then the steps it names; a change that does not touch the cuts only needs `run.sh`, not `prep.py` |

## 12. Deliver, and save what was learned

```
bash deliver.sh master.mp4 "../<name>_v1.mp4"
```

Never over an earlier version. It runs `gate.py` first and refuses while an ERROR is left; after the upload copy and `peakguard.py` it
runs `gate.py --sync-only` on the file that leaves and renames it `*.rejected.mp4` on an ERROR. A problem the user explicitly accepts is
waived per code only (`ACCEPT=<code> bash deliver.sh ...`), written to `LEIAME.md`, and said in the report. Then `check.py` on the
upload copy.

Before the final report, write what was learned into the project's `LEIAME.md` (a section "Lições para a skill", each lesson in generic
words: no folder names, paths, clip names, song titles or delivered file names) and into the session's memory. During a video NEVER
edit the installed skill: it is a copy of the public repository, the next install replaces it, and the user's projects must not leak
into it. The skill itself changes only when the user asks for it ("atualiza a skill", "manda pro GitHub"): apply those lessons in a
clone of the repository, test them, commit, push, and run the installer again.
