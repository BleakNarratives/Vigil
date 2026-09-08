#!/usr/bin/env python3
"""
vigil citybridge.py — THE BRIDGE: Code-City's real attack modules, wired
into the Vigil wargame.

Operator-spec (2026-09-08): the wargame's stdlib scanner was a stub. This
module replaces the seam with three lanes, all emitting the SAME finding
schema wargame.py already consumes ({path, line, pattern, severity, code}):

  LANE 1 — regex     : Vigil's deterministic VULN_PATTERNS base (kept:
                        never lose the plain sight).
  LANE 2 — city sigs : static signatures derived from Code-City's REAL
                        attack taxonomy — the six named attacks of
                        RedTeamAttacker (Code_City/red_team_attacks.py):
                        fiber theft w/o owner proof, collective-hash
                        breach, knot integrity tampering, relationship
                        injection, metadata tampering, fiber-flood DoS.
                        Each maps to the code smell that leaves the door
                        open for that attack.
  LANE 3 — live      : RUNS Code-City's actual RedTeamAttacker against a
                        freshly-built FortifiedCelticLoom (its own blue
                        team) and converts the attack log into findings —
                        red's map of where the city's defenses actually
                        broke. Deterministic given the same loom build.

Every lane is optional; default = regex + city sigs (pure static, zero
side effects). live=True imports Code-City code at scan time — opt-in
by design, because the city fights back.

Usage from wargame:
    ScoutWargame(target, scan_fn=citybridge.scan)

CLI:
    python3 vigil/citybridge.py <target_dir> [--live] [--json]
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # home root

from vigil.wargame import VULN_PATTERNS, SKIP_DIRS, scan as _base_scan  # noqa: E402

# ---------------------------------------------------------------------------
# LANE 2 — city attack signatures
#
# Source of truth: Code_City/red_team_attacks.py attack_1..attack_6. Each
# signature targets the CODE SHAPE that enables the named attack against a
# Celtic Data Loom / similar integrity-store: mutable registries, restored-
# not-rebuilt state, dict-direct writes, unchecked floods, trust in caller
# identity strings.
# ---------------------------------------------------------------------------

CITY_SIGNATURES = [
    # attack_1 single fiber theft: ownership checked by a plain string,
    # and the store's storage (self.fibers / registry dicts) is reachable.
    ("fiber_theft",
     re.compile(r"\bself\.(?:fibers|store|registry)\[[^\]]+\]\s*="),
     "high"),

    # attack_2 collective integrity breach: attacker rewrites storage then
    # recomputes the hash manually — direct dict write into a hash-protected
    # structure, or a hash computed over mutable state with no seal.
    ("integrity_breach",
     re.compile(r"\bcollective_hash\s*=\s*"),
     "high"),

    # attack_3 knot integrity attack: verification state that the attack
    # path can WRITE to (mutate in place and restore after).
    ("knot_tamper",
     re.compile(r"(?:knot_registry|integrity_hash)\[[^\]]+\]\s*="),
     "high"),

    # attack_4 relationship manipulation: relationships accepted as a plain
    # mutable list — append is the attack.
    ("relationship_inject",
     re.compile(r"\b(?:relationships|edges|links)\.append\("),
     "medium"),

    # attack_5 metadata tampering: owner_proof / owner identity stored as
    # mutable metadata the caller supplies.
    ("metadata_tamper",
     re.compile(r"['\"]owner_proof['\"]\s*]?\s*="),
     "high"),

    # attack_6 denial of service: unbounded add-loop, no cap on store size.
    ("flood_dos",
     re.compile(r"for\s+\w+\s+in\s+range\(\s*\d{2,}\s*\)\s*:\s*"
                r"(?:#.*\n\s*)*(?:\s*\w+\.add_fiber\(|\s*\w+\.add\()"),
     "low"),

    # cross-cutting city smell: trust boundary by caller-supplied name
    # (attack_1/5 precondition) — owner/actor passed as a bare string.
    ("string_identity",
     re.compile(r"def\s+\w+\([^)]*\b(?:owner|actor|caller|principal)\s*:\s*str\b"),
     "low"),
]

MAX_FILE_BYTES_CITY = 400_000     # Code-City has some big generated blobs
MAX_FINDINGS_PER_LANE = 400       # lane budget: keep the arena fightable

LaneFindings = List[Dict[str, Any]]


def _scan_static(target_dir: str,
                 patterns: List[tuple],
                 tag_prefix: str = "") -> LaneFindings:
    """Deterministic pattern sweep, shared by lanes 1 and 2."""
    findings: LaneFindings = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            try:
                if os.path.getsize(path) > MAX_FILE_BYTES_CITY:
                    continue
                with open(path, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                for label, rx, severity in patterns:
                    if rx.search(line):
                        findings.append({
                            "path": path, "line": i,
                            "pattern": f"{tag_prefix}{label}",
                            "severity": severity,
                            "code": line.strip()[:80],
                            "lane": "city_sigs" if tag_prefix else "regex",
                        })
                        break  # one finding per line per lane
    return findings


def _find_pair(target_dir: str, needed: set) -> Optional[str]:
    """Find the first dir (deterministic walk) containing ALL needed module
    files. Used to locate the celtic package and the city attack modules,
    which live in different trees of Code-City."""
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if needed.issubset(set(files)):
            return root
    return None


def _scan_live(target_dir: str) -> LaneFindings:
    """LANE 3 — run Code-City's REAL RedTeamAttacker battery (all six named
    attacks) against a fresh FortifiedCelticLoom built from the city's own
    code, and convert the attack log into wargame findings. A SUCCESSFUL
    attack = a high-severity finding (the defense failed); a blocked attack
    = a low-severity receipt (the defense held, mapped for the record).

    Side effects: imports Code-City code, builds in-memory looms only —
    no filesystem writes outside the scan process.
    """
    celtic_dir = _find_pair(target_dir, {"fiber_core.py", "celtic_crypto.py"})
    city_dir = _find_pair(target_dir,
                          {"red_team_attacks.py", "defensive_fortifications.py"})
    if not celtic_dir or not city_dir:
        return [{"path": target_dir, "line": 0,
                 "pattern": "city_live_unavailable", "severity": "low",
                 "code": "celtic package or city attack modules not found "
                          "under target — live lane offline",
                 "lane": "live"}]

    for p in (celtic_dir, city_dir):
        if p not in sys.path:
            sys.path.insert(0, p)

    findings: LaneFindings = []
    try:
        import importlib
        crypto = importlib.import_module("celtic_crypto")
        fiber_core = importlib.import_module("fiber_core")
        attacks = importlib.import_module("red_team_attacks")
        forts = importlib.import_module("defensive_fortifications")

        # Build the city's own blue team: the fortified loom is what the
        # six-attack battery was written to test.
        loom = forts.FortifiedCelticLoom()
        for i in range(4):
            loom.add_fiber(fiber_core.DataFiber(f"arena payload {i}",
                                                f"owner_{i}"))

        attacker = attacks.RedTeamAttacker(loom)

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            if hasattr(attacker, "run_all_attacks"):
                attacker.run_all_attacks()
            else:
                battery = [a for name, a in sorted(vars(attacker).items())
                           if name.startswith("attack_") and callable(a)]
                for fn in battery:
                    try:
                        fn()
                    except Exception as exc:
                        findings.append({
                            "path": city_dir, "line": 0,
                            "pattern": f"city_live_{fn.__name__}_error",
                            "severity": "medium", "code": str(exc)[:80],
                            "lane": "live"})
        for entry in attacker.attack_log:
            name = entry.get("attack", "unknown")
            success = "SUCCESS" in entry.get("result", "")
            findings.append({
                "path": city_dir, "line": 0,
                "pattern": "city_live_" + name.lower().replace(" ", "_"),
                "severity": "high" if success else "low",
                "code": (entry.get("details", "") or "")[:80],
                "lane": "live",
                "breach": success,
            })
    except Exception as exc:
        findings.append({
            "path": celtic_dir, "line": 0,
            "pattern": "city_live_error", "severity": "medium",
            "code": f"live lane failed: {exc}"[:80], "lane": "live",
        })
    return findings[:MAX_FINDINGS_PER_LANE]


def scan(target_dir: str, live: bool = False,
         lanes: str = "all") -> LaneFindings:
    """The wargame scan() contract, three lanes deep.

    lanes: "all" (default) = regex + city sigs (+ live when live=True);
           "regex" / "city" / "live" to run a single lane.
    Returns findings sorted by (severity, path, line) — deterministic.
    """
    out: LaneFindings = []
    want_all = lanes == "all"
    if want_all or lanes == "regex":
        base = _scan_static(target_dir, VULN_PATTERNS)
        out += base[:MAX_FINDINGS_PER_LANE]
    if want_all or lanes == "city":
        out += _scan_static(target_dir, CITY_SIGNATURES,
                            tag_prefix="city_")[:MAX_FINDINGS_PER_LANE]
    if (want_all and live) or lanes == "live":
        out += _scan_live(target_dir)[:MAX_FINDINGS_PER_LANE]

    sev_rank = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda f: (sev_rank.get(f["severity"], 3),
                            f["path"], f["line"]))
    # dedupe on (path, line, pattern)
    seen = set()
    deduped = []
    for f in out:
        key = (f["path"], f["line"], f["pattern"])
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    return deduped


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Code-City bridge scanner")
    ap.add_argument("target")
    ap.add_argument("--live", action="store_true",
                    help="run Code-City's real attack battery (lane 3)")
    ap.add_argument("--lanes", default="all",
                    help="all | regex | city | live")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    results = scan(args.target, live=args.live, lanes=args.lanes)
    by_lane: Dict[str, int] = {}
    for f in results:
        by_lane[f["lane"]] = by_lane.get(f["lane"], 0) + 1
    print(f"{len(results)} findings — by lane: "
          + ", ".join(f"{k}={v}" for k, v in sorted(by_lane.items())))
    if args.json:
        import json
        print(json.dumps(results, indent=2))
    else:
        for f in results[:25]:
            print(f"  [{f['severity']:>6}][{f['lane']:>9}] "
                  f"{Path(f['path']).name}:{f['line']} {f['pattern']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
