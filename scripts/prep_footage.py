"""Transcribe every speech clip in the open Resolve project — before you chat.

    venv/bin/python scripts/prep_footage.py               (Windows: venv\\Scripts\\python ...)
    venv/bin/python scripts/prep_footage.py --model small

Resolve must be running with the project open (and, on the free edition, the
in-app bridge started: Workspace > Scripts > resolve_bridge). Transcripts are
cached on disk, so the AI's `editor` tool finds them instantly instead of
spending its context (and your patience) waiting for Whisper. Re-running only
transcribes clips that are new or changed.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("DAVINCI_RESOLVE_MCP_UPDATE_CHECK", "0")


def _text(result) -> str:
    return getattr(result, "text", None) or str(result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=None, help="Whisper model (default: the one the installer downloaded)")
    parser.add_argument("--clips", default="speech", help="'speech' (default), 'all', or comma-separated c-numbers")
    args = parser.parse_args()

    from src import server

    print("Reading the media pool…")
    print(_text(server.editor("footage", {})))
    clips = args.clips if args.clips in ("speech", "all") else [c.strip() for c in args.clips.split(",")]
    started = time.time()
    while True:
        report = _text(server.editor("transcribe", {"clips": clips, "model": args.model, "wait_seconds": 30}))
        print(f"\n[{int(time.time() - started)}s]\n{report}")
        if "still running" not in report:
            break
    print("\nDone. In your chat, the AI can go straight to editor(action='sentences').")
    return 0


if __name__ == "__main__":
    sys.exit(main())
