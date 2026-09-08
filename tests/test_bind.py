"""Tests for THE BIND — the Zgent attribution geometry.

The operator's spec, verified as theorem:
  - the HALF-RULE: no unit may commit more than 50% of its self outward
  - the FOLD: re-extension passes at most half of holdings, so effective
    claims decay by powers of 1/2 per hop — the origin is never dissolved
  - the BIND: no coalition can hold a majority of any unit — the ledger
    REFUSES to mint the bind that would make a takeover possible
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.expanduser("~"))
sys.path.insert(0, os.path.expanduser("~/vigil"))

from vigil.bind import MAX_ATTRIBUTION, BindRegistry  # noqa: E402


class BindRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bind_test_")
        self.b = BindRegistry(os.path.join(self.tmp, "binds.jsonl"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- THE HALF-RULE --------------------------------------------------------

    def test_bind_under_half_is_allowed(self):
        bid = self.b.bind("viper", "ravage", 0.4)
        self.assertTrue(bid.startswith("bind_"))
        self.assertEqual(self.b.committed_total("viper"), 0.4)
        self.assertEqual(self.b.holdings_of("ravage"), 0.4)

    def test_bind_above_half_refused(self):
        with self.assertRaises(ValueError):
            self.b.bind("viper", "ravage", 0.6)
        self.assertEqual(self.b.committed_total("viper"), 0.0)

    def test_bind_that_would_let_coalition_reach_majority_refused(self):
        self.b.bind("viper", "ravage", 0.3)
        # 0.3 + 0.3 = 0.6 > 0.5 — the second bind would let a coalition
        # hold a majority of viper. The ledger refuses.
        with self.assertRaises(ValueError):
            self.b.bind("viper", "wrapper", 0.3)
        # the refusal is the theorem: committed stays at 0.3
        self.assertEqual(self.b.committed_total("viper"), 0.3)
        self.assertTrue(self.b.resolve("viper")["no_coalition_majority"])

    def test_multiple_binds_can_share_the_half(self):
        self.b.bind("viper", "ravage", 0.3)
        self.b.bind("viper", "wrapper", 0.2)  # 0.5 total — at the cap
        self.assertEqual(self.b.committed_total("viper"), 0.5)
        self.assertEqual(self.b.essential_floor("viper"), 0.5)
        # one more grain would break the law
        with self.assertRaises(ValueError):
            self.b.bind("viper", "lidarr", 0.01)

    # -- THE FOLD --------------------------------------------------------------

    def test_fold_halves_the_paper(self):
        self.b.bind("viper", "ravage", 0.5)
        self.b.extend("ravage", "wrapper", 0.5)  # half of what ravage holds
        # wrapper holds 0.25 of viper — folded once
        self.assertEqual(self.b.effective_claim("viper", "wrapper"), 0.25)

    def test_double_fold_quarters(self):
        self.b.bind("a", "b", 0.5)
        self.b.extend("b", "c", 0.5)
        self.b.extend("c", "d", 0.5)
        # three hops: 0.5^3 = 0.125 — the deepest node holds an eighth
        self.assertEqual(self.b.effective_claim("a", "d"), 0.125)

    def test_origin_never_dissolved(self):
        # even a maximal chain can't zero the origin — 0.5^k > 0 for all k
        self.b.bind("a", "b", 0.5)
        self.b.extend("b", "c", 0.5)
        self.b.extend("c", "d", 0.5)
        self.b.extend("d", "e", 0.5)
        self.b.extend("e", "f", 0.5)
        self.assertGreater(self.b.effective_claim("a", "f"), 0.0)
        # and the origin kept at least half of itself the whole time
        self.assertGreaterEqual(self.b.essential_floor("a"), 0.5)

    def test_extend_beyond_half_of_holdings_refused(self):
        self.b.bind("viper", "ravage", 0.4)
        # ravage may pass at most 0.5 * 0.4 = 0.2 onward
        with self.assertRaises(ValueError):
            self.b.extend("ravage", "wrapper", 0.6)
        self.assertEqual(self.b.holdings_of("wrapper"), 0.0)

    def test_extend_with_no_holdings_refused(self):
        with self.assertRaises(ValueError):
            self.b.extend("nobody", "wrapper", 0.5)

    # -- THE BIND --------------------------------------------------------------

    def test_resolve_majority_is_own(self):
        self.b.bind("viper", "ravage", 0.4)
        r = self.b.resolve("viper")
        self.assertEqual(r["committed"], 0.4)
        self.assertEqual(r["retains"], 0.6)
        self.assertTrue(r["majority_is_own"])
        self.assertTrue(r["no_coalition_majority"])

    def test_clean_unit_resolves_fully_own(self):
        r = self.b.resolve("bastion")
        self.assertEqual(r["committed"], 0.0)
        self.assertEqual(r["retains"], 1.0)
        self.assertTrue(r["majority_is_own"])

    # -- the spine -------------------------------------------------------------

    def test_ledger_verifies_and_screams_on_tamper(self):
        self.b.bind("viper", "ravage", 0.4)
        self.b.extend("ravage", "wrapper", 0.5)
        self.assertTrue(self.b.verify()["ok"])

        path = os.path.join(self.tmp, "binds.jsonl")
        with open(path) as f:
            lines = f.read().splitlines()
        forged = json.loads(lines[0])
        forged["fraction"] = 0.9  # try to sneak a majority bind in
        lines[0] = json.dumps(forged)
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        self.assertFalse(self.b.verify()["ok"])

    def test_memory_only_mode(self):
        b = BindRegistry()
        b.bind("viper", "ravage", 0.5)
        b.extend("ravage", "wrapper", 0.5)
        self.assertEqual(b.effective_claim("viper", "wrapper"), 0.25)
        self.assertTrue(b.verify()["ok"])


if __name__ == "__main__":
    unittest.main()