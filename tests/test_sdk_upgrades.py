"""
Tests for the Spyglass SDK capability upgrades (2026-09-08):

  1. integrity   — CommandGuard signs before emission; tamper is caught.
  2. geometry    — WhorlWeave positions, quadratic dispersion, latent state.
  3. fabrication — pheromone log vs bus log cross-check (self-audit).

Hermetic by default: fabrication tests use a FakeBus mirroring the
SyntaxEventBus public surface (publish + get_message_log). One integration
test exercises the REAL SyntaxEventBus when importable.
"""
import os
import tempfile
import unittest

from sdk.spyglass_sdk import (
    Spotting, PheromoneSink, Scout, SpottingBoard, BidResult, phm_id,
)
from sdk.integrity import CommandGuard, IntegrityError, ensure_key
from sdk.geometry import WhorlWeave, WeavePosition
from sdk.fabrication import FabricationDetector, FabricationReport

try:
    from SyntaxIntelligence.event_bus import SyntaxEventBus
    REAL_BUS = True
except ImportError:
    REAL_BUS = False

TEST_KEY = b"0123456789abcdef0123456789abcdef"


class FakeBus:
    """Minimal stand-in for SyntaxEventBus: publish + message log."""

    def __init__(self):
        self._log = []
        self._count = 0

    def publish(self, sender_id, channel, data):
        self._count += 1
        self._log.append({
            "timestamp": "2026-09-08T00:00:00+00:00",
            "type": "publish",
            "agent_id": sender_id,
            "channel": channel,
            "detail": "[REDACTED]",
            "msg_id": self._count,
        })

    def get_message_log(self, n=50):
        return list(self._log[-n:]) if n else list(self._log)


def make_env():
    """tmp store + FakeBus + signed sink; returns (sink, store, bus, guard)."""
    tmp = tempfile.mkdtemp()
    from pheromone_store import PheromoneStore
    store = PheromoneStore(store_path=os.path.join(tmp, "pheromones.jsonl"))
    bus = FakeBus()
    guard = CommandGuard(key=TEST_KEY)
    sink = PheromoneSink(store=store, event_bus=bus, guard=guard)
    return sink, store, bus, guard


# ---------------------------------------------------------------------------
# 1. INTEGRITY
# ---------------------------------------------------------------------------

