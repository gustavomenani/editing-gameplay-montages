# Edit options: what the user says → what to set

Every look option lives in one `LOOK` value in `timeline.py`, read by both renderers through `scripts/look.py`. `$PY look.py` prints
the table with the range of every key; `preflight.py` names a misspelled key ("vinheta" → did you mean "vignette"?) and `look.py`'s
`get()` clamps a value that would break a user rule and prints the clamp.

```python
LOOK = "intensa"                                            # a preset: suave, padrao, intensa, maxima, modelo
LOOK = {"vignette": 1.6, "shake": 0}                        # single options (multipliers of the default look)
LOOK = {"preset": "intensa", "grade": "cool", "shake": 0.3} # a preset, then single options on top of it
```

Numbers multiply the worked example's look: 1 = as there, 0 = off, 2 = strong. Above 1 the scale is not linear for vignette,
saturation, contrast and grain (2 reads as "clearly strong", not as a 15 % nudge). `exposure` is a multiplier of the light
(0.5 to 1.5); `wide_glow` is an amount (0 = none); `intro_vignette` follows `vignette` unless set. `"modelo"` is the model edit's look
and the reference drafter's default; `"padrao"` (or no `LOOK`) is the worked example's own look; the house style uses `"padrao"`.

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
| "estilo janela", "estilo house", "transições que mexem os dois clipes" | the house style (SKILL.md; edit-design.md): vertical only, shows two thirds of the game width, no words, no cover. Only on such a request |

## What is not built

A kill counter, a sound pack, a 3D transition, a text other than the lyrics, a soundtrack change mid-video, a watermark or a subtitle:
say so plainly and name the closest option that exists. Never promise one of them for a later version.

## Where the value must end up

`LOOK` is read by `render.py` (house) and `scripts/refstyle/render.py` (default) and validated by `preflight.py`. After changing it:
stills (`$PY render.py N N+1 look.jpg`) and then a render; the store does not change, so `run.sh` is the only heavy step.
