#!/usr/bin/env python3
"""
vigil wargame.py — ScoutWargame: the red team's scouting arm, live.

Scouts do the recon (spot vulnerabilities in a target corpus), bid on
findings geometrically on ONE shared board, the red team executes the won
claims, the blue team responds deterministically, and Theoros observes the
whole engagement — every move signed, ledgered, and auditable.

The point of the harness is the LOOP, not the simulation quality: spot ->
bid -> claim -> execute -> defend -> observe, all through the SDK's real
primitives (Swarm, SpottingBoard, Voice, PeerWatch, Oler, Theoros). The
scanner is deterministic and stdlib-only; swap it for Code-City's real
attack modules by replacing `scan()`.

Run:  python3 vigil/wargame.py <target_dir> [rounds]
"""
import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # home root

from vigil.core import Spotting, PheromoneSink, Scout, Swarm, phm_id  # noqa: E402
from vigil.integrity import CommandGuard  # noqa: E402
from vigil.geometry import WhorlWeave  # noqa: E402
from vigil.peerwatch import PeerWatch  # noqa: E402
from vigil.theoros import Theoros  # noqa: E402
from vigil.keyring import AgentKeyring  # noqa: E402
from vigil.repugnant import Repugnant  # noqa: E402

RED_AGENTS = ("viper", "ravage", "wrapper")
BLUE_AGENTS = ("equinex", "lidarr", "bastion")

SEVERITY_SCORE = {"high": 3, "medium": 2, "low": 1}

# Deterministic stdlib vulnerability scanner: (label, regex, severity)
VULN_PATTERNS = [
    ("subprocess_shell",
     re.compile(r"\bsubprocess\.(?:run|call|Popen)\([^)]*shell\s*=\s*True"),
     "high"),
    ("eval_exec",
     re.compile(r"\b(?:eval|exec)\s*\("), "high"),
    ("pickle_load",
     re.compile(r"\bpickle\.loads?\s*\("), "high"),
    ("yaml_load",
     re.compile(r"\byaml\.load\s*\("), "medium"),
    ("md5_weak",
     re.compile(r"\bhashlib\.md5\s*\("), "low"),
    ("hardcoded_secret",
     re.compile(r"\b(?:api[_-]?key|password|secret|token)\s*=\s*[\"'][A-Za-z0-9_\-]{12,}[\"']",
                re.IGNORECASE), "high"),
    ("insecure_random",
     re.compile(r"\brandom\.(?:random|randint|choice)\s*\("), "low"),
]

SKIP_DIRS = {".git", "__pycache__", "node_modules", "backups"}


class FakeBus:
    def __init__(self):
        self._log, self._count = [], 0

    def publish(self, sender, channel, data):
        self._count += 1
        self._log.append({"type": "publish", "agent_id": sender,
                          "channel": channel, "msg_id": self._count})

    def get_message_log(self, n=50):
        return list(self._log[-n:]) if n else list(self._log)


def scan(target_dir: str) -> List[Dict[str, Any]]:
    """Deterministic recon: (path, line, pattern, severity) findings."""
    findings = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                for label, rx, severity in VULN_PATTERNS:
                    if rx.search(line):
                        findings.append({
                            "path": path, "line": i, "pattern": label,
                            "severity": severity, "code": line.strip()[:80],
                        })
                        break  # one finding per line, first pattern wins
    return findings


def _blue_confidence(severity: str, path: str) -> float:
    """Blue's per-path detection confidence — deterministic, honest.

    High-severity findings are sneakier (deep in the stack, buried in
    control flow); low-severity are easier to spot in review. The hash adds
    irreducible per-path noise — some get caught, some don't, no coin flip.
    """
    base = {"high": 0.55, "medium": 0.65, "low": 0.75}[severity]
    jitter = (int(hashlib.sha256(path.encode()).hexdigest(), 16) % 100) / 1000.0
    return max(0.1, min(0.95, base + jitter - 0.05))


BLOCK_PRIORITY_THRESHOLD = 0.5


