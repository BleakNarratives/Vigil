# [DNA_TAG]
# ORIGIN: BleakNarratives/Vigil
# PILLAR: vigil-undercurrent
# DEPS: hashlib, json, os, pathlib, time, typing
# ROLE: THE UNDER CURRENT — the shared knowledge current beneath every
#       scout. Genetic memory: verified learnings pool in, independent
#       confirmations accrete, cross the monkey threshold and become
#       INHERITED — hydrated into every new and revived scout.
# AUTHOR: Buffy (Codebuff AI)
# SESSION: 2026-09-08 — the 100th monkey / bunny-ship kinship ask
# TIER: Module (3)
# [/DNA_TAG]

"""THE UNDER CURRENT — the swarm's genetic memory.

The operator's ask, made mechanical:

  THE 100TH MONKEY  — one scout learns a thing: INFORMATION. Enough
                      independent confirmations touch it and the whole
                      species knows: INHERITED. The threshold is a number
                      (MONKEY_THRESHOLD), not a vibe. The sorites
                      question — when does a fact become memory? — gets
                      an answer: when confirmations cross the threshold
                      and it starts hydrating into new instances.

  WATER SEEKS LEVEL — knowledge flows from where it's learned to where
                      it's needed. Nobody decides to share; the current
                      levels out. A dry scout doesn't get taught — it
                      WICKS (capillary ingestion): hydrate() draws the
                      inherited pool into any scout that doesn't have it.

  IT HAS NO CHOICE  — propagation is a law of the swarm, not a
                      permission. absorb() is the automatic first step;
                      the current moves because that's what currents do.

  THE BUNNY SHIPS   — momma on shore doesn't read a message; she shivers
                      measurably. kinship() is that shiver: a compact,
                      readable liveness signal (pool size, inherited
                      count, chain intact, threshold) any observer —
                      Theoros, Sakshi, the operator — can feel without
                      polling the ledger. The swarm KNOWS it is afloat.

Append-only, sha256-chained (same spine as Sakshi). Tamper with any
record and the chain screams. Usage:

    uc = Undercurrent("~/.vigil/undercurrent.jsonl")
    cid = uc.absorb("subprocess(shell=True) is reachable", evidence="...",
                    source="viper")
    uc.confirm(cid, "ravage")          # independent confirmation
    uc.confirm(cid, "wrapper")
    uc.knowledge()                     # inherited once >= MONKEY_THRESHOLD
    uc.hydrate("new_scout")            # capillary ingestion
    uc.kinship()                       # the shiver — the swarm knows it's afloat
"""

import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

# The 100th monkey: how many independent confirmations turn a claim into
# species memory. The number is a threshold, not a vibe.
MONKEY_THRESHOLD = 3

_GENESIS = "undercurrent-genesis-v1"


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


