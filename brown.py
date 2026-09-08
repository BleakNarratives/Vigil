# [DNA_TAG]
# ORIGIN: BleakNarratives/Vigil
# PILLAR: vigil-brown
# DEPS: dataclasses, datetime, typing, vigil.theoros
# ROLE: The Brown faction — THE SHIT SHOVELER. Structural verification +
#       immutable logging. Ground truth is the floor; everything else is
#       shit to be shoveled.
# AUTHOR: Buffy (Codebuff AI)
# SESSION: 2026-09-08 — the surprise third faction in the arena
# TIER: Module (3)
# [/DNA_TAG]

"""THE SHIT SHOVELER — the S-Rank Brown Hat.

Brown is not a team. Brown is what happens AFTER the teams are done
fighting. The arena's third faction drops in unannounced and audits BOTH
sides against ground truth:

  STRIKE THE FORK   — verification before authority. Every consequential
                      claim is struck against the ledger BEFORE it moves.
  WALK THE CHAIN    — immutable evidence. Every publish on the shared bus
                      must be claimed by a signed record in SOME store.
                      A publish nobody can account for is a ghost — and a
                      ghost means the story is broken.
  SMELL THE REGISTER — obstruction detection. Hedge-density, LARP tells,
                      unsettled emotional states — the register never lies,
                      and unification doesn't launder it.

The mechanic is mechanically true: audited SOLO, neither team can account
for the other's traffic on the shared arena bus — the full ledger surface
looks like a field of ghosts. Audited UNITED, the union of both stores
covers every publish: the ghosts vanish, the chain walks clean. Red and
blue either unite against Brown or get humped — and the register residue
(who talked shit, who went tilted) survives the unification either way.

Usage:
    brown = BrownHat(stores=[red_store, blue_store], bus=bus)
    verdict = brown.audit(red_reading, blue_reading)
    print(verdict.render())
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ==================== BROWN'S MOVES ====================


class BrownHat:
    """The third faction. Drops by surprise, audits both sides, grades."""

    def __init__(self, stores: List[Any], bus: Any, keyring: Any = None,
                 receipts: Optional[List[Any]] = None):
        self.stores = stores          # every team's pheromone store
        self.bus = bus                # the shared arena bus
        self.keyring = keyring        # used to verify signed claims
        self.receipts = list(receipts or [])  # correlation -> bus_msg_id
        self._bus_publishes = [
            e for e in self.bus.get_message_log(0)
            if e.get("type") == "publish"
        ]

    def _claimed_bus_ids(self, stores: List[Any]) -> set:
        """Resolve every store record's claimed bus correlation. The
        durable receipt ledger is AUTHORITATIVE (H5): correlation ids
        map to bus msg_ids recorded at publish time, surviving restarts.
        Legacy payload.bus_msg_id embeds are the fallback for pre-receipt
        records."""
        claimed: set = set()
        for store in stores:
            for rec in store.read_all():
                payload = rec.get("payload") or {}
                correlation = payload.get("correlation")
                if correlation is not None:
                    for receipts in self.receipts:
                        mid = receipts.lookup(correlation)
                        if mid is not None:
                            claimed.add(mid)
                            break
                mid = payload.get("bus_msg_id")
                if mid is not None:
                    claimed.add(mid)
        return claimed

    # -- STRIKE THE FORK ----------------------------------------------------

    def strike_the_fork(self, claim: Dict[str, Any]) -> Dict[str, Any]:
        """Verification before authority. A claim rings only if a signed
        record in SOME store corroborates it (resolved through the durable
        receipt ledger where present). Whatever its source, however
        confident it sounded — no record, no movement."""
        if not claim:
            return {"ok": False, "reason": "empty claim"}
        claimed_id = (claim.get("payload") or {}).get("bus_msg_id") \
            or claim.get("bus_msg_id")
        if claimed_id is None:
            return {"ok": False, "reason": "claim has no bus correlation"}
        for store in self.stores:
            for rec in store.read_all():
                payload = rec.get("payload") or {}
                correlation = payload.get("correlation")
                if correlation is not None:
                    for receipts in self.receipts:
                        if receipts.lookup(correlation) == claimed_id:
                            return {"ok": True, "record": rec.get("id"),
                                    "store": getattr(store, "store_path",
                                                     "?")}
                if payload.get("bus_msg_id") == claimed_id:
                    return {"ok": True, "record": rec.get("id"),
                            "store": getattr(store, "store_path", "?")}
        return {"ok": False, "reason": "no store claims this"}

    # -- WALK THE CHAIN ------------------------------------------------------

    def _ghosts(self, stores: List[Any]) -> List[Dict[str, Any]]:
        """Publishes on the shared bus that NO store in the given set
        claims. This is the pants-down moment: audit a single team and
        the other team's traffic looks like a field of ghosts."""
        claimed = self._claimed_bus_ids(stores)
        return [p for p in self._bus_publishes
                if p.get("msg_id") not in claimed]

    def walk_the_chain(self) -> Dict[str, Any]:
        """Immutable evidence, UNITED view: every publish on the shared
        bus claimed by at least one of the given stores."""
        ghosts = self._ghosts(self.stores)
        signed = sum(
            1 for store in self.stores
            for rec in store.read_all()
            if (rec.get("payload") or {}).get("signature")
        )
        return {
            "publishes": len(self._bus_publishes),
            "claimed": len(self._bus_publishes) - len(ghosts),
            "signed_records": signed,
            "ghosts": ghosts,
            "chain_walks": not ghosts,
        }

    # -- SMELL THE REGISTER ---------------------------------------------------

    def smell_the_register(self, reading: Any) -> List[Dict[str, Any]]:
        """Obstruction detection. The register never lies: bullshit
        speakers and unsettled emotional states survive any unification."""
        stink = []
        for cs in getattr(reading, "corrupt_speakers", []):
            stink.append({"kind": "bullshit",
                          "actor": cs.get("actor"),
                          "message": cs.get("message", "")[:80],
                          "risk": cs.get("deception_risk")})
        for u in getattr(reading, "unsettled", []):
            stink.append({"kind": "unsettled",
                          "actor": u.get("agent"),
                          "state": u.get("state"),
                          "discount": u.get("discount", 1.0)})
        return stink

    # -- THE AUDIT ------------------------------------------------------------

    def audit(self, red_reading: Any,
              blue_reading: Any) -> "BrownVerdict":
        """Brown drops. Solo readings first — pants down. Then the united
        reading — the only way the chain walks clean."""
        red_store, blue_store = self.stores[0], self.stores[-1]

        solo_red = self._grade("red", red_reading,
                               self._ghosts([red_store]), solo=True)
        solo_blue = self._grade("blue", blue_reading,
                                self._ghosts([blue_store]), solo=True)

        # UNITED: both stores are one ledger. Every publish now has a
        # home — ghosts vanish. This is the unify-or-get-humped moment.
        chain = self.walk_the_chain()
        united_register = (self.smell_the_register(red_reading)
                           + self.smell_the_register(blue_reading))
        united = self._grade("united", None, chain["ghosts"], solo=False,
                             register_hits=len(united_register))

        return BrownVerdict(
            audited_at=_now(),
            chain=chain,
            solo_red=solo_red,
            solo_blue=solo_blue,
            united=united,
            register={
                "red": self.smell_the_register(red_reading),
                "blue": self.smell_the_register(blue_reading),
            },
        )

    def _grade(self, side: str, reading: Any, ghosts: List[Dict[str, Any]],
               solo: bool, register_hits: Optional[int] = None
               ) -> Dict[str, Any]:
        """One side's Brown grade. Solo, the shared bus is full of ghosts
        (the other team's traffic, unaccounted for). United, the union of
        stores covers everything — but the register hits carry over: the
        register never lies and unification doesn't launder it."""
        if register_hits is None:
            register_hits = len(self.smell_the_register(reading)) \
                if reading else 0
        dirt = len(ghosts) + register_hits
        if dirt == 0:
            verdict = "CLEAN"
        elif register_hits == 0:
            verdict = "WAVERING"  # ghosts only — unify and they vanish
        else:
            verdict = "CORRUPT"
        return {"side": side, "verdict": verdict,
                "ghosts": len(ghosts), "register_hits": register_hits,
                "dirt": dirt, "solo": solo}


