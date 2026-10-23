"""editor: sentence splitting, transcript cache and the timeline plan maths."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils import editor as ed  # noqa: E402


def _words(t0, text, step=0.4):
    out, t = [], t0
    for w in text.split():
        out.append({"word": " " + w, "start": t, "end": t + step - 0.05})
        t += step
    return out


class SentenceTest(unittest.TestCase):
    def test_word_timestamps_split_on_punctuation_and_long_pauses(self):
        transcript = {"segments": [
            {"start": 1, "end": 4, "text": "Rolling? Okay so", "words": _words(1, "Rolling? Okay so")},
            {"start": 6, "end": 9, "text": "I built this.", "words": _words(6, "I built this.")},
        ]}
        got = ed.split_sentences(transcript)
        self.assertEqual([s["text"] for s in got], ["Rolling?", "Okay so", "I built this."])
        self.assertEqual(got[2]["start"], 6.0)
        self.assertEqual([s["n"] for s in got], [1, 2, 3])

    def test_segment_fallback_without_words(self):
        got = ed.split_sentences({"segments": [{"start": 0, "end": 10, "text": "One two. Three four five six."}]})
        self.assertEqual(len(got), 2)
        self.assertAlmostEqual(got[1]["end"], 10.0, places=1)

    def test_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(ed, "CACHE_DIR", tmp):
            media = os.path.join(tmp, "a.mp4")
            Path(media).write_bytes(b"x")
            self.assertIsNone(ed.load_transcript(media))
            ed.save_transcript(media, {"model": "small", "segments": [
                {"start": 0, "end": 2, "text": "Hi.", "words": _words(0, "Hi.")}]})
            self.assertEqual(ed.load_transcript(media)["sentences"][0]["text"], "Hi.")


class PlanTest(unittest.TestCase):
    CLIPS = {"c1": {"name": "cam", "fps": 50.0, "duration": 120.0, "kind": "video"},
             "c2": {"name": "story", "fps": 24.0, "duration": 300.0, "kind": "video"},
             "c3": {"name": "music", "fps": 0.0, "duration": 160.0, "kind": "music"}}
    SENTS = {"c1": [{"n": 1, "start": 4.0, "end": 7.95, "text": "A."},
                    {"n": 2, "start": 9.0, "end": 10.5, "text": "B."},
                    {"n": 3, "start": 12.0, "end": 13.0, "text": "C."}]}

    def plan(self, request):
        return ed.plan_timeline(request, self.CLIPS, self.SENTS.get, 25.0)

    def test_back_to_back_with_padding_and_exact_frames(self):
        plan = self.plan({"lines": [{"clip": "c2", "in": 10, "out": 14, "part": "Hook"}, "c1#1",
                                    {"ref": "c1#2-3", "part": "Problem"}]})
        self.assertEqual(plan["errors"], [])
        story, first, pair = plan["v1"]
        self.assertEqual((story["record"], story["frames"]), (0, 100))
        # c1#1: 4.00-0.1 .. 7.95+0.3 = 3.90..8.25 -> 109 timeline frames; 50 fps source
        self.assertEqual((first["start_frame"], first["end_frame"], first["record"]), (195, 413, 100))
        self.assertEqual(pair["record"], first["record"] + first["frames"])  # no gap
        self.assertEqual((pair["in"], pair["out"]), (8.9, 13.3))
        self.assertEqual([m["name"] for m in plan["markers"]], ["Hook", "Problem"])

    def test_covers_music_and_target(self):
        plan = self.plan({"lines": ["c1#1", "c1#2"], "covers": [{"clip": "c2", "in": 30, "out": 32, "over": "c1#2"}],
                          "music": "c3", "target_seconds": [55, 65]})
        cover = plan["covers"][0]
        self.assertEqual(cover["record"], plan["v1"][1]["record"] + 12)  # 0.5 s in, rounded
        self.assertEqual(plan["music"]["frames"], plan["total_frames"])
        self.assertTrue(any("outside the target" in e for e in plan["errors"]))

    def test_problems_are_reported_not_raised(self):
        plan = self.plan({"lines": ["c1#9", "c7#1", "nonsense", {"clip": "c2", "in": 5, "out": 4}]})
        self.assertEqual(len(plan["errors"]), 4)
        self.assertEqual(plan["v1"], [])

    def test_format_plan_is_compact(self):
        text = "\n".join(ed.format_plan(self.plan({"lines": ["c1#1", "c1#2"]}), 25.0))
        self.assertIn('V1   0.00-  4.36 c1#1 "A."', text)
        self.assertLess(len(text), 300)


if __name__ == "__main__":
    unittest.main()
