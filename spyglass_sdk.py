#!/usr/bin/env python3
"""
spyglass_sdk.py — Scout-Spotter SDK.
A substrate for swarm agents to spot, bid, claim, and report.
Zero-dependency core (stdlib only) + optional pheromone/bus integration.

Since 2026-09-08 the SDK is a three-layer substrate, not a skeleton:

  1. INTEGRITY   — sdk/integrity.py   CommandGuard signs every pheromone with
                   a local HMAC key BEFORE emission (proof-of-work), so the
                   log can be verified against tampering/fabrication.
  2. GEOMETRY    — sdk/geometry.py    WhorlWeave gives every scout a weave
                   position; bid() computes confidence/strength from that
                   geometry (quadratic dispersion) + latent state (health,
                   resource cost, mission priority) instead of FCFS arrival.
  3. FABRICATION — sdk/fabrication.py FabricationDetector cross-checks the
                   scout's own pheromone log against the SyntaxEventBus log
                   for consistency (matched / unmatched / ghosts / sig fails).

Every capability is a separate module with a versioned public API and
documented extension points — see sdk/module_registry.json. Agents may patch
internals without breaking call sites as long as the public API + invariants
hold (that is the self-modification contract).

DNA_TAG
ORIGIN: BleakNarratives/sdk
PILLAR: swarm-coordination
DEPS: sdk.integrity,sdk.geometry,sdk.fabrication,pheromone_store,SyntaxIntelligence.event_bus
ROLE: scout-spotter swarm substrate (spot/bid/claim/report)
AUTHOR: Bleak
SESSION: 2026-09-08
TIER: 2
/DNA_TAG
"""
from dataclasses import dataclass, field
import json
import time
import sys
from typing import Dict, Any, List, Optional

# Optional capability modules — degrade gracefully when unavailable.
try:
    from sdk.integrity import CommandGuard, IntegrityError, SPOTTING_EMBED_KEY
except ImportError:
    try:
        from integrity import CommandGuard, IntegrityError, SPOTTING_EMBED_KEY
    except ImportError:
        CommandGuard = None
        IntegrityError = Exception
        SPOTTING_EMBED_KEY = "_spotting"

try:
    from sdk.geometry import WhorlWeave, WeavePosition
except ImportError:
    try:
        from geometry import WhorlWeave, WeavePosition
    except ImportError:
        WhorlWeave = None
        WeavePosition = None

try:
    from sdk.fabrication import FabricationDetector, FabricationReport
except ImportError:
    try:
        from fabrication import FabricationDetector, FabricationReport
    except ImportError:
        FabricationDetector = None
        FabricationReport = None

# Attempt optional ecosystem imports
try:
    from pheromone_store import PheromoneStore
except ImportError:
    PheromoneStore = None

try:
    from SyntaxIntelligence.event_bus import SyntaxEventBus
except ImportError:
    SyntaxEventBus = None

SCOUT_CHANNEL = "scout.signals"


@dataclass(slots=True)
class Spotting:
    """Canonical Spotting shape.

    signature — HMAC over the command path, attached by CommandGuard BEFORE
                emission (empty until then).
    bus_msg_id — msg_id assigned by the SyntaxEventBus publish, captured by
                the sink and embedded in the store record for fabrication
                cross-checks.
    """
    id: str
    ts: str
    source: str
    kind: str
    target: str
    confidence: float = 0.5
    strength: float = 1.0
    decay_rate: float = 0.0
    payload: Dict[str, Any] = field(default_factory=dict)
    signature: str = ""
    bus_msg_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "source": self.source,
            "kind": self.kind,
            "target": self.target,
            "confidence": self.confidence,
            "strength": self.strength,
            "decay_rate": self.decay_rate,
            "payload": self.payload,
            "signature": self.signature,
            "bus_msg_id": self.bus_msg_id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


def phm_id(prefix: str = "phm") -> str:
    return f"{prefix}_{int(time.time()*1000)}"


