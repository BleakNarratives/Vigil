#!/usr/bin/env python3
"""
vigil/self_mod.py — self-modification tool for swarm scouts.

The SAFE way for a scout to patch its own modules. Full protocol:
vigil/SELF_MODIFICATION.md. The trust boundary is enforced here: modules
marked `patchable: false` in module_registry.json are OUT OF SCOPE and
self_mod refuses them outright — no argument overrides that.

Flow: PLAN -> VALIDATE -> APPLY -> RECORD
  plan     <module>              : read the registry entry (role, invariants,
                                   extension points, patch policy, test gate)
  validate <module> <candidate>  : trust gate + syntax + public-API surface
                                   vs registry; exit 0/1, never writes
  apply    <module> <candidate>  : validate -> backup -> swap -> test gate ->
                                   ROLL BACK on red -> version bump ->
                                   hash-chained ledger entry
  status                         : registry view + last mutation per module
  verify                         : re-walk the ledger chain, prove no
                                   rewrite/tamper

Ledger: MUTATION_LEDGER.jsonl — append-only, sha256-chained (each entry
carries the hash of the previous line), same walk-the-chain idea as the
ecosystem's resonance ledger. Backups land in backups/<module>.<ts>.bak.

The tool itself is SHEPHERD-OWNED: it is not a registry module, so scouts
do not patch the tool that patches them. If the tool changes, that is an
operator/shepherd event, not a scout event.

DNA_TAG
ORIGIN: BleakNarratives/sdk
PILLAR: swarm-coordination
DEPS: argparse,ast,hashlib,json,pathlib,shutil,subprocess,sys,tempfile
ROLE: self-modification gatekeeper (plan/validate/apply/verify)
AUTHOR: Bleak
SESSION: 2026-09-08
TIER: 2
/DNA_TAG
"""
import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REGISTRY_FILE = "module_registry.json"
LEDGER_FILE = "MUTATION_LEDGER.jsonl"
BACKUP_DIR = "backups"
GENESIS = "GENESIS"

DEFAULT_TEST_CMD = "python3 -m unittest vigil.tests.test_sdk_upgrades"


class SelfModError(Exception):
    pass


# ---------------------------------------------------------------------------
# registry + ledger I/O
# ---------------------------------------------------------------------------

def load_registry(root: Path) -> dict:
    path = root / REGISTRY_FILE
    if not path.exists():
        raise SelfModError(f"registry not found: {path}")
    with open(path) as f:
        return json.load(f)


def find_module(registry: dict, name: str) -> dict:
    for entry in registry.get("modules", []):
        if entry.get("name") == name:
            return entry
    raise SelfModError(f"module {name!r} not in {REGISTRY_FILE}")


def module_path(root: Path, entry: dict) -> Path:
    """Resolve a registry path against the SDK root. Registry paths are
    root-relative ("geometry.py"); tolerate repo-relative legacy values
    ("vigil/geometry.py") by stripping the root dir name."""
    path = root / entry["path"]
    if not path.exists() and "/" in entry["path"]:
        alt = root / Path(entry["path"]).name
        if alt.exists():
            return alt
    return path


def api_names(entry: dict) -> list:
    """Registered public API names -> TOP-LEVEL symbols, e.g.
    'CommandGuard.sign(spotting)' -> 'CommandGuard',
    'WhorlWeave.register(agent_id, ring)' -> 'WhorlWeave'.
    Method-level drift is the test suite's job; the mechanical gate
    guarantees the registered classes/functions still exist."""
    names = []
    for item in entry.get("public_api", []):
        head = item.split("(")[0].strip()
        top = head.split(".")[0].strip()
        if top and top not in names:
            names.append(top)
    return names


