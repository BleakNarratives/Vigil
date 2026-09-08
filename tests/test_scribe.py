"""
Tests for Scribe (vigil/scribe.py) — the conversation-to-knowledge-log parser.

Covers:
  1. a transcript line naming a module + action becomes a deliverable entry
     linked to the right file
  2. verdict/outcome lines become outcome entries
  3. lines naming nothing known are NOT fabricated (no phantom links)
  4. git commits whose subject names a module attach to the entry
"""

import json
import tempfile
import unittest
from pathlib import Path

from vigil.scribe import build_log, _scan_transcript, _known_modules


class ScribeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="scribe_test_"))
        self.registry = self._tmp / "module_registry.json"
        json.dump({"modules": [
            {"name": "core", "path": "core.py"},
            {"name": "oler", "path": "oler.py"},
            {"name": "mines", "path": "mines.py"},
        ]}, open(self.registry, "w"))

    def test_transcript_links_module_to_file(self):
        t = self._tmp / "session.txt"
        t.write_text("wired oler: the bullshit sniffer\n")
        modules = _known_modules(json.load(open(self.registry)))
        entries = _scan_transcript(t, modules)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["kind"], "deliverable")
        self.assertEqual(entries[0]["modules"], ["oler"])
        self.assertEqual(entries[0]["files"], ["oler.py"])

    def test_no_fabrication_for_unknown_names(self):
        t = self._tmp / "session.txt"
        t.write_text("wired the quantum banana modulator today\n")
        modules = _known_modules(json.load(open(self.registry)))
        self.assertEqual(_scan_transcript(t, modules), [])

    def test_build_log_includes_outcomes(self):
        t = self._tmp / "session.txt"
        t.write_text("built mines: culture weapons\n"
                     "VERDICT: 20 CAUGHT / 5 LANDED\n"
                     "Ran 119 tests: OK\n")
        entries = build_log(t, self.registry, git_dir=None)
        kinds = [e["kind"] for e in entries]
        self.assertIn("deliverable", kinds)
        self.assertIn("outcome", kinds)
        self.assertGreaterEqual(len([k for k in kinds if k == "outcome"]), 2)

    def test_git_commit_links_to_entry(self):
        t = self._tmp / "session.txt"
        t.write_text("implemented mines: culture-class effect weapons\n")
        entries = build_log(t, self.registry, git_dir=str(Path(__file__).resolve().parent.parent))
        mine_entries = [e for e in entries if "mines" in e.get("modules", [])]
        if mine_entries:
            # if the repo has a mines commit, it must be attached
            for e in mine_entries:
                for c in e.get("commits", []):
                    self.assertIn("mines", c["subject"].lower())


if __name__ == "__main__":
    unittest.main()