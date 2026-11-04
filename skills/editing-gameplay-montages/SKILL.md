---
name: editing-gameplay-montages
description: Edit gameplay clips (Valorant, CS2 or any shooter) into a music-synced highlight montage, frag movie, velocity edit or TikTok/Reels/Shorts "edit" with beat sync, slow motion, speed ramps, kill zooms, transitions, lyric words and a cover image; also copy the editing of a reference video ("com a mesma edição desse vídeo"), or fix a rendered edit that stutters ("travado", "quedas de fps"), has choppy slow motion or kills off the beat. Portuguese - "edita um vídeo", "faz um montage", "highlight", "edit pro TikTok", "faz uma capa". Not for plain trimming, joining or converting clips (use ffmpeg).
---

# Editing gameplay montages

A music-synced gameplay edit rendered by a custom Python pipeline. ffmpeg only decodes and encodes; time remapping, motion blur,
camera moves, transitions, text, colour and sound are computed in Python from one file, `timeline.py`, written in beats of the music.

**Core principle: you cannot watch or hear the video, so nothing is done by feel.** Frames are addressed by index, beats are measured
on the waveform, each kill is pinned to its muzzle-flash frame, and every render is judged by numbers and by images you read. Every
shortcut around this produced a version the user sent back (pitfalls.md).

The bundled scripts are measured, not assumed (on synthetic projects with sample-exact truth: every picture event on its exact frame,
every gunshot within 0.2 ms, the delivered sound within 0.1 ms of the song; verification.md). Copy them into the project and edit
`timeline.py`; do not rewrite the pipeline from memory.

## The rules that are never broken

1. **Every event on a MEASURED hit.** A kill, a cut, a bump, a boom, a riser end and a word sit on the attack of a drum hit
   (`beat_hits.py` is the one attack definition; `music_hits.py` writes `hits.json`) or a sung onset, converted with
   `hit(t) = (t - BEAT0) / PER - M0` to 9 decimals. A grid line only where the music has no hit. Never the grid time of a hit.
2. **One exact output frame per picture event:** `vis(beat, lead)` = the frame nearest the moment, then `lead` whole frames earlier.
   Cuts use `CUT_LEAD`, shots, accents, flash-ins and words `HIT_LEAD`; default 1 frame, with a reference its measured lead. The
   muzzle flash is whole on that frame and absent on the one before. No `ceil`, no tolerance.
3. **The enemy is SEEN before he dies:** a take's cut is SHOWN 12 to 16 whole frames (`lead_frames`, default 14) before its first shot,
   at real time up to it. Never a kill 4 frames after a cut ("tem kill que nem aparece").
4. **The enemy visibly DIES inside the take:** the take runs until the body is down (`upto`, measured per kill with `deathstrip.py`),
   slow motion only after that frame; the next cut never comes earlier.
5. **No take without a kill**, and no enemy of a few pixels; the kill feed row confirms each kill.
6. **No standing zoom:** never a crop or zoom that enlarges the gameplay for a whole shot. Only short accents that ease in and out,
   capped (`kill_zoom` ≤ 1.5).
7. **Nothing plays faster than real time** unless the user asks for velocity: `MAX_SPEED = 1.0`, which `draft_ref_timeline.py`
   writes and `preflight.py` enforces. In the house style (only on request) state the choice explicitly: `MAX_SPEED = None` (its
   blur-in squeezes to 1.6x) or `1.0` and a calmer blur-in; a timeline that omits it is refused at delivery (`no-ceiling`).
8. **Words:** centred in the exact middle, caps 21 / 19 % of the frame height (226 / 202 px at 1080p; vertical 0.60 of that), widest
   word 70 % of the width, translucent, and a word steps back from the shot until the body is down (`textfx` `duck_death`).
9. **Every kill is the player's**, visible at the aim, and its K is the shot that killed, re-measured on the pictures (`kverify.py`).
   The same play never twice (a DVR and its trim are the same footage); the best kills first (`kill_rank.py --check` clean).
10. **The ending only darkens** (no zoom on the ace); no label, subtitle or watermark.
11. **Output is 1080x1920 or 1920x1080 at 60 fps**, never 4K or an upscale. The whole game screen shows in both frames: vertical puts
    the 16:9 picture in a window over a blurred backdrop of the same footage, never a crop that hides the minimap or kill feed.
