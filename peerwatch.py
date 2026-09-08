#!/usr/bin/env python3
"""
spyglass peerwatch.py — PeerWatch: scouts rat on each other (H4).

A lying scout declares confidence=1.0 and strength=1.0 and outbids the
swarm — unless the swarm is watching. PeerWatch lets scouts flag or vouch
for another scout's declared values. Correct flags earn reputation;
the bid priority of a flagged scout is discounted by peer weight:

    weight(agent) = clamp((vouches + 1) / (flags + 1), 0.25, 1.25)

"Quietly, but not too quiet": flag/vouch records are append-only, signed
by the flagger, and visible to the shepherd. Nothing is broadcast loudly
at bid time — the ledger IS the incentive: the shepherd audits who ratted
on whom, correct flags build a scout's standing, false flags erode it.

This is the H4 peer-accountability layer: bids are no longer a function
of self-declared values alone.

DNA_TAG
ORIGIN: BleakNarratives/sdk
PILLAR: swarm-coordination
DEPS: json,time,typing,sdk.integrity
ROLE: peer flag/vouch reputation for bid weighting
AUTHOR: Bleak
SESSION: 2026-09-08
TIER: 2
/DNA_TAG
"""
import json
import os
import time
from typing import Any, Dict, List, Optional

try:
    from sdk.integrity import CommandGuard
except ImportError:
    try:
        from integrity import CommandGuard
    except ImportError:  # pragma: no cover - degraded mode
        CommandGuard = None

WEIGHT_MIN = 0.25
WEIGHT_MAX = 1.25


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class PeerWatch:
    """Append-only flag/vouch ledger with reputation weighting.

    Usage:
        watch = PeerWatch(path="peerwatch.jsonl", guard=scout_guard)
        watch.flag("scout-2", "scout-1", "phm_123", "declared strength is fantasy")
        weight = watch.weight("scout-1")      # < 1.0 after flags
        board = SpottingBoard(weave=weave, peer_watch=watch)
    """

    def __init__(self, path: Optional[str] = None, guard: Optional[Any] = None):
        self.path = path
        self.guard = guard  # flagger signs its own records when provided
        self._memory: List[Dict[str, Any]] = []

    # -- ledger ----------------------------------------------------------------

    def flag(self, flagger: str, target_agent: str, spotting_id: str,
             reason: str) -> Dict[str, Any]:
        """Publicly (to the shepherd) dispute a scout's declared values."""
        return self._append("flag", flagger, target_agent, spotting_id,
                            detail=reason)

    def vouch(self, voucher: str, target_agent: str, spotting_id: str,
              note: str = "") -> Dict[str, Any]:
        """Attest that a scout's declared values are credible."""
        return self._append("vouch", voucher, target_agent, spotting_id,
                            detail=note)

    def _append(self, kind: str, actor: str, target_agent: str,
                spotting_id: str, detail: str) -> Dict[str, Any]:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "kind": kind,
            "actor": actor,
            "target_agent": target_agent,
            "spotting_id": spotting_id,
            "detail": detail,
        }
        if self.guard is not None and hasattr(self.guard, "sign"):
            self.guard.sign(record)  # flagger signs its own record
        if self.path:
            d = os.path.dirname(self.path)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(self.path, "a") as f:
                f.write(json.dumps(record) + "\n")
        else:
            self._memory.append(record)
        return record

    # -- reads -----------------------------------------------------------------

    def history(self, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """All records, optionally filtered to one target agent. Shepherd's
        view — 'not too quiet': the ledger is auditable, not broadcast."""
        records = self._memory + self._read_file()
        if agent_id is not None:
            return [r for r in records if r.get("target_agent") == agent_id]
        return records

    def _read_file(self) -> List[Dict[str, Any]]:
        if not self.path or not os.path.exists(self.path):
            return []
        out = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def weight(self, agent_id: str) -> float:
        """Bid-priority multiplier from peer standing. Flags discount,
        vouches amplify — clamped to [WEIGHT_MIN, WEIGHT_MAX]."""
        records = self.history(agent_id)
        flags = sum(1 for r in records if r.get("kind") == "flag")
        vouches = sum(1 for r in records if r.get("kind") == "vouch")
        return _clamp((vouches + 1.0) / (flags + 1.0), WEIGHT_MIN, WEIGHT_MAX)

    def verify_record(self, record: Dict[str, Any]) -> bool:
        """True if a record carries a signature that verifies against the
        watch's guard (when one is configured)."""
        if self.guard is None or not record.get("signature"):
            return False
        try:
            return self.guard.verify(record)
        except Exception:
            return False


__all__ = ["PeerWatch", "WEIGHT_MIN", "WEIGHT_MAX"]