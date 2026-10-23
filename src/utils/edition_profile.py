"""Edition and tool-set profile: free-edition mode and "Resolve tools only".

Chosen in ``install.py`` and stored in ``~/.config/davinci-resolve-mcp/profile.json``;
the environment variables below override the file.

``edition = "free"`` (DAVINCI_RESOLVE_MCP_EDITION)
    - Connects through the in-app bridge only. External scripting is a Studio
      feature, so it is never attempted (DAVINCI_RESOLVE_BRIDGE=1 is implied).
    - Refuses Studio-only actions *before* they reach Resolve. On the free
      edition such a call does not just return False: Resolve raises an upsell
      modal that makes every later API call fail until a human dismisses it
      (see the api_truth entry "Studio-gated calls on the free edition…").
    - Hides tools that only drive Studio/paid features (Blackmagic Cloud).

``toolset = "resolve"`` (DAVINCI_RESOLVE_MCP_TOOLSET)
    Only the tools that control Resolve; the bridge's extras (local_ai,
    motion_graphics, knowledge) are not registered. Fewer tools means a
    smaller prompt, which small local models need.

``DAVINCI_RESOLVE_MCP_DISABLED_TOOLS=a,b`` hides any further tools by name.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, FrozenSet, List, Optional

SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".config", "davinci-resolve-mcp", "profile.json")
EDITIONS = ("studio", "free")
TOOLSETS = ("full", "resolve", "lean")

#: (tool, action) pairs whose Resolve call is gated to Studio (DaVinci Neural
#: Engine and other Studio-only features). Derived by tracing each action to
#: the Resolve API method it calls.
STUDIO_ONLY_ACTIONS: Dict[str, FrozenSet[str]] = {
    "folder": frozenset({
        "transcribe_audio", "clear_transcription", "perform_audio_classification",
        "analyze_for_intellisearch", "analyze_for_slate", "remove_motion_blur",
    }),
    "media_pool_item": frozenset({
        "transcribe_audio", "clear_transcription", "perform_audio_classification",
        "analyze_for_intellisearch", "analyze_for_slate", "remove_motion_blur",
    }),
    "media_pool": frozenset({"create_stereo_clip"}),
    "project_settings": frozenset({"generate_speech"}),
    "timeline": frozenset({"set_voice_isolation_state", "subtitle_generation_probe"}),
    "timeline_ai": frozenset({"create_subtitles", "detect_scene_cuts", "analyze_dolby_vision"}),
    "timeline_item": frozenset({"set_voice_isolation_state"}),
    "timeline_item_color": frozenset({"smart_reframe", "create_magic_mask", "regenerate_magic_mask"}),
}

#: Free-edition alternatives worth naming in the refusal.
_ALTERNATIVES = {
    "transcribe_audio": "local_ai(action='transcribe') runs Whisper locally instead.",
    "create_subtitles": "local_ai(action='transcribe', params={'import_srt': true}) makes an SRT locally; "
                        "motion_graphics Captions renders styled subtitles.",
    "subtitle_generation_probe": "local_ai(action='transcribe', params={'import_srt': true}).",
}

#: Whole tools that only drive Studio or paid services.
STUDIO_ONLY_TOOLS: FrozenSet[str] = frozenset({"project_manager_cloud"})
#: Tools that are this bridge's extras rather than Resolve control.
EXTRA_TOOLS: FrozenSet[str] = frozenset({"local_ai", "motion_graphics", "knowledge", "editor"})
#: The "lean" tool set: everything an edit needs in ~2k tokens of tool schema,
#: instead of ~35k for the full surface — which alone fills a local model's
#: context before it has read the task.
LEAN_TOOLS: FrozenSet[str] = frozenset({"editor", "motion_graphics"})


def _settings() -> Dict[str, Any]:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _choice(env_name: str, key: str, allowed, default: str) -> str:
    value = (os.environ.get(env_name) or str(_settings().get(key) or "")).strip().lower()
    return value if value in allowed else default


def edition() -> str:
    return _choice("DAVINCI_RESOLVE_MCP_EDITION", "edition", EDITIONS, "studio")


def toolset() -> str:
    return _choice("DAVINCI_RESOLVE_MCP_TOOLSET", "toolset", TOOLSETS, "full")


def hidden_tools(all_tools: Optional[List[str]] = None) -> List[str]:
    hidden = set()
    if edition() == "free":
        hidden |= STUDIO_ONLY_TOOLS
    if toolset() == "resolve":
        hidden |= EXTRA_TOOLS
    if toolset() == "lean":
        hidden |= {name for name in (all_tools or []) if name not in LEAN_TOOLS}
    extra = os.environ.get("DAVINCI_RESOLVE_MCP_DISABLED_TOOLS", "")
    hidden |= {name.strip() for name in extra.split(",") if name.strip()}
    return sorted(hidden)


def refusal(tool: str, action: Optional[str]) -> Optional[str]:
    """Why this call is blocked in the current profile, or None when it may run."""
    if edition() != "free" or not action:
        return None
    if action in STUDIO_ONLY_ACTIONS.get(tool, frozenset()):
        message = (f"{tool}.{action} needs DaVinci Resolve Studio; this server is set to the free edition. "
                   "It was not sent to Resolve (on the free edition it would raise an upgrade dialog that "
                   "blocks every later call).")
        alternative = _ALTERNATIVES.get(action) if "local_ai" not in hidden_tools() else None
        return f"{message} {alternative}" if alternative else message
    return None


def apply_transport_defaults() -> None:
    """Free edition: the bridge is the only transport; never try external scripting."""
    if edition() == "free":
        os.environ.setdefault("DAVINCI_RESOLVE_BRIDGE", "1")


def compact_output() -> bool:
    """Small replies for small models: on for the lean/resolve tool sets."""
    flag = os.environ.get("DAVINCI_RESOLVE_MCP_COMPACT", "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return flag in ("1", "true", "yes", "on") or toolset() in ("lean", "resolve")


def apply_compact_output(fastmcp) -> int:
    """Send each tool result once, as minified JSON, with no output schema.

    By default FastMCP returns every result twice — pretty-printed JSON text
    plus a structuredContent copy — and advertises an outputSchema per tool.
    For a local model that is pure context cost. Run after any other tool.fn
    wrapping (it wraps the final callable).
    """
    import json as _json

    from mcp import types as _types

    count = 0
    for tool in list(getattr(fastmcp._tool_manager, "_tools", {}).values()):
        try:
            tool.fn_metadata.output_schema = None
            tool.fn_metadata.output_model = None
            tool.fn_metadata.wrap_output = False
        except Exception:  # noqa: BLE001 — unexpected SDK shape: leave the tool alone
            continue
        inner, inner_async = tool.fn, getattr(tool, "is_async", False)

        def _compact(result):
            if isinstance(result, list) and result and all(
                    getattr(i.__class__, "__name__", "") in ("Image", "ImageContent", "TextContent") for i in result):
                return result  # preview image + caption
            if isinstance(result, (dict, list)):
                return _types.TextContent(type="text", text=_json.dumps(
                    result, separators=(",", ":"), ensure_ascii=False, default=str))
            return result

        if inner_async:
            async def wrapped(*args, __inner=inner, **kwargs):
                return _compact(await __inner(*args, **kwargs))
        else:
            def wrapped(*args, __inner=inner, **kwargs):
                return _compact(__inner(*args, **kwargs))
        import functools as _functools

        tool.fn = _functools.wraps(inner)(wrapped)
        count += 1
    return count


def apply_to_server(fastmcp) -> List[str]:
    """Unregister hidden tools from a FastMCP server; returns the names removed."""
    removed = []
    names = list(getattr(fastmcp._tool_manager, "_tools", {}).keys())
    for name in hidden_tools(names):
        try:
            fastmcp.remove_tool(name)
            removed.append(name)
        except Exception:  # noqa: BLE001 — unknown or already removed
            continue
    return removed


def save(edition_value: str, toolset_value: str, path: str = SETTINGS_PATH) -> str:
    data = _settings() if path == SETTINGS_PATH else {}
    data.update(edition=edition_value, toolset=toolset_value)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
    return path


def summary() -> Dict[str, Any]:
    return {
        "edition": edition(),
        "toolset": toolset(),
        "settings_file": SETTINGS_PATH,
        "hidden_tools": hidden_tools(),
        "studio_only_actions_blocked": edition() == "free",
        "transport": "bridge only" if edition() == "free" else "external scripting, bridge fallback",
    }
