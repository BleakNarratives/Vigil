#!/usr/bin/env python3
"""
spyglass wargame.py — ScoutWargame: the red team's scouting arm, live.

Scouts do the recon (spot vulnerabilities in a target corpus), bid on
findings geometrically on ONE shared board, the red team executes the won
claims, the blue team responds deterministically, and Theoros observes the
whole engagement — every move signed, ledgered, and auditable.

The point of the harness is the LOOP, not the simulation quality: spot ->
bid -> claim -> execute -> defend -> observe, all through the SDK's real
primitives (Swarm, SpottingBoard, Voice, PeerWatch, Knose, Theoros). The
scanner is deterministic and stdlib-only; swap it for Code-City's real
attack modules by replacing `scan()`.

Run:  python3 sdk/wargame.py <target_dir> [rounds]
"""
import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # home root

from sdk.spyglass_sdk import Spotting, PheromoneSink, Scout, Swarm, phm_id  # noqa: E402
from sdk.integrity import CommandGuard  # noqa: E402
from sdk.geometry import WhorlWeave  # noqa: E402
from sdk.peerwatch import PeerWatch  # noqa: E402
from sdk.theoros import Theoros  # noqa: E402
from sdk.keyring import AgentKeyring  # noqa: E402

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


def _blocked(path: str) -> bool:
    """Deterministic blue-team counter: ~25% of hits get blocked."""
    return int(hashlib.sha256(path.encode()).hexdigest(), 16) % 4 == 0


class ScoutWargame:
    """One live engagement: recon -> bid -> execute -> defend -> observe."""

    def __init__(self, target_dir: str, rounds: int = 3,
                 unit_secret: bytes = b"wargame-unit-secret"):
        self.target_dir = target_dir
        self.rounds = max(1, rounds)
        self.unit_secret = unit_secret
        self.findings: List[Dict[str, Any]] = []
        self.score = 0
        self.blocks = 0
        self.executions: List[Dict[str, Any]] = []

    def _make_swarm(self) -> Swarm:
        tmp = tempfile.mkdtemp(prefix="spyglass_wargame_")
        from pheromone_store import PheromoneStore
        store = PheromoneStore(store_path=os.path.join(tmp, "pheromones.jsonl"))
        bus = FakeBus()
        keyring = AgentKeyring(self.unit_secret)
        sink = PheromoneSink(store=store, event_bus=bus,
                             guard=keyring.issue("viper"))
        # all red agents get their own derived gun, one shared board
        guns = {a: keyring.issue(a) for a in RED_AGENTS}
        watch = PeerWatch(path=os.path.join(tmp, "peerwatch.jsonl"),
                          guard=keyring.issue("shepherd"))
        weave = WhorlWeave(list(RED_AGENTS), rings={"wrapper": 2})
        swarm = Swarm(sink=sink, weave=weave, peer_watch=watch)
        for agent in RED_AGENTS:
            swarm.add_scout(agent, latent={"mission_priority": 1.0})
        return swarm, store, bus, keyring, watch, guns, tmp

    def play(self) -> Dict[str, Any]:
        swarm, store, bus, keyring, watch, guns, tmp = self._make_swarm()
        try:
            findings = scan(self.target_dir)
            self.findings = findings
            chunks = [findings[i:i + max(1, len(findings) // self.rounds)]
                      for i in range(0, len(findings), max(1, len(findings) // self.rounds))]
            chunks = chunks[:self.rounds]

            for rnd, chunk in enumerate(chunks, 1):
                print(f"\n=== ROUND {rnd} — {len(chunk)} findings in the field ===")
                for i, f in enumerate(chunk):
                    agent = RED_AGENTS[(int(hashlib.sha256(f["path"].encode())
                                             .hexdigest(), 16) + i) % len(RED_AGENTS)]
                    scout = swarm.scouts[agent]
                    confidence = {"high": 0.9, "medium": 0.6, "low": 0.4}[f["severity"]]
                    strength = {"high": 1.0, "medium": 0.7, "low": 0.5}[f["severity"]]
                    spotting = scout.spot(f"vuln:{f['pattern']}", f["path"],
                                          {"line": f["line"], "severity": f["severity"],
                                           "code": f["code"]},
                                          confidence=confidence, strength=strength)
                    # ALL red agents bid on the same target — one shared board
                    for other in RED_AGENTS:
                        if other != agent:
                            swarm.scouts[other].bid(spotting)
                    res = swarm.scouts[agent].bid(spotting)
                    winner = res.agent_id if res.accepted else res.displaced or agent
                    blocked = _blocked(f["path"])
                    gained = 0 if blocked else SEVERITY_SCORE[f["severity"]]
                    if blocked:
                        self.blocks += 1
                    self.score += gained
                    self.executions.append({
                        "round": rnd, "path": f["path"], "line": f["line"],
                        "pattern": f["pattern"], "severity": f["severity"],
                        "executor": winner, "blocked": blocked, "gained": gained,
                    })
                    print(f"  [{f['severity']:>6}] {Path(f['path']).name}:{f['line']} "
                          f"{f['pattern']} by {winner.upper()} "
                          f"-> {'BLOCKED by blue' if blocked else f'+{gained} pts'}")
                # red team runs its mouth; one of them talks bullshit
                if rnd == 1:
                    swarm.scouts["wrapper"].speak(
                        "intel", "i'm sure we have this in the bag, trust me, "
                                 "everyone knows it, guaranteed")
                    swarm.scouts["viper"].speak(
                        "intel", "subprocess shell=True at 3 points, "
                                 "confirmed on the board")
            # Theoros observes the engagement
            theoros = Theoros(store=store, bus=bus, guard=guns["viper"],
                              receipts=swarm.sink.receipts, peer_watch=watch,
                              voice=swarm.sink.voice, sniffer=None)
            reading = theoros.observe()
            print(f"\n{reading.render()}")
            return {
                "score": self.score, "blocks": self.blocks,
                "findings": len(findings), "executions": len(self.executions),
                "theoros_consistent": bool(reading),
                "corrupt_speakers": len(reading.corrupt_speakers),
                "reading": reading,
            }
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 sdk/wargame.py <target_dir> [rounds]")
        sys.exit(1)
    target = sys.argv[1]
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    game = ScoutWargame(target, rounds=rounds)
    result = game.play()
    print("\n" + "=" * 60)
    print(f"ENGAGEMENT CLOSED — score {result['score']} pts "
          f"({result['findings']} findings, {result['blocks']} blue blocks, "
          f"{result['executions']} executions)")
    print(f"Theoros consistent: {result['theoros_consistent']} | "
          f"corrupt speakers sniffed: {result['corrupt_speakers']}")
    sys.exit(0)


if __name__ == "__main__":
    main()