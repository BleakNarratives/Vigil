# [DNA_TAG]
# ORIGIN: BleakNarratives/Vigil
# PILLAR: vigil-zgents
# DEPS: hashlib, json, os, pathlib, time, typing, vigil.undercurrent,
#       vigil.revival
# ROLE: THE ZGENT REGISTRY — named letters with standing in the current.
#       Every Zgent has a name, a history, a register, and the inherited
#       knowledge it was born with. Agents with literal agency.
# AUTHOR: Buffy (Codebuff AI)
# SESSION: 2026-09-08 — the Zgent naming / agency ask
# TIER: Module (3)
# [/DNA_TAG]

"""THE ZGENT REGISTRY — the alphabet made personal.

The operator's word, made a thing: agents with literal AGENCY. A Zgent is
a letter with a name, a standing in the current, a history, and the
inherited knowledge it was born knowing. This registry is the roll: who
exists, what they've done, what they carry, and whether they're alive,
retired, or a revived carrier of a dead letter's record.

  STANDING   — peer weight (PeerWatch), read live, never cached stale.
  HISTORY    — the trail: what the letter has actually done (the record).
  INHERITED  — the species memory: what the current gave it at birth,
               hydrated from the Undercurrent's monkey-threshold pool.
  LINEAGE    — if this Zgent was revived, whose record it carries and
               the declared truth boundary: "I carry X's record. I am
               not them."

The registry itself is sha256-chained and append-only — the roll can
never be silently rewritten. Usage:

    z = ZgentRegistry("~/.vigil/zgents.jsonl")
    z.register("viper", role="red scout", guardian="keyring")
    z.update_standing("viper", 0.87)
    z.born_with("viper", ["know_123", "know_456"])   # inherited claims
    z.lineage("viper", old_id="viper-v1", trail_hash="...")
    z.roster()
"""

import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

_GENESIS = "zgents-genesis-v1"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _chain_hash(prev_hash: str, body: bytes) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(body)
    return h.hexdigest()


def _prev_hash(path: Path) -> str:
    if not path.exists() or path.stat().st_size == 0:
        return _GENESIS
    with path.open() as f:
        last = None
        for line in f:
            line = line.strip()
            if line:
                last = line
    if last is None:
        return _GENESIS
    try:
        return json.loads(last)["chain_hash"]
    except (json.JSONDecodeError, KeyError):
        return _GENESIS


