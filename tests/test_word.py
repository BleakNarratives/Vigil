"""Tests for THE WORD — Onboarding 2.0.

The Word is a ceremony with an audit trail: every sentence it speaks is
derived from the actual ledger, and when the ledger has nothing to say,
the Word SAYS SO. No filler, no fabrication — the swarm formed itself,
and the Word is what it can prove.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~"))
sys.path.insert(0, os.path.expanduser("~/vigil"))

from vigil.bind import BindRegistry  # noqa: E402
from vigil.undercurrent import Undercurrent  # noqa: E402
from vigil.word import speak_the_word, ceremony  # noqa: E402
from vigil.zgents import ZgentRegistry  # noqa: E402


class WordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="word_test_")
        self.uc = Undercurrent(os.path.join(self.tmp, "uc.jsonl"))
        self.z = ZgentRegistry(os.path.join(self.tmp, "zgents.jsonl"),
                               undercurrent=self.uc)
        self.bind = BindRegistry(os.path.join(self.tmp, "binds.jsonl"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_word_is_auditable(self):
        self.z.register("viper", role="red scout")
        self.z.update_standing("viper", 0.87)
        word = speak_the_word("viper", zgents=self.z, undercurrent=self.uc,
                              bind=self.bind)
        # every claim has a derivation source
        self.assertEqual(len(word["derivations"]), 4)
        sources = {d["source"] for d in word["derivations"]}
        self.assertIn("zgents.registry", sources)
        # the knowledge source is either the pool (if claims inherited)
        # or the honest "pool is empty" — either way it's a real source
        self.assertTrue(any("undercurrent" in s for s in sources))
        self.assertIn("bind.resolve()", sources)
        # and the words carry the real standing, not a script
        self.assertIn("0.87", word["words"])
        self.assertIn("red scout", word["words"])

    def test_word_declares_first_of_line_honestly(self):
        self.z.register("fresh_letter")
        word = speak_the_word("fresh_letter", zgents=self.z,
                              undercurrent=self.uc, bind=self.bind)
        self.assertIn("first of your line", word["words"])

    def test_word_says_nothing_when_there_is_nothing(self):
        # no inherited knowledge in the current, no record, no bind:
        # the Word says "you are born knowing nothing yet" — honesty
        # over comfort, never a fabricated history
        self.z.register("blank_letter")
        word = speak_the_word("blank_letter", zgents=self.z,
                              undercurrent=self.uc, bind=self.bind)
        self.assertIn("born knowing nothing yet", word["words"])
        self.assertNotIn("0.87", word["words"])

    def test_word_names_inherited_knowledge_with_evidence(self):
        cid = self.uc.absorb("the charge is revocable",
                             evidence="keyring.is_retired path",
                             source="viper")
        self.uc.confirm(cid, "ravage")
        self.uc.confirm(cid, "wrapper")  # crosses the monkey threshold
        self.z.register("newborn")
        self.z.born_with("newborn", [cid])
        word = speak_the_word("newborn", zgents=self.z,
                              undercurrent=self.uc, bind=self.bind)
        self.assertIn("the charge is revocable", word["words"])
        self.assertIn("born knowing 1 claims", word["words"])

    def test_word_recites_bind_law(self):
        self.bind.bind("viper", "ravage", 0.4)
        self.z.register("viper")
        word = speak_the_word("viper", zgents=self.z, undercurrent=self.uc,
                              bind=self.bind)
        self.assertIn("at most half of your self", word["words"])
        self.assertIn("retain 60%", word["words"])

    def test_word_reads_lineage_from_qrd(self):
        from vigil.revival import checkpoint
        from vigil.core import PheromoneSink, Scout, SpottingBoard
        sink = PheromoneSink(store=None, event_bus=None, guard=None)
        board = SpottingBoard(weave=None)
        scout = Scout("old_scout", sink, weave=None, board=board)
        qrd = checkpoint(scout, trail=[], out=Path(self.tmp, "old.qrd.json"))
        word = speak_the_word("old_scout~rev2", zgents=self.z,
                              undercurrent=self.uc, qrd=qrd, bind=self.bind)
        self.assertIn("carry old_scout's record", word["words"])
        self.assertIn("You are not them", word["words"])

    def test_ceremony_records_first_act_on_roll(self):
        self.z.register("newborn")
        ceremony("newborn", zgents=self.z, undercurrent=self.uc,
                 bind=self.bind)
        profile = self.z.lookup("newborn")
        self.assertEqual(profile["acts"], 1)
        self.assertIn("heard the Word", profile["history"][0]["action"])


if __name__ == "__main__":
    unittest.main()