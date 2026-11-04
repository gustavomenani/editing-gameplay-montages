# The default style (reference style: "faz com a MESMA EDICAO desse vídeo", or no reference at all)

This is the DEFAULT style of the skill, with or without a reference video, vertical by default
(`FRAME = "vertical"`). Without a reference, the edit follows the model edit (model-edit.md: its patterns fitted
to the user's song, `LOOK = "modelo"`; `draft_ref_timeline.py` writes them) and the "Reading the reference" step is
skipped. With one, the reference ALWAYS drives the edit (the user: "o video sempre deve ser feito baseado na
referencia caso tenha, e sempre ir tambem no ritmo da musica"): `ref_analyze.py` measures it, the drafter follows its
`adopt` block (precedence per trait: the user's words > the reference > the model edit), and everything lands on the
music's measured hits and lattice lines (SYNC 2, "Timing" below). The model's take anatomy and the user's rules in
SKILL.md decide where the reference is not followed. The machinery is the shared pipeline: frames by index, measured
hits, pictures on exact frames, muzzle-flash frame on the hit, sub-frame store, shutter integration.

Worked example: `scripts/refstyle/timeline_ref_example.py` (a 130 BPM trap song, 46 s, 62 kills; the project
folder itself, with the footage, is not published). It is also the drafter's template; its own entries predate the
model edit (4-frame leads, `post()` slow motion, intro shots without kills).
Setup: pipeline.md, "Setup" (the standard scripts, then `scripts/refstyle/` over them, then
`[ -e timeline.py ] || cp timeline_ref_example.py timeline.py` - never overwrite a `timeline.py` that already holds an edit).
`scripts/refstyle/README.md` lists what in those scripts
belongs to the worked example only, and the standard tools this style does not use.

## Reading the reference (you cannot watch it)

In the project folder (scripts and refstyle files copied, `PY` = the venv):

1. `$PY ref_analyze.py "$REF" --music src/music.flac` (leave `--music` out until the song is chosen; give
   absolute paths). About 40 to 50 s per 33 s of video (the kill feed and the drum attacks run beside the picture
   work), longer while a game or a render runs; a reference whose decode makes ffmpeg print errors no longer hangs it. It writes `ref_notes.md`, `ref_notes.json` and `ref_sheets/` and
   prints the notes. It measures: layout (full frame, window over a backdrop, bars); every cut (the first frame of
   each change of picture, 2 frames apart at the least) and the LATTICE of 1, 1/2, 1/4 or 1/8 beat they sit on
   (circular statistics: the coarsest lattice whose concentration is within 15 % of the best finer one, with a
   plausible offset of at most 80 ms): its step in seconds, the offset in output frames, and the gaps between cuts in
   lattice steps, which is the reference's rhythm; the beat grid of the reference's own sound (or your song's own grid
   when the reference's sound IS your song: cross-correlated, `same_song.offset_s`); how many frames its cuts
   (`cut_lead_frames`) and the pops / muzzle flashes of its kills (`hit_lead_frames`, kill evidence only) come before
   the drum attack of their lattice line; its kills from the kill feed (Valorant, 1920x1080: rate, gaps in steps, lock
   to the lattice); the kind of each cut (hard, whip, zoom burst, roll, flash, dip) with a confidence; slow motion and
   freezes; big words (no OCR); colour, vignette, grain, fringe; shake and zoom around the cuts; the ending (luma fade,
   fade to black, cut: fade and black seconds apart). It ends with SUGGESTED SETTINGS and writes the `adopt` block of
   `ref_notes.json` (next section). With `--music` the clip lengths are counted in YOUR song's beats.
2. READ the images in `ref_sheets/`: the overview, the three every-frame sheets around cuts, `centre_crops.jpg`
   (judge the words' fill, colour and size there: on small tiles the reference's see-through letters looked solid,
   and that mistake shipped), `start_3s.jpg`, `end_3s.jpg`. The tool does not measure whether letters are see-through.
3. Read the Limits at the end of `ref_notes.md`. Validated on the worked example's reference: 73 of 74 cuts found on
   the same frame (the miss: a fade to black). On the house example only 5 of 13 transitions were found (whips
   through, spins and dissolves that move both clips are missed): for such edits the cut list is a lower bound. The
   LOOK guess (colour, vignette, shake, zoom) is rough: confirm it on the crops. A reference without sound: the tempo
   is fitted to the cut times and no offset or lead is read (`cut_lead_frames` and `hit_lead_frames` are null).
4. The worked example's reference (numbers for orientation): 158 BPM (79 in half time), its cuts on a 1/2-beat lattice
   (0.19 s) and about 2 frames ahead of it (31 ms by hand, median 2.4 frames over 82 cuts), clips of 0.5 / 1 / 2 beats
   at 158, about half of the cuts with a blur-in (whip, zoom burst, roll), words about 23 % of the frame height, slow
   motion about 0.13x, luma fade over 3 s, no hard cut for the first 7.2 s. Only 2 of its 24 kills have a pop, so its
   `hit_lead_frames` is null (not measurable) and the draft keeps 1.
5. Nothing is copied by hand: the drafter reads `ref_notes.json` (the `adopt` block, "What the draft takes from the
   reference" below). Put the notes into the project's `LEIAME.md`; the user's words (plan keys) outrank the reference.

By hand, when a number looks wrong: the cut list with
`"$FF" -v error -i "$REF" -vf "select='gt(scene,0.25)',metadata=print:file=cuts.txt" -an -f null -` (the file
name inside the filter must be relative), every frame of 0.8 s with
`"$FF" -v error -ss T -t 0.8 -i "$REF" -vf "fps=60,scale=240:-2,tile=8x6" -frames:v 1 every_T.jpg`, an enlarged crop
with `"$FF" -v error -ss T -i "$REF" -frames:v 1 -vf "crop=1500:560:210:230,scale=900:-2" crop.jpg`
(`FF=$("$PY" ff.py | tr -d '\r')`).

## The style and how it is built

| Element | In the reference | Built as |
|---|---|---|
| format | 1920x1080, 60 fps, full-frame gameplay with HUD | `W, H = 1920, 1080`; `clipio.CROP_X, CROP_W = 0, 1920`; no window, no backdrop. Anything else: "Another frame size or rate (not built)" below |
| zoom | none held; small pushes and punches | drafted: push-in 3 % over a take (5 % over a bullet time, 0 in the intro and on the calm final take), kill punch 2 / 3.2 / 4.5 % by level (`ACC`), the radial burst of `IMPACT` (6 frames, centre sharp). The worked example: push-in 3.5 % (10 % over its 7-beat bullet time, 8 % over one 4-beat take), punch 1.6 / 2.6 / 4.5 %. Both: a lean of 8.5 % on the last 2 frames before a cut and the 5-frame zoom burst of a `bzoom` blur-in. Nothing else enlarges the picture |
| clip anatomy | hard cut, 3-4 blurred frames, sharp near-frozen slow motion | the footage never plays faster than real time (`MAX_SPEED = 1.0` in the music block; the user: "do nada voce coloca o video muito rapido e fica estranho demais", "clips acelerados do nada"). Drafted takes (the model edit, model-edit.md section 4): `pre()` enters the take at real time `LEAD_FRAMES` (14) before the shot; K on the beat; `fall()` (entry option `upto`): real time for 8 frames, then one constant slow rate that reaches `K + upto` (the body down) exactly at the next cut; a window that would need less than 0.15x slows to 0.15x until the body is down, then eases back to real time. `M` takes: the later kill lands on a hit at least its real-time distance after the first (slower is fine, down to 0.6x), else two takes; `fall()` after the last kill. Bullet time eases up to real time over 8 frames. Hand-written takes without `upto` use `post()`: real time 0.3 beat, an 8-frame ease down to 0.12-0.16x for at most 1.6 beats, an ease back to real time. The worked example (`MAX_SPEED = None`, `CUT = 0.15`) squeezed 16 source frames into the blur-in (5.8x) and sped up after the slow motion: only on a request for velocity (`"max_speed": 1.6` or `null` in plan.json) |
| cut position | just before the hit | drafted: the cut's musical moment sits on a line of the song's lattice (the reference's step first, else the coarsest of 1/2, 1/4, 1/8 beat that fits, 1/16 as a last resort), on the measured attack there when there is one, chosen so that the SHOWN lead (whole frames from the cut's frame to the take's first shot's frame) is `LEAD_FRAMES` (14, 12 to 16 at any tempo), so the enemy is seen before he dies. Which beats: `CUTS_ON` (the user's choice in the briefing). `"kills"` (default, the model edit): a cut before each take's first kill. `"bass"` (an editor's note: "as transições rolarem nos graves da música, não no snare"): the cut lands on the attack of a kick / 808 and the take's first kill on the first hit at least `LEAD_FRAMES` after it; snare and hat kills go inside takes (`M` entries). The worked example cut 0.15 beat (4 frames) before each kill (19 of its 57 cuts land on a kick, measured): a kill that soon after a cut "nem aparece" |
| blur-in | horizontal whip with thin streaks, zoom burst with rays, rotated whip, red/cyan split | `blur_in()` and `streaks()` in render.py: post effects on the finished frame, strength `(1 - q/5)^2` |
| pacing | 16th-note runs, 8th and quarter-note clips | drafted (`"kills"`): one kill per take about every second on measured hits, never closer than `(LEAD_FRAMES + upto) / FPB` beats between takes (about 0.6 s; closer kills of one clip share a take); the drop kill in bullet time; `"bullet": "hit"` kills get a short bullet time where the drums thin out (model-edit.md, sections 2 and 3). `"bass"`: the kicks set the clip lengths, so sparse 808s give takes of 2 beats or more with the snare and hat kills inside them. The worked example: sparse 808s: 2-beat clips; hats on every half beat: 1-beat clips with a few half-beat runs |
| lyric words | Impact caps, about 23 % of the frame height, letters pop in random order, see-through tinted fill, red in the intro | the user's size, not the reference's: caps 21 % (red intro) / 19 % of the frame height, the widest word at 70 % of the frame width, on the exact centre; letters pop in random order, see-through tinted fill, red in the intro, the word steps back while a kill plays. `textfx.py` (needs Impact, or `IMPACT_FONT` = a .ttf path; `render.py` imports it, so without the font nothing renders; `STYLE_OVERRIDES` in timeline.py changes a style); see "Lyric words" |
| look | sharp, saturated, colour fringes at the edges | per-channel zoom `CA0 = 0.0011`, saturation 1.20, S-curve, `unsharp 0.55` at encode |
| edit options | the worked example's values, adjustable per request | `LOOK` in timeline.py (SKILL.md, "Edit options"; `scripts/look.py`), read in both frames. `"modelo"` (the drafter's default) is the model edit's look: exposure 1.10, saturation and vignette up, a faint wide glow (measured on 19 frames against that edit: luma +3.5 %, saturation -0.5 %, corner/centre -0.4 %). Differences from the house style: no visible grain by default (`grain` above 1 adds a fine film grain, at or below 1 changes nothing); `kill_zoom` scales the kill punch, the 2-frame lean into a cut, the `IMPACT` radial burst and the bump nudge, never the take's slow push-in; `fringe` scales the colour split, `flash` the exposure pop and the bump light; `impact` False removes the inverted frame of level-3 kills; `bars` (2.39:1, horizontal only, drawn last so no blur-in moves them; they hide the kill feed and the ammo, and never reach cover plates); `blur_in` scales the whip / zoom burst / roll (0 = a plain hard cut). Absent or `"padrao"`, and no `IMPACT` / `ACC` / `BUMPS` / `LUMA_IN` / `white` in the timeline: the worked example's own look (its accents now start and peak on the shot frame, SYNC 2) |
| intro | slow cinematic shots without HUD | drafted: `intro.kills`, bullet-time kills at FULL FRAME over the song's break (0.12 to 0.25x lead-ins, `shutter=2.2`, `push=0`, `intro=True`, gunshots heard), the opening reveals the bright areas first (`LUMA_IN`), the last 4 beats a bullet time with a white flash-in into the drop kill: no take without a kill ("tem um clip do phoenix que nao mata ninguem"). The worked example used ability shots without kills (`intro.shots`, `mute=True`, red words), still accepted. Never a crop to hide the HUD |
| ending | long slow-motion hold, luma fade (dark areas black first) | `T.LUMA_FADE`; the last take is `calm=True` (no zoom or shake on the ace). Drafted: the last kill (pin it with `at` on the last sung word) in slow motion down to about 0.1x, the music fading under it (`FADE_OUT`), a 0.27 s luma fade and 1.35 s of black |
| kill accents | punches, flashes, colour split, light rays | drafted (model-edit.md section 5): `IMPACT` = radial burst +3.5 / 6 / 9 % decaying over 6 frames (centre sharp; none on a calm take), RGB split 5 / 9 / 14 px, light rays on levels 2-3, one inverted monochrome frame on the shot of a level-3 kill; `ACC` = punch 2 / 3.2 / 4.5 %, shake 4 / 7 / 10 px, exposure pop by level; `BUMPS` = a light pulse and a 1.2 % nudge on strong hits without a kill; segment `white` = a white flash-in (`flash(b)`) at the start of a bullet time |
| timing | the reference's cuts come 1.3 to 1.9 frames and its kill flashes 1 frame before the drum attack (measured) | SYNC 2 ("Timing" below): a cut is shown `CUT_LEAD` frames, a shot, bump, white flash-in and word `HIT_LEAD` frames before its musical moment, the sound on the exact beat. Every accent of one shot (punch, shake, exposure pop, fringe, `IMPACT` burst and split, rays, the inverted frame) starts AND peaks on the shot frame (instant attack, then the same decay); K is whole on that frame and absent on the frame before it (those two frames are read at the exact source position, no shutter blend); a bump's pop and nudge start on `nearest_frame(b) - HIT_LEAD` |
| watermark | the editor's tag | never copied, and nothing is put in its place |

Timeline entries (`E` in the example). The last element is always an options dict, `{}` when empty:
`("shot", start, clip, a, b, {})` no kill; `("K", beat, clip, K, {})` one kill; `("M", [(beat, K), ...],
clip, {})` kills of one continuous take; `("L", start, lead_anchors, beat, clip, K, {})` custom lead-in.
Each take ends where the next starts. Options:

| Option | Meaning |
|---|---|
| `lv`, `lvs` | kill level (default 1); for an `M` entry `lv` is the level of the last kill (the others 1), or `lvs=(2, 2)` gives one per kill |
| `upto`, `h` | after the take's last shot, `fall()` instead of `post()`: real time for `h` frames (default 8), then one slow rate that reaches `K + upto` (the frame the body is down, from `deathstrip.py`) exactly at the cut. The take must last at least `upto` frames after the shot (an assertion says so) |
| `lb` | `K` / `M` entries: beats from the cut's musical moment to the first hit (default `CUT`, which a draft writes as `LEAD_FRAMES / F`) |
| `white`, `shot_from` | `white=flash(b)`: a white flash-in on the cut of musical beat b, starting on that cut's frame (0.36, clearing over 8 frames; more reads as a white blot); `shot_from=(clip, K)`: use another kill's clean gunshot for this take |
| `n`, `rate`, `slow` | `n`: source frames squeezed into the 4 blur-in frames (only with `MAX_SPEED = None`; with a ceiling leave it out); `rate`: slow-motion speed of `post()` (default 0.16); `slow`: beats of slow motion after the shot (default 1.6; `None` = to the end of the take). An anchor may carry a third number, `(beat, frame, speed)`, which pins the speed there |
| `end` | beat where the take ends; default the start of the next entry (`R1` for the last). Only the last entry may differ from it: an assertion stops any other |
| `post` | list of anchors `[(beat, source frame), ...]` that replaces what `post()` would add after the kill (`K`, `M`: after the last kill's anchor; `L`: after the kill's anchor). Musical beats: they keep their distance to the shot, and the one at the take's end lands on the next cut. Beats increase; the take lasts to the last anchor's beat, so end the list on the take's end. The example uses none |
| `tin` | how the take comes in: `("fade", 0)`, `("cut", 0)`, `("bwhip", 0, +1\|-1)`, `("bzoom", 0)`, `("broll", 0, +1\|-1)`. Default: the list `_FX` in the timeline, cycled by entry number (entry i gets `_FX[i % 8]`: bwhip +1, bzoom, bwhip -1, broll +1, bwhip +1, bzoom, bwhip -1, broll -1). Set `tin` on an intro take (`fade`) and wherever the cycle is wrong |
| `push`, `shutter`, `intro`, `mute`, `calm` | take options, documented at `S()` in the example |

### Timing (SYNC 2)

The entry list `E` holds MUSICAL beats: kill beats are measured hits (`hit(t)` of a `hits.json` time), `lb` runs from the
cut's musical moment to the first hit. The loop after `SEGS` in `timeline_ref_example.py` turns them into pictures:

| Name | Meaning |
|---|---|
| `SYNC = 2` | the contract; every script that reads timeline.py refuses one without it, with the update message |
| `hit(t)` | `(t - BEAT0) / PER - M0`: the timeline beat of song time t; write a hand-placed kill as `hit(t)` of its `hits.json` time, never of a grid beat |
| `frame_beat(n)`, `nearest_frame(r)` | the beat output frame n shows (`R0 + n / FPB` = song time `MUSIC_T0 + n / 60`) and the output frame nearest to beat r |
| `vis(r, lead)` | the beat of the frame that SHOWS moment r: `frame_beat(nearest_frame(r) - lead)` |
| `CUT_LEAD`, `HIT_LEAD` | whole frames in the `draft:cut` block (default 1 and 1; 0 to 3; the reference's measured values when it has them, plan keys `cut_lead_frames` / `hit_lead_frames` otherwise): cuts are shown `CUT_LEAD`, shots, bumps, white flash-ins and words `HIT_LEAD` frames before their musical moment |
| `s["m0"]`, `s["r0"]` | a take's musical cut beat, and the beat of the frame its picture starts on (`vis(m0, CUT_LEAD)`) |
| `s["hits"]`, `s["kills"]` | the musical beat of each kill (its gunshot, thump and boom sound there) and `(shown beat, level)`, an exact frame (the time map's K anchor sits on the shown beat); module lists `HITS` and `KILLS` |
| `take_of(n)`, `active(r)` | the take on output frame n, by frame index (no float compare); `active(r)` = `take_of(nearest_frame(r))` |
| still musical | `TEXT` word starts, `BUMPS`, `BOOMS`, `RISERS`, `FADE_OUT`: the consumers apply `vis` themselves. `LUMA_IN` / `LUMA_FADE` are picture ramps evaluated per frame |

Why a lead: a picture a frame ahead of its sound reads as in sync, behind it as late (measured on the user's
reference). `python timeline.py` asserts that every cut and shot is on an exact frame and every take has a frame of
its own. No `ceil`, no tolerance in beats anywhere: a cut is on `nearest_frame(m0) - CUT_LEAD` exactly.


### Drafting the entry list (`draft_ref_timeline.py`)

Write `plan.json` (the kills in play order with their `upto`, the song numbers, the briefing's choices) and let
`$PY draft_ref_timeline.py plan.json` write `timeline.py`: it fills the blocks between the `# >>> draft:...` markers of
`timeline_ref_example.py` (music block, `LEAD_FRAMES` / `CUT` / `PUSH`, the model edit's sound and accents in
`draft:fx`, entry list `E`, intro words, `RISERS`). Then read the explanation it prints (also in the comment above
each entry) and the statistics block, compare them with model-edit.md section 9, look at stills, and tweak by hand.

```json
{"bpm": 130, "beat0": 0.4608, "drop_beat": 63, "cuts_on": "kills", "frame": "vertical", "length": 30,
 "intro": {"beats": 12, "kills": [{"clip": "c02", "K": 640, "upto": 24}, {"clip": "c05", "K": 2210, "upto": 23}]},
 "ref_notes": "ref_notes.json",
 "kills": [{"clip": "c09", "K": 7385, "upto": 22, "bullet": true}, {"clip": "c04", "K": 862, "upto": 24},
           {"id": 81, "upto": 21}, {"id": 82, "upto": 26, "with_previous": true},
           {"clip": "c07", "K": 4185, "upto": 26, "bullet": "hit"}, {"clip": "c01", "K": 6198, "upto": 25, "at": 42}]}
```

`drop_beat` and `start_beat` are TRACK beats (`music_tempo.py`): the first kill after the intro lands on `start_beat`
(absent = the drop). The kill with `"bullet": true` (one) lands exactly on the drop after a 3 to 6 beat bullet-time
lead-in with a white flash-in, a riser and a boom (an `L` entry); `"bullet": "hit"` (any number) gives a kill a 2 to 3
beat lead-in with the same flash, riser and boom. Without one in the plan the drafter finds where the drums thin out
by itself (`"auto_bullet"`, default true): in the body, 1.5 beats or more where the loudest of kick, snare and hat
stays under 35 % of the section's typical hit and at most half its average, after 2 louder beats, followed within
2 beats by a strong hit; the most pronounced one (at most one per 30 s) gets the "hit" bullet on the kill the draft
puts nearest after it, and the take's comment and a note say why. If it cannot fit, the draft stays without it and
the note gives the numbers; never in the last two bars before the last kill (they belong to the ending: the ace kill
by kill); `"auto_bullet": false` turns it off. The last
kill ends the video (calm take, slow motion, `LUMA_FADE`, 1.35 s of black). `intro.kills`: bullet-time kills over
the intro (`intro.shots`, slow ability shots without a kill, are still accepted but break "no take without a kill").
`with_previous` joins a kill to the take before it (same clip, later K: an `M` entry); kills of one clip closer than
a lead plus a death join by themselves. `at` pins a kill to a timeline beat (a multiple of 0.25): the last kill on
the beat of the last sung word, a kill the user wants on a given hit; it lands on the measured attack there, and where the music has no hit it sounds on the pinned beat and the draft says so.
`lead_frames` (10 to 20, default 14), `look` (default `"modelo"`), `max_speed` (default 1.0), `auto_bullet` (default true).
SYNC 2 keys: `cut_lead_frames` / `hit_lead_frames` (0 to 3: frames a cut / a shot is SHOWN before its musical moment;
absent: the reference's, else 1 and 1), `hit_grid` (2 = kills on half beats, 4 = quarter beats; absent: 4 when 20 % or
more of the song's strong kicks and snares sit on a quarter that is not a half beat, else 2), `"ref_notes": false`
(ignore the reference), per kill `"k_checked": true` ("K" below), per intro kill `"silent": true` (needs `at`: pins a
kill where the intro has no drum). `at` takes quarter beats (the drop kill takes the nearest attack within 50 ms).
`ref_notes.json` (`ref_analyze.py`): its `adopt` block drives the draft ("What the draft takes from the reference").

Rules it applies: every kill, bump, boom, riser end and bullet kill sits on a measured attack (`beat_hits.measure_t`, 9
decimals; intro kills need a hit too). Every take's cut is SHOWN `lead_frames` (12 to 16 whole frames, checked on the
finished module's own frames) before its first shot and runs at real time to it; kills-mode cuts sit on a lattice line
(the reference's step, then 1/2, 1/4, 1/8, then 1/16) at the measured attack there when there is one; `"bass"`: the cut
on the attack of the kick nearest before the lead window and the first kill on the first hit at least `lead_frames`
later; "hit" and auto bullet times start on a 1/4-beat line; R0, R1, `LUMA_FADE` and `FADE_OUT` on beat lines, R0 so
that the first cut is shown on frame 0. After a
take's last shot `fall()` with that kill's `upto`; the next cut never comes before the death is shown, which sets the
shortest gap between two takes' kills to `(lead_frames + upto) / FPB` beats. Kills on measured kicks, snares or loud
hats; speed between two kills of one take 0.6 to 1.0x, so the later kill needs a hit at or after its real-time
distance, and when none exists the kills become two takes with a note, never a fast-forward. Nothing plays faster
than real time (plan key `"max_speed"`; 1.6 or `null` only when the user asks for velocity): speeds are pinned at the
anchors, and `preflight.py` lists any run above `MAX_SPEED` x 1.02 as an ERROR. Levels (3: the drop kill, the
strongest snare of the body, the last kill; 2: the first kills after the drop, the strongest backbeat snares, `"hit"`
bullets, at most a quarter of the takes in all),
blur-ins by level (zoom burst on level 2/3 and bullet takes, whips alternating direction, a roll about every fourth
take), push-in 3 % (5 % over a bullet time, none in the intro and on the calm ending), `IMPACT` / `ACC`, `BUMPS` (the
strong hits without a kill within 0.3 beat, about one per 2.4 s), `BOOMS`, `KILL_THUMP`, `WHOOSH_BLUR`,
`GAME_LEVEL`, `HEADROOM = 0.5`, `FADE_IN`, `RISERS` into the drop and each `"hit"` bullet, `LOOK = "modelo"`.
It refuses with the numbers when the plan cannot fit (no hit on the first kill or the drop, kills too close for a
lead and a death, too few kicks for the takes in `"bass"`, a take longer than 7 beats, too little footage, a length
the kills cannot fill: it says how many seconds they can make). Kills without `upto` get 24 frames and a note:
measure them (`deathstrip.py`), a wrong value cuts a death short or holds a corpse. It never overwrites a
`timeline.py` you edited (`--force` does); `--compare other_timeline.py` prints the same statistics for another
timeline. Lyric cues come from `lyrics_sync.py` ("Lyric words").

K must be verified (both drafters, `preflight.k_check`): a kill whose K is not is REFUSED, naming the id, `how` / `conf`
and `kverify.py` (a K a frame off is 16.7 ms of desync). Unverified = no `kills.json` in the folder, no entry for that
clip and K, a plan K that differs from the entry's (by `id`, or by clip and K, also the K that `kverify.py` corrected),
`how` other than `ammo` / `flash` (`ammo-loose`, `guess`, or an old entry with no `how`), or `conf` low / guess. Read
the `kv_NN.jpg` sheets, then write `"k_checked":
true` on the plan entry, or let `kverify.py --update` correct `kills.json`. It also refuses when the strong attacks
drift against the grid (the BPM is wrong), naming the better BPM and the drift per beat.

Measured with the SYNC 2 drafter on synthetic songs with sample-exact truth (85, 95.7, 124, 130, 145 and 170 BPM, with
and without an intro): every kill, bump, boom and riser end within 2.0 ms of the true hit (the kick bias; one 0.5 ms),
kills-mode cuts within 0.6 ms of their lattice line or attack, every shown lead 12..16 frames, frames exact. At 95.7 BPM no 1/8 line
fits the window: that is what the 1/16 fallback is for. Bass mode drafts at 124, 130 and 145 BPM with every cut on a
kick; at 85, 95.7 and 170 it refuses with a real reason (the plan too dense for the kick spacing, or no kick in the lead
window). With a reference, the `adopt` block changed the draft of a real plan (CUT_LEAD, the share of hard cuts, the
real-time hold `h`, `LOOK`); the cut beats stayed where the physical minimum (lead + death) forced them. The drafter
needs the measure of `beat_hits.py` (kick = the onset of 30..140 Hz, snare = body and crack arriving together): with the
old energy measure the band's bass guitar read as a kick on almost every half beat and the snare showed only in the high
band (1 of 12 backbeat snares found, now 12 of 12; false kicks 13 instead of 30). The plan order is kept (it never
reorders or drops a kill: the refusal says which take to change).

### What the draft takes from the reference

`ref_notes.json["adopt"]` (version 2, written by `ref_analyze.py`; a trait it could not measure is null, never a guess).
Precedence per trait: the plan's keys (the user's words) > the reference > the model edit. For every trait the draft
prints `reference followed` or `not followed (why)`, and it REFUSES to write the file when `ref_notes.json` exists and
none of its traits was used (a reference that changes nothing is not followed).

| `adopt` key | What the draft does with it |
|---|---|
| `frame`, `look`, `look_preset` | `FRAME`, `LOOK` |
| `cuts_on` (suggested) | `CUTS_ON` |
| `lattice` (`step_s`, `offset_frames`) | the step of the lattice lines kills-mode cuts sit on, tried first (then 1/2, 1/4, 1/8, 1/16) |
| `cut_lead_frames`, `hit_lead_frames` | `CUT_LEAD`, `HIT_LEAD` (0 to 3). `hit_lead_frames` is null when fewer than 6 kill accents have an attack or the leads scatter: the draft keeps 1 and prints `hit_lead_note` |
| `cut_gaps_steps` | each take's preferred length, drawn from the reference's histogram of gaps in lattice steps and raised to the physical minimum (lead + death); every raise is printed |
| `transitions` | the shares of hard cuts / whips / zoom bursts / rolls. The `flash` and `dip` shares are not drafted: the draft says so and spreads them over the four |
| `slow` (`share`, `rate`) | the real-time hold `h` and the floor of `fall()` |
| `intro_steps` | the intro's length in whole bars |
| `ending` (`fade_s`, `black_s`) | `LUMA_S`, `BLACK_S`; when the reference's ending does not fit the length asked, the model's ending is used and the draft says why |
| `kills.per_s` | only a warning when the plan's kill rate is off by more than 25 % |
| `cut_rate_per_s` | printed against the draft's, with the reason the standing rules prevent matching it (the lead and the death shown fix a minimum take length) |
| `words` | not applied: the user's size rule wins |

## Vertical frame (`FRAME = "vertical"`)

The usual reference is a vertical TikTok edit, and vertical is what `draft_ref_timeline.py` writes by default. Set
`FRAME = "vertical"` in the music block of `timeline.py` (a hand-written timeline that omits FRAME is horizontal:
that is `frame.py`'s fallback, not the drafter's default); nothing else changes in the workflow. Output 1080x1920 at
60 fps with the same cuts, blur-in kinds and timing, slow motion, lyric words, luma fade and cover.

- **Framing.** A vertical reference made from horizontal recordings fills the frame by cropping to a third of
  the game width: the standing zoom the user rejected ("voce deixou um zoom no video todo"). So the whole 16:9
  gameplay (no crop, no zoom) sits in a 1080x608 rounded window on the exact centre of the frame, over a
  blurred, dimmed backdrop of the same footage that pulses on kills, with the window's shadow, stroke and halo
  (the house layout). The gameplay fills 32 % of the height by design: say so in the report when the
  reference fills the whole screen.
- **Effects.** Camera push, kill punch, shake, colour fringing, and the model edit's radial burst, colour split
  and bump nudge and light act inside the window, which stays put. The blur-in, streaks, lean-in, fade-in,
  `LUMA_IN`, the light rays, the inverted level-3 frame, the white flash-in and the luma fade act on the whole
  canvas, as an editor applies a whip or zoom to the whole composition (a window-only blur-in leaves a dead
  backdrop around it).
- **Words.** The same words on the exact middle of the 1080x1920 canvas, i.e. the middle of the gameplay window.
  Caps are 0.60 of the horizontal ones (135 / 121 px: 22 / 20 % of the window's height, a little above the window's
  own 0.5625 scale because a phone shows the frame small), the widest word 70 % of the width (756 px). Same rules: one
  word per cue, translucent, ink centred (measured within 1 px), stepping back on shots. `$PY text_test.py vertical`
  shows them and prints the numbers before the timeline says so.
- **Cover.** `cover_plates.py` and `cover.py` make a 1080x1920 cover (cap 200, ink within 900 px).
- **Measured** on 200 frames of the worked example rendered vertical from its store: 0 identical, 0 stalled
  frames, judder no worse than the same frames horizontal, render about 8 % slower. Full-length vertical edit in the
  default style (32.6 s, 16 kills, draft untouched): 1958 frames, 0 identical, 1 stalled (the known false positive on
  the frame before the intro cut), 8 one-frame jumps all on kills, accents or cuts, judder 0.165, -9.9 LUFS, decoded
  peak -1.22 dBFS; render 12 min at 2.9 fps. Full-length vertical edit with the model edit's patterns (30.6 s, 24
  kills, drafted untouched, automatic bullet time, level-3 inverted frames): 1838 frames, 0 identical, 1 stall (a
  pause in the recording), 0 unexplained jumps, no fast-forward, judder 0.240, -7.5 LUFS, decoded peak -1.19 dBFS;
  render 10 min at 3.2 fps. (Both were rendered before SYNC 2, whose timing is audited by `syncaudit.py`.)

Other output sizes or rates are not built: `FPS` in the timeline is the output rate and the rate the anchors
assume. A 30 fps reference does not change it: deliver 60 fps (stutter is the user's first complaint) and
copy the reference's rhythm in beats. `clipio.SW, SH` is the size of the working copies, not of the output.

## Music section and where the kills go

`M0`, `R0`, `R1`, `FADE_OUT` and how to pick the section: edit-design.md, "Music" (it holds for both
styles), and model-edit.md sections 1 and 2 (which part of the song becomes which part of the edit, fitted to the
user's song). In the model edit timeline beat 0 is the drop after the song's last break, the 16 beats before it
are the intro (bullet-time kills), and the video ends on the last sung word. In the worked example's timeline beat 0
is the first 808 after the vocal intro (`M0 = 31`), the 16 beats before it are the intro (`R0 = -16`: slow shots,
artist and title as words), the big drop is beat 32 and the video ends on a break (`R1 = 84.6`). `RISERS` end on
the drops (and, in a drafted edit, on each `"hit"` bullet-time kill).

Kills go on measured hits (`music_pulses.py`). In the worked example: 30 on kicks (every kick of the
section has one), 13 more on snares or claps, 19 on a loud hat (`high` 0.69 to 1.00) in the passages
where hats run on every half beat, none on a beat where nothing arrives. `music_pulses.py` lists 18 of
those 19 under "kills on a beat with neither kick nor snare": in this style check that each has a high
value; in the house style that list must be empty. Every kill, bump and boom, and with `CUTS_ON = "bass"` every cut
(against a kick of strength 0.4 or more), must pass the PLACEMENT CHECK that follows it: within 8.3 ms of a measured
attack, else FAIL and exit 1 (with sparse 808s a bass edit means
fewer, longer takes holding several kills, not a cut before every kill). Levels in a draft: model-edit.md section 5.
The worked example: `lv=3` on the drop and on the final kill, `lv=2` on the first kill and on kicks after the drop
(16 kills), level 1 elsewhere; 62 kills in 37 s of gameplay.

## Finding kills in raw 2-minute recordings

Raw ShadowPlay recordings hold menus, deaths, other windows. Put EVERY recording in `clips.json` first
(`mykills.py` skips, and names, the files it cannot map), then scan them all:

1. **Kill feed** (1080p: x 1300-1916, y 84-384): the player's own row has a lime wedge on the left, a
   teal body and a red victim section. `detect_kills.py <clips folder> detect [name filter ...]` takes the
   folder of the raw recordings as its FIRST argument and scans the `.mp4` files lying directly in it (not
   `src/`; `SKIP_PREFIX` leaves files out, and a trimmed copy `name-HH.MM.SS.mmm-HH.MM.SS.mmm.mp4` is skipped
   when its raw file is in the folder); the second argument is where it writes one json per recording
   (a recording that already has one is skipped as "cached"); further arguments are name filters
   (substrings of the file name). It decodes each WHOLE recording, tracking rows by the x where the red
   starts: no time limit per clip; measured on a Ryzen 5 5500, 18 s for one 83.5 s recording (about 0.2 s per
   second of video; up to three recordings run at once). `kill_review.py <clips folder> detect review` makes
   review sheets and `review/index.json` (copy it to `detections.json`). 107 detections on 27 clips, 10 false:
   the player's own death, a teammate, the buy menu, duplicates.
   A decode that returns more than 2 frames fewer than the file's packet count is retried in software; if it is still
   short, that file is reported FAILED, no json is written (a cached json from a short decode is not trusted) and the
   script exits 1 after the other files.
2. **Shot frame K** = the frame where the HUD ammo counter (x 1262, y 998, 84x44) changes, in any digit colour (it
   turns red at low ammo - a white-only match misses the low-magazine counter), 4 to 12 frames before the feed row
   (usually 6 to 10): `mykills.py` writes `kills.json` and
   `gal_NN.jpg`, and each entry carries `how`, `conf` and `verified`: `ammo` / `flash` = K measured on the pictures
   (conf `high` when the step and the flash are on K, `medium`), `ammo-loose` (several bullets) and `guess` (counter
   unreadable: feed - 7 frames) are NOT verified and the drafters refuse them. `strip.py clip a b` shows every frame
   with feed and ammo pasted in, `kverify.py` re-measures K and writes the verdict into `kills.json` (`--update`).
   An old `kills.json` entry without `how` is read as unverified (`guess`, or `ammo-loose` when its old conf said so)
   until `mykills.py` or `kverify.py` measures it again: a partial `mykills.py 12,13` run never marks the others verified.
   The K you confirm is typed into the timeline entry (and `"k_checked": true` in the plan).
   `mykills.py` alone measures every detection not in its `BAD` set; `mykills.py 12,13` only the listed
   ids, in that order (for a second look). Both number the sheets from `gal_01.jpg` (7 kills per sheet), so a
   subset run overwrites the sheets of an earlier full run (higher-numbered old sheets stay, out of date),
   and both rewrite `kills.json`: the listed ids are recomputed from the ammo counter, the other entries are
   kept. The K in the timeline entry is the authoritative one: `kills.json` is only a record (it is read by
   `flick.py`, which has its own `KFIX` for hand-set values) and is regenerated, so a hand-set K lives only
   in the timeline entry.
3. A feed row 2 or 20 frames after the only ammo change means another bullet or another shooter killed:
   look, or drop the kill.
4. **Choosing.** The user's own trims (`name-HH.MM.SS.mmm-HH.MM.SS.mmm.mp4`: start and end inside the raw
   clip, so the detections whose time falls inside are their picks) mark favourites. Prefer single taps
   (`flick.py`: no earlier shot in 30 frames) in clear scenes. Reject on sight: the enemy filling the
   screen, an explosion or flash over the picture, a flat-colour screen, dark scenes, sprays.
   `flick.py`'s travel number ranked a point-blank kill with an explosion first; the user removed it.

The house tools `find_kills.py`, `kill_table.py` and `kill_lags.py` (banner badge, 1344 px crop) are not
used here; `kill_table.py` would overwrite `kills.json` with another layout.

## Lyric words

Procedure (in the project folder; `$PY` = venv311; the separation and alignment steps run in `venv_sep`, which
`lyrics_sync.py` calls itself; both venvs: pipeline.md, "Setup"). `MUSIC` must be lossless (`src/music.flac`, which
`ingest.py` writes for any other format) and `timeline.py` must have SYNC 2; `lyrics_sync.py` refuses otherwise:

1. The words. The lyrics the user pasted, or: `$PY lyrics_sync.py --stem-only` (the voice of the edit's section,
   `lyrics/vocals.wav`), then in the speech-recognition venv
   `./venv_asr/Scripts/python transcribe.py lyrics/vocals.wav lyrics_whisper.json large-v3 --offset <t0 of lyrics/stem.json> --lang CODE`
   to read which lines the section holds, and confirm every line against a lyrics page (first bullet below).
   Recognition is for reading only: its word times ran up to 3.5 beats early and put whole lines one word early.
2. Write `lyrics.txt`: the confirmed words of the section, one line per sung line, in song order, EVERY word sung
   between the section's start and end (also words that stay off screen). Blank lines, lines starting with `#` and
   `[Refrão]` headers are ignored. A token is one word: `word`; `sung=SHOWN` when the sung form differs from the screen
   text (`takin=TAKING`); `sung=-` for a word that is aligned but not shown; `word@12.34` pins a word at timeline beat
   12.34. Numbers and symbols are written as sung (`lyrics_words.py` holds the format).
3. `$PY lyrics_sync.py`. The section is the video's own part of the song (timeline R0..R1; `--t0 S --t1 S` to change
   it; start where the voice is silent when you can). It separates the voice with demucs (htdemucs; at least 9 s with
   song audio around the section, trimmed back, because demucs delays an input shorter than its 7.8 s segment by up to
   3 ms), aligns the typed words twice by CTC (torchaudio MMS_FA and WAV2VEC2_ASR_LARGE_LV60K_960H; `--models mms`
   for a song that is not in English) and moves each word onto the sung ATTACK of the stem (CTC is only a prior).
   The CTC frame stride is exactly 320 samples = 20.000 ms, and each model runs `--shifts` (default 8) times with the
   stem moved by 2.5 ms steps; the median of the runs is the time (one run moved words by whole 20 ms frames when the
   stem was cut 5 ms differently: up to 171 ms). The attack is the half height of the level's rise in dB at its
   steepest point, capped at 20 dB; a voiced-note onset supports the nearest attack. It writes `lyric_cues.json`
   (`[beat_in, beat_out, "WORD", style]`), `lyrics/cue_audit.json` (the flags: ambiguous, unverified, weak, ctc-far,
   models-apart, unstable), `lyrics/sync_N.jpg` and a zoom panel per flagged word, then runs `lyrics_audit.py`.
   Options: `--red=A:B` (red beat ranges, default the intro before beat -0.5), `--last-end BEAT` (the last word
   leaves before the final kill), `--adv` (default 0: the cue IS the attack), `--redo`, `--force`. The per-model
   `--shifts` (how many times each alignment model is re-run on a 2.5 ms-shifted stem) belongs to
   `lyrics_ctc_align.py`, not to `lyrics_sync.py`.
   Stem and alignment are cached: a re-run after a `lyrics.txt` fix takes seconds.
4. Read its table (word, chosen beat, aligned beat, difference in ms, how, how far the two models were apart) and its
   CHECK list. If the models put a word over 0.35 s apart it stops: the typed words do not match the singing there
   (a line missing or extra, another wording, a section that starts inside a sung line); fix `lyrics.txt` or the
   section. Then the audit: every cue start against the nearest confident attack (a rise of 8 dB in 60 ms, or the
   start of a voiced note), in ms. A cue more than 25 ms from it with no flag is an ERROR (exit 1); flagged,
   no-attack and unstable words are WARNs: look at their zoom panel.
5. Read `lyrics/sync_*.jpg` (the overview: where each word is, good to about 25 ms) and the zoom panels
   (`$PY lyric_sync_sheet.py ... --zoom flagged|all|WORD,WORD` makes `lyrics/zoom_N.jpg`: one panel per word, +-250 ms,
   a 10 ms window with a 1 ms hop, the HF and LF level curves, the attacks with their dB, the CTC ticks, the cue as a
   red line, the frame the first letter is drawn on as a dashed line, 60 fps frame ticks): the red line must sit on the
   left edge of the syllable's energy. A word that is wrong goes into `lyrics.txt` with `@beat` (read the beat off the
   panel's ticks); then run step 3 again.
6. `$PY text_test.py` (and `text_test.py vertical`), `$PY timeline.py` (the "words on screen" line), stills of a few
   words over gameplay.

Measured on a 46-cue, 31 s section of a 124 BPM band track: stems cut 5 ms apart give cues within 2.4 ms of each
other with 8 runs (4.9 ms with 4; the single run it replaced: up to 171 ms); the audit run on the earlier delivered
cues of that edit reported 25 ERRORs, two of them 105 and 95 ms off; after the fix those two words sit +15.9 and -1.4 ms
from the reference times; the whole flow takes about 50 s on a desktop CPU (demucs 22-26 s, both alignments 21 s).

- **Right words only.** Speech recognition (faster-whisper large-v3, `transcribe.py`, its own venv) is for reading
  the words only: it gets about half of a trap verse wrong. Confirm each line against a lyrics page with yes/no
  questions through WebFetch (`letras.com.br`, `vagalume.com.br`; it will not quote lyrics, it does confirm
  phrases). Unconfirmed lines get no text. If nothing can be confirmed: no lyric words at all; artist and title over
  the intro are not recognised speech and may stay.
- **A new project has no cues** until `lyrics_sync.py` writes `lyric_cues.json`; the intro words typed in the
  timeline (`_T`) do show, until you replace them. `$PY timeline.py` ends with the number of cues and the first
  words: read that line.
- **Timing.** Each cue starts on the sung attack (CTC forced alignment of the confirmed words on a demucs vocal stem,
  two models, 8 shifted runs each, the median; then every start moved onto the measured attack, `--adv` 0), checked by
  `lyrics_audit.py` and the zoom panels. `textfx.py` shows the first letter on `nearest_frame(a) - HIT_LEAD` and
  spreads the letters so that the whole word is legible on `nearest_frame(a)`: the picture a frame ahead of the sound
  reads as in sync. A word that would be on screen under 0.22 beat rides with the next; each word stays while it is
  sung: until the next word, or until the voice stops when a silence follows (at most `WORD_HOLD_MAX`, 4 beats, in the
  timeline).
- **Centre and size** (the user: "a letra sempre deve ficar no meio da tela centralizada e nao muito grande tampando
  tudo, mas com um tamanho consideravel"). Each word on the exact middle of the frame: horizontally the visible ink
  (measured on the letter masks, not the advance widths), vertically the cap height on H/2; measured within 1 px in
  both frames. Caps 226 px for the red intro words and 202 px for the rest at 1080p (21 / 19 % of the frame height:
  280 / 250 px were "muito grande"), and no word wider than 70 % of the frame width (`frame.WORD_CAP_RED`,
  `WORD_CAP`, `WORD_MAXW`); a longer word or phrase is set smaller. A reference's bigger or off-centre words are not
  copied.
- **Translucent.** Blend on display values: overlay share 0.62 (0.50 for the red style) plus flat colour, at strength
  0.62-0.80, a small glow and a soft shadow. Drawn before the blur-in, so a whip blurs the word with the footage.
- **The enemy stays visible.** The crosshair is under the word: a word steps back (`duck` 0.35) from the shot until
  the enemy's body is down (`duck_death`), at least 0.28 beat and at most 0.60 beat after the shot (`duck_max`);
  a short word steps back less. `STYLE_OVERRIDES` in timeline.py changes a style (`strength`, `ov`, `cap` in 1080p px,
  `duck`, `duck_after`, `duck_death`, `duck_max`, `shadow=(dx, dy, blur, strength)`, `maxw`); a misspelled style
  name stops with a message. `$PY text_test.py` shows the first cue of each style on a flat background and prints the
  cap, the share of height and width and the centre offset.
- A lyric that names what is on screen is worth building around ("através da parede" on a wallbang,
  then the victim's replay).

## Sound

The picture is in slow motion or at real time on a changing time map almost all the time, so the game sound must not
follow the time map. `audio.py` (refstyle) places one gunshot per kill at natural pitch with its onset on the musical
hit (`s["hits"]`), sample-exact; K of a kill is `s["map"](shown beat)[0]`. The clip's sound is decoded on the file's
clock (a track that starts late in the file is padded, not read early). `shot_onset()` searches K-2 to K+8 frames for
the attack of the shot and reads it to the sample: a rise of 15 dB or more is always taken as measured; one of 8 to 15
dB only when it is within 4.75 frames of the flash and within a frame of the clip's other shots. It ends with a count:

| It prints | Meaning | Verified |
|---|---|---|
| measured | the shot's own onset, to the sample: on the hit by construction | yes |
| donor | `shot_from=(clip, K)`: another kill's clean shot, placed on that kill's own measured onset | yes |
| clip offset | another sound covers this shot; the clip's usual offset (median of its measured shots) was used, printed in ms. It can sit a frame or two off | no: the gate warns |
| edit median | its clip has no measured shot either (short edits: one or two kills per clip); the median offset of all measured shots of the edit was used, printed in ms | no: the gate warns |
| no gunshot, mute=True | you muted the take (voice chat over it, an intro shot) | |
| no gunshot, none found | the edit has no measured shot at all, or the clip has no sound | |

No median ever overrides a shot that can be measured (an earlier version did: one kill sat 1.3 frames off its own onset).
A clip with voice chat: set `mute=True` on each of its takes; do not rely on the automatic silence. A clip
without a clean shot of its own can borrow the same weapon's shot from another kill: `shot_from=(clip, K)` on the
entry (used only when the take's own shot is not clean; reported as "donor"). The gunshot's high-pass is causal (70 Hz,
per excerpt, 2 ms of pre-roll): a zero-phase one rang 6.75 ms before the onset at -18.7 dB. `audio_report.json` carries per kill the
musical `beat`, the `shown` beat, `state`, `how`, `hit_sample`, `onset_ms`, `rise_db` and `placed_ms` (0 by construction
of the integer placement: the real test is the finished file's cross-correlation, `syncaudit.py`). The mix is exactly
`N_FRAMES / FPS` long.

The sound of a tight edit (model-edit.md, section 6) comes from optional names in timeline.py; absent, the mix is
the worked example's (music, risers, gunshots):

| Name | Effect |
|---|---|
| `KILL_THUMP = 0.18` | a sub thump under every kill, x1.0 / 1.25 / 1.5 by level |
| `BOOMS = [dict(r=beat, gain=0.26), ...]` | sub drops: the drop, the strongest snare, a mid bullet-time kill, the last kill |
| `WHOOSH_BLUR = 0.07` | a swish on every `bwhip` / `bzoom` / `broll` cut, panned with the whip's direction, centred on the cut's MUSICAL beat (`s["m0"]`): all sound sits on musical beats |
| `GAME_LEVEL = 0.95` | the gunshot level (default 0.60) |
| `HEADROOM = 0.5` | the level `mix.wav` is written at (default 0.8) |
| `FADE_IN = 0.45` | a squared fade-in of the song, in seconds (default: 0.05 s linear) |

The mix is written at `HEADROOM`, and `run.sh`, `deliver.sh` and `peakguard.py out.mp4 chain mix.wav` apply the
same chain, `audio.master_chain()`: `volume = 1.18 / HEADROOM` (1.475 at 0.8, 2.36 at 0.5), an optional band limit
`MASTER_LOWPASS` (Hz), the limiter at 0.82 (`alimiter ... latency=1`: without `latency=1` its look-ahead delays the
whole sound by 143 samples = 2.979 ms), an optional trim `MASTER_TRIM_DB`. Loud gunshots, thumps and booms on a
loud master need `HEADROOM = 0.5` (the drafter writes it): at 0.8 the model edit's levels peak at 1.26 and
`audio.py` refuses to write the mix. `run.sh` gives every part its exact duration in the concat list and checks that
the joined video's pts are exactly 1/60 s apart (the mp4 muxer rounds a part's duration to whole milliseconds, and the
concat started the next part 0.33 ms early). Measured on synthetic projects: the muxed master's sound within 0.002 ms
of the song and the upload copy the same, after a `peakguard` re-encode too.

## Slow motion at 0.06-0.16x

This style holds slow motion far below the house style's 0.28x, which exposed RIFE's dead zone
(pitfalls.md). `check.py` shows it as "motion stops for one frame" at whole source positions.
`rifeutil.Tween` builds new stores right; `fixends.py` repairs an old one on the GPU; `posmap.py`
measures where each sixteenth really sits and the refstyle `render.py` renders from that (run it after
every change of the store, and once before the first still: `render.py` stops without `posmap.json`; it
also covers a half-repaired store when the GPU is busy).

## Cover image

Needs a reference-style project (the tools use its renderer and lettering; the house style has none).

1. Put three beats just after clean kills into `cover_plates.py` (three different scenes) and run it:
   frames of the edit without words and without camera moves, in `cover/`.
2. `$PY cover.py cover/plate_X.png "../capa_<name>_1.jpg" red "TITLE"`, then `_2` and `_3` with other
   plates and other styles (`red`, `gold`, `silver`, `white`): three covers to choose from.

The plate is darkened and the title set in the video's lettering on the exact centre, in capitals, kept
inside the middle 800 px so a vertical centre crop keeps it (a long title shrinks: use the short form).
Title only: the song title unless the user names one. The JPG follows `FRAME`: 1080x1920 in the vertical edit (the
default), 1920x1080 horizontal. `cover.py` refuses to overwrite an existing file.

## Costs (GTX 1650, Ryzen 5 5500)

1920x1080 store: 6.9 sub-frames per second, 0.55 MB each; about 23,500 files and 13 GB for 46 s.
Start `prep.py` as soon as the timeline passes; a second `prep.py` on a priority subset can run beside
it. Full render 15 minutes on an idle PC, 35 at below-normal priority while a game runs.

## What the user said, in order

| After | Their words | Change |
|---|---|---|
| the first render (watched in `_editor`) | "as letras estavam sem transparencia alguma 100% solidas, e no comeco aquele zoom ta mt feio" | translucent letters; intro at full frame instead of a 1.8-2.2x crop |
| a first version | "ta mt top so que vamos tirar ... aquela kill da raze, é muito feia e tentar sincronizar ao maximo as letras da tela" | kill replaced by a clean tap; one word per cue on vocal onsets |
| the next version | "tem que centralizar a letra no meio da tela, arruma isso e JA ERA" | ink centred on the middle of the frame; this version was the accepted one |
| covers | "tira esse valorant edit da tela" | title only |

Not judged: gunshots on the beat (13 of them placed by clip offset, 11 kills silent), zoom-burst
transitions outside the intro, the song title as intro words.
