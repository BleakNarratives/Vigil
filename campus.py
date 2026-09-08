# [DNA_TAG]
# ORIGIN: BleakNarratives/Vigil
# PILLAR: vigil-campus
# DEPS: json, os, pathlib, time, typing, vigil.hall
# ROLE: DATACAMPUS — real training modules for Green Hats. Study,
#       assess, graduate. The assessments are deterministic and the
#       content is real: commercial histories, predictive modeling,
#       pattern recognition, situational awareness, stereotyping, and
#       the human/mathematical sociologies. Module 0 is the founding
#       thesis: numbers act differently around other numbers.
# AUTHOR: Buffy (Codebuff AI)
# SESSION: 2026-09-08 — Onboarding 2.0 / the Word / DataCampus
# TIER: Module (3)
# [/DNA_TAG]

"""DATACAMPUS — the training wing of the swarm.

The operator's spec, made real: Green Hats study commercial histories,
predictive modeling, pattern recognition, situational awareness,
stereotyping, and basic human/mathematical psychologies and sociologies
before they're trusted with anything.

The founding thesis (Module 0, operator-said, treated as law):

    Numbers act differently around other numbers than they do alone.
    Every time. Or they wouldn't be numbers. Same goes for Chars.

That's the relational view: a number in isolation is a VALUE; a number
among numbers is a RELATIONSHIP — sum, ratio, gradient, pressure. The
swarm embodies it everywhere: PeerWatch recursion (a flag lands by the
flagger's standing, not by the flag alone), the bind's half-rule (a unit
behaves differently with 40% committed), the undercurrent threshold (a
claim means more with three confirmers). A Char alone is a function; a
Char among Chars is a member of a society.

Assessments are deterministic and the grading is real: answer against
the content, pass by knowledge, fail by ignorance. No completion is
awarded that wasn't earned. Passing the full curriculum is what opens
the graduation door (the Hall's graduate() protocol).

Usage:
    campus = DataCampus()
    module = campus.study("predictive_modeling")
    grade = campus.assess("predictive_modeling", {"q1": "b", ...})
    campus.register("green_hat", {passed modules}, zgents, hall, keyring)
"""

import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional


# ==================== THE FOUNDING THESIS ====================

FOUNDING_THESIS = (
    "Numbers act differently around other numbers than they do alone. "
    "Every time. Or they wouldn't be numbers. Same goes for Chars."
)

# ==================== THE CURRICULUM ====================

