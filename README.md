# DaVinci Resolve MCP Bridge

[![Version](https://img.shields.io/badge/version-4.14.4-blue.svg)](CHANGELOG.md)
[![Tools](https://img.shields.io/badge/MCP%20Tools-40%20(390%20full)-blue.svg)](#whats-what)
[![Advanced](https://img.shields.io/badge/Advanced%20(offline)-18%20tools-blueviolet.svg)](#whats-what)
[![Local AI](https://img.shields.io/badge/local%20AI-Whisper%20%2B%20vision-green.svg)](#local-ai-transcription-and-vision)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Control DaVinci Resolve from an AI assistant over MCP. Works with local models (LM Studio, Ollama) as well as Claude, Cursor and others. Includes a local Whisper + vision suite, so a local model can "hear" and "see" your footage without any cloud service.

> This is a personal fork of [samuelgursky/davinci-resolve-mcp](https://github.com/samuelgursky/davinci-resolve-mcp) (MIT).
> Changes in this fork: a `local_ai` tool (Whisper transcription + LM Studio/Ollama vision), a `motion_graphics` tool (Remotion + Three.js templates rendered straight into Resolve), the installer always installs the Resolve bridge, the installer can set up LM Studio directly, promo for the upstream's paid app is removed, and this README is shorter.

## Install

```bash
git clone https://github.com/Thefrizzy1/davinci-resolve-mcp-bridge.git
cd davinci-resolve-mcp-bridge
python install.py
```

The installer runs these steps in order:

1. Finds Resolve and asks two questions:
   - **Which edition do you have, Free or Studio?** Free means the server talks to Resolve only through the in-app bridge, never through external scripting (a Studio feature), and Studio-only actions are removed. See [Free vs Studio](#free-vs-studio).
   - **Which tools should the AI see?** *Everything*, or *Resolve only*. Resolve only drops `local_ai`, `motion_graphics` and `knowledge`, which keeps the tool list small for local models.
2. Creates a `venv/` with the dependencies.
3. **Always installs the in-app bridge** into Resolve's `Scripts/Utility` folders. You need it on the free edition. On Studio it does no harm.
4. Asks whether to install the **local AI extras** (faster-whisper). If you say yes, you pick a Whisper model and the installer **downloads it right away**, so the first transcription doesn't stall on a download.
5. Asks whether to install the **motion graphics extra** (Remotion + Three.js). The default answer is no, since many people already have their own setup.
6. Asks **"Install straight into LM Studio?"**, which writes `~/.lmstudio/mcp.json`. After that you can pick any other clients.
7. Checks the connection to Resolve (through the bridge on the free edition).

To run it without the prompts:

```bash
python install.py --lmstudio --edition free --toolset resolve   # free edition, Resolve tools only
python install.py --lmstudio --local-ai --whisper-model small    # LM Studio + Whisper, download "small"
python install.py --motion                       # add Remotion + Three.js motion graphics
python install.py --clients lmstudio,cursor      # several clients
python install.py --clients manual               # just print the JSON config
```

**Before connecting:**
- **Studio:** set Preferences ▸ General ▸ *External scripting using* to **Local**.
- **Free edition:** restart Resolve, open a project, then run **Workspace ▸ Scripts ▸ resolve_bridge**. The server finds the bridge automatically.

## Editing with a local model (the fast way)

The full tool list costs about 36,000 tokens before your model reads a word, which is more than most local models can hold. Pick **Lean editor** in the installer (or run `python install.py --toolset lean`). The model then sees only the `editor` and `motion_graphics` tools, about 1,000 tokens. Replies are compact text instead of pretty-printed JSON sent twice.

1. **Before you chat**, with your project open in Resolve (and the bridge running on the free edition):
   `venv\Scripts\python scripts\prep_footage.py` (on macOS/Linux: `venv/bin/python scripts/prep_footage.py`)
   This transcribes all speech clips once. Transcripts are cached, so later chats skip this step.
2. **In the chat**, the model works through five calls:

| Call | What comes back |
|---|---|
| `editor footage` | One line per clip: `c3 G02A1952.MP4 \| video \| 2:25.00 \| 50fps \| transcribed` |
| `editor transcribe` | Only needed if you skipped step 1. Repeat it until it says "All done". |
| `editor sentences` | `c3#4 20.00-23.55 The catch is it is slow on twelve gigabytes.` |
| `editor build` with `dry_run: true` | The timeline plan, the total length, and `PROBLEM:` lines to fix |
| `editor build` | Builds it: back to back on V1, covers on V2, music on A2, colours, markers, then checks for gaps |

The model only picks sentences (`"c3#4"`, or `"c3#4-6"` for several in a row) and says which part each starts. The server converts seconds to frames, adds 0.1 s before and 0.3 s after each sentence so no word is clipped, and places everything with no gaps.

A prompt that fits this workflow:

> Make a 55-65 s video from my footage with the editor tool. Story: Hook (the result, on my own RTX 3060) → Problem (everyone uses cloud tools, I wanted local) → Workflow (what I built) → Catch (slow on 12 GB) → Get it (free on GitHub). Each line must follow from the last with a "but" or "so". Open with 3-5 s of the fox story, then my best complete sentences (no false starts or crew talk). Add 4-6 covers of 2-5 s over the lines they match, never over my first sentence, plus the music. Colours: talking Blue, story Green, 3D Orange. Put a part on the first line of each section. Do a dry run first, fix any problems, then build, and tell me the sentences you chose.

## What's what

| Part | What it is | When you need it |
|---|---|---|
| `src/server.py` | **Main MCP server.** 40 grouped tools (project, media pool, timeline, color, Fusion, Fairlight, render, `editor`, `local_ai`, `motion_graphics`…) | Always. This is what your client runs. |
| `src/server.py --full` | Same server with one tool per Resolve API method (390 tools) | Only for power users. It's too many tools for small local models. |
| `local_ai` tool | Whisper transcription and frame descriptions, all on this machine | When your model can't read audio or images itself |
| `motion_graphics` tool + `motion-graphics/` | Remotion + Three.js templates (titles, lower thirds, captions, counters, 3D) rendered to ProRes 4444/H.264 and imported into Resolve | When you want generated graphics on the timeline (optional extra) |
| Resolve bridge (`scripts/install_resolve_bridge.py`) | A small script that runs *inside* Resolve and passes commands from the server over loopback (HMAC-signed) | Free edition (required) or when external scripting is off |
| `bin/davinci-resolve-advanced-mcp.mjs` | Optional Node server that edits `.drp/.drt/.drx` files offline, with Resolve closed | Offline project, timeline and grade file work |
| Control panel (`venv/bin/python -m src.control_panel`) | Local browser UI for inspecting Resolve state and analysis results | Optional |
| `docs/` | Install details, API coverage, workflow guides | Reference |

## Local AI: transcription and vision

```text
local_ai(action="status")
local_ai(action="transcribe", params={"clip_name": "A001_C003", "write_srt": true, "add_markers": true})
local_ai(action="describe",   params={"path": "/footage/interview.mov", "frames": 4})
local_ai(action="analyze",    params={"clip_name": "A001_C003"})   # both at once
```

- **Target:** use one of `path` (a file), `clip_name`, or `clip_id` (a Media Pool clip).
- **Transcribe:** uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) on CPU, or on CUDA if it's available. You get back text and timed segments. Options:
  - `write_srt` saves an `.srt` next to the media.
  - `import_srt` also brings that `.srt` into the Media Pool.
  - `add_markers` puts one marker per spoken line on the clip.
  - `translate: true` outputs English.
  - The installer downloads the model you choose and makes it the default. `base` and `small` are quick on a CPU. `medium`, `large-v3` and `turbo` are much more accurate but take minutes per clip without a GPU.
- **Long jobs run in the background.** Each call waits up to 25 seconds. If the work isn't finished by then, the call returns a `job_id` and a progress value, and `local_ai(action="job_status", params={"job_id": ...})` collects the result (it waits too). This means LM Studio's tool timeout never cuts a transcription off. Jobs run one at a time, so you can start several clips and collect them in order. `jobs` lists them all.
- **Describe:** pulls a few frames (with ffmpeg, or OpenCV as a fallback) and sends them to the vision model loaded in **LM Studio** (default `http://127.0.0.1:1234/v1`) or **Ollama**. Load a vision model first, for example Qwen2.5-VL, Gemma 3 or LLaVA. If you don't name a model, it picks a loaded vision model automatically.
- The built-in `media_analysis` pipeline also uses faster-whisper as its first-choice transcription backend.

| Env var | Default | Purpose |
|---|---|---|
| `DAVINCI_RESOLVE_MCP_WHISPER_MODEL` | `base` | Whisper model size |
| `DAVINCI_RESOLVE_MCP_WHISPER_DEVICE` | `auto` | `cpu` / `cuda` / `auto` |
| `DAVINCI_RESOLVE_MCP_VISION_URL` | `http://127.0.0.1:1234/v1` | Any OpenAI-compatible server (`http://127.0.0.1:11434/v1` for Ollama) |
| `DAVINCI_RESOLVE_MCP_VISION_MODEL` | auto | Which vision model to use |

Install the extras later with `venv/bin/pip install -r requirements-local-ai.txt` (on Windows, `venv\Scripts\pip`).

## Motion graphics: Remotion + Three.js

This is an optional extra. Install it with `python install.py --motion` (needs Node 18.18+). The AI picks a template, fills in the props, renders it, and drops the result onto your timeline:

```text
motion_graphics(action="list_templates")
motion_graphics(action="render", params={"template": "LowerThird",
    "props": {"name": "Ada Lovelace", "title": "Mathematician"},
    "import_to_resolve": true, "track_index": 2, "at_playhead": true})
motion_graphics(action="render", params={"template": "Captions",
    "transcript_from": {"clip_name": "A001_C003"}, "import_to_resolve": true})
motion_graphics(action="still", params={"template": "Text3D", "props": {"text": "SEASON 2"}})
```

| Template | What it is |
|---|---|
| `LowerThird` · `KineticText` · `Captions` · `Counter` | Overlays with an alpha channel (ProRes 4444) |
| `TitleCard` · `EndCard` | Full-frame cards |
| `Particles3D` · `Text3D` · `Shapes3D` | three.js scenes. Set `transparentBackground: true` for alpha. |

- Every template accepts `durationSeconds`, `fps`, `width` and `height`.
- `Captions` can take `segments`, an `srt_path`, or `transcript_from`. With `transcript_from` it runs `local_ai` Whisper first, then renders word-by-word subtitles.
- Long renders return a `job_id`. Poll it with `job_status`. The import onto the timeline happens when the render finishes.
- `studio` opens Remotion Studio so you can preview and tweak in the browser. You can also run `cd motion-graphics && npm run studio`.
- Claude Code and other shell tools can call the renderer directly:
  `node motion-graphics/render.mjs --template TitleCard --props '{"title":"Hi"}' --out title.mp4`
- **Already have your own Remotion project?** Skip the extra and set `DAVINCI_RESOLVE_MCP_MOTION_PROJECT=/path/to/project`. The tool will list and render your own compositions with your own Remotion version.
- To add a template, put a component in `motion-graphics/src/templates/`, register it in `src/Root.jsx`, and add an entry to `templates.json`.
- **Licence:** Remotion is free for individuals and companies of up to 3 people. Larger companies need a [Remotion company licence](https://www.remotion.dev/license). Three.js is MIT.

| Env var | Purpose |
|---|---|
| `DAVINCI_RESOLVE_MCP_MOTION_PROJECT` / `_ENTRY` | Use your own Remotion project and entry file |
| `DAVINCI_RESOLVE_MCP_MOTION_OUT` | Where renders go (default `Videos/Resolve MCP Motion` in your user folder) |
| `DAVINCI_RESOLVE_MCP_MOTION_BROWSER` | Path to a Chrome or Chromium binary, if Remotion's download is blocked |
| `DAVINCI_RESOLVE_MCP_MOTION_GL` | WebGL backend: `angle` (default on Mac and Windows), `swangle` (default on Linux), `egl` or `vulkan` |

## Codex

`python install.py --clients codex` writes `[mcp_servers.davinci-resolve]` into `~/.codex/config.toml` (`%USERPROFILE%\.codex\config.toml` on Windows). It includes `startup_timeout_sec = 120` and `tool_timeout_sec = 600`. Codex's defaults are 10 s and 60 s, which is too short for this server to start, especially on Windows. When a server doesn't start in time, Codex drops it silently and the tools just don't appear. On Windows the entry also passes `SYSTEMROOT`, `APPDATA` and similar variables, because Codex starts servers with a trimmed environment. Values you've set yourself in that table are kept. After installing, restart Codex and open a **new** chat.

## LM Studio tips

- The installer adds the server as `davinci-resolve` to `~/.lmstudio/mcp.json`. Any other servers already in that file stay as they are. Restart LM Studio after installing.
- Use a model that's good at tool calling (for example Qwen 2.5/3 or Llama 3.1+ instruct) with a context of 16k or more, because the tool list is large.
- You can run a text model for chat and a separate vision model for `local_ai describe` at the same time.

## Free vs Studio

| | Free (`--edition free`) | Studio (`--edition studio`) |
|---|---|---|
| Connection | In-app bridge only. External scripting is never tried. | External scripting, with the bridge as a fallback |
| Studio-only actions | Removed. The AI gets a clear error instead. | Available |
| `project_manager_cloud` (Blackmagic Cloud) | Hidden | Available |

The removed actions are the Neural Engine and Studio features: Resolve's own transcription and subtitle generation, scene-cut detection, magic mask, smart reframe, voice isolation, IntelliSearch, slate analysis, speech generation, motion deblur, audio classification, Dolby Vision analysis and stereo 3D clips.

They're blocked on purpose rather than just failing. On the free edition, such a call makes Resolve show an upgrade dialog, and **every** later call fails until you click it away. For transcription and subtitles, use `local_ai` instead.

The choice is saved in `~/.config/davinci-resolve-mcp/profile.json`. Re-run the installer to change it. You can also override it with the environment variables `DAVINCI_RESOLVE_MCP_EDITION=free|studio` and `DAVINCI_RESOLVE_MCP_TOOLSET=full|resolve`. To hide any other tools, set `DAVINCI_RESOLVE_MCP_DISABLED_TOOLS=a,b`.

## Free edition (in-app bridge)

Blackmagic only allows *external* scripting on Studio. The bridge is a small script that runs inside Resolve (Workspace ▸ Scripts ▸ resolve_bridge) and passes commands from the server over loopback, using HMAC-signed requests with one-time nonces. `install.py` always installs it. To reinstall it by hand, run `python scripts/install_resolve_bridge.py`. Once it's running, the server uses it automatically. Set `DAVINCI_RESOLVE_BRIDGE=1` to force the server to use only the bridge. The connection to the bridge is kept open between requests. Older versions opened a new connection for every API call, and on Windows a busy session ran out of ports and the bridge seemed to "die". **After updating, run `python install.py` (or `python scripts/install_resolve_bridge.py`) again and restart the bridge in Resolve** so the copy inside Resolve is updated too.

## Things to know

- **Your source media is read-only.** Analysis writes only sidecar reports and Resolve metadata. It never re-encodes or changes your camera files.
- **Free edition, 21.1 and later:** Blackmagic moved Python scripting to Studio, so the bridge reliably works only up to 21.0.x on the free edition.
- **macOS with the free edition:** Resolve finds Python only via `PYTHON3HOME` or `/usr/local/bin/python3`. If the bridge doesn't show up in the Scripts menu, run:
  `launchctl setenv PYTHON3HOME "$(python3 -c 'import sys; print(sys.prefix)')"`
  then restart Resolve. The `resolve_bridge_canary` script in the menu tells you whether Resolve can see Python.
- **Safety:** Risky edits use a plan, review, then confirm flow. Grade copies that would overwrite hand work are refused unless you pass `acknowledge_trap: true`.

## More docs

- [Install and client config](docs/install.md)
- [AI skill reference](docs/SKILL.md)
- [Media analysis guide](docs/guides/media-analysis-guide.md)
- [API coverage](docs/reference/api-coverage.md)
- [Control panel](docs/guides/control-panel.md)
- [Security](SECURITY.md)

## Requirements

- DaVinci Resolve 18.5 or later (Studio, or the free edition through the bridge)
- Python 3.10–3.12 is the safest choice. 3.13+ works on recent Resolve builds.
- Optional: ffmpeg, Node 18.18+ (for motion graphics) / 20.9+ (for the advanced offline server)

## License

MIT. Original work © DaVinci Resolve MCP Contributors (Samuel Gursky et al.). See [LICENSE](LICENSE).
