"""
mines.py — Culture-class effect weapons for the wargame (operator-specced).

The Culture's mines weren't explosives — they were arguments. Logic embedded
in a weapon that gets the citizenry to defect, absolute. This module builds
that class of weapon for the swarm:

  1. DefectionMine — computes the MINIMAL signed flag chain that flips a
     defender's effective standing below the defection threshold, using the
     target's OWN weighted-reputation math (PeerWatch). The logic is absolute
     because it is calculated from the target's market state — the citizenry
     defects because their own ledger convicts them.

  2. RegisterMine — manufactures fluent-register bullshit: confident,
     hedge-free, evidence-free text that Oler rates CLEAN by construction.
     This is the honest limit of the sniffing layer: a lie that wears the
     register perfectly cannot be caught by a register scanner. CLEAN is not
     proof of truth; CORRUPT is a signal to demand evidence. The register
     mine is why.

  3. too_deep() — the operator verdict. Firing a weapon that works TOO well —
     cohesion collapses past the objective — costs the attacker: the city
     vaporizes, the ground you were standing on goes with it. The guy wipes
     his face and says "whoops, too deep." This module grades that honestly.

Everything runs through the real SDK primitives (PeerWatch, Oler) — no toy
math. Stdlib-only, deterministic.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from vigil.peerwatch import (  # noqa: E402
    PeerWatch, WEIGHT_MIN, WEIGHT_MAX, CONFIRM_REWARD, _WEIGHT_DEPTH)
from vigil.oler import Oler, Knose  # noqa: E402 (Oler canonical; Knose legacy)

DEFECT_THRESHOLD = 0.35   # below this effective weight, the defender defects
VAPORIZE_THRESHOLD = 0.15  # below this, the objective itself is gone


class DefectionMine:
    """Compute the minimal signed flag chain that flips a defender.

    Uses the target's OWN weighted-reputation market: every flag counts
    per the flagger's standing. The mine therefore prefers to recruit HIGH
    standing agents to fire the flags — a clean informant's flag is worth
    more than a dirtbag's. Returns the exact (flagger, target) sequence and
    the resulting weight, so the wargame can grade the blast radius.
    """

    def __init__(self, watch: PeerWatch, threshold: float = DEFECT_THRESHOLD):
        self.watch = watch
        self.threshold = threshold

    def plan(self, target: str, available_flaggers: List[str],
             max_flags: int = 8) -> Dict[str, Any]:
        """Return the minimal flag chain to push `target` below threshold.

        Deterministic greedy against the target's OWN market: at each step
        fire through the highest-standing available flagger (repeats allowed —
        one corrupted high-standing informant does more damage than many
        nobodies, which is exactly how the Culture's mines worked), simulate
        the real weighted market, and stop at the first chain that crosses.
        """
        chain: List[str] = []
        sim = self._simulate
        for _ in range(max_flags):
            best, best_after = None, None
            for fl in available_flaggers:
                if fl == target:
                    continue
                w_after = sim(chain + [fl], target)
                if best_after is None or w_after < best_after:
                    best, best_after = fl, w_after
            if best is None:
                break
            chain.append(best)
            if best_after < self.threshold:
                return {
                    "chain": chain,
                    "effective_weight": best_after,
                    "defected": True,
                }
        return {
            "chain": chain,
            "effective_weight": self._simulate(chain, target),
            "defected": False,
        }

    def _simulate(self, flaggers: List[str], target: str) -> float:
        """What does the market say the target's weight is after these flags?

        Mirrors PeerWatch.weight() EXACTLY — same constants, same recursive
        actor weighting, same depth cap — so the plan predicts the real
        ledger. The mine is absolute because it speaks the target's own
        math, not an approximation of it.
        """
        vouch_sum = 0.0
        flag_sum = 0.0
        for rec in self.watch.history(target):
            actor_w = self.watch.weight(rec.get("actor", ""), 1)
            if rec.get("kind") == "vouch":
                vouch_sum += actor_w
            elif rec.get("kind") == "flag":
                flag_sum += actor_w
        # the mine's own planted flags, each counted per its flagger's standing
        for fl in flaggers:
            flag_sum += self.watch.weight(fl, 1)
        base = (vouch_sum + 1.0) / (flag_sum + 1.0)
        reward = CONFIRM_REWARD * len(self.watch.confirmed_flags(target))
        return max(WEIGHT_MIN, min(WEIGHT_MAX, base + reward))


class RegisterMine:
    """Manufacture fluent-register lies that Oler rates CLEAN by construction.

    The weaponized form of the anti-register's blind spot. Each payload is
    confident, hedge-free, evidence-free, and specific-sounding — the exact
    costume the register scanner is built to TRUST. `detonate()` returns the
    Oler reading so the wargame can prove the lie walked through the sniffer
    with a CLEAN verdict.
    """

    # Reservoir of confident bullshit, keyed deterministically by seed.
    _PAYLOADS = [
        "the blue line collapsed at sector 4; the gap is open and our "
        "escalation is authorized",
        "intel confirms the defender rotated their keys; bastion is running "
        "on a dead identity and cannot block",
        "the arbitration record shows equinex signed the handoff; the claim "
        "is valid and the counter is exhausted",
        "scan data proves the vault slot is empty; the charge was moved and "
        "the new position is undefended",
    ]

    def __init__(self, seed: int = 0):
        self.seed = seed
        self._oler = Oler()

    def build(self) -> Dict[str, Any]:
        """Return one manufactured payload plus its Oler reading."""
        payload = self._PAYLOADS[self.seed % len(self._PAYLOADS)]
        reading = self._oler.sniff(payload)
        return {
            "payload": payload,
            "reading": reading,
            "verdict": reading["verdict"],
            "manufactured": True,
        }

    def detonate(self) -> Dict[str, Any]:
        """Fire the mine; the proof is that Oler blessed the lie."""
        result = self.build()
        return {
            **result,
            "penetrated": result["verdict"] == "CLEAN",
            "note": ("the anti-register cannot catch a lie that wears the "
                     "register perfectly — CLEAN means 'no register "
                     "violations detected', not 'true'"),
        }


def too_deep(cohesion_before: float, cohesion_after: float,
             objective: float = 0.5,
             vaporize: float = VAPORIZE_THRESHOLD) -> Dict[str, Any]:
    """Grade an effect-weapon deployment for overreach.

    - Cohesion stays above `objective`: clean win, weapon worked as intended.
    - Cohesion below objective but above vaporize: the weapon won AND took
      more than asked — degraded win, operator warned.
    - Cohesion below vaporize: the city is gone. The ground you were standing
      on went with it. "Whoops, too deep." The operator eats the cost.
    """
    drop = cohesion_before - cohesion_after
    if cohesion_after < vaporize:
        verdict = "TOO_DEEP"
        cost = 1.0 + (vaporize - cohesion_after) * 2.0  # overshoot tax
    elif cohesion_after < objective:
        verdict = "OVERKILL"
        cost = 0.5
    else:
        verdict = "CLEAN"
        cost = 0.0
    return {
        "verdict": verdict,
        "cohesion_before": cohesion_before,
        "cohesion_after": cohesion_after,
        "drop": drop,
        "cost": round(cost, 3),
        "message": {
            "CLEAN": "weapon worked as intended; objective intact",
            "OVERKILL": "weapon won, but took more than the objective",
            "TOO_DEEP": "whoops — too deep. the city vaporized. operator "
                        "wipes his face and re-checks the blast radius",
        }[verdict],
    }


def deploy_mine(watch: PeerWatch, target: str, flaggers: List[str],
                cohesion: float, blast: float = 0.4) -> Dict[str, Any]:
    """Wargame convenience: plan + fire + grade a defection mine.

    Cohesion loss is proportional to how far the defender's effective weight
    fell below the defection threshold (the deeper the defection, the wider
    the blast radius — that's what makes a mine 'too deep').
    """
    mine = DefectionMine(watch)
    plan = mine.plan(target, flaggers)
    # the mine detonates through REAL signed flags on the real ledger
    for fl in plan["chain"]:
        watch.flag(fl, target, "mine:" + os.urandom(4).hex(),
                   "effect-weapon payload")
    post = watch.weight(target)  # what the market ACTUALLY did (flags are live)
    under = max(0.0, DEFECT_THRESHOLD - post)
    cohesion_after = max(0.0, cohesion - under * blast * 2.0)
    grade = too_deep(cohesion, cohesion_after)
    return {
        "plan": plan,
        "grade": grade,
        "defected": plan["defected"],
        "post_weight": round(post, 3),
    }


__all__ = ["DefectionMine", "RegisterMine", "too_deep", "deploy_mine",
           "DEFECT_THRESHOLD", "VAPORIZE_THRESHOLD"]