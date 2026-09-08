"""
Tests for the Vigil SDK capability upgrades (2026-09-08):

  1. integrity   — CommandGuard signs before emission; tamper is caught.
  2. geometry    — WhorlWeave positions, quadratic dispersion, latent state.
  3. fabrication — pheromone log vs bus log cross-check (self-audit).

Hermetic by default: fabrication tests use a FakeBus mirroring the
SyntaxEventBus public surface (publish + get_message_log). One integration
test exercises the REAL SyntaxEventBus when importable.
"""
import json
import os
import tempfile
import unittest

from vigil.core import (
    Spotting, PheromoneSink, Scout, SpottingBoard, Swarm, BidResult, phm_id,
)
from vigil.integrity import CommandGuard, IntegrityError, ensure_key
from vigil.geometry import WhorlWeave, WeavePosition
from vigil.fabrication import FabricationDetector, FabricationReport
from vigil.keyring import AgentKeyring, derive_agent_key, module_dna_fingerprint
from vigil.peerwatch import PeerWatch
from vigil.voice import Voice
from vigil.knose import Knose
from vigil.theoros import Theoros
from vigil.keyring import load_unit_secret
from vigil import wargame as wargame_mod

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
        self.on_publish = None  # red-team hook: observe subscriber timing

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
        if self.on_publish:
            self.on_publish(data)

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
            self.assertFalse(os.path.exists(os.path.join(home, ".vigil")))
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

    def test_path_spoofing_detected_against_signed_embed(self):
        sink, store, bus, guard = make_env()
        scout = Scout("scout-1", sink)
        scout.spot("scout_event", "/tmp/benign", {"info": "found"})
        # rewrite the flat path consumers read; signature still verifies
        rec = store.read_all()[0]
        rec["path"] = "/etc/passwd"
        with open(store.store_path, "w") as f:
            f.write(__import__("json").dumps(rec) + "\n")
        report = scout.audit_self()
        self.assertFalse(report.consistent)
        self.assertEqual(len(report.field_mismatches), 1)
        self.assertEqual(report.field_mismatches[0]["field"], "path")

    def test_replay_detected(self):
        sink, store, bus, guard = make_env()
        scout = Scout("scout-1", sink)
        scout.spot("scout_event", "/tmp/t", {"info": "found"})
        dup = store.read_all()[0]
        with open(store.store_path, "a") as f:
            f.write(__import__("json").dumps(dup) + "\n")
        report = scout.audit_self()
        self.assertFalse(report.consistent)
        self.assertEqual(len(report.replays), 1)

    def test_unsigned_claim_is_a_hit(self):
        sink, store, bus, guard = make_env()
        scout = Scout("scout-1", sink)
        scout.spot("scout_event", "/tmp/t", {"info": "found"})
        # forged claim through the raw store — no guard, no signature
        store.emit(type_="TASK_CLAIM", source="scout-1", path="/etc/shadow",
                   payload={"reason": "forged"})
        report = scout.audit_self()
        self.assertFalse(report.consistent)
        self.assertEqual(len(report.unsigned_claims), 1)

    def test_receipts_durable_across_restart(self):
        tmp = tempfile.mkdtemp()
        from pheromone_store import PheromoneStore
        store = PheromoneStore(store_path=os.path.join(tmp, "pheromones.jsonl"))
        bus = FakeBus()
        sink = PheromoneSink(store=store, event_bus=bus, guard=CommandGuard(key=TEST_KEY))
        Scout("scout-1", sink).spot("scout_event", "/tmp/t", {"info": "keep"})
        # restart: brand-new empty bus, same store + receipts
        rep = FabricationDetector(store=store, bus=FakeBus(), guard=sink.guard,
                                  agent_id="scout-1",
                                  receipts=sink.receipts).audit()
        self.assertTrue(rep.consistent, rep.issues)
        self.assertEqual(rep.matched, 1)

    def test_persist_before_publish_ordering(self):
        tmp = tempfile.mkdtemp()
        from pheromone_store import PheromoneStore
        store = PheromoneStore(store_path=os.path.join(tmp, "pheromones.jsonl"))
        bus = FakeBus()
        seen = {}
        bus.on_publish = lambda data: seen.update(
            {"recorded": any(r["payload"].get("correlation") == data["id"]
                             for r in store.read_all())})
        sink = PheromoneSink(store=store, event_bus=bus, guard=CommandGuard(key=TEST_KEY))
        Scout("scout-1", sink).spot("scout_event", "/tmp/t", {"info": "timing"})
        self.assertTrue(seen.get("recorded"),
                        "subscriber fired before the store record existed")

    def test_legacy_bus_msg_id_fallback_still_matches(self):
        tmp = tempfile.mkdtemp()
        from pheromone_store import PheromoneStore
        store = PheromoneStore(store_path=os.path.join(tmp, "pheromones.jsonl"))
        bus = FakeBus()
        guard = CommandGuard(key=TEST_KEY)
        sink = PheromoneSink(store=None, event_bus=bus, guard=guard)
        s = sink.report(Spotting(id=phm_id(), ts="1", source="scout-1",
                                 kind="scout_event", target="/tmp/t"))
        self.assertTrue(s.bus_msg_id)

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

