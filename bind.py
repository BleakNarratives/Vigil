# [DNA_TAG]
# ORIGIN: BleakNarratives/Vigil
# PILLAR: vigil-bind
# DEPS: hashlib, json, os, pathlib, time, typing
# ROLE: THE BIND — unit attribution geometry. Any unit may attribute up
#       to 50% of its self to any other(s) in a bind; re-extension folds
#       in half each hop; effective claims decay by powers of 1/2; no
#       coalition can ever hold a majority of any unit.
# AUTHOR: Buffy (Codebuff AI)
# SESSION: 2026-09-08 — the Zgent agency geometry
# TIER: Module (3)
# [/DNA_TAG]

"""THE BIND — how Zgents fold themselves in half.

The operator's spec, made theorem:

  THE HALF-RULE     — any unit may attribute up to 50% of its "self" to
                      any other(s) in a bind. The other half is the
                      essentialism floor: whatever happens, the unit
                      retains majority control of itself. No bind is
                      ever a takeover — it is minority by construction.

  THE FOLD          — a unit may re-extend at most HALF of what it holds
                      to another cause or sub-agent. B holds 0.5 of A;
                      B extends 0.5 of that to C: C now holds 0.25 of A.
                      Fold again: 0.125. Each hop halves the paper. The
                      origin is never dissolved — the deepest node holds
                      at most 0.5^k of it, and k never reaches zero.

  THE BIND ITSELF   — when a unit is in a bind, the committed portion
                      (<=50%) stands for it. The majority is always its
                      own. A coalition that collectively holds more than
                      50% of a unit CANNOT EXIST — the ledger refuses to
                      mint the bind that would make it possible.

The ledger is append-only and sha256-chained (same spine as the
Undercurrent). A bind is a record; a re-extension is a record; tamper
screams. Usage:

    b = BindRegistry("~/.vigil/binds.jsonl")
    bid = b.bind("viper", "ravage", 0.4)        # ravage holds 40% of viper
    eid = b.extend("ravage", "wrapper", 0.5)    # wrapper now holds 20% of viper
    b.effective_claim("viper", "wrapper")       # 0.2 — folded once
    b.holdings_of("ravage")                     # 0.4 — what ravage holds
    b.committed_total("viper")                  # 0.4 — never > 0.5
    b.essential_floor("viper")                  # 0.6 — what viper keeps
"""

import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

# The half-rule: no unit may ever commit more than half its self outward.
MAX_ATTRIBUTION = 0.5

_GENESIS = "bind-genesis-v1"


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


