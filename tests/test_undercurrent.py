"""Tests for THE UNDER CURRENT — the swarm's genetic memory.

The operator's ask, verified:
  - one scout's learning is INFORMATION; N independent confirmations make
    it INHERITED (the 100th monkey, made a number)
  - hydrate() wicks inherited knowledge into new/revived scouts
    (capillary ingestion — water seeks level, nobody teaches)
  - kinship() is the shiver: a measurable liveness signal
  - the sha256 spine screams on tamper
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.expanduser("~"))
sys.path.insert(0, os.path.expanduser("~/vigil"))

from vigil.undercurrent import MONKEY_THRESHOLD, Undercurrent  # noqa: E402


class UndercurrentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="uc_test_")
        self.path = os.path.join(self.tmp, "undercurrent.jsonl")
        self.uc = Undercurrent(self.path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_absorb_is_information_not_memory(self):
        cid = self.uc.absorb("subprocess(shell=True) is reachable",
                             evidence="found in src/core", source="viper")
        # below threshold: not inherited yet — information, not memory
        self.assertEqual(self.uc.confirmations(cid), 1)
        self.assertEqual(self.uc.knowledge(), [])

    def test_confirmation_accretes_toward_threshold(self):
        cid = self.uc.absorb("unvalidated redirect in login flow",
                             source="ravage")
        self.uc.confirm(cid, "wrapper")
        self.assertEqual(self.uc.confirmations(cid), 2)
        self.assertEqual(self.uc.knowledge(), [])  # still not enough
        self.uc.confirm(cid, "viper")  # third monkey
        pool = self.uc.knowledge()
        self.assertEqual(len(pool), 1)
        self.assertTrue(pool[0]["inherited"])

    def test_threshold_is_the_sorites_answer(self):
        # the pile/sand question: at what point does a fact become memory?
        # Answer: exactly at MONKEY_THRESHOLD confirmations.
        cid = self.uc.absorb("secrets leak via debug endpoints", source="a")
        for m in ("b", "c", "d", "e"):
            self.uc.confirm(cid, m)
        pool = self.uc.knowledge()
        self.assertEqual(len(pool), 1)
        self.assertEqual(len(pool[0]["confirmers"]), 5)

    def test_hydrate_wicks_inherited_pool(self):
        cid = self.uc.absorb("readable world-state via /api/state",
                             source="viper")
        self.uc.confirm(cid, "ravage")
        # absorb counts as the first monkey; 2 total = below threshold,
        # so a new scout is born knowing nothing yet
        self.assertEqual(self.uc.hydrate("fresh_scout"), [])
        # third monkey crosses it — the 100th monkey, at three
        self.uc.confirm(cid, "wrapper")
        pool = self.uc.hydrate("fresh_scout")
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[0]["claim"],
                         "readable world-state via /api/state")

    def test_level_is_the_gradient(self):
        cid = self.uc.absorb("the charge is revocable", source="viper")
        self.uc.confirm(cid, "ravage")
        self.uc.confirm(cid, "wrapper")
        # a scout that already knows it is at level; one that doesn't
        # has a gradient — water seeks level toward it
        self.assertEqual(self.uc.level(known=[cid]), [])
        self.assertEqual(len(self.uc.level(known=[])), 1)

    def test_kinship_is_the_shiver(self):
        cid = self.uc.absorb("the chain is durable", source="viper")
        self.uc.confirm(cid, "ravage")
        self.uc.confirm(cid, "wrapper")
        shiver = self.uc.kinship()
        self.assertTrue(shiver["afloat"])
        self.assertTrue(shiver["chain_intact"])
        self.assertEqual(shiver["pool"], 1)
        self.assertEqual(shiver["inherited"], 1)
        self.assertEqual(shiver["threshold"], MONKEY_THRESHOLD)

    def test_chain_screams_on_tamper(self):
        self.uc.absorb("honest claim", source="viper")
        self.uc.absorb("another honest claim", source="ravage")
        # forge: rewrite the first record's claim in place
        path = self.path
        with open(path) as f:
            lines = f.read().splitlines()
        forged = json.loads(lines[0])
        forged["claim"] = "LIAR: this was rewritten"
        lines[0] = json.dumps(forged)
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        verdict = self.uc.verify()
        self.assertFalse(verdict["ok"])
        # and the shiver knows the ship is NOT afloat
        self.assertFalse(self.uc.kinship()["afloat"])

    def test_memory_only_version_in_memory(self):
        uc = Undercurrent()  # no path — memory only, still chained
        cid = uc.absorb("in-memory knowledge", source="viper")
        self.uc_ = uc
        uc.confirm(cid, "ravage")
        uc.confirm(cid, "wrapper")
        self.assertEqual(len(uc.knowledge()), 1)
        self.assertTrue(uc.verify()["ok"])


if __name__ == "__main__":
    unittest.main()