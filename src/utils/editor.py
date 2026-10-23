"""Editor helpers: the logic behind the one-stop `editor` MCP tool.

Built for small local models with little context: everything an edit needs —
listing footage, transcribing it once (cached on disk), reading it back as
numbered sentences, and turning a short list of picks into a finished timeline —
in a handful of calls with compact text replies. The frame maths, padding,
back-to-back placement, colours, markers and the final check happen here, not
in the model.

Nothing in this module talks to Resolve; the server tool does that.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "davinci-resolve-mcp", "transcripts")
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aif", ".aiff", ".m4a", ".flac", ".ogg", ".aac"}
SCREEN_HINTS = (".mkv",)
_SENTENCE_END = re.compile(r"[.!?…]+[\"')\]]*$")


class EditorError(Exception):
    """A request the editor cannot carry out; the message says what to change."""


# ─── Footage ─────────────────────────────────────────────────────────────────

def guess_kind(name: str, clip_type: str = "", has_audio: Optional[bool] = None) -> str:
    """music | screen | video — a first guess; transcripts tell the rest."""
    ext = os.path.splitext(name or "")[1].lower()
    ctype = (clip_type or "").lower()
    if ext in AUDIO_EXTENSIONS or ctype == "audio":
        return "music"
    if ext in SCREEN_HINTS or "screen" in (name or "").lower() or "recording" in (name or "").lower():
        return "screen"
    if ctype in ("still", "timeline", "compound", "generator", "fusion title"):
        return ctype.replace(" ", "_")
    return "video"


def short_ids(names: List[str]) -> Dict[str, str]:
    """Stable short ids (c1, c2, …) by clip name order. Returns name-key -> short id."""
    return {key: f"c{i}" for i, key in enumerate(sorted(names, key=lambda n: n.lower()), 1)}


def fmt_seconds(value: float) -> str:
    value = max(0.0, float(value))
    minutes, seconds = divmod(value, 60)
    return f"{int(minutes)}:{seconds:05.2f}" if minutes else f"{seconds:.2f}s"


# ─── Transcript cache ────────────────────────────────────────────────────────

def _cache_key(path: str) -> str:
    try:
        st = os.stat(path)
        ident = f"{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        ident = os.path.abspath(path)
    return hashlib.sha1(ident.encode("utf-8")).hexdigest()[:20]


def cache_path(path: str) -> str:
    return os.path.join(CACHE_DIR, _cache_key(path) + ".json")


def load_transcript(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(cache_path(path), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def save_transcript(path: str, transcript: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(CACHE_DIR, exist_ok=True)
    data = {
        "file": os.path.abspath(path),
        "model": transcript.get("model"),
        "language": transcript.get("language"),
        "duration": transcript.get("duration"),
        "sentences": split_sentences(transcript),
    }
    tmp = cache_path(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
    os.replace(tmp, cache_path(path))
    return data


# ─── Sentences ───────────────────────────────────────────────────────────────

def split_sentences(transcript: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Whisper segments -> sentences with accurate first/last-word times.

    Uses word timestamps when present (cuts land on real word boundaries);
    otherwise falls back to segment times, splitting a segment's text at
    sentence punctuation in proportion to its length.
    """
    words: List[Dict[str, Any]] = []
    for seg in transcript.get("segments") or []:
        for w in seg.get("words") or []:
            text = str(w.get("word", w.get("text", ""))).strip()
            if text and w.get("start") is not None and w.get("end") is not None:
                words.append({"text": text, "start": float(w["start"]), "end": float(w["end"])})
    sentences: List[Dict[str, Any]] = []
    if words:
        current: List[Dict[str, Any]] = []
        for i, w in enumerate(words):
            current.append(w)
            gap_after = words[i + 1]["start"] - w["end"] if i + 1 < len(words) else 0.0
            if _SENTENCE_END.search(w["text"]) or gap_after > 1.5:
                sentences.append(_sentence(current))
                current = []
        if current:
            sentences.append(_sentence(current))
    else:
        for seg in transcript.get("segments") or []:
            text = str(seg.get("text", "")).strip()
            start, end = float(seg.get("start") or 0.0), float(seg.get("end") or 0.0)
            parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", text) if p.strip()]
            total = sum(len(p) for p in parts) or 1
            t = start
            for part in parts:
                d = (end - start) * len(part) / total
                sentences.append({"start": round(t, 2), "end": round(t + d, 2), "text": part})
                t += d
    for i, s in enumerate(sentences, 1):
        s["n"] = i
    return sentences


