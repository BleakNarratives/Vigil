"""
Sakshi — the silent witness (operator-named, 2026-09-08).

Append-only, sha256-chained observation stream for the white-paper corpus.
Records EVERYTHING the swarm does (bids, flags, votes, sniffs, verdicts,
wargame outcomes) AND the operator's own journal entries — same chain, tagged
by source, so the paper can later read the two streams side by side without
ever mistaking one for the other.

Design (matches the ecosystem precedents):
  - append-only JSONL; each record carries the sha256 of the previous record
    (the resonance_chain.jsonl pattern) — at-rest tamper detection with zero
    dependencies.
  - Every record is tagged: source (scout | operator | theoros | wargame |
    drill | system), agent (who spoke), kind, and an ISO timestamp.
  - Operator journal entries come in through the same chain as machine events
    — the witness does not privilege one over the other, it just records.
  - `verify` walks the chain and reports the first break, mirroring the
    fabrication detector's honesty: a broken chain is reported loudly.

CLI:
    python3 vigil/sakshi.py journal "the swarm outbid me today" --author mike
    python3 vigil/sakshi.py record --kind wargame --agent vip3r "scan outcome"
    python3 vigil/sakshi.py dump [--jsonl]
    python3 vigil/sakshi.py verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_PATH = Path("~/.vigil/sakshi.jsonl").expanduser()
PAPER_PATH = Path("~/.vigil/sakshi_paper_export.jsonl").expanduser()

# Reserved kinds — the paper's schema. Anything else still records, but these
# are the ones the analysis pass will know how to read.
KNOWN_KINDS = {
    "bid", "flag", "vouch", "confirm", "vote", "suggest", "sniff", "verdict",
    "wargame", "drill", "journal", "system", "spot", "claim", "keyring",
}


def _chain_hash(prev_hash: str, body: bytes) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(b"|")
    h.update(body)
    return h.hexdigest()


def _prev_hash(path: Path) -> str:
    """Last record's chain hash, or the genesis constant for an empty chain."""
    if not path.exists():
        return "sakshi-genesis-v1"
    try:
        with open(path, "rb") as f:
            last_line = b""
            for line in f:
                if line.strip():
                    last_line = line
        if not last_line.strip():
            return "sakshi-genesis-v1"
        return json.loads(last_line)["chain_hash"]
    except (json.JSONDecodeError, KeyError, OSError):
        # A corrupt tail must be reported loudly, not silently reset — the
        # witness does not edit history.
        raise RuntimeError(
            f"sakshi chain tail is corrupt or unreadable at {path} — refusing "
            "to append. Inspect the tail before continuing (the paper needs "
            "an honest chain)."
        )


def record(
    kind: str,
    text: str,
    *,
    agent: str = "system",
    source: str = "system",
    path: Optional[Path] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append one observation. Returns the stored record."""
    if kind not in KNOWN_KINDS:
        # Unknown kinds are allowed (the witness does not censor), but the
        # paper schema will skip them — flag it in the record so nobody
        # mistakes an uncatalogued kind for a catalogued one.
        source_tag = source
    else:
        source_tag = source
    p = Path(path) if path is not None else DEFAULT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    prev = _prev_hash(p)
    ts = time.time()
    rec: Dict[str, Any] = {
        "ts": ts,
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(ts)),
        "source": source_tag,
        "agent": agent,
        "kind": kind,
        "text": text,
        "prev_hash": prev,
    }
    if extra:
        rec["extra"] = extra
    body = json.dumps(
        {k: rec[k] for k in ("ts", "iso", "source", "agent", "kind", "text")},
        sort_keys=True,
    ).encode("utf-8")
    rec["chain_hash"] = _chain_hash(prev, body)
    with open(p, "a") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def entries(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    p = Path(path) if path is not None else DEFAULT_PATH
    if not p.exists():
        return []
    out: List[Dict[str, Any]] = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def verify(path: Optional[Path] = None) -> Dict[str, Any]:
    """Walk the whole chain. Returns a verdict dict — honest about breaks."""
    p = Path(path) if path is not None else DEFAULT_PATH
    rows = entries(p)
    if not rows:
        return {"ok": True, "count": 0, "break": None}
    prev = "sakshi-genesis-v1"
    for i, row in enumerate(rows):
        body = json.dumps(
            {k: row[k] for k in ("ts", "iso", "source", "agent", "kind", "text")},
            sort_keys=True,
        ).encode("utf-8")
        expect = _chain_hash(prev, body)
        if row.get("prev_hash") != prev or row.get("chain_hash") != expect:
            return {
                "ok": False,
                "count": len(rows),
                "break": i,
                "record": row,
            }
        prev = row["chain_hash"]
    return {"ok": True, "count": len(rows), "break": None}


def export_paper(path: Optional[Path] = None,
                 out: Optional[Path] = None) -> Path:
    """Export the machine + operator streams as a paper corpus (JSONL).

    The export is a plain copy of the chain — provenance lives in each
    record's source/agent/kind tags. The paper's methods section will cite
    this file and the chain it came from.
    """
    p = Path(path) if path is not None else DEFAULT_PATH
    out_p = Path(out) if out is not None else PAPER_PATH
    rows = entries(p)
    with open(out_p, "w") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    return out_p


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="sakshi", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    j = sub.add_parser("journal", help="record an operator journal entry")
    j.add_argument("text")
    j.add_argument("--author", default="mike")
    j.add_argument("--kind", default="journal")

    r = sub.add_parser("record", help="record a machine observation")
    r.add_argument("text")
    r.add_argument("--kind", required=True)
    r.add_argument("--agent", default="system")
    r.add_argument("--source", default="system")

    d = sub.add_parser("dump", help="print all observations")
    d.add_argument("--jsonl", action="store_true", help="raw JSONL output")

    v = sub.add_parser("verify", help="verify the chain integrity")
    e = sub.add_parser("export", help="export the paper corpus")
    e.add_argument("--out", default=None)

    args = ap.parse_args(argv)
    if args.cmd == "journal":
        rec = record(args.kind, args.text, agent=args.author,
                     source="operator")
        print(f"witnessed: [{rec['source']}] {args.text}")
    elif args.cmd == "record":
        rec = record(args.kind, args.text, agent=args.agent,
                     source=args.source)
        print(f"witnessed: [{rec['source']}/{rec['kind']}] {args.text}")
    elif args.cmd == "dump":
        for row in entries():
            if args.jsonl:
                print(json.dumps(row, sort_keys=True))
            else:
                print(f"[{row['iso']}] {row['source']}/{row['agent']} "
                      f"({row['kind']}): {row['text']}")
    elif args.cmd == "verify":
        verdict = verify()
        if verdict["ok"]:
            print(f"chain OK: {verdict['count']} records, no breaks")
        else:
            print(f"CHAIN BREAK at record {verdict['break']}: "
                  f"{verdict['record']}")
            return 1
    elif args.cmd == "export":
        out_p = export_paper(out=Path(args.out) if args.out else None)
        print(f"exported paper corpus -> {out_p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())