"""Offline tests for the motion-graphics extra (no Node render is started)."""

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils import motion_graphics as mg  # noqa: E402


class CatalogTest(unittest.TestCase):
    def test_every_template_is_registered_and_has_a_component(self):
        catalog = mg.load_catalog()
        ids = [t["id"] for t in catalog]
        self.assertEqual(len(ids), len(set(ids)), "duplicate template ids")
        root = (ROOT / "motion-graphics" / "src" / "Root.jsx").read_text(encoding="utf-8")
        registered = re.search(r"const COMPONENTS = \{([^}]+)\}", root).group(1)
        for template in catalog:
            self.assertIn(template["id"], registered)
            self.assertTrue((ROOT / "motion-graphics" / "src" / "templates" / f"{template['id']}.jsx").is_file())
            for key in ("width", "height", "fps", "durationSeconds", "defaultProps", "description"):
                self.assertIn(key, template, f"{template['id']} is missing {key}")

    def test_dependencies_are_pinned_exactly(self):
        import json

        pkg = json.loads((ROOT / "motion-graphics" / "package.json").read_text(encoding="utf-8"))
        for name, version in pkg["dependencies"].items():
            self.assertRegex(version, r"^\d+\.\d+\.\d+$", f"{name} must be pinned to an exact version")
        remotion = {v for k, v in pkg["dependencies"].items() if k == "remotion" or k.startswith("@remotion/")}
        self.assertEqual(len(remotion), 1, "all remotion packages must share one version")


class HelpersTest(unittest.TestCase):
    def test_srt_to_segments(self):
        with tempfile.NamedTemporaryFile("w", suffix=".srt", delete=False, encoding="utf-8") as handle:
            handle.write("﻿1\r\n00:00:01,000 --> 00:00:02,500\r\nHello\r\nthere\r\n\r\n"
                         "2\r\n00:01:00.250 --> 00:01:01.000\r\nSecond\r\n")
        try:
            segments = mg.srt_to_segments(handle.name)
        finally:
            os.unlink(handle.name)
        self.assertEqual(segments, [
            {"start": 1.0, "end": 2.5, "text": "Hello there"},
            {"start": 60.25, "end": 61.0, "text": "Second"},
        ])

    def test_default_output_extension_follows_alpha(self):
        with mock.patch.dict(os.environ, {"DAVINCI_RESOLVE_MCP_MOTION_PROJECT": ""}):
            self.assertEqual(mg._default_out("LowerThird", {}, None, False, False).suffix, ".mov")
            self.assertEqual(mg._default_out("TitleCard", {}, None, False, False).suffix, ".mp4")
            self.assertEqual(mg._default_out("Shapes3D", {"transparentBackground": True}, None, False, False).suffix, ".mov")
            self.assertEqual(mg._default_out("TitleCard", {}, "vp9", False, False).suffix, ".webm")
            self.assertEqual(mg._default_out("TitleCard", {}, None, True, False).suffix, ".png")

    def test_render_refuses_cleanly_when_not_installed(self):
        with mock.patch.object(mg, "bundled_installed", return_value=False), \
                mock.patch.object(mg, "node_command", return_value="/usr/bin/node"), \
                mock.patch.dict(os.environ, {"DAVINCI_RESOLVE_MCP_MOTION_PROJECT": ""}):
            with self.assertRaises(mg.MotionError) as ctx:
                mg.start_render("LowerThird", {})
            self.assertIn("install.py --motion", str(ctx.exception))

    def test_status_without_node(self):
        with mock.patch.object(mg, "node_command", return_value=None):
            result = mg.status()
        self.assertFalse(result["available"])
        self.assertIn("Node.js", result["install"])

    def test_unknown_job(self):
        with self.assertRaises(mg.MotionError):
            mg.job_status("nope")


class StandaloneServerTest(unittest.TestCase):
    def test_motion_server_does_not_load_resolve(self):
        """The motion server must start with no Resolve, bridge or scripting API."""
        import subprocess

        code = ("import sys; sys.argv=['x']; import src.motion_server as m; "
                "print(sorted(m.server._tool_manager._tools), 'src.server' in sys.modules)")
        out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True,
                             encoding="utf-8", stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(out.stdout.strip(), "['motion'] False", out.stderr)

    def test_motion_is_not_part_of_the_resolve_server(self):
        text = (ROOT / "src" / "server.py").read_text(encoding="utf-8")
        self.assertNotIn("def motion_graphics(", text)


if __name__ == "__main__":
    unittest.main()
