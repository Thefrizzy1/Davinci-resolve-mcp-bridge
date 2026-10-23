"""Motion graphics: Remotion + Three.js templates rendered to files Resolve imports.

The renderer lives in ``motion-graphics/`` (a small Remotion project with
ready-made 2D and three.js templates, see ``templates.json``). It is an
optional extra: ``install.py`` offers it, or run ``npm install`` in that folder.

People who already have their own Remotion project can point the bridge at it
with ``DAVINCI_RESOLVE_MCP_MOTION_PROJECT`` (and ``..._ENTRY`` if the entry file
is not ``src/index.*``); its compositions are then rendered instead.

Renders run as a child Node process. Short ones finish inside the call; long
ones return a ``job_id`` to poll with :func:`job_status`, so an MCP client's
tool timeout never kills a render half-way.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
MOTION_DIR = REPO / "motion-graphics"
RENDER_SCRIPT = MOTION_DIR / "render.mjs"
CATALOG_PATH = MOTION_DIR / "templates.json"
#: Must stay under MCP clients' request timeout (LM Studio ~60 s). At 90 s the
#: client gave up first, the model retried, and every retry started another
#: render — a feedback loop that ran for hours.
DEFAULT_WAIT_SECONDS = 20.0
#: A render (or a still) that runs longer than this is killed and reported with
#: the renderer's own last output, instead of "running" forever.
RENDER_TIMEOUT_SECONDS = float(os.environ.get("DAVINCI_RESOLVE_MCP_MOTION_TIMEOUT", "900"))
STILL_TIMEOUT_SECONDS = 300.0
#: An identical request finished this recently returns that file instead of rendering again.
REUSE_SECONDS = 600.0
MAX_JOB_AGE_SECONDS = 6 * 3600

_jobs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


class MotionError(Exception):
    """A motion-graphics call that cannot proceed; the message says what to fix."""


# ─── Environment ─────────────────────────────────────────────────────────────

def _env(name: str) -> Optional[str]:
    value = os.environ.get(name, "").strip()
    return value or None


def node_command() -> Optional[str]:
    return _env("DAVINCI_RESOLVE_MCP_NODE") or shutil.which("node")


def custom_project() -> Optional[Path]:
    value = _env("DAVINCI_RESOLVE_MCP_MOTION_PROJECT")
    return Path(value).expanduser().resolve() if value else None


def output_dir() -> Path:
    """Where renders go: somewhere a person will actually look (~/Videos)."""
    value = _env("DAVINCI_RESOLVE_MCP_MOTION_OUT")
    return Path(value).expanduser() if value else Path.home() / "Videos" / "Resolve MCP Motion"


def open_file(path: str) -> bool:
    """Open a finished render in the system's default player/viewer."""
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except (OSError, AttributeError):
        return False


def bundled_installed() -> bool:
    return (MOTION_DIR / "node_modules" / "@remotion" / "renderer").is_dir()