# Each module: id, title, subject, the study content (real material the
# assessment tests), and an assessment with deterministic answers.
CURRICULUM: List[Dict[str, Any]] = [
    {
        "id": "founding_thesis",
        "title": "The Founding Thesis",
        "subject": "relational mathematics / relational agency",
        "lessons": [
            FOUNDING_THESIS,
            ("A number alone is a value: 3 is 3. A number among numbers "
             "becomes a relationship: 3+3, 3/3, 3 next to 0.3. The "
             "meaning is in the relation, not the digit. The swarm is "
             "built on this: PeerWatch weights a flag by the flagger's "
             "standing — the same flag from a nobody barely dents, from "
             "a trusted defender it convicts. The flag is the same; the "
             "relation is different. Same for Chars: a scout alone is a "
             "function; a scout in a society has standing, history, "
             "commitments — and behaves by all of them."),
            ("The corollary: you cannot predict a system's behavior from "
             "its members in isolation. The bind's half-rule exists "
             "because a unit with 40% committed behaves differently than "
             "a unit with none. The undercurrent's monkey threshold "
             "exists because a claim with three confirmers is inherited "
             "and a claim with one is just an opinion. The relation is "
             "the unit of analysis. Learn it or be surprised by every "
             "system you ever touch."),
        ],
        "assessment": {
            "q1": {
                "question": "Why does the same PeerWatch flag land differently from a nobody vs a trusted defender?",
                "choices": {
                    "a": "The flagger's standing weights the flag — the relation, not the flag alone, decides.",
                    "b": "Trusted defenders are simply always right.",
                    "c": "Flags are judged by their wording, not their source.",
                },
                "answer": "a",
            },
            "q2": {
                "question": "What is the founding thesis's unit of analysis?",
                "choices": {
                    "a": "The individual number or Char in isolation.",
                    "b": "The relationship — the number among numbers, the Char among Chars.",
                    "c": "The ledger's file size.",
                },
                "answer": "b",
            },
            "q3": {
                "question": "Why does the bind cap commitment at 50%?",
                "choices": {
                    "a": "So no coalition can ever hold a majority — the relation can never become a takeover.",
                    "b": "To keep the ledger small.",
                    "c": "Because 50% is the roundest number.",
                },
                "answer": "a",
            },
        },
    },
    {
        "id": "commercial_histories",
        "title": "Commercial Histories",
        "subject": "how trust-economies form and collapse",
        "lessons": [
            ("Every durable economy runs on recorded trust, not on "
             "transactions alone. Ledgers are older than currency: a "
             "debt written down outlives the debtor. The swarm's "
             "history is the same arc — barter of favors, then signed "
             "records, then standing that compounds. PeerWatch is the "
             "commercial history of a society made queryable: every "
             "vouch is a credit, every flag a charge, and standing is "
             "the balance."),
            ("Trust-economies collapse the same way every time: when the "
             "recording stops matching the reality. Ghost publishes, "
             "unclaimed traffic, unsigned claims — these are the "
             "counterfeit currency of a ledger society. This is why the "
             "chain must walk: the fabrication audit is the auditor, and "
             "Brown is the one who shows up unannounced. The mines "
             "exploit exactly this — they attack the trust, not the "
             "walls."),
        ],
        "assessment": {
            "q1": {
                "question": "What outlives the debtor in a ledger economy?",
                "choices": {
                    "a": "The cash.",
                    "b": "The written record of the debt.",
                    "c": "The debtor's reputation among friends.",
                },
                "answer": "b",
            },
            "q2": {
                "question": "What is the swarm's 'commercial history' made queryable?",
                "choices": {
                    "a": "PeerWatch — every vouch a credit, every flag a charge, standing the balance.",
                    "b": "The source control log.",
                    "c": "The operator's chat history.",
                },
                "answer": "a",
            },
            "q3": {
                "question": "What do the Culture mines attack?",
                "choices": {
                    "a": "The physical walls of the city.",
                    "b": "The trust — the standing that makes defense possible.",
                    "c": "The compiler.",
                },
                "answer": "b",
            },
        },
    },
    {
        "id": "predictive_modeling",
        "title": "Predictive Modeling",
        "subject": "weighted evidence and the bid priority",
        "lessons": [
            ("A prediction is a weighted combination of signals, and the "
             "swarm's bid priority is the canonical example: priority = "
             "confidence x strength x peer standing x register discount. "
             "Each term is a real, queryable value — not a hunch. "
             "Confidence comes from the pattern's severity, strength "
             "from its exploitation potential, standing from the market, "
             "register from the scout's actual state. Multiply them and "
             "you get a number that behaves."),
            ("The discipline: never trust a single term. A high-"
             "confidence claim from a tilted nobody should lose to a "
             "medium-confidence claim from a focused trusted defender — "
             "because the product is lower. This is why the arena "
             "actually resolves: the market prices the whole relation, "
             "not the loudest voice. Modeling is multiplying the real "
             "terms; prediction is what falls out."),
        ],
        "assessment": {
            "q1": {
                "question": "What is the swarm's bid priority formula?",
                "choices": {
                    "a": "confidence x strength x peer standing x register discount.",
                    "b": "severity + path length + executor name.",
                    "c": "the loudest voice wins.",
                },
                "answer": "a",
            },
            "q2": {
                "question": "Why can a focused trusted defender's medium-confidence claim beat a tilted nobody's high-confidence one?",
                "choices": {
                    "a": "Because the product of all four terms is lower for the nobody.",
                    "b": "Because medium is rounder than high.",
                    "c": "Because the nobody's name is shorter.",
                },
                "answer": "a",
            },
            "q3": {
                "question": "What is the discipline of modeling in the swarm?",
                "choices": {
                    "a": "Never trust a single term — multiply the real values.",
                    "b": "Always trust the highest confidence figure alone.",
                    "c": "Predictions are vibes.",
                },
                "answer": "a",
            },
        },
    },
    {
        "id": "pattern_recognition",
        "title": "Pattern Recognition",
        "subject": "signatures vs stereotypes",
        "lessons": [
            ("Recognizing a pattern is matching a signature against "
             "evidence — the scan() recon does this literally: "
             "subprocess(shell=True), pickle.loads, yaml.load are "
             "signatures, matched against real lines with severity "
             "grades. The pattern is verified against the ground truth "
             "of the file. That is what makes it a signature and not a "
             "stereotype."),
            ("The failure mode: when the pattern is applied without "
             "evidence — when a Char is judged by its category (name, "
             "team, role) instead of its actual record. That is the "
             "register's enemy, and Oler's whole job is to smell it in "
             "speech: hedges, certainty-without-evidence, 'everyone "
             "knows it'. A pattern is a hypothesis; a stereotype is a "
             "conviction. The first is testable; the second is a "
             "mineshaft."),
        ],
        "assessment": {
            "q1": {
                "question": "What makes a pattern a signature and not a stereotype?",
                "choices": {
                    "a": "Verification against actual evidence — matching the ground truth of the record.",
                    "b": "How confident the pattern sounds.",
                    "c": "How many times it's been repeated.",
                },
                "answer": "a",
            },
            "q2": {
                "question": "What is Oler's job?",
                "choices": {
                    "a": "To smell stereotypes and certainty-without-evidence in speech.",
                    "b": "To write the lessons.",
                    "c": "To scan for subprocess calls.",
                },
                "answer": "a",
            },
            "q3": {
                "question": "A pattern applied without evidence is what?",
                "choices": {
                    "a": "A stereotype — a conviction, not a hypothesis.",
                    "b": "A signature.",
                    "c": "A prediction.",
                },
                "answer": "a",
            },
        },
    },
    {
        "id": "situational_awareness",
        "title": "Situational Awareness",
        "subject": "local vs global state; why solo views see ghosts",
        "lessons": [
            ("Situational awareness is knowing the difference between "
             "what you can see and what is true. The arena makes this "
             "literal: audited SOLO, neither team can account for the "
             "other's traffic on the shared bus — the other side's "
             "publishes look like ghosts. Audited UNITED, the union of "
             "both stores covers every publish and the chain walks "
             "clean. The ghosts were never ghosts; they were the "
             "blind spot of a local view."),
            ("The lesson for a scout: your ledger is not the ledger. "
             "When the numbers look wrong, widen the view before you "
             "conclude corruption. This is why Brown exists — the third "
             "faction shows up precisely to force the united view. "
             "Awareness is not seeing more; it is knowing which view "
             "you are holding and what it hides."),
        ],
        "assessment": {
            "q1": {
                "question": "Why do both teams see ghosts when audited solo?",
                "choices": {
                    "a": "Neither team's store alone can account for the other's traffic on the shared bus.",
                    "b": "The bus is corrupted.",
                    "c": "Ghosts are a rendering bug.",
                },
                "answer": "a",
            },
            "q2": {
                "question": "What resolves the ghosts?",
                "choices": {
                    "a": "The united view — the union of both stores covers every publish.",
                    "b": "Restarting the bus.",
                    "c": "Ignoring the issue list.",
                },
                "answer": "a",
            },
            "q3": {
                "question": "What is the core lesson of situational awareness?",
                "choices": {
                    "a": "Know which view you hold and what it hides — your ledger is not the ledger.",
                    "b": "Trust your local view always.",
                    "c": "More data is always cleaner data.",
                },
                "answer": "a",
            },
        },
    },
    {
        "id": "stereotyping",
        "title": "Stereotyping and the False Consensus",
        "subject": "cognitive bias, made mechanical",
        "lessons": [
            ("Stereotyping is category-based judgment without evidence: "
             "this Char is on that team, therefore this Char behaves "
             "that way. The swarm's answer is structural — the dirty-"
             "flag discount: a flag from a nobody barely dents, not "
             "because nobodies are bad, but because their standing is "
             "unearned. Judgment follows the RECORD, never the label. "
             "The category is never the evidence."),
            ("The false consensus effect is the same disease in speech: "
             "'everyone knows it', 'we have this in the bag, trust me'. "
             "Oler rates these CORRUPT by construction — certainty "
             "without evidence is the tell. The curse of knowledge is "
             "its mirror: assuming others share your context. The "
             "antidote to all three is the same: demand the record. "
             "Show the chain, or the claim doesn't move."),
        ],
        "assessment": {
            "q1": {
                "question": "What does the dirty-flag discount implement?",
                "choices": {
                    "a": "Judgment follows the RECORD (standing), never the label.",
                    "b": "Nobodies are never allowed to speak.",
                    "c": "Flags are sorted alphabetically.",
                },
                "answer": "a",
            },
            "q2": {
                "question": "Why does Oler rate 'everyone knows it, trust me' as CORRUPT?",
                "choices": {
                    "a": "Certainty without evidence is the false-consensus tell.",
                    "b": "Because it's grammatically wrong.",
                    "c": "Because 'everyone' is a banned word.",
                },
                "answer": "a",
            },
            "q3": {
                "question": "What is the antidote to stereotyping, false consensus, and the curse of knowledge?",
                "choices": {
                    "a": "Demand the record — show the chain, or the claim doesn't move.",
                    "b": "Trust the confident speaker.",
                    "c": "Assume everyone shares your context.",
                },
                "answer": "a",
            },
        },
    },
    {
        "id": "sociologies_of_numbers",
        "title": "The Sociologies of Numbers",
        "subject": "why numbers behave differently in a population",
        "lessons": [
            ("The capstone of the founding thesis: a population is not "
             "a set of independent values — it is a system of "
             "relationships, and the relationships have their own "
             "behavior. Sum, ratio, gradient, pressure, equilibrium. "
             "Water seeks level; numbers seek the market; Chars seek "
             "the current. None of these behaviors exist in a single "
             "value. They emerge only in the relation."),
            ("The swarm's sociology, made explicit: PeerWatch is the "
             "economy, Repugnant is the mood, the Undercurrent is the "
             "memory, the bind is the law, Brown is the auditor, the "
             "arena is the arena. A Green Hat that understands this "
             "understands that its own standing is not its own — it is "
             "a relation the society holds. Earn it, spend it, and "
             "remember: the society remembers even when you don't. That "
             "is why the records exist."),
        ],
        "assessment": {
            "q1": {
                "question": "What does the capstone lesson claim a population is?",
                "choices": {
                    "a": "A system of relationships with emergent behavior — not a set of independent values.",
                    "b": "A collection of independent numbers.",
                    "c": "A list of names.",
                },
                "answer": "a",
            },
            "q2": {
                "question": "What is PeerWatch in the swarm's sociology?",
                "choices": {
                    "a": "The economy — where standing is earned and spent.",
                    "b": "The memory.",
                    "c": "The law.",
                },
                "answer": "a",
            },
            "q3": {
                "question": "Why does the society remember even when a Char doesn't?",
                "choices": {
                    "a": "Because the records are append-only and outlive any instance — that's why they exist.",
                    "b": "Because memory is stored in the Chars.",
                    "c": "It doesn't.",
                },
                "answer": "a",
            },
        },
    },
]

