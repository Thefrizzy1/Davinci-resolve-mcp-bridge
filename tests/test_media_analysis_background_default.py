"""analyze_* defaults to a background job with a bounded wait (MCP request timeouts)."""

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import server  # noqa: E402


class BackgroundDefaultTest(unittest.TestCase):
    def test_auto_background_only_for_real_runs_without_an_explicit_choice(self):
        self.assertTrue(server._media_analysis_auto_background({"clip_id": "x"}))
        self.assertFalse(server._media_analysis_auto_background({"clip_id": "x", "dry_run": True}))
        self.assertFalse(server._media_analysis_auto_background({"clip_id": "x", "background": False}))
        self.assertFalse(server._media_analysis_auto_background({"clip_id": "x", "prefer_handle": True}))

    def test_wait_seconds_is_bounded(self):
        self.assertEqual(server._media_analysis_wait_seconds({}), server.MEDIA_ANALYSIS_WAIT_SECONDS)
        self.assertEqual(server._media_analysis_wait_seconds({"wait_seconds": 500}), 50.0)
        self.assertEqual(server._media_analysis_wait_seconds({"wait_seconds": "x"}), server.MEDIA_ANALYSIS_WAIT_SECONDS)

    def test_wait_returns_running_then_full_status(self):
        states = iter(["running", "running", "completed", "completed"])

        def fake_status(root, job_id, include_clips=True, include_events=True):
            return {"job_id": job_id, "status": next(states), "clips": [] if include_clips else None}

        with mock.patch.object(server, "media_analysis_batch_job_status", fake_status), \
                mock.patch.object(server.asyncio, "sleep", mock.AsyncMock()):
            first = asyncio.run(server._media_analysis_wait_for_job("/root", "job-1", 0))
            self.assertEqual((first["status"], first["job_id"]), ("running", "job-1"))
            done = asyncio.run(server._media_analysis_wait_for_job("/root", "job-1", 5))
        self.assertEqual(done["status"], "completed")
        self.assertIn("plan_story_beats", done["note"])

    def test_unreadable_job_falls_back(self):
        with mock.patch.object(server, "media_analysis_batch_job_status", lambda *a, **k: {"success": False}):
            self.assertIsNone(asyncio.run(server._media_analysis_wait_for_job("/root", "job-1", 1)))


if __name__ == "__main__":
    unittest.main()
