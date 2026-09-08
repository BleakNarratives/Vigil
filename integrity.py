#!/usr/bin/env python3
"""
spyglass integrity.py — CommandGuard: proof-of-work / integrity layer.

The CommandGuard hashes the command path (the full canonical Spotting) and
signs it with a LOCAL key BEFORE the pheromone is emitted. Anyone can later
verify the pheromone log against tampering or fabrication — a signature that
does not verify means the record was altered after emission, or was never
signed by the owning scout.

Design notes (for agent self-modification):
  * The signature covers everything EXCEPT the signature and bus_msg_id
    fields, so bus correlation metadata can be attached after signing without
    invalidating the record.
  * Key handling is pluggable: pass an explicit `key` (bytes) or a
    `key_path`. The default path is ~/.spyglass/scout_key, created 0600 on
    first use. Swap in asymmetric signing (ed25519) by overriding sign() /
    verify() — call sites never change.
  * Zero dependencies: stdlib hashlib + hmac + json only.

DNA_TAG
ORIGIN: BleakNarratives/sdk
PILLAR: swarm-coordination
DEPS: hashlib,hmac,json,os,pathlib
ROLE: proof-of-work integrity for scout pheromones
AUTHOR: Bleak
SESSION: 2026-09-08
TIER: 2
/DNA_TAG
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Fields excluded from the canonical command path — metadata attached AFTER
# signing must never invalidate the record.
_SIGNATURE_FIELDS = {"signature", "bus_msg_id"}

# Reserved payload key: the sink embeds the exact signed Spotting fields here
# so a store record (type/path/timestamp schema, confidence inside payload)
# verifies against the same canonical string that was signed at emit time.
SPOTTING_EMBED_KEY = "_spotting"

VERSION = "1"

DEFAULT_KEY_DIR = Path("~/.spyglass").expanduser()
DEFAULT_KEY_PATH = DEFAULT_KEY_DIR / "scout_key"


class IntegrityError(Exception):
    """Raised when a signing/verification operation cannot complete."""


def ensure_key(key_path: Optional[Path] = None) -> bytes:
    """Load the local scout key, generating + persisting it (0600) if absent.

    Idempotent and safe to call on every boot. Returns the key bytes.
    """
    path = Path(key_path or DEFAULT_KEY_PATH)
    if path.exists():
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(32)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, key)
    finally:
        os.close(fd)
    return key


def _normalize(spotting: Dict[str, Any]) -> Dict[str, Any]:
    """Map a Spotting dict OR a store record to the canonical field set.

    Store records use type/path/timestamp and bury confidence inside the
    payload; the embedded SPOTTING_EMBED_KEY (written by the sink at emit
    time) carries the exact signed fields, which is what makes log
    verification exact. Signature/bus_msg_id are always excluded.
    """
    payload = dict(spotting.get("payload") or {})
    for key in list(payload):
        if key in _SIGNATURE_FIELDS:
            payload.pop(key, None)

    embed = payload.pop(SPOTTING_EMBED_KEY, None)
    if isinstance(embed, dict):
        inner = dict(embed.get("payload") or {})
        for key in list(inner):
            if key in _SIGNATURE_FIELDS or key == SPOTTING_EMBED_KEY:
                inner.pop(key, None)
        fields = {
            "version": VERSION,
            "id": embed.get("id", ""),
            "ts": embed.get("ts", ""),
            "source": embed.get("source", ""),
            "kind": embed.get("kind", ""),
            "target": embed.get("target", ""),
            "confidence": float(embed.get("confidence", 0.5)),
            "strength": float(embed.get("strength", 1.0)),
            "decay_rate": float(embed.get("decay_rate", 0.0)),
            "payload": inner,
        }
    else:
        # Legacy / un-embedded record (or a plain Spotting dict): translate
        # store keys back and pull confidence out of the payload if needed.
        confidence = spotting.get("confidence")
        if confidence is None:
            confidence = payload.pop("confidence", 0.5)
        strength = spotting.get("strength")
        if strength is None:
            strength = payload.pop("strength", 1.0)
        decay = spotting.get("decay_rate")
        if decay is None:
            decay = payload.pop("decay_rate", 0.0)
        for key in ("confidence", "strength", "decay_rate"):
            payload.pop(key, None)
        fields = {
            "version": VERSION,
            "id": spotting.get("id", ""),
            "ts": spotting.get("ts", spotting.get("timestamp", "")),
            "source": spotting.get("source", ""),
            "kind": spotting.get("kind", spotting.get("type", "")),
            "target": spotting.get("target", spotting.get("path", "")),
            "confidence": float(confidence),
            "strength": float(strength),
            "decay_rate": float(decay),
            "payload": payload,
        }
    return fields


def _canonical_string(spotting: Dict[str, Any]) -> str:
    """Deterministic canonical form of a Spotting (or store record).

    Payload is JSON-serialized with sorted keys; signature/bus_msg_id and the
    embedded Spotting copy are excluded before hashing so correlation metadata
    can be added post-signing without breaking verification.
    """
    return json.dumps(_normalize(spotting), sort_keys=True, separators=(",", ":"))


class CommandGuard:
    """Hashes the command path and signs it with a local key.

    Usage:
        guard = CommandGuard()                       # auto key at ~/.spyglass/scout_key
        guard = CommandGuard(key=b"shared-secret")   # explicit key (tests / fleet)
        guard.sign(spotting)                         # attach signature BEFORE emit
        guard.verify(spotting)                       # True/False

    Everything is HMAC-SHA256; verification uses compare_digest so a forged
    signature cannot be timing-probed.
    """

    def __init__(self, key_path: Optional[Path] = None, key: Optional[bytes] = None):
        if key is not None:
            self.key = bytes(key)
        else:
            self.key = ensure_key(key_path)
        self.key_path = str(key_path or DEFAULT_KEY_PATH)

    # -- command-path hashing -------------------------------------------------

    def hash_command(self, spotting: Any) -> str:
        """sha256 of the canonical command path (target + kind + source + payload).

        Stable across processes: two scouts signing the same spotting produce
        the same command hash, which is what makes cross-checking possible.
        """
        return hashlib.sha256(self.canonical(spotting).encode("utf-8")).hexdigest()

    def canonical(self, spotting: Any) -> str:
        """Canonical string a signature covers. Accepts Spotting or dict."""
        data = spotting.to_dict() if hasattr(spotting, "to_dict") else spotting
        return _canonical_string(data)

    # -- signing / verification ----------------------------------------------

    def sign(self, spotting: Any) -> str:
        """Sign the spotting in place (attaches .signature) and return the hex.

        MUST be called before the pheromone is emitted — this is the
        proof-of-work boundary. Raises IntegrityError if already signed, to
        prevent double-signing drift.
        """
        if getattr(spotting, "signature", "") or (isinstance(spotting, dict) and spotting.get("signature")):
            raise IntegrityError("spotting already signed")
        sig = hmac.new(self.key, self.canonical(spotting).encode("utf-8"),
                       hashlib.sha256).hexdigest()
        if hasattr(spotting, "signature"):
            spotting.signature = sig
        else:
            spotting["signature"] = sig
        return sig

    def verify(self, spotting: Any) -> bool:
        """Verify a Spotting (or dict). Never trusts the signature field
        content — recomputes the MAC from scratch and compares safely."""
        data = spotting.to_dict() if hasattr(spotting, "to_dict") else spotting
        provided = data.get("signature", "") or (data.get("payload") or {}).get("signature", "")
        if not provided:
            return False
        expected = hmac.new(self.key, self.canonical(data).encode("utf-8"),
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, str(provided))

    def verify_log(self, records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Batch-verify stored pheromone records (from PheromoneStore.read_all()).

        Returns {"valid": [...], "invalid": [...], "unsigned": [...]}.
        """
        valid, invalid, unsigned = [], [], []
        for rec in records:
            sig = rec.get("signature") or (rec.get("payload") or {}).get("signature")
            if not sig:
                unsigned.append(rec)
            elif self.verify(rec):
                valid.append(rec)
            else:
                invalid.append(rec)
        return {"valid": valid, "invalid": invalid, "unsigned": unsigned}


__all__ = [
    "CommandGuard", "IntegrityError", "ensure_key",
    "DEFAULT_KEY_PATH", "SPOTTING_EMBED_KEY", "VERSION",
]