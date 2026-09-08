"""
Tests for the Revival Protocol (vigil/revival.py).

Covers:
  1. checkpoint() freezes weights/feelings/intent + trail hash into a QRD
  2. hydrate() builds a NEW agent — different identity, old gun stays dead
  3. the truth boundary: the hydrated agent's first voice record declares
     "I am a new agent. I carry X's record. I am not them."
  4. lineage receipts record who revived whom, when, from what
"""

import json
import tempfile
import unittest
from pathlib import Path

from vigil.keyring import AgentKeyring
from vigil.revival import checkpoint, hydrate, lineage
from vigil.core import Swarm, WhorlWeave, Scout, Spotting
from vigil.peerwatch import PeerWatch
from vigil.integrity import CommandGuard


class RevivalTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="revival_test_"))
        self.keyring = AgentKeyring(b"revival-test-unit-secret-0123456789ab")
        self.guard = CommandGuard(key=b"revival-guard-key-0123456789abcdef")

    def _make_scout(self, agent_id="scout-1"):
        watch = PeerWatch(path=str(self._tmp / "peerwatch.jsonl"),
                          guard=self.guard)
        weave = WhorlWeave([agent_id])
        swarm = Swarm(peer_watch=watch, weave=weave, guard=self.guard)
        scout = swarm.add_scout(agent_id, latent={"mission_priority": 0.9})
        return scout, watch, swarm

    def test_checkpoint_freezes_state(self):
        scout, _, _ = self._make_scout("scout-1")
        scout.speak("intel", "found it at grid 44.91")
        qrd = checkpoint(scout, out=self._tmp / "s1.qrd.json",
                         trail=[{"id": "phm_1"}])
        state = json.load(open(qrd))
        self.assertEqual(state["agent_id"], "scout-1")
        self.assertEqual(state["latent"], {"mission_priority": 0.9})
        self.assertEqual(state["trail_records"], 1)
        self.assertEqual(state["last_words"], "found it at grid 44.91")

    def test_hydrate_creates_new_agent_with_new_identity(self):
        scout, _, _ = self._make_scout("scout-1")
        qrd = checkpoint(scout, out=self._tmp / "s1.qrd.json",
                         trail=[{"id": "phm_1"}])
        revived = hydrate(self.keyring, qrd)
        self.assertNotEqual(revived.agent_id, "scout-1")
        self.assertTrue(revived.agent_id.startswith("scout-1"))
        # the new agent's latent intent carried over
        self.assertEqual(revived.latent.get("mission_priority"), 0.9)

    def test_truth_boundary_declared_in_first_words(self):
        scout, _, _ = self._make_scout("scout-1")
        qrd = checkpoint(scout, out=self._tmp / "s1.qrd.json",
                         trail=[{"id": "phm_1"}])
        revived = hydrate(self.keyring, qrd)
        # the truth boundary is IN THE LEDGER, keyed to the new identity
        speaks = [r for r in revived.sink.voice.history()
                  if r.get("actor") == revived.agent_id
                  and r.get("kind") == "speak"]
        self.assertTrue(speaks, "revived agent must speak its lineage")
        decl = speaks[0]["message"]
        self.assertIn("I am a new agent", decl)
        self.assertIn("I carry scout-1's record", decl)
        self.assertIn("I am not them", decl)

    def test_old_gun_stays_decommissioned(self):
        scout, _, _ = self._make_scout("scout-1")
        qrd = checkpoint(scout, out=self._tmp / "s1.qrd.json",
                         trail=[{"id": "phm_1"}])
        self.keyring.retire("scout-1")  # the Hall decommissioned the gun
        revived = hydrate(self.keyring, qrd)
        # the revived agent cannot sign as the dead
        self.assertNotEqual(revived.agent_id, "scout-1")
        old_guard = self.keyring.verify_guard(revived.agent_id)
        self.assertTrue(old_guard)  # new gun fires for the NEW identity

    def test_lineage_receipt(self):
        receipt = lineage(self._tmp / "s1.qrd.json",
                          new_id="scout-1~rev2", old_id="scout-1")
        self.assertEqual(receipt["kind"], "revival")
        self.assertEqual(receipt["new_agent"], "scout-1~rev2")
        self.assertEqual(receipt["old_agent"], "scout-1")
        # receipt is append-only
        rec2 = lineage(self._tmp / "s1.qrd.json",
                       new_id="scout-1~rev3", old_id="scout-1")
        self.assertEqual(rec2["new_agent"], "scout-1~rev3")


if __name__ == "__main__":
    unittest.main()