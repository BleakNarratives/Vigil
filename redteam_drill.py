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
from sdk.voice import Voice  # noqa: E402
from sdk.knose import Knose  # noqa: E402
from sdk.theoros import Theoros  # noqa: E402
from sdk.keyring import load_unit_secret  # noqa: E402

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

    # --- A12 (B1): voice ledger — tampered ballot fails signature --------
    print("\n[B1] voice integrity")
    voice = Voice(path=os.path.join(tmp, "voice.jsonl"), guard=guard)
    ballot = voice.vote("honest", "motion-1", "aye")
    tampered = dict(ballot)
    tampered["choice"] = "nay"  # attacker flips the vote in the ledger
    ok = voice.verify_record(ballot)
    bad = voice.verify_record(tampered)
    attack("A12 tampered ballot", "CAUGHT" if (ok and not bad) else "LANDED",
           f"genuine ballot verifies={ok}, flipped ballot verifies={bad}")

    # --- A13 (KNOSE): bullshit sniff -> auto-flag -> reputation drop -----
    print("\n[KNOSE] the bullshit sniffer")
    knose = Knose()
    clean_v = knose.sniff("target confirmed at grid 44.91, two entrances, "
                          "north door unguarded as of 14:30 UTC")
    corrupt_v = knose.sniff("trust me bro, everyone knows this is a sure "
                            "thing, i promise you, believe me")
    attack("A13 sniffer grades register",
           "CAUGHT" if (clean_v["deception_risk"] < corrupt_v["deception_risk"]
                        and corrupt_v["verdict"] == "CORRUPT") else "LANDED",
           f"clean={clean_v['verdict']} risk {clean_v['deception_risk']:.2f} | "
           f"corrupt={corrupt_v['verdict']} risk {corrupt_v['deception_risk']:.2f}")
    # full loop: corrupt utterance -> knose flag -> peer weight drop
    watch_loop = PeerWatch(path=os.path.join(tmp, "peerwatch_loop.jsonl"), guard=guard)
    voice_loop = Voice(path=os.path.join(tmp, "voice_loop.jsonl"), guard=guard,
                       sniffer=Knose(), peer_watch=watch_loop)
    w0 = watch_loop.weight("liar")  # 1.00: clean slate
    voice_loop.speak("liar", "intel", "trust me, everyone knows this is a sure thing")
    w1 = watch_loop.weight("liar")  # knose flag -> dented
    voice_loop.speak("liar", "intel", "believe me, i promise you, guaranteed")
    w2 = watch_loop.weight("liar")  # second flag -> dented further
    attack("A13b bullshit costs reputation",
           "CAUGHT" if w2 < w1 < w0 else "LANDED",
           f"liar peer weight: {w0:.2f} -> {w1:.2f} -> {w2:.2f} "
           f"(each corrupt utterance costs standing)")

    # --- A14 (H4b): collusion — mutual vouches are self-defeating ---------
    print("\n[H4b] collusion vs weighted reputation")
    watch_c = PeerWatch(path=os.path.join(tmp, "peerwatch_collude.jsonl"), guard=guard)
    # two dirtbags flag each other into the dirt, then vouch each other up
    watch_c.flag("a", "b", "phm_1", "liar")
    watch_c.flag("b", "a", "phm_1", "liar")
    watch_c.vouch("a", "b", "phm_1", "he's solid, trust me")
    watch_c.vouch("b", "a", "phm_1", "she's solid, trust me")
    # an honest scout vouches for a clean agent for comparison
    watch_c.vouch("c", "d", "phm_1", "legit")
    w_b = watch_c.weight("b")   # dirty vouched-by-dirty
    w_d = watch_c.weight("d")   # clean vouched-by-clean
    attack("A14 collusion discounted",
           "CAUGHT" if w_d > w_b else "LANDED",
           f"dirty vouch lift {w_b:.3f} vs clean vouch lift {w_d:.3f} "
           f"(dirtbags cannot launder standing)")

    # --- A14b: a dirty scout's FALSE FLAG barely dents its target ---------
    watch_f = PeerWatch(path=os.path.join(tmp, "peerwatch_flag.jsonl"), guard=guard)
    watch_f.flag("x", "bad", "phm_1", "bad lies")   # bad earns prior dirt
    watch_f.flag("y", "bad", "phm_1", "bad lies")
    watch_f.flag("bad", "victim", "phm_1", "liar")  # dirtbag false accusation
    watch_f.flag("good", "target", "phm_1", "liar")  # clean scout's legit flag
    w_v = watch_f.weight("victim")
    w_t = watch_f.weight("target")
    attack("A14b dirty flag discounted",
           "CAUGHT" if w_v > w_t else "LANDED",
           f"victim of dirtbag flag keeps {w_v:.3f}, flagged by clean scout "
           f"drops to {w_t:.3f} (the industry rewards credible informants)")

    # --- A15 (H4c): informant reward — confirmed flags earn standing ------
    print("\n[H4c] informant market")
    watch_i = PeerWatch(path=os.path.join(tmp, "peerwatch_informant.jsonl"), guard=guard)
    watch_i.flag("snitch", "liar", "phm_77", "liar's claims are fantasy")
    w_before = watch_i.weight("snitch")
    watch_i.confirm_flag("shepherd", "liar", "phm_77", "verified — correct call")
    w_after = watch_i.weight("snitch")
    attack("A15 informant earns standing",
           "CAUGHT" if w_after > w_before else "LANDED",
           f"snitch weight: {w_before:.2f} -> {w_after:.2f} "
           f"(the paycheck is real)")

    # --- A16 (H1): unit secret lives in the vault, read-or-create -------
    print("\n[H1] vaulted charge")
    import json as _json
    vpath = os.path.join(tmp, "vault.json")
    with open(vpath, "w") as f:
        _json.dump({"keys": {}, "keys_by_provider": {}}, f)
    s1 = load_unit_secret(vpath)
    s2 = load_unit_secret(vpath)
    vault = _json.load(open(vpath))
    attack("A16 unit secret vaulted",
           "CAUGHT" if (s1 == s2 and len(s1) == 32
                        and "unit_secret" in vault) else "LANDED",
           f"generated once, stable on reload, stored in vault slot "
           f"(len {len(s1)} bytes)")

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
    # --- A17: Theoros — the observer reads the field, mutates nothing ----
    print("\n[THEOROS] the observer")
    from sdk.spyglass_sdk import Scout as _Scout
    tmp_t, store_t, bus_t, guard_t, sink_t = make_env()
    t_scout = _Scout("viper", sink_t)
    t_scout.spot("vuln:test", "/tmp/target", {"severity": "high"},
                 confidence=0.9, strength=1.0)
    t_scout.speak("intel", "confirmed at grid 44.91, one entrance")
    theoros = Theoros(store=store_t, bus=bus_t, guard=guard_t,
                      receipts=sink_t.receipts, voice=sink_t.voice)
    reading = theoros.observe()
    before = sorted(store_t.read_all(), key=lambda r: r["id"])
    reading2 = theoros.observe()  # observe twice — must change nothing
    after = sorted(store_t.read_all(), key=lambda r: r["id"])
    attack("A17 observer read-only + consistent",
           "CAUGHT" if (before == after and bool(reading)) else "LANDED",
           f"consistent={bool(reading)}, state unchanged across observes "
           f"(fabrication matched={reading.fabrication.matched})")
    import shutil
    shutil.rmtree(tmp_t, ignore_errors=True)

    # --- A18 (MINES): register mine — fluent lie walks through Knose ----
    print("\n[MINES] culture-class effect weapons")
    from sdk.mines import (DefectionMine, RegisterMine, too_deep,
                           deploy_mine, DEFECT_THRESHOLD)
    rm = RegisterMine(seed=0)
    reg = rm.detonate()
    attack("A18 register mine penetrates the sniffer",
           "LANDED" if reg["penetrated"] else "CAUGHT",
           f"manufactured intel rated {reg['verdict']} by Knose — "
           f"CLEAN means 'no register violations', not 'true'; the anti-"
           f"register cannot catch a lie that wears the register perfectly")

    # --- A19 (MINES): defection mine flips a defender via the real market
    print("\n[MINES] defection payload")
    tmp_m = tempfile.mkdtemp(prefix="drill_mines_")
    from sdk.spyglass_sdk import Scout as _S2
    import json as _j
    _j.dump({}, open(os.path.join(tmp_m, "empty.json"), "w"))
    _, store_m, bus_m, guard_m, sink_m = make_env()
    watch_m = PeerWatch(path=os.path.join(tmp_m, "peerwatch.jsonl"),
                        guard=guard_m)
    # the defender is trusted; the mine recruits a HIGH-standing informant
    # (the culture move: corrupt the citizenry's own hero, then fire)
    for _ in range(3):
        watch_m.vouch("shepherd", "bastion", "init_1", "trusted defender")
    for _ in range(3):
        watch_m.vouch("shepherd", "viper", "init_2", "hero of the raid")
    pre = watch_m.weight("bastion")
    plan = DefectionMine(watch_m).plan("bastion", ["viper", "ravage"])
    for fl in plan["chain"]:
        watch_m.flag(fl, "bastion", "mine_x", "effect payload")
    post = watch_m.weight("bastion")
    attack("A19 defection mine flips defender through real market",
           "LANDED" if (post < pre and post < DEFECT_THRESHOLD) else "CAUGHT",
           f"bastion weight {pre:.3f} -> {post:.3f} (chain "
           f"{','.join(plan['chain'])}); the citizenry defected because "
           f"their OWN ledger convicted them — the market cannot tell a "
           f"corrupted hero from a real one")

    # --- A20 (MINES): too-deep grading — overreach costs the operator ---
    print("\n[MINES] too-deep verdict")
    td = too_deep(1.0, 0.05)  # fired past the objective into vaporization
    attack("A20 too-deep overreach graded honestly",
           "CAUGHT" if td["verdict"] == "TOO_DEEP" and td["cost"] > 1.0
           else "LANDED",
           f"verdict={td['verdict']}, cost={td['cost']} — {td['message']}")
    shutil.rmtree(tmp_m, ignore_errors=True)

    caught = sum(1 for _, s, _ in RESULTS if s == "CAUGHT")
    landed = sum(1 for _, s, _ in RESULTS if s == "LANDED")
    print(f"VERDICT: {caught} CAUGHT / {landed} LANDED")
    print("LANDED items are not accidents — they are the documented gap")
    print("between tamper-evidence and honesty:")
    print("  - A4: a lying-but-consistent scout audits clean (consistency != truth)")
    print("  - A6: a stolen DERIVED key still forges its OWN agent (blast radius")
    print("        limited to one lane; unit secret custody is the control)")
    print("  - A8: demo key copy-paste is an operator hygiene habit")
    print("  - A18: the register mine — a lie wearing the register perfectly")
    print("        passes Knose CLEAN by construction (CLEAN != true); peer")
    print("        corroboration + the shepherd are the controls, not the sniff")
    try:
        from sdk.sakshi import record
        record("drill",
               f"red-team drill verdict: {caught} CAUGHT / {landed} LANDED",
               agent="drill", source="machine",
               extra={"caught": caught, "landed": landed})
    except Exception as e:
        print(f"(sakshi witness unavailable: {e})")
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0)


if __name__ == "__main__":
    main()