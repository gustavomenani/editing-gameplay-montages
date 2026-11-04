# Verifying an edit you cannot watch or hear

Two kinds of evidence: numbers, and pictures you read. A contact sheet read through the Read tool is
your eyes; a spectrogram is your ears. Sheets wider than about 2000 px are shrunk when you read them,
so keep tiles at 100 px or more with large labels (the scripts do).

## Before rendering video

| Check | Passes when |
|---|---|
| `$PY timeline.py` | prints every segment, no assertion, no "note:" you did not intend |
| `$PY music_grid.py` / `$PY music_hits.py` | the grid is not refused (a wrong BPM exits 1 and names the better one); the verdict says `constant grid` fits, or you place every event on the `hits.json` times; `$PY music_tempo.py` says `tempo steady?` |
| `$PY music_pulses.py` | the PLACEMENT CHECK ends without a FAIL: every kill (`T.HITS`), every bump, boom and, with `CUTS_ON = "bass"`, every cut (against a kick of strength 0.4 or more) is within 8.3 ms (half a frame) of a measured attack, printed in ms and frames; exit 1 otherwise. House style also "kills on a beat with neither kick nor snare: none" |
| `$PY ranges.py` | no ERROR (anchors inside the clips) |
| `$PY check_store.py` | `missing footage: 0` and no frame that copies its predecessor |
| `autokill_NN.jpg` from `kills_auto.py` (Valorant alternatives: the gallery from `kill_table.py`, `gal_NN.jpg` from `mykills.py`) | for every kill: it is the player's (own row in the feed), the flash is visible on tile K (`+0`) and absent on K-1, the ammo counter steps at K. HIDDEN in red = nothing to see at the aim (ability wall, smoke, flash): do not build a take on it. `how` `ammo` / `flash` = K was measured on the pictures; `ammo-loose` (several bullets) and `guess` (counter unreadable, feed - 7 frames) are unverified: read their tiles, run `kverify.py`. `no_shot` = no bullet fired before the row (ability or knife kill). Wrong K: set it in the timeline entry (`strip.py` or `peek.py` every frame to find it) |
| `$PY kverify.py` (any time after `kills.json`; `kverify.py timeline.py` once it exists) | every kill `verified`: the ammo step or the muzzle flash starts ON K and nothing on K-1. `CORRECT` names the sure K (use it); `SUSPECT` / `not measurable` (replay camera, weapon hidden): read the `kv_NN.jpg` row (tiles K-3..K+3: green = ammo step, yellow = flash, cyan = both). The gate repeats it (`kill-frame`). Moved by one frame, no K passed as verified in the test on 110 kills; it does not prove K is the killing shot of a spray |
| `$PY kill_rank.py --check` (after the timeline is written) | no ERROR: `hidden`, `not-yours`, `duplicate` (the same source moment twice, also across a DVR and its trim), `wrong-shot` (K is not the shot that killed), `k-after-row` (K after the feed row: a follow-up shot). WARN `weak-shot` / `unverified`: look at the frames. Measured: on the worked example it names the kill hidden behind a wall and one death row taken for a kill; on another accepted edit, a spray's first shot and a follow-up shot used as K |
| `$PY deathstrip.py ds.jpg` (after the timeline is written) | every enemy's body is down on a green tile (a tile the edit shows), and no "WARNING: ... the death is cut short" line. A red tile before the fall: raise that kill's `upto` (or give the take more room) and draft again |
| the drafter's statistics block | close to the model edit (model-edit.md section 9): lead 14 frames on every take, deaths shown on every take, fastest frame at most 1.02x in the default style (the house style squeezes its blur-ins to 1.6x and reaches 4.6x; a delivery with `MAX_SPEED = None` is judged by the user's request, not by this number), kills per 10 s and gaps fitted to the song's tempo (model-edit.md section 3) |
| `$PY render.py N N+1 x.jpg` on a kill, a transition middle, a slow-motion frame, the first and last second | framing right, window and backdrop as intended, nothing black, torn or doubled |
| `$PY render.py A B x.jpg 2` across a transition | both clips visible mid-way, smooth smear, no stepped copies |
| `$PY audio.py` | house style: each kill's gunshot measured to the sample and placed on its hit (it stops on a kill it cannot measure); `mix peak` up to 2.0 is fine, the files are written at half level. Default style: read the closing count of measured, donor, clip-offset, edit-median and silent gunshots (reference-style.md, "Sound"); `mix peak` below 1.0 at the written level (`HEADROOM`; worked example 0.94 at 0.8, model edit 0.785 at 0.5), the script stops above it |

