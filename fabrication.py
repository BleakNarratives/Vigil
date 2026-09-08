#!/usr/bin/env python3
"""
vigil fabrication.py — FabricationDetector: pheromone-vs-bus consistency.

Scouts are "honesty-based" until they can prove it. This module gives a scout
(or a shepherd) the ability to cross-check its OWN pheromone log against the
SyntaxEventBus logs and get a verdict:

    * matched          — pheromone claims a bus_msg_id that exists on the bus
    * unmatched        — pheromone claims a bus_msg_id that does NOT exist
                         (fabricated receipt / forged record / dropped write)
    * ghost_bus_events — bus publishes with no pheromone claiming them
                         (signal emitted without a store record — an
                         injection or a skipped persistence write)
    * signature_failures — pheromone signed but the MAC does not verify
                         (tampered after emission)
    * uncorrelated     — pheromone with no bus_msg_id (legacy / unsigned rows;
                         an integrity GAP, reported but not a fabrication hit)

Correlation model: the sink publishes to the bus FIRST, captures the bus
msg_id, and embeds it into the store record's payload as `bus_msg_id`. The
bus log itself stores metadata only ([REDACTED] payload), so msg_id is the
one unforgeable link — and since it's assigned by the bus under lock, a
fabricated receipt cannot invent one without a matching publish.

Design notes (for agent self-modification):
    * `match()` is the seam for a different correlation key (e.g. hash of
      the payload instead of bus_msg_id).
    * `audit()` returns a plain dataclass — safe to serialize into a
      pheromone of its own if a scout wants to report its self-check.

DNA_TAG
ORIGIN: BleakNarratives/sdk
PILLAR: swarm-coordination
DEPS: dataclasses,datetime,typing
ROLE: fabrication detection for scout pheromone logs
AUTHOR: Bleak
SESSION: 2026-09-08
TIER: 2
/DNA_TAG
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Reserved payload key the sink uses to embed the exact signed fields; a
# hardcoded fallback keeps this module importable even if integrity.py is
# missing (degraded mode still cross-checks the flat fields).
try:
    from vigil.integrity import SPOTTING_EMBED_KEY
    SPOTTING_EMBED_KEY = SPOTTING_EMBED_KEY
except ImportError:
    try:
        from integrity import SPOTTING_EMBED_KEY
    except ImportError:
        SPOTTING_EMBED_KEY = "_spotting"

DEFAULT_CHANNEL = "scout.signals"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class FabricationReport:
    """Verdict of one audit pass. Truthy iff consistent (no hits)."""
    audited_at: str = field(default_factory=_now)
    agent_id: Optional[str] = None
    pheromone_count: int = 0
    bus_publish_count: int = 0
    matched: int = 0
    unmatched: List[Dict[str, Any]] = field(default_factory=list)
    ghost_bus_events: List[Dict[str, Any]] = field(default_factory=list)
    signature_failures: List[Dict[str, Any]] = field(default_factory=list)
    field_mismatches: List[Dict[str, Any]] = field(default_factory=list)
    replays: List[Dict[str, Any]] = field(default_factory=list)
    unsigned_claims: List[Dict[str, Any]] = field(default_factory=list)
    uncorrelated: List[Dict[str, Any]] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)

    @property
    def consistent(self) -> bool:
        return not (self.unmatched or self.ghost_bus_events
                    or self.signature_failures or self.field_mismatches
                    or self.replays or self.unsigned_claims)

    def __bool__(self) -> bool:
        return self.consistent

    def summary(self) -> str:
        return (
            f"FabricationAudit agent={self.agent_id} consistent={self.consistent} "
            f"pheromones={self.pheromone_count} bus={self.bus_publish_count} "
            f"matched={self.matched} unmatched={len(self.unmatched)} "
            f"ghosts={len(self.ghost_bus_events)} sig_fail={len(self.signature_failures)} "
            f"field_mismatch={len(self.field_mismatches)} replays={len(self.replays)} "
            f"unsigned_claims={len(self.unsigned_claims)} "
            f"uncorrelated={len(self.uncorrelated)}"
        )


class FabricationDetector:
    """Cross-checks a PheromoneStore against a SyntaxEventBus message log."""

    def __init__(self, store: Any, bus: Any, guard: Optional[Any] = None,
                 agent_id: Optional[str] = None,
                 channel: str = DEFAULT_CHANNEL,
                 receipts: Optional[Any] = None,
                 claim_types: frozenset = frozenset({"TASK_CLAIM"})):
        self.store = store
        self.bus = bus
        self.guard = guard
        self.agent_id = agent_id
        self.channel = channel
        self.receipts = receipts
        self.claim_types = claim_types

    # -- matching seam ---------------------------------------------------------

    def match(self, pheromone: Dict[str, Any],
              publish: Dict[str, Any]) -> bool:
        """True if a store pheromone corresponds to a bus publish record.

        Correlation is resolved via the durable receipt ledger first
        (persist-before-publish sink), falling back to the legacy
        payload.bus_msg_id embed. Override for a different key (applies to
        the legacy path and ghost matching).
        """
        payload = pheromone.get("payload") or {}
        claimed = None
        if self.receipts is not None:
            correlation = payload.get("correlation")
            if correlation:
                claimed = self.receipts.lookup(correlation)
        if claimed is None:
            claimed = payload.get("bus_msg_id")
        return claimed is not None and publish.get("msg_id") == claimed

    # -- audit -----------------------------------------------------------------

    def audit(self, agent_id: Optional[str] = None) -> FabricationReport:
        """Run one consistency pass over store vs bus for `agent_id` (or all)."""
        agent_id = agent_id or self.agent_id
        report = FabricationReport(agent_id=agent_id)

        pheromones = [
            e for e in self.store.read_all()
            if not agent_id or e.get("source") == agent_id
        ]
        # get_message_log(0) returns the FULL log (slice from 0).
        bus_entries = self.bus.get_message_log(0)
        publishes = [
            e for e in bus_entries
            if e.get("type") == "publish"
            and e.get("channel") == self.channel
            and (not agent_id or e.get("agent_id") == agent_id)
        ]
        report.pheromone_count = len(pheromones)
        report.bus_publish_count = len(publishes)

        referenced: set = set()
        seen_ids: set = set()

        for ph in pheromones:
            payload = ph.get("payload") or {}
            sig = payload.get("signature")

            # resolve the claimed bus correlation: the durable receipt ledger
            # is AUTHORITATIVE (H5) — a receipt recorded by the sink at
            # publish time proves the publish happened, even if the in-memory
            # bus log was lost to a restart. Legacy payload.bus_msg_id embed
            # is the fallback for records written before the receipts era.
            correlation = payload.get("correlation")
            receipt_msg_id = None
            if self.receipts is not None and correlation:
                receipt_msg_id = self.receipts.lookup(correlation)

            # replay detection: a store record id may appear only once
            rid = ph.get("id")
            if rid in seen_ids:
                report.replays.append(ph)
                report.issues.append(
                    f"replay: duplicate store record id {rid} ({ph.get('path')})")
            seen_ids.add(rid)

            if sig:
                if self.guard and not self.guard.verify(ph):
                    report.signature_failures.append(ph)
                    report.issues.append(
                        f"signature failure: {ph.get('id')} ({ph.get('path')})")
            else:
                # claims decide who does what — an unsigned claim is a HIT
                # (H3), anything else unsigned is an integrity gap only
                if ph.get("type") in self.claim_types:
                    report.unsigned_claims.append(ph)
                    report.issues.append(
                        f"unsigned claim: {ph.get('id')} type={ph.get('type')} "
                        f"({ph.get('path')})")
                else:
                    report.uncorrelated.append(ph)

            # sign-what's-read: the signed embed and the flat store fields
            # consumers actually read must agree (H2: path spoofing)
            embed = payload.get(SPOTTING_EMBED_KEY)
            if isinstance(embed, dict):
                pairs = [
                    ("path", "target"), ("type", "kind"),
                    ("source", "source"), ("strength", "strength"),
                    ("decay_rate", "decay_rate"),
                ]
                for flat_key, embed_key in pairs:
                    flat_val, embed_val = ph.get(flat_key), embed.get(embed_key)
                    if flat_val != embed_val:
                        report.field_mismatches.append({"id": ph.get("id"),
                                                        "field": flat_key,
                                                        "flat": flat_val,
                                                        "signed": embed_val})
                        report.issues.append(
                            f"field mismatch: {ph.get('id')} flat {flat_key}="
                            f"{flat_val!r} vs signed {embed_key}={embed_val!r}")
                        break

            if receipt_msg_id is not None:
                referenced.add(receipt_msg_id)
                report.matched += 1
                continue

            claimed = payload.get("bus_msg_id")
            if claimed is None:
                report.issues.append(
                    f"uncorrelated pheromone (no bus correlation): {ph.get('id')} "
                    f"({ph.get('path')})")
                continue

            if any(self.match(ph, pub) for pub in publishes):
                referenced.add(claimed)
                report.matched += 1
            else:
                report.unmatched.append(ph)
                report.issues.append(
                    f"unmatched pheromone: {ph.get('id')} claims bus msg_id {claimed} "
                    f"({ph.get('path')})")

        for pub in publishes:
            if pub.get("msg_id") not in referenced:
                report.ghost_bus_events.append(pub)
                report.issues.append(
                    f"ghost bus publish: msg_id {pub.get('msg_id')} on {self.channel} "
                    f"from {pub.get('agent_id')} has no store record")

        return report


__all__ = ["FabricationDetector", "FabricationReport", "DEFAULT_CHANNEL"]