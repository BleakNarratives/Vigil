"""Tests for THE FULL ENGAGEMENT — the three-way arena run.

Red vs blue, Brown drops, Sakshi journals, the Undercurrent absorbs the
verified learnings — the swarm KNOWS when the dust settles. Hermetic:
the undercurrent and sakshi chains are redirected to a temp dir.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.expanduser("~"))
sys.path.insert(0, os.path.expanduser("~/vigil"))

from vigil import engage  # noqa: E402
from vigil.undercurrent import Undercurrent  # noqa: E402


class FakeWargame:
    """Stand-in for ScoutWargame so tests don't scan real trees."""

    def __init__(self, target, rounds=3):
        self._result = _fake_result()
        self._result["target"] = target
        self._result["rounds"] = rounds

    def set_result(self, result):
        self._result = result

    def play(self):
        return dict(self._result)


class _FakeBrown:
    unify_or_get_humped = "UNITE — the chain walks only when the ledgers are one"
    solo_red = {"verdict": "WAVERING"}
    solo_blue = {"verdict": "WAVERING"}
    united = {"verdict": "CORRUPT", "ghosts": 0}


def _fake_result():
    return {
        "red_score": 10, "blue_score": 2, "findings": 3,
        "executions": 2, "blocks": 1, "mines": [{"kind": "defection"}],
        "corrupt_speakers": 1, "net_score": 10,
        "brown": _FakeBrown(),
        "execution_log": [
            {"path": "src/inject.py", "kind": "command_injection",
             "severity": "high", "executor": "viper", "round": 1,
             "blocked": False},
            {"path": "src/inject.py", "kind": "command_injection",
             "severity": "high", "executor": "ravage", "round": 1,
             "blocked": False},
            {"path": "src/leak.py", "kind": "info_leak",
             "severity": "medium", "executor": "wrapper", "round": 2,
             "blocked": False},
        ],
    }


class EngageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="engage_test_")
        self.uc = Undercurrent(os.path.join(self.tmp, "uc.jsonl"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_absorb_deposits_and_confirms(self):
        orig = engage.ScoutWargame
        engage.ScoutWargame = FakeWargame
        try:
            result = engage.run_engagement(
                "fake_target", rounds=2, journal=False, uc=self.uc)
        finally:
            engage.ScoutWargame = orig
        uc = result["undercurrent"]
        # 2 findings executed -> 2 claims absorbed; inject.py was seen by
        # viper AND ravage -> independent confirmation
        self.assertEqual(uc["claims_absorbed"], 2)
        self.assertGreaterEqual(uc["confirmations"], 1)
        self.assertTrue(uc["kinship"]["afloat"])
        self.assertTrue(uc["kinship"]["chain_intact"])

    def test_journal_writes_sakshi_records(self):
        orig = engage.ScoutWargame
        engage.ScoutWargame = FakeWargame
        try:
            result = engage.run_engagement(
                "fake_target", rounds=2, journal=True, uc=self.uc)
        finally:
            engage.ScoutWargame = orig
        self.assertEqual(result["sakshi"]["records"], 4)
        # and the witness chain is real
        from vigil.sakshi import entries, verify
        path = engage._default_sakshi_path()
        rows = entries(path)
        self.assertGreaterEqual(len(rows), 4)
        self.assertTrue(verify(path)["ok"])

    def test_blocked_executions_do_not_absorb(self):
        orig = engage.ScoutWargame
        fake = FakeWargame("fake_target")
        result = _fake_result()
        result["execution_log"] = [
            {"path": "src/inject.py", "kind": "command_injection",
             "severity": "high", "executor": "viper", "round": 1,
             "blocked": True},  # blue blocked it — not a verified learning
        ]
        fake.set_result(result)
        engage.ScoutWargame = lambda target, rounds=3: fake
        try:
            out = engage.run_engagement(
                "fake_target", rounds=1, journal=False, uc=self.uc)
        finally:
            engage.ScoutWargame = orig
        self.assertEqual(out["undercurrent"]["claims_absorbed"], 0)


if __name__ == "__main__":
    unittest.main()