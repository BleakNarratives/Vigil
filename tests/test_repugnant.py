"""
Tests for Repugnant — the 4th register layer (vigil/repugnant.py).

Covers:
  1. signed append-only emotional snapshots; tamper caught
  2. state_discount: TILTED hero pays a bid penalty, calm scout pays none
  3. unsettled(): subjects below threshold surface with a demand-evidence
     note — recorded, never accused
  4. board integration: a tilted scout's bid loses to a calm scout's bid
     through the real SpottingBoard (4th register priced into priority)
  5. Theoros reads the emotional register (unsettled in the reading)
"""

import json
import tempfile
import unittest
from pathlib import Path

from vigil.integrity import CommandGuard
from vigil.repugnant import Repugnant, STATE_DISCOUNT
from vigil.core import SpottingBoard, Spotting
from vigil.theoros import Theoros
from vigil.peerwatch import PeerWatch


class RepugnantTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="repugnant_test_"))
        self.guard = CommandGuard(key=b"repugnant-test-key-0123456789ab")
        self.reg = Repugnant(path=str(self._tmp / "repugnant.jsonl"),
                             guard=self.guard)

    def test_signed_append_only_snapshot(self):
        rec = self.reg.observe("viper", "tilted", confidence=0.4,
                               frustration=0.85, observed_by="shepherd",
                               note="over-committed")
        self.assertTrue(self.reg.verify_record(rec))
        self.assertTrue(self.reg.verify()["ok"])
        # tamper: rewrite the state, signature must fail
        rec["state"] = "confident"
        self.assertFalse(self.reg.verify_record(rec))

    def test_state_discounts(self):
        self.assertEqual(self.reg.state_discount("never-seen"), 1.0)
        self.reg.observe("viper", "tilted", observed_by="shepherd")
        self.assertEqual(self.reg.state_discount("viper"),
                         STATE_DISCOUNT["tilted"])
        self.reg.observe("viper", "focused", observed_by="shepherd")
        self.assertEqual(self.reg.state_discount("viper"),
                         STATE_DISCOUNT["focused"])

    def test_unsettled_demands_evidence_not_conviction(self):
        self.reg.observe("wrapper", "burnt_out", observed_by="shepherd")
        self.reg.observe("viper", "confident", observed_by="shepherd")
        unsettled = self.reg.unsettled()
        names = {u["subject"] for u in unsettled}
        self.assertIn("wrapper", names)
        self.assertNotIn("viper", names)
        self.assertLess(unsettled[0]["discount"], 1.0)

    def test_unknown_state_rejected(self):
        with self.assertRaises(ValueError):
            self.reg.observe("viper", "angsty", observed_by="shepherd")

    def test_board_prices_tilted_hero(self):
        """Same claim, same confidence: the calm scout beats the tilted one —
        the 4th register prices what the market can't see."""
        board = SpottingBoard(repugnant=self.reg)
        self.reg.observe("calm", "confident", observed_by="shepherd")
        self.reg.observe("hero", "tilted", observed_by="shepherd")
        s1 = Spotting(id="phm_a", ts="1.0", source="calm",
                      kind="scout_event", target="target_a",
                      confidence=0.9, strength=1.0)
        s2 = Spotting(id="phm_b", ts="2.0", source="hero",
                      kind="scout_event", target="target_a",
                      confidence=0.9, strength=1.0)
        res1 = board.bid(s1)
        res2 = board.bid(s2)
        self.assertTrue(res1.accepted)         # calm claims first
        self.assertFalse(res2.accepted)        # tilted hero outbid
        self.assertEqual(res2.reason, "outbid")
        # the claim stays with the calm scout — priority never flipped
        self.assertEqual(board.claims["target_a"]["agent_id"], "calm")
        # and the emotional weight is visible in the geometry
        self.assertEqual(res1.geometry["emotional_weight"], 1.0)
        self.assertLess(res2.geometry["emotional_weight"], 1.0)

    def test_theoros_reads_the_fourth_register(self):
        class FakeStore:
            def read_all(self):
                return []

        class FakeBus:
            def get_message_log(self, n=50):
                return []

        self.reg.observe("wrapper", "burnt_out", observed_by="shepherd")
        self.reg.observe("viper", "confident", observed_by="shepherd")
        watch = PeerWatch(guard=self.guard)
        theoros = Theoros(store=FakeStore(), bus=FakeBus(), guard=self.guard,
                          receipts=None, peer_watch=watch,
                          repugnant=self.reg)
        reading = theoros.observe()
        names = {u["subject"] for u in reading.unsettled}
        self.assertIn("wrapper", names)
        self.assertNotIn("viper", names)
        self.assertIn("unsettled: wrapper", reading.render())


if __name__ == "__main__":
    unittest.main()