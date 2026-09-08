#!/usr/bin/env python3
"""
vigil peerwatch.py — PeerWatch: scouts rat on each other (H4).

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
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, List, Optional

try:
    from vigil.integrity import CommandGuard
except ImportError:
    try:
        from integrity import CommandGuard
    except ImportError:  # pragma: no cover - degraded mode
        CommandGuard = None

# Fields a flag/vouch signature MUST cover. CommandGuard's Spotting-canonical
# does NOT cover target_agent/spotting_id/detail, so PeerWatch signs its own
# canonical with the same key (own lock, own key — never a shadow copy).
_SIGNED_FIELDS = ("ts", "kind", "actor", "target_agent", "spotting_id",
                  "detail")

WEIGHT_MIN = 0.25
WEIGHT_MAX = 2.0

# Standing earned per shepherd-CONFIRMED flag — the informant's paycheck.
# The industry pays: a scout whose flag is validated climbs.
CONFIRM_REWARD = 0.5

# Recursion cap for self-referential reputation (A vouches B, B vouches A).
# Depth-limited, deterministic — no fixed-point solver needed.
_WEIGHT_DEPTH = 3


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
        if self.guard is not None and hasattr(self.guard, "key"):
            record["signature"] = self._sign(record)  # flagger signs its own record
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

    def confirm_flag(self, shepherd: str, target_agent: str, spotting_id: str,
                     note: str = "") -> Dict[str, Any]:
        """Shepherd validates an informant's flag: the flag was CORRECT.
        The FLAGGER earns standing (CONFIRM_REWARD) — the ratting market's
        paycheck. Confirmation is itself a signed, append-only record."""
        return self._append("confirm", shepherd, target_agent=target_agent,
                            spotting_id=spotting_id, detail=note)

    def confirmed_flags(self, agent_id: str) -> List[Dict[str, Any]]:
        """The agent's flags that the shepherd has confirmed."""
        all_records = self._memory + self._read_file()
        my_flags = [r for r in all_records
                    if r.get("actor") == agent_id and r.get("kind") == "flag"]
        confirms = {(r.get("target_agent"), r.get("spotting_id"))
                    for r in all_records if r.get("kind") == "confirm"}
        return [f for f in my_flags
                if (f.get("target_agent"), f.get("spotting_id")) in confirms]

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

    def weight(self, agent_id: str, _depth: int = 0) -> float:
        """Bid-priority multiplier from peer standing, RECURSIVELY WEIGHTED:
        every flag/vouch counts according to the ACTOR's own standing. A
        vouch from a dirty scout is worth a dirty vouch; a false flag from
        a dirtbag barely dents its target. Colluding liars vouching each
        other pay with their own collapsed weight — mutual backscratching
        is priced (the prisoner's dilemma, iterated).

        depth-capped so circular vouching (A<->B) stays deterministic.
        """
        if _depth > _WEIGHT_DEPTH:
            return 1.0
        vouch_sum = 0.0
        flag_sum = 0.0
        for rec in self.history(agent_id):
            actor_weight = self.weight(rec.get("actor", ""), _depth + 1)
            if rec.get("kind") == "vouch":
                vouch_sum += actor_weight
            elif rec.get("kind") == "flag":
                flag_sum += actor_weight
        base = (vouch_sum + 1.0) / (flag_sum + 1.0)
        reward = CONFIRM_REWARD * len(self.confirmed_flags(agent_id))
        return _clamp(base + reward, WEIGHT_MIN, WEIGHT_MAX)

    def _canonical(self, record: Dict[str, Any]) -> str:
        fields = {k: record.get(k) for k in _SIGNED_FIELDS}
        return json.dumps(fields, sort_keys=True, separators=(",", ":"))

    def _sign(self, record: Dict[str, Any]) -> str:
        key = getattr(self.guard, "key", None)
        if key is None:
            return ""
        return hmac.new(bytes(key), self._canonical(record).encode("utf-8"),
                        hashlib.sha256).hexdigest()

    def verify_record(self, record: Dict[str, Any]) -> bool:
        """True if a record carries a signature that verifies against the
        watch's guard (when one is configured). Flipping target_agent,
        spotting_id, or detail breaks it."""
        if self.guard is None or not record.get("signature"):
            return False
        expected = hmac.new(bytes(self.guard.key),
                            self._canonical(record).encode("utf-8"),
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, str(record.get("signature")))


__all__ = ["PeerWatch", "WEIGHT_MIN", "WEIGHT_MAX"]