"""
Tests for Sakshi — the silent witness (sdk/sakshi.py).

Covers:
  1. append-only chain: records link by sha256, genesis prefix
  2. tamper detection: editing an old record breaks the chain at that point
  3. operator journal + machine events live in the SAME chain, tagged by source
  4. corrupt-tail refusal: a mangled last line blocks appends (no silent reset)
  5. export: paper corpus is a faithful copy of the chain
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from sdk.sakshi import entries, export_paper, record, verify


class SakshiChainTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.path = Path(self._tmp) / "sakshi.jsonl"

    def test_append_only_chain_links_records(self):
        r1 = record("journal", "first thought", agent="mike",
                    source="operator", path=self.path)
        r2 = record("bid", "scout-1 bids 0.5", agent="scout-1",
                    source="machine", path=self.path)
        self.assertEqual(r1["prev_hash"], "sakshi-genesis-v1")
        self.assertEqual(r2["prev_hash"], r1["chain_hash"])
        self.assertNotEqual(r1["chain_hash"], r2["chain_hash"])
        verdict = verify(self.path)
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["count"], 2)

    def test_tamper_detected_at_break_point(self):
        r1 = record("journal", "original entry", agent="mike",
                    source="operator", path=self.path)
        record("journal", "second entry", agent="mike",
               source="operator", path=self.path)
        # Forge the FIRST record's text in place.
        rows = entries(self.path)
        rows[0]["text"] = "FORGED"
        with open(self.path, "w") as f:
            for row in rows:
                f.write(json.dumps(row, sort_keys=True) + "\n")
        verdict = verify(self.path)
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["break"], 0)

    def test_machine_and_operator_streams_share_one_chain(self):
        record("journal", "operator thought", agent="mike",
               source="operator", path=self.path)
        record("verdict", "drill: 16 CAUGHT", agent="drill",
               source="machine", path=self.path)
        rows = entries(self.path)
        self.assertEqual([r["source"] for r in rows],
                         ["operator", "machine"])
        self.assertEqual([r["agent"] for r in rows], ["mike", "drill"])
        self.assertTrue(verify(self.path)["ok"])

    def test_corrupt_tail_refuses_append(self):
        record("journal", "good entry", agent="mike", source="operator",
               path=self.path)
        with open(self.path, "a") as f:
            f.write("this is not json at all\n")
        with self.assertRaises(RuntimeError):
            record("journal", "should not append", agent="mike",
                   source="operator", path=self.path)

    def test_export_is_faithful_copy(self):
        record("journal", "thought one", agent="mike", source="operator",
               path=self.path)
        record("drill", "16 CAUGHT", agent="drill", source="machine",
               path=self.path)
        out = Path(self._tmp) / "paper.jsonl"
        export_paper(path=self.path, out=out)
        exported = [json.loads(line) for line in open(out)]
        self.assertEqual(len(exported), 2)
        self.assertEqual(exported[0]["text"], "thought one")
        self.assertEqual(exported[1]["text"], "16 CAUGHT")

    def test_unknown_kind_still_records_but_is_tagged(self):
        rec = record("telemetry_extra", "uncatalogued", agent="x",
                     source="machine", path=self.path)
        self.assertEqual(rec["kind"], "telemetry_extra")
        self.assertTrue(verify(self.path)["ok"])


if __name__ == "__main__":
    unittest.main()