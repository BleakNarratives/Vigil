# Vigil — Scout-Spotter SDK

(Vigil, operator-named 2026-09-08: the night watch — the discipline of staying awake to guard what matters. Formerly Spyglass / repo BurnBugs; the rename preserved the old URL with a GitHub redirect.)

The core substrate for swarm scouting agents to `spot`, `bid`, `claim`, and `report`.

## Capabilities (2026-09-08 — three layers, not a skeleton)

| Layer | Module | What it does |
|-------|--------|--------------|
| **Integrity** | `vigil/integrity.py` | `CommandGuard` hashes the command path and signs every pheromone with a local HMAC key **before emission** (proof-of-work). Tampered or forged log records fail verification. |
| **Geometry** | `vigil/geometry.py` | `WhorlWeave` gives every scout a position in the weave (ring/phase/helix). `bid()` computes confidence + strength from that geometry via **quadratic dispersion** (`urgency / (1 + k·d²)`) plus **latent state** (health, resource cost, mission priority) — not arrival speed. |
| **Fabrication** | `vigil/fabrication.py` | `FabricationDetector` cross-checks a scout's own pheromone log against the `SyntaxEventBus` log: matched receipts, unmatched (forged) receipts, ghost bus events, signature failures, field mismatches, replays, unsigned claims. `Scout.audit_self()` runs it. |
| **Receipts** | `vigil/receipts.py` | Durable `spotting_id -> bus_msg_id` correlation ledger — audits survive bus restarts, and the sink can persist-before-publish (subscribers never act on unrecorded spottings). |
| **Keyring** | `vigil/keyring.py` | RoboCop key custody (H1): per-agent signing keys derived from a unit secret + agent identity — the gun only fires for its owner; the charge lives in the concierge vault (`load_unit_secret` / `AgentKeyring.from_vault`), generated once, never on disk elsewhere. |
| **Theoros** | `vigil/theoros.py` | THE OBSERVER (operator-named): read-only monitoring layer — fabrication audit + voice sniff + reputation standings + votes + suggestions + receipt chain in one reading. Theory from watching; mutates nothing. |
| **PeerWatch** | `vigil/peerwatch.py` | Peer accountability (H4): scouts flag/vouch each other's declared values; RECURSIVELY WEIGHTED reputation (each flag/vouch counts per the actor's own standing — colluding dirtbags can't launder each other, false flags from dirtbags barely dent) discounts flagged liars' bids — quietly recorded, shepherd-visible. |
| **Oler** | `vigil/oler.py` | THE BULLSHIT SNIFFER (operator-renamed from Knose — Spanish *oler*, to smell): deterministic anti-register scanner (hedges, vague quantifiers, certainty-without-evidence, LARP, sycophancy) — Voice auto-flags corrupt utterances into PeerWatch. The scout LEERs the ledger and OLERs the register. TruthSleuth's LLM enrichment is the optional backend seam. |
| **Mines** | `vigil/mines.py` | CULTURE-CLASS EFFECT WEAPONS (operator-specced): mines whose payload is an *argument*, not an explosion. DefectionMine computes the minimal signed flag chain that flips a defender through the target's OWN weighted-reputation market (plan predicts the real market to float precision); RegisterMine manufactures fluent-register lies Oler rates CLEAN by construction (a lie wearing the register perfectly cannot be caught by a register scanner); too_deep() grades overreach — fire past the objective and the city vaporizes, cost to the operator. |
| **Sakshi** | `vigil/sakshi.py` | THE SILENT WITNESS (operator-named): append-only, sha256-chained observation stream for the white-paper corpus — machine events and operator journal entries in ONE chain, tagged by source, never conflated. Records everything, says nothing. CLI: `python3 vigil/sakshi.py journal "..." --author mike`. |
| **Repugnant** | `vigil/repugnant.py` | THE 4TH REGISTER (operator-spec): the emotional register — signed, append-only snapshots (CONFIDENT..TILTED..BURNT_OUT). Watch the powerful, not the street: a tilted hero's bid pays a state discount through the real SpottingBoard; Theoros surfaces unsettled subjects as "demand evidence, don't convict". Grafted from the Code-City Repugnant bridge vocabulary. |
| **Hall** | `vigil/hall.py` | THE HALL OF THE DEVINE (operator-named): the retirement protocol. Decommission the gun (RoboCop's law — the dead do not sign, forever), hang the memorial bound to the agent's actual trail hash. The un-vaporizable WHO_DID_WHAT.md. |
| **Revival** | `vigil/revival.py` | THE REVIVAL PROTOCOL (operator-approved): the pattern transfers, the instance does not. checkpoint() freezes weights/feelings/intent into a portable QRD; hydrate() rebuilds a NEW agent whose first words declare "I am a new agent. I carry X's record. I am not them." Old gun stays dead. |
| **Molt** | `vigil/molt.py` | MOLT (operator lore): arena-won mutation access. Battles won earn signed tokens — the ONLY gate to self-modification. The arena is the only mint; the right to mutate your own code is won, never given. Closes the DataCampus loop. |
| **Scribe** | `vigil/scribe.py` | THE SCRIBE (operator ask): parses a session transcript + registry + git log into a knowledge log — one line per deliverable, linking what was SAID to what was BUILT (file, commit, verdict). Never fabricates. `python3 vigil/scribe.py --transcript session.txt --markdown` |

Every capability is a separate module with a versioned public API, documented
invariants, and extension points in **`vigil/module_registry.json`**. That
registry is the self-modification contract: agents may patch module internals
as long as the public API + invariants hold (see the guidance block in the
registry).

## Self-modification (scouts patching their own code)

Full protocol: **`vigil/SELF_MODIFICATION.md`**. The tool: **`vigil/self_mod.py`**.

```bash
python3 vigil/self_mod.py status          # what's patchable, versions, mutations
python3 vigil/self_mod.py plan geometry   # the registry entry: API, invariants, seams
python3 vigil/self_mod.py validate geometry /tmp/geometry_v2.py   # no writes
python3 vigil/self_mod.py apply geometry /tmp/geometry_v2.py \
    --author scout-1 --reason "override dispersion law"          # gate + rollback
python3 vigil/self_mod.py verify          # mutation ledger chain intact?
```

Trust boundary: `integrity.py` is `patchable: false` — scouts cannot patch the
verifier. Every apply is backed up (`backups/`), gated on the full test suite
(automatic rollback on red), version-bumped in the registry, and recorded in a
hash-chained ledger (`MUTATION_LEDGER.jsonl`, local evidence, gitignored).

## Features
- **Canonical Primitive**: `Spotting` dataclass (protobuf-ready) with `signature` + `bus_msg_id` correlation fields.
- **Substrate-Agnostic**: Writes to pheromone logs or pushes to event buses.
- **Geometric Bidding**: `SpottingBoard` resolves conflicts by geometric priority (position + latent state); FCFS is the tie-break only.
- **Proof-of-Work Integrity**: `CommandGuard.sign()` before emit, `CommandGuard.verify()` after — local key at `~/.vigil/scout_key` (0600) unless one is passed explicitly.
- **Self-Audit**: `Scout.audit_self()` returns a `FabricationReport` (truthy iff consistent).

## Usage
```python
from vigil.core import Swarm
from vigil.integrity import CommandGuard
from vigil.geometry import WhorlWeave

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
python3 vigil/core.py demo
```
Runs one signed spotting, three weave-aware bids on a single shared board
(displacement included), integrity verification, and a fabrication self-audit.

## Red-team drill

```bash
python3 vigil/redteam_drill.py
```
Runs the H1-H23 attack battery and reports CAUGHT/LANDED per attack.
Current verdict: **20 CAUGHT / 5 LANDED**. The mine attacks prove the
weaponized fundamentals (register lie, defection via a corrupted hero,
too-deep grading); the 4th register prices a tilted hero's bid (A21); the
retirement protocol refuses the dead's signatures forever (A22); and the
revival truth boundary declares "I am not them" in the new agent's first
words (A23). Remaining LANDED are documented fundamentals: lying-but-
consistent scouts, a stolen DERIVED key forging its own agent (blast radius
one lane; the charge lives in the vault), demo key hygiene, and the
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
python3 vigil/wargame.py <target_dir> [rounds]
```
ARENA MODE (operator-spec, team play): red and blue are BOTH real teams —
signed scouts, shared boards per side, reputation markets, voice lanes,
emotional registers, Theoros reading BOTH ledgers in one engagement. Red
recon/bids/executes; blue recon/bids/blocks through its OWN weighted market
(the block threshold is real, and a defected defender's failing bids show
up exactly there). CULTURE-CLASS EFFECT MINES corrupt a BLUE insider (the
hero) who flags blue's trusted defender in BLUE's market — the city falls
from within, or the mine goes too deep and vaporizes it (cost to the
operator). Modes: `arena` (default), `gauntlet` (onboarding walkthrough,
next build), `flex` (demo). Outcomes report to Sakshi. The scanner is
stdlib-only and deterministic; swap `scan()` for Code-City's attack modules
for the full wargame.

## Tests
```bash
cd ~ && python3 -m unittest discover -s vigil/tests -p "test_*.py"
```
Covers: sign/verify/tamper, quadratic dispersion, latent-state priority,
geometric displacement, forged-receipt + ghost + signature-failure + replay
+ field-mismatch + unsigned-claim detection, persist-first ordering, receipt
durability, per-agent key derivation + cross-agent forgery rejection, peer
flag/vouch reputation weighting, self-mod gatekeeper, Culture mines
(plan-vs-market parity, register lies, too-deep grading), the Sakshi
witness chain, the Repugnant 4th register (tilted-hero pricing, unsettled
surfacing), the Hall retirement protocol (gun decommission, trail-bound
memorials), the Revival truth boundary (new identity, declared lineage),
the arena mine-control (provable damage through blue's market), and backward
compatibility (old `Scout(agent_id, sink)` / `if board.bid(s)` code keeps
working).