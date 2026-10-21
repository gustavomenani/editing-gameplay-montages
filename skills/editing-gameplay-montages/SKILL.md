---
name: editing-gameplay-montages
description: Edit gameplay clips (Valorant, CS2, Fortnite, any shooter) into a music-synced highlight montage, frag movie, velocity edit or TikTok/Reels/Shorts "edit" with beat sync, slow motion, speed ramps, kill zooms, transitions, lyric words, cover image; also copy the editing of a reference video ("com a mesma edição desse vídeo"), or fix a rendered edit that stutters ("travado", "quedas de fps"), has choppy slow motion or kills off the beat. Portuguese - "edita um vídeo", "faz um montage", "highlight", "edit pro TikTok", "faz uma capa". Not for plain trimming, joining or converting clips (use ffmpeg).
---

# Editing gameplay montages

## Overview

A music-synced gameplay edit rendered by a custom Python pipeline. ffmpeg only decodes and encodes; time remapping, motion blur, camera moves, transitions, text, colour and sound are computed in Python from one file, `timeline.py`, written in beats of the music.

**Core principle: you cannot watch or hear the video, so nothing is done by feel.** Frames are addressed by index, beats are measured on the waveform, each kill is pinned to its muzzle-flash frame, and every render is judged by numbers and by images you read. Every shortcut around this produced a version the user sent back (pitfalls.md).

The bundled scripts are measured, not assumed: on synthetic projects with sample-exact truth every picture event lands on its exact frame (0 frames off), every gunshot within 0.2 ms of its hit and the delivered sound within 0.1 ms of the song, and the delivery gate repeats that audit on every file that leaves (verification.md). Copy them into the project and edit `timeline.py`; do not rewrite the pipeline from memory.

## Sync: everything lands on the music's measured hits (SYNC 2)

The user's most repeated complaint is desync (quotes in "What the user wants"). Every script that reads `timeline.py` holds it to this contract; the gate refuses a file that breaks it.

