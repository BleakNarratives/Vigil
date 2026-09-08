"""
Tests for Culture-class effect weapons (vigil/mines.py).

Covers:
  1. DefectionMine.plan() — computed from the REAL PeerWatch market math
     (same constants, same recursive weighting), not an approximation
  2. RegisterMine — manufactured intel reads CLEAN to Knose (the honest
     blind spot, weaponized)
  3. too_deep() — overreach grading: CLEAN / OVERKILL / TOO_DEEP with cost
  4. deploy_mine() — full fire: real signed flags on the real ledger,
     grade reflects the blast
"""

import json
import tempfile
import unittest
from pathlib import Path

from vigil.knose import Knose
from vigil.peerwatch import PeerWatch, CONFIRM_REWARD
from vigil.mines import (DefectionMine, RegisterMine, too_deep, deploy_mine,
                         DEFECT_THRESHOLD, VAPORIZE_THRESHOLD)
from vigil.integrity import CommandGuard


class MinesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="mines_test_"))
        self.guard = CommandGuard(key=b"mines-test-key-0123456789ab")
        self.watch = PeerWatch(path=str(self._tmp / "peerwatch.jsonl"),
                               guard=self.guard)

    def test_plan_matches_real_market_after_firing(self):
        for _ in range(3):
            self.watch.vouch("shepherd", "bastion", "init_1", "trusted")
        pre = self.watch.weight("bastion")
        mine = DefectionMine(self.watch)
        plan = mine.plan("bastion", ["viper", "ravage", "wrapper"])
        # the plan predicts the post-fire weight BEFORE any flag lands
        predicted = plan["effective_weight"]
        # fire the plan through REAL signed flags
        for fl in plan["chain"]:
            self.watch.flag(fl, "bastion", "mine_1", "effect payload")
        post = self.watch.weight("bastion")
        # the pre-fire prediction must match the real post-fire market
        self.assertAlmostEqual(predicted, post, places=6)
        self.assertLess(post, pre)
        self.assertEqual(plan["defected"], post < DEFECT_THRESHOLD)

    def test_register_mine_walks_through_knose_clean(self):
        rm = RegisterMine(seed=2)
        result = rm.detonate()
        self.assertTrue(result["manufactured"])
        self.assertEqual(result["verdict"], "CLEAN")
        self.assertTrue(result["penetrated"])
        # and the honest disclaimer is attached
        self.assertIn("cannot catch a lie", result["note"])

    def test_too_deep_grades(self):
        clean = too_deep(1.0, 0.8)
        self.assertEqual(clean["verdict"], "CLEAN")
        self.assertEqual(clean["cost"], 0.0)
        overkill = too_deep(1.0, 0.4)
        self.assertEqual(overkill["verdict"], "OVERKILL")
        self.assertEqual(overkill["cost"], 0.5)
        deep = too_deep(1.0, 0.05)
        self.assertEqual(deep["verdict"], "TOO_DEEP")
        self.assertGreater(deep["cost"], 1.0)
        self.assertIn("too deep", deep["message"])

    def test_deploy_mine_full_fire(self):
        self.watch.vouch("shepherd", "bastion", "init_1", "trusted")
        result = deploy_mine(self.watch, "bastion",
                             flaggers=["viper", "ravage"], cohesion=1.0)
        self.assertIn("plan", result)
        self.assertIn("grade", result)
        self.assertIsInstance(result["defected"], bool)
        # flags really landed on the ledger
        self.assertTrue(any(r["kind"] == "flag" and r["target_agent"] == "bastion"
                            for r in self.watch.history()))

    def test_one_stranger_flag_does_not_flip(self):
        """A single flag from a clean stranger must NOT flip a defender —
        one flag: (1)/(1+1) = 0.5, above threshold. The mine needs either
        numbers (repeated flags from nobodies) or a corrupted hero."""
        mine = DefectionMine(self.watch)
        plan = mine.plan("bastion", ["viper"], max_flags=1)
        self.assertFalse(plan["defected"])
        self.assertGreater(plan["effective_weight"], DEFECT_THRESHOLD)

    def test_corrupted_hero_flips_with_fewer_flags_than_mob(self):
        """The Culture move: corrupt the hero, not the mob. A high-standing
        flagger (weight 2.0 via vouches) crosses the threshold with fewer
        flags than a clean nobody — one betrayal beats a crowd."""
        for _ in range(3):
            self.watch.vouch("shepherd", "bastion", "init_1", "trusted")
        for _ in range(3):
            self.watch.vouch("shepherd", "viper", "init_2", "hero")
        mine = DefectionMine(self.watch)
        hero_plan = mine.plan("bastion", ["viper"], max_flags=6)
        self.assertTrue(hero_plan["defected"])
        self.assertLess(hero_plan["effective_weight"], DEFECT_THRESHOLD)
        # a clean nobody needs more flags to do the same damage
        mob_plan = mine.plan("bastion", ["ravage"], max_flags=6)
        self.assertLessEqual(len(hero_plan["chain"]), len(mob_plan["chain"])
                             or mob_plan["defected"] is False)


if __name__ == "__main__":
    unittest.main()