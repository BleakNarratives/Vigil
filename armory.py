#!/usr/bin/env python3
"""
vigil armory.py — THE ARMORY: live findings become EXECUTABLE red-team
moves on real breach points.

Operator-spec (2026-09-08): the citybridge live lane produced intel
("collective_integrity_breach: HIGH, breach=True") — but intel is not a
move. The armory closes that gap. For each live finding with breach=True
it builds an ArmoredMove:

  1. EXECUTE HANDLE — a callable that rebuilds the city's own loom fresh,
     re-fires THE EXACT named attack from Code-City's RedTeamAttacker,
     and returns the real result. The move is the attack, not a report
     about the attack.
  2. AGENT ROUTING — canon routing to the right red specialist:
       VIPER   (Precision/Auger)   -> surgical single-point breaches
                                     (fiber theft, knot tampering, metadata)
       RAVAGE  (Brute Force)       -> floods, hashes, anything with volume
                                     (integrity breach, DoS)
       WRAPPER (UI Mimicry)        -> trust/identity surface work
                                     (relationship injection, string identity)
     Blue's block market can interdict: a blocked move scores blue, not red.
  3. EVIDENCE-BASED SCORING — red only scores when the re-run CONFIRMS the
     breach on a fresh loom. An unconfirmed finding scores zero and is
     flagged. STRIKE THE FORK: the claim (finding) must ring against ground
     truth (the re-fired attack) before it moves the score.

Everything executes in-memory against looms the armory builds itself —
no filesystem writes, no network, nothing outside the arena process.

CLI:
    python3 vigil/armory.py <target_dir> [--json]
"""
from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # home root

from vigil.citybridge import (  # noqa: E402
    _find_pair, _scan_live, MAX_FINDINGS_PER_LANE,
)

# ---------------------------------------------------------------------------
# Canon routing — Code City Red team (CLAUDE.md AGENT CANON, do not rename)
# ---------------------------------------------------------------------------

VIPER, RAVAGE, WRAPPER = "viper", "ravage", "wrapper"

AGENT_ROUTING = {
    # surgical, single-point breaches -> THE PRECISION/AUGER
    "single_fiber_theft": VIPER,
    "knot_integrity_attack": VIPER,
    "metadata_tampering": VIPER,
    # volume / hash / flood -> THE BRUTE FORCE
    "collective_integrity_breach": RAVAGE,
    "denial_of_service": RAVAGE,
    # trust/identity surface -> THE UI MIMICRY
    "relationship_manipulation": WRAPPER,
}

SEVERITY_SCORE = {"high": 3, "medium": 2, "low": 1}


class _CityModules:
    """Loaded-once holder for the city's attack modules (imported lazily,
    shared across all execute handles — the modules are pure logic, the
    looms are built fresh per move)."""

    def __init__(self, target_dir: str):
        self.celtic_dir = _find_pair(target_dir,
                                     {"fiber_core.py", "celtic_crypto.py"})
        self.city_dir = _find_pair(target_dir,
                                   {"red_team_attacks.py",
                                    "defensive_fortifications.py"})
        if not self.celtic_dir or not self.city_dir:
            raise RuntimeError(
                "city modules not found under target — live lane offline")
        for p in (self.celtic_dir, self.city_dir):
            if p not in sys.path:
                sys.path.insert(0, p)
        import importlib
        self.fiber_core = importlib.import_module("fiber_core")
        self.forts = importlib.import_module("defensive_fortifications")
        self.attacks = importlib.import_module("red_team_attacks")

    def fresh_fortified_loom(self):
        """A new city, every move. Seeded with fibers so attacks have
        surface area (DoS needs baseline counts; knot attacks need knots)."""
        import celtic_crypto
        loom = self.forts.FortifiedCelticLoom()
        for i in range(4):
            loom.add_fiber(self.fiber_core.DataFiber(f"armory payload {i}",
                                                     f"owner_{i}"))
        return loom


def _attack_name(finding: Dict[str, Any]) -> Optional[str]:
    """'city_live_collective_integrity_breach' -> 'collective_integrity_breach'
    (the RedTeamAttacker method suffix: attack_<name>)."""
    p = finding.get("pattern", "")
    if not p.startswith("city_live_") or p.endswith("_error"):
        return None
    return p[len("city_live_"):]


