#!/usr/bin/env python3
"""
spyglass_sdk.py — Scout-Spotter SDK.
A substrate for swarm agents to spot, bid, claim, and report.
Zero-dependency core (stdlib only) + optional pheromone/bus integration.
"""
from dataclasses import dataclass, field
import json
import time
import sys
from typing import Dict, Any, List, Optional

# Attempt optional imports
try:
    from pheromone_store import PheromoneStore
except ImportError:
    PheromoneStore = None

try:
    from SyntaxIntelligence.event_bus import SyntaxEventBus
except ImportError:
    SyntaxEventBus = None

@dataclass(slots=True)
class Spotting:
    """Canonical Spotting shape."""
    id: str
    ts: str
    source: str
    kind: str
    target: str
    confidence: float = 0.5
    strength: float = 1.0
    decay_rate: float = 0.0
    payload: Dict[str, Any] = field(default_factory=dict)

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
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

def phm_id(prefix:str="phm") -> str:
    return f"{prefix}_{int(time.time()*1000)}"

class PheromoneSink:
    """Handles reporting spottings to persistence and the event bus."""
    def __init__(self, store: Optional[Any] = None, event_bus: Optional[Any] = None):
        self.store = store if store else (PheromoneStore() if PheromoneStore else None)
        self.event_bus = event_bus

    def report(self, spotting: Spotting):
        # Persistence
        if self.store:
            self.store.emit(
                type_=spotting.kind,
                source=spotting.source,
                path=spotting.target,
                strength=spotting.strength,
                decay_rate=spotting.decay_rate,
                payload={**spotting.payload, "confidence": spotting.confidence}
            )
        
        # Bus propagation
        if self.event_bus:
            self.event_bus.publish(spotting.source, "scout.signals", spotting.to_dict())

class Scout:
    """Navi-like sub-agent helper."""
    def __init__(self, agent_id: str, sink: PheromoneSink):
        self.agent_id = agent_id
        self.sink = sink
    
    def spot(self, kind: str, target: str, payload: Dict[str, Any], 
             confidence: float = 0.5, strength: float = 1.0, decay_rate: float = 0.0) -> Spotting:
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

class SpottingBoard:
    """Bid management: FCFS + self-healing claims."""
    def __init__(self):
        self.claims: Dict[str, float] = {}
    
    def bid(self, spotting: Spotting) -> bool:
        if spotting.target in self.claims:
            return False
        self.claims[spotting.target] = time.time()
        return True

class CommandGuard:
    """Integrity verification layer."""
    @staticmethod
    def verify(spotting: Spotting) -> bool:
        # Placeholder for WaveLang-style integrity hash check
        return bool(spotting.id and spotting.source)

def main():
    if len(sys.argv) < 2:
        print("Usage: spyglass_sdk.py [demo]")
        sys.exit(1)
    
    if sys.argv[1] == "demo":
        print("Running Spyglass SDK Demo...")
        sink = PheromoneSink()
        scout = Scout("demo-agent", sink)
        s = scout.spot("demo_event", "demo_target", {"status": "success"})
        
        board = SpottingBoard()
        if board.bid(s):
            print(f"Bid accepted: {s.target}")
        else:
            print(f"Bid rejected: {s.target}")
        
        verified = CommandGuard.verify(s)
        print(f"Integrity check: {verified}")
        
        if verified:
            sys.exit(0)
        else:
            sys.exit(1)

if __name__ == "__main__":
    main()