class TestIntegrity(unittest.TestCase):

    def _spotting(self, **over):
        fields = dict(
            id=phm_id(), ts="1.0", source="scout-1", kind="scout_event",
            target="/tmp/target", confidence=0.8, strength=0.9,
            decay_rate=0.1, payload={"info": "found"},
        )
        fields.update(over)
        return Spotting(**fields)

    def test_sign_attaches_signature_and_verifies(self):
        guard = CommandGuard(key=TEST_KEY)
        s = self._spotting()
        sig = guard.sign(s)
        self.assertTrue(sig)
        self.assertEqual(s.signature, sig)
        self.assertTrue(guard.verify(s))

    def test_tampered_payload_fails_verification(self):
        guard = CommandGuard(key=TEST_KEY)
        s = self._spotting()
        guard.sign(s)
        s.payload["info"] = "forged"
        self.assertFalse(guard.verify(s))

    def test_tampered_command_path_fails_verification(self):
        guard = CommandGuard(key=TEST_KEY)
        s = self._spotting()
        guard.sign(s)
        s.target = "/tmp/DIFFERENT"
        self.assertFalse(guard.verify(s))

    def test_double_sign_raises(self):
        guard = CommandGuard(key=TEST_KEY)
        s = self._spotting()
        guard.sign(s)
        with self.assertRaises(IntegrityError):
            guard.sign(s)

    def test_explicit_key_never_touches_disk(self):
        home = tempfile.mkdtemp()
        old = os.environ.get("HOME")
        os.environ["HOME"] = home
        try:
            guard = CommandGuard(key=TEST_KEY)
            s = self._spotting()
            guard.sign(s)
            self.assertTrue(guard.verify(s))
            self.assertFalse(os.path.exists(os.path.join(home, ".spyglass")))
        finally:
            if old is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old

    def test_ensure_key_generates_0600_file(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "scout_key")
        key = ensure_key(path)
        self.assertEqual(len(key), 32)
        mode = os.stat(path).st_mode & 0o777
        self.assertEqual(mode, 0o600)
        # idempotent
        self.assertEqual(ensure_key(path), key)

    def test_hash_command_stable_across_guards(self):
        g1 = CommandGuard(key=TEST_KEY)
        g2 = CommandGuard(key=TEST_KEY)
        s1 = self._spotting()
        s2 = self._spotting(id=s1.id, ts=s1.ts)  # identical fields -> same hash
        self.assertEqual(g1.hash_command(s1), g2.hash_command(s2))
        s2.target = "/other"
        self.assertNotEqual(g1.hash_command(s1), g2.hash_command(s2))

    def test_verify_log_batch(self):
        guard = CommandGuard(key=TEST_KEY)
        s = self._spotting()
        guard.sign(s)
        good = s.to_dict()
        # stored-record shape: signature lives inside the payload
        bad = s.to_dict()
        bad["payload"] = {**bad["payload"], "signature": "deadbeef", "bus_msg_id": None}
        bad["signature"] = ""
        unsigned = self._spotting().to_dict()
        result = guard.verify_log([good, bad, unsigned])
        self.assertEqual(len(result["valid"]), 1)
        self.assertEqual(len(result["invalid"]), 1)
        self.assertEqual(len(result["unsigned"]), 1)


# ---------------------------------------------------------------------------
# 2. GEOMETRY
# ---------------------------------------------------------------------------

class TestGeometry(unittest.TestCase):

    def test_positions_assigned_and_spread(self):
        weave = WhorlWeave(["a", "b", "c"], rings={"c": 2})
        pa, pb, pc = weave.position("a"), weave.position("b"), weave.position("c")
        self.assertEqual(pa.ring, 0)
        self.assertEqual(pc.ring, 2)
        self.assertNotEqual(pa.phase, pb.phase)  # golden-angle spread
        self.assertEqual(weave.position("unknown").agent_id, "__center__")

    def test_register_adds_agent(self):
        weave = WhorlWeave(["a"])
        weave.register("b", ring=1)
        self.assertEqual(weave.position("b").ring, 1)

    def test_dispersion_quadratic(self):
        weave = WhorlWeave([], dispersion_k=1.0)
        self.assertEqual(weave.dispersion(1.0, 0.0), 1.0)
        d1, d2 = weave.dispersion(1.0, 1.0), weave.dispersion(1.0, 2.0)
        # 1/(1+4) == 0.2 vs 1/(1+1) == 0.5  -> exactly quadratic
        self.assertAlmostEqual(d2, 0.2)
        self.assertAlmostEqual(d1, 0.5)
        self.assertLess(d2, d1)

    def test_modulate_attenuates_with_distance(self):
        weave = WhorlWeave(["near", "far"], rings={"far": 4})
        s_near = Spotting(id=phm_id(), ts="1", source="near", kind="k", target="t",
                          confidence=0.8, strength=1.0)
        s_far = Spotting(id=phm_id(), ts="1", source="far", kind="k", target="t",
                         confidence=0.8, strength=1.0)
        g_near = weave.modulate(s_near)
        g_far = weave.modulate(s_far)
        self.assertGreater(g_near["strength"], g_far["strength"])
        self.assertGreater(g_near["priority"], g_far["priority"])
        self.assertLessEqual(g_far["confidence"], 1.0)
        self.assertGreaterEqual(g_far["confidence"], 0.0)

    def test_latent_state_shapes_priority(self):
        weave = WhorlWeave(["a"])
        s = Spotting(id=phm_id(), ts="1", source="a", kind="k", target="t",
                     confidence=0.8, strength=1.0)
        healthy = weave.modulate(s, latent={"health": 1.0, "mission_priority": 1.0, "resource_cost": 0.0})
        sick = weave.modulate(s, latent={"health": 0.2, "mission_priority": 0.5, "resource_cost": 0.9})
        self.assertGreater(healthy["priority"], sick["priority"])

    def test_distance_between_positions(self):
        weave = WhorlWeave(["a", "b"], rings={"b": 3})
        d = weave.position("a").distance_to(weave.position("b"))
        self.assertGreater(d, 0.0)


