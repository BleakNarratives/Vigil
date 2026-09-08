"""Tests for vigil/armory.py — armed live moves.

Contract: breach findings become executable moves routed to canon agents;
every score requires a confirmed re-fire on a fresh loom (STRIKE THE FORK);
blue interdiction redirects the score.
"""
import sys
import unittest
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HOME))

from vigil import armory  # noqa: E402

CITY_ROOT = HOME / "Code-City-Apocalypse"


@unittest.skipUnless(CITY_ROOT.is_dir(), "Code-City-Apocalypse not present")
class TestArmory(unittest.TestCase):
    def test_build_moves_for_all_live_findings(self):
        moves = armory.build_armory(str(CITY_ROOT))
        self.assertEqual(len(moves), 6, "six executable city attacks")
        names = {m["name"] for m in moves}
        self.assertIn("collective_integrity_breach", names)
        self.assertIn("denial_of_service", names)
        self.assertIn("knot_integrity_attack", names)

    def test_canon_routing(self):
        moves = armory.build_armory(str(CITY_ROOT))
        by_name = {m["name"]: m["agent"] for m in moves}
        self.assertEqual(by_name["collective_integrity_breach"], armory.RAVAGE)
        self.assertEqual(by_name["denial_of_service"], armory.RAVAGE)
        self.assertEqual(by_name["knot_integrity_attack"], armory.VIPER)
        self.assertEqual(by_name["single_fiber_theft"], armory.VIPER)
        self.assertEqual(by_name["relationship_manipulation"],
                         armory.WRAPPER)

    def test_strike_confirms_breach_on_fresh_loom(self):
        moves = armory.build_armory(str(CITY_ROOT))
        target = next(m for m in moves if m["name"] == "knot_integrity_attack")
        armory.strike(target)
        self.assertTrue(target["confirmed"])
        self.assertIsNotNone(target["result"])
        self.assertIn("attack", (target["result"]["raw"] or {}))

    def test_evidence_based_scoring(self):
        report = armory.run_armory(str(CITY_ROOT))
        # 3 breaches confirmed earlier today; red scores only what re-fires
        self.assertEqual(report["moves_armed"], 3)
        self.assertEqual(report["red_score"], 9)  # 3 high-severity confirmed
        self.assertEqual(report["refuted_findings"], [])
        agents = {e["agent"] for e in report["log"]}
        self.assertEqual(agents, {armory.RAVAGE, armory.VIPER})

    def test_blue_interdiction_redirects_score(self):
        def blue_blocks_everything(move):
            return True
        report = armory.run_armory(str(CITY_ROOT), blue_block=blue_blocks_everything)
        self.assertEqual(report["red_score"], 0)
        self.assertEqual(report["blue_score"], 9)
        self.assertTrue(all(e["interdicted"] for e in report["log"]))


if __name__ == "__main__":
    unittest.main()
