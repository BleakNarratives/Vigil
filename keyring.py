#!/usr/bin/env python3
"""
vigil keyring.py — AgentKeyring: RoboCop key custody (H1).

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
import base64
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Optional

try:
    from vigil.integrity import CommandGuard
except ImportError:
    try:
        from integrity import CommandGuard
    except ImportError:  # pragma: no cover - degraded mode
        CommandGuard = None

DNA_NAMESPACE = b"vigil-agent-key-v1"


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


DEFAULT_VAULT_PATH = Path("~/.concierge/vault.json").expanduser()
VAULT_SLOT = "unit_secret"


def load_unit_secret(vault_path: Optional[Path] = None,
                     slot: str = VAULT_SLOT) -> bytes:
    """Read-or-create the swarm's unit secret INSIDE the concierge vault.

    The charge is generated once (os.urandom(32)), stored base64 under the
    vault's `unit_secret` slot with a pre-write backup, and is NEVER written
    to any other file. The agent only ever receives DERIVED keys — the unit
    secret stays in the vault, out of scout scope.

    Usage:
        keyring = AgentKeyring(load_unit_secret())
    """
    path = Path(vault_path) if vault_path is not None else DEFAULT_VAULT_PATH
    if not path.exists():
        raise FileNotFoundError(f"vault not found: {path}")
    with open(path) as f:
        vault = json.load(f)
    existing = vault.get(slot)
    if isinstance(existing, str) and existing:
        return base64.b64decode(existing)

    secret = os.urandom(32)
    vault[slot] = base64.b64encode(secret).decode("ascii")
    backup = str(path) + f".bak_{time.strftime('%Y%m%dT%H%M%S')}"
    shutil.copy2(path, backup)
    os.chmod(path, 0o600)
    with open(path, "w") as f:
        json.dump(vault, f, indent=2)
        f.write("\n")
    return secret


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
        self._revoked: set = set()

    def retire(self, agent_id: str) -> None:
        """DECOMMISSION THE GUN (RoboCop's law, operator-spec): the derived
        key of a retired/dead agent is a loaded weapon with no hand.
        Retirement is FOREVER — after this, verify_guard() refuses the
        agent's signatures. The Hall of the Devine calls this before it
        hangs the memorial, so there is no gap where the dead can fire."""
        self._revoked.add(agent_id)

    def is_retired(self, agent_id: str) -> bool:
        return agent_id in self._revoked

    def issue(self, agent_id: str, dna: Optional[str] = None):
        """Issue the agent's signing guard at birth. The agent receives a
        CommandGuard holding ONLY its derived key — never the unit secret."""
        if CommandGuard is None:
            raise RuntimeError("CommandGuard unavailable (vigil/integrity.py missing)")
        return CommandGuard(key=derive_agent_key(self._unit_secret, agent_id, dna))

    def verify_guard(self, agent_id: str, dna: Optional[str] = None):
        """Shepherd-side guard for verifying an agent's signatures. Derives
        the SAME key the agent was issued — the gun only fires for its owner.
        RETIRED agents are refused: the dead do not sign. Retirement is
        forever; there is no un-retire path by design."""
        if agent_id in self._revoked:
            raise RuntimeError(f"agent {agent_id!r} is RETIRED — signatures "
                               f"refused (RoboCop's law: the gun does not "
                               f"fire for the dead)")
        if CommandGuard is None:
            raise RuntimeError("CommandGuard unavailable (vigil/integrity.py missing)")
        return CommandGuard(key=derive_agent_key(self._unit_secret, agent_id, dna))

    def verify_signature(self, agent_id: str, spotting: object,
                         dna: Optional[str] = None) -> bool:
        """Convenience: verify one spotting against an agent's identity."""
        return self.verify_guard(agent_id, dna).verify(spotting)

    @classmethod
    def from_vault(cls, vault_path: Optional[Path] = None) -> "AgentKeyring":
        """Build a keyring whose charge lives in the concierge vault."""
        return cls(load_unit_secret(vault_path))


__all__ = ["AgentKeyring", "derive_agent_key", "module_dna_fingerprint",
           "load_unit_secret", "DEFAULT_VAULT_PATH", "VAULT_SLOT"]