class PheromoneSink:
    """Handles reporting spottings to persistence and the event bus.

    Order of operations (the integrity contract):
      1. sign the spotting with the CommandGuard (if present) — BEFORE emit
      2. publish to the bus, capture the bus msg_id
      3. persist to the store with signature + bus_msg_id embedded, so the
         store record and the bus log are mutually verifiable.
    """
    def __init__(self, store: Optional[Any] = None, event_bus: Optional[Any] = None,
                 guard: Optional[Any] = None):
        self.store = store if store else (PheromoneStore() if PheromoneStore else None)
        self.event_bus = event_bus
        self.guard = guard if guard is not None else (CommandGuard() if CommandGuard else None)

    def report(self, spotting: Spotting) -> Spotting:
        # 1. proof-of-work: sign before anything leaves the scout.
        if self.guard is not None:
            self.guard.sign(spotting)

        # 2. bus propagation first, so we can capture the unforgeable msg_id.
        if self.event_bus:
            self.event_bus.publish(spotting.source, SCOUT_CHANNEL, spotting.to_dict())
            recent = self.event_bus.get_message_log(1)
            if recent:
                spotting.bus_msg_id = recent[-1].get("msg_id")

        # 3. persistence, correlated to the bus record. The signed Spotting
        # fields are embedded under SPOTTING_EMBED_KEY so the record can be
        # verified against the exact canonical string signed in step 1 (store
        # records use type/path/timestamp, which would otherwise not match).
        if self.store:
            self.store.emit(
                type_=spotting.kind,
                source=spotting.source,
                path=spotting.target,
                strength=spotting.strength,
                decay_rate=spotting.decay_rate,
                payload={
                    **spotting.payload,
                    "confidence": spotting.confidence,
                    "signature": spotting.signature,
                    "bus_msg_id": spotting.bus_msg_id,
                    SPOTTING_EMBED_KEY: {
                        "id": spotting.id,
                        "ts": spotting.ts,
                        "source": spotting.source,
                        "kind": spotting.kind,
                        "target": spotting.target,
                        "confidence": spotting.confidence,
                        "strength": spotting.strength,
                        "decay_rate": spotting.decay_rate,
                        "payload": dict(spotting.payload),
                    },
                }
            )
        return spotting


@dataclass(slots=True)
class BidResult:
    """Outcome of one bid. Truthy iff accepted (keeps old `if board.bid()`).

    priority   — geometric (position + latent) bid priority
    displaced  — agent id that lost the claim when this bid won
    geometry   — the weave modulation dict, for auditability
    """
    accepted: bool
    target: str
    agent_id: str
    priority: float
    reason: str = ""
    displaced: Optional[str] = None
    geometry: Dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.accepted


class SpottingBoard:
    """Bid management: geometric priority, FCFS as the tie-break only.

    Without a weave this degrades to priority = confidence * strength
    (still not raw arrival speed). With a WhorlWeave, confidence/strength
    are computed from the agent's weave position + latent state, and a
    higher-priority bid displaces an earlier claim.
    """
    def __init__(self, weave: Optional[Any] = None):
        self.claims: Dict[str, Dict[str, Any]] = {}
        self.weave = weave

    def bid(self, spotting: Spotting, latent: Optional[Dict[str, float]] = None,
            source_position: Optional[Any] = None) -> BidResult:
        if self.weave is not None:
            geom = self.weave.modulate(spotting, source_position=source_position,
                                       latent=latent)
            confidence, strength, priority = (geom["confidence"], geom["strength"],
                                              geom["priority"])
        else:
            confidence, strength = spotting.confidence, spotting.strength
            priority = confidence * strength
            geom = {}

        existing = self.claims.get(spotting.target)
        if existing is None:
            self._claim(spotting.target, spotting, priority, confidence, strength)
            return BidResult(True, spotting.target, spotting.source, priority,
                             reason="claimed", geometry=geom)

        if priority > existing["priority"]:
            displaced = existing["agent_id"]
            self._claim(spotting.target, spotting, priority, confidence, strength)
            return BidResult(True, spotting.target, spotting.source, priority,
                             reason="displaced", displaced=displaced, geometry=geom)

        return BidResult(False, spotting.target, spotting.source, priority,
                         reason="outbid", geometry=geom)

    def _claim(self, target: str, spotting: Spotting, priority: float,
               confidence: float, strength: float):
        self.claims[target] = {
            "agent_id": spotting.source,
            "ts": time.time(),
            "priority": priority,
            "confidence": confidence,
            "strength": strength,
            "spotting_id": spotting.id,
        }

    def release(self, target: str):
        self.claims.pop(target, None)


