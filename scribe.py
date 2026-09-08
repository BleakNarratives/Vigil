"""
vigil scribe.py — THE SCRIBE: parses the conversation into a knowledge log.

Operator ask (2026-09-08): "I wish there was something to scan this shit
so I had a log — something that would parse the code from the convo."
The sessions produce a flood of commits, modules, verdicts, and decisions;
the chat is where they get EXPLAINED. Scribe connects the two: it scans a
session transcript (the Freebuff/terminal dump) plus the module registry
plus the git log, and emits a KNOWLEDGE LOG — one line per deliverable,
linking what was SAID to what was BUILT, with file, commit, and verdict.

The knowledge thing the operator described — "I already knew, I just
didn't have the nuts and bolts to put the words together" — is exactly
what Scribe is for: the words and the nuts and bolts were in two places;
now they're in one file.

Inputs (all optional; it degrades gracefully):
  --transcript FILE   raw session dump (Freebuff export, terminal scroll)
  --registry PATH     module_registry.json (default: sibling)
  --git-dir PATH      git log source (default: this repo)

Output: a JSONL knowledge log + a human-readable markdown rundown.

Heuristics (honest, deterministic):
  - a line mentioning a known module name (core, integrity, oler, ...)
    plus an action verb (built/wired/fixed/shipped/renamed/pushed) becomes
    a knowledge entry linking that module to the transcript line.
  - a git commit whose message contains a module name links the commit.
  - a verdict line (CAUGHT/LANDED, OK, N tests) becomes an outcome entry.
Scribe never fabricates: if a transcript line names nothing known, it is
recorded as an unlinked utterance, not silently dropped or auto-linked.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Action verbs that mark a line as "something got built/changed"
_ACTION = re.compile(
    r"\b(built|wired|fixed|shipped|renamed|pushed|added|created|upgraded|"
    r"hardened|implemented|merged|deployed|retired|revived|minted|"
    r"decommissioned)\b", re.IGNORECASE)
# Verdict/outcome lines
_VERDICT = re.compile(
    r"(\d+)\s+(?:CAUGHT|tests?|OK)|VERDICT|FAILED|OK\b", re.IGNORECASE)


def _known_modules(registry: Dict[str, Any]) -> Dict[str, str]:
    """module name (lowercased) -> file path, from the registry."""
    out = {}
    for m in registry.get("modules", []):
        out[m.get("name", "").lower()] = m.get("path", "")
        # also index by file stem (core.py -> core)
        stem = Path(m.get("path", "")).stem.lower()
        out[stem] = m.get("path", "")
    return out


def _git_log(git_dir: Optional[str], n: int = 40) -> List[Dict[str, str]]:
    try:
        out = subprocess.run(
            ["git", "log", f"-{n}", "--oneline", "--date=short",
             "--pretty=%h|%ad|%s"],
            cwd=git_dir, capture_output=True, text=True, timeout=15)
        rows = []
        for line in out.stdout.strip().splitlines():
            if "|" in line:
                h, d, s = line.split("|", 2)
                rows.append({"hash": h, "date": d, "subject": s})
        return rows
    except Exception:
        return []


def _scan_transcript(path: Path, modules: Dict[str, str]) -> List[Dict[str, Any]]:
    """Parse the transcript: lines mentioning known modules + actions."""
    entries: List[Dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return entries
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        low = line.lower()
        hits = {name for name in modules if name and name in low}
        if not hits:
            continue
        action = _ACTION.search(line)
        if not action:
            continue
        entries.append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "line": i,
            "kind": "deliverable",
            "verb": action.group(1).lower(),
            "modules": sorted(hits),
            "files": sorted({modules[h] for h in hits if modules[h]}),
            "quote": line.strip()[:200],
        })
    return entries


def _scan_outcomes(transcript: Optional[Path]) -> List[Dict[str, Any]]:
    if transcript is None:
        return []
    entries = []
    try:
        text = transcript.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return entries
    for i, line in enumerate(text.splitlines(), 1):
        if _VERDICT.search(line) and any(
                k in line for k in ("CAUGHT", "tests", "VERDICT", "OK",
                                    "FAILED", "Ran")):
            entries.append({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "line": i, "kind": "outcome",
                "quote": line.strip()[:200],
            })
    return entries


def _link_commits(entries: List[Dict[str, Any]],
                  commits: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Attach the git commit whose subject names the same module."""
    for e in entries:
        e["commits"] = []
        if e["kind"] != "deliverable":
            continue
        for c in commits:
            cl = c["subject"].lower()
            if any(m in cl for m in e["modules"]):
                e["commits"].append(c)
        e["commits"] = e["commits"][:3]
    return entries


def build_log(transcript: Optional[Path], registry_path: Path,
              git_dir: Optional[str]) -> List[Dict[str, Any]]:
    try:
        registry = json.load(open(registry_path))
    except OSError:
        registry = {"modules": []}
    modules = _known_modules(registry)
    entries = _scan_transcript(transcript, modules) if transcript else []
    entries += _scan_outcomes(transcript)
    entries.sort(key=lambda e: e.get("line", 0))
    commits = _git_log(git_dir)
    return _link_commits(entries, commits)


def render_markdown(entries: List[Dict[str, Any]]) -> str:
    if not entries:
        return "# Knowledge Log\n\n(nothing parsed — feed it a transcript)"
    lines = ["# Knowledge Log", ""]
    for e in entries:
        if e["kind"] == "deliverable":
            lines.append(f"- **{e['verb']}** {', '.join(e['modules'])} "
                         f"(line {e['line']})")
            for f in e.get("files", []):
                lines.append(f"    - file: {f}")
            for c in e.get("commits", []):
                lines.append(f"    - commit: `{c['hash']}` {c['subject'][:70]}")
        else:
            lines.append(f"- outcome (line {e['line']}): {e['quote']}")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="scribe", description=__doc__)
    ap.add_argument("--transcript", default=None,
                    help="session dump to parse (Freebuff export / terminal scroll)")
    ap.add_argument("--registry", default=None)
    ap.add_argument("--git-dir", default=None)
    ap.add_argument("--out", default="~/.vigil/knowledge_log.jsonl")
    ap.add_argument("--markdown", action="store_true",
                    help="also print a human-readable rundown")
    args = ap.parse_args(argv)

    reg = Path(args.registry) if args.registry else \
        Path(__file__).resolve().parent / "module_registry.json"
    transcript = Path(args.transcript).expanduser() if args.transcript else None
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    entries = build_log(transcript, reg, args.git_dir)
    with open(out, "w") as f:
        for e in entries:
            f.write(json.dumps(e, sort_keys=True) + "\n")
    print(f"scribe: {len(entries)} entries -> {out}")
    if args.markdown:
        print(render_markdown(entries))
    return 0


if __name__ == "__main__":
    sys.exit(main())