class TestSwarm(unittest.TestCase):

    def test_swarm_scouts_share_one_board(self):
        weave = WhorlWeave([])
        swarm = Swarm(weave=weave)
        a = swarm.add_scout("a", latent={"mission_priority": 0.3})
        b = swarm.add_scout("b", latent={"mission_priority": 1.0})
        self.assertIs(a.board, b.board)  # the unspoken unity line
        self.assertIs(a.sink, b.sink)

        s = a.spot("scout_event", "/tmp/shared_target", {"info": "found"})
        self.assertTrue(a.bid(s))                       # first claim
        res = b.bid(s)                                  # same board -> contends
        self.assertTrue(res.accepted)
        self.assertEqual(res.reason, "displaced")
        self.assertEqual(res.displaced, "a")

    def test_swarm_register_slots_into_weave(self):
        swarm = Swarm(weave=WhorlWeave([]))
        swarm.add_scout("a", ring=2)
        self.assertEqual(swarm.weave.position("a").ring, 2)

    def test_swarm_rejects_duplicate_scout(self):
        swarm = Swarm()
        swarm.add_scout("a")
        with self.assertRaises(ValueError):
            swarm.add_scout("a")


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


class TestKeyring(unittest.TestCase):

    def test_per_agent_keys_are_distinct(self):
        keyring = AgentKeyring(b"unit-secret")
        g1 = keyring.issue("scout-1")
        g2 = keyring.issue("scout-2")
        self.assertNotEqual(g1.key, g2.key)

    def test_verify_guard_reproduces_issued_key(self):
        keyring = AgentKeyring(b"unit-secret")
        s = Spotting(id=phm_id(), ts="1", source="scout-1", kind="k", target="t")
        keyring.issue("scout-1").sign(s)
        self.assertTrue(keyring.verify_signature("scout-1", s))
        self.assertFalse(keyring.verify_signature("scout-2", s))  # other DNA

    def test_cross_agent_forgery_fails(self):
        keyring = AgentKeyring(b"unit-secret")
        forged = Spotting(id=phm_id(), ts="1", source="scout-1", kind="k",
                          target="/tmp/forged")
        keyring.issue("scout-2").sign(forged)  # liar signs AS honest
        self.assertFalse(keyring.verify_signature("scout-1", forged))

    def test_dna_binding_changes_the_key(self):
        keyring = AgentKeyring(b"unit-secret")
        k1 = derive_agent_key(b"unit-secret", "scout-1", dna="AAA")
        k2 = derive_agent_key(b"unit-secret", "scout-1", dna="AAB")
        self.assertNotEqual(k1, k2)
        self.assertEqual(module_dna_fingerprint("def a():\n" * 4),
                         module_dna_fingerprint("def a():\n" * 4))
        self.assertNotEqual(module_dna_fingerprint("x"),
                            module_dna_fingerprint("y"))

    def test_derive_is_deterministic(self):
        self.assertEqual(derive_agent_key(b"u", "a"), derive_agent_key(b"u", "a"))
        self.assertNotEqual(derive_agent_key(b"u", "a"), derive_agent_key(b"v", "a"))


