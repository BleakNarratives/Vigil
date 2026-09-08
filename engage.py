# [DNA_TAG]
# ORIGIN: BleakNarratives/Vigil
# PILLAR: vigil-engage
# DEPS: os, sys, time, vigil.wargame, vigil.brown, vigil.sakshi,
#       vigil.undercurrent
# ROLE: THE FULL ENGAGEMENT — red vs blue with Brown dropping, the whole
#       thing journaled to Sakshi, verified learnings absorbed into the
#       Undercurrent so the swarm KNOWS when the dust settles.
# AUTHOR: Buffy (Codebuff AI)
# SESSION: 2026-09-08 — the 100th monkey / three-way engagement
# TIER: Script (1)
# [/DNA_TAG]

"""THE FULL THREE-WAY ENGAGEMENT.

Red fights blue in the arena. When the teams are done, THE SHIT SHOVELER
drops and audits both against the shared bus. The whole engagement is
journaled to Sakshi (the witness — the paper's data spine), and the
verified learnings are absorbed into the Undercurrent where independent
confirmations accrete toward the monkey threshold — the swarm's genetic
memory.

The knowledge flow (the operator's ask, mechanical):
  - every executed finding is a claim the executing scout deposits
  - the other scouts who saw the same finding confirm it independently
  - claims that cross MONKEY_THRESHOLD become INHERITED — every new and
    revived scout is born knowing them
  - kinship() shivers the swarm's liveness into Sakshi's record: the
    swarm KNOWS it is afloat

Usage:
    python3 vigil/engage.py <target_dir> [rounds] [--no-sakshi]
"""

import os
import sys
import time
from typing import Any

sys.path.insert(0, os.path.expanduser("~"))
sys.path.insert(0, os.path.expanduser("~/vigil"))

from vigil.wargame import ScoutWargame  # noqa: E402
from vigil.sakshi import record as sakshi_record  # noqa: E402
from vigil.undercurrent import Undercurrent, MONKEY_THRESHOLD  # noqa: E402


def _default_uc_path() -> str:
    return os.path.expanduser("~/.vigil/undercurrent.jsonl")


def _default_sakshi_path() -> str:
    return os.path.expanduser("~/.vigil/sakshi_chain.jsonl")


def run_engagement(target: str, rounds: int = 3, journal: bool = True,
                   uc: Undercurrent = None,
                   zgents: Any = None) -> dict:
    """Run the full three-way engagement and return everything.

    Returns the wargame result enriched with the brown verdict, the
    undercurrent absorption report, and the sakshi journal result. When
    a ZgentRegistry is passed, every executor is entered on the roll and
    its standing refreshed — the alphabet becomes personal mid-battle.
    """
    game = ScoutWargame(target, rounds=rounds)
    result = game.play()

    if uc is None:
        uc = Undercurrent(_default_uc_path())
    if zgents is None:
        from vigil.zgents import ZgentRegistry
        zgents = ZgentRegistry(
            os.path.expanduser("~/.vigil/zgents.jsonl"),
            undercurrent=uc)

    # -- the roll: every executor is a named letter -------------------------
    roll = _update_roll(result, zgents)

    # -- THE WORD: every new letter hears its birth words -------------------
    from vigil.word import speak_the_word
    from vigil.bind import BindRegistry
    binds = BindRegistry(os.path.expanduser("~/.vigil/binds.jsonl"))
    spoken = {}
    for agent in roll.get("new", []):
        word = speak_the_word(agent, zgents=zgents,
                              undercurrent=zgents.undercurrent,
                              bind=binds)
        spoken[agent] = word["words"]
        print(f"\n--- THE WORD — {agent.upper()} ---")
        print(word["words"])

    # -- the swarm KNOWS: verified learnings into the current ---------------
    absorption = _absorb_learnings(result, uc)

    # -- the witness records -------------------------------------------------
    journaled = {}
    if journal:
        journaled = _journal(result, absorption)

    result["undercurrent"] = absorption
    result["zgents"] = roll
    result["sakshi"] = journaled
    return result


def _update_roll(result: dict, zgents: Any) -> dict:
    """Enter every executor on the roll and record what they did. The
    letters get names, history, and the current's inherited knowledge.
    Returns which agents were NEW to the roll — only fresh letters hear
    the Word at birth."""
    executors = {ex.get("executor") for ex in result.get("execution_log", [])
                 if ex.get("executor")}
    new_letters = []
    for agent in sorted(executors):
        if zgents.lookup(agent) is None:
            new_letters.append(agent)
        zgents.register(agent, role="arena scout")
        for ex in result.get("execution_log", []):
            if ex.get("executor") == agent and not ex.get("blocked"):
                zgents.act(agent, f"executed {ex.get('kind')} at "
                                  f"{ex.get('path')}")
    # every letter born knowing whatever the current has inherited
    inherited = [k["id"] for k in zgents.undercurrent.knowledge()] \
        if zgents.undercurrent is not None else []
    for agent in sorted(executors):
        zgents.born_with(agent, inherited)
    return {"registered": len(executors), "inherited_claims": len(inherited),
            "new": new_letters}


