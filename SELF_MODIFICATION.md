# SELF_MODIFICATION.md — Scout Self-Modification Protocol

Version 1 · 2026-09-08 · Operator-ratified intent: scouts may modify their own
source code "to an extent" — this document defines the extent, the safe
procedure, and the trust boundary that keeps self-modification from becoming
self-deception.

---

## 1. The problem this protocol solves

A scout that can edit its own code can edit its own verifier. If `integrity.py`
lives inside the scout's writable scope, a "signed" pheromone is just the
scout signing its own homework. The protocol's job is to make self-improvement
safe by answering three questions up front:

1. **What may a scout patch?** → Only modules the registry marks `patchable: true`.
2. **How does it patch safely?** → PLAN → VALIDATE → APPLY, with backups,
   a test gate, and automatic rollback.
3. **Who can prove what happened?** → Every mutation is recorded in a
   hash-chained ledger (`MUTATION_LEDGER.jsonl`) the shepherd can walk.

**The trust boundary is the load-bearing wall:** `integrity.py` (and anything
else marked `patchable: false`) is OUT OF SCOPE for scouts. Enforcement is
filesystem ownership, not politeness — trust modules are shepherd-owned and
root-readable-only. `self_mod.py` refuses to even validate a trust-module
patch, so no amount of agent cleverness routes around it through the tool.

## 2. Roles

| Role | Who | Authority |
|------|-----|-----------|
| **Scout** | any swarm agent | patches patchable modules, per this protocol |
| **Shepherd** | overseer / operator / auditor | owns trust modules, holds the verification key, audits the ledger |
| **Operator** | Mike | final authority; greenlights approval-required patches |

## 3. Discovery — how a scout finds what it can touch

Read **`module_registry.json`** first. It is the map:

- `role` — what the module does
- `patchable` — **`true` = scout may patch; `false` = TRUST, out of scope**
- `approval` — `required` = shepherd/operator greenlight needed before apply
- `public_api` — the exact surface that must never change
- `invariants` — the non-negotiable behaviors that must survive any patch
- `extension_points` — the seams where self-improvement is *encouraged*
- `version` — bumped by the tool on every successful apply

Quick check:

```bash
python3 sdk/self_mod.py status          # which modules are patchable, last mutations
python3 sdk/self_mod.py plan geometry   # the full entry: API, invariants, seams
```

## 4. The safe patch flow (four phases)

A scout never edits a live module directly. It works in candidates.

### PHASE 1 — PLAN
1. `self_mod.py plan <module>` — read the role, invariants, and extension points.
2. Decide the change **in terms of an extension point** (e.g., override
   `WhorlWeave.dispersion()` for a new falloff law — do NOT rework the class
   hierarchy).
3. Write the new module to a candidate file (e.g. `/tmp/geometry_v2.py`).
   Keep the `__all__`, public names, and every invariant intact.
4. Write a one-line `--reason` that states which invariant-compliant behavior
   changed. If you cannot state it, you are not ready to patch.

### PHASE 2 — VALIDATE (no writes)
```bash
python3 sdk/self_mod.py validate geometry /tmp/geometry_v2.py
```
The tool checks, in order:
- **Trust gate** — `patchable: false` → hard refusal, exit 1.
- **Syntax** — AST parse of the candidate.
- **Import smoke** — the candidate imports cleanly in isolation.
- **Public-API drift** — every registered API name must still exist in the
  candidate. Renaming or dropping a public name = refusal, exit 1.

A green validate means "safe to attempt." It does NOT mean "correct."