def build_armory(target_dir: str,
                 findings: Optional[List[Dict[str, Any]]] = None
                 ) -> List[Dict[str, Any]]:
    """Forge one ArmoredMove per live breach finding.

    Returns a list of move dicts:
      { finding, name, agent, method_name, execute(), confirmed }
    `execute` re-fires the exact attack on a FRESH fortified loom and
    returns {'breach': bool, 'details': str, 'raw': entry}. Built lazily —
    the handle is forged even for non-breached findings, but only breach
    findings default to armed in the arena.
    """
    if findings is None:
        findings = _scan_live(target_dir)
    mods = _CityModules(target_dir)
    moves: List[Dict[str, Any]] = []

    for f in findings:
        name = _attack_name(f)
        if not name:
            continue
        # city methods are numbered: attack_1_single_fiber_theft ...
        # resolve by suffix so the finding name stays clean.
        method_name = None
        for cand in ("attack_1_", "attack_2_", "attack_3_", "attack_4_",
                     "attack_5_", "attack_6_", "attack_"):
            if hasattr(mods.attacks.RedTeamAttacker, cand + name):
                method_name = cand + name
                break
        method = (getattr(mods.attacks.RedTeamAttacker, method_name, None)
                  if method_name else None)

        if method is None:
            continue  # a finding without an executable method is not a move

        def make_handle(m=method, mm=mods):
            def execute() -> Dict[str, Any]:
                loom = mm.fresh_fortified_loom()
                attacker = mm.attacks.RedTeamAttacker(loom)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    try:
                        success = bool(m(attacker))
                    except Exception as exc:
                        return {"breach": False, "details": f"crashed: {exc}",
                                "raw": None}
                raw = attacker.attack_log[-1] if attacker.attack_log else None
                return {"breach": success,
                        "details": (raw or {}).get("details", "") if raw else "",
                        "raw": raw}
            return execute

        moves.append({
            "finding": f,
            "name": name,
            "agent": AGENT_ROUTING.get(name, VIPER),
            "method_name": method_name,
            "execute": make_handle(),
            "confirmed": None,   # set by strike()
            "result": None,
        })
    return moves[:MAX_FINDINGS_PER_LANE]


def strike(move: Dict[str, Any]) -> Dict[str, Any]:
    """STRIKE THE FORK: execute the move's handle and mark the finding
    confirmed or refuted by ground truth. Returns the move for chaining."""
    result = move["execute"]()
    move["confirmed"] = bool(result["breach"])
    move["result"] = result
    return move


def run_armory(target_dir: str, findings: Optional[List[Dict[str, Any]]] = None,
               blue_block: Optional[Callable[[Dict[str, Any]], bool]] = None
               ) -> Dict[str, Any]:
    """Arm every live breach finding, route to the canon agent, execute.

    blue_block: optional interdiction hook — if it returns True for a move,
    blue intercepted the strike (scored for blue, the move still executes
    for evidence but scores zero for red). The wargame passes its real
    block market here.

    Scoring (evidence-based):
      red   += severity score ONLY when confirmed (breach re-fires true)
      blue  += severity score for each interdicted move
      unconfirmed breach findings score NOTHING and are flagged.
    """
    moves = build_armory(target_dir, findings)
    breach_moves = [m for m in moves if m["finding"].get("breach")]
    armed = []
    red_score = blue_score = 0
    log = []

    for m in breach_moves:
        interdicted = bool(blue_block and blue_block(m))
        strike(m)
        sev = m["finding"].get("severity", "low")
        pts = SEVERITY_SCORE.get(sev, 1)
        if m["confirmed"]:
            if interdicted:
                blue_score += pts
            else:
                red_score += pts
        armed.append(m)
        log.append({
            "agent": m["agent"], "move": m["name"],
            "severity": sev, "interdicted": interdicted,
            "confirmed": m["confirmed"],
            "details": (m["result"] or {}).get("details", "")[:80],
        })

    refuted = [m["name"] for m in armed if not m["confirmed"]]
    return {
        "moves_built": len(moves),
        "moves_armed": len(armed),
        "red_score": red_score,
        "blue_score": blue_score,
        "refuted_findings": refuted,   # claimed breaches that didn't re-fire
        "log": log,
    }


def main():
    import argparse
    import json
    ap = argparse.ArgumentParser(description="Vigil armory — armed live moves")
    ap.add_argument("target")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    print(f"FORGING ARMORY against {args.target} ...")
    report = run_armory(args.target)
    print(f"\nMOVES BUILT: {report['moves_built']}  "
          f"ARMED: {report['moves_armed']}  "
          f"RED {report['red_score']} / BLUE (interdiction) "
          f"{report['blue_score']}")
    if report["refuted_findings"]:
        print(f"REFUTED (claimed breach, did not re-fire): "
              f"{', '.join(report['refuted_findings'])}")
    for entry in report["log"]:
        flag = "CONFIRMED" if entry["confirmed"] else "REFUTED"
        inter = " [INTERDICTED]" if entry["interdicted"] else ""
        print(f"  [{entry['agent'].upper():>7}] {entry['move']:<38} "
              f"[{entry['severity']:>6}]{inter} -> {flag}")
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