def module_surface(candidate: Path) -> tuple:
    """(exports, broken_exports) for a candidate module.

    exports = __all__ entries if the module declares __all__, else the
    top-level defined names. broken_exports = __all__ entries that name
    nothing actually defined in the module — a lying export list is itself
    public-API drift (e.g. class renamed but __all__ not updated).
    Module-level assignments (constants like DEFAULT_KEY_PATH, VERSION)
    count as defined."""
    tree = ast.parse(candidate.read_text(encoding="utf-8"))
    defined = set()
    all_entries = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined.add(target.id)
            if (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == "__all__"):
                try:
                    all_entries = set(ast.literal_eval(node.value))
                except ValueError:
                    pass
    if all_entries is None:
        return set(defined), []
    broken = sorted(e for e in all_entries if e not in defined)
    return all_entries, broken


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def line_sha256(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def ledger_append(root: Path, entry: dict) -> None:
    path = root / LEDGER_FILE
    entries = read_ledger(root)
    prev = line_sha256(entries[-1]) if entries else GENESIS
    entry["prev_hash"] = prev
    entry["seq"] = len(entries) + 1
    line = json.dumps(entry, sort_keys=True) + "\n"
    with open(path, "a") as f:
        f.write(line)


def read_ledger(root: Path) -> list:
    path = root / LEDGER_FILE
    if not path.exists():
        return []
    with open(path) as f:
        return [ln for ln in f if ln.strip()]


def verify_ledger(root: Path) -> tuple:
    """Returns (ok, message). Walks the chain; tamper = broken link."""
    lines = read_ledger(root)
    for i, line in enumerate(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            return False, f"corrupt ledger line {i + 1}"
        if i == 0:
            if entry.get("prev_hash") != GENESIS:
                return False, f"genesis line {1} prev_hash != {GENESIS}"
        else:
            if entry.get("prev_hash") != line_sha256(lines[i - 1]):
                return False, f"chain break at line {i + 1} (seq {entry.get('seq')})"
    return True, f"chain OK: {len(lines)} record(s)"


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def validate_candidate(root: Path, registry: dict, entry: dict,
                       candidate: Path) -> tuple:
    """Returns (ok, message). Never writes."""
    if not entry.get("patchable", False):
        return False, (
            f"REFUSED: {entry['name']} is a TRUST module (patchable: false). "
            f"Scouts do not patch trust boundaries. Shepherd-only."
        )
    if not candidate.exists():
        return False, f"candidate not found: {candidate}"

    # syntax
    try:
        ast.parse(candidate.read_text(encoding="utf-8"))
    except SyntaxError as e:
        return False, f"syntax error: {e}"

    # import smoke — stage the candidate UNDER ITS REAL MODULE NAME alongside
    # its sibling modules (core imports integrity/fabrication/geometry
    # via fallback), then import it in isolation.
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            for e in registry.get("modules", []):
                src = module_path(root, e)
                if src.exists():
                    shutil.copy2(src, tmpdir / Path(e["path"]).name)
            mod_name = Path(entry["path"]).stem
            shutil.copy2(candidate, tmpdir / Path(entry["path"]).name)
            subprocess.run(
                [sys.executable, "-c", f"import {mod_name}"],
                cwd=tmp, capture_output=True, timeout=30, check=True,
            )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        detail = getattr(e, "stderr", b"").decode(errors="replace")[-400:]
        return False, f"import smoke failed: {detail.strip()}"

    # public-API surface vs registry
    exports, broken_exports = module_surface(candidate)
    missing = [n for n in api_names(entry) if n not in exports]
    problems = []
    if missing:
        problems.append(
            f"PUBLIC API DRIFT: candidate no longer defines {', '.join(missing)}")
    if broken_exports:
        problems.append(
            f"BROKEN EXPORTS: __all__ names nothing defined: {', '.join(broken_exports)}")
    if problems:
        return False, ". ".join(problems) + ". Changing the public API is forbidden."
    return True, "validation passed (trust gate + syntax + import + public API)"


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_plan(args):
    registry = load_registry(args.root)
    entry = find_module(registry, args.module)
    lines = [
        f"module       : {entry['name']}",
        f"path         : {entry['path']}",
        f"patchable    : {'YES' if entry.get('patchable') else 'NO (TRUST — out of scope)'}",
        f"approval     : {entry.get('approval', 'none')}",
        f"version      : {entry.get('version')}",
        f"role         : {entry.get('role')}",
        f"test gate    : {args.test_cmd}",
        "",
        "public API   :",
    ] + [f"  {n}" for n in api_names(entry)] + [
        "",
        "invariants   :",
    ] + [f"  - {i}" for i in entry.get("invariants", [])] + [
        "",
        "extension points:",
    ] + [f"  - {x}" for x in entry.get("extension_points", [])] + [
        "",
        f"patch policy: {entry.get('patch_policy', 'invariants must hold')}",
    ]
    print("\n".join(lines))


def cmd_validate(args):
    registry = load_registry(args.root)
    entry = find_module(registry, args.module)
    ok, msg = validate_candidate(args.root, registry, entry, args.candidate)
    print(("OK   " if ok else "FAIL ") + msg)
    sys.exit(0 if ok else 1)


def cmd_apply(args):
    registry = load_registry(args.root)
    entry = find_module(registry, args.module)
    live = module_path(args.root, entry)

    ok, msg = validate_candidate(args.root, registry, entry, args.candidate)
    if not ok:
        print("REFUSED: " + msg)
        sys.exit(1)

    if entry.get("approval") == "required" and not args.approved:
        print(f"REFUSED: {entry['name']} requires shepherd/operator approval. "
              f"Re-run with --approved (a deliberate tripwire, not a control — "
              f"the real enforcement is filesystem ownership of trust modules).")
        sys.exit(1)
    if not args.author or not args.reason:
        print("REFUSED: --author and --reason are required (ledger provenance).")
        sys.exit(1)

    # backup
    backups = args.root / BACKUP_DIR
    backups.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    backup = backups / f"{entry['name']}.{stamp}.bak"
    shutil.copy2(live, backup)
    print(f"backup  : {backup}")

    # swap
    shutil.copy2(args.candidate, live)
    new_sha = file_sha256(live)

    # test gate
    gate = subprocess.run(
        args.test_cmd, shell=True, capture_output=True, timeout=args.timeout,
    )
    if gate.returncode != 0:
        shutil.copy2(backup, live)  # ROLL BACK
        tail = (gate.stdout + gate.stderr).decode(errors="replace")[-800:]
        print(f"GATE RED — rolled back to {backup}\n{tail}")
        sys.exit(1)

    # version bump + registry write-back
    try:
        version = int(entry.get("version", 1)) + 1
    except (TypeError, ValueError):
        version = 2
    entry["version"] = str(version)
    for i, mod in enumerate(registry["modules"]):
        if mod["name"] == entry["name"]:
            registry["modules"][i] = entry
    with open(args.root / REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")

    # ledger
    ledger_append(args.root, {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "module": entry["name"],
        "action": "apply",
        "author": args.author,
        "reason": args.reason,
        "version": entry["version"],
        "sha256": new_sha,
        "backup": str(backup.relative_to(args.root)),
    })
    print(f"APPLIED: {entry['name']} v{entry['version']} sha256={new_sha[:12]}... "
          f"gate green, ledger seq {len(read_ledger(args.root))}")
    sys.exit(0)


def cmd_status(args):
    registry = load_registry(args.root)
    lines = read_ledger(args.root)
    last = {}
    for line in lines:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        last[e.get("module")] = f"seq {e.get('seq')} {e.get('ts')} v{e.get('version')}"
    print(f"{'module':<14} {'patchable':<10} {'approval':<10} {'version':<8} last mutation")
    print("-" * 72)
    for entry in registry.get("modules", []):
        print(f"{entry['name']:<14} {str(entry.get('patchable')):<10} "
              f"{entry.get('approval', 'none'):<10} {str(entry.get('version')):<8} "
              f"{last.get(entry['name'], '—')}")
    ok, msg = verify_ledger(args.root)
    print(f"\nledger: {msg}")


def cmd_verify(args):
    ok, msg = verify_ledger(args.root)
    print(("OK   " if ok else "TAMPER ") + msg)
    if ok and len(read_ledger(args.root)) <= 1:
        print("NOTE: single-record ledger — in-place rewrite of the sole record is"
              " not detectable by the chain alone; cross-check sha256 + git diff.")
    sys.exit(0 if ok else 1)


def main():
    parser = argparse.ArgumentParser(description="Scout self-modification gatekeeper")
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="SDK root (default: alongside this script)")
    parser.add_argument("--test-cmd", dest="test_cmd", default=DEFAULT_TEST_CMD,
                        help="test gate command (env SPYGLASS_TEST_CMD overrides)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_plan = sub.add_parser("plan", help="show registry entry for a module")
    p_plan.add_argument("module")

    p_val = sub.add_parser("validate", help="validate a candidate patch (no writes)")
    p_val.add_argument("module")
    p_val.add_argument("candidate", type=Path)

    p_apply = sub.add_parser("apply", help="validate, backup, swap, gate, rollback, record")
    p_apply.add_argument("module")
    p_apply.add_argument("candidate", type=Path)
    p_apply.add_argument("--author", required=False)
    p_apply.add_argument("--reason", required=False)
    p_apply.add_argument("--approved", action="store_true",
                         help="tripwire for approval-required modules")

    sub.add_parser("status", help="registry view + mutation history")
    sub.add_parser("verify", help="verify the mutation ledger chain")

    args = parser.parse_args()
    import os
    args.test_cmd = os.environ.get("SPYGLASS_TEST_CMD", args.test_cmd)
    args.timeout = 300

    try:
        {"plan": cmd_plan, "validate": cmd_validate, "apply": cmd_apply,
         "status": cmd_status, "verify": cmd_verify}[args.cmd](args)
    except SelfModError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()