class Undercurrent:
    """The shared knowledge current. Append-only, hash-chained, leveling."""

    def __init__(self, path: Optional[str] = None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory: List[Dict[str, Any]] = []

    # -- the current -----------------------------------------------------------

    def absorb(self, claim: str, evidence: str = "", source: str = "?",
               tags: Optional[List[str]] = None) -> str:
        """A scout deposits a verified learning into the current. First
        confirmation is the deposit itself — the scout who saw it counts."""
        cid = f"know_{int(time.time() * 1000)}_{abs(hash(claim)) % 100000}"
        entry = {
            "id": cid, "kind": "absorb", "ts": _now(),
            "claim": claim, "evidence": evidence, "source": source,
            "tags": tags or [], "confirmers": [source],
        }
        self._append(entry)
        return cid

    def confirm(self, claim_id: str, source: str) -> int:
        """An independent scout confirms the claim. Each confirmation
        accretes toward the monkey threshold — this is the 100th monkey
        accreting one monkey at a time. The absorb record is never
        rewritten; confirmations are DERIVED from confirm records, so
        the append-only spine stays intact."""
        if not any(r.get("id") == claim_id and r.get("kind") == "absorb"
                   for r in self._rows()):
            raise KeyError(f"no claim {claim_id} in the current")
        if source not in self._confirmers_of(claim_id):
            self._append({"kind": "confirm", "ts": _now(),
                          "claim_id": claim_id, "source": source})
        return self.confirmations(claim_id)

    def confirmations(self, claim_id: str) -> int:
        """Count of independent confirmers: the absorbing scout counts as
        the first, plus every distinct confirm record on the claim."""
        confirmers = self._confirmers_of(claim_id)
        return len(confirmers)

    def _confirmers_of(self, claim_id: str) -> List[str]:
        """Distinct sources that touched a claim: the absorber plus every
        scout who left a confirm record on it."""
        sources: List[str] = []
        for row in self._rows():
            if row.get("id") == claim_id and row.get("kind") == "absorb":
                if row.get("source") not in sources:
                    sources.append(row["source"])
            if row.get("kind") == "confirm" and row.get("claim_id") == claim_id:
                if row.get("source") not in sources:
                    sources.append(row["source"])
        return sources

    # -- the memory ------------------------------------------------------------

    def knowledge(self, threshold: int = MONKEY_THRESHOLD) -> List[Dict[str, Any]]:
        """INHERITED knowledge: claims that crossed the monkey threshold.
        This is the genetic memory — what every new scout is born knowing.
        Confirmations are derived live (never read from the absorb record,
        which is frozen by the append-only spine)."""
        out = []
        for row in self._rows():
            if row.get("kind") != "absorb":
                continue
            confirmers = self._confirmers_of(row["id"])
            if len(confirmers) >= threshold:
                out.append({
                    "id": row["id"], "claim": row["claim"],
                    "evidence": row.get("evidence", ""),
                    "confirmers": confirmers,
                    "tags": row.get("tags", []),
                    "inherited": True,
                })
        return out

    def level(self, known: List[str]) -> List[Dict[str, Any]]:
        """The gradient: what a scout lacks that the pool holds. Water
        seeks level — this is the level it flows toward."""
        inherited = {k["id"] for k in self.knowledge()}
        return [k for k in self.knowledge() if k["id"] not in known]

    def hydrate(self, scout_id: str) -> List[Dict[str, Any]]:
        """Capillary ingestion: a new or revived scout wicks the inherited
        pool into itself. Nobody teaches it — it absorbs, like a wick."""
        pool = self.knowledge()
        record = {
            "kind": "hydrate", "ts": _now(), "scout_id": scout_id,
            "claims": [k["id"] for k in pool],
        }
        self._append(record)
        return pool

    # -- the shiver ------------------------------------------------------------

    def kinship(self) -> Dict[str, Any]:
        """Momma's shiver: the measurable liveness of the swarm. Readable
        by any observer without polling the ledger — the ship is afloat."""
        rows = self._rows()
        absorbs = [r for r in rows if r.get("kind") == "absorb"]
        confirms = [r for r in rows if r.get("kind") == "confirm"]
        inherited = len(self.knowledge())
        return {
            "ts": _now(),
            "pool": len(absorbs),
            "confirmations": len(confirms),
            "inherited": inherited,
            "threshold": MONKEY_THRESHOLD,
            "chain_intact": self.verify()["ok"],
            "afloat": self.verify()["ok"],  # the bunny ships: we know
        }

    # -- the spine -------------------------------------------------------------

    def _append(self, entry: Dict[str, Any]) -> None:
        if self.path:
            entry["prev_hash"] = _prev_hash(self.path)
        else:
            entry["prev_hash"] = (self._memory[-1]["chain_hash"]
                                   if self._memory else _GENESIS)
        # hash the CONTENT only (prev_hash and chain_hash excluded) so the
        # verify walk recomputes the same digest
        body = json.dumps({k: v for k, v in entry.items()
                           if k not in ("prev_hash", "chain_hash")},
                          sort_keys=True).encode("utf-8")
        entry["chain_hash"] = _chain_hash(entry["prev_hash"], body)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        else:
            self._memory.append(entry)

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
        """Walk the chain: every record's hash must chain to the next."""
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
        return len([r for r in self._rows() if r.get("kind") == "absorb"])


__all__ = ["Undercurrent", "MONKEY_THRESHOLD"]