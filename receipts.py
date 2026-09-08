#!/usr/bin/env python3
"""
vigil receipts.py — ReceiptLedger: durable bus-correlation receipts.

The SyntaxEventBus message log is IN-MEMORY: restart the process and every
surviving pheromone's bus correlation evaporates, turning honest records
into false fabrication hits. This module gives the sink a DURABLE
append-only receipt ledger mapping spotting_id -> bus_msg_id, so audits
keep working across restarts (H5).

It also enables persist-before-publish (H7): the sink can write the store
record FIRST (with a correlation id), publish second, and record the
receipt third — subscribers never act on a spotting that was never
persisted, and correlation survives.

Design notes (for agent self-modification):
    * The ledger is append-only jsonl; lookup reads the file (audit paths
      are not hot).
    * Memory-only mode (path=None) exists for store-less sinks — honest
      about its own durability: it does NOT survive restart.
    * This module is scout-patchable: swap the backing store (sqlite,
      MCP) by overriding record()/lookup() — the sink and detector only
      use these two methods.

DNA_TAG
ORIGIN: BleakNarratives/sdk
PILLAR: swarm-coordination
DEPS: json,os,time,pathlib
ROLE: durable pheromone<->bus correlation receipts
AUTHOR: Bleak
SESSION: 2026-09-08
TIER: 2
/DNA_TAG
"""
import json
import os
import time
from typing import Any, Dict, Optional


class ReceiptLedger:
    """Append-only spotting_id -> bus_msg_id mapping, durable on disk."""

    def __init__(self, path: Optional[str] = None):
        self.path = path
        self._memory: Dict[str, int] = {}

    @property
    def durable(self) -> bool:
        return self.path is not None

    def record(self, spotting_id: str, bus_msg_id: int) -> None:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "spotting_id": spotting_id,
            "bus_msg_id": bus_msg_id,
        }
        if self.path:
            d = os.path.dirname(self.path)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(self.path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        else:
            self._memory[spotting_id] = bus_msg_id

    def lookup(self, spotting_id: str) -> Optional[int]:
        """Most recent bus_msg_id for a spotting id, or None."""
        if not self.path:
            return self._memory.get(spotting_id)
        if not os.path.exists(self.path):
            return None
        found = None
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("spotting_id") == spotting_id:
                    found = e.get("bus_msg_id")
        return found

    def all_ids(self) -> list:
        """All recorded spotting ids (for ghost cross-checks)."""
        if not self.path:
            return list(self._memory)
        if not os.path.exists(self.path):
            return []
        ids = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("spotting_id"):
                    ids.append(e["spotting_id"])
        return ids


__all__ = ["ReceiptLedger"]