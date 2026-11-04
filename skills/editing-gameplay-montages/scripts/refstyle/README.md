# scripts/refstyle

Files for the reference style (../../reference-style.md). Copy the standard set first, then these over it
(the whole setup with the venv: ../../pipeline.md, "Setup"):

```bash
cp "$SK"/scripts/*.* . && cp -r "$SK"/scripts/games "$SK"/models . && cp "$SK"/scripts/refstyle/*.* . && ([ -e timeline.py ] || cp timeline_ref_example.py timeline.py)
```

The `[ -e timeline.py ] ||` guard matters: this is also the line an existing project runs to take a newer copy of the scripts, and an
unconditional `cp` would replace the user's edit.

Replace the standard file of the same name:

| File | Difference |
|---|---|
| `render.py` | horizontal 1920x1080 full frame, or vertical 1080x1920 (`FRAME = "vertical"` in the timeline: the gameplay in a window over a blurred backdrop): blur-in cuts, streaks, colour split, lyric words, luma fade; the model edit's accents when the timeline sets them (`IMPACT` radial burst / split / rays / inverted level-3 frame, `ACC`, `BUMPS`, `LUMA_IN`, the segment key `white`); reads `posmap.json`. Refuses a timeline without `SYNC = 2`; every cut and shot is an exact frame (`take_of(n)`, `nearest_frame`) and every accent of a shot (punch, shake, exposure pop, fringe, `IMPACT`, the backdrop pulse) starts and peaks on the shot frame; the frames next to the shot are read with no shutter blend, so K is whole on its frame and absent on the frame before |
| `audio.py` | one gunshot per kill at natural pitch on its musical hit (`s["hits"]`), onset measured per kill to the sample (no median override), causal high-pass, mix exactly as long as the picture, blur-in whooshes on the cut's musical beat (`s["m0"]`); optional `KILL_THUMP`, `BOOMS`, `WHOOSH_BLUR`, `GAME_LEVEL`, `FADE_IN`, `shot_from`; mix written at `HEADROOM` (default 0.8), `master_chain()` gives the level back (`alimiter ... latency=1`); refuses a timeline without `SYNC = 2`; writes `audio_report.json` |
| `check.py` | 1920x1080 or 1080x1920 (from `FRAME`; it refuses a video of the other size); motion measured in two bands above and below the words; the MEASURED flash frame of every kill against the shot frame (`ok` / `EARLY` / `LATE` / `spread` / `not measurable`); refuses a timeline without `SYNC = 2` |
| `clipio.py` | full-width frames; frame/time conversion through the real time table (recordings with gaps) |
| `densify.py` | 1920 px scale; only footage shown near real time (0.75 to 2.2x) |
| `run.sh`, `deliver.sh` | the sound chain from `audio.master_chain()` (`volume = 1.18 / HEADROOM`: 1.475 at 0.8, limiter with `latency=1`); `run.sh` gives each part its exact `duration` in the concat list and checks the joined video's pts (`ff.py pts`); `deliver.sh`: upload copy up to 22 Mbps, then `peakguard.py`, then `gate.py --sync-only` on the copy (an ERROR renames it `*.rejected.mp4`) |

Added:

