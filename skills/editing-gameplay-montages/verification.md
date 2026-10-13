# Verifying an edit you cannot watch or hear

Two kinds of evidence: numbers, and pictures you read. A contact sheet read through the Read tool is
your eyes; a spectrogram is your ears. Sheets wider than about 2000 px are shrunk when you read them,
so keep tiles at 100 px or more with large labels (the scripts do).

## Before rendering video

| Check | Passes when |
|---|---|
| `$PY timeline.py` | prints every segment, no assertion, no "note:" you did not intend |
| `$PY music_pulses.py` | with `CUTS_ON = "bass"`: "transitions not on a kick / bass hit: none" (both styles); house style also "kills on a beat with neither kick nor snare: none" |
| `$PY ranges.py` | no ERROR (anchors inside the clips) |
| `$PY check_store.py` | `missing footage: 0` and no frame that copies its predecessor |
| `autokill_NN.jpg` from `kills_auto.py` (Valorant alternatives: the gallery from `kill_table.py`, `gal_NN.jpg` from `mykills.py`) | for every kill: it is the player's (own row in the feed), the flash is visible on tile K (`+0`) and absent on K-1, the ammo counter steps at K. HIDDEN in red = nothing to see at the aim (ability wall, smoke, flash): do not build a take on it. conf `guess` = K is feed-8, +-3 frames: read its tiles. `no_shot` = no bullet fired before the row (ability or knife kill). Wrong K: set it in the timeline entry (`strip.py` or `peek.py` every frame to find it) |
| `$PY kill_rank.py --check` (after the timeline is written) | no ERROR: `hidden`, `not-yours`, `duplicate` (the same source moment twice, also across a DVR and its trim), `wrong-shot` (K is not the shot that killed), `k-after-row` (K after the feed row: a follow-up shot). WARN `weak-shot` / `unverified`: look at the frames. Measured: on the worked example it names the kill hidden behind a wall and one death row taken for a kill; on another accepted edit, a spray's first shot and a follow-up shot used as K |
| `$PY deathstrip.py ds.jpg` (after the timeline is written) | every enemy's body is down on a green tile (a tile the edit shows), and no "WARNING: ... the death is cut short" line. A red tile before the fall: raise that kill's `upto` (or give the take more room) and draft again |
| the drafter's statistics block | close to the model edit (model-edit.md section 9): lead 14 frames on every take, deaths shown on every take, fastest frame at most 1.02x, kills per 10 s and gaps fitted to the song's tempo (model-edit.md section 3) |
| `$PY render.py N N+1 x.jpg` on a kill, a transition middle, a slow-motion frame, the first and last second | framing right, window and backdrop as intended, nothing black, torn or doubled |
| `$PY render.py A B x.jpg 2` across a transition | both clips visible mid-way, smooth smear, no stepped copies |
| `$PY audio.py` | house style: each kill line near 0 ms (see "Sound" below); `mix peak` up to 2.0 is fine, the files are written at half level. Default style: read the closing count of measured, clip-offset, edit-median and silent gunshots (reference-style.md, "Sound"); `mix peak` below 1.0 at the written level (`HEADROOM`; worked example 0.94 at 0.8, model edit 0.785 at 0.5), the script stops above it |

Frame number of a beat: `round((beat - R0) * FPB)`.

## After rendering: `$PY check.py master.mp4 --sheets`

| Output | Reference (the house example) | Meaning |
|---|---|---|
| frames identical to the previous one | 0 | any hit is a bug in frame access or the store |
| frames where the motion stops for one frame | 1, a real pause of the aim | every other hit is stutter the user will feel; a rejected earlier version had 20 |
| one-frame jumps not on a kill, accent, cut or transition | 1, a shot that did not kill | look at each with `peek.py`; a jump you cannot explain is a bug |
| overall judder index | 0.22 (an earlier version: 0.34) | evenness of motion; compare versions of the same edit, not different edits |
| sound | -8.5 LUFS, true peak -0.2, decoded peak -0.7 dBFS | a decoded peak at or above 0 clips (earlier versions were at +3.0 to +3.2) |
| `sync_N.jpg` | flash absent on `-1`; first seen on `+0` for 19 kills (faint on 3) and on `+1` for 3, as the printed table says | one row per kill, frames -3 to +4 |
| `pv_NN.jpg` | | the whole video at two frames per beat: order, framing, slow-motion bars, transitions, fades |

A beat rarely falls on the centre of a frame. `check.py` prints, per kill, the exact frame position and
where the flash must first show: on `+0` (only faintly when just a few percent of that frame's
exposure lies after the shot), or on `+1` when the shot comes after the exposure of `+0`. Later than
that tile means K or the beat is wrong (or, in a slow lead-in, that the time map reaches the kill below real
speed: the row "Bullet time into a kill" in the "Picture" table of pitfalls.md). A level 3 kill shows its impact frame on `+0`: an inverted
monochrome picture (nearly black for a bright scene, nearly white for a dark one). That is the effect,
not a fault; judge its flash on the next tiles.