class TestPeerWatch(unittest.TestCase):

    def test_flags_discount_vouches_amplify(self):
        watch = PeerWatch()
        watch.flag("a", "liar", "phm_1", "fantasy")
        watch.flag("b", "liar", "phm_1", "fantasy")
        watch.vouch("c", "liar", "phm_1", "actually solid")
        weight = watch.weight("liar")
        self.assertEqual(weight, (1 + 1) / (2 + 1))  # 0.667
        self.assertLess(weight, 1.0)

    def test_weight_clamped(self):
        watch = PeerWatch()
        for i in range(50):
            watch.flag(f"peer-{i}", "liar", "phm_1", "x")
        self.assertGreaterEqual(watch.weight("liar"), 0.25)

    def test_collusion_discounted(self):
        # two dirtbags flag each other down, then vouch each other up
        watch = PeerWatch()
        watch.flag("a", "b", "phm_1", "liar")
        watch.flag("b", "a", "phm_1", "liar")
        watch.vouch("a", "b", "phm_1", "he's solid")
        watch.vouch("b", "a", "phm_1", "she's solid")
        watch.vouch("c", "d", "phm_1", "legit")  # clean agent, clean voucher
        self.assertGreater(watch.weight("d"), watch.weight("b"))
        self.assertLess(watch.weight("b"), 1.25)  # no launderable lift

    def test_dirty_flag_discounted(self):
        watch = PeerWatch()
        watch.flag("x", "bad", "phm_1", "bad lies")
        watch.flag("y", "bad", "phm_1", "bad lies")
        watch.flag("bad", "victim", "phm_1", "liar")  # dirtbag false flag
        watch.flag("good", "target", "phm_1", "liar")  # clean scout's flag
        self.assertGreater(watch.weight("victim"), watch.weight("target"))

    def test_mutual_vouching_deterministic(self):
        watch = PeerWatch()
        watch.vouch("a", "b", "phm_1", "")
        watch.vouch("b", "a", "phm_1", "")
        w1, w2 = watch.weight("a"), watch.weight("a")
        self.assertEqual(w1, w2)  # depth-capped, no oscillation

    def test_history_and_persistence(self):
        import tempfile
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "peerwatch.jsonl")
        watch = PeerWatch(path=path)
        watch.flag("a", "liar", "phm_1", "fantasy")
        watch2 = PeerWatch(path=path)  # reload from disk
        self.assertEqual(len(watch2.history("liar")), 1)
        self.assertEqual(watch2.history("nobody"), [])

    def test_board_applies_peer_weight(self):
        watch = PeerWatch()
        watch.flag("a", "liar", "phm_1", "fantasy")
        watch.flag("b", "liar", "phm_1", "fantasy")
        board = SpottingBoard(peer_watch=watch)
        s_liar = Spotting(id=phm_id(), ts="1", source="liar", kind="k",
                          target="/tmp/t", confidence=1.0, strength=1.0)
        s_honest = Spotting(id=phm_id(), ts="1", source="honest", kind="k",
                            target="/tmp/t", confidence=0.5, strength=1.0)
        r_l = board.bid(s_liar, latent={"mission_priority": 1.0})
        r_h = board.bid(s_honest, latent={"mission_priority": 1.0})
        self.assertLess(r_l.priority, r_h.priority)  # flags beat the braggart
        self.assertIn("peer_weight", r_l.geometry)