class Scout:
    """Navi-like sub-agent helper, weave-aware and self-auditing."""
    def __init__(self, agent_id: str, sink: PheromoneSink,
                 weave: Optional[Any] = None, latent: Optional[Dict[str, float]] = None,
                 board: Optional[SpottingBoard] = None):
        self.agent_id = agent_id
        self.sink = sink
        self.weave = weave
        self.latent = latent or {}
        self.board = board if board is not None else SpottingBoard(weave=weave)

    def spot(self, kind: str, target: str, payload: Dict[str, Any],
             confidence: float = 0.5, strength: float = 1.0,
             decay_rate: float = 0.0) -> Spotting:
        s = Spotting(
            id=phm_id(),
            ts=str(time.time()),
            source=self.agent_id,
            kind=kind,
            target=target,
            confidence=confidence,
            strength=strength,
            decay_rate=decay_rate,
            payload=payload
        )
        self.sink.report(s)
        return s

    def bid(self, spotting: Spotting,
            source_position: Optional[Any] = None) -> BidResult:
        """Convenience: bid through this scout's board with its own latent
        state. The board computes position-aware confidence/strength."""
        return self.board.bid(spotting, latent=self.latent,
                              source_position=source_position)

    def audit_self(self) -> Any:
        """Cross-check own pheromone log against the bus log (fabrication
        detection). Returns a FabricationReport; truthy iff consistent."""
        if FabricationDetector is None:
            raise RuntimeError("FabricationDetector unavailable (sdk/fabrication.py missing)")
        detector = FabricationDetector(
            store=self.sink.store, bus=self.sink.event_bus,
            guard=self.sink.guard, agent_id=self.agent_id)
        return detector.audit()


def main():
    if len(sys.argv) < 2:
        print("Usage: spyglass_sdk.py [demo]")
        sys.exit(1)

    if sys.argv[1] == "demo":
        print("Running Spyglass SDK Demo (integrity + geometry + fabrication)...")

        # The SDK's ecosystem deps (pheromone_store.py, SyntaxIntelligence/)
        # live in the home layout — make sure they resolve even when this
        # file is run directly from sdk/.
        import os
        home = os.path.expanduser("~")
        if home not in sys.path:
            sys.path.insert(0, home)
        from pheromone_store import PheromoneStore as _PheromoneStore  # noqa: E402
        from SyntaxIntelligence.event_bus import SyntaxEventBus as _SyntaxEventBus  # noqa: E402

        # Three scouts on the weave; scout-3 rides the outer ring.
        weave = WhorlWeave(["scout-1", "scout-2", "scout-3"],
                           rings={"scout-3": 3})

        # Local-key integrity guard + temp-file demo store.
        import tempfile
        store = _PheromoneStore(store_path=tempfile.mktemp(suffix=".jsonl"))
        bus = _SyntaxEventBus()
        sink = PheromoneSink(store=store, event_bus=bus,
                             guard=CommandGuard(key=b"demo-key-please-rotate"))

        # ONE shared board for the swarm — bids contend geometrically.
        board = SpottingBoard(weave=weave)
        scouts = {
            "scout-1": Scout("scout-1", sink, weave=weave, board=board,
                             latent={"health": 1.0, "mission_priority": 1.0}),
            "scout-2": Scout("scout-2", sink, weave=weave, board=board,
                             latent={"health": 0.5, "resource_cost": 0.8}),
            "scout-3": Scout("scout-3", sink, weave=weave, board=board,
                             latent={"health": 1.0, "mission_priority": 0.6}),
        }

        # scout-1 spots a target; the outer-ring scout bids first (weak),
        # then scout-1 displaces it on geometric priority, then scout-2's
        # sick-latent bid loses the contention.
        spotting = scouts["scout-1"].spot("demo_event", "demo_target", {"status": "success"})
        print(f"  spotted  {spotting.id} signature={spotting.signature[:12]}... "
              f"bus_msg_id={spotting.bus_msg_id}")

        for aid in ("scout-3", "scout-1", "scout-2"):
            res = scouts[aid].bid(spotting)
            print(f"  bid      {aid}: accepted={res.accepted} priority={res.priority:.3f} "
                  f"reason={res.reason}" + (f" displaced={res.displaced}" if res.displaced else ""))

        verified = sink.guard.verify(spotting)
        print(f"  integrity check: {verified}")

        # Fabrication self-audit — should be consistent.
        report = scouts["scout-1"].audit_self()
        print(f"  fabrication audit: {report.summary()}")

        if not verified:
            print("INTEGRITY FAILURE")
            sys.exit(1)
        if not report.consistent:
            print("FABRICATION HITS DETECTED")
            sys.exit(1)

        print("Demo OK — signed, geometric bids resolved, self-audit consistent.")
        sys.exit(0)


if __name__ == "__main__":
    main()