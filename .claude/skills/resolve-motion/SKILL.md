---
name: resolve-motion
description: Motion graphics for the DaVinci Resolve MCP — lower thirds, title cards, kinetic text, animated captions/subtitles, number counters, end cards and three.js 3D scenes (particles, 3D titles, shapes) rendered with Remotion and dropped into Resolve. Apply when asked to make a title, lower third, caption burn, animated text, intro/outro, 3D sting or any generated graphic for the timeline.
---

# Resolve Motion Graphics (Remotion + Three.js)

Tool: `motion_graphics` (live Python server). Renderer: `motion-graphics/render.mjs`
(Remotion project with the templates in `motion-graphics/src/templates/`,
metadata and default props in `motion-graphics/templates.json`).

## Workflow
1. `motion_graphics(action="status")` — if `available` is false, tell the user to run
   `python install.py --motion` (optional extra, needs Node) or set
   `DAVINCI_RESOLVE_MCP_MOTION_PROJECT` to their own Remotion project.
2. `list_templates` — read `defaultProps`; only pass the props you change.
3. Preview cheaply with `still` (one PNG frame, `scale: 0.5`) before a full render
   when the look matters; read the PNG if your client can show images.
4. `render` with `import_to_resolve: true`; overlays go on a track above the
   footage (`track_index: 2`) and usually `at_playhead: true`.
5. Long renders return `job_id` → poll `job_status` (it performs the pending import).

## Choosing a template
| Need | Template | Notes |
|---|---|---|
| Name/role strap | `LowerThird` | alpha; `position: left/right` |
| Section/chapter title | `TitleCard` | full frame |
| Quote / hook / lyric | `KineticText` | alpha; wrap words in `*asterisks*` to highlight |
| Burned-in subtitles | `Captions` | alpha; `transcript_from: {clip_name}` runs local_ai Whisper first, or `srt_path` |
| Stat / number | `Counter` | alpha; `from`, `to`, `prefix`, `suffix`, `decimals` |
| Outro | `EndCard` | full frame |
| 3D backdrop / transition | `Particles3D` | `transparentBackground: true` for alpha |
| 3D title / logo sting | `Text3D`, `Shapes3D` | any system font; shapes: torusKnot, icosahedron, torus, box, sphere |

All templates take `durationSeconds`, `fps`, `width`, `height` (match the timeline:
e.g. 1080x1920 for vertical). Colours are CSS colours.

## Rules
- Rendered files are new media in `motion-graphics/out/` (or `out_path`); never
  write over source media.
- Match the timeline's resolution and frame rate in props before rendering.
- Transparent templates render ProRes 4444 `.mov`; do not force `h264` on them
  (no alpha channel).