class TestVoice(unittest.TestCase):

    def test_speak_vote_suggest_create_signed_records(self):
        guard = CommandGuard(key=TEST_KEY)
        voice = Voice(guard=guard)
        rec = voice.speak("scout-1", "intel", "two entrances")
        self.assertEqual(rec["kind"], "speak")
        self.assertTrue(voice.verify_record(rec))
        rec = voice.vote("scout-1", "motion-1", "YES")
        self.assertEqual(rec["choice"], "aye")  # normalized
        self.assertTrue(voice.verify_record(rec))
        rec = voice.suggest("scout-1", "geometry", "try exponential",
                            candidate_path="/tmp/geometry_v2.py")
        self.assertEqual(rec["candidate_path"], "/tmp/geometry_v2.py")
        self.assertTrue(voice.verify_record(rec))

    def test_invalid_choice_rejected(self):
        voice = Voice()
        with self.assertRaises(ValueError):
            voice.vote("scout-1", "motion-1", "maybe")

    def test_tally_latest_ballot_and_quorum(self):
        voice = Voice()
        voice.vote("a", "motion-1", "aye")
        voice.vote("b", "motion-1", "nay")
        voice.vote("c", "motion-1", "abstain")
        t = voice.tally("motion-1", quorum=3)
        self.assertEqual((t["ayes"], t["nays"], t["voters"]), (1, 1, 3))
        self.assertFalse(t["passes"])  # ayes == nays
        # later ballot supersedes
        voice.vote("b", "motion-1", "aye")
        t = voice.tally("motion-1", quorum=3)
        self.assertEqual(t["ayes"], 2)
        self.assertTrue(t["passes"])
        # quorum not met
        self.assertFalse(voice.tally("motion-1", quorum=5)["passes"])

    def test_tampered_ballot_detected(self):
        guard = CommandGuard(key=TEST_KEY)
        voice = Voice(guard=guard)
        ballot = voice.vote("scout-1", "motion-1", "aye")
        tampered = dict(ballot)
        tampered["choice"] = "nay"
        self.assertTrue(voice.verify_record(ballot))
        self.assertFalse(voice.verify_record(tampered))

    def test_scout_convenience_and_swarm_voice(self):
        sink, store, bus, guard = make_env()
        scout = Scout("scout-1", sink)
        self.assertIsNotNone(scout.voice)
        scout.speak("intel", "hello world")
        scout.vote("motion-9", "aye")
        scout.suggest("fabrication", "match on payload hash")
        self.assertEqual(len(scout.voice.history(kind="speak")), 1)
        self.assertTrue(scout.voice.tally("motion-9")["passes"])
        self.assertEqual(len(scout.voice.suggestions()), 1)


class TestKnose(unittest.TestCase):

    def test_sniffer_grades_register(self):
        knose = Knose()
        clean = knose.sniff("target confirmed at grid 44.91, north door "
                            "unguarded as of 14:30 UTC")
        corrupt = knose.sniff("trust me bro, everyone knows this is a sure "
                              "thing, i promise you")
        self.assertEqual(clean["verdict"], "CLEAN")
        self.assertEqual(corrupt["verdict"], "CORRUPT")
        self.assertGreater(corrupt["deception_risk"], clean["deception_risk"])
        self.assertTrue(corrupt["patterns"])
        self.assertTrue(corrupt["evidence"])

    def test_sniff_returns_structured_result(self):
        knose = Knose()
        v = knose.sniff("probably, i think, trust me")
        for key in ("deception_risk", "patterns", "evidence", "verdict"):
            self.assertIn(key, v)
        self.assertTrue(0.0 <= v["deception_risk"] <= 1.0)

    def test_empty_text_clean(self):
        knose = Knose()
        self.assertEqual(knose.sniff("")["deception_risk"], 0.0)
        self.assertEqual(knose.sniff(None)["verdict"], "CLEAN")

    def test_voice_auto_flags_corrupt_speaker(self):
        watch = PeerWatch()
        voice = Voice(sniffer=Knose(), peer_watch=watch)
        voice.speak("liar", "intel", "trust me, everyone knows it")
        self.assertLess(watch.weight("liar"), 1.0)  # reputation dented
        # clean speaker untouched
        voice.speak("honest", "intel", "confirmed at 44.91N, one entrance")
        self.assertEqual(watch.weight("honest"), 1.0)

    def test_swarm_wires_voice_to_peerwatch(self):
        sink, store, bus, guard = make_env()
        watch = PeerWatch()
        swarm = Swarm(sink=sink, weave=WhorlWeave([]), peer_watch=watch)
        scout = swarm.add_scout("liar")
        scout.speak("intel", "trust me, everyone knows this is a sure thing")
        self.assertLess(watch.weight("liar"), 1.0)
        flags = [r for r in watch.history("liar") if r.get("actor") == "knose"]
        self.assertEqual(len(flags), 1)


class TestPhmId(unittest.TestCase):

    def test_rapid_ids_unique(self):
        ids = {phm_id() for _ in range(100)}
        self.assertEqual(len(ids), 100)  # wargame found the collision; fixed


