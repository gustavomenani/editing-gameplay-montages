# scripts/refstyle

Files for the reference style (../../reference-style.md). Copy the standard set first, then these over it
(the whole setup with the venv: ../../pipeline.md, "Setup"):

```bash
cp "$SK"/scripts/*.* . && cp -r "$SK"/scripts/games "$SK"/models . && cp "$SK"/scripts/refstyle/*.* . && cp timeline_ref_example.py timeline.py
```

Replace the standard file of the same name:

| File | Difference |
|---|---|
| `render.py` | horizontal 1920x1080 full frame, or vertical 1080x1920 (`FRAME = "vertical"` in the timeline: the gameplay in a window over a blurred backdrop): blur-in cuts, streaks, colour split, lyric words, luma fade; the model edit's accents when the timeline sets them (`IMPACT` radial burst / split / rays / inverted level-3 frame, `ACC`, `BUMPS`, `LUMA_IN`, the segment key `white`); reads `posmap.json` |
| `audio.py` | one gunshot per kill at natural pitch on the beat; optional `KILL_THUMP`, `BOOMS`, `WHOOSH_BLUR`, `GAME_LEVEL`, `FADE_IN`, `shot_from`; mix written at `HEADROOM` (default 0.8), `master_chain()` gives the level back |
| `check.py` | 1920x1080 or 1080x1920 (from `FRAME`; it refuses a video of the other size); motion measured in two bands above and below the words |
| `clipio.py` | full-width frames; frame/time conversion through the real time table (recordings with gaps) |
| `densify.py` | 1920 px scale; only footage shown near real time (0.75 to 2.2x) |
| `run.sh`, `deliver.sh` | the sound chain from `audio.master_chain()` (`volume = 1.18 / HEADROOM`: 1.475 at 0.8); upload copy up to 22 Mbps |

Added:

| File | What it does |
|---|---|
| `timeline_ref_example.py` | the worked example's edit and the drafter's template: entry list `E`, `pre()` / `post()` / `fall()` / `flash()`, `TEXT`, `LUMA_FADE`, the empty `# >>> draft:fx` block for the model edit's accents and sound. Its lyric cues are not published (song lyrics); a project gets its own from `lyrics_align.py` |
| `frame.py` | the frame geometry from `FRAME` in timeline.py (`"horizontal"` default, `"vertical"`): sizes, gameplay window, word caps; read by render.py, textfx.py, check.py, cover.py, cover_plates.py. A misspelled `FRAME` stops with a message |
| `textfx.py`, `text_test.py` | lyric words: Impact (Windows font folder, or `IMPACT_FONT`), random letter reveal, translucent tinted fill, ink centred on the frame (vertical: exact middle of 1080x1920, caps 0.62 of the horizontal ones); `$PY text_test.py` shows the first cue of every style on a flat background, `text_test.py vertical` the vertical words |
| `detect_kills.py`, `kill_review.py` | `$PY detect_kills.py <clips folder> detect` scans raw recordings for the player's kills on the kill feed; `$PY kill_review.py <clips folder> detect review` writes review sheets and `review/index.json` (copy to `detections.json`) |
| `mykills.py`, `strip.py`, `flick.py` | shot frame K from the ammo counter with galleries (`gal_NN.jpg`: flash on tile `+0`, absent on `-1`): `$PY mykills.py` for every detection not in `BAD`, `$PY mykills.py 12,13` for those ids only (it numbers the sheets from `gal_01.jpg` again, so it overwrites the sheets of a full run, and it rewrites `kills.json`); per-frame strips to set K by hand; camera travel and earlier shots per kill. The K typed into the timeline entry is the authoritative one: `kills.json` is a regenerated record, read by `flick.py` |
| `introcand.py` | candidate shots as sheets: `$PY introcand.py 1 c1:6600:6800:10` (zoom 1: the HUD-hiding crop it was written for is what the user rejected) |
| `transcribe.py`, `lyrics_lines.py`, `cue_onsets.py`, `lyrics_align.py` | recognised words (own venv with faster-whisper; `--lang`, `--prompt`, `--lyrics`); the typed `lyrics.txt` aligned to the recognition -> `lines.json`; plain vocal onsets per word; one cue per word on its onset |
| `cover_plates.py`, `cover.py` | cover image: clean frames of the edit, title only, centred |
| `ref_analyze.py`, `refmeasure.py` | measure a reference edit: layout, beat grid, cuts with offsets and note values, transition kinds, speed, words, colour, ending; writes `ref_notes.md` / `.json` and `ref_sheets/` with SUGGESTED SETTINGS (`$PY ref_analyze.py REF.mp4 [--music src/music.flac]`) |
| `draft_ref_timeline.py` | a first-draft `timeline.py` from `plan.json` (kills in order with their `upto`, song numbers, `cuts_on`, `lead_frames`, `frame`, intro kills, bullets, `look`, optional `ref_notes.json`) with the model edit's patterns (../../model-edit.md): a cut 14 frames before each take's first shot, kills on measured hits, every death shown, bullet times on the drop and on `"hit"` kills, levels, blur-ins, bumps, booms, risers, calm last take with the luma fade; prints statistics to compare with the model; refuses with numbers (reference-style.md, "Drafting the entry list") |

Values that belong to the worked example's project and must be replaced:

| File | What |
|---|---|
| the timeline | the whole music block (`MUSIC` with its extension, `BPM`, `BEAT0`, `M0`, `R0`, `R1`, `FADE_OUT`, `LUMA_FADE`, the `RISERS` beats), the entry list `E`, the intro words `_T` and the `-1.5` beat that separates them from lyric words, the `draft:fx` block: `draft_ref_timeline.py` writes all of it. The example's `CUT = 0.15` is 4 frames at 130 BPM; a drafted timeline writes `LEAD_FRAMES` and `CUT = LEAD_FRAMES / F`, and `upto` on every take so `fall()` replaces `post()`; by hand do the same. Keep the `# >>> draft:` markers when you edit the example |
| `detect_kills.py` | `SKIP_PREFIX` (file names to leave out); it scans `.mp4` only |
| `mykills.py` | `BAD` (rejected detections) |
| `flick.py` | `KFIX` (hand-set shot frames: detection id -> K) and `SKIP` (detection ids to leave out): they act in `flick.py` only, `mykills.py` has neither |
| `lyrics_align.py` | `LINES` is optional (leave it empty to use `lines.json` from `lyrics_lines.py`), `OVERRIDE`, `DROP`, `RED` (beat ranges whose words are red; default: only the intro, before beat -0.5: the worked example also had its breakdown, beats 27.5 to 31.5) |
| `transcribe.py` | `LANG` (language code) and `PROMPT`, or `--lang` / `--prompt` on the command line |
| `cover_plates.py` | the three beats |

Standard tools not used in this style: `find_kills.py`, `kill_table.py`, `kill_lags.py` (banner method on
the 1344 px crop; `kill_table.py` would overwrite `kills.json` with another layout). `peek.py` shows the whole
frame here.
