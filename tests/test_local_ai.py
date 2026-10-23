"""Offline tests for src/utils/local_ai.py (no model downloads, no live server)."""

import json
import os
import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils import local_ai  # noqa: E402


class _FakeVisionServer(BaseHTTPRequestHandler):
    models = ["llama-3.1-8b-instruct", "qwen2.5-vl-7b-instruct"]
    last_body = None

    def log_message(self, *args):
        pass

    def _send(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send({"data": [{"id": m} for m in self.models]})

    def do_POST(self):
        type(self).last_body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._send({"choices": [{"message": {"content": "A test card."}}]})


class LocalAITest(unittest.TestCase):
    def test_srt_formatting(self):
        srt = local_ai.segments_to_srt([
            {"start": 0.0, "end": 1.5, "text": " Hello. "},
            {"start": 3661.25, "end": 3662.0, "text": "Later."},
        ])
        self.assertIn("1\n00:00:00,000 --> 00:00:01,500\nHello.\n", srt)
        self.assertIn("2\n01:01:01,250 --> 01:01:02,000\nLater.\n", srt)

    def test_transcribe_missing_file(self):
        with self.assertRaises(local_ai.LocalAIError):
            local_ai.transcribe("/nonexistent/clip.mov")

    def test_transcribe_with_stub_model(self):
        seg = types.SimpleNamespace(start=0.0, end=1.0, text=" Rolling. ", words=None)
        info = types.SimpleNamespace(language="en", language_probability=0.9, duration=1.0)
        stub = mock.Mock()
        stub.transcribe.return_value = (iter([seg]), info)
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "a.wav")
            Path(media).write_bytes(b"\0")
            with mock.patch.object(local_ai, "_load_whisper", return_value=stub):
                out = local_ai.transcribe(media, srt_path=os.path.join(tmp, "a.srt"))
            self.assertEqual(out["text"], "Rolling.")
            self.assertEqual(out["backend"], "faster_whisper")
            self.assertTrue(Path(out["srt_path"]).read_text(encoding="utf-8").startswith("1\n00:00:00,000"))

    def test_vision_model_pick_and_describe(self):
        server = HTTPServer(("127.0.0.1", 0), _FakeVisionServer)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        env = {"DAVINCI_RESOLVE_MCP_VISION_URL": f"http://127.0.0.1:{server.server_port}/v1"}
        try:
            with mock.patch.dict(os.environ, env), \
                    mock.patch.object(local_ai, "extract_frames", return_value=[(1.0, b"\xff\xd8jpeg")]):
                self.assertEqual(local_ai.pick_vision_model(), "qwen2.5-vl-7b-instruct")
                out = local_ai.describe("/any/file.mov", prompt="What is this?")
        finally:
            server.shutdown()
        self.assertEqual(out["description"], "A test card.")
        content = _FakeVisionServer.last_body["messages"][0]["content"]
        self.assertEqual(content[0]["text"], "What is this?")
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    def test_vision_unreachable_is_clean_error(self):
        with mock.patch.dict(os.environ, {"DAVINCI_RESOLVE_MCP_VISION_URL": "http://127.0.0.1:9/v1"}):
            self.assertFalse(local_ai.status()["vision"]["reachable"])
            with self.assertRaises(local_ai.LocalAIError):
                local_ai.pick_vision_model()

    def test_background_jobs_queue_and_report_progress(self):
        release = threading.Event()

        def work(progress):
            progress("transcribing", 0.5)
            release.wait(5)
            return {"text": "done"}

        first = local_ai.start_job("transcribe", "a", work)
        second = local_ai.start_job("transcribe", "b", lambda progress: {"text": "second"})
        snap = local_ai.wait_job(first, 0.3)
        self.assertEqual((snap["status"], snap["progress"]), ("running", 0.5))
        self.assertEqual(local_ai.wait_job(second, 0)["status"], "queued")
        release.set()
        self.assertEqual(local_ai.wait_job(first, 5)["result"], {"text": "done"})
        self.assertEqual(local_ai.wait_job(second, 5)["result"], {"text": "second"})

    def test_failed_job_reports_error(self):
        def work(progress):
            raise local_ai.LocalAIError("no model")

        job = local_ai.wait_job(local_ai.start_job("transcribe", "x", work), 5)
        self.assertEqual((job["status"], job["error"]), ("error", "no model"))


if __name__ == "__main__":
    unittest.main()