def load_catalog() -> List[Dict[str, Any]]:
    with open(CATALOG_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def status() -> Dict[str, Any]:
    node = node_command()
    version = None
    if node:
        try:
            version = subprocess.run(
                [node, "--version"], capture_output=True, text=True, encoding="utf-8",
                errors="replace", stdin=subprocess.DEVNULL, timeout=10,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            version = None
    project = custom_project()
    installed = bundled_installed()
    result: Dict[str, Any] = {
        "success": True,
        "available": bool(node) and (installed or bool(project)),
        "node": {"path": node, "version": version},
        "bundled_templates": {"installed": installed, "dir": str(MOTION_DIR),
                              "count": len(load_catalog())},
        "custom_project": str(project) if project else None,
        "output_dir": str(output_dir()),
        "running_jobs": [j["id"] for j in _jobs.values() if j["status"] == "running"],
        "queued_jobs": [j["id"] for j in _jobs.values() if j["status"] == "queued"],
    }
    if not node:
        result["install"] = "Install Node.js 18.18+ (https://nodejs.org), then re-run install.py --motion."
    elif not installed and not project:
        result["install"] = "Run: python install.py --motion   (or: cd motion-graphics && npm install)"
    return result


# ─── Templates ───────────────────────────────────────────────────────────────

def _run_render_script(args: List[str], timeout: float) -> Dict[str, Any]:
    node = node_command()
    if not node:
        raise MotionError("Node.js was not found. Install Node 18.18+ or set DAVINCI_RESOLVE_MCP_NODE.")
    proc = subprocess.run(
        [node, str(RENDER_SCRIPT), *args], cwd=str(MOTION_DIR), capture_output=True, text=True,
        encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=timeout,
    )
    return _parse_result(proc.stdout, proc.stderr)


def _parse_result(stdout: str, stderr: str) -> Dict[str, Any]:
    for line in reversed((stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    tail = "\n".join((stderr or stdout or "").strip().splitlines()[-12:])
    return {"success": False, "error": tail or "renderer produced no output"}


def list_templates() -> Dict[str, Any]:
    project = custom_project()
    if project is None:
        return {"success": True, "source": "bundled", "templates": load_catalog()}
    if not bundled_installed():
        raise MotionError(
            "Listing a custom Remotion project uses the bridge's renderer; run "
            "`python install.py --motion` once, or render by composition id with action='render'."
        )
    args = ["--list", "--project", str(project)]
    if _env("DAVINCI_RESOLVE_MCP_MOTION_ENTRY"):
        args += ["--entry", _env("DAVINCI_RESOLVE_MCP_MOTION_ENTRY")]
    result = _run_render_script(args, timeout=300)
    result["source"] = str(project)
    return result


# ─── Captions helpers ────────────────────────────────────────────────────────

_SRT_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def srt_to_segments(path: str) -> List[Dict[str, Any]]:
    """Parse an .srt file into ``[{start, end, text}]`` for the Captions template."""
    with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
        blocks = re.split(r"\n\s*\n", handle.read().replace("\r\n", "\n"))
    segments = []
    for block in blocks:
        lines = [l for l in block.strip().splitlines() if l.strip()]
        for i, line in enumerate(lines):
            m = _SRT_TIME.search(line)
            if m:
                g = [int(x) for x in m.groups()]
                start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
                end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
                text = " ".join(lines[i + 1:]).strip()
                if text:
                    segments.append({"start": round(start, 3), "end": round(end, 3), "text": text})
                break
    return segments


# ─── Rendering ───────────────────────────────────────────────────────────────

def _prune() -> None:
    now = time.time()
    for job_id in [k for k, j in _jobs.items()
                   if j["status"] != "running" and now - (j.get("ended_at") or now) > MAX_JOB_AGE_SECONDS]:
        _jobs.pop(job_id, None)


def _tail(path: str, lines: int = 8) -> str:
    try:
        return "\n".join(Path(path).read_text(encoding="utf-8", errors="replace").strip().splitlines()[-lines:])
    except OSError:
        return ""


def _pump() -> None:
    """Start the oldest queued render when nothing is running (call under _lock).

    One render at a time: Remotion already uses every core, and parallel
    renders only made each one slower — which made clients time out and retry.
    """
    if any(j["status"] == "running" for j in _jobs.values()):
        return
    queued = sorted((j for j in _jobs.values() if j["status"] == "queued"), key=lambda j: j["created_at"])
    if not queued:
        return
    job = queued[0]
    spec = job.pop("_spec")
    with open(job["_stdout"], "w", encoding="utf-8") as so, open(job["_stderr"], "w", encoding="utf-8") as se:
        job["_proc"] = subprocess.Popen(spec["cmd"], cwd=spec["cwd"], stdout=so, stderr=se,
                                        stdin=subprocess.DEVNULL, env=spec["env"])
    job.update(status="running", started_at=time.time())


def _finish(job: Dict[str, Any]) -> None:
    """Fold a finished child process into the job record (call under _lock)."""
    proc = job.get("_proc")
    if job["status"] != "running" or proc is None:
        return
    if proc.poll() is None:
        if time.time() - job["started_at"] > job["_timeout"]:
            proc.kill()
            job.update(status="error", ended_at=time.time(), result={
                "success": False,
                "error": (f"Render took longer than {job['_timeout'] / 60:g} min and was stopped. "
                          f"Last renderer output:\n{_tail(job['_stderr']) or _tail(job['_stdout']) or '(none)'}"),
            })
            job.pop("_proc", None)
        return
    stdout = Path(job["_stdout"]).read_text(encoding="utf-8", errors="replace")
    stderr = Path(job["_stderr"]).read_text(encoding="utf-8", errors="replace")
    result = _parse_result(stdout, stderr)
    if not result.get("success") and proc.returncode == 0 and os.path.exists(job["out"]):
        result = {"success": True, "out": job["out"]}  # project's own CLI prints no JSON
    job["result"] = result
    job["status"] = "done" if result.get("success") else "error"
    job["ended_at"] = time.time()
    job.pop("_proc", None)


def _public(job: Dict[str, Any]) -> Dict[str, Any]:
    progress = None
    try:
        with open(job["_progress"], "r", encoding="utf-8") as handle:
            progress = json.load(handle)
    except (OSError, ValueError):
        pass
    out = {k: v for k, v in job.items() if not k.startswith("_")}
    if progress:
        out["stage"] = progress.get("stage")
        out["progress"] = round(float(progress.get("progress") or 0), 3)
    started = job.get("started_at") or job["created_at"]
    out["elapsed_seconds"] = round((job.get("ended_at") or time.time()) - started, 1)
    if job["status"] == "queued":
        out["queue_position"] = sum(1 for j in _jobs.values()
                                    if j["status"] in ("queued", "running") and j["created_at"] < job["created_at"])
    return out


def _default_out(template: str, props: Dict[str, Any], codec: Optional[str], still: bool, alpha: bool) -> Path:
    if still:
        ext = ".png"
    else:
        ext = {"prores": ".mov", "vp9": ".webm", "vp8": ".webm", "h264": ".mp4", "h265": ".mp4"}.get(codec or "", "")
        if not ext:
            meta = next((t for t in load_catalog() if t["id"] == template), {}) if custom_project() is None else {}
            transparent = alpha or meta.get("transparent") or props.get("transparentBackground") is True
            ext = ".mov" if transparent else ".mp4"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return output_dir() / f"{template}-{stamp}-{uuid.uuid4().hex[:4]}{ext}"


def _npx() -> str:
    npx = shutil.which("npx")
    if not npx:
        raise MotionError("npx was not found (it ships with Node.js).")
    return npx


def start_render(
    template: str,
    props: Optional[Dict[str, Any]] = None,
    *,
    out_path: Optional[str] = None,
    codec: Optional[str] = None,
    still_frame: Optional[int] = None,
    scale: Optional[float] = None,
    alpha: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """Spawn the renderer and return a job id immediately."""
    node = node_command()
    if not node:
        raise MotionError("Node.js was not found. Install Node 18.18+ or set DAVINCI_RESOLVE_MCP_NODE.")
    if not template:
        raise MotionError("'template' is required (see action='list_templates').")
    project = custom_project()
    if project is None and not bundled_installed():
        raise MotionError("Motion templates are not installed. Run: python install.py --motion "
                          "(or: cd motion-graphics && npm install).")
    props = dict(props or {})
    still = still_frame is not None
    key = json.dumps([template, props, out_path, codec, still_frame, scale, bool(alpha), str(project)],
                     sort_keys=True, default=str)
    with _lock:
        for existing in _jobs.values():
            if existing.get("_key") != key:
                continue
            if existing["status"] in ("queued", "running"):
                return existing["id"]  # a retry of a request still in progress
            if (existing["status"] == "done" and time.time() - (existing.get("ended_at") or 0) < REUSE_SECONDS
                    and os.path.exists(existing["out"])):
                return existing["id"]  # rendered moments ago: hand back the same file
    out = Path(out_path).expanduser().resolve() if out_path else _default_out(template, props, codec, still, alpha)
    out.parent.mkdir(parents=True, exist_ok=True)

    job_id = uuid.uuid4().hex[:8]
    work = Path(tempfile.mkdtemp(prefix=f"motion-{job_id}-"))
    props_file = work / "props.json"
    props_file.write_text(json.dumps(props), encoding="utf-8")
    entry = _env("DAVINCI_RESOLVE_MCP_MOTION_ENTRY")

    if project is not None and not bundled_installed():
        # Bring-your-own Remotion: drive the project's own CLI and versions.
        cmd = [_npx(), "--no-install", "remotion", "still" if still else "render",
               *([entry] if entry else []), template, str(out), f"--props={props_file}"]
        if still:
            cmd.append(f"--frame={int(still_frame)}")
        elif codec:
            cmd.append(f"--codec={codec}")
        if scale:
            cmd.append(f"--scale={float(scale)}")
        cwd = str(project)
    else:
        cmd = [node, str(RENDER_SCRIPT), "--template", template, "--props-file", str(props_file),
               "--progress-file", str(work / "progress.json"), "--out", str(out)]
        if project is not None:
            cmd += ["--project", str(project), *(["--entry", entry] if entry else [])]
        if still:
            cmd += ["--still", str(int(still_frame))]
        if codec:
            cmd += ["--codec", str(codec)]
        if scale:
            cmd += ["--scale", str(float(scale))]
        if alpha:
            cmd += ["--alpha"]
        cwd = str(MOTION_DIR)

    stdout_path, stderr_path = work / "stdout.log", work / "stderr.log"
    env = dict(os.environ)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    with _lock:
        _prune()
        _jobs[job_id] = {
            "id": job_id, "template": template, "status": "queued", "result": None, "out": str(out),
            "created_at": time.time(), "started_at": None, "ended_at": None, "extra": extra or {},
            "_key": key, "_spec": {"cmd": cmd, "cwd": cwd, "env": env},
            "_timeout": STILL_TIMEOUT_SECONDS if still else RENDER_TIMEOUT_SECONDS,
            "_stdout": str(stdout_path), "_stderr": str(stderr_path), "_progress": str(work / "progress.json"),
        }
        _pump()
    return job_id


def wait(job_id: str, seconds: float = DEFAULT_WAIT_SECONDS) -> Dict[str, Any]:
    deadline = time.time() + max(0.0, float(seconds))
    while True:
        with _lock:
            job = _jobs.get(job_id)
            if job is None:
                raise MotionError(f"Unknown job_id {job_id!r}")
            for other in list(_jobs.values()):
                _finish(other)
            _pump()
            if job["status"] not in ("running", "queued") or time.time() >= deadline:
                return _public(job)
        time.sleep(0.25)


def job_status(job_id: str, seconds: float = DEFAULT_WAIT_SECONDS) -> Dict[str, Any]:
    """Long-poll: waits up to ``seconds`` for the job to finish."""
    return wait(job_id, seconds)


def cancel(job_id: str) -> Dict[str, Any]:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise MotionError(f"Unknown job_id {job_id!r}")
        proc = job.get("_proc")
        if proc is not None and proc.poll() is None:
            proc.terminate()
        job.update(status="cancelled", ended_at=time.time())
        job.pop("_proc", None)
        job.pop("_spec", None)
        _pump()
        return _public(job)


def mark_extra(job_id: str, **values: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            job["extra"].update(values)


def start_studio(port: int = 3000) -> Dict[str, Any]:
    """Launch Remotion Studio (live preview/editor in the browser) in the background."""
    project = custom_project() or MOTION_DIR
    if project == MOTION_DIR and not bundled_installed():
        raise MotionError("Motion templates are not installed. Run: python install.py --motion")
    entry = _env("DAVINCI_RESOLVE_MCP_MOTION_ENTRY") or ("src/index.jsx" if project == MOTION_DIR else "")
    cmd = [_npx(), "--no-install", "remotion", "studio", *([entry] if entry else []), f"--port={int(port)}"]
    log = open(Path(tempfile.gettempdir()) / "remotion-studio.log", "w", encoding="utf-8")
    subprocess.Popen(cmd, cwd=str(project), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     start_new_session=os.name != "nt")
    return {"success": True, "url": f"http://localhost:{int(port)}", "project": str(project),
            "log": log.name, "note": "Studio takes a few seconds to bundle before the page loads."}
