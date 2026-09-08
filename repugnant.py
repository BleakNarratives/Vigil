"""
vigil repugnant.py — REPUGNANT: the emotional register (4th register layer).

Operator history: Repugnant began as a Code-City integration bridge (human
behavior monitor — emotional state inference, taunt effectiveness, adaptive
difficulty). Its vocabulary was the right one; its scope was the arena. This
module grafts that vocabulary onto the swarm as a REGISTER — a signed,
append-only stream of emotional snapshots, read by Theoros alongside
PeerWatch (behavioral) and Knose (bullshit).

The law of the fourth register (operator-spec, 2026-09-08): watch the
powerful, not the street. A lie from a nobody barely dents (PeerWatch's
dirty-flag discount); a lie from a TILTED hero is a liability with weight.
Repugnant watches whoever's IN the arena with standing, and discounts their
bid priority by their emotional state — the register the market already
prices is the one that can hurt it most.

Emotional states (from the original bridge): CONFIDENT, FOCUSED, FRUSTRATED,
TILTED, BURNT_OUT, EXCITED, ANXIOUS, FLOW_STATE. Each snapshot is signed by
the recorder (the shepherd or an observer), append-only, and tagged with the
subject's peer standing at capture time — so a reading can answer: who holds
weight, and what state are they in?

Invariant: REPUGNANT RECORDS, IT DOES NOT ACCUSE. A TILTED reading is a
signal to demand evidence, never a verdict of guilt — same as Knose's CLEAN
!= true, CORRUPT is a signal, not a conviction.
"""

from __future__ import annotations

import json
import os
import time
from enum import Enum
from typing import Any, Dict, List, Optional

try:
    from vigil.integrity import CommandGuard
except ImportError:
    try:
        from integrity import CommandGuard
    except ImportError:  # pragma: no cover - degraded mode
        CommandGuard = None

# Fields a snapshot signature MUST cover — own lock, own key, never a shadow
# copy (the PeerWatch pattern).
_SIGNED_FIELDS = ("ts", "subject", "state", "confidence", "frustration",
                  "observed_by", "note")

# Emotional bid-priority discounts. A scout in a hot state cannot be trusted
# to price its own claims — the market discounts for it. FLOW_STATE and
# CONFIDENT are the only states that cost nothing; everything else pays.
STATE_DISCOUNT = {
    "confident": 1.00,
    "flow_state": 1.00,
    "focused": 0.95,
    "excited": 0.90,
    "anxious": 0.80,
    "frustrated": 0.70,
    "tilted": 0.50,
    "burnt_out": 0.40,
}


class EmotionalState(Enum):
    CONFIDENT = "confident"
    FOCUSED = "focused"
    FRUSTRATED = "frustrated"
    TILTED = "tilted"
    BURNT_OUT = "burnt_out"
    EXCITED = "excited"
    ANXIOUS = "anxious"
    FLOW_STATE = "flow_state"


class Repugnant:
    """Signed, append-only emotional register. Records, never accuses."""

    def __init__(self, path: Optional[str] = None,
                 guard: Optional[Any] = None):
        self.path = path
        self.guard = guard
        self._memory: List[Dict[str, Any]] = []

    # -- ledger ----------------------------------------------------------------

    def observe(self, subject: str, state: str, *,
                confidence: float = 0.5, frustration: float = 0.0,
                observed_by: str = "shepherd", note: str = "") -> Dict[str, Any]:
        """Record one emotional snapshot. Signed when a guard is provided."""
        state = state.lower()
        if state not in STATE_DISCOUNT:
            raise ValueError(f"unknown emotional state: {state!r} "
                             f"(known: {sorted(STATE_DISCOUNT)})")
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "subject": subject,
            "state": state,
            "confidence": max(0.0, min(1.0, confidence)),
            "frustration": max(0.0, min(1.0, frustration)),
            "observed_by": observed_by,
            "note": note,
        }
        if self.guard is not None and hasattr(self.guard, "key"):
            record["signature"] = self._sign(record)
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

    def history(self, subject: Optional[str] = None) -> List[Dict[str, Any]]:
        records = self._memory + self._read_file()
        if subject is not None:
            return [r for r in records if r.get("subject") == subject]
        return records

    def current_state(self, subject: str) -> Optional[Dict[str, Any]]:
        """The subject's most recent snapshot, or None if never observed."""
        mine = self.history(subject)
        return mine[-1] if mine else None

    def state_discount(self, subject: str) -> float:
        """Bid-priority multiplier from the subject's CURRENT emotional
        state. 1.0 (no cost) for never-observed or calm states; down to 0.4
        for burnt_out. The register prices the risk the market can't see."""
        snap = self.current_state(subject)
        if snap is None:
            return 1.0
        return STATE_DISCOUNT.get(snap.get("state", "focused"), 1.0)

    def unsettled(self, threshold: float = 0.60) -> List[Dict[str, Any]]:
        """Subjects currently in a state below `threshold` discount — the
        ones Theoros should flag as 'demand evidence, don't convict'."""
        subjects = {r.get("subject") for r in self.history()}
        out = []
        for s in subjects:
            d = self.state_discount(s)
            if d < threshold:
                snap = self.current_state(s)
                out.append({**snap, "discount": d})
        return sorted(out, key=lambda r: r.get("discount", 1.0))

    # -- signing ---------------------------------------------------------------

    def _canonical(self, record: Dict[str, Any]) -> str:
        fields = {k: record.get(k) for k in _SIGNED_FIELDS}
        return json.dumps(fields, sort_keys=True, separators=(",", ":"))

    def _sign(self, record: Dict[str, Any]) -> str:
        import hashlib
        import hmac
        return hmac.new(self.guard.key, self._canonical(record).encode("utf-8"),
                        hashlib.sha256).hexdigest()

    def verify_record(self, record: Dict[str, Any]) -> bool:
        """Recompute the signature from scratch — never trust the stored one."""
        if self.guard is None or not hasattr(self.guard, "key"):
            return True  # unsigned mode: nothing to verify against
        sig = record.get("signature")
        if not sig:
            return False
        import hashlib
        import hmac
        expect = hmac.new(self.guard.key,
                          self._canonical(record).encode("utf-8"),
                          hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expect)

    def verify(self) -> Dict[str, Any]:
        """Walk the register: every record's signature must verify."""
        bad = [r for r in self.history() if not self.verify_record(r)]
        return {"ok": not bad, "count": len(self.history()), "bad": bad}

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


__all__ = ["Repugnant", "EmotionalState", "STATE_DISCOUNT"]