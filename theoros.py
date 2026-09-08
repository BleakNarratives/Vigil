#!/usr/bin/env python3
"""
vigil theoros.py — THEOROS: the observer.

From Greek *theoros*: the spectator sent to observe — the root of
"theory". Theoros is the face of the monitoring layer: it watches the
swarm's entire ledger surface (fabrication audit, voice lane, reputation
standings, votes, suggestions, receipt chain) and produces one reading —
understanding from watching. Read-only by contract: it NEVER mutates
state. When it speaks, it is the final word a shepherd can act on.

The observer's discipline (the brown-hat triad, applied):
    * STRIKE THE FORK  — every claim in the report is derived from ledgers,
                         never from confidence.
    * WALK THE CHAIN   — the report cites what it walked: receipts,
                         signatures, flags, votes.
    * SMELL THE REGISTER — the Knose sweep is part of every observation.

Theoros does not judge intent. It reports what the swarm's own signed
records say, which is the only ground truth available.

DNA_TAG
ORIGIN: BleakNarratives/sdk
PILLAR: swarm-coordination
DEPS: dataclasses,datetime,typing,sdk.fabrication,sdk.knose
ROLE: read-only observer; the monitoring layer's face
AUTHOR: Bleak
SESSION: 2026-09-08
TIER: 2
/DNA_TAG
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from vigil.fabrication import FabricationDetector
except ImportError:
    try:
        from fabrication import FabricationDetector
    except ImportError:
        FabricationDetector = None

try:
    from vigil.knose import Knose
except ImportError:
    try:
        from knose import Knose
    except ImportError:
        Knose = None

try:
    from vigil.integrity import CommandGuard
except ImportError:
    try:
        from integrity import CommandGuard
    except ImportError:
        CommandGuard = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class TheorosReading:
    """One observation pass. Truthy iff the swarm's ledgers are consistent
    and no register corruption surfaced in the voice lane."""
    observed_at: str = field(default_factory=_now)
    fabrication: Optional[Any] = None
    corrupt_speakers: List[Dict[str, Any]] = field(default_factory=list)
    standings: List[Dict[str, float]] = field(default_factory=list)
    motions: List[Dict[str, Any]] = field(default_factory=list)
    suggestions_open: int = 0
    receipts_durable: bool = False
    receipt_count: int = 0
    issues: List[str] = field(default_factory=list)

    @property
    def consistent(self) -> bool:
        fab_ok = self.fabrication is None or bool(self.fabrication)
        return bool(fab_ok and not self.corrupt_speakers and not self.issues)

    def __bool__(self) -> bool:
        return self.consistent

    def summary(self) -> str:
        fab = (f"fab={'OK' if bool(self.fabrication) else 'HITS'}"
               if self.fabrication is not None else "fab=n/a")
        return (f"Theoros {self.observed_at} consistent={self.consistent} "
                f"{fab} corrupt_speakers={len(self.corrupt_speakers)} "
                f"standings={len(self.standings)} motions={len(self.motions)} "
                f"suggestions={self.suggestions_open} receipts={self.receipt_count}")

    def render(self) -> str:
        """The observer's written reading — human-readable verdict."""
        lines = [f"THEOROS READING — {self.observed_at}",
                 f"  consistency: {'CLEAR' if self.consistent else 'CORRUPT'}"]
        if self.fabrication is not None:
            lines.append(f"  fabrication: {self.fabrication.summary()}")
        for sp in self.corrupt_speakers:
            lines.append(f"  corrupt register: {sp.get('actor')} risk "
                         f"{sp.get('deception_risk', 0):.2f} — "
                         f"\"{str(sp.get('message'))[:60]}\"")
        if self.standings:
            top = ", ".join(f"{s['agent']}={s['weight']:.2f}"
                            for s in self.standings[:3])
            lines.append(f"  standing leaders: {top}")
        for m in self.motions:
            lines.append(f"  motion {m['motion']}: {m['ayes']}aye/{m['nays']}nay "
                         f"passes={m['passes']}")
        lines.append(f"  suggestion box: {self.suggestions_open} open")
        lines.append(f"  receipt chain: {self.receipt_count} durable="
                     f"{self.receipts_durable}")
        for issue in self.issues:
            lines.append(f"  issue: {issue}")
        return "\n".join(lines)


class Theoros:
    """Read-only observer over the swarm's ledger surface."""

    def __init__(self, store: Any = None, bus: Any = None,
                 guard: Optional[Any] = None, receipts: Any = None,
                 peer_watch: Any = None, voice: Any = None,
                 sniffer: Any = None, keyring: Any = None):
        self.store = store
        self.bus = bus
        self.guard = guard
        self.receipts = receipts
        self.peer_watch = peer_watch
        self.voice = voice
        self.sniffer = sniffer if sniffer is not None else (Knose() if Knose else None)
        self.keyring = keyring  # unused today; the charge's custody record

    def observe(self, agent_id: Optional[str] = None) -> TheorosReading:
        """One pass over every ledger. Read-only — this function mutates
        nothing. That is the observer's contract."""
        reading = TheorosReading()

        # 1. fabrication audit (walk the chain: store vs receipts vs bus)
        if FabricationDetector is not None and self.store is not None \
                and self.bus is not None:
            reading.fabrication = FabricationDetector(
                store=self.store, bus=self.bus, guard=self.guard,
                receipts=self.receipts).audit(agent_id)
            for issue in reading.fabrication.issues:
                reading.issues.append(issue)

        # 2. receipt durability (H5)
        if self.receipts is not None:
            reading.receipts_durable = bool(getattr(self.receipts, "durable", False))
            reading.receipt_count = len(self.receipts.all_ids())

        # 3. voice lane: sniff the register, tally motions, count suggestions
        if self.voice is not None:
            for rec in self.voice.history(kind="speak"):
                message = rec.get("message", "")
                if self.sniffer is not None and message:
                    verdict = self.sniffer.sniff(message)
                    if verdict.get("deception_risk", 0.0) >= self.sniffer.threshold:
                        reading.corrupt_speakers.append({
                            "actor": rec.get("actor"), "message": message,
                            "deception_risk": verdict.get("deception_risk", 0.0),
                            "verdict": verdict.get("verdict"),
                        })
            motions = {r.get("topic") for r in self.voice.history(kind="vote")}
            for motion in sorted(motions):
                reading.motions.append(self.voice.tally(motion))
            reading.suggestions_open = len(self.voice.suggestions())

        # 4. reputation standings
        if self.peer_watch is not None:
            agents = {r.get("target_agent") for r in self.peer_watch.history()}
            agents |= {r.get("actor") for r in self.peer_watch.history()}
            reading.standings = sorted(
                ({"agent": a, "weight": self.peer_watch.weight(a)} for a in agents
                 if a and a != "knose"),
                key=lambda s: s["weight"], reverse=True)

        return reading


__all__ = ["Theoros", "TheorosReading"]