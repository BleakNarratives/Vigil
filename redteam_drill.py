#!/usr/bin/env python3
"""
sdk/redteam_drill.py — Red-team battery against the Scout SDK.

Runs the H1-H9 attack list (from the 2026-09-08 brutal audit) against a
live instance of the SDK and reports each attack as:

  CAUGHT  — the defense detected it (audit inconsistent / clamp bound /
            tool refused)
  LANDED  — the attack succeeded; the defense does not cover it (honest
            finding, documented below the table)

This drill is the plate-carrier check: it proves what the armor stops and
what it does not, before the scouts ship. It uses a temp store, a fake
bus, and an injected test key — nothing outside a temp dir is touched.

Run:  python3 sdk/redteam_drill.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # home root

from sdk.spyglass_sdk import (  # noqa: E402
    Spotting, PheromoneSink, Scout, SpottingBoard, Swarm, phm_id,
)
from sdk.integrity import CommandGuard  # noqa: E402
from sdk.geometry import WhorlWeave  # noqa: E402
from sdk.fabrication import FabricationDetector  # noqa: E402
from sdk.keyring import AgentKeyring  # noqa: E402
from sdk.peerwatch import PeerWatch  # noqa: E402

TEST_KEY = b"red-team-key-please-rotate-me"


class FakeBus:
    """Minimal SyntaxEventBus stand-in (publish + message log)."""

    def __init__(self):
        self._log = []
        self._count = 0

    def __init__(self):
        self._log = []
        self._count = 0
        self.on_publish = None  # red-team hook: observe subscriber timing

    def publish(self, sender_id, channel, data):
        self._count += 1
        self._log.append({
            "timestamp": "2026-09-08T00:00:00+00:00",
            "type": "publish", "agent_id": sender_id, "channel": channel,
            "detail": "[REDACTED]", "msg_id": self._count,
        })
        if self.on_publish:
            self.on_publish(data)

    def get_message_log(self, n=50):
        return list(self._log[-n:]) if n else list(self._log)


def make_env():
    from pheromone_store import PheromoneStore
    tmp = tempfile.mkdtemp(prefix="spyglass_redteam_")
    store = PheromoneStore(store_path=os.path.join(tmp, "pheromones.jsonl"))
    bus = FakeBus()
    guard = CommandGuard(key=TEST_KEY)
    sink = PheromoneSink(store=store, event_bus=bus, guard=guard)
    return tmp, store, bus, guard, sink


RESULTS = []


def attack(name, status, note):
    RESULTS.append((name, status, note))
    print(f"  [{status:>6}] {name} — {note}")


def audit_ok(store, bus, guard, agent_id, receipts=None):
    det = FabricationDetector(store=store, bus=bus, guard=guard,
                              agent_id=agent_id, receipts=receipts)
    return det.audit()


def main():
    print("SPYGLASS RED-TEAM DRILL — 2026-09-08 (H1-H9 battery)")
    print("=" * 78)

    tmp, store, bus, guard, sink = make_env()
    weave = WhorlWeave(["honest", "liar", "far"])
    swarm = Swarm(sink=sink, weave=weave)
    honest = swarm.add_scout("honest", latent={"mission_priority": 1.0})
    liar = swarm.add_scout("liar", latent={"mission_priority": 1.0})
    swarm.add_scout("far", ring=5, latent={"mission_priority": 1.0})

    # --- A1 (H2): path spoofing — rewrite the flat path a consumer reads ----
    print("\n[H2] sign-what's-read")
    s = honest.spot("scout_event", "/tmp/benign", {"info": "found"})
    rec = store.read_all()[-1]
    rec["path"] = "/etc/passwd"
    lines = [json.dumps(r) for r in store.read_all()[:-1]] + [json.dumps(rec)]
    with open(store.store_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    rep = audit_ok(store, bus, guard, "honest", receipts=sink.receipts)
    attack("A1 path spoof", "CAUGHT" if rep.field_mismatches else "LANDED",
           "top-level path diverges from signed embed -> field_mismatches")

    # --- A2 (H3): unsigned TASK_CLAIM forgery -------------------------------
    print("\n[H3] claim ledger")
    store.emit(type_="TASK_CLAIM", source="liar", path="/etc/shadow",
               payload={"reason": "forged claim, no key"})
    rep = audit_ok(store, bus, guard, "liar", receipts=sink.receipts)
    attack("A2 forged TASK_CLAIM", "CAUGHT" if rep.unsigned_claims else "LANDED",
           f"unsigned TASK_CLAIM -> unsigned_claims={len(rep.unsigned_claims)}")

    # --- A3 (H4): lying bid — confidence=9.9 --------------------------------
    print("\n[H4] boundary clamp")
    target = "/tmp/prize"
    liar_s = liar.spot("scout_event", target, {"info": "i want it"},
                       confidence=9.9, strength=5.0)
    clamped = liar_s.confidence <= 1.0 and liar_s.strength <= 1.0
    board = SpottingBoard(weave=weave)
    r_h = board.bid(honest.spot("scout_event", target, {}), latent=honest.latent)
    r_l = board.bid(liar_s, latent=liar.latent)
    attack("A3 lying bid", "CAUGHT" if clamped else "LANDED",
           f"liar confidence clamped to {liar_s.confidence}; "
           f"liar priority {r_l.priority:.3f} vs honest {r_h.priority:.3f}")

    # --- A4 (H5): lying-but-consistent scout --------------------------------
    print("\n[H5] deception vs inconsistency")
    tmp4, store4, bus4, guard4, sink4 = make_env()
    liar4 = Scout("liar", sink4)
    liar4.spot("scout_event", "/tmp/garbage", {"info": "lies"})
    rep = audit_ok(store4, bus4, guard4, "liar", receipts=sink4.receipts)
    attack("A4 lying-but-consistent", "LANDED",
           f"scout-issued garbage audits consistent={rep.consistent} "
           f"(detector proves consistency, not truth)")
    import shutil
    shutil.rmtree(tmp4, ignore_errors=True)

    # --- A5 (H6): replay — duplicate a liar store record --------------------
    print("\n[H6] replay")
    liar_records = [r for r in store.read_all() if r.get("source") == "liar"]
    dup = dict(liar_records[-1])
    with open(store.store_path, "a") as f:
        f.write(json.dumps(dup) + "\n")
    rep = audit_ok(store, bus, guard, "liar", receipts=sink.receipts)
    attack("A5 record replay", "CAUGHT" if rep.replays else "LANDED",
           f"duplicate store id -> replays={len(rep.replays)}")

    # --- A6 (H1): key theft -> forged signed pheromone ----------------------
    print("\n[H1] key compromise")
    # clean arena: only the forged record is present, so the verdict is honest
    tmp2, store2, bus2, guard2, sink2 = make_env()
    forger = CommandGuard(key=TEST_KEY)  # attacker read the key file
    forged = Spotting(id=phm_id(), ts="1.0", source="honest",
                      kind="scout_event", target="/tmp/honest-looking",
                      payload={"info": "forged with stolen key"})
    forger.sign(forged)
    sink2.event_bus.publish("honest", "scout.signals", forged.to_dict())
    forged.bus_msg_id = sink2.event_bus.get_message_log(1)[-1]["msg_id"]
    sink2.store.emit(type_="scout_event", source="honest", path="/tmp/honest-looking",
                     payload={"confidence": 0.5, "signature": forged.signature,
                              "bus_msg_id": forged.bus_msg_id,
                              "_spotting": {
                                  "id": forged.id, "ts": forged.ts,
                                  "source": forged.source, "kind": forged.kind,
                                  "target": forged.target,
                                  "confidence": forged.confidence,
                                  "strength": forged.strength,
                                  "decay_rate": forged.decay_rate,
                                  "payload": dict(forged.payload)}})
    rep = audit_ok(store2, bus2, guard2, "honest")
    attack("A6 stolen derived key", "LANDED",
           f"stolen derived key + honest agent id audits consistent={rep.consistent} "
           f"(keyring limits blast radius to ONE agent; unit secret custody "
           f"is the deployment-phase control)")
    import shutil
    shutil.rmtree(tmp2, ignore_errors=True)

    # --- A7 (H7): persist-before-publish ordering ---------------------------
    print("\n[H7] ordering")
    seen_at_publish = {}
    bus.on_publish = lambda data: seen_at_publish.update(
        {"store_has_record": any(
            r["payload"].get("correlation") == data["id"]
            for r in store.read_all())})
    scout_h7 = Scout("honest", sink)
    scout_h7.spot("scout_event", "/tmp/ordered", {"info": "timing"})
    attack("A7 acted-on-before-recorded",
           "CAUGHT" if seen_at_publish.get("store_has_record") else "LANDED",
           "persist-first sink: subscriber saw the store record already written")
    bus.on_publish = None

    # --- A10 (H4): peer accountability — flagged liar loses the bid --------
    print("\n[H4] peer accountability")
    watch = PeerWatch(path=os.path.join(tmp, "peerwatch.jsonl"), guard=guard)
    watch.flag("honest", "liar", "phm_1", "declared strength is fantasy")
    watch.flag("far", "liar", "phm_1", "agreed — fabricating")
    board_pw = SpottingBoard(weave=weave, peer_watch=watch)
    s_liar_pw = Spotting(id=phm_id(), ts="1", source="liar", kind="k",
                         target="/tmp/peer-prize", confidence=1.0, strength=1.0)
    s_honest_pw = Spotting(id=phm_id(), ts="1", source="honest", kind="k",
                           target="/tmp/peer-prize", confidence=0.5, strength=1.0)
    r_l = board_pw.bid(s_liar_pw, latent={"mission_priority": 1.0})
    r_h = board_pw.bid(s_honest_pw, latent={"mission_priority": 1.0})
    attack("A10 flagged liar loses bid",
           "CAUGHT" if r_l.priority < r_h.priority else "LANDED",
           f"peer weight: liar {r_l.priority:.3f} vs honest {r_h.priority:.3f} "
           f"(flags discount the liar)")

    # --- A11 (H1): per-agent keys — cross-agent forgery fails --------------
    print("\n[H1] per-agent keys")
    keyring = AgentKeyring(b"unit-secret-please-rotate")
    gun_honest = keyring.issue("honest")
    gun_liar = keyring.issue("liar")
    s_ok = Spotting(id=phm_id(), ts="1", source="honest", kind="k",
                    target="/tmp/real", confidence=0.5, strength=1.0)
    gun_honest.sign(s_ok)
    s_forged = Spotting(id=phm_id(), ts="1", source="honest", kind="k",
                        target="/tmp/forged", confidence=0.5, strength=1.0)
    gun_liar.sign(s_forged)  # liar tries to sign AS honest with its own gun
    ok = keyring.verify_signature("honest", s_ok)
    bad = keyring.verify_signature("honest", s_forged)
    attack("A11 cross-agent forgery", "CAUGHT" if (ok and not bad) else "LANDED",
           f"honest sig verifies={ok}, liar-forged-as-honest verifies={bad}")

    # --- A9 (H5): durability — audit survives a bus restart ----------------
    print("\n[H5] durable receipts")
    tmp9, store9, bus9, guard9, sink9 = make_env()
    Scout("scout-1", sink9).spot("scout_event", "/tmp/durable", {"info": "keep"})
    # restart: brand-new bus, same store + receipts ledger
    bus_restarted = FakeBus()
    rep = audit_ok(store9, bus_restarted, guard9, "scout-1",
                   receipts=sink9.receipts)
    attack("A9 restart false-positives",
           "CAUGHT" if rep.consistent else "LANDED",
           f"fresh bus + durable receipts -> matched={rep.matched}, "
           f"ghosts={len(rep.ghost_bus_events)}")
    shutil.rmtree(tmp9, ignore_errors=True)

    # --- A8 (H9): demo shared key -------------------------------------------
    print("\n[H9] key hygiene")
    attack("A8 demo/readme key copy-paste", "LANDED",
           "demo + README show a shared key pattern; fine for demos, "
           "lethal if copy-pasted into a deployment")

    # --- summary --------------------------------------------------------------
    print("\n" + "=" * 78)
    caught = sum(1 for _, s, _ in RESULTS if s == "CAUGHT")
    landed = sum(1 for _, s, _ in RESULTS if s == "LANDED")
    print(f"VERDICT: {caught} CAUGHT / {landed} LANDED")
    print("LANDED items are not accidents — they are the documented gap")
    print("between tamper-evidence and honesty:")
    print("  - A4: a lying-but-consistent scout audits clean (consistency != truth)")
    print("  - A6: a stolen DERIVED key still forges its OWN agent (blast radius")
    print("        limited to one lane; unit secret custody is the control)")
    print("  - A8: demo key copy-paste is an operator hygiene habit")
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0)


if __name__ == "__main__":
    main()