"""Tests for the Brown faction — the surprise third faction in the arena.

THE SHIT SHOVELER drops in after the teams fight and audits BOTH sides:
  - solo, neither team can account for the other's traffic on the shared
    bus -> ghosts -> WAVERING/CORRUPT (pants down)
  - united, the union of stores claims every publish -> chain walks clean
  - the register never lies: bullshit and unsettled states survive
    unification (residue the unified ledger doesn't launder)

Hermetic: builds two tiny stores + a fake bus with cross traffic, no
disk state beyond the temp stores.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.expanduser("~"))
sys.path.insert(0, os.path.expanduser("~/vigil"))

from vigil.brown import BrownHat  # noqa: E402
from vigil.theoros import TheorosReading  # noqa: E402


class FakeBus:
    """Minimal bus: publishes carry msg_id + agent_id, appended to a log."""

    def __init__(self):
        self.log = []

    def publish(self, msg_id, agent_id):
        self.log.append({"type": "publish", "msg_id": msg_id,
                         "agent_id": agent_id})

    def get_message_log(self, _n=0):
        return list(self.log)


class FakeStore:
    """Minimal pheromone store: records claim bus msg_ids."""

    def __init__(self, path):
        self.store_path = path
        self.records = []

    def read_all(self):
        return list(self.records)


class BrownAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="brown_test_")
        self.bus = FakeBus()
        self.red_store = FakeStore(os.path.join(self.tmp, "red.jsonl"))
        self.blue_store = FakeStore(os.path.join(self.tmp, "blue.jsonl"))

        # red publishes 3 claims; blue publishes 2. Cross traffic on
        # one shared bus — the classic arena shape.
        for i in range(3):
            self.bus.publish(f"red_{i}", "viper")
            self.red_store.records.append(
                {"id": f"r{i}", "source": "viper",
                 "payload": {"bus_msg_id": f"red_{i}",
                             "signature": "sig"}})
        for i in range(2):
            self.bus.publish(f"blue_{i}", "bastion")
            self.blue_store.records.append(
                {"id": f"b{i}", "source": "bastion",
                 "payload": {"bus_msg_id": f"blue_{i}",
                             "signature": "sig"}})

        self.brown = BrownHat(stores=[self.red_store, self.blue_store],
                              bus=self.bus)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reading(self, corrupt=None, unsettled=None):
        """A TheorosReading with optional register stink."""
        return TheorosReading(
            corrupt_speakers=corrupt or [],
            unsettled=unsettled or [],
        )

    def test_solo_audits_find_ghosts_pants_down(self):
        v = self.brown.audit(self._reading(), self._reading())
        # red's store alone can't account for blue's 2 publishes
        self.assertEqual(v.solo_red["ghosts"], 2)
        # blue's store alone can't account for red's 3 publishes
        self.assertEqual(v.solo_blue["ghosts"], 3)
        # both are dirty solo
        self.assertGreater(v.solo_red["dirt"], 0)
        self.assertGreater(v.solo_blue["dirt"], 0)

    def test_united_chain_walks_clean(self):
        v = self.brown.audit(self._reading(), self._reading())
        self.assertEqual(v.united["ghosts"], 0)
        self.assertTrue(v.chain["chain_walks"])
        self.assertEqual(v.chain["publishes"], 5)
        self.assertEqual(v.chain["claimed"], 5)
        self.assertIn("UNITE", v.unify_or_get_humped)

    def test_register_residue_survives_unification(self):
        red_stink = [{"actor": "wrapper", "message": "trust me, everyone "
                       "knows this works", "deception_risk": 0.8}]
        v = self.brown.audit(self._reading(corrupt=red_stink),
                             self._reading())
        # unified ledger cleared the ghosts but the bullshit remains
        self.assertEqual(v.united["ghosts"], 0)
        self.assertGreater(v.united["register_hits"], 0)
        self.assertIn("residue", v.unify_or_get_humped)

    def test_strike_the_fork_verifies_claims(self):
        ok = self.brown.strike_the_fork(
            {"payload": {"bus_msg_id": "red_1"}})
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["record"], "r1")
        miss = self.brown.strike_the_fork(
            {"payload": {"bus_msg_id": "ghost_claim"}})
        self.assertFalse(miss["ok"])

    def test_smell_the_register_catches_bullshit_and_unsettled(self):
        reading = self._reading(
            corrupt=[{"actor": "viper", "message": "we have this in the bag",
                      "deception_risk": 0.75}],
            unsettled=[{"agent": "viper", "state": "tilted",
                        "discount": 0.5}],
        )
        stink = self.brown.smell_the_register(reading)
        kinds = {h["kind"] for h in stink}
        self.assertEqual(kinds, {"bullshit", "unsettled"})

    def test_clean_solo_verdict_when_no_cross_traffic(self):
        # no cross traffic: every publish claimed by its own store, no
        # register stink -> the solo audit is CLEAN
        bus = FakeBus()
        rs = FakeStore(os.path.join(self.tmp, "only.jsonl"))
        bus.publish("a", "viper")
        rs.records.append({"id": "a", "source": "viper",
                           "payload": {"bus_msg_id": "a", "signature": "s"}})
        brown = BrownHat(stores=[rs], bus=bus)
        v = brown.audit(self._reading(), self._reading())
        self.assertEqual(v.solo_red["ghosts"], 0)
        self.assertEqual(v.solo_red["verdict"], "CLEAN")


if __name__ == "__main__":
    unittest.main()