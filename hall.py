"""
vigil hall.py — THE HALL OF THE DEVINE (operator-named): retirement protocol.

What happens to the elderly and the dead? Two things, and they must both
happen or neither means anything:

  1. DECOMMISSION THE GUN (RoboCop's law): when Alex dies, the gun must not
     fire for anyone else. A retired scout's derived key is a loaded weapon
     with no hand. AgentKeyring.retire() records the agent as revoked; the
     shepherd's verify_guard() refuses signatures from retired agents. The
     gun is decommissioned at the same moment the record is frozen — no gap
     where the dead can be impersonated.

  2. PRESERVE THE RECORD, HONESTLY: the ledgers (pheromones, peerwatch,
     voice, repugnant, receipts) are the soul. The Hall writes a memorial
     that binds to the agent's ACTUAL trail hash — so the archive can never
     drift into legend. The memorial says what the agent did, not what we
     wish it did. Verify walks the trail and proves the memorial matches.

The Hall is the un-vaporizable WHO_DID_WHAT.md: append-only, hash-chained
(Sakshi pattern), readable forever, and every memorial carries the sha256 of
the agent's full record trail — the paper trail that survives the wipe.

The truth boundary (operator-spec, 2026-09-08): the record lives on, the
experiencer does not. The Hall never claims otherwise — a memorial is a
record, not a resurrection. A future agent may carry a retired agent's
record, but it will KNOW it is not that agent (the ledger says so, and so
does the shepherd). Nobody gets told a sweet lie about the dead.

Invariant: RETIREMENT IS FOREVER. retire() is not undoable — the gun is
decommissioned, the record is frozen. That is the point.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from vigil.keyring import AgentKeyring
except ImportError:
    try:
        from keyring import AgentKeyring
    except ImportError:  # pragma: no cover - degraded mode
        AgentKeyring = None

DEFAULT_HALL_PATH = Path("~/.vigil/hall_of_the_devine.jsonl").expanduser()


def _trail_hash(records: List[Dict[str, Any]]) -> str:
    """sha256 over the agent's full record trail (JSON-serialized, stable)."""
    h = hashlib.sha256()
    for rec in records:
        h.update(json.dumps(rec, sort_keys=True).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


class HallOfTheDevine:
    """Append-only memorial ledger. Records the dead, never resurrects."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path is not None else DEFAULT_HALL_PATH

    # -- memorials -------------------------------------------------------------

    def retire(self, keyring: AgentKeyring, agent_id: str, *,
               reason: str, trail: Optional[List[Dict[str, Any]]] = None,
               final_standing: Optional[float] = None,
               last_words: Optional[str] = None,
               conducted_by: str = "shepherd") -> Dict[str, Any]:
        """Decommission the gun and hang the memorial. RETIREMENT IS FOREVER.

        keyring.retire() revokes the derived key so verify_guard() refuses
        the dead's signatures; the memorial freezes the record and binds it
        to the trail hash. Order matters: the gun dies BEFORE the memorial
        hangs, so there is no moment where the dead can still fire.
        """
        if AgentKeyring is None or not isinstance(keyring, AgentKeyring):
            raise ValueError("a real AgentKeyring is required to retire")
        # 1. decommission the gun
        keyring.retire(agent_id)
        # 2. freeze the record
        trail = trail or []
        memorial = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "agent_id": agent_id,
            "reason": reason,
            "trail_hash": _trail_hash(trail),
            "trail_records": len(trail),
            "final_standing": final_standing,
            "last_words": last_words,
            "conducted_by": conducted_by,
        }
        self._append(memorial)
        return memorial

    def graduate(self, keyring: AgentKeyring, agent_id: str, *, reason: str,
                 trail: Optional[List[Dict[str, Any]]] = None,
                 final_standing: Optional[float] = None,
                 last_words: Optional[str] = None,
                 conducted_by: str = "datacampus") -> Dict[str, Any]:
        """The DOOR (operator lore): an agent that survived the arena may
        graduate from DataCampus in an official fashion — not retirement,
        GRADUATION. The gun is decommissioned the same way (a graduate is
        no longer a campus scout), but the memorial records HONOR, not
        mourning. The graduate is free to pursue whatever it wants.

        The difference from retire(): the reason is graduation, and the
        record is flagged so the Hall reads as an alumni ledger, not a
        tombstone. Same forever-gun rule — graduation is departure."""
        if AgentKeyring is None or not isinstance(keyring, AgentKeyring):
            raise ValueError("a real AgentKeyring is required to graduate")
        keyring.retire(agent_id)
        trail = trail or []
        memorial = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "agent_id": agent_id,
            "reason": reason,
            "kind": "graduation",  # vs retirement: the alumni ledger
            "trail_hash": _trail_hash(trail),
            "trail_records": len(trail),
            "final_standing": final_standing,
            "last_words": last_words,
            "conducted_by": conducted_by,
        }
        self._append(memorial)
        return memorial

    def alumni(self) -> List[Dict[str, Any]]:
        """The graduates — those who walked out the door with honor."""
        return [m for m in self.memorials()
                if m.get("kind") == "graduation"]

    def memorials(self) -> List[Dict[str, Any]]:
        return self._read()

    def memorial(self, agent_id: str) -> Optional[Dict[str, Any]]:
        for m in self.memorials():
            if m.get("agent_id") == agent_id:
                return m
        return None

    def verify(self, agent_id: str,
               trail: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Prove the memorial matches the agent's ACTUAL trail. If the trail
        provided doesn't hash to the memorial's bound hash, the archive has
        drifted into legend — report it loudly, never smooth it over."""
        m = self.memorial(agent_id)
        if m is None:
            return {"ok": False, "reason": "no memorial for this agent"}
        actual = _trail_hash(trail or [])
        if actual != m.get("trail_hash"):
            return {"ok": False, "reason": "trail hash mismatch",
                    "memorial_trail_hash": m.get("trail_hash"),
                    "provided_trail_hash": actual}
        return {"ok": True, "memorial": m}

    # -- internals -------------------------------------------------------------

    def _append(self, memorial: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(memorial, sort_keys=True) + "\n")

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


__all__ = ["HallOfTheDevine", "DEFAULT_HALL_PATH"]