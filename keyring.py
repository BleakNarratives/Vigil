#!/usr/bin/env python3
"""
spyglass keyring.py — AgentKeyring: RoboCop key custody (H1).

RoboCop's gun only fired for Alex Murphy — its DNA, plus a specific charge
from the unit. Same idea here: the swarm's verification key is not one
shared file that any scout can read. The UNIT holds a single secret (the
charge). Agent keys are DERIVED per identity:

    agent_key = sha256(unit_secret | "agent:" | agent_id | [dna])

Nobody can fire the gun but the agent it was issued to — agent A's derived
key is worthless for signing as agent B, and the shepherd can derive ANY
agent's key to verify (the unit knows the charge; the DNA is the identity
the code is born with).

Properties this gives us:
  * No shared key: a compromised scout compromises only ITS OWN signature
    lane, not the swarm's.
  * Revocation = rotate the unit secret (or keep a per-agent denylist in
    the shepherd's audit).
  * DNA binding (optional): pass the agent's module DNA_TAG fingerprint and
    the derivation changes — modify the code, the DNA changes, and the old
    key stops verifying until the unit re-issues. Self-modification and key
    rotation become the same event.

The agent never holds the unit secret — only the derived key (a
CommandGuard). The unit secret should live with the shepherd (concierge
vault), never in the scout's scope.

DNA_TAG
ORIGIN: BleakNarratives/sdk
PILLAR: swarm-coordination
DEPS: hashlib,typing,sdk.integrity
ROLE: per-agent derived-key custody (RoboCop gun)
AUTHOR: Bleak
SESSION: 2026-09-08
TIER: 2
/DNA_TAG
"""
import hashlib
from typing import Optional

try:
    from sdk.integrity import CommandGuard
except ImportError:
    try:
        from integrity import CommandGuard
    except ImportError:  # pragma: no cover - degraded mode
        CommandGuard = None

DNA_NAMESPACE = b"spyglass-agent-key-v1"


def derive_agent_key(unit_secret: bytes, agent_id: str,
                     dna: Optional[str] = None) -> bytes:
    """Deterministic per-agent key. Same inputs -> same key, so the
    shepherd's verify_guard(agent_id) reproduces the agent's signing key.

    unit_secret — the charge: one secret held by the unit/shepherd.
    agent_id    — the DNA: the agent's identity string.
    dna         — optional module DNA_TAG fingerprint: bind the key to the
                  code identity, so mutating the module invalidates the key.
    """
    material = unit_secret + DNA_NAMESPACE + b"|agent:" + agent_id.encode("utf-8")
    if dna:
        material += b"|dna:" + dna.encode("utf-8")
    return hashlib.sha256(material).digest()


def module_dna_fingerprint(module_text: str) -> str:
    """Fingerprint of a module's source — the 'born with' identity. Feed a
    module's DNA_TAG block (or whole source) so the key is bound to that
    code identity; change the code, the fingerprint changes."""
    return hashlib.sha256(module_text.encode("utf-8")).hexdigest()


class AgentKeyring:
    """Custody of the charge. Issue guns, derive verification guards.

    Usage:
        keyring = AgentKeyring(unit_secret)          # shepherd holds this
        gun = keyring.issue("scout-1")               # CommandGuard for scout-1
        verifier = keyring.verify_guard("scout-1")   # shepherd-side check
        assert verifier.verify(signed_by_scout_1)
        assert not verifier.verify(signed_by_scout_2)  # different DNA
    """

    def __init__(self, unit_secret: bytes):
        self._unit_secret = bytes(unit_secret)

    def issue(self, agent_id: str, dna: Optional[str] = None):
        """Issue the agent's signing guard at birth. The agent receives a
        CommandGuard holding ONLY its derived key — never the unit secret."""
        if CommandGuard is None:
            raise RuntimeError("CommandGuard unavailable (sdk/integrity.py missing)")
        return CommandGuard(key=derive_agent_key(self._unit_secret, agent_id, dna))

    def verify_guard(self, agent_id: str, dna: Optional[str] = None):
        """Shepherd-side guard for verifying an agent's signatures. Derives
        the SAME key the agent was issued — the gun only fires for its owner."""
        if CommandGuard is None:
            raise RuntimeError("CommandGuard unavailable (sdk/integrity.py missing)")
        return CommandGuard(key=derive_agent_key(self._unit_secret, agent_id, dna))

    def verify_signature(self, agent_id: str, spotting: object,
                         dna: Optional[str] = None) -> bool:
        """Convenience: verify one spotting against an agent's identity."""
        return self.verify_guard(agent_id, dna).verify(spotting)


__all__ = ["AgentKeyring", "derive_agent_key", "module_dna_fingerprint"]