Run it again on the upload copy: that is the file the user gets.

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
| crop of a still beside the same crop of the reference: `ffmpeg -ss T -i ref.mp4 -frames:v 1 -vf crop=1500:560:210:230 a.jpg`, the same crop of `render.py N N+1 still.jpg`, joined with `hstack` | letters as see-through and as large as in the reference; placement follows the user's rule (exact centre). Stills lack the encoder's `unsharp`, so do not judge crispness here |
| text centre: guide lines on a still, or `cue.ink` in `textfx.py` | ink centre 960 +/- 0.5 px, caps centred on y = 540, for every cue |
| `lyrics_align.py` table | every word within about 100 ms of its recognised time; overrides explained; unconfirmed lines absent |
| `posmap.py` | prints a measured position table per kind of grid, or says it uses the reference table for a kind the store does not contain; after `fixends.py` nearly every dense interval counts as fixed |
| `check.py` on the reference-style master | no stall at a whole source position inside slow motion |

Reference values (the worked example, 46 s): identical frames 2 (the black opening fade), stalls 1 (the frame before
an intro cut: false positive), unexplained jumps 2 (a real flick at real time, a muzzle flash in a replay),
judder index 0.27, -9.3 LUFS, decoded sample peak -0.4 dBFS, true peak 0.0 dBFS; flash table: 42 kills on
`+0`, 8 faint on `+0`, 12 on `+1`. Its master reads 1 unexplained jump and judder 0.264. The first render
of the same edit had 2 real stalls at whole source positions (RIFE dead zone).

## Sound

- Reference style: `audio.py` places each gunshot by construction and ends with a count (reference-style.md,
  "Sound"). The shots "placed with the clip offset" or "the edit median" are the ones to doubt; nothing measures them. Do not
  measure the finished stem: every shot fades in from silence 8 ms before its onset and neighbours overlap.
- House style: `audio.py` prints, per kill, where the loudest game-sound onset lands relative to the beat. Within
  a few ms of 0: the shot is on the beat. In the house example that held for 12 of 22 kills (within 7 ms). A value of +20 to +50 ms
  usually means a louder sound right after the shot (kill sound, the body of the gunshot) was picked,
  and slow-motion or voice-chat kills have no clean onset at all. Check those on the `kill_lags.py`
  strip instead of chasing the number.
- `$PY mix_spec.py r0 r1 ...`: a riser must end on its beat, the sweep must close and reopen where
  intended, whooshes must sit on transitions, the game stem must be silent in slow motion.
- `kill_lags.py` prints `K+2.75` (clear), `K~2.25` (found on a looser pass: look at the strip) or `K ?`.
  In the house example the looser pass agreed with the values read by eye for 4 of 5 game-sound kills within 0.05
  frame, and was meaningless on the clip with voice chat.
- Loudness has no pass mark. The house example's four deliveries measured -7.7 to -8.5 LUFS, the worked example's
  -9.3, short test edits -8.2 and -9.3; the user never commented on loudness, and what the platform does with it is unknown.
  The decoded peak is the hard limit: below 0 dBFS.

## The delivery gate (`gate.py`)

`$PY gate.py master.mp4` is the last check; `deliver.sh` calls it before it encodes and refuses while an ERROR is
left (each line says what and how to fix it).

- ERROR (refuse): timeline problems and fast-forward (preflight); file against timeline (size, 60 fps, frame
  count, duration, audio at 48 kHz); a master rendered from another `timeline.py` (`run.sh` stamps
  `timeline_sha1` into it); frozen frames; stalls and jumps the master does not reproduce from the footage; kill
  sync (the master must show the source frames the timeline asks for around each kill); decoded peak above
  -0.5 dBFS; `mix.wav` / `audio_report.json` made for another `timeline.py`; a kill without gunshot (default
  style); kills hidden, not the player's, duplicated or on the wrong shot (`kill_rank.py`); a lyric word not in
  `lyrics.txt`; no `MAX_SPEED` while frames play above 1.25x (`no-ceiling`: waive it only for a user who asked for
  velocity); a check that crashed (never waivable).
- WARN (print and pass): jumps that are in the footage, one frame of sync, loudness outside -14..-7 LUFS, gunshot
  offsets not measured, kills not verified.
- A problem the user chooses to accept is waived per code only: `ACCEPT=<code> bash deliver.sh ...`
  (`$PY gate.py --codes` lists them); it is written to `LEIAME.md` with the date. Say it in the report.
- `--json` prints the list; `--no-pixels` skips the decoding. 15 s to 2 min.
- Measured on a full-length default-style master, the worked example and the house example: no false ERROR; the worked example's decoded peak of -0.41 dBFS is an
  ERROR, as the rule says. Planted faults (fast hand edit, silent kill, truncated master, +5 dB, a duplicated
  frame, a timeline changed after `audio.py`) were each caught with their code.

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