| What | Rule |
|---|---|
| The musical moment | a MEASURED time: the attack of a drum hit (`beat_hits.py`, the ONE attack definition of the skill; `music_hits.py` writes `hits.json`) or a sung onset. In the timeline `hit(t) = (t - BEAT0) / PER - M0`, 9 decimals. A grid line only where the music has no hit (a cut between two hits, the ending). Never the grid time of a hit |
| The picture | one exact output frame: `vis(r, lead)` = the frame nearest to the moment, then `lead` whole frames earlier. Cuts use `CUT_LEAD`, shots, kill accents, bumps, white flash-ins and words `HIT_LEAD`. Default 1 frame each; with a reference, the reference's measured lead. Every accent of one shot (punch, shake, exposure pop, fringe, burst, rays, inverted frame) starts AND peaks on that frame; the muzzle flash is whole on it and absent on the frame before. No `ceil`, no beat-domain tolerance |
| The sound | gunshot, thump, boom, riser end and the song itself on the exact musical beat, sample-exact (`s["hits"]`; `take_of(n)` = the take on output frame n) |
| Why the lead | a picture a frame ahead of its sound reads as in sync, behind it as late. Measured on the user's reference: its cuts come 1.3 to 1.9 frames and its kill flashes 1 frame before the drum attack |
| The bar | picture events 0 frames off; every placed gunshot within 1 ms of its hit (the audit matches the clip's own excerpt in the master); delivered audio against the song 0 +- 0.1 ms; video timestamps on the exact 1/60 s lattice |
| Old timelines | a `timeline.py` without `SYNC = 2` is refused (render, audio, check, preflight, gate, music_pulses, lyrics scripts) with the update message: copy `scripts/`, then `scripts/refstyle/` over it, copy the SYNC block of the timeline example, draft again, render again. No silent fallback |

## The model edit: the quality bar

One edit made with this pipeline is the author's best ("muito bem sincronizado e bem editado"). **model-edit.md**
holds its patterns, written as relations to the music (beats, measured hits, the song's sections), so they fit
whatever song the user sends: the intro on the song's break, the bullet-time kill on its drop, a kill about every
second on its measured hits, each take cut 14 frames before its shot and held until the enemy's body is down, the
ace on its last line, bumps on the hits between kills, accents and sound by kill level. The default style follows
them: `draft_ref_timeline.py` writes them and `LOOK = "modelo"` is their look. Read model-edit.md before you write
or tune a timeline, and check every draft and render against its section 9. A reference video decides its own look
and cut rhythm; the take anatomy (lead, death shown, nothing faster than real time) and the user's rules still hold.

## First reply: the briefing

**Language comes first.** Write the whole first message in the language of the user's message: English
message, English reply; Spanish, Spanish. The Portuguese briefing below is the version for Portuguese speakers
only; for anyone else, translate every line of it (headings, questions, tips) and leave no Portuguese word in.

When this skill loads, the first message you write is the briefing, in the user's language and tone. You may
first list the folder (read only) to see the clips, song and reference video; never claim to have seen what
you did not list. Leave out every item their message or the folder already answers.

Skip the briefing, say in two or three lines which defaults you take, and start, when either holds:
- they tell you not to ask ("não me pergunte nada", "só faz", "decide você", "don't ask me anything", "just do it");
- their message already settles the build options AND says how the edit should look: format, length, the look
  (a reference video in the folder, a description, effects, or "padrão"), where the transitions land, lyrics,
  cover, the song and its section. Plays, intensity and the game are not reasons to ask once those are set: find
  the game and clips in the folder, use the plays they named ("abre com o ace"), take the defaults for the rest.

A message that settles only some of them gets the briefing with only the missing items. "How it should look" is
always asked unless it is settled: the quality of the edit depends on it. Then wait for the answer; after it,
decide everything else alone. Ask only what the skill can deliver (see "Never promise"). Map every effect the
user names to the options in "Edit options" below.

> Bora fazer esse edit! Pra ficar do jeito que você imagina, me conta:
>
> 1. **Como você quer o edit**: descreve do seu jeito (por exemplo "agressivo, muito tremor e cor fria", "limpo e cinematográfico", "velocity com a letra na tela"). Vertical (TikTok, Reels, Shorts) ou horizontal (YouTube)? Quanto tempo, uns 15, 30 ou 45 segundos?
> 2. **Referência, o que mais faz diferença**: coloca na pasta um edit que você curtiu, baixado do TikTok ou do YouTube, vertical ou horizontal. Com ela eu copio os cortes, o ritmo, os efeitos e o texto, e o resultado fica muito mais perto do que você quer. Sem referência eu uso o meu estilo padrão e as opções abaixo.
> 3. **Efeitos** (escolhe os que quiser, ou fala "padrão"):
>    - intensidade geral: suave, padrão, intensa ou máxima
>    - transições: no ritmo das kills (o padrão: um corte logo antes de cada kill) ou no grave da música (menos cortes, mais fino)
>    - cor: natural, quente, fria, teal & orange, preto e branco ou vibrante; mais ou menos saturação e contraste
>    - vinheta, granulado de filme, brilho (glow), aberração cromática (RGB split): mais, menos ou sem
>    - nas kills: tremor, zoom e flash: mais, menos ou sem
>    - câmera lenta: mais ou menos; barras de cinema (só no horizontal)
> 4. **Letra e capa**: quer a letra da música na tela, palavra por palavra no tempo da voz? Se quiser, cola a letra aqui. Quer capa?
> 5. **As jogadas**: quais são as melhores, e qual você quer abrindo e fechando o vídeo? Tem alguma que não pode faltar ou que você não curte?
> 6. **A música**: qual arquivo, e se quiser, qual parte (por exemplo "o drop em 0:45"). **O jogo**: Valorant, CS2 ou outro?
>
> Dicas para ficar top:
> - **Clipes**: o ideal é 1920x1080 ou mais, a 60 fps ou mais (ShadowPlay, Outplayed, OBS, Medal), com uns segundos antes e depois de cada jogada. Gravação crua de alguns minutos também serve, eu acho as kills. O vídeo sai sempre em 1080p a 60 fps, mesmo com clipes em 4K.
> - No vertical o gameplay fica inteiro numa janela sobre um fundo desfocado do próprio jogo: eu não corto a imagem para encher a tela, porque isso vira um zoom que borra o jogo.
> - **Música** em boa qualidade: .flac, .wav ou .mp3 320k.
> - Tudo na mesma pasta. Eu crio uma pasta `_editor` lá dentro para o projeto. Reserve de 7 a 13 GB livres nesse disco, mais o tamanho das cópias convertidas quando os clipes não são 1920x1080 a 60 fps, ou estão em outro disco.
>
> Depois disso eu decido o resto sozinho e te entrego cada versão como um arquivo novo, sem apagar nada seu. Depois de ver, é só me dizer o que mudar.

Never promise, never offer (say it in the first message, name what you deliver instead, and go on; never turn
it into a question you cannot act on):
- an output other than 1080x1920 or 1920x1080 at 60 fps: no 4K, no upscale "extra". A vertical edit never crops
  the gameplay to fill the screen: it sits whole in a window over a blurred backdrop (reference-style.md,
  "Vertical frame"); say so when the reference fills the screen;
- lyrics or a cover in the house style (it has no text renderer, edit-design.md "Not done yet"): the house style is
  made only on request, and a user of it who wants words or a cover gets the default style instead;
- CS2 or any game but Valorant as proven kill finding: say you check every kill on the review sheets.

Defaults for anything left unanswered: THE REFERENCE STYLE (the default style for everyone, with or without a
reference video), vertical (`FRAME = "vertical"`: the whole game in a window over a blurred backdrop), about 30 s,
the model edit's patterns and look (model-edit.md; `draft_ref_timeline.py` writes them, `LOOK = "modelo"`),
transitions with the kill rhythm (`CUTS_ON = "kills"`: a cut 14 frames before each kill), no text on screen unless
the user pasted lyrics or asked for them, no cover, the section and plays you judge best. With a reference video in
the folder it ALWAYS drives the edit: the `adopt` block of `ref_analyze.py` (frame, look, cut lattice and lead, cut
gaps, transitions, slow motion, intro, ending, kills per second), artist and title as intro words, lyric
words only from lines the user pasted or that were confirmed (reference-style.md, "Lyric words"). Write the answers
and the defaults taken into the project's `LEIAME.md`.

## Edit options (what the user asks for, what to set)

The user's words outrank the reference and the defaults. Every look option lives in one `LOOK` value in
`timeline.py`, read by both renderers through `scripts/look.py` (`$PY look.py` prints the table with ranges):
`LOOK = "intensa"`, `LOOK = {"vignette": 1.6, "shake": 0}`, or `LOOK = {"preset": "intensa", "grade": "cool"}`.
Numbers multiply the worked example's look: 1 = as there, 0 = off, 2 = strong. No `LOOK` (or `"padrao"`) is the worked example's own look; `"modelo"` is the model edit's look (more saturated, a visible vignette, brighter; the
drafter's default). A value that would break a user rule is clamped and the clamp is printed; `preflight.py`
names a misspelled key ("vinheta" -> did you mean "vignette"?).

| The user says | Set |
|---|---|
| "suave", "leve", "clean" / "intenso", "agressivo" / "no máximo", "pesado" | `LOOK` preset `"suave"` / `"intensa"` / `"maxima"` |
| "vinheta" (forte, leve, sem) | `vignette` 1.6 to 2 / 0.5 / 0 |
| "cor quente", "cor fria", "teal & orange", "preto e branco", "cores vivas" (+ "leve" / "forte") | `grade` `"warm"`, `"cool"`, `"teal_orange"`, `"mono"`, `"vibrant"`; `grade_amount` 0.5 / 2 |
| "mais saturado", "mais contraste" (or less) | `saturation`, `contrast` 1.5 to 2 (0.5) |
| "granulado", "estilo filme" | `grain` 1.5 to 2 (the reference style has none by default: 1 = none there) |
| "glow", "brilho" | `bloom` (alias `glow`) |
| "sem tremor" / "mais tremor" | `shake` 0 / 1.5 to 2 |
| "sem zoom nas kills" / "mais zoom" | `kill_zoom` 0 / up to 1.5 (never more: a bigger zoom stops being an accent) |
| "flash nas kills" (mais, sem) | `flash` |
| "RGB split", "aberração cromática", "glitch" | `fringe` 1.5 to 2 |
| "frame de impacto" (sem) | `impact` False: the house style's impact frames, and in the default style the inverted frame of level-3 kills (`IMPACT` in the timeline) |
| "mais claro" / "mais escuro" | `exposure` 1.1 to 1.3 / 0.8 to 0.9 |
| "brilho em volta", "glow largo" | `wide_glow` 1 to 2 (default 0; `"modelo"` uses 1) |
| "igual ao edit modelo", "o melhor estilo" | `LOOK = "modelo"` and the drafter's defaults (model-edit.md) |
| "barras de cinema", "cinematográfico" | `bars` True (reference style horizontal only: they cover the kill feed and the ammo, say so) |
| "cortes mais secos" / "mais borrão nos cortes" | `blur_in` 0 / 1.5 to 2 (reference style) |
| "transições no ritmo das kills" / "no grave" | `CUTS_ON = "kills"` (default) / `"bass"` |
| "vertical" / "horizontal" | `FRAME = "vertical"` (default) / `"horizontal"` |
| "mais câmera lenta" / "menos" / "sem" | drafted takes slow down only for the enemy's death until the next cut (`fall()`): "mais" = longer gaps between kills, more `"bullet": "hit"` kills, a lower `rate` on the last take; "menos" = shorter gaps; "sem" = gaps of about `(14 + upto) / FPB` beats, where the death fills the take at real time. Hand-written takes: `post()` slow rate 0.12 to 0.16x (house style on request: `tail()` rate and finishers) |
| "transições" of a named kind (whip, zoom, giro) | blur-in kinds `bwhip`, `bzoom`, `broll` (`tin` of an entry); house style on request: `tin` kinds (edit-design.md, "Transitions") |
| "letra na tela", "capa" | reference-style.md, "Lyric words", "Cover image" |
| "estilo janela", "estilo house", "transições que mexem os dois clipes" | the house style (below; edit-design.md): vertical only, shows two thirds of the game width, no words, no cover. Only on such a request |

Anything not in this table that the user asks for (a kill counter, a sound pack, a 3D transition, a text other
than the lyrics) is not built: say so plainly and name the closest option.

## Which style

| The user gives | Style | Read |
|---|---|---|
| anything: clips and a song, with or without a reference video | the DEFAULT, the reference style with the model edit's patterns (model-edit.md): blur-in cuts, a cut 14 frames before each kill, the death held in slow motion, bullet times on the drop and where the drums thin out, lyric words on request, luma fade, cover. OUTPUT 1080x1920 by default (`FRAME = "vertical"`: the whole gameplay in a window over a blurred backdrop) or 1920x1080 full frame; sources of any size and rate are fine (`ingest.py`) | model-edit.md; reference-style.md; `scripts/` plus `scripts/refstyle/` |
| an explicit request for the window style ("estilo house") | house style, below | edit-design.md; `scripts/` only |

The house style used to be the default for edits without a reference; the user found it weaker than the reference
style ("esse estilo house nao ta legal, a gente precisa ter um padrao legal igual ao padrao referencia"), and it
crops the game to two thirds of its width, against "eu prefiro que a tela toda aparece". It stays available on request.

Not for: plain trimming, joining or converting (use ffmpeg directly); edits the user wants to keep adjusting by hand in an editor (tools-research.md).

## House style (only on request)

- 1080x1920, 60 fps. Gameplay in a wide rounded window over a blurred backdrop of the same footage that pulses with the beat; the window shows two thirds of the game width (minimap and kill feed cut off): say so when it is asked for.
- Every kill on a measured kick or snare, with its gunshot heard on that beat.
- Zoom, shake and flash are short accents on kills. Slow motion only as a finisher, with real motion blur. Inside a take, speed ramps replace cuts.
- Transitions move both clips (whip, spin, zoom-through). No white flashes. Where they land is the user's choice (`CUTS_ON` in the timeline): on the bass by default, or with the kill rhythm.
- Intense but smooth: stutter is the defect the user notices first.

## What the user wants, in their words

These hold in BOTH styles and outrank a reference video where the two disagree.

| Rule | Their words |
|---|---|
| No standing zoom: never a crop or zoom that enlarges the gameplay for a whole shot, not even to hide the HUD. Short accents that ease in and out were accepted, each style with its own values: house (windowed) kill zooms of 12 to 21 %, edit-design.md; reference (full frame) a push-in of 3.5 % per take and a kill punch under 5 %, reference-style.md | "voce deixou um zoom no video todo ... fica estranho"; "no comeco aquele zoom ta mt feio" |
| Nothing may stutter; slow motion perfectly smooth | "o slow motion ta bem travadinho"; "sinto umas quedas de fps" |
| Nothing plays faster than real time unless the user asks for velocity: no fast-forward in the blur-in, between kills or after the slow motion (`MAX_SPEED = 1.0`, which `draft_ref_timeline.py` writes and `preflight.py` enforces; on request 1.6 or `None`) | "do nada voce coloca o video muito rapido e fica estranho demais"; "clips acelerados do nada" |
| Everything lands on the music's measured hits, frame-exact: kills, transitions, effects, words and sound, never a desync between clips and music (the Sync section above; the gate refuses it) | "da pra sincronizar melhor"; "os videos sempre tem muitos problemas de sincronizacao com a musica nas kills e transicoes e efeitos isso tem que ficar perfeito e nunca ter essas desincronizacoes com os clips e musicas ... tem que ser rigoroso" |
| The edit is made from the reference whenever there is one (ALWAYS: `ref_analyze.py` -> `adopt` block of `ref_notes.json` -> the drafter follows it; plan keys only for what the user said), and always goes with the music's rhythm (every event on the song's measured hits or lattice lines) | "o video sempre deve ser feito baseado na referencia caso tenha, e sempre ir tambem no ritmo da musica" |
| Every kill in the edit is the player's, visible at the aim, with K on the shot that killed; the same play never twice (a DVR and its trim are the same footage); the best kills first (`kill_rank.py`), and `kill_rank.py --check` clean before render | "ela tem que escolher melhor os clips, e tem algumas vezes que coloca algumas kills erradas"; "a nossa skill tem que ser cirurgica nao pode ter erros idiotas" |
| Every kill must be SEEN: the enemy on screen before the shot. A take's cut is SHOWN 14 frames (`lead_frames`: 12 to 16 whole frames from the cut's frame to the shot's frame at any tempo) before its first shot and runs at real time to it; never a kill 4 frames after a cut | "reveja as kills por que tem kill que nem aparece, precisamos ser cirurgicos" |
| The enemy visibly DIES inside the take: after the shot it runs until the body is down (`upto`, measured per kill with `deathstrip.py`: tiles the edit shows are green), slow motion only after that frame is reached; the next cut never comes earlier | "teve um clip do omen que ele nem chegou a morrer" |
| No take without a kill: no ability or skin hold where nobody dies, even if a reference has them (`intro.kills` replaces intro shots) | "tem um clip do phoenix que nao mata ninguem ele so anda na smoke retira isso" |
| Where transitions land is an OPTION asked in the briefing, `CUTS_ON` in timeline.py. `"kills"` (default, as in the model edit): a cut on a line of the song's lattice (the reference's step first, else 1/2, 1/4, 1/8 beat), on the measured attack there when there is one, chosen so that the SHOWN lead to the take's first kill is 12 to 16 frames; the kills carry the rhythm. `"bass"`: every transition on the attack of a kick / 808, never on a snare alone, and the take's first kill at least `lead_frames` after it; fewer, longer takes in sparse trap (measured on accepted edits with the kill rhythm: the house example had 0 of 13 transitions on a kick, the worked example 19 of 57) | an editor's note: "as trasições rolarem nos graves da música, não no snare. acho que vai ficar mais fino"; the user: "essas transicoes no grave pode ser uma opcao da pessoa" |
| The ending only darkens: no zoom on the ace | "no fim nao de um zoom no ace apenas deixe a tela escurecer" |
| Words on screen are translucent | "as letras estavam sem transparencia alguma 100% solidas" |
| Words ALWAYS sit centred in the exact middle of the screen, big enough to read at a glance but never covering the game: caps 21 / 19 % of the frame height (226 px red intro words / 202 px the rest at 1080p), the widest word at 70 % of the frame width (280 / 250 px and 86 % were "muito grande"); vertical frame: 0.60 of those (135 / 121 px, 22 / 20 % of the gameplay window), widest word 756 px. The crosshair, i.e. the enemy, is there too: a word steps back from the shot until the body is down (textfx `duck_death`, `duck_max`). A reference's bigger or off-centre words are not copied; `$PY text_test.py` prints the numbers | "a letra sempre deve ficar no meio da tela centralizada e nao muito grande tampando tudo, mas com um tamanho consideravel"; "tem que centralizar a letra no meio da tela"; "ta muito grande tem que dar uma diminuida leve nela" |
| Words follow the voice one by one, exactly where each is sung: CTC forced alignment of the confirmed lyrics on a demucs vocal stem, two models (`lyrics_sync.py`), each cue moved onto the measured sung attack (no advance: the first letter shows `HIT_LEAD` frames before it, the whole word on it), checked by `lyrics_audit.py` and the zoom panels before rendering; speech recognition only to read the words, never for their times (it put whole lines one word early) | "tentar sincronizar ao maximo as letras da tela"; "as letras da tela nao estao sincronizadas com a musica" |
| No label, subtitle or watermark: only the song's words (artist and title as intro words passed without comment) | "tira esse valorant edit da tela" |
| "Bonito" = a clean kill at a distance, not the biggest flick | "aquela kill da raze, é muito feia" (point-blank, explosion over the screen) |
| After the briefing, decide alone and report afterwards: no questions in the middle of the work | "nao me pergunte NADA"; "apenas faça o que voce decidir" |
| When they say they will play, stop every heavy job at once (how: pipeline.md, "Handling jobs on the user's PC") | "consegue renderizar dps ?vou jogar agora" |
| The whole game screen shows, in vertical and in horizontal: the reference style's vertical frame puts the full 16:9 picture in a window over the blurred backdrop, never a crop that hides the minimap, kill feed or HUD to make the gameplay bigger. Do not offer a cropped vertical | "eu prefiro que a tela toda aparece na vertical e horizontal" |