| File | What it does |
|---|---|
| `timeline_ref_example.py` | the worked example's edit and the drafter's template: the SYNC 2 block (`SYNC = 2`, `hit()`, `frame_beat()`, `nearest_frame()`, `vis()`, `take_of()`, `CUT_LEAD` / `HIT_LEAD` in the `draft:cut` block), entry list `E` in musical beats, `pre()` / `post()` / `fall()` / `flash()`, `TEXT`, `LUMA_FADE`, the empty `# >>> draft:fx` block for the model edit's accents and sound. Its lyric cues are not published (song lyrics); a project gets its own from `lyrics_sync.py` |
| `frame.py` | the frame geometry from `FRAME` in timeline.py (`"horizontal"` is only the CODE fallback when a hand-written timeline omits FRAME; `draft_ref_timeline.py` writes `"vertical"`, which is the documented default): sizes, gameplay window, word sizes (`WORD_CAP_RED` 226 / `WORD_CAP` 202 px at 1080p, `WORD_MAXW` 70 % of the width, `CAP_K` 0.60 in vertical); read by render.py, textfx.py, check.py, cover.py, cover_plates.py, preview.py. A misspelled `FRAME` stops with a message |
| `textfx.py`, `text_test.py` | lyric words: Impact (Windows font folder, or `IMPACT_FONT`), random letter reveal (the first letter on `nearest_frame(cue) - HIT_LEAD`, every letter on `nearest_frame(cue)`), translucent tinted fill, soft shadow, ink centred on the frame (vertical: exact middle of 1080x1920, caps 0.60 of the horizontal ones), the word steps back while a kill plays until the body is down (`duck`, `duck_death`, `duck_max`); `STYLE_OVERRIDES` in timeline.py changes a style; `$PY text_test.py` shows the first cue of every style on a flat background and prints cap, share of height and width, centre offset and the letter-reveal check, `text_test.py vertical` the vertical words |
| `detect_kills.py`, `kill_review.py` | `$PY detect_kills.py <clips folder> detect` scans raw recordings for the player's kills on the kill feed (a decode that returns more than 2 frames fewer than the file's packet count is retried in software; still short, the file is reported FAILED, no json is written and the exit status is 1); `$PY kill_review.py <clips folder> detect review` writes review sheets and `review/index.json` (copy to `detections.json`) |
| `mykills.py`, `strip.py`, `flick.py` | shot frame K from the ammo counter (any digit colour: the same detector as `kverify.py`) with galleries (`gal_NN.jpg`: flash on tile `+0`, absent on `-1`): `$PY mykills.py` for every detection not in `BAD`, `$PY mykills.py 12,13` for those ids only (it numbers the sheets from `gal_01.jpg` again, so it overwrites the sheets of a full run, and it rewrites `kills.json`: every entry carries `how`, `conf` and `verified`; `ammo` / `flash` are verified, `ammo-loose` / `guess` are not, and the guess fallback is feed - 7; an old entry with no `how` becomes `guess` / `ammo-loose`, unverified, until measured, so a partial run never marks unmeasured kills verified); per-frame strips to set K by hand; camera travel and earlier shots per kill. The K typed into the timeline entry is the authoritative one: `kills.json` is a regenerated record, read by `flick.py`. `kverify.py` (in `scripts/`) re-measures K on the pictures |
| `introcand.py` | candidate shots as sheets: `$PY introcand.py 1 c1:6600:6800:10` (zoom 1: the HUD-hiding crop it was written for is what the user rejected) |
| `lyrics_sync.py` | the lyric words in one command from `lyrics.txt` (the confirmed words of the section; format in `lyrics_words.py`): `lyrics_stem.py` (demucs on the section, sample-exact cut, at least 9 s separated) -> `lyrics_ctc_align.py` (two CTC models, exact 20.000 ms stride, `--shifts` 8 runs each, median) -> `cues_from_alignment.py` (each word on the sung attack measured by `lyrics_attack.py`, CTC as the prior; flags in `lyrics/cue_audit.json`) -> `lyric_cues.json`, `lyric_sync_sheet.py` (`lyrics/sync_N.jpg`, and with `--zoom flagged\|all\|WORD,WORD` one zoom panel per word) and `lyrics_audit.py` (every cue against the measured attack in ms; exit 1 beyond 25 ms with no flag). The first two run in the separation venv (`requirements_sep.txt`, ../../pipeline.md "Setup"); `lyrics_attack.py` is imported by the cue, audit and sheet scripts and must be copied with them; `--stem-only`, `--t0` / `--t1`, `--models mms`, `--red=A:B`, `--last-end`, `--adv` (default 0), `--shifts`. Refuses a `MUSIC` that is not lossless and a timeline without `SYNC = 2` |
| `transcribe.py` | faster-whisper to READ the words of a section (own venv; best on `lyrics/vocals.wav` with `--offset`; `--t0 --t1 --lang --prompt`), never for timing |
| `cover_plates.py`, `cover.py` | cover image: clean frames of the edit, title only, centred |
| `ref_analyze.py`, `refmeasure.py` | measure a reference edit: layout, every cut on the lattice of its own grid (step, offset in frames, gaps in steps), the frames its cuts and kill flashes come before the drum attack, its kills from the kill feed, transition kinds, speed, words, colour, ending; writes `ref_notes.md` / `.json` (with the `adopt` block the drafter follows) and `ref_sheets/` with SUGGESTED SETTINGS (`$PY ref_analyze.py REF.mp4 [--music src/music.flac]`) |
| `draft_ref_timeline.py` | a first-draft `timeline.py` from `plan.json` (kills in order with their `upto`, song numbers, `cuts_on`, `lead_frames`, `cut_lead_frames` / `hit_lead_frames`, `hit_grid`, `frame`, intro kills, bullets, `look`, optional `ref_notes.json`) with the model edit's patterns (../../model-edit.md): every kill, bump, boom and riser end on a measured attack, a cut SHOWN 12 to 16 frames before each take's first shot on a lattice line, every death shown, bullet times on the drop and on `"hit"` kills, levels, blur-ins, bumps, booms, risers, calm last take with the luma fade; follows the reference's `adopt` block (plan > reference > model) and prints `reference followed / not followed`; prints statistics to compare with the model; refuses with numbers, an unverified K and a drifting BPM included (reference-style.md, "Drafting the entry list") |

Values that belong to the worked example's project and must be replaced:

| File | What |
|---|---|
| the timeline | the whole music block (`MUSIC` with its extension, `BPM`, `BEAT0`, `M0`, `R0`, `R1`, `FADE_OUT`, `LUMA_FADE`, the `RISERS` beats), the entry list `E` (its beats are not measured hits of your song), the intro words `_T` and the `-1.5` beat that separates them from lyric words, the `draft:fx` block: `draft_ref_timeline.py` writes all of it. The example's `CUT = 0.15` is 4 frames at 130 BPM; a drafted timeline writes `LEAD_FRAMES`, `CUT = LEAD_FRAMES / F`, `CUT_LEAD` and `HIT_LEAD`, and `upto` on every take so `fall()` replaces `post()`; by hand do the same. Keep the `# >>> draft:` markers when you edit the example |
| `detect_kills.py` | `SKIP_PREFIX` (file names to leave out); it scans `.mp4` only |
| `mykills.py` | `BAD` (rejected detections) |
| `flick.py` | `KFIX` (hand-set shot frames: detection id -> K) and `SKIP` (detection ids to leave out): they act in `flick.py` only, `mykills.py` has neither |
| `lyrics.txt` | the section's confirmed words: written per project, never copied from another one (`word@beat` pins, `sung=SHOWN`, `sung=-`) |
| `transcribe.py` | `LANG` (language code) and `PROMPT`, or `--lang` / `--prompt` on the command line |
| `cover_plates.py` | the three beats |

Standard tools not used in this style: `find_kills.py`, `kill_table.py`, `kill_lags.py` (banner method on
the 1344 px crop; `kill_table.py` would overwrite `kills.json` with another layout). `peek.py` shows the whole
frame here.
