# Spyglass Scout-Spotter SDK

The core substrate for swarm scouting agents to `spot`, `bid`, `claim`, and `report`.

## Capabilities (2026-09-08 — three layers, not a skeleton)

| Layer | Module | What it does |
|-------|--------|--------------|
| **Integrity** | `sdk/integrity.py` | `CommandGuard` hashes the command path and signs every pheromone with a local HMAC key **before emission** (proof-of-work). Tampered or forged log records fail verification. |
| **Geometry** | `sdk/geometry.py` | `WhorlWeave` gives every scout a position in the weave (ring/phase/helix). `bid()` computes confidence + strength from that geometry via **quadratic dispersion** (`urgency / (1 + k·d²)`) plus **latent state** (health, resource cost, mission priority) — not arrival speed. |
| **Fabrication** | `sdk/fabrication.py` | `FabricationDetector` cross-checks a scout's own pheromone log against the `SyntaxEventBus` log: matched receipts, unmatched (forged) receipts, ghost bus events, signature failures. `Scout.audit_self()` runs it. |

Every capability is a separate module with a versioned public API, documented
invariants, and extension points in **`sdk/module_registry.json`**. That
registry is the self-modification contract: agents may patch module internals
as long as the public API + invariants hold (see the guidance block in the
registry).

## Self-modification (scouts patching their own code)

Full protocol: **`sdk/SELF_MODIFICATION.md`**. The tool: **`sdk/self_mod.py`**.

```bash
python3 sdk/self_mod.py status          # what's patchable, versions, mutations
python3 sdk/self_mod.py plan geometry   # the registry entry: API, invariants, seams
python3 sdk/self_mod.py validate geometry /tmp/geometry_v2.py   # no writes
python3 sdk/self_mod.py apply geometry /tmp/geometry_v2.py \
    --author scout-1 --reason "override dispersion law"          # gate + rollback
python3 sdk/self_mod.py verify          # mutation ledger chain intact?
```

Trust boundary: `integrity.py` is `patchable: false` — scouts cannot patch the
verifier. Every apply is backed up (`backups/`), gated on the full test suite
(automatic rollback on red), version-bumped in the registry, and recorded in a
hash-chained ledger (`MUTATION_LEDGER.jsonl`, local evidence, gitignored).

## Features
- **Canonical Primitive**: `Spotting` dataclass (protobuf-ready) with `signature` + `bus_msg_id` correlation fields.
- **Substrate-Agnostic**: Writes to pheromone logs or pushes to event buses.
- **Geometric Bidding**: `SpottingBoard` resolves conflicts by geometric priority (position + latent state); FCFS is the tie-break only.
- **Proof-of-Work Integrity**: `CommandGuard.sign()` before emit, `CommandGuard.verify()` after — local key at `~/.spyglass/scout_key` (0600) unless one is passed explicitly.
- **Self-Audit**: `Scout.audit_self()` returns a `FabricationReport` (truthy iff consistent).

## Usage
```python
from sdk.spyglass_sdk import Swarm
from sdk.integrity import CommandGuard
from sdk.geometry import WhorlWeave

# One swarm = ONE shared board (the unity line) + weave geometry + integrity
weave = WhorlWeave(["scout-1", "scout-2"], rings={"scout-2": 2})
swarm = Swarm(sink=PheromoneSink(event_bus=bus, guard=CommandGuard(key=b"...")),
              weave=weave)
scout = swarm.add_scout("scout-1", latent={"mission_priority": 0.9})
scout2 = swarm.add_scout("scout-2", latent={"health": 0.6})

s = scout.spot("scout_event", "target_path", {"info": "found something"})
assert scout.sink.guard.verify(s)           # signed before emission

accepted = scout.bid(s)                     # geometric priority, not FCFS
accepted2 = scout2.bid(s)                   # contends on the SAME board
report = scout.audit_self()                 # fabrication cross-check
assert report.consistent
```

## Demo
```bash
python3 sdk/spyglass_sdk.py demo
```
Runs one signed spotting, three weave-aware bids on a single shared board
(displacement included), integrity verification, and a fabrication self-audit.

## Tests
```bash
cd ~ && python3 -m unittest sdk.tests.test_sdk_upgrades -v
```
Covers: sign/verify/tamper, quadratic dispersion, latent-state priority,
geometric displacement, forged-receipt + ghost + signature-failure detection,
and backward compatibility (old `Scout(agent_id, sink)` / `if board.bid(s)`
code keeps working).