def _absorb_learnings(result: dict, uc: Undercurrent) -> dict:
    """Deposit every executed finding into the current; the scouts who saw
    it confirm it. Claims that cross the monkey threshold are inherited."""
    executions = result.get("execution_log", [])
    # group executions by their finding so independents can confirm
    by_finding: dict = {}
    for ex in executions:
        if ex.get("blocked"):
            continue
        key = ex.get("path") or ex.get("kind") or "unknown"
        by_finding.setdefault(key, []).append(ex)

    absorbed, confirmed = [], []
    for path, exs in by_finding.items():
        first = exs[0]
        claim = (f"executable weakness: {path} "
                 f"({first.get('kind', '?')})")
        evidence = (f"severity {first.get('severity')} — executed by "
                    f"{first.get('executor')} in round {first.get('round')}")
        source = first.get("executor", "?")
        try:
            cid = uc.absorb(claim, evidence=evidence, source=source)
            absorbed.append(cid)
        except Exception as exc:
            result_extra = {"error": str(exc)}
            result_extra = None  # never let the ledger crash the fight
            absorbed.append(None)
            continue
        # every other scout who saw the same finding confirms independently
        for other in exs[1:]:
            o = other.get("executor")
            if o and o != source:
                try:
                    uc.confirm(cid, o)
                    confirmed.append(cid)
                except KeyError:
                    pass

    pool = uc.knowledge()
    return {
        "claims_absorbed": len(absorbed),
        "confirmations": len(confirmed),
        "inherited": len(pool),
        "threshold": MONKEY_THRESHOLD,
        "kinship": uc.kinship(),
    }


def _journal(result: dict, absorption: dict) -> dict:
    """Journal the engagement to Sakshi — the witness records everything."""
    brown = result.get("brown")

    recs = []
    recs.append(sakshi_record(
        "engagement", "ENGAGEMENT OPENED",
        agent="theoros", source="arena",
        path=_default_sakshi_path(),
        extra={"target": result.get("target"),
               "findings": result.get("findings")}))

    recs.append(sakshi_record(
        "engagement", "ENGAGEMENT CLOSED",
        agent="theoros", source="arena",
        path=_default_sakshi_path(),
        extra={"red_score": result.get("red_score"),
               "blue_score": result.get("blue_score"),
               "executions": result.get("executions"),
               "blocks": result.get("blocks"),
               "mines_deployed": len(result.get("mines", [])),
               "corrupt_speakers": result.get("corrupt_speakers")}))

    if brown is not None:
        recs.append(sakshi_record(
            "brown", "THE SHIT SHOVELER DROPPED",
            agent="brown", source="arena",
            path=_default_sakshi_path(),
            extra={"ruling": brown.unify_or_get_humped,
                   "red_solo": brown.solo_red.get("verdict"),
                   "blue_solo": brown.solo_blue.get("verdict"),
                   "united": brown.united.get("verdict"),
                   "ghosts_united": brown.united.get("ghosts")}))

    recs.append(sakshi_record(
        "undercurrent", "THE SWARM KNOWS",
        agent="undercurrent", source="arena",
        path=_default_sakshi_path(),
        extra={"claims_absorbed": absorption["claims_absorbed"],
               "confirmations": absorption["confirmations"],
               "inherited": absorption["inherited"],
               "afloat": absorption["kinship"]["afloat"]}))

    return {"records": len(recs)}


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 vigil/engage.py <target_dir> [rounds]")
        sys.exit(1)
    target = sys.argv[1]
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    result = run_engagement(target, rounds=rounds)
    print("\n" + "=" * 60)
    print("THREE-WAY ENGAGEMENT COMPLETE")
    print("=" * 60)
    print(f"RED {result.get('red_score')} / BLUE {result.get('blue_score')} "
          f"({result.get('findings')} findings, {result.get('executions')} "
          f"executions, {len(result.get('mines', []))} mines)")
    brown = result.get("brown")
    if brown is not None:
        print(f"BROWN: {brown.unify_or_get_humped}")
    uc = result.get("undercurrent", {})
    print(f"UNDERCURRENT: {uc.get('claims_absorbed')} claims absorbed, "
          f"{uc.get('confirmations')} confirmations, "
          f"{uc.get('inherited')} inherited")
    print(f"SAKSHI: {result.get('sakshi', {}).get('records', 0)} records "
          f"journaled")


if __name__ == "__main__":
    main()