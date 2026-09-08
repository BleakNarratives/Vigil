"""Tests for THE ZGENT REGISTRY + the wired-in species memory.

The alphabet made personal:
  - every letter has a name, standing, history, and inherited knowledge
  - revival's checkpoint freezes the current's inherited pool; hydrate
    reborn a revived scout knowing BOTH the checkpoint's claims and
    whatever the current accumulated since (capillary ingestion)
  - Theoros reads the Undercurrent's kinship shiver as the 5th surface
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~"))
sys.path.insert(0, os.path.expanduser("~/vigil"))

from vigil.undercurrent import Undercurrent  # noqa: E402
from vigil.zgents import ZgentRegistry  # noqa: E402


class ZgentRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="zgents_test_")
        self.uc = Undercurrent(os.path.join(self.tmp, "uc.jsonl"))
        self.z = ZgentRegistry(os.path.join(self.tmp, "zgents.jsonl"),
                               undercurrent=self.uc)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_register_and_roster(self):
        self.z.register("viper", role="red scout")
        self.z.register("bastion", role="blue defender")
        self.assertEqual(len(self.z.roster()), 2)
        p = self.z.lookup("viper")
        self.assertEqual(p["role"], "red scout")
        self.assertEqual(p["standing"], 0.0)
        self.assertEqual(p["status"], "alive")

    def test_standing_and_history_accrue(self):
        self.z.register("viper")
        self.z.update_standing("viper", 0.87)
        self.z.act("viper", "executed command injection finding")
        self.z.act("viper", "earned molt token")
        p = self.z.lookup("viper")
        self.assertEqual(p["standing"], 0.87)
        self.assertEqual(p["acts"], 2)
        self.assertEqual(len(p["history"]), 2)

    def test_inherited_knowledge_resolves_from_current(self):
        cid = self.uc.absorb("the charge is revocable", source="viper")
        self.uc.confirm(cid, "ravage")
        self.uc.confirm(cid, "wrapper")  # crosses the monkey threshold
        self.z.register("fresh_letter")
        self.z.born_with("fresh_letter", [cid])
        inherited = self.z.inherited_knowledge("fresh_letter")
        self.assertEqual(len(inherited), 1)
        self.assertEqual(inherited[0]["claim"], "the charge is revocable")
        self.assertTrue(inherited[0]["inherited"])

    def test_lineage_declares_truth_boundary(self):
        self.z.register("viper~rev2")
        self.z.lineage("viper~rev2", old_id="viper",
                       trail_hash="deadbeef")
        p = self.z.lookup("viper~rev2")
        self.assertEqual(p["lineage"]["old_id"], "viper")
        self.assertEqual(p["lineage"]["trail_hash"], "deadbeef")

    def test_retire_keeps_record_on_the_roll(self):
        self.z.register("wrapper")
        self.z.act("wrapper", "talked bullshit")
        self.z.retire("wrapper", reason="hall of the devine")
        p = self.z.lookup("wrapper")
        self.assertEqual(p["status"], "retired")
        self.assertEqual(p["acts"], 1)  # the record survives

    def test_ledger_screams_on_tamper(self):
        self.z.register("viper")
        path = os.path.join(self.tmp, "zgents.jsonl")
        with open(path) as f:
            lines = f.read().splitlines()
        forged = json.loads(lines[0])
        forged["agent_id"] = "EVE"
        lines[0] = json.dumps(forged)
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        self.assertFalse(self.z.verify()["ok"])


class RevivalSpeciesMemory(unittest.TestCase):
    """checkpoint freezes the current; hydrate reborns knowing both the
    frozen claims and whatever the current accumulated since."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="revive_uc_test_")
        self.uc = Undercurrent(os.path.join(self.tmp, "uc.jsonl"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _scout(self, agent_id):
        from vigil.core import PheromoneSink, Scout, SpottingBoard
        sink = PheromoneSink(store=None, event_bus=None, guard=None)
        board = SpottingBoard(weave=None)
        return Scout(agent_id, sink, weave=None, board=board)

    def test_checkpoint_freezes_inherited_claims(self):
        from vigil.revival import checkpoint
        cid = self.uc.absorb("honest claim", source="viper")
        self.uc.confirm(cid, "ravage")
        self.uc.confirm(cid, "wrapper")  # inherited now
        scout = self._scout("viper")
        out = checkpoint(scout, trail=[], out=Path(self.tmp, "viper.qrd.json"),
                         undercurrent=self.uc)
        state = json.load(open(out))
        self.assertIn(cid, state["inherited_claims"])

    def test_hydrate_reborn_knowing_current(self):
        from vigil.revival import checkpoint, hydrate
        from vigil.keyring import AgentKeyring
        cid = self.uc.absorb("the city walls are loose", source="viper")
        self.uc.confirm(cid, "ravage")
        self.uc.confirm(cid, "wrapper")
        scout = self._scout("viper")
        qrd = checkpoint(scout, trail=[], out=Path(self.tmp, "viper.qrd.json"),
                         undercurrent=self.uc)
        keyring = AgentKeyring(b"test-secret")
        # a NEW claim lands in the current AFTER the checkpoint froze
        late = self.uc.absorb("molt is won not granted", source="ravage")
        self.uc.confirm(late, "wrapper")
        self.uc.confirm(late, "viper")
        revived = hydrate(keyring, qrd, new_id="viper~rev2",
                          undercurrent=self.uc)
        inherited = revived.latent.get("_inherited", [])
        # born knowing BOTH the frozen claim and the late one
        self.assertIn(cid, inherited)
        self.assertIn(late, inherited)


class TheorosKinshipSurface(unittest.TestCase):
    def test_kinship_appears_in_reading(self):
        from vigil.theoros import Theoros
        tmp = tempfile.mkdtemp(prefix="theoros_uc_")
        try:
            uc = Undercurrent(os.path.join(tmp, "uc.jsonl"))
            cid = uc.absorb("we know things now", source="viper")
            uc.confirm(cid, "ravage")
            uc.confirm(cid, "wrapper")
            t = Theoros(undercurrent=uc)
            reading = t.observe()
            self.assertIsNotNone(reading.kinship)
            self.assertTrue(reading.kinship["afloat"])
            self.assertEqual(reading.kinship["inherited"], 1)
            rendered = reading.render()
            self.assertIn("kinship:", rendered)
            self.assertIn("the swarm knows itself", rendered)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()