# ---------------------------------------------------------------------------
# 3. FABRICATION + END-TO-END
# ---------------------------------------------------------------------------

class TestFabrication(unittest.TestCase):

    def test_self_audit_consistent_end_to_end(self):
        sink, store, bus, guard = make_env()
        scout = Scout("scout-1", sink)
        scout.spot("scout_event", "/tmp/t", {"info": "found"})
        report = scout.audit_self()
        self.assertTrue(report.consistent, report.issues)
        self.assertEqual(report.matched, 1)
        self.assertEqual(report.pheromone_count, 1)
        self.assertEqual(report.bus_publish_count, 1)
        self.assertFalse(report.unmatched)
        self.assertFalse(report.ghost_bus_events)
        self.assertFalse(report.signature_failures)

    def test_unmatched_receipt_detected(self):
        sink, store, bus, guard = make_env()
        scout = Scout("scout-1", sink)
        scout.spot("scout_event", "/tmp/t", {"info": "found"})
        # forge a pheromone claiming a bus msg_id that never existed
        from pheromone_store import PheromoneStore
        store.emit(
            type_="scout_event", source="scout-1", path="/tmp/forged",
            payload={"signature": guard.sign(
                Spotting(id=phm_id(), ts="2", source="scout-1", kind="scout_event",
                         target="/tmp/forged")), "bus_msg_id": 999999},
        )
        report = scout.audit_self()
        self.assertFalse(report.consistent)
        self.assertEqual(len(report.unmatched), 1)
        self.assertIn("/tmp/forged", report.unmatched[0]["path"])

    def test_tampered_signature_detected(self):
        sink, store, bus, guard = make_env()
        scout = Scout("scout-1", sink)
        scout.spot("scout_event", "/tmp/t", {"info": "found"})
        record = store.read_all()[0]
        record["payload"]["signature"] = "deadbeef"
        # rewrite the tampered record back
        lines = open(store.store_path).read().splitlines()
        lines[-1] = __import__("json").dumps(record)
        with open(store.store_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        report = scout.audit_self()
        self.assertFalse(report.consistent)
        self.assertEqual(len(report.signature_failures), 1)

    def test_ghost_bus_event_detected(self):
        sink, store, bus, guard = make_env()
        scout = Scout("scout-1", sink)
        scout.spot("scout_event", "/tmp/t", {"info": "found"})
        # publish to the bus WITHOUT persisting a pheromone (injection / skipped write)
        bus.publish("scout-1", "scout.signals", {"fake": True})
        report = scout.audit_self()
        self.assertFalse(report.consistent)
        self.assertEqual(len(report.ghost_bus_events), 1)

    def test_uncorrelated_legacy_rows_are_gaps_not_hits(self):
        sink, store, bus, guard = make_env()
        scout = Scout("scout-1", sink)
        scout.spot("scout_event", "/tmp/t", {"info": "found"})
        store.emit(type_="scout_event", source="scout-1", path="/tmp/legacy",
                   payload={})  # no signature, no bus_msg_id
        report = scout.audit_self()
        self.assertTrue(report.consistent)
        self.assertEqual(len(report.uncorrelated), 1)
        self.assertIn("uncorrelated", report.issues[0] if report.issues else "")

    @unittest.skipUnless(REAL_BUS, "SyntaxIntelligence not importable")
    def test_integration_with_real_event_bus(self):
        tmp = tempfile.mkdtemp()
        from pheromone_store import PheromoneStore
        store = PheromoneStore(store_path=os.path.join(tmp, "pheromones.jsonl"))
        bus = SyntaxEventBus()
        sink = PheromoneSink(store=store, event_bus=bus, guard=CommandGuard(key=TEST_KEY))
        scout = Scout("scout-1", sink)
        s = scout.spot("scout_event", "/tmp/t", {"info": "found"})
        self.assertTrue(s.bus_msg_id)  # captured from the real bus
        report = scout.audit_self()
        self.assertTrue(report.consistent, report.issues)


# ---------------------------------------------------------------------------
# 4. GEOMETRIC BIDDING (SpottingBoard) + BACKWARD COMPAT
# ---------------------------------------------------------------------------

class TestSpottingBoard(unittest.TestCase):

    def test_fcfs_tie_break_without_weave(self):
        board = SpottingBoard()
        s1 = Spotting(id=phm_id(), ts="1", source="a", kind="k", target="t",
                      confidence=0.5, strength=1.0)
        s2 = Spotting(id=phm_id(), ts="2", source="b", kind="k", target="t",
                      confidence=0.5, strength=1.0)
        r1 = board.bid(s1)
        self.assertTrue(r1)
        self.assertEqual(r1.reason, "claimed")
        r2 = board.bid(s2)
        self.assertFalse(r2)          # equal priority -> first wins
        self.assertEqual(r2.reason, "outbid")
        self.assertIsInstance(r1, BidResult)

    def test_geometric_priority_displaces_earlier_claim(self):
        weave = WhorlWeave(["near", "far"], rings={"far": 5})
        board = SpottingBoard(weave=weave)
        s_far = Spotting(id=phm_id(), ts="1", source="far", kind="k", target="t",
                         confidence=0.8, strength=1.0)
        s_near = Spotting(id=phm_id(), ts="2", source="near", kind="k", target="t",
                          confidence=0.8, strength=1.0)
        first = board.bid(s_far, latent={"mission_priority": 0.5})
        self.assertTrue(first)
        second = board.bid(s_near, latent={"mission_priority": 1.0})
        self.assertTrue(second)                     # later arrival but closer + higher priority
        self.assertEqual(second.reason, "displaced")
        self.assertEqual(second.displaced, "far")
        # third bidder loses to the current champion
        s_mid = Spotting(id=phm_id(), ts="3", source="far", kind="k", target="t",
                         confidence=0.1, strength=0.1)
        self.assertFalse(board.bid(s_mid))

    def test_release_clears_claim(self):
        board = SpottingBoard()
        s = Spotting(id=phm_id(), ts="1", source="a", kind="k", target="t")
        self.assertTrue(board.bid(s))
        board.release("t")
        self.assertTrue(board.bid(s))  # claimable again


class TestBackwardCompat(unittest.TestCase):

    def test_old_construction_and_truthiness(self):
        # original README example still works
        from sdk.spyglass_sdk import PheromoneSink as PSink, Scout as S
        sink = PSink(store=None, event_bus=None, guard=None)
        scout = S("my-agent", sink)
        s = scout.spot("scout_event", "target_path", {"info": "found something"})
        self.assertTrue(s.source, "my-agent")
        board = SpottingBoard()
        self.assertTrue(bool(board.bid(s)))  # BidResult truthy when accepted

    def test_spotting_to_dict_additive(self):
        s = Spotting(id=phm_id(), ts="1", source="a", kind="k", target="t")
        d = s.to_dict()
        for key in ("id", "ts", "source", "kind", "target", "confidence",
                    "strength", "decay_rate", "payload"):
            self.assertIn(key, d)
        self.assertIn("signature", d)
        self.assertIn("bus_msg_id", d)


if __name__ == "__main__":
    unittest.main()