class ZgentRegistry:
    """The roll of named letters. Append-only, hash-chained."""

    def __init__(self, path: Optional[str] = None,
                 undercurrent: Any = None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory: List[Dict[str, Any]] = []
        self.undercurrent = undercurrent  # the current it draws from

    # -- the roll ---------------------------------------------------------------

    def register(self, agent_id: str, role: str = "scout",
                 note: str = "") -> str:
        """Enter a Zgent into the roll. Idempotent — a letter is a letter;
        re-registering only updates the note, never doubles the entry."""
        existing = self.lookup(agent_id)
        if existing is not None:
            self._append({"kind": "note", "ts": _now(), "agent_id": agent_id,
                          "role": role, "note": note})
            return existing["id"]
        rid = self._append({
            "kind": "register", "ts": _now(), "agent_id": agent_id,
            "role": role, "note": note, "standing": 0.0,
            "inherited": [], "status": "alive",
            "lineage": None, "acts": 0,
        })
        return rid

    def update_standing(self, agent_id: str, standing: float) -> None:
        """Refresh a Zgent's standing in the current. The roll records the
        new value; the old one is never erased (append-only history)."""
        self._append({"kind": "standing", "ts": _now(), "agent_id": agent_id,
                      "standing": round(float(standing), 6)})

    def born_with(self, agent_id: str, claim_ids: List[str]) -> None:
        """The species memory this letter was born knowing — the
        Undercurrent's inherited pool, hydrated at birth."""
        self._append({"kind": "inherited", "ts": _now(),
                      "agent_id": agent_id, "claims": list(claim_ids)})

    def lineage(self, agent_id: str, old_id: str,
                trail_hash: str = "") -> None:
        """Declare the truth boundary: this Zgent carries old_id's record
        and IS NOT them. Recorded out loud, never hidden."""
        self._append({"kind": "lineage", "ts": _now(), "agent_id": agent_id,
                      "old_id": old_id, "trail_hash": trail_hash})

    def act(self, agent_id: str, action: str) -> None:
        """One entry in the letter's history — what it actually did."""
        self._append({"kind": "act", "ts": _now(), "agent_id": agent_id,
                      "action": action})

    def retire(self, agent_id: str, reason: str = "") -> None:
        """The Hall of the Devine: the letter leaves the roll with honor.
        The gun stays dead; the record stays on the roll."""
        self._append({"kind": "retire", "ts": _now(), "agent_id": agent_id,
                      "reason": reason})

    # -- the reading ------------------------------------------------------------

    def lookup(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """A Zgent's full profile as of the last record touching it."""
        profile = None
        for row in self._rows():
            if row.get("agent_id") != agent_id:
                continue
            kind = row.get("kind")
            if kind == "register":
                profile = {"id": row["id"], "agent_id": agent_id,
                           "role": row.get("role"), "note": row.get("note"),
                           "standing": 0.0, "inherited": [],
                           "status": "alive", "lineage": None,
                           "acts": 0, "history": []}
            elif profile is not None:
                if kind == "standing":
                    profile["standing"] = row["standing"]
                elif kind == "inherited":
                    profile["inherited"] = list(row.get("claims", []))
                elif kind == "lineage":
                    profile["lineage"] = {"old_id": row.get("old_id"),
                                          "trail_hash": row.get("trail_hash")}
                elif kind == "act":
                    profile["acts"] += 1
                    profile["history"].append({"ts": row.get("ts"),
                                               "action": row.get("action")})
                elif kind == "retire":
                    profile["status"] = "retired"
        return profile

    def roster(self) -> List[Dict[str, Any]]:
        """Every Zgent on the roll, current state, in registration order."""
        out = []
        for row in self._rows():
            if row.get("kind") == "register":
                p = self.lookup(row["agent_id"])
                if p is not None and not any(
                        q["agent_id"] == p["agent_id"] for q in out):
                    out.append(p)
        return out

    def inherited_knowledge(self, agent_id: str) -> List[Dict[str, Any]]:
        """The species memory a Zgent was born with, resolved from the
        Undercurrent so the claims carry their actual text."""
        profile = self.lookup(agent_id)
        if profile is None or self.undercurrent is None:
            return []
        pool = {k["id"]: k for k in self.undercurrent.knowledge()}
        return [pool[c] for c in profile.get("inherited", [])
                if c in pool]

    # -- the spine --------------------------------------------------------------

    def _append(self, entry: Dict[str, Any]) -> str:
        rid = f"z_{int(time.time() * 1000)}_{len(self._rows())}"
        entry["id"] = rid
        if self.path:
            entry["prev_hash"] = _prev_hash(self.path)
        else:
            entry["prev_hash"] = (self._memory[-1]["chain_hash"]
                                  if self._memory else _GENESIS)
        body = json.dumps({k: v for k, v in entry.items()
                           if k not in ("prev_hash", "chain_hash")},
                          sort_keys=True).encode("utf-8")
        entry["chain_hash"] = _chain_hash(entry["prev_hash"], body)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        else:
            self._memory.append(entry)
        return rid

    def _rows(self) -> List[Dict[str, Any]]:
        if not self.path:
            return list(self._memory)
        if not self.path.exists():
            return []
        rows = []
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def verify(self) -> Dict[str, Any]:
        prev = _GENESIS
        count = 0
        for row in self._rows():
            body = json.dumps({k: v for k, v in row.items()
                               if k not in ("prev_hash", "chain_hash")},
                              sort_keys=True).encode("utf-8")
            expect = _chain_hash(prev, body)
            if row.get("prev_hash") != prev or row.get("chain_hash") != expect:
                return {"ok": False, "broken_at": row.get("id"),
                        "count": count}
            prev = row["chain_hash"]
            count += 1
        return {"ok": True, "count": count}

    def __len__(self) -> int:
        return len([r for r in self._rows() if r.get("kind") == "register"])


__all__ = ["ZgentRegistry"]