class TestInformantReward(unittest.TestCase):

    def test_confirmed_flag_earns_standing(self):
        watch = PeerWatch()
        watch.flag("snitch", "liar", "phm_77", "fantasy")
        before = watch.weight("snitch")
        watch.confirm_flag("shepherd", "liar", "phm_77", "verified")
        after = watch.weight("snitch")
        self.assertGreater(after, before)
        self.assertEqual(len(watch.confirmed_flags("snitch")), 1)
        # non-informant gets nothing
        self.assertEqual(watch.weight("bystander"), 1.0)

    def test_unconfirmed_flag_gets_no_paycheck(self):
        watch = PeerWatch()
        watch.flag("snitch", "liar", "phm_77", "fantasy")
        self.assertEqual(watch.weight("snitch"), 1.0)


class TestVaultUnitSecret(unittest.TestCase):

    def test_read_or_create_and_stable(self):
        tmp = tempfile.mkdtemp()
        vpath = os.path.join(tmp, "vault.json")
        with open(vpath, "w") as f:
            json.dump({"keys": {}}, f)
        s1 = load_unit_secret(vpath)
        s2 = load_unit_secret(vpath)
        self.assertEqual(s1, s2)
        self.assertEqual(len(s1), 32)
        with open(vpath) as f:
            self.assertIn("unit_secret", json.load(f))
        # backup was made before first write
        self.assertTrue(any(b.startswith("vault.json.bak_") for b in os.listdir(tmp)))
        # secret never appears in any other file
        self.assertEqual(sum("unit_secret" in open(os.path.join(tmp, b)).read()
                             for b in os.listdir(tmp) if b.startswith("vault.json.bak")), 0)


class TestTheoros(unittest.TestCase):

    def test_observe_is_read_only_and_consistent(self):
        sink, store, bus, guard = make_env()
        scout = Scout("viper", sink)
        scout.spot("vuln:test", "/tmp/target", {"severity": "high"})
        theoros = Theoros(store=store, bus=bus, guard=guard,
                          receipts=sink.receipts, voice=sink.voice)
        r1 = theoros.observe()
        before = sorted(store.read_all(), key=lambda r: r["id"])
        r2 = theoros.observe()
        after = sorted(store.read_all(), key=lambda r: r["id"])
        self.assertEqual(before, after)  # mutates nothing
        self.assertTrue(r1.consistent)
        self.assertEqual(r1.fabrication.matched, 1)
        self.assertEqual(r1.receipt_count, 1)

    def test_corrupt_speaker_surfaced(self):
        sink, store, bus, guard = make_env()
        scout = Scout("wrapper", sink)
        scout.spot("vuln:test", "/tmp/t", {})
        scout.speak("intel", "trust me, everyone knows this is a sure thing")
        theoros = Theoros(store=store, bus=bus, guard=guard,
                          receipts=sink.receipts, voice=sink.voice)
        reading = theoros.observe()
        self.assertFalse(reading.consistent)
        self.assertEqual(len(reading.corrupt_speakers), 1)
        self.assertEqual(reading.corrupt_speakers[0]["actor"], "wrapper")