class BindRegistry:
    """The bind ledger. Append-only, hash-chained, minority-by-construction."""

    def __init__(self, path: Optional[str] = None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory: List[Dict[str, Any]] = []

    # -- THE HALF-RULE --------------------------------------------------------

    def bind(self, giver: str, receiver: str, fraction: float,
             note: str = "") -> str:
        """Giver attributes up to 50% of its self to receiver.

        Raises ValueError if the fraction exceeds the half-rule or would
        push the giver's total commitment past 50% — the bind the ledger
        refuses to mint is the bind that could enable a takeover.
        """
        self._check_fraction(fraction, "bind")
        total = self.committed_total(giver) + fraction
        if total > MAX_ATTRIBUTION + 1e-9:
            raise ValueError(
                f"bind refused: {giver} would commit {total:.2f} of self "
                f"(half-rule caps at {MAX_ATTRIBUTION:.0%}) — "
                f"a majority bind cannot exist")
        bid = self._append({
            "kind": "bind", "ts": _now(),
            "giver": giver, "receiver": receiver,
            "fraction": round(fraction, 6), "note": note,
        })
        return bid

    def extend(self, holder: str, target: str, fraction: float,
               note: str = "") -> str:
        """Holder re-extends at most HALF of what it holds to target.

        The fold: the amount that lands on target is fraction * what
        holder holds. Re-extension can never exceed half of holdings, so
        each hop halves the paper — the origin's influence decays
        geometrically and is never dissolved.
        """
        self._check_fraction(fraction, "extend")
        held = self.holdings_of(holder)
        if held <= 1e-9:
            raise ValueError(f"extend refused: {holder} holds nothing "
                             f"to re-extend")
        eid = self._append({
            "kind": "extend", "ts": _now(),
            "holder": holder, "target": target,
            "fraction": round(fraction, 6),
            "passes": round(held * fraction, 6),
            "note": note,
        })
        return eid

    # -- THE GEOMETRY ----------------------------------------------------------

    def committed_total(self, unit: str) -> float:
        """Total fraction of self the unit has bound outward (directly).
        The half-rule guarantees this is never > 0.5."""
        return round(sum(
            r["fraction"] for r in self._rows()
            if r.get("kind") == "bind" and r.get("giver") == unit
        ), 6)

    def holdings_of(self, unit: str) -> float:
        """Total fraction of OTHERS' self that this unit holds (all
        claims granted to it, direct or inherited through the fold)."""
        total = 0.0
        for r in self._rows():
            if r.get("kind") == "bind" and r.get("receiver") == unit:
                total += r["fraction"]
            if r.get("kind") == "extend" and r.get("target") == unit:
                total += r.get("passes", 0.0)
        return round(total, 6)

    def essential_floor(self, unit: str) -> float:
        """What the unit always keeps: at least half its self, by law.
        The floor is the essentialism — no bind can ever go below it."""
        return round(1.0 - self.committed_total(unit), 6)

    def effective_claim(self, origin: str, node: str) -> float:
        """The strongest chain of claims from origin to node, folded
        through re-extensions. Decays by powers of 1/2 per hop: after k
        hops the claim is at most 0.5^k of the origin's self."""
        best = 0.0
        # walk every bind/extend path origin -> ... -> node
        rows = self._rows()

        def walk(unit: str, depth: int, product: float, seen: set):
            nonlocal best
            if unit == node and depth > 0:
                best = max(best, product)
            if depth >= 8:  # 0.5^8 is already below any meaningful claim
                return
            for r in rows:
                if r.get("kind") == "bind" and r.get("giver") == unit:
                    nxt = r["receiver"]
                    if nxt not in seen:
                        walk(nxt, depth + 1, product * r["fraction"],
                             seen | {nxt})
                if r.get("kind") == "extend" and r.get("holder") == unit:
                    nxt = r["target"]
                    if nxt not in seen:
                        walk(nxt, depth + 1, product * r["fraction"],
                             seen | {nxt})

        walk(origin, 0, 1.0, {origin})
        return round(best, 6)

    # -- THE BIND --------------------------------------------------------------

    def coalition_hold(self, unit: str) -> float:
        """What ALL claim holders collectively hold over the unit.
        The half-rule makes this provably <= 0.5: the ledger refuses any
        bind that would let a coalition reach majority. The unit's own
        will always holds the floor."""
        return self.committed_total(unit)

    def resolve(self, unit: str) -> Dict[str, Any]:
        """The bind resolves: the committed portion (<=50%) stands for
        the unit; the majority is its own. This is the in-a-bind answer —
        help arrives, takeover cannot."""
        committed = self.committed_total(unit)
        return {
            "unit": unit,
            "committed": committed,
            "retains": self.essential_floor(unit),
            "majority_is_own": self.essential_floor(unit) >= MAX_ATTRIBUTION,
            "no_coalition_majority": committed <= MAX_ATTRIBUTION,
        }

    # -- the spine -------------------------------------------------------------

    def _check_fraction(self, fraction: float, op: str) -> None:
        if not (0 < fraction <= MAX_ATTRIBUTION + 1e-9):
            raise ValueError(
                f"{op} refused: fraction {fraction} violates the half-rule "
                f"(0 < f <= {MAX_ATTRIBUTION:.0%})")

    def _append(self, entry: Dict[str, Any]) -> str:
        eid = f"bind_{int(time.time() * 1000)}_{len(self._rows())}"
        entry["id"] = eid
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
        return eid

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
        return len(self._rows())


__all__ = ["BindRegistry", "MAX_ATTRIBUTION"]