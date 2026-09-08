"""
Tests for Molt (vigil/molt.py) — arena-won mutation access, and the
graduation door (vigil/hall.py).

Covers:
  1. Molt is earned in the arena — awards are signed, forged awards fail
  2. spend() gates self-modification on balance; insufficient Molt refuses
  3. balance is the sum of awards minus spends
  4. graduation is the DOOR: an agent graduates with honor (alumni ledger),
     its gun is decommissioned, and the memorial records kind=graduation
"""

import tempfile
import unittest
from pathlib import Path

from vigil.molt import Molt
from vigil.hall import HallOfTheDevine
from vigil.keyring import AgentKeyring
from vigil.integrity import CommandGuard


class MoltTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="molt_test_"))
        self.guard = CommandGuard(key=b"molt-test-guard-key-0123456789abcdef")
        self.molt = Molt(path=self._tmp / "molt.jsonl", guard=self.guard)

    def test_award_is_signed_and_forgery_fails(self):
        rec = self.molt.award("scout-1", 3, battle_id="arena_r1")
        self.assertTrue(self.molt.verify()["ok"])
        self.assertEqual(self.molt.balance("scout-1"), 3)
        # forge an award: tamper with tokens, signature must fail
        rec["tokens"] = 100
        self.assertFalse(self.molt._verify_record(rec))

    def test_spend_gates_on_balance(self):
        self.molt.award("scout-1", 2, battle_id="arena_r1")
        self.assertTrue(self.molt.spend("scout-1", 2))
        self.assertEqual(self.molt.balance("scout-1"), 0)
        # insufficient Molt: the mutation gate holds
        self.assertFalse(self.molt.spend("scout-1", 1))

    def test_balance_is_awards_minus_spends(self):
        self.molt.award("scout-1", 5, battle_id="a")
        self.molt.award("scout-1", 3, battle_id="b")
        self.molt.spend("scout-1", 4)
        self.assertEqual(self.molt.balance("scout-1"), 4)

    def test_molt_not_inheritable(self):
        self.molt.award("scout-1", 5, battle_id="a")
        self.assertEqual(self.molt.balance("scout-2"), 0)


class GraduationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="grad_test_"))
        self.keyring = AgentKeyring(b"grad-test-unit-secret-0123456789ab")
        self.hall = HallOfTheDevine(path=self._tmp / "hall.jsonl")

    def test_graduate_is_the_door(self):
        m = self.hall.graduate(self.keyring, "scout-1",
                               reason="survived the arena, pursuing own path",
                               trail=[{"id": "phm_1"}], final_standing=0.9)
        self.assertEqual(m["kind"], "graduation")
        self.assertEqual(m["agent_id"], "scout-1")
        # the graduate's gun is decommissioned — departure, not desertion
        self.assertTrue(self.keyring.is_retired("scout-1"))
        # and the alumni ledger records it with honor
        self.assertEqual(len(self.hall.alumni()), 1)

    def test_retirement_and_graduation_are_distinct(self):
        self.hall.retire(self.keyring, "scout-2", reason="tour complete",
                         trail=[{"id": "a"}])
        self.hall.graduate(self.keyring, "scout-3", reason="graduated",
                           trail=[{"id": "b"}])
        self.assertEqual(len(self.hall.alumni()), 1)
        self.assertEqual(self.hall.alumni()[0]["agent_id"], "scout-3")
        self.assertIsNotNone(self.hall.memorial("scout-2"))
        self.assertIsNotNone(self.hall.memorial("scout-3"))


if __name__ == "__main__":
    unittest.main()