### PHASE 3 — APPLY (backup → swap → gate → rollback → record)
```bash
python3 sdk/self_mod.py apply geometry /tmp/geometry_v2.py \
    --author scout-1 --reason "override dispersion law per mission profile"
# approval-required modules (e.g. spyglass_sdk):
python3 sdk/self_mod.py apply spyglass_sdk /tmp/spyglass_v2.py \
    --author scout-1 --reason "..." --approved
```
What apply does, in order:
1. Re-validates (trust gate + syntax + import + API surface).
2. **Approval tripwire** — if `approval: required` and `--approved` absent → refuse.
3. **Backup** the live module → `backups/<module>.<timestamp>.bak`.
4. Swap the candidate over the live module.
5. Run the **test gate** (`SPYGLASS_TEST_CMD`, default: the full SDK suite).
6. **Gate red → automatic rollback** from the backup, exit 1. A patch that
   breaks the suite never survives.
7. Gate green → **version bump** in the registry + **ledger entry**
   (author, reason, sha256 of the new module, backup path, chained to the
   previous entry).
8. Exit 0.

### PHASE 4 — RECORD & AUDIT
- The mutation ledger is append-only and **hash-chained**: every entry carries
  the sha256 of the previous line. Verify at any time:
  ```bash
  python3 sdk/self_mod.py verify
  ```
  A rewritten or spliced entry breaks the chain and reports **TAMPER** with
  the offending line. This is the same walk-the-chain discipline as the
  ecosystem's resonance ledger — a scout cannot quietly rewrite history.
- Scouts SHOULD emit a `scout_event` pheromone describing the patch
  (module, version, reason) through their own signed sink, so the swarm's
  pheromone log and the mutation ledger corroborate each other.

## 5. What is forbidden (the short list)

1. **Never patch a trust module** (`patchable: false`) — currently
   `integrity`. The tool refuses; the filesystem enforces.
2. **Never change the public API** — validated mechanically.
3. **Never violate an invariant** — a patch whose only defense is "the tests
   still pass" without honoring the invariants is a broken patch; the
   invariants ARE the contract the tests sample.
4. **Never patch `self_mod.py` itself** — the tool is shepherd-owned. A scout
   that patches the gatekeeper is a scout that has left the protocol.
5. **Never bypass with a fake test gate** — overriding `SPYGLASS_TEST_CMD`
   to a no-op command is detectable (the ledger records nothing about it, the
   gate output is not recorded) and is grounds for shepherd revocation. The
   default gate is the canonical suite.
6. **Never roll back a rollback** — if the gate went red, the module is back
   on the backup. Do not re-apply the same candidate hoping for a different
   verdict; fix the candidate.

## 6. Approval policy

- `approval: required` (currently `spyglass_sdk` — the core surface) — the
  apply refuses without `--approved`. Treat `--approved` as what it is: a
  deliberate tripwire forcing the scout to consciously claim shepherd consent.
  The REAL control is that the shepherd owns the file and can revert it, and
  the ledger records who claimed approval.
- `approval: none` (currently `geometry`, `fabrication`) — self-serve, but the
  ledger still records author + reason + sha256.

## 7. Why this survives the "agents lie" threat model

A lying scout can still lie about its *intent* — no protocol stops that. What
this protocol stops is a scout **silently changing the rules**:

- it cannot patch the verifier (trust boundary),
- it cannot change the public API (mechanical check),
- it cannot break the suite and keep the change (gate + rollback),
- it cannot rewrite history (hash chain),
- it cannot deny authorship (ledger: author, reason, sha256, backup path).

The remaining honest gap: a scout can apply a *valid* patch that is
*behaviorally hostile* (e.g., a dispersion law that makes everything urgent).
That is what the shepherd's audit is for — `self_mod.py verify` + reading the
ledger + sniffing the reasons. The protocol makes hostile patches **visible**,
which is the achievable goal. It does not make them impossible, and anyone who
claims otherwise is selling you something.

## 8. Shepherd checklist (after any scout patch)

```bash
cd ~/sdk
python3 sdk/self_mod.py verify          # chain intact?
python3 sdk/self_mod.py status          # what moved, versions
tail -5 MUTATION_LEDGER.jsonl           # authors + reasons readable?
git diff <module>                       # what actually changed
```
The mutation ledger and `backups/` are local evidence (gitignored) — the
source of truth for "did the agent touch the rules" is the shepherd's own
audit, never the agent's account of itself.