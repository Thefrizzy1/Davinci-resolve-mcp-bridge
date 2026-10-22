# DaVinci Resolve MCP Bridge

[![Version](https://img.shields.io/badge/version-4.14.4-blue.svg)](CHANGELOG.md)
[![Tools](https://img.shields.io/badge/MCP%20Tools-38%20(390%20full)-blue.svg)](#whats-what)
[![Advanced](https://img.shields.io/badge/Advanced%20(offline)-18%20tools-blueviolet.svg)](#whats-what)
[![Local AI](https://img.shields.io/badge/local%20AI-Whisper%20%2B%20vision-green.svg)](#local-ai-transcription-and-vision)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Control DaVinci Resolve from an AI assistant over MCP. Works with local models (LM Studio, Ollama) as well as Claude, Cursor and others. Includes a local Whisper + vision suite, so a local model can "hear" and "see" your footage without any cloud service.

> This is a personal fork of [samuelgursky/davinci-resolve-mcp](https://github.com/samuelgursky/davinci-resolve-mcp) (MIT).
> Changes in this fork: a `local_ai` tool (Whisper transcription + LM Studio/Ollama vision), the installer always installs the Resolve bridge, the installer can set up LM Studio directly, promo for the upstream's paid app is removed, and this README is shorter.

## Install

```bash
git clone https://github.com/Thefrizzy1/davinci-resolve-mcp-bridge.git
cd davinci-resolve-mcp-bridge
python install.py
```

The installer runs these steps in order:

1. Finds Resolve and creates a `venv/` with the dependencies.
2. **Always installs the in-app bridge** into Resolve's `Scripts/Utility` folders. You need it on the free edition. On Studio it does no harm.
3. Asks whether to install the **local AI extras** (faster-whisper).
4. Asks **"Install straight into LM Studio?"**, which writes `~/.lmstudio/mcp.json`. After that you can pick any other clients.
5. Checks the connection to Resolve.

To run it without the prompts:

```bash
python install.py --lmstudio --local-ai          # LM Studio + Whisper
python install.py --clients lmstudio,cursor      # several clients
python install.py --clients manual               # just print the JSON config
```

**Before connecting:**
- **Studio:** set Preferences ▸ General ▸ *External scripting using* to **Local**.
- **Free edition:** restart Resolve, open a project, then run **Workspace ▸ Scripts ▸ resolve_bridge**. The server finds the bridge automatically.

## What's what

| Part | What it is | When you need it |
|---|---|---|
| `src/server.py` | **Main MCP server.** 38 grouped tools (project, media pool, timeline, color, Fusion, Fairlight, render, `local_ai`…) | Always. This is what your client runs. |
| `src/server.py --full` | Same server with one tool per Resolve API method (390 tools) | Only for power users. It's too many tools for small local models. |
| `local_ai` tool | Whisper transcription and frame descriptions, all on this machine | When your model can't read audio or images itself |
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
  - The model downloads once on first use. The default is `base`; you can also use `tiny`, `small`, `medium`, `large-v3` or `turbo`.
- **Describe:** pulls a few frames (with ffmpeg, or OpenCV as a fallback) and sends them to the vision model loaded in **LM Studio** (default `http://127.0.0.1:1234/v1`) or **Ollama**. Load a vision model first, for example Qwen2.5-VL, Gemma 3 or LLaVA. If you don't name a model, it picks a loaded vision model automatically.
- The built-in `media_analysis` pipeline also uses faster-whisper as its first-choice transcription backend.

| Env var | Default | Purpose |
|---|---|---|
| `DAVINCI_RESOLVE_MCP_WHISPER_MODEL` | `base` | Whisper model size |
| `DAVINCI_RESOLVE_MCP_WHISPER_DEVICE` | `auto` | `cpu` / `cuda` / `auto` |
| `DAVINCI_RESOLVE_MCP_VISION_URL` | `http://127.0.0.1:1234/v1` | Any OpenAI-compatible server (`http://127.0.0.1:11434/v1` for Ollama) |
| `DAVINCI_RESOLVE_MCP_VISION_MODEL` | auto | Which vision model to use |

Install the extras later with `venv/bin/pip install -r requirements-local-ai.txt` (on Windows, `venv\Scripts\pip`).

## LM Studio tips

- The installer adds the server as `davinci-resolve` to `~/.lmstudio/mcp.json`. Any other servers already in that file stay as they are. Restart LM Studio after installing.
- Use a model that's good at tool calling (for example Qwen 2.5/3 or Llama 3.1+ instruct) with a context of 16k or more, because the tool list is large.
- You can run a text model for chat and a separate vision model for `local_ai describe` at the same time.

## Free edition (in-app bridge)

Blackmagic only allows *external* scripting on Studio. The bridge is a small script that runs inside Resolve (Workspace ▸ Scripts ▸ resolve_bridge) and passes commands from the server over loopback, using HMAC-signed requests with one-time nonces. `install.py` always installs it. To reinstall it by hand, run `python scripts/install_resolve_bridge.py`. Once it's running, the server uses it automatically. Set `DAVINCI_RESOLVE_BRIDGE=1` to force the server to use only the bridge.

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
- Optional: ffmpeg, Node 20.9+ (for the advanced offline server)

## License

MIT. Original work © DaVinci Resolve MCP Contributors (Samuel Gursky et al.). See [LICENSE](LICENSE).
