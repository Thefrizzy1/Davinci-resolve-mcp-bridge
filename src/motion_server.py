"""Standalone motion-graphics MCP server (Remotion + Three.js). No Resolve needed.

    python src/motion_server.py

Separate from the DaVinci Resolve server on purpose: rendering never touches
Resolve, so it needs no bridge, no scripting API and no running Resolve, and a
client that only wants graphics loads one small tool instead of the Resolve
surface. To put a render into Resolve, use the Resolve server's
editor(action="import", params={"folder": "renders"}).
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, Optional

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp import types
from mcp.server.fastmcp import FastMCP, Image

from src.utils import motion_graphics as mg

INSTRUCTIONS = (
    "Motion graphics with Remotion + Three.js; DaVinci Resolve is not needed. "
    "Call motion with action list_templates to see templates and their props, still for a one-frame "
    "PNG preview, render for the video (add open=true to play it). If a reply says running or queued, "
    "call job_status with that job_id until done — never call render again for the same video. "
    "Files are saved in the user's Videos/Resolve MCP Motion folder."
)

server = FastMCP("motion-graphics", instructions=INSTRUCTIONS)
ACTIONS = ("status", "list_templates", "render", "still", "job_status", "cancel", "studio")


def _text(payload: Any) -> types.TextContent:
    if isinstance(payload, str):
        return types.TextContent(type="text", text=payload)
    return types.TextContent(type="text", text=json.dumps(payload, separators=(",", ":"),
                                                           ensure_ascii=False, default=str))


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _deliver(job: Dict[str, Any], params: Dict[str, Any]) -> Any:
    """A finished job as the reply: where the file is, opened if asked, and the
    frame itself for stills (a chat cannot play video, but it can show a PNG)."""
    if job["status"] in ("running", "queued"):
        return _text({**job, "note": (f"Still {job['status']} — normal, not an error. Call motion "
                                      f"job_status with job_id '{job['id']}' (it waits 20 s). Do NOT "
                                      "call render again: the same request returns this same job.")})
    result = job.get("result") or {}
    if job["status"] != "done" or not result.get("success"):
        return _text({"success": False, "job_id": job["id"],
                      "error": result.get("error") or f"render {job['status']}"})
    out = result.get("out") or job.get("out")
    reply = {"success": True, "job_id": job["id"], "out": out,
             **{k: result[k] for k in ("durationSeconds", "width", "height", "alpha", "codec") if k in result}}
    if out and _truthy(params.get("open")):
        reply["opened"] = mg.open_file(out)
    reply["note"] = f"Saved to {out}" + (" and opened." if reply.get("opened") else ". Pass open=true to play it.")
    if str(out).lower().endswith(".png") and os.path.isfile(out) and params.get("preview", True) is not False:
        return [_text(reply), Image(path=out)]
    return _text(reply)


@server.tool(structured_output=False)
def motion(action: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """Render motion graphics videos with Remotion + Three.js. Resolve is NOT needed.

    Templates — 2D: TitleCard, LowerThird, KineticText, Captions, Counter, EndCard.
    3D (three.js): Text3D, Particles3D, Shapes3D. Overlays render with transparency
    (ProRes .mov); the rest H.264 .mp4. Files go to ~/Videos/Resolve MCP Motion.

    Actions:
      list_templates() -> each template's id, length and props (only pass what you change)
      still(template, props?, frame?, scale?) -> one PNG frame, shown in the chat
      render(template, props?, duration_seconds?, width?, height?, fps?, open?, srt_path?)
        -> the video file. open=true plays it. Captions: props.segments or srt_path.
        Replies within 20 s; if status is running/queued, call job_status — never render again.
      job_status(job_id) -> waits up to 20 s, then the result or progress
      cancel(job_id) | status() | studio() -> live Remotion Studio in the browser
    """
    p: Dict[str, Any] = dict(params or {})
    if action not in ACTIONS:
        return _text({"success": False, "error": f"Unknown action {action!r}; use one of {list(ACTIONS)}."})
    try:
        if action == "status":
            return _text(mg.status())
        if action == "list_templates":
            listing = mg.list_templates()
            rows = [{"id": t["id"], "seconds": t.get("durationSeconds"), "transparent": t.get("transparent"),
                     "about": t.get("description"), "props": t.get("defaultProps")}
                    for t in listing.get("templates", [])]
            return _text({"templates": rows})
        if action == "studio":
            return _text(mg.start_studio(int(p.get("port", 3000))))
        if action == "cancel":
            return _text(mg.cancel(str(p["job_id"])))
        if action == "job_status":
            return _deliver(mg.job_status(str(p["job_id"]), float(p.get("wait_seconds", mg.DEFAULT_WAIT_SECONDS))), p)

        template = str(p["template"])
        props = dict(p.get("props") or {})
        for key in ("durationSeconds", "fps", "width", "height"):
            snake = re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), key)
            if p.get(snake) is not None and key not in props:
                props[key] = p[snake]
        if template == "Captions" and not props.get("segments") and p.get("srt_path"):
            props["segments"] = mg.srt_to_segments(os.path.expanduser(str(p["srt_path"])))
        still = action == "still"
        job_id = mg.start_render(
            template, props, out_path=p.get("out_path"), codec=p.get("codec"),
            still_frame=int(p.get("frame", 30)) if still else None,
            scale=p.get("scale"), alpha=_truthy(p.get("alpha")),
        )
        return _deliver(mg.wait(job_id, float(p.get("wait_seconds", mg.DEFAULT_WAIT_SECONDS))), p)
    except KeyError as exc:
        return _text({"success": False, "error": f"Missing parameter {exc}."})
    except mg.MotionError as exc:
        return _text({"success": False, "error": str(exc)})


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
