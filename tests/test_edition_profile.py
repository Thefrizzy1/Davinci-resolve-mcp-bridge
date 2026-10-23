"""Free-edition / Resolve-only profile: Studio-only actions refused, tools hidden."""

import ast
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils import edition_profile as ep  # noqa: E402

STUDIO_API = {
    "TranscribeAudio", "ClearTranscription", "CreateSubtitlesFromAudio", "DetectSceneCuts",
    "CreateMagicMask", "RegenerateMagicMask", "SmartReframe", "AnalyzeForIntellisearch",
    "AnalyzeForSlate", "GenerateSpeech", "RemoveMotionBlur", "SetVoiceIsolationState",
    "CreateStereoClip", "AnalyzeDolbyVision", "PerformAudioClassification",
}


def _env(**values):
    base = {"DAVINCI_RESOLVE_MCP_EDITION": "", "DAVINCI_RESOLVE_MCP_TOOLSET": "",
            "DAVINCI_RESOLVE_MCP_DISABLED_TOOLS": ""}
    base.update(values)
    return mock.patch.dict(os.environ, base)


class EditionProfileTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(ep, "SETTINGS_PATH", str(ROOT / "nonexistent-profile.json"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_defaults_are_studio_full(self):
        with _env():
            self.assertEqual((ep.edition(), ep.toolset()), ("studio", "full"))
            self.assertEqual(ep.hidden_tools(), [])
            self.assertIsNone(ep.refusal("timeline_ai", "create_subtitles"))

    def test_free_refuses_studio_actions_only(self):
        with _env(DAVINCI_RESOLVE_MCP_EDITION="free"):
            self.assertIn("Studio", ep.refusal("timeline_item_color", "create_magic_mask"))
            self.assertIn("local_ai", ep.refusal("media_pool_item", "transcribe_audio"))
            self.assertIsNone(ep.refusal("timeline_item_color", "stabilize"))
            self.assertIsNone(ep.refusal("media_pool", "auto_sync_audio"))
            self.assertEqual(ep.hidden_tools(), ["project_manager_cloud"])

    def test_resolve_only_toolset_hides_extras_and_their_hints(self):
        with _env(DAVINCI_RESOLVE_MCP_EDITION="free", DAVINCI_RESOLVE_MCP_TOOLSET="resolve",
                  DAVINCI_RESOLVE_MCP_DISABLED_TOOLS="gallery"):
            hidden = ep.hidden_tools()
            for name in ("local_ai", "motion_graphics", "knowledge", "project_manager_cloud", "gallery"):
                self.assertIn(name, hidden)
            self.assertNotIn("local_ai", ep.refusal("media_pool_item", "transcribe_audio"))

    def test_free_forces_the_bridge(self):
        with _env(DAVINCI_RESOLVE_MCP_EDITION="free"):
            os.environ.pop("DAVINCI_RESOLVE_BRIDGE", None)
            ep.apply_transport_defaults()
            self.assertEqual(os.environ.get("DAVINCI_RESOLVE_BRIDGE"), "1")
            os.environ.pop("DAVINCI_RESOLVE_BRIDGE", None)

    def test_every_studio_api_call_in_server_is_behind_a_refusal(self):
        """A new action reaching a Studio-gated API must be added to STUDIO_ONLY_ACTIONS."""
        tree = ast.parse((ROOT / "src" / "server.py").read_text(encoding="utf-8"))
        funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}

        def direct(node):
            names = set()
            for n in ast.walk(node):
                if isinstance(n, ast.Call):
                    if isinstance(n.func, ast.Attribute) and n.func.attr in STUDIO_API:
                        names.add(n.func.attr)
                    elif isinstance(n.func, ast.Name) and n.func.id in funcs:
                        names.add("fn:" + n.func.id)
            return names

        memo = {}

        def gated(name, seen=()):
            if name not in memo:
                found = set()
                for c in direct(funcs[name]):
                    if c.startswith("fn:"):
                        if c[3:] not in seen:
                            found |= gated(c[3:], seen + (name,))
                    else:
                        found.add(c)
                memo[name] = found
            return memo[name]

        missing = []
        for tool in tree.body:
            if not (isinstance(tool, ast.FunctionDef) and any(
                    isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool" for d in tool.decorator_list)):
                continue
            for node in ast.walk(tool):
                if not (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                        and isinstance(node.test.left, ast.Name) and node.test.left.id == "action"):
                    continue
                actions = [c.value for c in node.test.comparators if isinstance(c, ast.Constant)]
                hits = set()
                for stmt in node.body:
                    for c in direct(stmt):
                        hits |= gated(c[3:]) if c.startswith("fn:") else {c}
                for action in actions:
                    if hits and tool.name != "script_plugin" and action not in ep.STUDIO_ONLY_ACTIONS.get(tool.name, ()):
                        missing.append(f"{tool.name}.{action} -> {sorted(hits)}")
        self.assertEqual(missing, [], "Studio-gated API reachable in free mode")


if __name__ == "__main__":
    unittest.main()