Frame of a beat: `nearest_frame(beat)` = `floor((beat - R0) * FPB + 0.5)`; a cut is shown on `nearest_frame(m0) - CUT_LEAD`, a shot on `nearest_frame(hit) - HIT_LEAD`. Never `round`, `ceil` or a tolerance in beats.

## After rendering: `$PY check.py master.mp4 --sheets`

| Output | Reference (the house example) | Meaning |
|---|---|---|
| frames identical to the previous one | 0 | any hit is a bug in frame access or the store |
| frames where the motion stops for one frame | 1, a real pause of the aim | every other hit is stutter the user will feel; a rejected earlier version had 20 |
| one-frame jumps not on a kill, accent, cut or transition | 1, a shot that did not kill | look at each with `peek.py`; a jump you cannot explain is a bug |
| overall judder index | 0.22 (an earlier version: 0.34) | evenness of motion; compare versions of the same edit, not different edits |
| sound | -8.5 LUFS, true peak -0.2, decoded peak -0.7 dBFS | a decoded peak at or above 0 clips (earlier versions were at +3.0 to +3.2) |
| `sync_N.jpg` | the muzzle flash first shows on tile `+0` = the SHOT frame (`nearest_frame` of the shown beat) and is absent on `-1`; the printed table gives per kill `ok` (measured on the shot frame, absent on -1), `EARLY` / `LATE` (another frame), `spread` (also on -1) or `not measurable` (never a pass: a level-3 kill's impact frame, a flat picture) | one row per kill, frames -3 to +4 |
| `pv_NN.jpg` | | the whole video at two frames per beat: order, framing, slow-motion bars, transitions, fades |

`check.py` measures the flash itself (the difference image of the source frames K-1 to K matched against the master's
frame differences, `syncaudit.flash_score`) and prints per kill the frame it found against the shot frame. `EARLY` or
`LATE` means K or the hit is wrong (or, in a slow lead-in, that the time map reaches the kill below real speed: the
row "Bullet time into a kill" in the "Picture" table of pitfalls.md). A level 3 kill shows its impact frame on `+0`: an
inverted monochrome picture (nearly black for a bright scene, nearly white for a dark one). That is the effect, not a
fault, and not measurable by the flash: judge its flash on the next tiles. There is no `+1` case: the flash is whole
on the shot frame and absent on the one before, because those two frames are read at the exact source position.

Run it again on the upload copy: that is the file the user gets. `check.py` is not part of `deliver.sh` (a full decode of the copy takes
minutes, and the picture is the master's, re-encoded): `deliver.sh` runs `peakguard.py` and then `gate.py --sync-only` on the copy, which
is the audit that catches a re-encode that moved the picture or the sound. Run `$PY check.py out.mp4` by hand when the copy's sharpness
or smoothness is in doubt.

### A stalled frame: what is it?

`check.py` names the beat, the clip and the source frame. Two cases need no further look:

- **The beat is the last frame before a cut, or lies in the opening fade**: false positive (the neighbours
  are transition frames or black).
- **A whole source position (`source frame 7379.0`) inside slow motion below about 0.2x**: RIFE's dead zone
  in a store built without `rifeutil.Tween`. `$PY fixends.py` (GPU), in the reference style then
  `$PY posmap.py`, render again (the dead-zone row in the "Picture" table of pitfalls.md).

Otherwise `$PY cadence.py <clip> <frame-8> <frame+8> --detail`:

- **Every region drops to about 0 for one frame** between normally moving frames: the recorder
  duplicated a frame. `$PY repair.py clip:frame`, render again. (`prep.py` repairs these while building;
  `check_store.py` lists any left.)
- **The world slows over several frames, stops, starts again, while the weapon still moves a little**:
  the player paused the aim. Real footage; leave it. Say so if you report the number.
- **The source is fine**: the fault is in the pipeline. Is every frame read through `clipio`? Does
  `check_store.py` pass? Was the store built before an anchor change?

A duplicated source frame shown at real time does not produce a full stall (shutter integration
spreads it into a small unevenness), so do not rely on `check.py` alone: `check_store.py` is the gate.

## Reference style: extra checks

| Check | Passes when |
|---|---|
| crop of a still beside the same crop of the reference: `ffmpeg -ss T -i ref.mp4 -frames:v 1 -vf crop=1500:560:210:230 a.jpg`, the same crop of `render.py N N+1 still.jpg`, joined with `hstack` | letters as see-through as in the reference; size and placement follow the user's rule, not the reference (exact centre; caps 226 / 202 px at 1080p, widest word 70 % of the width). Stills lack the encoder's `unsharp`, so do not judge crispness here |
| `$PY text_test.py` and `$PY text_test.py vertical` (cap px, share of height and width, ink centre offset per style and for the widest word) | ink centre within 2 px of the frame centre (horizontal 960 / 540, vertical 540 / 960) for every cue; no word wider than 70 % of the width |
| `lyrics_sync.py` table + `lyrics/sync_*.jpg` + `lyrics_audit.py` | every red line on its syllable's left edge (flagged words: the zoom panel `lyrics/zoom_N.jpg`, red line on the left edge of the syllable's energy); no CHECK word left unexplained; the two models within 0.35 s on every word; the audit has no ERROR (every cue within 25 ms of a confident sung attack, or flagged); unconfirmed lines absent |
| `posmap.py` | prints a measured position table per kind of grid, or says it uses the reference table for a kind the store does not contain; after `fixends.py` nearly every dense interval counts as fixed |
| `check.py` on the reference-style master | no stall at a whole source position inside slow motion |

Reference values (the worked example, 46 s, rendered before SYNC 2): identical frames 2 (the black opening fade), stalls 1
(the frame before an intro cut: false positive), unexplained jumps 2 (a real flick at real time, a muzzle flash in a
replay), judder index 0.27, -9.3 LUFS, decoded sample peak -0.4 dBFS, true peak 0.0 dBFS. Its master reads 1 unexplained
jump and judder 0.264. The first render of the same edit had 2 real stalls at whole source positions (RIFE dead zone).

## Sound

- Reference style: `audio.py` places each gunshot on its own measured onset (state `measured`, or `donor` for
  `shot_from`) and ends with a count (reference-style.md, "Sound"). The shots "placed with the clip offset" or "the
  edit median" are the ones to doubt: they are printed in ms and the gate warns. The finished file is audited by
  `syncaudit.py` (below): the song is subtracted and the onset of the rest is compared with the hit, good to about 2 ms
  (do not read a shot off the stem by eye: it fades in before its onset and neighbours overlap).
- House style: `audio.py` measures every kill's gunshot onset (`kill_lags.measure`, to the sample) and corrects it for
  the offset between the flash frame and the hit; it prints per kill `onset_ms` read on the finished stem (within a few
  ms of 0 = on the hit; scratch tests within 0.14 ms) and refuses a kill it cannot measure. Slow-motion or voice-chat
  kills have no clean onset at all: check those on the `kill_lags.py` strip instead of chasing a number.
- `$PY mix_spec.py r0 r1 ...`: a riser must end on its beat, the sweep must close and reopen where
  intended, whooshes must sit on transitions, the game stem must be silent in slow motion.
- `kill_lags.py` prints `K+2.75` (clear, to the sample), `K~2.25` (found on a looser pass: look at the strip; `audio.py`
  refuses it unless the timeline types the lag) or `K ?`. A looser-pass value is meaningless on a clip with voice chat.
- Loudness has no pass mark. The house example's four deliveries measured -7.7 to -8.5 LUFS, the worked example's
  -9.3, short test edits -8.2 and -9.3; the user never commented on loudness, and what the platform does with it is unknown.
  The decoded peak is the hard limit: below 0 dBFS.

## The delivery gate (`gate.py`)

`$PY gate.py master.mp4` is the last check; `deliver.sh` calls it before it encodes and refuses while an ERROR is
left (each line says what and how to fix it).

- ERROR (refuse): an old timeline (no `SYNC = 2`, `timeline-old`); timeline problems and fast-forward (preflight);
  file against timeline (size, 60 fps, frame count, duration, audio at 48 kHz, audio as long as the picture); a
  master rendered from another `timeline.py` (`run.sh` stamps `timeline_sha1` into it); the picture or the sound
  starting late (`pts-gap`: the first video packet at pts 0 and both tracks starting together, within a frame: an
  `-itsoffset`, an `elst` / edit list or a mux offset leaves a file that is otherwise perfect); frozen frames;
  stalls and jumps the master does not reproduce from the footage; kill sync (the master must show the source
  frames the timeline asks for around each kill: the 6 frames before the shot when the take started 12 frames or
  more earlier, as every drafted take does, so no punch, burst or inverted frame disturbs the measure; after the
  shot for a take cut a few frames before it); decoded peak above 0 dBFS (`peakguard.py` keeps the delivered copy below -0.5); `mix.wav` / `audio_report.json` made
  for another `timeline.py`; a kill without gunshot (default style); kills hidden, not the player's, duplicated, on
  the wrong shot or 2-12 frames after their feed row (`kill_rank.py`); a K that `kverify.py` corrects or suspects
  (`kill-frame`); a lyric word not in `lyrics.txt`; the sync audit's errors (next section); no `MAX_SPEED` while
  frames play above 1.25x (`no-ceiling`: waive it only for a user who asked for velocity); a check that crashed
  (never waivable).
- A stall or jump is the gameplay WARN only when the master's OWN frame is the source frame the timeline asks for
  (a mean over the 5 frames around it let correct neighbours hide one bad frame, and a stutter passed as gameplay)
  and, for a stall (an output frame that repeats the one before it), only when the timeline's own map repeats the
  source position there (`p(n) == p(n-1)`: the footage is frozen). A real pause of the aim that the map moves past (two
  identical pictures from two different source frames) is therefore refused; `cadence.py` (the fix line) says whether
  the source really paused, and `ACCEPT=stall` waives it. The reference style's inverted level-3 impact frame is an
  accent, not a wrong frame: it stays a WARN.
- WARN (print and pass): jumps that are in the footage, one frame of sync, loudness outside -14..-7 LUFS, gunshot
  placed with an offset that was not measured, kills not verified (`kill-frame-unmeasured`, and `kills-unverified`
  when `kverify.py` or `kill_rank.py` is missing from the project). EVERYTHING the audit could not measure is a WARN
  that lists the events, never a pass: `gunshot-unmeasured`, `bump-unmeasured`, `fx-unmeasured`, `flash-unmeasured`,
  `cut-unmeasured`, `word-unverified` (cue starts not verified against the singing), `grid-unmeasured`,
  `sync-unmeasured` (the kill sync could not be measured for those kills: `check.py` returns every kill, an
  unreadable one with `measurable: false`, so none can disappear from the list), and `kill-audio-double` (the placed
  gunshot is on its hit but a louder attack follows it: listen).
- A problem the user chooses to accept is waived per code only: `ACCEPT=<code> bash deliver.sh ...`
  (`$PY gate.py --codes` lists them); it is written to `LEIAME.md` with the date. Say it in the report. NEVER
  waivable (an ERROR stays, `--accept` refuses the code): `av-offset`, `av-drift`, `frame-count`, `cut-frame`,
  `pts-gap`, `timeline-old`, `check-failed`. The gate runs `kverify.py` with the game's profile: `GAME` in
  timeline.py, the one `"game"` of the `kills.json` entries (`kills_auto.py` writes it), `$KVERIFY_GAME`, else
  `valorant` (never a `"game"` key in clips.json: `ingest.py` reads every key there as a clip).
- `--json` prints the list; `--no-pixels` skips every check that decodes pictures (the picture checks, the kill sync and `kverify.py`:
  the timeline, file, sound against the song, audio report, kills and lyrics checks still run, and the picture events that could not be
  measured are WARNed, never dropped); `--table` also prints the sync audit's table; `--deep`
  renders about 10 frames again and compares them with the file (1-2 minutes more). 15 s to 2 min.
- `$PY gate.py --sync-only FILE` runs ONLY the sync audit, on one file: `deliver.sh` runs it on the UPLOAD COPY after
  `peakguard.py`, the file that leaves (it needs `timeline.py`, `src/`, the song and, for the sound checks,
  `audio_report.json`). Exit 0 = no ERROR; 1 = an ERROR (the copy is renamed `*.rejected.mp4`); 2 = a bad call (a code that does
  not exist, or a missing FILE). A `peakguard.py` failure renames the copy the same way, so nothing unverified is ever left under
  the upload name.
- `deliver.sh` refuses a master older than `timeline.py` before it encodes (one line, no ffmpeg run): the copy is audited against
  the current timeline, so it would be rejected after the whole encode. The gate keeps it a WARN (`master-older`: an mtime alone
  does not prove the picture changed); the deliverer, whose copy is measured anyway, treats it as the refusal it becomes.
- Earlier measurement (before SYNC 2, on the worked example and the house example): no false ERROR; planted faults
  (fast hand edit, silent kill, truncated master, +5 dB, a duplicated frame, a timeline changed after `audio.py`) were
  each caught with their code. A kill-sync measure taken AFTER the shot gave a false ERROR on a vertical model-style
  master (score 0.57, best offset +4 under the punch, shake and burst); taken BEFORE it every kill matches at offset 0.

## Sync audit (`syncaudit.py`, also run by the gate)

Everything is read from the OUTPUT (decoded frames, decoded audio, the container's timestamps) and compared with what
`timeline.py` says and with the REAL song, never with the render's or the mixer's own bookkeeping. `$PY syncaudit.py
master.mp4` prints the table (per event: expected frame / measured frame / ms) and the findings, about 1 minute for 45
s; `--deep` adds S10; `--legacy` diagnoses a master of the old pipeline (diagnosis only: the gate refuses an old
timeline). An event that cannot be measured is LISTED as such, never counted as a pass.

| Stage | What it measures | Code and severity |
|---|---|---|
| S1 container | video pts on the 1/60 s lattice, frame count = `N_FRAMES`; the START of the tracks: first video pts at 0, both tracks starting within a frame | `pts-gap` (WARN under 1 ms of drift, ERROR above; ERROR when the picture starts late or the sound does not start with it), `frame-count` |
| S2 audio vs song | the decoded audio (file clock) against the song at `MUSIC_T0`: band-passed cross-correlation, the lag in samples, then 2 s windows (min, max, slope) | `av-offset` (ERROR above 1 ms, WARN above 0.25), `av-drift` (the lag moves by more than 1 ms), `audio-unmatched` |
| S3 gunshots | for a kill `audio_report.json` says was placed on its measured onset (`measured`), the clip's OWN 60 ms excerpt is matched-filtered against the master's song-free residual (the song, shifted by the S2 lag with its gain fitted, is subtracted) within +-20 ms of the hit; for others the loudest attack of the residual is compared with the hit | `kill-audio`: a placed shot more than 1 ms from its hit, or missing from the mix (match below 0.3): ERROR; house `heard` shots by the attack detector: WARN from 2 ms, ERROR above 4 ms; any other state WARN above 8.3 ms; `kill-audio-double` (WARN: a louder attack more than 15 ms after the placed one); `gunshot-unmeasured` (WARN) |
| S4 accents | the frame of the exposure pop and of the burst (the first frame with a real share of the window's largest RGB split) of each kill, and of each bump. A level-3 kill shows the INVERTED frame on the shot frame (that is its impact; no split can be seen on it) and the burst shows from the NEXT frame. A kill on a cut / blur-in, and bumps inside `LUMA_IN` / `LUMA_FADE`, the opening fade, near a cut or inside a kill's accent window (nk-1..nk+6) are not measurable | `fx-frame`, `bump-frame` (must be on `nearest_frame(shown beat)`, bumps on `nearest_frame(b) - HIT_LEAD`); `fx-unmeasured`, `bump-unmeasured` (WARN) |
| S5 flash | the muzzle flash (the source's K-1 to K difference image, correlation of at least 0.45) searched on nk-2..nk+2: on the shot frame and absent on the frame before | `kill-flash` (ERROR), `flash-unmeasured` (WARN) |
| S7 cuts | each take's picture starts on `nearest_frame(r0)`: the clearest layout step within +-8 frames of it is the cut; the cut's musical moment is within half a frame of a lattice line or a measured attack; each kill's musical beat reads 0 ms (within 1 ms) against a measured attack | `cut-frame` (ERROR, non-waivable: a clear cut is on another frame; names the take: a dropped or repeated frame, a late take, a bad part join), `cut-unmeasured` (WARN: no clear step), `cut-grid` (WARN to 2 frames, ERROR beyond), `kill-hit` (WARN up to a frame, ERROR beyond) |
| S8 words | the first change of the word's pixels on `nearest_frame(a) - HIT_LEAD` (where the cue sits against the SUNG attack is `lyrics_audit.py`'s job, which the gate runs) | `word-frame`, `word-sung` |
| S9 grid | the phase of the song's strong hits against `BEAT0 + k * PER / 2` (or `PER / 4`) | `grid-phase` (hits agree and are more than 25 ms off), `grid-unmeasured` |
| S10 deep | `--deep` (it runs): part joins and some cuts rendered again and matched against the file's frames -2..+2 | `render-mismatch` |

## What no check tells you

How it feels in motion, whether the accents are too strong or too weak, the balance of music, shots
and effects, whether voice chat should stay. Say this in every report; the user's reaction is the only
measurement of taste.

Unverified: a vendor blog (ShortSync) says TikTok may convert 60 fps uploads to 30 fps unless "Allow
high-quality uploads" is on or the upload is made from a desktop browser. Not confirmed by an
official source. Mention it as unconfirmed, with the link, because it would undo the smoothness:
https://shortsync.app/resources/tiktok-upload-method-high-quality ,
https://www.shortsync.app/features/60fps-video-upload

## The report

In the user's language, informal, no questions (what to make was settled in the briefing). Shape that worked:

1. First sentence: the file path, length, size, and that it was checked by measurement but not watched.
2. The user's main complaint first: cause, fix, and the number before and after.
3. What changed, in a few bullets with plain words (no script names, no beat numbers).
4. What only they can judge, and anything left out or unconfirmed.
5. Where the project is kept and how much disk it uses.
