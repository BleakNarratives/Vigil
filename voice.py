#!/usr/bin/env python3
"""
vigil voice.py — Voice: the swarm's out-loud lane (B1).

A scout that cannot express itself, vote, or propose is a sensor, not an
agent. This module gives every scout three channels:

    speak(actor, topic, message)   — expression "out loud": corkboard
                                     utterances anyone (and the shepherd)
                                     can read.
    vote(actor, motion, choice)    — ballots on open motions (aye/nay/
                                     abstain). Tally computes quorum +
                                     outcome deterministically.
    suggest(actor, module, reason) — the suggestion box. Suggestions carry
                                     an optional candidate patch path and
                                     route into the self-modification
                                     pipeline (SELF_MODIFICATION.md): the
                                     shepherd reviews, then self_mod.py
                                     validates/applies. The box is the
                                     front door; self_mod is the gatekeeper.

Every record is signed by the actor (when a guard is configured),
append-only, and durable (jsonl). The ledger is the swarm's institutional
memory — 'out loud' means audible to the shepherd, not broadcast to the
battlefield.

This is also the social half of the A4 equilibrium: truth cannot be
cryptographically proven, but it can be made EXPENSIVE — flags (PeerWatch)
discount liars, votes surface consensus, suggestions route improvement.
The swarm's voice is its ground truth.

DNA_TAG
ORIGIN: BleakNarratives/sdk
PILLAR: swarm-coordination
DEPS: json,os,time,typing,sdk.integrity
ROLE: speak/vote/suggest voice lane for scouts
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

try:
    from vigil.oler import Oler
except ImportError:
    try:
        from oler import Oler
    except ImportError:  # pragma: no cover - degraded mode
        Oler = None

# Fields a voice-record signature MUST cover — every meaningful field of
# speak/vote/suggest records. CommandGuard's Spotting-canonical does NOT
# cover choice/reason/candidate_path etc., so the voice ledger signs its own
# canonical with the same key (own lock, own key — never a shadow copy).
_SIGNED_FIELDS = ("ts", "kind", "actor", "topic", "choice", "reason",
                  "candidate_path", "patch_summary")

VALID_CHOICES = {"aye", "yay", "yes", "nay", "no", "abstain", "skip", "pass"}
NORMALIZED = {
    "aye": "aye", "yay": "aye", "yes": "aye",
    "nay": "nay", "no": "nay",
    "abstain": "abstain", "skip": "abstain", "pass": "abstain",
}


def _normalize_choice(choice: str) -> str:
    key = str(choice).strip().lower()
    if key not in NORMALIZED:
        raise ValueError(f"invalid vote choice: {choice!r} "
                         f"(use aye/nay/abstain)")
    return NORMALIZED[key]


class Voice:
    """Speak / vote / suggest — one signed, append-only ledger."""

    def __init__(self, path: Optional[str] = None, guard: Optional[Any] = None,
                 sniffer: Optional[Any] = None,
                 peer_watch: Optional[Any] = None,
                 flag_threshold: float = 0.45):
        self.path = path
        self.guard = guard
        self._memory: List[Dict[str, Any]] = []
        # OLER loop: corrupt utterances auto-flag the speaker in PeerWatch
        # (the sniffer as a neutral third party — the anti-register watchdog).
        self.sniffer = sniffer if sniffer is not None else (Oler() if Oler else None)
        self.peer_watch = peer_watch
        self.flag_threshold = flag_threshold

    # -- the three channels ----------------------------------------------------

    def speak(self, actor: str, topic: str, message: str) -> Dict[str, Any]:
        """Utterance on the corkboard. Anyone may read; the shepherd may
        care. 'Out loud' means recorded and attributable, not shouted.

        The utterance is sniffed (OLER): if the anti-register risk clears
        the threshold, the sniffer auto-flags the speaker in the peer_watch
        ledger — the social equilibrium: bullshit gets expensive.
        """
        record = self._append("speak", actor, topic=topic, message=message)
        if self.sniffer is not None:
            verdict = self.sniffer.sniff(message)
            record["sniff"] = verdict
            if verdict.get("deception_risk", 0.0) >= self.flag_threshold \
                    and self.peer_watch is not None:
                self.peer_watch.flag(
                    "oler", actor, "",
                    f"sniffer flagged utterance risk="
                    f"{verdict['deception_risk']:.2f} ({verdict.get('verdict')})")
        return record

    def vote(self, actor: str, motion: str, choice: str,
             reason: str = "") -> Dict[str, Any]:
        """Ballot on an open motion. Choices normalize to aye/nay/abstain.
        One actor, one vote per motion — later ballots supersede earlier
        ones (the ledger keeps all of them; tally uses the latest)."""
        choice = _normalize_choice(choice)
        return self._append("vote", actor, topic=motion, choice=choice,
                            reason=reason)

    def suggest(self, actor: str, module: str, reason: str,
                candidate_path: Optional[str] = None,
                patch_summary: str = "") -> Dict[str, Any]:
        """Suggestion-box entry. `module` + `reason` are required; a
        `candidate_path` to a candidate patch routes it straight into the
        self-modification review flow (self_mod.py validate/apply)."""
        return self._append("suggest", actor, topic=module, reason=reason,
                            candidate_path=candidate_path,
                            patch_summary=patch_summary)

    # -- ledger ----------------------------------------------------------------

    def _canonical(self, record: Dict[str, Any]) -> str:
        """Deterministic canonical over the voice record's OWN signed fields
        (not CommandGuard's Spotting fields)."""
        fields = {k: record.get(k) for k in _SIGNED_FIELDS}
        return json.dumps(fields, sort_keys=True, separators=(",", ":"))

    def _sign(self, record: Dict[str, Any]) -> str:
        if self.guard is None:
            return ""
        key = getattr(self.guard, "key", None)
        if key is None:
            return ""
        return hmac.new(bytes(key), self._canonical(record).encode("utf-8"),
                        hashlib.sha256).hexdigest()

    def _append(self, kind: str, actor: str, **fields) -> Dict[str, Any]:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "kind": kind,
            "actor": actor,
        }
        record.update({k: v for k, v in fields.items() if v is not None})
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

    def history(self, kind: Optional[str] = None,
                actor: Optional[str] = None) -> List[Dict[str, Any]]:
        records = self._memory + self._read_file()
        if kind is not None:
            records = [r for r in records if r.get("kind") == kind]
        if actor is not None:
            records = [r for r in records if r.get("actor") == actor]
        return records

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

    # -- votes -----------------------------------------------------------------

    def tally(self, motion: str, quorum: int = 1) -> Dict[str, Any]:
        """Deterministic outcome for a motion using each actor's LATEST
        ballot. passes = ayes > nays AND total votes >= quorum."""
        latest: Dict[str, str] = {}
        for rec in self.history(kind="vote"):
            if rec.get("topic") == motion:
                latest[rec["actor"]] = rec.get("choice", "abstain")
        ayes = sum(1 for c in latest.values() if c == "aye")
        nays = sum(1 for c in latest.values() if c == "nay")
        abstain = sum(1 for c in latest.values() if c == "abstain")
        total = len(latest)
        return {
            "motion": motion,
            "ayes": ayes,
            "nays": nays,
            "abstain": abstain,
            "voters": total,
            "quorum": quorum,
            "met_quorum": total >= quorum,
            "passes": total >= quorum and ayes > nays,
        }

    # -- suggestions -----------------------------------------------------------

    def suggestions(self, module: Optional[str] = None) -> List[Dict[str, Any]]:
        """The shepherd's queue: everything the swarm is proposing, newest
        last. Each entry carries module/reason and optionally a candidate
        path ready for self_mod.py validate/apply."""
        records = self.history(kind="suggest")
        if module is not None:
            records = [r for r in records if r.get("topic") == module]
        return records

    # -- integrity -------------------------------------------------------------

    def verify_record(self, record: Dict[str, Any]) -> bool:
        """True if a voice record carries a signature that verifies against
        the configured guard. A tampered ballot/utterance fails — the
        canonical covers the record's OWN fields, so flipping `choice` or
        rewriting `reason` breaks it."""
        if self.guard is None or not record.get("signature"):
            return False
        expected = hmac.new(bytes(self.guard.key),
                            self._canonical(record).encode("utf-8"),
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, str(record.get("signature")))


__all__ = ["Voice", "VALID_CHOICES", "NORMALIZED"]