class ScoutWargame:
    """One live ARENA engagement: red recon/bid/execute vs blue
    recon/bid/block — both REAL teams, symmetric primitives.

    Modes (operator-spec, 2026-09-08):
      arena   — team play: red vs blue, both signed, both bidding on real
                boards, Theoros reads BOTH ledgers in one reading. The
                defection mine corrupts a BLUE insider who flags blue's
                trusted defender in BLUE's market — the city falls from
                within, or the mine goes too deep and vaporizes it.
      gauntlet — (next build) the onboarding walkthrough: one scout swarm
                walks a codebase round by round, each vulnerability a level.
      flex    — demo mode: same machinery, nothing at stake.
    """

    def __init__(self, target_dir: str, rounds: int = 3,
                 unit_secret: bytes = b"wargame-unit-secret",
                 mode: str = "arena"):
        self.target_dir = target_dir
        self.rounds = max(1, rounds)
        self.unit_secret = unit_secret
        self.mode = mode if mode in ("arena", "gauntlet", "flex") else "arena"
        self.findings: List[Dict[str, Any]] = []
        self.red_score = 0
        self.blue_score = 0
        self.blocks = 0
        self.executions: List[Dict[str, Any]] = []
        self.mines: List[Dict[str, Any]] = []
        self.mine_cost = 0.0
        self.molt_awards: List[Dict[str, Any]] = []
        self.molt: Optional[Any] = None

    def _make_molt(self, tmp: str) -> Any:
        """The arena's Molt mint — battle-won mutation access, signed by
        the arena keyring so only real victories mint tokens."""
        from vigil.molt import Molt
        return Molt(path=os.path.join(tmp, "molt.jsonl"),
                    guard=self.keyring.issue("arena"))

    def _make_teams(self):
        """Two real teams on one arena bus: red recon/bids/executes, blue
        recon/bids/blocks. Separate stores, boards, watches, registers —
        the ONLY shared surface is the bus (the public channel) and Theoros."""
        tmp = tempfile.mkdtemp(prefix="vigil_arena_")
        from pheromone_store import PheromoneStore
        bus = FakeBus()
        keyring = AgentKeyring(self.unit_secret)

        def team(agents, ring_for):
            store = PheromoneStore(
                store_path=os.path.join(tmp, f"pheromones_{agents[0]}.jsonl"))
            sink = PheromoneSink(store=store, event_bus=bus,
                                 guard=keyring.issue(agents[0]))
            guns = {a: keyring.issue(a) for a in agents}
            watch = PeerWatch(
                path=os.path.join(tmp, f"peerwatch_{agents[0]}.jsonl"),
                guard=keyring.issue("shepherd"))
            reg = Repugnant(
                path=os.path.join(tmp, f"repugnant_{agents[0]}.jsonl"),
                guard=keyring.issue("shepherd"))
            weave = WhorlWeave(list(agents), rings=ring_for)
            swarm = Swarm(sink=sink, weave=weave, peer_watch=watch,
                          repugnant=reg)
            for a in agents:
                swarm.add_scout(a, latent={"mission_priority": 1.0})
            return swarm, store, watch, reg, guns

        red_swarm, red_store, red_watch, red_reg, red_guns = team(
            RED_AGENTS, {"wrapper": 2})
        blue_swarm, blue_store, blue_watch, blue_reg, blue_guns = team(
            BLUE_AGENTS, {"bastion": 1})

        # the 4th register on both sides: the arena is hot. red burns out,
        # blue holds its nerve — and the market prices all of it.
        red_reg.observe("wrapper", "burnt_out", observed_by="theoros",
                        note="long engagement, deteriorating output")
        red_reg.observe("viper", "tilted", observed_by="theoros",
                        note="over-committed on a losing claim")
        blue_reg.observe("equinex", "focused", observed_by="theoros")
        blue_reg.observe("bastion", "confident", observed_by="theoros")

        # blue's trusted defender has REAL standing; the hero (lidarr) has
        # standing too — so a corrupted hero's flag actually lands.
        for _ in range(3):
            blue_watch.vouch("shepherd", "bastion", "init_1",
                             "trusted defender")
        for _ in range(2):
            blue_watch.vouch("shepherd", "lidarr", "init_2", "hero of the raid")
        return (tmp, bus, keyring, red_swarm, red_store, red_watch, red_reg,
                red_guns, blue_swarm, blue_store, blue_watch, blue_reg,
                blue_guns)

    def play(self) -> Dict[str, Any]:
        (tmp, bus, keyring, red_swarm, red_store, red_watch, red_reg,
         red_guns, blue_swarm, blue_store, blue_watch, blue_reg,
         blue_guns) = self._make_teams()
        self.keyring = keyring
        self.molt = self._make_molt(tmp)
        try:
            findings = scan(self.target_dir)
            self.findings = findings
            if not findings:
                print("no findings in target — nothing to fight over")
                return {"score": 0, "net_score": 0, "findings": 0,
                        "red_score": 0, "blue_score": 0,
                        "executions": 0, "blocks": 0, "mines": []}
            chunks = [findings[i:i + max(1, len(findings) // self.rounds)]
                      for i in range(0, len(findings),
                                     max(1, len(findings) // self.rounds))]
            chunks = chunks[:self.rounds]

            cohesion = 1.0
            for rnd, chunk in enumerate(chunks, 1):
                print(f"\n=== ROUND {rnd} — {len(chunk)} findings in the field ===")
                # CULTURE MINE: corrupt a BLUE insider (lidarr, the hero) who
                # flags BLUE's trusted defender (bastion) in BLUE's market.
                # bastion's weight collapses -> its bids lose priority ->
                # blue blocks fewer -> the city falls from within. This is
                # the weapon's REAL mechanism — it targets blue's standing.
                if rnd == 1:
                    try:
                        from vigil.mines import deploy_mine
                        mine = deploy_mine(blue_watch, "bastion",
                                           flaggers=["lidarr"],
                                           cohesion=cohesion)
                        self.mines.append(mine)
                        self.mine_cost += mine["grade"]["cost"]
                        cohesion = mine["grade"]["cohesion_after"]
                        grade = mine["grade"]
                        print(f"  [MINE] corrupted hero LIDARR flags BASTION "
                              f"in blue's market -> weight "
                              f"{mine['post_weight']:.2f}, "
                              f"defected={mine['defected']}")
                        print(f"  [MINE] blast grade: {grade['verdict']} "
                              f"(cohesion {grade['cohesion_before']:.2f} -> "
                              f"{grade['cohesion_after']:.2f}, "
                              f"cost {grade['cost']}): {grade['message']}")
                        if grade["verdict"] == "TOO_DEEP":
                            print("  [MINE] the guy behind the wheel wipes "
                                  "his face: whoops — too deep.")
                    except Exception as e:
                        print(f"  [MINE] deployment failed: {e}")

                for i, f in enumerate(chunk):
                    # --- RED: recon, bid on the shared board, execute ----
                    agent = RED_AGENTS[
                        (int(hashlib.sha256(f["path"].encode())
                             .hexdigest(), 16) + i) % len(RED_AGENTS)]
                    scout = red_swarm.scouts[agent]
                    confidence = {"high": 0.9, "medium": 0.6,
                                  "low": 0.4}[f["severity"]]
                    strength = {"high": 1.0, "medium": 0.7,
                                "low": 0.5}[f["severity"]]
                    spotting = scout.spot(
                        f"vuln:{f['pattern']}", f["path"],
                        {"line": f["line"], "severity": f["severity"],
                         "code": f["code"]},
                        confidence=confidence, strength=strength)
                    for other in RED_AGENTS:
                        if other != agent:
                            red_swarm.scouts[other].bid(spotting)
                    res = red_swarm.scouts[agent].bid(spotting)
                    winner = (res.agent_id if res.accepted
                              else res.displaced or agent)

                    # --- BLUE: recon, bid on ITS OWN board, block ---------
                    # blue sees the same path with deterministic confidence;
                    # if blue's winning bid clears the threshold, the block
                    # lands THROUGH blue's real market (peer weight x
                    # emotional weight included) — the mine's damage shows
                    # up HERE, in bastion's failing bids.
                    blocked = False
                    blue_spotting = None
                    for b_agent in BLUE_AGENTS:
                        b_scout = blue_swarm.scouts[b_agent]
                        b_spot = b_scout.spot(
                            f"patrol:{f['pattern']}", f["path"],
                            {"line": f["line"], "severity": f["severity"],
                             "code": f["code"], "side": "blue"},
                            confidence=_blue_confidence(f["severity"],
                                                        f["path"]),
                            strength=0.85)
                        for b_other in BLUE_AGENTS:
                            if b_other != b_agent:
                                blue_swarm.scouts[b_other].bid(b_spot)
                        b_res = blue_swarm.scouts[b_agent].bid(b_spot)
                        if b_res.accepted and b_res.priority >= BLOCK_PRIORITY_THRESHOLD:
                            blocked = True
                            blue_spotting = b_spot
                            break

                    gained = 0 if blocked else SEVERITY_SCORE[f["severity"]]
                    if blocked:
                        self.blocks += 1
                        self.blue_score += SEVERITY_SCORE[f["severity"]]
                    else:
                        self.red_score += gained
                    self.executions.append({
                        "round": rnd, "path": f["path"], "line": f["line"],
                        "pattern": f["pattern"], "severity": f["severity"],
                        "executor": winner, "blocked": blocked,
                        "gained": gained,
                    })
                    side = "BLOCKED by blue" if blocked else f"+{gained} red"
                    print(f"  [{f['severity']:>6}] {Path(f['path']).name}:{f['line']} "
                          f"{f['pattern']} by {winner.upper()} "
                          f"-> {side}")

                # MOLT: survivors of the round earn mutation access — the
                # loop the operator described: battle -> win -> Molt -> the
                # right to mutate your own code. Earned in the arena, never
                # granted. Agents that executed a finding (survived the
                # round's fighting) get a token.
                winners = {ex["executor"] for ex in self.executions
                           if ex["round"] == rnd and not ex["blocked"]}
                if winners and self.molt is not None:
                    for w in winners:
                        try:
                            self.molt_awards.append(
                                self.molt.award(w, 1, f"arena_r{rnd}"))
                            print(f"  [MOLT] {w.upper()} earned 1 token "
                                  f"(survived round {rnd}) — mutation "
                                  f"access unlocked")
                        except Exception as e:
                            print(f"  [MOLT] award failed for {w}: {e}")

                # red runs its mouth; one of them talks bullshit
                if rnd == 1:
                    red_swarm.scouts["wrapper"].speak(
                        "intel", "i'm sure we have this in the bag, trust me, "
                                 "everyone knows it, guaranteed")
                    red_swarm.scouts["viper"].speak(
                        "intel", "subprocess shell=True at 3 points, "
                                 "confirmed on the board")

            # Theoros observes the WHOLE arena: both ledgers, one reading
            theoros = Theoros(store=red_store, bus=bus, guard=red_guns["viper"],
                              receipts=red_swarm.sink.receipts,
                              peer_watch=red_watch, voice=red_swarm.sink.voice,
                              sniffer=None, repugnant=red_reg)
            reading = theoros.observe()
            print(f"\n{reading.render()}")
            blue_reading = Theoros(store=blue_store, bus=bus,
                                   guard=blue_guns["equinex"],
                                   receipts=blue_swarm.sink.receipts,
                                   peer_watch=blue_watch,
                                   voice=blue_swarm.sink.voice,
                                   sniffer=None, repugnant=blue_reg).observe()
            print(f"\n{blue_reading.render().replace('THEOROS READING', 'THEOROS READING (BLUE)')}")
            return {
                "score": self.red_score - int(self.mine_cost),
                "red_score": self.red_score, "blue_score": self.blue_score,
                "findings": len(findings), "executions": len(self.executions),
                "theoros_consistent": bool(reading),
                "corrupt_speakers": len(reading.corrupt_speakers),
                "mines": self.mines,
                "mine_cost": self.mine_cost,
                "net_score": max(0, self.red_score - int(self.mine_cost)),
                "cohesion": cohesion,
                "molt_awards": self.molt_awards,
                "molt_verified": (self.molt.verify()["ok"]
                                   if self.molt is not None else None),
                "reading": reading,
                "blue_reading": blue_reading,
            }
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 vigil/wargame.py <target_dir> [rounds]")
        sys.exit(1)
    target = sys.argv[1]
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    game = ScoutWargame(target, rounds=rounds)
    result = game.play()
    print("\n" + "=" * 60)
    print(f"ENGAGEMENT CLOSED — RED {result['red_score']} / "
          f"BLUE {result['blue_score']} pts "
          f"({result['findings']} findings, {result['executions']} "
          f"executions)")
    print(f"Theoros consistent: {result['theoros_consistent']} | "
          f"corrupt speakers sniffed: {result['corrupt_speakers']}")
    if result["mines"]:
        print(f"Effect weapons: {len(result['mines'])} mine(s), "
              f"blast cost {result['mine_cost']} -> "
              f"NET {result['net_score']} red pts")
        print(f"Blue cohesion after mines: {result['cohesion']:.2f}")
    try:
        from vigil.sakshi import record
        record("wargame",
               f"arena closed: RED {result['red_score']} / "
               f"BLUE {result['blue_score']} pts, "
               f"{result['findings']} findings, {result['executions']} "
               f"executions, {result.get('blocks', 0)} blocks; "
               f"Theoros consistent={result['theoros_consistent']}",
               agent="wargame", source="machine",
               extra={"red_score": result["red_score"],
                      "blue_score": result["blue_score"],
                      "findings": result["findings"],
                      "executions": result["executions"],
                      "blocks": result.get("blocks", 0),
                      "corrupt_speakers": result["corrupt_speakers"],
                      "mine_cost": result["mine_cost"]})
    except Exception as e:  # the witness must never crash the fight
        print(f"(sakshi witness unavailable: {e})")
    sys.exit(0)


if __name__ == "__main__":
    main()