def _sentence(words: List[Dict[str, Any]]) -> Dict[str, Any]:
    text = " ".join(w["text"] for w in words)
    text = re.sub(r"\s+([,.!?;:…])", r"\1", text)
    return {"start": round(words[0]["start"], 2), "end": round(words[-1]["end"], 2), "text": text}


def format_sentences(short: str, sentences: List[Dict[str, Any]], contains: str = "") -> List[str]:
    needle = contains.lower().strip()
    lines = []
    for s in sentences:
        if needle and needle not in s["text"].lower():
            continue
        lines.append(f"{short}#{s['n']} {s['start']:.2f}-{s['end']:.2f} {s['text']}")
    return lines


# ─── Timeline plan ───────────────────────────────────────────────────────────

_REF = re.compile(r"^\s*(c\d+)\s*#\s*(\d+)(?:\s*-\s*(\d+))?\s*$", re.IGNORECASE)


def parse_ref(ref: str) -> Tuple[str, int, int]:
    """'c1#4' or 'c1#4-6' -> ('c1', 4, 6)."""
    m = _REF.match(str(ref))
    if not m:
        raise EditorError(f"Bad sentence reference {ref!r}; use 'c1#4' (clip c1, sentence 4) or 'c1#4-6'.")
    first = int(m.group(2))
    last = int(m.group(3) or first)
    if last < first:
        first, last = last, first
    return m.group(1).lower(), first, last


