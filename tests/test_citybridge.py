"""Tests for vigil/citybridge.py — the Code-City attack-module bridge.

Contract: every lane emits wargame-schema findings, deterministic, and the
live lane (opt-in) actually runs Code-City's six-attack battery against its
own FortifiedCelticLoom.
"""
import sys
import unittest
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HOME))

from vigil import citybridge  # noqa: E402

CITY_ROOT = HOME / "Code-City-Apocalypse"
SCHEMA_KEYS = {"path", "line", "pattern", "severity", "code"}


class TestCityBridge(unittest.TestCase):
    def setUp(self):
        if not CITY_ROOT.is_dir():
            self.skipTest("Code-City-Apocalypse not present on this box")

    def test_static_lanes_emit_schema(self):
        findings = citybridge.scan(str(CITY_ROOT), lanes="all")
        self.assertGreater(len(findings), 0)
        for f in findings:
            self.assertTrue(SCHEMA_KEYS.issubset(f.keys()),
                            f"missing schema keys in {f}")
            self.assertIn(f["severity"], ("high", "medium", "low"))
            self.assertIn(f["lane"], ("regex", "city_sigs"))

    def test_scan_is_deterministic(self):
        a = citybridge.scan(str(CITY_ROOT), lanes="city")
        b = citybridge.scan(str(CITY_ROOT), lanes="city")
        self.assertEqual(a, b)

    def test_lane_selection(self):
        regex_only = citybridge.scan(str(CITY_ROOT), lanes="regex")
        for f in regex_only:
            self.assertEqual(f["lane"], "regex")

    def test_no_duplicate_path_line_pattern(self):
        findings = citybridge.scan(str(CITY_ROOT), lanes="all")
        keys = [(f["path"], f["line"], f["pattern"]) for f in findings]
        self.assertEqual(len(keys), len(set(keys)))

    def test_city_sigs_found_in_city_code(self):
        """The celtic loom code itself must trip the city signatures —
        a signature set that can't find its own source of truth is noise."""
        findings = citybridge.scan(str(CITY_ROOT), lanes="city")
        patterns = {f["pattern"] for f in findings}
        self.assertIn("city_integrity_breach", patterns)
        self.assertIn("city_fiber_theft", patterns)

    def test_live_lane_runs_real_battery(self):
        """LANE 3 runs Code-City's actual RedTeamAttacker: the six named
        attacks appear in the log, each marked breach True/False."""
        findings = citybridge.scan(str(CITY_ROOT), lanes="live")
        live = [f for f in findings if f["lane"] == "live"]
        self.assertGreaterEqual(len(live), 6, "six attacks expected")
        names = {f["pattern"] for f in live}
        for expected in ("city_live_single_fiber_theft",
                         "city_live_collective_integrity_breach",
                         "city_live_knot_integrity_attack",
                         "city_live_denial_of_service"):
            self.assertIn(expected, names)
        for f in live:
            self.assertIn("breach", f)
            self.assertIsInstance(f["breach"], bool)

    def test_wargame_accepts_bridge(self):
        """The seam: ScoutWargame must accept the bridge scan_fn and run."""
        from vigil.wargame import ScoutWargame
        game = ScoutWargame(str(CITY_ROOT), rounds=2,
                            scan_fn=citybridge.scan)
        result = game.play()
        self.assertEqual(result["findings"], len(game.findings))
        self.assertGreater(result["findings"], 0)


if __name__ == "__main__":
    unittest.main()