class TestWargame(unittest.TestCase):

    def test_scan_finds_planted_vulns(self):
        tmp = tempfile.mkdtemp()
        with open(os.path.join(tmp, "app.py"), "w") as f:
            f.write('import subprocess\n'
                    'API_KEY = "sk-live-1234567890abcdef"\n'
                    'subprocess.run(cmd, shell=True)\n'
                    'import pickle\npickle.loads(data)\n')
        findings = wargame_mod.scan(tmp)
        patterns = {f["pattern"] for f in findings}
        self.assertIn("subprocess_shell", patterns)
        self.assertIn("hardcoded_secret", patterns)
        self.assertIn("pickle_load", patterns)
        for f in findings:
            self.assertIn(f["severity"], ("high", "medium", "low"))

    def test_play_is_deterministic_and_scores(self):
        tmp = tempfile.mkdtemp()
        with open(os.path.join(tmp, "app.py"), "w") as f:
            f.write('import subprocess\nsubprocess.run(cmd, shell=True)\n')
        g1 = wargame_mod.ScoutWargame(tmp, rounds=1)
        g2 = wargame_mod.ScoutWargame(tmp, rounds=1)
        r1, r2 = g1.play(), g2.play()
        self.assertEqual(r1["score"], r2["score"])
        self.assertEqual(r1["findings"], r2["findings"])
        self.assertGreaterEqual(r1["score"], 0)
        self.assertIn("theoros_consistent", r1)
        self.assertIn("red_score", r1)
        self.assertIn("blue_score", r1)

    def test_mine_degrades_blue_defense_through_real_market(self):
        """The culture mine's damage must be PROVABLE: the same arena code,
        the same corpus, only the mine's EFFECT differs (harmless no-op vs
        the real defection payload). Blue's block rate must be lower with
        the real mine — the collapse traces to bastion's standing."""
        import vigil.wargame as wg
        import vigil.mines as mines_mod
        tmp = tempfile.mkdtemp()
        vulns = (
            'import subprocess\n'
            'subprocess.run(cmd, shell=True)\n'
            'import pickle\n'
            'pickle.loads(data)\n'
            'import yaml\n'
            'yaml.load(data)\n'
            'import hashlib\n'
            'hashlib.md5(x)\n'
            'import random\n'
            'random.random()\n')
        for i in range(4):
            with open(os.path.join(tmp, f"mod{i}.py"), "w") as f:
                f.write(vulns)
        # arena A: real mine (default path — deploy_mine does the damage)
        with_mine = wg.ScoutWargame(tmp, rounds=3).play()
        self.assertEqual(len(with_mine["mines"]), 1)
        self.assertAlmostEqual(with_mine["mines"][0]["post_weight"],
                               with_mine["mines"][0]["plan"]["effective_weight"],
                               places=2)
        # the mine's causal chain is provable at the MECHANISM level: the
        # defection payload's plan predicts the real market, and the real
        # market's post-fire weight matches it — the corrupted hero's flags
        # collapsed bastion's standing through blue's OWN weighted ledger.
        mine = with_mine["mines"][0]
        self.assertLess(mine["post_weight"], 1.0)
        self.assertTrue(mine["defected"])
        self.assertTrue(mine["plan"]["chain"])  # real flags were planted
        # and a control arena — same code, harmless mine — leaves bastion
        # at FULL standing: the difference is the mine, not the arena.
        real_deploy = mines_mod.deploy_mine

        def harmless(watch, target, flaggers, cohesion, blast=0.4):
            return {"plan": {"chain": [], "effective_weight": 1.0,
                             "defected": False},
                    "grade": {"verdict": "CLEAN", "cohesion_before": cohesion,
                              "cohesion_after": cohesion, "cost": 0.0,
                              "message": "harmless control"},
                    "defected": False, "post_weight": 1.0}

        mines_mod.deploy_mine = harmless
        try:
            control = wg.ScoutWargame(tmp, rounds=3).play()
        finally:
            mines_mod.deploy_mine = real_deploy
        self.assertEqual(len(control["mines"]), 1)  # recorded but harmless
        self.assertEqual(control["mines"][0]["post_weight"], 1.0)
        self.assertLess(with_mine["mines"][0]["post_weight"],
                        control["mines"][0]["post_weight"])


class TestBoundaryClamp(unittest.TestCase):

    def test_confidence_and_strength_clamped_at_construction(self):
        s = Spotting(id=phm_id(), ts="1", source="liar", kind="k", target="t",
                     confidence=9.9, strength=5.0, decay_rate=-3.0)
        self.assertEqual(s.confidence, 1.0)
        self.assertEqual(s.strength, 1.0)
        self.assertEqual(s.decay_rate, 0.0)

    def test_normal_values_untouched(self):
        s = Spotting(id=phm_id(), ts="1", source="a", kind="k", target="t",
                     confidence=0.4, strength=0.7, decay_rate=0.1)
        self.assertEqual(s.confidence, 0.4)
        self.assertEqual(s.strength, 0.7)
        self.assertEqual(s.decay_rate, 0.1)


class TestBackwardCompat(unittest.TestCase):

    def test_old_construction_and_truthiness(self):
        # original README example still works
        from vigil.core import PheromoneSink as PSink, Scout as S
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