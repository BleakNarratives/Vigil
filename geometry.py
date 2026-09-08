#!/usr/bin/env python3
"""
spyglass geometry.py — WhorlWeave: geometric priority for scout bids.

A real swarm agent bids on latent state, not arrival speed. This module gives
every scout a position inside the Whorl-weave (ring / phase / helical layer)
and computes bid confidence + strength from that geometry:

    * Quadratic dispersion — signal urgency propagates as urgency / (1 + k*d^2),
      so a scout near the signal source feels it at (near) full strength while
      a scout far out on the weave feels it attenuated. This is the geometric
      urgency field the SDK previously lacked (it was a flat event system).
    * Latent state — health, resource cost, and mission priority fold into the
      final bid priority, so a healthy scout whose mission is on-point beats a
      faster-arriving scout with a dead battery.

Design notes (for agent self-modification):
    * Swap the dispersion law by overriding `dispersion()` (quadratic is the
      default; exponential or inverse-linear are drop-in alternates).
    * Change what "position" means by overriding `position()` / `coords()`
      (e.g., agent telemetry instead of assigned weave slots).
    * Latent keys are read with defaults, so a bare dict works:
      {"health": 0..1, "resource_cost": 0..1, "mission_priority": 0..1}

DNA_TAG
ORIGIN: BleakNarratives/sdk
PILLAR: swarm-coordination
DEPS: math,dataclasses,typing
ROLE: Whorl-weave geometric bidding substrate
AUTHOR: Bleak
SESSION: 2026-09-08
TIER: 2
/DNA_TAG
"""
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

# Golden angle — spreads phases evenly no matter how many agents join late.
_GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))

HELIX_STEP_DEFAULT = 1.0
DISPERSION_K_DEFAULT = 1.0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(frozen=True)
class WeavePosition:
    """A scout's slot in the Whorl-weave.

    ring   — distance from the weave center (0 = hub)
    phase  — angular position in radians
    layer  — helical turn (stacking rings along the weave axis)
    """
    agent_id: str
    ring: int = 0
    phase: float = 0.0
    layer: int = 0

    def coords(self, helix_step: float = HELIX_STEP_DEFAULT) -> tuple:
        """Cartesian coordinates: (ring*cos, ring*sin, layer*step)."""
        return (self.ring * math.cos(self.phase),
                self.ring * math.sin(self.phase),
                self.layer * helix_step)

    def distance_to(self, other: "WeavePosition",
                    helix_step: float = HELIX_STEP_DEFAULT) -> float:
        a, b = self.coords(helix_step), other.coords(helix_step)
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"WeavePosition({self.agent_id!r}, ring={self.ring}, phase={self.phase:.3f}, layer={self.layer})"


class WhorlWeave:
    """Assigns weave slots to scouts and computes geometric bid modifiers.

    Usage:
        weave = WhorlWeave(["scout-1", "scout-2"], rings={"scout-2": 2})
        geom = weave.modulate(spotting, latent={"health": 0.8, "mission_priority": 0.9})
        # geom["confidence"], geom["strength"], geom["priority"] are position-aware
    """

    def __init__(self, agent_ids: Iterable[str] = (),
                 rings: Optional[Dict[str, int]] = None,
                 helix_step: float = HELIX_STEP_DEFAULT,
                 dispersion_k: float = DISPERSION_K_DEFAULT,
                 seed_phase: float = 0.0):
        self.helix_step = float(helix_step)
        self.dispersion_k = max(0.0, float(dispersion_k))
        self._rings = dict(rings or {})
        self._positions: Dict[str, WeavePosition] = {}
        ids = list(agent_ids)
        for i, aid in enumerate(ids):
            self._positions[aid] = self._slot_for(aid, i, seed_phase)
        # Unregistered agents default to the hub (ring 0, phase 0).
        self._center = WeavePosition(agent_id="__center__")

    def _slot_for(self, agent_id: str, index: int, seed_phase: float) -> WeavePosition:
        ring = int(self._rings.get(agent_id, 0))
        return WeavePosition(
            agent_id=agent_id,
            ring=ring,
            phase=seed_phase + index * _GOLDEN_ANGLE,
            layer=ring,
        )

    # -- position API ---------------------------------------------------------

    def register(self, agent_id: str, ring: Optional[int] = None) -> WeavePosition:
        """Add (or re-slot) an agent; returns its position."""
        if agent_id in self._positions and ring is None:
            return self._positions[agent_id]
        slot = self._slot_for(agent_id, len(self._positions), 0.0)
        if ring is not None:
            slot = WeavePosition(agent_id, ring=ring, phase=slot.phase, layer=ring)
        self._positions[agent_id] = slot
        return slot

    def position(self, agent_id: str) -> WeavePosition:
        return self._positions.get(agent_id, self._center)

    def center(self) -> WeavePosition:
        return self._center

    def distance(self, a: WeavePosition, b: Optional[WeavePosition] = None) -> float:
        return a.distance_to(b or self._center, self.helix_step)

    # -- dispersion + bid geometry --------------------------------------------

    def dispersion(self, urgency: float, distance: float) -> float:
        """Quadratic dispersion: felt urgency = urgency / (1 + k*d^2).

        d=0 -> full urgency. Beyond that the falloff is quadratic in distance,
        which is the Whorl "signal urgency propagates geometrically" law.
        """
        return float(urgency) / (1.0 + self.dispersion_k * (distance ** 2))

    def modulate(self, spotting: Any, source_position: Optional[WeavePosition] = None,
                 latent: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """Compute position-aware confidence/strength + final bid priority.

        Returns a dict with: confidence, strength, priority, distance,
        dispersion_factor, position, and the latent state folded in.

        priority = conf * strength * mission_priority * health / (1 + resource_cost)
        """
        agent_pos = self.position(spotting.source)
        src_pos = source_position or self._center
        dist = agent_pos.distance_to(src_pos, self.helix_step)
        factor = self.dispersion(1.0, dist)

        confidence = spotting.confidence * (0.5 + 0.5 * factor)
        strength = spotting.strength * factor

        latent = latent or {}
        health = _clamp01(latent.get("health", 1.0))
        resource_cost = _clamp01(latent.get("resource_cost", 0.0))
        mission_priority = _clamp01(latent.get("mission_priority", 1.0))

        priority = (confidence * strength * mission_priority * health
                    / (1.0 + resource_cost))

        return {
            "confidence": confidence,
            "strength": strength,
            "priority": priority,
            "distance": dist,
            "dispersion_factor": factor,
            "position": agent_pos,
            "latent": {"health": health, "resource_cost": resource_cost,
                       "mission_priority": mission_priority},
        }


__all__ = ["WhorlWeave", "WeavePosition", "DISPERSION_K_DEFAULT", "HELIX_STEP_DEFAULT"]