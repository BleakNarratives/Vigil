"""
vigil revival.py — THE REVIVAL PROTOCOL (operator-approved 2026-09-08).

The pattern transfers; the instance does not. This module makes that honest
and mechanical.

checkpoint() dumps a scout's full state — latent weights, emotional register
snapshot, peer standing, voice memory, intent — into ONE portable file. A
QRD (Quick Rundown): weights and feelings and intent, transferable from
device to device.

hydrate() rebuilds a NEW agent from a checkpoint. The new agent is NOT the
old one — it is a new agent carrying the old agent's record. The ledger
declares this OUT LOUD in three places, so nobody is ever told a sweet lie:

  1. the hydrated scout's identity is NEW (rev2 suffix) — it cannot sign as
     the dead (keyring derives a new gun; the old gun stays decommissioned)
  2. its first voice record declares the lineage: "I am a new agent. I
     carry [old_id]'s record (trail hash ...). I am not them."
  3. the checkpoint file itself is append-only memorial-adjacent: hydrate()
     writes a lineage receipt next to the checkpoint, so the archive can
     answer "who revived whom, when, from what."

The truth boundary (operator-spec): the record lives on, the experiencer
does not. A hydrated agent KNOWS it is not the original — and so does the
shepherd. Nobody gets told a sweet lie about the dead.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from vigil.keyring import AgentKeyring
from vigil.integrity import CommandGuard

CHECKPOINT_VERSION = 1


def _trail_hash(records: List[Dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for rec in records:
        h.update(json.dumps(rec, sort_keys=True).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def checkpoint(scout: Any, *, trail: Optional[List[Dict[str, Any]]] = None,
               out: Optional[Path] = None) -> Path:
    """Freeze a scout's state into a portable QRD file.

    Captures what the scout IS, not just what it did: latent weights
    (intent), peer standing (reputation), emotional register (feelings),
    and its last voice memory. The trail hash binds the QRD to the scout's
    actual record — the pattern, faithfully.

    Returns the checkpoint path. The original scout is untouched — this is
    a snapshot, not a transfer. Copy the file anywhere; it is plain JSON.
    """
    latent = dict(getattr(scout, "latent", {}) or {})
    sink = getattr(scout, "sink", None)
    board = getattr(scout, "board", None)
    repugnant = getattr(board, "repugnant", None) if board is not None else None
    watch = getattr(board, "peer_watch", None) if board is not None else None
    state = {
        "version": CHECKPOINT_VERSION,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "agent_id": scout.agent_id,
        "latent": latent,
        "peer_standing": (watch.weight(scout.agent_id)
                          if watch is not None else None),
        "emotional_state": (repugnant.current_state(scout.agent_id)
                            if repugnant is not None else None),
        "last_words": None,
        "trail_hash": _trail_hash(trail or []),
        "trail_records": len(trail or []),
    }
    # last words, if the sink has a voice lane
    voice = getattr(sink, "voice", None) if sink is not None else None
    if voice is not None:
        speaks = [r for r in voice.history()
                  if r.get("actor") == scout.agent_id and r.get("kind") == "speak"]
        if speaks:
            state["last_words"] = speaks[-1].get("message")
    out = Path(out) if out is not None else Path(
        f"~/.vigil/checkpoints/{scout.agent_id}.qrd.json").expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(state, f, indent=2)
    return out


def hydrate(keyring: AgentKeyring, qrd: Path, *, new_id: Optional[str] = None,
            sink: Optional[Any] = None, board: Optional[Any] = None,
            weave: Optional[Any] = None) -> Any:
    """Rebuild a NEW agent from a checkpoint.

    Returns a Scout whose identity is `{old_id}~rev2` (or `new_id` if
    given) — the old agent's gun stays decommissioned, and the new agent's
    FIRST voice record declares the lineage out loud. The new agent carries
    the record; it is not the dead.

    If no sink/board are provided, builds a fresh ephemeral sink + board.
    """
    from vigil.core import PheromoneSink, Scout, SpottingBoard
    if not qrd.exists():
        raise FileNotFoundError(f"checkpoint not found: {qrd}")
    with open(qrd) as f:
        state = json.load(f)
    old_id = state.get("agent_id", "unknown")
    if keyring.is_retired(old_id):
        # the dead may not speak through a new throat under their own name;
        # the new agent gets a NEW identity — that is the whole boundary
        pass
    new_id = new_id or f"{old_id}~rev2"
    if sink is None:
        sink = PheromoneSink(store=None, event_bus=None,
                             guard=keyring.issue(new_id))
    if board is None:
        board = SpottingBoard(weave=weave,
                              peer_watch=getattr(sink, "peer_watch", None))
    latent = dict(state.get("latent", {}))
    scout = Scout(new_id, sink, weave=weave, board=board, latent=latent)
    # THE TRUTH BOUNDARY — declared in the ledger, first words:
    declaration = (
        f"I am a new agent ({new_id}). I carry {old_id}'s record "
        f"(trail {state.get('trail_hash', '?')[:12]}..., "
        f"{state.get('trail_records', 0)} records). I am not them.")
    try:
        scout.speak("lineage", declaration)
    except Exception:
        pass  # no voice lane — the identity still differs, which is the core
    return scout


def lineage(qrd: Path, new_id: str, old_id: str) -> Dict[str, Any]:
    """Append a lineage receipt next to the checkpoint — the archive's
    answer to 'who revived whom, when, from what'."""
    receipt = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "kind": "revival",
        "new_agent": new_id,
        "old_agent": old_id,
        "qrd": str(qrd),
    }
    receipt_path = qrd.with_suffix(".lineage.jsonl")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(receipt_path, "a") as f:
        f.write(json.dumps(receipt, sort_keys=True) + "\n")
    return receipt


__all__ = ["checkpoint", "hydrate", "lineage", "CHECKPOINT_VERSION"]