## Workflow

`PY=./venv311/Scripts/python`, in Git Bash, from the project folder `<clips folder>/_editor/`. Every Bash call starts in a fresh shell, so begin each command with `cd "<project>" && PY=./venv311/Scripts/python &&`. Setup commands, script table and timings: pipeline.md.

0. **Briefing**: unless one of its skip conditions holds ("First reply: the briefing", above), the first message is the briefing; wait for the answer. Then list the folder and decide the rest alone.
1. **Project**: copy the scripts and `models/` (pipeline.md, "Setup"), create the venv, run `$PY doctor.py`: on `FALTA:` fix each item with the fix it prints and run it again before going on; an `AVISO` does not stop you but goes into the report (OneDrive, accents in the path, RIFE on the CPU = hours). Then write `clips.json` and `$PY ingest.py && $PY mkpts.py`. `ingest.py` accepts any size, frame rate and container (1440p, 4K, 4:3 stretched, 21:9, 30 to 240 fps, HEVC, AV1, .ts, OBS multi-track, HDR tone mapped, rotated phone clips upright, vertical ones padded) and makes 1920x1080 60 fps working copies; everything after it assumes that format. It exits 1 when an entry failed and says which: read its last lines.
2. **Reference (when the folder holds one: ALWAYS, it drives the edit)**: `$PY ref_analyze.py "$REF" --music src/music.flac` (`--music` once the song is chosen), then read `ref_notes.md` and every image in `ref_sheets/` (reference-style.md, "Reading the reference"); keep the notes in the project. The `adopt` block of `ref_notes.json` (cut lattice, how many frames its cuts and kill flashes come before the drum, cut gaps, transitions, slow motion, intro, ending, kills per second) is what the drafter follows in step 5: plan keys only for what the user said.
3. **Watch the clips and choose the kills**. `$PY peek.py c1 0 99999 60` shows a clip at one tile per second. First `$PY dupes.py` (in the project: the same footage in several files, as a full DVR recording and its trims or an identical `-seg1` copy, with the offset; `dupes.json`). Any game: `$PY kills_auto.py <game>` (profiles in `games/`: `valorant`, `cs2`, `generic`; another game: copy `generic.json` to `games/<game>.json` and set its rectangles with `--regions`) writes `kills.json` (with `hidden`, `headshot`, `no_shot`, `conf`), `rows_other.json` (rows dropped: teammates', your deaths) and review sheets `autokill_NN.jpg`. K is ALWAYS the shot that killed: the last shot with an ammo step before the feed row (which slides in 4 to 12 frames after it), never the first shot of a spray, never a flash without an ammo step while the counter is steady (death highlight, the row sliding in, an ability). Only `valorant` is measured on footage (26 clips): of the 66 real kills two accepted edits used, K exact in 62 and within 1 frame in 3 (one knife kill is +-3); 123 own rows kept, 116 teammates' rows and deaths dropped by colour; a row seen again is not a second kill. `cs2` comes from the game's HUD files and was never run on footage: run `--regions` on a frame with a kill first. `generic` finds the feed rows but keeps everyone's kills and picks the wrong shot in sprays (K exact 13 of 23): use it only to start a profile. Then `$PY kill_rank.py --seconds <length>`: every kill scored with its reasons (headshot, multi-kill run, clean shot, one-tap, flick, visibility), each kill once even across duplicate files, and the best set for the length; read `kill_rank_*.jpg`. The score agrees only moderately with what the user kept (held out on another accepted edit: 10 of its 25 kills in the top 25, random about 5): it orders the candidates, YOU choose by reading the stills and the user's words. Never build a take on a kill marked `hidden` (nothing visible at the aim), `no_shot` or not the player's. Valorant also has the banner tools for trimmed clips (`find_kills.py`, `kill_table.py`) and the kill-feed + ammo tools for raw recordings (reference-style.md, "Finding kills in raw 2-minute recordings"). After writing the timeline: `$PY kill_rank.py --check` must print no ERROR (hidden, not-yours, duplicate, wrong-shot, k-after-row; `gate.py` refuses delivery on them).
3b. **Check K on the pictures**: `$PY kverify.py` re-measures every K (the ammo-counter step in any digit colour, the muzzle-flash start, a replay cut) and prints per kill verified / CORRECT (the sure K) / SUSPECT / not measurable, with `kv_NN.jpg` sheets (K-3 to K+3); it takes `timeline.py` (refused without `SYNC = 2`), `plan.json`, `kills.json [--ids]` or `clip@K`, and `--game NAME` (the game's profile in `games/`, default `valorant`; the gate takes it from `GAME` in timeline.py, the `"game"` that `kills_auto.py` writes into `kills.json`, or `$KVERIFY_GAME`; never put it in clips.json, `ingest.py` reads every key there as a clip). A K one frame off is 16.7 ms of desync, and a guessed K is off in 3 of 4 cases. `--update` writes the verdict into `kills.json` (`how` `ammo` / `flash` = verified; `ammo-loose` / `guess` = not; an old entry with no `how` counts as unverified until measured). It proves K is a shot's first frame, not that it is the shot that killed in a spray (`kill_rank.py` does that). Both drafters refuse a K that is unverified: no `kills.json`, no matching entry, a plan K different from the entry's, or `how` not `ammo` / `flash`; unless the plan entry says `"k_checked": true` (after reading the `kverify.py` sheets).
4. **Music**: `$PY music_tempo.py` (tempo with its half / double alternative and the evidence for each, candidate drops; it reads the tempo again in every 30 s window and in 10 s beat-phase windows and says `tempo steady?` / `beat phase steady?`; a WEAK fit is printed as a warning with the best fit and the drop table, and only a WEAK fit that is also not steady prints `NO TEMPO` and stops with exit 1), then `$PY music_grid.py BPM BEAT0 [T0 T1]` (never skip). It measures every drum attack with the skill's one attack definition, then: REFUSES a BPM that the strong attacks fit worse than another (it names the better one, prints no BEAT0, exit 1: run it again with that BPM), prints the BEAT0 with the alternatives when a grid shifted by an eighth or a sixteenth fits as well, corrects the tempo only from 60 s of track, and gives an honest verdict (median offset, share of hits beyond 8.3 ms, the worst hit). `constant grid NOT adequate` (a live drummer, swing, a tempo that wanders) means no kill, cut, bump or boom goes on a grid beat: each goes on its hit's own time (`$PY music_hits.py` writes `hits.json`: every hit with its attack time `t`, `r = hit(t)` and band). Use the BPM and BEAT0 it prints; a song that is not flac / wav / aiff was decoded once to `src/music.flac` by `ingest.py` (ffmpeg's seek is 8 to 40 ms off the sample in AAC / mp3), and every tool reads that. Fill in the music block at the top of `timeline.py` (`MUSIC`, `BPM`, `BEAT0`, `M0`, `R0`, `R1`, `FADE_OUT`, `CUTS_ON`, and what is tied to the song's structure: the `RISERS` beats, in the house style `SWEEP` and `PULSES`, in the reference style `LUMA_FADE`; choosing the section: edit-design.md "Music", valid for both styles). The example's segments are still in the file at this point, so the stars `music_pulses.py` puts on kills are theirs: ignore them until step 5. Then read the hits with `$PY music_pulses.py`, `$PY music_hits.py` and `$PY music_spec.py` (triangles on the measured attacks). Lyric words: reference-style.md.
5. **Write `timeline.py`**. Measure first how long each chosen kill's death takes: `$PY deathstrip.py ds.jpg c01@862 c04@303 ...` (1:1 crops K-8 to K+52 and the kill feed; `--fine` for every second frame up to K+30) and note per kill `upto` = frames from K until the body is down. Write `plan.json` with the plays in order (with `upto`, the drop kill `"bullet": true`, the pre-drop kills in `intro.kills`; model-edit.md says where each part of the song goes; the bullet time where the drums thin out is found by the drafter itself, `"auto_bullet"`) and let the drafter write a correct draft that explains every segment: house style `$PY draft_timeline.py plan.json` (edit-design.md, "Drafting the timeline"); reference style `$PY draft_ref_timeline.py plan.json` with `ref_notes.json` from step 2 (reference-style.md, "Drafting the entry list"). The reference-style draft follows model-edit.md by default (14-frame leads, deaths to `upto`, levels, blur-ins, bumps, booms, risers, the thin-out bullet time, `LOOK = "modelo"`). Every kill, bump, boom and riser end sits on a measured attack (9 decimals); every kills-mode cut on a lattice line with a SHOWN lead of 12 to 16 frames, a bass cut on a kick attack, the ending on beat lines. With a reference it follows the `adopt` block (precedence per trait: the plan's keys > the reference > the model edit) and prints `reference followed / not followed (why)` for each trait. It refuses, with the numbers: an unverified K (step 3b), a BPM whose grid drifts against the hits (it names the better one), and a plan that cannot fit. Read the explanation and the statistics it prints, compare them with model-edit.md section 9, then tweak by hand. Nothing of the example stays (its clips, frames, `SEGS` / `E`, `PULSES`, `RISERS`, `SWEEP`, `_T`, docstring are the author's): best moments on the drops, the plays the user named where they asked, kills as anchors on measured hits, `CUTS_ON` as chosen in the briefing (`"kills"` by default), `LOOK` from the user's words ("Edit options"). `$PY timeline.py` must pass: it asserts that every cut and shot sits on an exact frame and every take has a frame of its own, and runs `preflight.py` first, which lists every problem at once (`SYNC = 2`, the grid identities FPS / PER / FPB / MUSIC_T0 / N_FRAMES, one musical hit per kill shown on `vis(hit, HIT_LEAD)`, clips missing from `src/`, anchors, kills outside their segment or clip, a misspelled `CUTS_ON` or `LOOK` key, a song shorter than the edit, malformed `BUMPS` / `BOOMS` / `IMPACT` / `white`). Then `$PY music_pulses.py` must end without a FAIL (every kill, bass cut, bump and boom within 8.3 ms of a measured attack, exit 0; house style also "none" for kills on empty beats); `$PY deathstrip.py ds.jpg` (no arguments: every kill of the timeline) must show each body down on a green tile. Never run `ranges.py` or `prep.py` on the example's segments: they point at the author's clips and frames.
5b. **Preview while the heavy work runs**: `$PY preview.py ../<name>_previa.mp4` (half a minute horizontal, about a minute vertical; no store needed), then start step 6 in the background. Tell the user in one line where the preview is and that it is rough (no effects, slow motion choppy on purpose): it shows the order, the cuts, the kills on the beat, the words and the music. Do not wait for an answer; if they comment before the render, change the timeline then (only what they asked; `prep.py` builds only what is missing).
6. **Footage**: `$PY ranges.py && $PY prep.py ranges.json` (GPU, in the background), `$PY densify.py run 12 28`, reference style also `$PY posmap.py`, then `$PY check_store.py` (0 missing, no duplicates).
7. **Stills before video**: `$PY render.py N N+1 look.jpg` on each kill, transition, slow-motion frame, word, first and last second; read them (stills can start while `prep.py` still runs; reference style: after one `$PY posmap.py`). Reference style: enlarged crops of your stills beside the same crops of the reference BEFORE the first full render (verification.md).
8. **Sound**: `$PY audio.py` finds each gunshot's onset in the clip's own sound to the sample and puts it on its musical hit (`s["hits"]`), with no median override. Every sound sits on a musical beat, the blur-in whooshes on the cut's musical beat (`s["m0"]`) like the house whooshes. Reference style: it prints how each shot was placed (measured, donor = another kill's shot via `shot_from`, clip offset, edit median, none): only measured and donor are verified, the other two are printed in ms and the gate warns; house style: it stops on a kill it cannot measure (`kill_lags.py` shows the strip) and on a typed `lag` that disagrees with the measurement by more than 0.25 frame. The mix is exactly as long as the picture, and `mix peak` must be below 1.0; a kill over voice chat gets `mute=True`. Read `audio_report.json` before the render.
9. **Render** in the background: `bash run.sh master.mp4` (12 to 16 min).
10. **Verify**: `$PY check.py master.mp4 --sheets` prints per kill the MEASURED flash frame (the difference image of source frames K-1 to K matched in the master, searched on the shot frame +-2): `ok` = on the shot frame and absent on -1, `EARLY` / `LATE` = another frame, `not measurable` is never a pass. Read `sync_*.jpg` (tile +0 is the shot frame) and `pv_*.jpg`; `$PY syncaudit.py master.mp4` is the independent audit of the file (pts, sound against the song, cuts, flashes, accents, words; every item it cannot measure is listed as a WARN, never a pass; verification.md); compare the numbers with model-edit.md section 9. Fix and repeat (verification.md).
11. **Deliver**: `bash deliver.sh master.mp4 "../<name>_vN.mp4"`, never over an earlier version. It runs `gate.py` first and refuses while an ERROR is left (verification.md, "The delivery gate"): fix the cause, never work around the gate. After the upload copy and `peakguard.py` it runs `gate.py --sync-only` on the copy that leaves (container, sound against the song, cut / shot / flash / accent / word frames); on an ERROR it renames the copy `*.rejected.mp4` and fails. A problem the user explicitly accepts is waived per code only (`ACCEPT=<code> bash deliver.sh ...`), written to LEIAME.md; say it in the report. `av-offset`, `av-drift`, `frame-count`, `cut-frame`, `pts-gap` and `timeline-old` can never be waived. Run `check.py` on the upload copy.
12. **Save what was learned, outside the skill.** During a video NEVER edit the installed skill (`~/.claude/skills/editing-gameplay-montages`): it is a copy of the public repository, the next install replaces it, and the user's projects must not leak into it. Write what was learned in the project's `LEIAME.md` (the project's history, and a section "Lições para a skill" with each lesson in generic words: no folder names, paths, clip names, song titles or delivered file names) and in the session's memory, before the final report. The skill itself changes only when the user asks for it ("atualiza a skill", "manda pro GitHub"): then apply those lessons in a clone of the repository (the one `install.sh` / `install.ps1` ran from), test them, commit, push (or open a pull request), and run the installer again.

## Rules, and what happened without them

| Rule | Without it |
|---|---|
| Read frames by index (`clipio`), never `-ss` plus an `fps` filter | 1 frame in 3 duplicated or dropped: "travado", "quedas de fps" |
| Refine the beat grid with `music_grid.py` and keep its refusal and verdict | an early provisional grid was 38 ms early (the old tools were also 39 to 116 ms off on trap, funk and lo-fi), kills beside the hits; a BPM 0.7 % off drifted 4.6 ms per beat against the hits |
| The picture event sits on its exact frame (`vis()`), the gunshot on the musical hit to the sample, both from the measured attack (never the grid time) | kills and cuts up to 57 ms off their drum, a gunshot placed 1.3 frames off its own onset, "problemas de sincronizacao" |
| Any speed other than 1 comes from interpolated sub-frames, shutter-integrated | "slow motion ta bem travadinho" |
| Sub-frames are built through `rifeutil.Tween` (the bundled scripts do); a store built without it, as the first stores of both examples were, needs `fixends.py` | slow motion stalled an eighth of a frame at every real frame |
| Recording duplicates are rebuilt before interpolating (`prep.py`, `repair.py`) | slow motion freezes on them |
| Real time for 0.2 to 0.3 beat after the shot before slowing (`tail()`, `post()`) | slow motion sat on the flash and magnified artifacts |
| A slow lead-in reaches the kill at real speed: one anchor a frame before it (reference-style `L` entries add it; the house example's bullet time predates the rule and arrives at 0.53x) | the flash appeared 2 frames after the beat |
| Judge a reference's look on enlarged crops, not contact-sheet tiles | letters drawn 90 % opaque when the reference's were see-through |
| Rank kills by reading stills; camera travel is only a hint | the biggest "flick" was the kill the user called ugly |
| One word per cue on its sung ATTACK (`lyrics_sync.py`, checked by `lyrics_audit.py`); only lyric lines confirmed against a lyrics page | phrases appeared before they were sung, words up to 157 ms late on a delivered edit; speech recognition gets half a trap verse wrong and its word times put whole lines one word early |
| AAC with `-aac_pns 0 -aac_tns 0 -aac_is 0` after the limiter; check the decoded peak | three deliveries clipped at +3 dBFS |
| Sound files keep headroom until the limiter | a 16-bit mix flattened 0.05 % of the house example's samples before the limiter saw them |
| Stills first; long jobs in the background with short status notes | flaws found only after a 12-minute render; the user interrupted a long blocking wait |
| A GPU job that slows down: look for the user's game before touching the code (commands: pipeline.md, "Handling jobs on the user's PC") | an hour of interpolation at an eighth of the speed while CS2 ran |
| Before overwriting a file of this skill, read its current version: another session may have updated it. A project made with an older copy of the scripts must take ALL of `scripts/*.*` again (rifeutil.py, preflight.py and the scripts that import them change together) | a newer `rifeutil.py` (with `finish()`) was replaced by an older copy and two scripts broke |

## Reporting to the user

Reply in the user's language (typically Brazilian Portuguese, informal). Lead with the file path and its state. Say what changed, give the measured facts, and state plainly that you cannot watch or hear it, so feel, intensity and mix are theirs to judge. End by saying they can describe in their own words anything to change. No questions after the briefing: decide, and never need a confirmation, by not deleting or overwriting anything of theirs. Answer a message that arrives mid-run in the next line you write.

## Files

| File | Read it when |
|---|---|
| model-edit.md | before writing or tuning any timeline in the default style: the best edit's patterns, fitted to the user's song; after a render, its section 9 to compare against |
| pipeline.md | setting up, running or modifying the scripts; timings; what to re-run after a change |
| edit-design.md | the house ("janela") style, only on request: sequence, beats, speed ramps, effect values, transitions, sound; its "Music" section serves both styles |
| reference-style.md | the DEFAULT style: drafting its timeline, copying a reference video, vertical frame, lyric words, cover image; raw recordings |
| verification.md | judging a render; thresholds; reading the sheets; the delivery gate and the sync audit (`syncaudit.py`, its stages and codes); the report |
| feedback.md | the user commented on a delivered version ("travado", "kill fora do beat", "muito escuro", "tira essa kill"...): what to check, what to change, what to re-run |
| pitfalls.md | something looks or measures wrong (symptom, cause, fix), including shell traps on Windows |
| tools-research.md | the user asks about other editors, MCPs or skills |
| scripts/, models/ | the shared pipeline (plus the house style's own render, sound and check) and the interpolation network |
| scripts/refstyle/ | files that replace or extend `scripts/` for the default style; always copied over `scripts/` unless the house style was asked for (README.md inside) |