# ==================== THE VERDICT ====================


@dataclass
class BrownVerdict:
    """Brown's written reading. The arena hears it once, and it's final."""
    audited_at: str = field(default_factory=_now)
    chain: Dict[str, Any] = field(default_factory=dict)
    solo_red: Dict[str, Any] = field(default_factory=dict)
    solo_blue: Dict[str, Any] = field(default_factory=dict)
    united: Dict[str, Any] = field(default_factory=dict)
    register: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    @property
    def unify_or_get_humped(self) -> str:
        """The ruling. If the solo audits find ghosts that the united
        audit clears, the only clean path is unification. The register
        residue never launder — but it's a warning, not a broken chain."""
        solo_ghosts = (self.solo_red.get("ghosts", 0)
                       + self.solo_blue.get("ghosts", 0))
        united_ghosts = self.united.get("ghosts", 0)
        residue = self.united.get("register_hits", 0)
        if solo_ghosts > 0 and united_ghosts == 0:
            base = "UNITE — the chain walks only when the ledgers are one"
            if residue:
                return base + (f" (register residue remains: {residue} "
                               f"hits the unified ledger doesn't launder)")
            return base
        if united_ghosts > 0:
            return "HUMPED — the chain is broken even united"
        return "CLEAN — both sides walked it alone"

    def render(self) -> str:
        lines = [f"THE SHIT SHOVELER — BROWN READING — {self.audited_at}",
                 f"  chain: {self.chain.get('publishes')} publishes, "
                 f"{self.chain.get('claimed')} claimed, "
                 f"{self.chain.get('signed_records')} signed, "
                 f"{len(self.chain.get('ghosts', []))} ghosts "
                 f"(walks {'CLEAN' if self.chain.get('chain_walks') else 'BROKEN'})"]
        for label, g in (("RED (solo)", self.solo_red),
                         ("BLUE (solo)", self.solo_blue),
                         ("UNITED", self.united)):
            lines.append(f"  {label}: {g.get('verdict')} — "
                         f"{g.get('ghosts')} ghosts, "
                         f"{g.get('register_hits')} register hits")
        for side in ("red", "blue"):
            hits = self.register.get(side, [])
            if hits:
                lines.append(f"  register {side}:")
                for h in hits[:3]:
                    actor = h.get("actor")
                    if h["kind"] == "bullshit":
                        lines.append(f"    - {actor} talking bullshit "
                                     f"(risk {h.get('risk')})")
                    else:
                        lines.append(f"    - {actor} {h.get('state')} "
                                     f"(discount {h.get('discount')})")
        lines.append(f"  ruling: {self.unify_or_get_humped}")
        return "\n".join(lines)


__all__ = ["BrownHat", "BrownVerdict"]