12. **Never waive a sync code and never work around the gate** (`av-offset`, `av-drift`, `frame-count`, `cut-frame`, `pts-gap`,
    `timeline-old`, `check-failed`). Fix the cause and render again.

Everything the user actually said, with their words, is in **user-rules.md**; that page outranks a reference video and the defaults.

## Request → path

| The user asks | Style | Read |
|---|---|---|
| anything, with or without a reference video | the DEFAULT (reference style with the model edit's patterns) | model-edit.md, reference-style.md, `scripts/` + `scripts/refstyle/` |
| "estilo house", "estilo janela", "transições que mexem os dois clipes" | the house style, on that request only | edit-design.md, `scripts/` only |
| "mais ou menos intenso", cor, vinheta, grão, tremor, zoom, flash, barras | one `LOOK` value in `timeline.py` | the table below; `$PY look.py` |
| "com a MESMA edição desse vídeo" + a file in the folder | default; `ref_analyze.py` measures it and the `adopt` block drives every trait | reference-style.md "Reading the reference" |
| only a link or a description of an edit ("igual aquele do TikTok") | default with the model edit's patterns; ask for the file once, never promise a copy | reference-style.md |
| letra na tela | default + lyric words (a separate venv and a lossless song) | reference-style.md "Lyric words" |
| capa | default + cover image | reference-style.md "Cover image" |
| another game (Fortnite, Apex, ...) | default; a kill profile is needed and guessed kills must be checked | step 3 below and `games/` |
| "travado", "kill fora do beat", "muito escuro", "tira essa kill" (after a version) | what feedback.md says for that symptom | feedback.md |
| plain trimming, joining or converting | not this skill (ffmpeg directly) | — |

**Defaults when the user leaves it open:** the reference style, vertical, about 30 s, the model edit's patterns and `LOOK = "modelo"`,
cuts with the kill rhythm (`CUTS_ON = "kills"`, a cut 14 frames before each kill), no words unless the lyrics were pasted or asked for,
no cover, the section and plays you judge best. With a reference video in the folder it ALWAYS drives the edit. Write the answers and
the defaults taken into the project's `LEIAME.md`.

## Per-style defaults (the two styles never mix in one project)

| | DEFAULT (reference style) | HOUSE (only on request) |
|---|---|---|
| Frame | vertical `1080x1920`, whole game in a window | vertical `1080x1920`, window shows two thirds of the game width |
| Cuts | `CUTS_ON = "kills"` (the model edit) | `CUTS_ON = "bass"` (the house example's rhythm) |
| Look | `LOOK = "modelo"` | no `LOOK` (`"padrao"`: the house look) |
| Speed | `MAX_SPEED = 1.0` written by the drafter | `MAX_SPEED = None` stated explicitly |
| Words / cover | on request | not built (the house style has no text renderer) |
| Drafter | `draft_ref_timeline.py` | `draft_timeline.py` |

The house style used to be the default; the user found it weaker than the reference style and it crops the game, so it stays available
on request only. Say so when it is asked for, and if that user wants words or a cover, build the default style instead and tell them why.

## The briefing (first reply)

**Language comes first:** write the whole first message in the language of the user's message, and translate every line of the
template (headings, questions, tips) - leave no Portuguese word in an English or Spanish reply.

**Skip the briefing** and say in two or three lines which defaults you take, then start, when either holds: they told you not to ask
("não me pergunte nada", "só faz", "decide você", "don't ask me anything"); or their message already settles the build options AND how
the edit should look (format, length, look or reference video, where transitions land, lyrics, cover, song and section). Plays,
intensity and the game are not reasons to ask once those are set.

Otherwise the first message is the briefing, in the user's language and tone; you may list the folder (read only) first to see the
clips, song and reference, and leave out every item the message or the folder already answers. The template, the per-item questions
and the "never promise" list are in **briefing.md**. Then wait for the answer; after it, decide everything else alone and ask nothing
in the middle of the work.

## Edit options (what the user says → what to set)

Every look option lives in one `LOOK` value in `timeline.py`, read by both renderers through `scripts/look.py` (`$PY look.py` prints
the table with ranges): `LOOK = "intensa"`, `LOOK = {"vignette": 1.6, "shake": 0}`, or `LOOK = {"preset": "intensa", "grade": "cool"}`.
Numbers multiply the worked example's look: 1 = as there, 0 = off, 2 = strong. A value that would break a user rule is clamped and the
clamp is printed; `preflight.py` names a misspelled key ("vinheta" → did you mean "vignette"?). The full mapping, with the ranges to
use for every phrasing a user may try, is in **look-options.md**.

| The user says | Set |
|---|---|
| "suave", "leve", "clean" / "intenso", "agressivo" / "no máximo", "pesado" | `LOOK` preset `"suave"` / `"intensa"` / `"maxima"` |
| "vinheta" / "granulado" / "glow" / "RGB split" / "flash" | `vignette` / `grain` / `bloom` / `fringe` / `flash` |
| "cor quente", "cor fria", "teal & orange", "preto e branco", "cores vivas" | `grade` `"warm"`, `"cool"`, `"teal_orange"`, `"mono"`, `"vibrant"` |
| "sem tremor" / "mais tremor"; "sem zoom nas kills" / "mais zoom" | `shake` 0 / 1.5-2; `kill_zoom` 0 / up to 1.5 |
| "barras de cinema" (horizontal only), "mais borrão nos cortes" | `bars` True; `blur_in` 1.5-2 |
| "transições no ritmo das kills" / "no grave" | `CUTS_ON = "kills"` (default) / `"bass"` |
| "vertical" / "horizontal" | `FRAME = "vertical"` (default) / `"horizontal"` |
| "igual ao edit modelo", "o melhor estilo" | `LOOK = "modelo"` and the drafter's defaults |

Anything not in that table (a kill counter, a sound pack, a 3D transition, text other than the lyrics) is not built: say so plainly
and name the closest option.

## Workflow

`PY=./venv311/Scripts/python`, in Git Bash, from the project folder `<clips folder>/_editor/`. Every Bash call starts in a fresh shell,
so begin each command with `cd "<project>" && export PY=./venv311/Scripts/python &&` (exported: `run.sh` and `deliver.sh` read `$PY`
from the environment, a plain assignment is not inherited). Setup, the script table and the timings are in
pipeline.md; the detail of each step (commands, what to read before moving on, the traps) is in **workflow.md**.

0. **Briefing** - unless a skip condition holds; then list the folder and decide the rest alone.
1. **Project** - copy `scripts/` (then `scripts/refstyle/` over it), `models/`, `games/`; `uv venv --python 3.11 venv311`; install
   `requirements.txt`; `$PY doctor.py` until `PRONTO` (every `FALTA:` fixed first, `AVISO` goes in the report); `clips.json`,
   `$PY ingest.py`, `$PY mkpts.py`.
2. **Reference** (when the folder holds one: always) - `$PY ref_analyze.py "$REF" --music src/music.flac`, then read `ref_notes.md`
   and every image in `ref_sheets/`. Its `adopt` block is what the drafter follows.
3. **Kills** - `$PY dupes.py`, then `$PY kills_auto.py <game>` (profiles in `games/`; another game: copy `generic.json`, tune the
   rectangles, check them with `--regions`), read the `autokill_NN.jpg` sheets, then `$PY kill_rank.py --seconds <length>` and read
   `kill_rank_*.jpg`. Then `$PY kverify.py` (3b) and `kverify.py --update` so every K is verified on the pictures: the drafters refuse
   an unverified K.
4. **Music** - `$PY music_tempo.py`, then `$PY music_grid.py BPM BEAT0` (never skip: it can refuse the BPM and prints BEAT0), then
   `$PY music_hits.py` (and `music_pulses.py`, `music_spec.py` to read the hits). Fill the music block of `timeline.py`.
5. **Timeline** - `$PY deathstrip.py ds.jpg ...` for each kill's `upto`; write `plan.json`; let the drafter write the draft
   (`draft_ref_timeline.py plan.json` or `draft_timeline.py plan.json`); read its explanation, compare with model-edit.md section 9,
   tune by hand. `$PY timeline.py` must pass, then `$PY music_pulses.py` (no FAIL).
6. **Preview** - `$PY preview.py ../<name>_previa.mp4` while the heavy work runs; tell the user where it is and that it is rough.
7. **Footage** - `$PY ranges.py && $PY prep.py ranges.json` (GPU, background), `$PY densify.py run 12 28`, reference style also
   `$PY posmap.py`, then `$PY check_store.py` (0 missing, 0 too coarse, no duplicates).
8. **Stills** - `$PY render.py N N+1 look.jpg` on every kill, transition, slow-motion frame, word and the first/last second; read them.
   Reference style: enlarged crops of your stills beside the same crops of the reference BEFORE the first full render.
9. **Sound** - `$PY audio.py` (each gunshot on its musical hit; `mix peak` below 1.0), read `audio_report.json`.
10. **Render** - in the background: `bash run.sh master.mp4` (12 to 16 min).
11. **Verify** - `$PY check.py master.mp4 --sheets` and `$PY syncaudit.py master.mp4`; read `sync_*.jpg`; compare the numbers with
    model-edit.md section 9. Fix and repeat (verification.md).
12. **Deliver** - `bash deliver.sh master.mp4 "../<name>_vN.mp4"`, never over an earlier version; it runs the gate first and refuses
    while an ERROR is left. Then `check.py` on the upload copy, and save what was learned in the project's `LEIAME.md` (never edit the
    installed skill during a video; that happens only when the user asks for it).

## When a check or the gate says no

| Symptom | What it means |
|---|---|
| `preflight.py` lists problems | fix `timeline.py`; it lists every problem at once, with the value it wanted |
| `music_pulses.py` FAIL | an event sits more than 8.3 ms off every measured attack: move it onto the attack's own time |
| `check_store.py` missing / too coarse / duplicates | `ranges.py && prep.py ranges.json && densify.py run 12 28`, then `repair.py` for duplicates |
| `check.py` `EARLY` / `LATE` / `not measurable` | the flash is not on the shot frame: never a pass; fix the anchors and render again |
| gate ERROR `fast-forward` / `no-ceiling` | the footage plays faster than the ceiling: fix the anchors, or `MAX_SPEED` only if the user asked |
| gate ERROR `no-gunshot` / `kill-frame` / `hidden` / `not-yours` | the kill or its sound is wrong: fix the kill, do not waive |
| gate WARN | it passes, but say so in the report; every item that could not be measured is a WARN, never a pass |
| a code the user accepted | `ACCEPT=<code> bash deliver.sh ...` only for a code that is not sync, and write it in `LEIAME.md` |

## Never promise, never offer

Say it in the first message, name what you deliver instead, and go on; never turn it into a question you cannot act on:

- an output other than 1080x1920 or 1920x1080 at 60 fps (no 4K, no "extra" upscale); a vertical edit never crops the gameplay to fill
  the screen (it sits whole in a window over a blurred backdrop) - say so when the reference fills the screen;
- lyric words or a cover in the house style (it has no text renderer): a user of it who wants them gets the default style instead;
- proven kill finding for any game but Valorant (say you check every kill on the review sheets).

## Reporting to the user

Reply in the user's language (typically Brazilian Portuguese, informal). Lead with the file path and its state, say what changed, give
the measured facts, and state plainly that you cannot watch or hear it, so feel, intensity and mix are theirs to judge. End by saying
they can describe in their own words anything to change. No questions after the briefing: decide, and never need a confirmation by not
deleting or overwriting anything of theirs. Answer a message that arrives mid-run in the next line you write.

## Files

| File | Read it when |
|---|---|
| briefing.md | writing the first message: the template in PT and EN, the questions, the skip rules |
| user-rules.md | before deciding anything the user has an opinion about: every rule **in their words**, both styles |
| workflow.md | running a step: the exact commands, what to read before moving on, the traps of each step |
| look-options.md | mapping a user's phrasing ("vinheta", "mais contraste", "cor fria") to a `LOOK` value |
| model-edit.md | before writing or tuning any timeline in the default style; after a render, its section 9 |
| reference-style.md | the DEFAULT style: drafting its timeline, copying a reference, vertical frame, lyric words, cover, raw recordings |
| edit-design.md | the house ("janela") style, only on request; its "Music" section serves both styles |
| verification.md | judging a render: thresholds, reading the sheets, the delivery gate and the sync audit, the report |
| feedback.md | the user commented on a delivered version ("travado", "kill fora do beat", "muito escuro", "tira essa kill") |
| pitfalls.md | something looks or measures wrong (symptom, cause, fix), including shell traps on Windows |
| pipeline.md | setup, the script table, timings, what to re-run after a change, jobs on the user's PC |
| tools-research.md | the user asks about other editors, MCPs or skills |
| scripts/, models/, scripts/games/, scripts/refstyle/ | the pipeline, the interpolation network, the kill profiles, the default style's own scripts (README.md inside) |
