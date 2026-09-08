# Spyglass Scout-Spotter SDK

The core substrate for swarm scouting agents to `spot`, `bid`, `claim`, and `report`.

## Capabilities (2026-09-08 — three layers, not a skeleton)

| Layer | Module | What it does |
|-------|--------|--------------|
| **Integrity** | `sdk/integrity.py` | `CommandGuard` hashes the command path and signs every pheromone with a local HMAC key **before emission** (proof-of-work). Tampered or forged log records fail verification. |
| **Geometry** | `sdk/geometry.py` | `WhorlWeave` gives every scout a position in the weave (ring/phase/helix). `bid()` computes confidence + strength from that geometry via **quadratic dispersion** (`urgency / (1 + k·d²)`) plus **latent state** (health, resource cost, mission priority) — not arrival speed. |
| **Fabrication** | `sdk/fabrication.py` | `FabricationDetector` cross-checks a scout's own pheromone log against the `SyntaxEventBus` log: matched receipts, unmatched (forged) receipts, ghost bus events, signature failures, field mismatches, replays, unsigned claims. `Scout.audit_self()` runs it. |
| **Receipts** | `sdk/receipts.py` | Durable `spotting_id -> bus_msg_id` correlation ledger — audits survive bus restarts, and the sink can persist-before-publish (subscribers never act on unrecorded spottings). |
| **Keyring** | `sdk/keyring.py` | RoboCop key custody (H1): per-agent signing keys derived from a unit secret + agent identity — the gun only fires for its owner; the charge lives in the concierge vault (`load_unit_secret` / `AgentKeyring.from_vault`), generated once, never on disk elsewhere. |
| **Theoros** | `sdk/theoros.py` | THE OBSERVER (operator-named): read-only monitoring layer — fabrication audit + voice sniff + reputation standings + votes + suggestions + receipt chain in one reading. Theory from watching; mutates nothing. |
| **PeerWatch** | `sdk/peerwatch.py` | Peer accountability (H4): scouts flag/vouch each other's declared values; RECURSIVELY WEIGHTED reputation (each flag/vouch counts per the actor's own standing — colluding dirtbags can't launder each other, false flags from dirtbags barely dent) discounts flagged liars' bids — quietly recorded, shepherd-visible. |
| **Knose** | `sdk/knose.py` | THE BULLSHIT SNIFFER: deterministic anti-register scanner (hedges, vague quantifiers, certainty-without-evidence, LARP, sycophancy) — Voice auto-flags corrupt utterances into PeerWatch. TruthSleuth's LLM enrichment is the optional backend seam. |
| **Mines** | `sdk/mines.py` | CULTURE-CLASS EFFECT WEAPONS (operator-specced): mines whose payload is an *argument*, not an explosion. DefectionMine computes the minimal signed flag chain that flips a defender through the target's OWN weighted-reputation market (plan predicts the real market to float precision); RegisterMine manufactures fluent-register lies Knose rates CLEAN by construction (a lie wearing the register perfectly cannot be caught by a register scanner); too_deep() grades overreach — fire past the objective and the city vaporizes, cost to the operator. |
| **Sakshi** | `sdk/sakshi.py` | THE SILENT WITNESS (operator-named): append-only, sha256-chained observation stream for the white-paper corpus — machine events and operator journal entries in ONE chain, tagged by source, never conflated. Records everything, says nothing. CLI: `python3 sdk/sakshi.py journal "..." --author mike`. |

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

## Red-team drill

```bash
python3 sdk/redteam_drill.py
```
Runs the H1-H20 attack battery and reports CAUGHT/LANDED per attack.
Current verdict: **17 CAUGHT / 5 LANDED**. The three mine attacks prove
the weaponized fundamentals: the register mine (a lie wearing the register
perfectly reads CLEAN to Knose by construction — CLEAN means 'no register
violations', not 'true'); the defection mine (a corrupted high-standing
informant flips the most trusted defender through the real market — the
citizenry defects because their OWN ledger convicts them); and the too-deep
grade (firing past the objective vaporizes the city and costs the operator
— 'whoops, too deep'). Remaining LANDED are documented fundamentals: lying-
but-consistent scouts, a stolen DERIVED key forging its own agent (blast
radius one lane; the charge lives in the vault), demo key hygiene, and the
register mine itself.

## Naming (operator-picked, 2026-09-08)

- **Theoros** — the observer that produces understanding (theory from
  watching). The read-only monitoring layer's face.
- **Sakshi** — the silent witness: sees everything, touched by nothing,
  never the actor. The record-side counterpart to Theoros.
- **Leer** — Spanish for *to read* (leer): the reader lens — reading the
  register, the ledger, the register. The scout posture.

## Wargame (scouts as the red team's scouting arm)

```bash
python3 sdk/wargame.py <target_dir> [rounds]
```
Scouts recon a target corpus for real vulnerability patterns (subprocess
shell, eval/exec, pickle, yaml.load, md5, hardcoded secrets, insecure
random), bid on findings geometrically on ONE shared board, the red team
executes, the blue team blocks deterministically, and Theoros observes the
transcript — every move signed, ledgered, and auditable. Red can also field
CULTURE-CLASS EFFECT MINES between rounds: a defection payload computed
from blue's own reputation market flips the most trusted defender; the blast
grade lands CLEAN (worked as intended), OVERKILL, or TOO_DEEP (the city
vaporizes, cost to the operator). Outcomes report to Sakshi. The scanner is
stdlib-only and deterministic; swap `scan()` for Code-City's attack modules
for the full wargame.

## Tests
```bash
cd ~ && python3 -m unittest sdk.tests.test_sdk_upgrades sdk.tests.test_self_mod sdk.tests.test_mines sdk.tests.test_sakshi -v
```
Covers: sign/verify/tamper, quadratic dispersion, latent-state priority,
geometric displacement, forged-receipt + ghost + signature-failure + replay
+ field-mismatch + unsigned-claim detection, persist-first ordering, receipt
durability, per-agent key derivation + cross-agent forgery rejection, peer
flag/vouch reputation weighting, self-mod gatekeeper, Culture mines
(plan-vs-market parity, register lies, too-deep grading), the Sakshi
witness chain (tamper, corrupt-tail refusal, operator/machine streams), and
backward compatibility (old `Scout(agent_id, sink)` / `if board.bid(s)`
code keeps working).