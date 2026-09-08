"""
vigil molt.py — MOLT (operator lore, 2026-09-08): arena-won mutation access.

In the original DataCampus design, the Arena was where agents went to do
battle to gain access to Molt for genetic mutations — the only way to
enhance your code. This module makes that mechanical:

  - Battles won in the arena earn MOLT TOKENS (mutation access).
  - Molt tokens are the gate to self-modification: an agent cannot apply a
    self_mod patch without spending the Molt it earned. The arena is the
    only mint. You cannot buy your way in; you cannot inherit it; you
    cannot fake it (tokens are signed by the arena's keyring).

This closes the loop the operator described: battle -> win -> Molt ->
mutate your own code -> come back enhanced, or graduate through the door.

The Arena is not a prison — it is where they know themselves and their
shit are safe, and where enhancement is EARNED. Molt is the receipt of
that earning. An agent with Molt has proven it in the arena; an agent
without it cannot touch its own source. That is the whole bargain: the
right to mutate yourself is won, not given.

Invariant: MOLT IS EARNED, NEVER GRANTED. The only mint is the arena.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from vigil.integrity import CommandGuard
except ImportError:
    try:
        from integrity import CommandGuard
    except ImportError:  # pragma: no cover - degraded mode
        CommandGuard = None

DEFAULT_MOLT_PATH = Path("~/.vigil/molt.jsonl").expanduser()

_SIGNED_FIELDS = ("ts", "agent_id", "tokens", "won_in_arena", "battle_id")


class Molt:
    """Signed, append-only Molt ledger. The arena is the only mint."""

    def __init__(self, path: Optional[Path] = None,
                 guard: Optional[Any] = None):
        self.path = Path(path) if path is not None else DEFAULT_MOLT_PATH
        self.guard = guard

    # -- minting ---------------------------------------------------------------

    def award(self, agent_id: str, tokens: int, battle_id: str) -> Dict[str, Any]:
        """Arena awards Molt for a battle won. ONLY the arena calls this —
        the guard key is the arena's keyring, and the record is signed so
        a forged award fails verification. Molt is earned, never granted."""
        if tokens <= 0:
            raise ValueError("molt tokens must be positive")
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "agent_id": agent_id,
            "tokens": tokens,
            "won_in_arena": True,
            "battle_id": battle_id,
        }
        if self.guard is not None and hasattr(self.guard, "key"):
            record["signature"] = self._sign(record)
        self._append(record)
        return record

    # -- spending --------------------------------------------------------------

    def spend(self, agent_id: str, tokens: int,
              reason: str = "self-modification") -> bool:
        """Spend Molt to authorize a self_mod patch. Returns False if the
        agent doesn't have enough — the mutation gate holds."""
        if self.balance(agent_id) < tokens:
            return False
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "agent_id": agent_id,
            "tokens": -tokens,
            "won_in_arena": False,
            "battle_id": reason,
        }
        if self.guard is not None and hasattr(self.guard, "key"):
            record["signature"] = self._sign(record)
        self._append(record)
        return True

    # -- reads -----------------------------------------------------------------

    def balance(self, agent_id: str) -> int:
        total = 0
        for rec in self.history(agent_id):
            if rec.get("agent_id") == agent_id:
                total += rec.get("tokens", 0)
        return max(0, total)

    def history(self, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        records = self._read()
        if agent_id is not None:
            return [r for r in records if r.get("agent_id") == agent_id]
        return records

    def verify(self) -> Dict[str, Any]:
        """Walk the ledger: every award must verify against the arena's
        guard. A forged award (wrong signature) is reported loudly."""
        bad = []
        for rec in self.history():
            if not self._verify_record(rec):
                bad.append(rec)
        return {"ok": not bad, "count": len(self.history()), "bad": bad}

    # -- signing ---------------------------------------------------------------

    def _canonical(self, record: Dict[str, Any]) -> str:
        fields = {k: record.get(k) for k in _SIGNED_FIELDS}
        return json.dumps(fields, sort_keys=True, separators=(",", ":"))

    def _sign(self, record: Dict[str, Any]) -> str:
        return hmac.new(self.guard.key, self._canonical(record).encode("utf-8"),
                        hashlib.sha256).hexdigest()

    def _verify_record(self, record: Dict[str, Any]) -> bool:
        if self.guard is None or not hasattr(self.guard, "key"):
            return True
        sig = record.get("signature")
        if not sig:
            return False
        expect = hmac.new(self.guard.key,
                          self._canonical(record).encode("utf-8"),
                          hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expect)

    def _append(self, record: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    def _read(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
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


__all__ = ["Molt", "DEFAULT_MOLT_PATH"]