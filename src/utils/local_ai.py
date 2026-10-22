"""Local AI suite: quick Whisper transcription and local-vision frame descriptions.

Everything here runs on this machine — no cloud calls, no API keys, no costs.

- **Transcription** uses ``faster-whisper`` (CTranslate2). It decodes audio and
  video containers itself through PyAV, so ffmpeg is not required. Models are
  downloaded once from Hugging Face on first use and cached.
- **Vision** sends a few frames to any OpenAI-compatible chat endpoint serving a
  vision-language model: LM Studio (default ``http://127.0.0.1:1234/v1``) or
  Ollama (``http://127.0.0.1:11434/v1``). This is what lets a local text model
  "see" footage: the server does the looking and returns plain text.

Configuration (all optional, read per call):

    DAVINCI_RESOLVE_MCP_WHISPER_MODEL   tiny|base|small|medium|large-v3|turbo (default: base)
    DAVINCI_RESOLVE_MCP_WHISPER_DEVICE  auto|cpu|cuda (default: auto)
    DAVINCI_RESOLVE_MCP_VISION_URL      OpenAI-compatible base URL (default: LM Studio)
    DAVINCI_RESOLVE_MCP_VISION_MODEL    model id; otherwise a loaded vision model is picked
    DAVINCI_RESOLVE_MCP_VISION_API_KEY  bearer token if your server wants one
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import shutil
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

DEFAULT_WHISPER_MODEL = "base"
DEFAULT_VISION_URL = "http://127.0.0.1:1234/v1"
DEFAULT_VISION_PROMPT = (
    "These are frames sampled in order from one video clip. Describe the clip for "
    "an editor: setting, subjects, action, shot type and camera movement, lighting, "
    "and any on-screen text. Be concise and factual."
)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}

# Substrings that mark a model id as vision-capable, used when no model is set.
_VISION_HINTS = (
    "vl", "vision", "llava", "gemma-3", "gemma3", "gemma-4", "pixtral", "minicpm-v",
    "moondream", "smolvlm", "bakllava", "mistral-small-3", "internvl", "phi-4-multimodal",
)

_whisper_models: Dict[tuple, Any] = {}
_whisper_lock = threading.Lock()


class LocalAIError(Exception):
    """A local-AI call that cannot proceed; the message says what to fix."""


# ─── Status ──────────────────────────────────────────────────────────────────

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name, "").strip()
    return value or default


def vision_base_url() -> str:
    return (_env("DAVINCI_RESOLVE_MCP_VISION_URL", DEFAULT_VISION_URL) or DEFAULT_VISION_URL).rstrip("/")


def _http_json(url: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 5.0) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    key = _env("DAVINCI_RESOLVE_MCP_VISION_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    # A system HTTP(S)_PROXY must not swallow calls to a model server on this machine.
    opener = (urllib.request.build_opener(urllib.request.ProxyHandler({}))
              if host in ("127.0.0.1", "localhost", "::1") else urllib.request.build_opener())
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def list_vision_server_models() -> List[str]:
    payload = _http_json(f"{vision_base_url()}/models", timeout=3.0)
    return [str(item.get("id")) for item in payload.get("data") or [] if item.get("id")]


def status() -> Dict[str, Any]:
    """Report what is installed and reachable. Never downloads anything."""
    vision: Dict[str, Any] = {"url": vision_base_url(), "configured_model": _env("DAVINCI_RESOLVE_MCP_VISION_MODEL")}
    try:
        models = list_vision_server_models()
        vision.update(reachable=True, models=models, vision_models=[m for m in models if _looks_like_vision(m)])
    except (OSError, ValueError) as exc:
        vision.update(reachable=False, error=str(exc),
                      hint="Start LM Studio's server (Developer tab) or Ollama, and load a vision model "
                           "such as Qwen2.5-VL, Gemma 3 or LLaVA.")
    whisper_ok = importlib.util.find_spec("faster_whisper") is not None
    return {
        "success": True,
        "transcription": {
            "available": whisper_ok,
            "backend": "faster_whisper",
            "default_model": _env("DAVINCI_RESOLVE_MCP_WHISPER_MODEL", DEFAULT_WHISPER_MODEL),
            "loaded_models": [f"{name} ({device})" for name, device, _ in _whisper_models],
            **({} if whisper_ok else {"install": "venv/bin/pip install -r requirements-local-ai.txt"}),
        },
        "vision": vision,
        "frame_extraction": {"ffmpeg": shutil.which("ffmpeg"), "opencv": importlib.util.find_spec("cv2") is not None},
    }


# ─── Transcription ───────────────────────────────────────────────────────────

def _load_whisper(model: str, device: str, compute_type: str):
    key = (model, device, compute_type)
    with _whisper_lock:
        if key not in _whisper_models:
            try:
                from faster_whisper import WhisperModel  # type: ignore[import-not-found]
            except ImportError as exc:
                raise LocalAIError(
                    "faster-whisper is not installed. Run: venv/bin/pip install -r requirements-local-ai.txt "
                    "(or re-run install.py and accept the local AI extras)."
                ) from exc
            try:
                _whisper_models[key] = WhisperModel(model, device=device, compute_type=compute_type)
            except Exception as exc:  # download blocked, bad model name, CUDA libs missing…
                raise LocalAIError(
                    f"Could not load Whisper model {model!r} on {device}: {exc}. The first run downloads "
                    "the model from huggingface.co; set DAVINCI_RESOLVE_MCP_WHISPER_DEVICE=cpu if CUDA fails."
                ) from exc
        return _whisper_models[key]


def _srt_time(seconds: float) -> str:
    ms = int(round(max(seconds, 0.0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: List[Dict[str, Any]]) -> str:
    blocks = []
    for index, seg in enumerate(segments, 1):
        blocks.append(f"{index}\n{_srt_time(seg['start'])} --> {_srt_time(seg['end'])}\n{seg['text'].strip()}\n")
    return "\n".join(blocks)


def transcribe(
    path: str,
    *,
    model: Optional[str] = None,
    language: Optional[str] = None,
    word_timestamps: bool = False,
    vad_filter: bool = True,
    srt_path: Optional[str] = None,
    task: str = "transcribe",
) -> Dict[str, Any]:
    """Transcribe an audio or video file. Returns text, timed segments and optional SRT."""
    if not path or not os.path.isfile(path):
        raise LocalAIError(f"File not found: {path!r}")
    model = model or _env("DAVINCI_RESOLVE_MCP_WHISPER_MODEL", DEFAULT_WHISPER_MODEL)
    device = _env("DAVINCI_RESOLVE_MCP_WHISPER_DEVICE", "auto")
    whisper = _load_whisper(model, device, "int8" if device == "cpu" else "auto")
    raw_segments, info = whisper.transcribe(
        path,
        language=language or None,
        task=task,
        word_timestamps=word_timestamps,
        vad_filter=vad_filter,
    )
    segments: List[Dict[str, Any]] = []
    for seg in raw_segments:  # a generator: decoding happens here
        entry: Dict[str, Any] = {"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip()}
        if word_timestamps and seg.words:
            entry["words"] = [
                {"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3),
                 "probability": round(w.probability, 3)}
                for w in seg.words
            ]
        segments.append(entry)
    result: Dict[str, Any] = {
        "success": True,
        "backend": "faster_whisper",
        "model": model,
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration": round(info.duration, 3),
        "text": " ".join(seg["text"] for seg in segments).strip(),
        "segments": segments,
    }
    if srt_path:
        os.makedirs(os.path.dirname(os.path.abspath(srt_path)), exist_ok=True)
        with open(srt_path, "w", encoding="utf-8") as handle:
            handle.write(segments_to_srt(segments))
        result["srt_path"] = os.path.abspath(srt_path)
    return result


# ─── Frames ──────────────────────────────────────────────────────────────────

def _probe_duration(path: str) -> Optional[float]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, timeout=30,
        )
        try:
            return float(proc.stdout.strip())
        except ValueError:
            return None
    return None


def _ffmpeg_frame(ffmpeg: str, path: str, at: Optional[float], max_dim: int) -> bytes:
    cmd = [ffmpeg, "-v", "error"]
    if at is not None:
        cmd += ["-ss", f"{at:.3f}"]
    cmd += ["-i", path, "-frames:v", "1",
            "-vf", f"scale='min({max_dim},iw)':'min({max_dim},ih)':force_original_aspect_ratio=decrease",
            "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "4", "-"]
    # stdin=DEVNULL: over stdio the server's stdin is the JSON-RPC stream, and
    # ffmpeg reads keyboard commands from whatever stdin it inherits.
    proc = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, timeout=60)
    if proc.returncode != 0 or not proc.stdout:
        raise LocalAIError(f"ffmpeg could not read a frame at {at}s: {proc.stderr.decode(errors='replace').strip()}")
    return proc.stdout


def _cv2_frames(path: str, count: int, max_dim: int, times: Optional[List[float]]):
    import cv2  # type: ignore[import-not-found]

    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total / fps if total else 0.0
    stamps = times or [duration * (i + 0.5) / count for i in range(count)]
    frames = []
    for at in stamps:
        cap.set(cv2.CAP_PROP_POS_MSEC, at * 1000.0)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        scale = min(1.0, max_dim / float(max(h, w)))
        if scale < 1.0:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if ok:
            frames.append((round(at, 3), buf.tobytes()))
    cap.release()
    return frames


def extract_frames(path: str, count: int = 4, max_dim: int = 768,
                   times: Optional[List[float]] = None) -> List[tuple]:
    """Return ``[(seconds_or_None, jpeg_bytes), ...]`` evenly spread through the clip."""
    if not path or not os.path.isfile(path):
        raise LocalAIError(f"File not found: {path!r}")
    count = max(1, min(int(count), 16))
    is_image = os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        if is_image:
            return [(None, _ffmpeg_frame(ffmpeg, path, None, max_dim))]
        duration = _probe_duration(path) or 0.0
        stamps = times or ([duration * (i + 0.5) / count for i in range(count)] if duration else [0.0])
        return [(round(at, 3), _ffmpeg_frame(ffmpeg, path, at, max_dim)) for at in stamps]
    if is_image:
        with open(path, "rb") as handle:  # sent as-is; most servers resize anyway
            return [(None, handle.read())]
    if importlib.util.find_spec("cv2") is not None:
        frames = _cv2_frames(path, count, max_dim, times)
        if frames:
            return frames
    raise LocalAIError("Need ffmpeg (recommended) or opencv-python to pull frames from video.")


# ─── Vision ──────────────────────────────────────────────────────────────────

def _looks_like_vision(model_id: str) -> bool:
    lowered = model_id.lower()
    return any(hint in lowered for hint in _VISION_HINTS)


def pick_vision_model(requested: Optional[str] = None) -> str:
    chosen = requested or _env("DAVINCI_RESOLVE_MCP_VISION_MODEL")
    if chosen:
        return chosen
    try:
        models = list_vision_server_models()
    except (OSError, ValueError) as exc:
        raise LocalAIError(
            f"No vision server at {vision_base_url()} ({exc}). Start LM Studio's local server or Ollama, "
            "or set DAVINCI_RESOLVE_MCP_VISION_URL."
        ) from exc
    vision = [m for m in models if _looks_like_vision(m)]
    if vision:
        return vision[0]
    if models:
        return models[0]
    raise LocalAIError("The vision server has no models loaded. Load a vision model (e.g. Qwen2.5-VL, Gemma 3).")


def describe(
    path: str,
    *,
    prompt: Optional[str] = None,
    frames: int = 4,
    times: Optional[List[float]] = None,
    model: Optional[str] = None,
    max_tokens: int = 600,
    max_dim: int = 768,
    timeout: float = 300.0,
) -> Dict[str, Any]:
    """Ask a local vision model to describe an image or a few frames of a video."""
    sampled = extract_frames(path, count=frames, max_dim=max_dim, times=times)
    chosen = pick_vision_model(model)
    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt or DEFAULT_VISION_PROMPT}]
    for _, jpeg in sampled:
        content.append({"type": "image_url",
                        "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")}})
    body = {"model": chosen, "messages": [{"role": "user", "content": content}],
            "max_tokens": int(max_tokens), "temperature": 0.2, "stream": False}
    try:
        reply = _http_json(f"{vision_base_url()}/chat/completions", body, timeout=timeout)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise LocalAIError(f"Vision server returned HTTP {exc.code}: {detail}. Is '{chosen}' a vision model?") from exc
    except (OSError, ValueError) as exc:
        raise LocalAIError(f"Vision request to {vision_base_url()} failed: {exc}") from exc
    choices = reply.get("choices") or []
    text = (choices[0].get("message") or {}).get("content", "") if choices else ""
    return {
        "success": True,
        "model": chosen,
        "server": vision_base_url(),
        "frame_times": [at for at, _ in sampled],
        "description": str(text).strip(),
    }
