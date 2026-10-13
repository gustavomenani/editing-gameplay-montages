# The model edit: the patterns to follow, fitted to the user's song

The edit the skill's author rates as the best this pipeline has made ("muito bem sincronizado e bem editado"). Its
patterns are written here as relations to the music (beats, measured hits, the song's sections), never as copied
times: **the song the user sends decides where everything lands.** A kill goes where the user's song has a hit, the
intro sits on the user's song's break, the ace on its last line. When the user's song lacks a feature the model used,
"When the song is different" below says what to do instead. The user's words outrank all of it.

The model in numbers: a 124 BPM band track, 30.9 s (the last chorus and the outro), 21 takes, 24 kills,
horizontal 1920x1080 at 60 fps, judder 0.26, -7.5 LUFS.

`draft_ref_timeline.py` writes these patterns by default (reference-style.md, "Drafting the entry list"); this page is
what to check the draft against, what to tune by hand, and why.

## 1. The section

| Pattern | In the model | Fitted to any song |
|---|---|---|
| The drop | timeline beat 0 = the loudest bar of the song, right after a break where the band stops | the strongest re-entry `music_tempo.py` lists, ideally one that follows a break, a drop-out or a riser |
| Where the video starts | 16 beats (7.7 s) before the drop, on a bar line, over the break | a bar line 6 to 9 s before the drop (16 beats from about 105 to 160 BPM, 8 or 12 below, 24 above) |
| Where it ends | the last sung word, then slow motion and a luma fade, then 1.35 s of black | the last word of a vocal line, or the last strong hit of an instrumental; always slow motion, fade, about 1.4 s of black |
| Length | 30.9 s | 25 to 35 s unless the user asked for another length; a section that ends on a phrase beats one cut to the second |

Prefer a late section (last chorus plus outro): it ends on a natural last word, which the final kill can land on.

## 2. The song's parts become the edit's parts

| The song does | The edit does | Built with |
|---|---|---|
| a break or quiet bars before the drop | bullet-time kills: each take a slow lead-in (0.11 to 0.25x, shutter 2.2 frames, softer intro look) into a kill on a measured hit, one kill every 4 to 8 beats; the opening reveals the bright areas first | `intro.kills` in plan.json; `LUMA_IN` |
| the last 4 beats before the drop | the last intro take: a white flash-in at its start, a riser over the 4 beats, a slow lead-in that reaches real time a frame before the shot | the drop kill (`"bullet": true`) |
| the drop | that kill fires exactly on it: level 3 (inverted frame, biggest burst), a boom | |
| the full band after the drop | one kill per take, about one per second, every kill on a measured kick or snare; the first kills after the drop come fastest (1 to 1.5 beats) | `cuts_on: "kills"` |
| the strongest snare of the section | a level-3 kill, a boom | levels |
| the drums thin out (a bar with weak kick and snare) | a second bullet time: 2 to 3 beats of slow lead-in with a white flash-in and a riser into the next strong hit, a boom | the drafter finds it by itself (`auto_bullet`, on by default): 1.5 beats or more of drums under 35 % of a typical hit after a louder passage, then a strong hit within 2 beats; at most one per 30 s, never in the last two bars (the ace's). Your own `"bullet": "hit"` on a kill, or `"auto_bullet": false`, overrides it |
| the last vocal line | the best multi-kill (the ace) kill by kill, one kill every 1.5 to 2.5 beats, all from the same clip | plan order |
| the last sung word | the final kill (level 3 but calm: no zoom, punch or shake), then slow motion at about 0.08x under the fade | the last kill of the plan, pinned with `"at"` on the beat of the last sung word |
| strong hits that carry no kill | a light pulse and a 1.2 % nudge (a "bump") so the picture keeps moving with the drums | `BUMPS` (the drafter fills it from the measured hits) |

Where the song has no such part, leave that part out; never invent a bullet time where the drums do not thin out.

## 3. Kill rhythm

- Kills only on measured hits (`beat_hits.py` / `music_pulses.py`). In the model 8 of the 21 kills after the drop sit
  on the backbeat snare; the others on kicks (on the beat and on off-beat eighths) and three syncopated hits.
- The spacing is set in SECONDS, then rounded to the song's hits: median 1.0 s, range 0.5 to 1.7 s, about 10 kills per
  10 s. In beats that is `gap ≈ BPM / 60` beats:

| Song tempo (the drums' tempo) | Typical gap | Shortest gap between two takes |
|---|---|---|
| 80 BPM | 1 to 1.5 beats | 1 beat |
| 100 BPM | 1.5 to 2 beats | 1 beat |
| 124 BPM (the model) | 2 beats (1 to 3.4) | 1.5 beats |
| 140 BPM | 2 to 2.5 beats | 1.5 beats |
| 160 to 175 BPM | 2.5 to 3 beats | 2 beats |

- The shortest gap is physical, not a taste: a take needs its lead (14 frames) and the enemy's death (about 22
  frames) on screen, so two takes' kills are at least `(14 + upto) / FPB` beats apart (about 0.6 s at any tempo).
  Closer kills go into ONE take (an `M` entry: a double, a spray transfer), where the footage between them plays at
  0.6 to 1.0x and the later kill still lands on a hit.
- Vary the gaps (1.5, 2, 2.5 beats), never a metronome; tighten them right after the drop and over the ace, loosen
  them before an accent.
- What matters is the time (about one kill per second), not the beat count: whether `music_tempo.py` counts a trap
  groove at 70 or at 140 BPM, the kills stay about a second apart, on its measured hits.
- The fit, measured: the model's 24 kills drafted on a 130 BPM trap song (sparse 808s, loud hats on every half beat)
  give 30.7 s with every kill on a measured hit there (6 kicks, 4 snares, 14 loud hats), the 14-frame lead = 0.51
  beat, median gap 2 beats = 0.92 s, levels 15 / 6 / 3, 13 bumps: the same edit, re-timed to the other song.

## 4. Take anatomy (every take)

| Phase | In the model | Why |
|---|---|---|
| Cut | 14 output frames before the take's first shot (0.48 beat at 124 BPM, so a kill on the beat gets its cut on the eighth before it) | the enemy is seen before he dies; a kill 4 frames after a cut "nem aparece" |
| Lead | real time from the cut to the shot; the muzzle-flash frame on the hit | nothing ever plays faster than real time ("do nada voce coloca o video muito rapido") |
| Shot | real time for 8 frames (recoil, flash) | slow motion on the flash magnifies interpolation artifacts |
| Death | one constant slow rate that reaches `K + upto` (the frame the body is down) exactly at the next cut: 0.2 to 0.9x depending on the gap | the enemy visibly dies inside the take ("ele nem chegou a morrer") |
| Long gap | when the death would need less than about 0.15x, slow until the body is down, then ease back toward real time | no near-frozen picture |

Keep the lead between 12 and 16 frames at any tempo (it is the time the eye needs, not a fraction of a beat).
`upto` is measured per kill on `deathstrip.py` sheets (21 to 28 frames in the model); the default 24 is only a guess.
No take without a kill; no enemy of a few pixels; the kill feed row confirms each kill (SKILL.md, the user's rules).

## 5. Accents

| Level | Which kills (model: 15 / 6 / 3) | Picture | Sound |
|---|---|---|---|
| 1 | the rest | radial burst +3.5 % decaying over 6 frames (centre sharp), RGB split 5 px, punch 2 %, shake 4 px | gunshot, thump |
| 2 | the first kills after the drop, the strongest backbeat snares, the mid bullet-time kill: about a quarter of the takes, never more (level 2 everywhere is no accent) | burst +6 %, split 9 px, light rays, punch 3.2 %, shake 7 px | + harder thump |
| 3 | the drop, the strongest snare, the last kill | burst +9 %, split 14 px, rays, ONE inverted monochrome frame on the shot, punch 4.5 %, shake 10 px (the last kill: calm, only the fade) | + boom |

- Blur-in on every cut (5 frames): a zoom burst on takes with a level-2/3 or bullet-time kill, whips alternating
  direction on the others, a roll about every fourth take; the opening fades in from black.
- Camera push-in 3 % over a take, 5 % over a bullet time, none in the intro and on the calm ending.
- `IMPACT` and `ACC` in timeline.py hold these values; LOOK scales them (`kill_zoom`, `fringe`, `shake`, `flash`,
  `impact`).

## 6. Sound

- One gunshot per kill with its onset on the beat, a little louder than the house mix (`GAME_LEVEL` 0.95): "dar um
  pequeno destaque a mais no som das kills". A clip without a clean shot borrows the same weapon's shot (`shot_from`).
- A sub thump under every kill (`KILL_THUMP` 0.18), a swish on every blur-in cut (`WHOOSH_BLUR` 0.07, panned with the
  whip), booms on the level-3 and bullet-time kills (`BOOMS`, 0.18 to 0.26).
- Risers that stop dead on the drop and on the mid bullet-time kill.
- The music fades out under the final slow motion. The model's master: -7.5 LUFS integrated, true peak -1.0 dBFS.

## 7. Look

Saturated, contrasty, with a clearly visible vignette (the user asked for "vinheta, uma cor mais saturada"):
exposure 1.10, saturation 1.32 (intro 1.22), vignette 0.42 (intro 0.55, corners at 0.80 of the centre), S-curve 0.06,
bloom 0.11 and a faint wide glow. `LOOK = "modelo"` reproduces it; the user's words about colour override it.

## 8. When the song is different

| The user's song | Do |
|---|---|
| no break or quiet bars before its drop | an 8-beat intro, or start one bar before the drop with only the bullet-time lead-in; keep the riser |
| no strong drop at all (steady groove) | start on a bar line at a phrase start; the first kill on the first strong snare gets level 3 |
| instrumental, no last word | end on the last strong hit or the final chord; same slow motion, fade and black |
| very fast (above 150 BPM, drum and bass) | gaps of 2.5 to 3 beats; lead 12 frames; the mid bullet time on the breakdown |
| slow (below 90 BPM) | gaps of 1 to 1.5 beats; loud hats may carry kills in dense bars |
| half-time trap (808 on 1, snare on 3) | kills on 808s and snares (loud hats in dense bars); gaps by seconds (section 3) |
| a live band mix (the bass on every half beat) | nothing to do: the measure takes the kick from the onset of the low band (a held bass note does not count) and the snare from body and crack arriving together, within +-50 ms of the half beat (a drummer drifts), so `music_pulses.py` lists the backbeat snares and the drafter gives them level 2 (measured: 12 of 12 backbeat snares found); give `level` in the plan only to override |
| drums everywhere equally strong | fewer bumps: about one every 2 s, on the strongest hits only |
| no bar where the drums thin out | no mid bullet time |
| fewer kills than the section needs | a shorter section, not slower takes; never repeat a play |
| the user named the plays, the order, the look or the transitions | their words win; keep the rest of this page |

## 9. Check a draft or a render against the model

| Measure | Model | Where to read it |
|---|---|---|
| kills on measured hits | 24 of 24 | `music_pulses.py` |
| lead per take (frames from cut to shot) | 14 (bullet times: their lead-in) | the drafter's explanation |
| every death shown | 24 of 24 | `deathstrip.py` (green tiles until the body is down) |
| kills per 10 s after the drop | about 10 | `timeline.py` |
| median gap after the drop | 1.0 s | the drafter's explanation |
| fastest frame | 1.17x (easing); with `MAX_SPEED = 1.0` the drafter keeps it at or below 1.02 | preflight, `check.py` "fast-forward" |
| output frames below 0.6x | 63 % | the drafter's statistics |
| bumps | 13 in 31 s | `timeline.py` |
| flashes | 18 on +0, 3 faint on +0, 3 on +1 (`check.py`'s prediction for the tiles of `sync_*.jpg`) | `check.py --sheets` |
| judder | 0.26 | `check.py` |
| sound | -7.5 LUFS, true peak -1.0 dBFS | `check.py` |
