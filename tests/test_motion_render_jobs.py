"""Render jobs: retries reuse the job, one render at a time, hard timeout, long-poll.

A model that hit the client timeout used to call render again, and every retry
started another render — a loop that ran for hours.
"""

import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils import motion_graphics as mg  # noqa: E402

FAKE_RENDERER = textwrap.dedent("""
    import json, sys, time
    args = sys.argv[1:]
    out = args[args.index("--out") + 1]
    props = json.load(open(args[args.index("--props-file") + 1], encoding="utf-8"))
    time.sleep(float(props.get("sleep", 0.3)))
    open(out, "w", encoding="utf-8").write("video")
    print(json.dumps({"success": True, "out": out}))
""")


class RenderJobTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        script = Path(self.tmp.name) / "fake_render.py"
        script.write_text(FAKE_RENDERER, encoding="utf-8")
        for patcher in (
            mock.patch.object(mg, "RENDER_SCRIPT", script),
            mock.patch.object(mg, "node_command", return_value=sys.executable),
            mock.patch.object(mg, "bundled_installed", return_value=True),
            mock.patch.object(mg, "custom_project", return_value=None),
            mock.patch.dict(os.environ, {"DAVINCI_RESOLVE_MCP_MOTION_OUT": self.tmp.name}),
            mock.patch.dict(mg._jobs, clear=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_retry_returns_the_same_job_and_then_the_same_file(self):
        first = mg.start_render("TitleCard", {"title": "x"})
        self.assertEqual(mg.start_render("TitleCard", {"title": "x"}), first)
        done = mg.job_status(first, 10)
        self.assertEqual(done["status"], "done")
        self.assertEqual(mg.start_render("TitleCard", {"title": "x"}), first)
        self.assertNotEqual(mg.start_render("TitleCard", {"title": "y"}), first)

    def test_one_render_at_a_time(self):
        first = mg.start_render("TitleCard", {"sleep": 0.5})
        second = mg.start_render("Counter", {"sleep": 0.1})
        self.assertEqual(mg.job_status(second, 0)["status"], "queued")
        self.assertEqual(mg.job_status(second, 10)["status"], "done")
        self.assertEqual(mg.job_status(first, 0)["status"], "done")

    def test_hung_render_is_stopped_with_its_output(self):
        with mock.patch.object(mg, "RENDER_TIMEOUT_SECONDS", 0.3):
            job = mg.job_status(mg.start_render("Particles3D", {"sleep": 30}), 10)
        self.assertEqual(job["status"], "error")
        self.assertIn("was stopped", job["result"]["error"])

    def test_default_wait_stays_under_client_timeouts(self):
        self.assertLessEqual(mg.DEFAULT_WAIT_SECONDS, 30)


if __name__ == "__main__":
    unittest.main()
