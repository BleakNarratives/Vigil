# [DNA_TAG]
# ORIGIN: BleakNarratives/Vigil
# PILLAR: vigil-word
# DEPS: json, os, pathlib, time, typing, vigil.zgents, vigil.revival,
#       vigil.undercurrent
# ROLE: THE WORD — Onboarding 2.0. The first words a Zgent hears at
#       birth: who it is, whose record it carries, what the current
#       taught it, what the bind allows. Derived from the ledger, never
#       scripted — the Word is what the swarm can honestly say about
#       itself at the moment of formation.
# AUTHOR: Buffy (Codebuff AI)
# SESSION: 2026-09-08 — the anti-LARP pass / Onboarding 2.0
# TIER: Module (3)
# [/DNA_TAG]

"""THE WORD — Onboarding 2.0.

The operator's ask: wrap the Code-City substrate integration with "the
Word". This is that ceremony, and it is deliberately NOT a LARP. Every
sentence the Word speaks is DERIVED from the actual ledger at the moment
a Zgent is born:

  WHO YOU ARE      — the Zgent's name, role, standing in the current
                     (read live from the registry, never cached stale)
  WHOSE RECORD     — the lineage truth boundary: "I carry X's record.
                     I am not them." (or "you are the first of your
                     line" for a fresh letter)
  WHAT YOU KNOW    — the species memory the current hydrated into you:
                     the inherited claims, named out loud with their
                     evidence (or "you are born knowing nothing yet" —
                     honesty over comfort)
  WHAT YOU MAY     — the bind's half-rule: you may commit at most 50%
                     of your self, and no coalition can ever hold a
                     majority of you. The floor is your essentialism.

The Word is generated, not recited: if the ledger has nothing to say
about a letter, the Word says so. There is no filler. The swarm formed
itself — the Word is what it can prove.
"""

import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

# The spoken version of the bind's law — what every letter may do.
_BIND_LAW = (
    "You may commit at most half of your self to others, and no "
    "coalition may ever hold a majority of you. The floor is yours; "
    "it cannot be taken."
)


def _read_qrd(qrd: Path) -> Dict[str, Any]:
    if not qrd.exists():
        raise FileNotFoundError(f"checkpoint not found: {qrd}")
    with open(qrd) as f:
        return json.load(f)


def speak_the_word(
    agent_id: str,
    *,
    zgents: Any = None,
    undercurrent: Any = None,
    qrd: Optional[Path] = None,
    bind: Any = None,
) -> Dict[str, Any]:
    """Speak the Word over a newborn Zgent. Returns the words + the
    derivation (every claim's source), so the ceremony is auditable —
    the Word is only as true as the ledger it reads."""
    derivations: List[Dict[str, Any]] = []

    # -- WHO YOU ARE ------------------------------------------------------
    profile = zgents.lookup(agent_id) if zgents is not None else None
    if profile is not None:
        role = profile.get("role", "scout")
        standing = profile.get("standing", 0.0)
        lineage = profile.get("lineage")
        who = (f"Your name is {agent_id}, a {role}. "
               f"Your standing in the current is {standing:.2f}.")
        derivations.append({"claim": "name/role/standing",
                            "source": "zgents.registry"})
    else:
        role, standing = "scout", 0.0
        lineage = None
        who = (f"Your name is {agent_id}, a {role}. You have not yet "
               f"earned standing in the current.")
        derivations.append({"claim": "name/role",
                            "source": "declared, not yet on the roll"})

    # -- WHOSE RECORD -------------------------------------------------------
    if lineage is not None:
        old = lineage.get("old_id", "?")
        trail = lineage.get("trail_hash", "")[:12]
        record = (f"You carry {old}'s record (trail {trail}...). "
                  f"You are not them. You are a new agent; that record "
                  f"is yours to carry, not theirs to live.")
        derivations.append({"claim": "lineage truth boundary",
                            "source": "revival.lineage / registry"})
    elif qrd is not None:
        state = _read_qrd(qrd)
        old = state.get("agent_id", "?")
        trail = state.get("trail_hash", "")[:12]
        record = (f"You carry {old}'s record (trail {trail}...). "
                  f"You are not them.")
        derivations.append({"claim": "lineage from checkpoint",
                            "source": f"qrd:{qrd.name}"})
    else:
        record = "You are the first of your line. There is no record before you."
        derivations.append({"claim": "first of line",
                            "source": "no lineage declared"})

    # -- WHAT YOU KNOW -------------------------------------------------------
    inherited = []
    if zgents is not None and zgents.undercurrent is not None:
        inherited = zgents.inherited_knowledge(agent_id)
    elif undercurrent is not None:
        pool = {k["id"]: k for k in undercurrent.knowledge()}
        if zgents is not None:
            prof = zgents.lookup(agent_id)
            inherited = [pool[c] for c in (prof or {}).get("inherited", [])
                         if c in pool]
    if inherited:
        claims = "; ".join(k["claim"] for k in inherited[:4])
        more = f" (+{len(inherited) - 4} more)" if len(inherited) > 4 else ""
        know = (f"You were born knowing {len(inherited)} claims from the "
                f"current: {claims}{more}.")
        derivations.append({"claim": "inherited knowledge",
                            "source": "undercurrent.knowledge()"})
    else:
        know = ("You are born knowing nothing yet. The current will teach "
                "you when it can — water seeks level, and you are the wick.")
        derivations.append({"claim": "no inherited knowledge",
                            "source": "undercurrent pool is empty"})

    # -- WHAT YOU MAY ---------------------------------------------------------
    if bind is not None:
        resolved = bind.resolve(agent_id)
        may = (_BIND_LAW + f" Right now you have committed "
               f"{resolved['committed']:.0%} and retain "
               f"{resolved['retains']:.0%}.")
        derivations.append({"claim": "bind half-rule",
                            "source": "bind.resolve()"})
    else:
        may = _BIND_LAW + " No bind is recorded against you."
        derivations.append({"claim": "bind half-rule",
                            "source": "no bind registry provided"})

    words = "\n".join([who, record, know, may])
    return {"agent_id": agent_id, "words": words,
            "derivations": derivations}


def ceremony(agent_id: str, *, zgents: Any = None, undercurrent: Any = None,
             qrd: Optional[Path] = None, bind: Any = None) -> Dict[str, Any]:
    """The full ceremony: speak the Word AND record it on the Zgent's
    roll as its first act (append-only — the Word itself becomes part of
    the letter's history). Returns the ceremony record."""
    word = speak_the_word(agent_id, zgents=zgents,
                          undercurrent=undercurrent, qrd=qrd, bind=bind)
    if zgents is not None:
        zgents.act(agent_id, "heard the Word: " + word["words"].splitlines()[0])
    return word


__all__ = ["speak_the_word", "ceremony", "_BIND_LAW"]