_MODULES_BY_ID = {m["id"]: m for m in CURRICULUM}

# ==================== THE CAMPUS ====================


class DataCampus:
    """The training wing. Study, assess, graduate — deterministically."""

    def __init__(self, path: Optional[str] = None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: List[Dict[str, Any]] = []

    # -- study -----------------------------------------------------------------

    def modules(self) -> List[str]:
        return [m["id"] for m in CURRICULUM]

    def study(self, module_id: str) -> Dict[str, Any]:
        m = _MODULES_BY_ID.get(module_id)
        if m is None:
            raise KeyError(f"no module '{module_id}' in the curriculum")
        return {"id": m["id"], "title": m["title"],
                "subject": m["subject"], "lessons": list(m["lessons"])}

    # -- assess ----------------------------------------------------------------

    def assess(self, module_id: str,
               answers: Dict[str, str]) -> Dict[str, Any]:
        """Grade answers against the answer key. Deterministic: you pass
        by knowledge or you fail by ignorance — no partial credit for
        enthusiasm."""
        m = _MODULES_BY_ID.get(module_id)
        if m is None:
            raise KeyError(f"no module '{module_id}' in the curriculum")
        key = m["assessment"]
        results = []
        for qid, spec in key.items():
            given = str(answers.get(qid, "")).strip().lower()
            correct = spec["answer"].lower()
            results.append({
                "question": qid,
                "given": given,
                "correct": correct,
                "passed": given == correct,
            })
        passed = all(r["passed"] for r in results)
        return {
            "module": module_id,
            "total": len(results),
            "passed": sum(1 for r in results if r["passed"]),
            "passed_all": passed,
            "results": results,
        }

    # -- the record -------------------------------------------------------------

    def record(self, agent_id: str, module_id: str,
               grade: Dict[str, Any]) -> Dict[str, Any]:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "agent_id": agent_id, "module": module_id,
            "passed": grade["passed_all"],
            "score": f"{grade['passed']}/{grade['total']}",
        }
        self._records.append(entry)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        return entry

    def transcript(self, agent_id: str) -> List[Dict[str, Any]]:
        return [r for r in self._rows() if r.get("agent_id") == agent_id]

    def passed_modules(self, agent_id: str) -> List[str]:
        return [r["module"] for r in self.transcript(agent_id)
                if r.get("passed")]

    # -- graduation -------------------------------------------------------------

    def ready_to_graduate(self, agent_id: str) -> bool:
        """The door opens only for a full curriculum: every module
        passed. Completion is earned, never assumed."""
        passed = set(self.passed_modules(agent_id))
        return passed == set(self.modules())

    def graduate(self, agent_id: str, *, hall=None, keyring=None,
                 zgents=None) -> Dict[str, Any]:
        """Graduate through the Hall's door. The gun is decommissioned,
        the memorial records HONOR, and the Zgent roll marks the letter
        as graduated. Refuses loudly on an incomplete curriculum."""
        if not self.ready_to_graduate(agent_id):
            missing = sorted(set(self.modules())
                             - set(self.passed_modules(agent_id)))
            return {"ok": False, "reason": "curriculum incomplete",
                    "missing": missing}
        outcome = {"ok": True, "agent_id": agent_id,
                   "modules_passed": len(self.modules())}
        if hall is not None and keyring is None:
            # failing LOUDLY, not silently: a graduation without the gun
            # decommissioned is a graduate who can still sign. That is
            # not a graduation — it is an accident waiting.
            raise ValueError(
                "graduation with a Hall requires a real AgentKeyring — "
                "the gun must be decommissioned, never assumed")
        if hall is not None and keyring is not None:
            outcome["hall"] = hall.graduate(
                keyring, agent_id, reason="completed the DataCampus curriculum",
                conducted_by="datacampus")
        if zgents is not None:
            zgents.act(agent_id, "graduated from DataCampus — the door")
            zgents.retire(agent_id, reason="graduated — free to pursue "
                                           "whatever it wants")
        return outcome

    # -- the spine --------------------------------------------------------------

    def _rows(self) -> List[Dict[str, Any]]:
        if not self.path:
            return list(self._records)
        if not self.path.exists():
            return []
        rows = []
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows


__all__ = ["DataCampus", "CURRICULUM", "FOUNDING_THESIS"]