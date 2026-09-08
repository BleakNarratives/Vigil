"""
Tests for the Hall of the Devine (vigil/hall.py) — the retirement protocol.

Covers:
  1. retire() decommissions the gun BEFORE hanging the memorial — a retired
     agent's signatures are refused (RoboCop's law)
  2. memorials are append-only and bound to the agent's trail hash — the
     archive cannot drift into legend
  3. verify() proves the memorial matches the ACTUAL trail; a mismatched
     trail is reported loudly, never smoothed over
  4. retirement is forever — no un-retire path exists
"""

import json
import tempfile
import unittest
from pathlib import Path

from vigil.hall import HallOfTheDevine
from vigil.keyring import AgentKeyring, derive_agent_key
from vigil.integrity import CommandGuard


class HallTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="hall_test_"))
        self.keyring = AgentKeyring(b"hall-test-unit-secret-0123456789ab")
        self.hall = HallOfTheDevine(path=self._tmp / "hall.jsonl")

    def test_retire_decommissions_gun_before_memorial(self):
        gun = self.keyring.issue("scout-1")
        from vigil.core import Spotting
        spotting = Spotting(id="phm_1", ts="1.0", source="scout-1",
                            kind="k", target="t", confidence=0.5, strength=1.0)
        gun.sign(spotting)  # signs in place, returns the sig string
        self.assertTrue(self.keyring.verify_guard("scout-1").verify(spotting))
        # retire: the gun dies, then the memorial hangs
        self.hall.retire(self.keyring, "scout-1", reason="tour complete",
                         trail=[{"id": "phm_1"}], final_standing=0.8)
        self.assertTrue(self.keyring.is_retired("scout-1"))
        with self.assertRaises(RuntimeError):
            self.keyring.verify_guard("scout-1")  # dead do not sign

    def test_memorial_bound_to_trail_hash(self):
        trail = [{"id": "phm_1", "kind": "spot"}, {"id": "phm_2", "kind": "bid"}]
        m = self.hall.retire(self.keyring, "scout-2", reason="retired",
                             trail=trail, final_standing=0.9)
        self.assertEqual(m["trail_records"], 2)
        self.assertEqual(m["agent_id"], "scout-2")
        self.assertTrue(self.hall.verify("scout-2", trail)["ok"])

    def test_verify_reports_drift_loudly(self):
        trail = [{"id": "phm_1", "kind": "spot"}]
        self.hall.retire(self.keyring, "scout-3", reason="fell",
                         trail=trail)
        # the archive drifted: someone provides a different trail
        verdict = self.hall.verify("scout-3",
                                   [{"id": "phm_999", "kind": "legend"}])
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["reason"], "trail hash mismatch")
        # and no memorial for an unknown agent is reported honestly
        self.assertFalse(self.hall.verify("nobody", [])["ok"])

    def test_retirement_is_forever(self):
        self.hall.retire(self.keyring, "scout-4", reason="gone",
                         trail=[], final_standing=0.5)
        self.assertTrue(self.keyring.is_retired("scout-4"))
        # no un-retire path exists by design — check the class surface
        self.assertFalse(hasattr(self.keyring, "unretire"))
        self.assertFalse(hasattr(self.hall, "unretire"))

    def test_memorials_append_only(self):
        self.hall.retire(self.keyring, "scout-5", reason="one",
                         trail=[{"id": "a"}])
        self.hall.retire(self.keyring, "scout-6", reason="two",
                         trail=[{"id": "b"}])
        self.assertEqual(len(self.hall.memorials()), 2)
        self.assertIsNotNone(self.hall.memorial("scout-5"))
        self.assertIsNotNone(self.hall.memorial("scout-6"))


if __name__ == "__main__":
    unittest.main()