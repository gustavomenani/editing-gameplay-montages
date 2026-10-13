# Other tools, MCPs and skills (researched October 2026)

The user asked for "um metodo melhor que o ffmpeg ... ou mcps ou skills que va elevar nosso nivel de
edicao". Nothing below was installed or tested; the notes come from the projects' own pages. Re-check
before relying on them: this field moves fast.

## Conclusion

ffmpeg is not the limit: it only decodes and encodes, the effects are our own code. What limits the
work is that the editor cannot watch or hear, the user has no editable project, and every change is a
render. The recommendation given was to keep and improve the own pipeline, and the user went on with it:

- everything already runs on the user's PC (GTX 1650: fine for RIFE, marginal for Resolve or After Effects);
- what the user asked for (smoother, better synced, natural zooms) is motion blur and timing, both
  solved inside the pipeline since then.

## Options compared

| Path | Gain | Cost and risk |
|---|---|---|
| Improve the own pipeline | frame-blended motion blur, newer RIFE, better beat detection | free, works today. Done in the house example (blur and index-exact frames); the newer RIFE gained under 1 % |
| CapCut + draft generation (VectCutAPI, capcut-mcp) | Claude builds the project, the user opens it, sees it live, adjusts, exports | unofficial; depends on the CapCut version; export is manual; some effects are paid. The biggest change for a TikTok workflow and the likeliest to break. Not tried |
| DaVinci Resolve Free + MCP bridge | professional timeline, Fusion effects, real colour | the free version blocks external scripting; the bridge that claims to work with it had 1 commit and 0 stars; heavy for this GPU |
| Remotion + its agent skills | animated text, kill counters, intros, browser preview | poor at speed-ramping gameplay; useful as a layer on top |
| After Effects + MCP | the scene's standard (Twixtor, RSMB) | paid and heavy; not recommended |

## Notes

- **Motion blur**: the community tools (blur, smoothie-rs) interpolate to about 5x the frame rate and
  blend back to 60. The pipeline now does the same thing itself, per output frame and without
  blurring the HUD differently from the scene.
- **Beat tracking**: Beat This! (MIT, runs on CPU) returns beats and downbeats. Not adopted: measuring
  onsets against a comb grid (`music_grid.py`) placed the grid within 1 ms (median) on the track used.
- **Sound**: whooshes and risers are synthesised. Impact sounds from a sound-effects pack would add
  more, but need the user's ear to approve.
- **Skills that would not help**: video-use (cuts by speech transcript, needs a paid ElevenLabs key),
  the ecliptic-ai beat-sync skill and the ffmpeg MCP servers do less than this pipeline. A registry
  search for video-editing skills found only generic ffmpeg guides from unknown authors.
- **Kill detection**: no ready tool for Valorant, only datasets; the methods here remain the way (trimmed clips:
  the kill banner, `find_kills.py`; raw recordings: kill feed and ammo counter, reference-style.md).
- Nothing in the user's PC was an editor at the time (no Resolve, CapCut or Adobe); Node and Bun were installed.

## Links

- CapCut: https://github.com/sun-guannan/VectCutAPI , https://github.com/yeroshalmiariel-ai/capcut-mcp
- Resolve: https://github.com/lastpack/claude-resolve-mcp , https://github.com/hiteshK03/davinci-resolve-mcp , https://www.mdskills.ai/mcp-servers/davinci-resolve-mcp
- Motion blur: https://github.com/f0e/blur , https://github.com/couleur-tweak-tips/smoothie-rs
- RIFE: https://github.com/TNTwise/rife-ncnn-vulkan , https://github.com/styler00dollar/VapourSynth-RIFE-ncnn-Vulkan
- Remotion: https://www.remotion.dev/docs/ai/skills , https://www.remotion.dev/docs/videos/accelerated-video
- HyperFrames (HeyGen): https://developers.heygen.com/hyperframes-overview
- Beat This!: https://github.com/CPJKU/beat_this
- After Effects MCP: https://github.com/kumoproductions/mcp-aftereffects
- video-use: https://github.com/browser-use/video-use
- Beat-sync skill: https://skills.sh/ecliptic-ai/skills/beat-sync-video-editing
- Surveys: https://www.opus.pro/blog/best-mcp-servers-for-video , https://valmera.io/mcp/video-editing-mcp-servers
- Valorant kill-feed dataset: https://universe.roboflow.com/saltarcs/valorant-killfeed-detection-4lvoa