def plan_timeline(
    request: Dict[str, Any],
    clips: Dict[str, Dict[str, Any]],
    sentences_for,
    timeline_fps: float,
) -> Dict[str, Any]:
    """Turn the model's picks into exact placements. Pure: no Resolve calls.

    ``clips`` maps short id -> {name, fps, duration, kind}; ``sentences_for(short)``
    returns that clip's sentence list (or None when not transcribed).
    """
    pad_in = float(request.get("pad_in", 0.1))
    pad_out = float(request.get("pad_out", 0.3))
    errors: List[str] = []
    v1: List[Dict[str, Any]] = []
    cursor = 0  # timeline frames from the timeline start

    def clip_of(short: str) -> Dict[str, Any]:
        info = clips.get(short.lower())
        if info is None:
            raise EditorError(f"Unknown clip {short!r}; call editor(action='footage') for the c-numbers.")
        return info

    def place(short: str, src_in: float, src_out: float, record: int, track: str, extra: Dict[str, Any]):
        info = clip_of(short)
        clip_fps = float(info.get("fps") or timeline_fps)
        duration = float(info.get("duration") or 0.0)
        src_in = max(0.0, src_in)
        if duration:
            src_out = min(duration, src_out)
        if src_out <= src_in:
            raise EditorError(f"{short}: out ({src_out:.2f}s) must be after in ({src_in:.2f}s).")
        tl_frames = max(1, round((src_out - src_in) * timeline_fps))
        start_frame = round(src_in * clip_fps)
        end_frame = start_frame + max(1, round(tl_frames * clip_fps / timeline_fps))
        return {
            "clip": short, "name": info.get("name"), "kind": info.get("kind"), "track": track,
            "in": round(src_in, 3), "out": round(src_out, 3),
            "start_frame": start_frame, "end_frame": end_frame, "clip_fps": clip_fps,
            "record": record, "frames": tl_frames, **extra,
        }

    for raw in request.get("lines") or []:
        item = {"ref": raw} if isinstance(raw, str) else dict(raw)
        try:
            if item.get("ref"):
                short, first, last = parse_ref(item["ref"])
                sents = sentences_for(short)
                if not sents:
                    raise EditorError(f"{short} has no transcript yet; run editor(action='transcribe').")
                chosen = [s for s in sents if first <= s["n"] <= last]
                if len(chosen) != last - first + 1:
                    raise EditorError(f"{item['ref']}: {short} has sentences 1-{len(sents)}.")
                src_in = chosen[0]["start"] - pad_in
                src_out = chosen[-1]["end"] + pad_out
                text = " ".join(s["text"] for s in chosen)
            else:
                short = str(item.get("clip") or "").lower()
                src_in, src_out = float(item["in"]), float(item["out"])
                text = item.get("label") or ""
            placed = place(short, src_in, src_out, cursor, "V1",
                           {"ref": item.get("ref"), "text": text, "part": item.get("part")})
            cursor += placed["frames"]
            v1.append(placed)
        except (EditorError, KeyError, TypeError, ValueError) as exc:
            errors.append(f"line {raw!r}: {exc}")

    total_frames = cursor
    starts_by_ref = {p["ref"].lower(): p for p in v1 if p.get("ref")}
    covers: List[Dict[str, Any]] = []
    for raw in request.get("covers") or []:
        try:
            item = dict(raw)
            short = str(item["clip"]).lower()
            src_in, src_out = float(item["in"]), float(item["out"])
            if item.get("over"):
                anchor = starts_by_ref.get(str(item["over"]).lower().replace(" ", ""))
                if anchor is None:
                    raise EditorError(f"'over': {item['over']!r} is not one of the lines.")
                at = anchor["record"] + round(float(item.get("offset", 0.5)) * timeline_fps)
            else:
                at = round(float(item["at"]) * timeline_fps)
            placed = place(short, src_in, src_out, at, "V2", {"over": item.get("over")})
            if placed["record"] + placed["frames"] > total_frames:
                errors.append(f"cover {short} runs past the end of the edit; shorten it or move it earlier.")
            covers.append(placed)
        except (EditorError, KeyError, TypeError, ValueError) as exc:
            errors.append(f"cover {raw!r}: {exc}")

    music = None
    raw_music = request.get("music")
    if raw_music and total_frames:
        try:
            item = {"clip": raw_music} if isinstance(raw_music, str) else dict(raw_music)
            src_in = float(item.get("in", 0.0))
            music = place(str(item["clip"]).lower(), src_in, src_in + total_frames / timeline_fps, 0, "A2", {})
        except (EditorError, KeyError, TypeError, ValueError) as exc:
            errors.append(f"music {raw_music!r}: {exc}")

    markers = []
    seen_parts = set()
    for p in v1:
        part = p.get("part")
        if part and part not in seen_parts:
            seen_parts.add(part)
            markers.append({"name": str(part), "frame": p["record"]})

    seconds = total_frames / timeline_fps if timeline_fps else 0.0
    target = request.get("target_seconds")
    if isinstance(target, (list, tuple)) and len(target) == 2 and total_frames:
        low, high = float(target[0]), float(target[1])
        if not low <= seconds <= high:
            errors.append(f"total {seconds:.2f}s is outside the target {low:g}-{high:g}s.")
    return {"v1": v1, "covers": covers, "music": music, "markers": markers,
            "total_frames": total_frames, "total_seconds": round(seconds, 3), "errors": errors}


def format_plan(plan: Dict[str, Any], timeline_fps: float) -> List[str]:
    fps = timeline_fps or 1.0
    lines = [f"Total {plan['total_seconds']:.2f}s ({plan['total_frames']} frames @ {fps:g} fps)"]
    for p in plan["v1"]:
        start = p["record"] / fps
        label = p.get("ref") or f"{p['clip']} {p['in']:.2f}-{p['out']:.2f}"
        text = f' "{p["text"][:70]}"' if p.get("text") else ""
        part = f"[{p['part']}] " if p.get("part") else ""
        lines.append(f"V1 {start:6.2f}-{start + p['frames'] / fps:6.2f} {part}{label}{text}")
    for p in plan["covers"]:
        start = p["record"] / fps
        lines.append(f"V2 {start:6.2f}-{start + p['frames'] / fps:6.2f} {p['clip']} {p['in']:.2f}-{p['out']:.2f}"
                     + (f" over {p['over']}" if p.get("over") else ""))
    if plan.get("music"):
        lines.append(f"A2   0.00-{plan['total_seconds']:6.2f} music {plan['music']['clip']}")
    for e in plan["errors"]:
        lines.append(f"PROBLEM: {e}")
    return lines
