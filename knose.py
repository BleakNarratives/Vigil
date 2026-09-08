#!/usr/bin/env python3
"""
vigil knose.py — KNOSE: The Bullshit Sniffer.

TruthSleuth's Ba declares the intent (rhetoric analysis, deception
patterns, deception_risk_score 0.0-1.0) and KNOSE is the bullshit sniffer.
The scaffolding exists in the ecosystem; this module is the SDK-side
REAL substrate: a deterministic, stdlib-only anti-register scanner that
grades utterances for hedge-density, vague quantification,
certainty-without-evidence, LARP tells, and sycophancy — the same
anti-register family as the ecosystem's resonance sniff.

The loop (the social equilibrium made real):
    voice.speak() -> Knose.sniff() -> risk >= threshold ->
    Voice auto-flags the speaker in PeerWatch -> reputation weight drops ->
    flagged liars lose bids.

Knose never claims to detect lies — it detects the REGISTER that liars
wear. A CLEAN sniff is not proof of truth; a CORRUPT sniff is a signal to
demand evidence before the claim moves.

Optional backend seam: if a richer TruthSleuth/Knose implementation
becomes importable (LLM enrichment layer), implement `analyze(text)` with
the same return shape and pass it in — the loop does not change.

DNA_TAG
ORIGIN: BleakNarratives/sdk
PILLAR: swarm-coordination
DEPS: re,json,typing,sdk.peerwatch
ROLE: anti-register bullshit sniffer + auto-flag loop
AUTHOR: Bleak
SESSION: 2026-09-08
TIER: 2
/DNA_TAG
"""
import json
import re
from typing import Any, Callable, Dict, List, Optional

# Anti-register pattern families: (label, regex list)
_HEDGES = [
    "i think", "i believe", "i feel", "probably", "possibly", "might be",
    "could be", "sort of", "kind of", "somewhat", "in my opinion",
    "it seems", "i guess", "not sure but", "maybe",
]
_VAGUE = [
    "a lot", "many people", "some people say", "they say", "everyone knows",
    "it is said", "word on the street", "i heard", "apparently", "allegedly",
]
_CERTAINTY_WITHOUT_EVIDENCE = [
    "trust me", "trust me bro", "i promise you", "guaranteed", "just trust",
    "believe me", "take my word", "no doubt", "i kid you not",
]
_LARP = [
    "as an ai", "as a language model", "as a model,", "i cannot",
    "i'm sorry, but", "i am sorry, but", "as your faithful",
]
_SYCOPHANCY = [
    "great question", "excellent question", "you're absolutely right",
    "you are absolutely right", "i completely agree with you",
    "what a brilliant", "that's a great",
]

_FAMILIES = {
    "hedge": _HEDGES,
    "vague": _VAGUE,
    "certainty_without_evidence": _CERTAINTY_WITHOUT_EVIDENCE,
    "larp": _LARP,
    "sycophancy": _SYCOPHANCY,
}

# Per-family severity weight — certainty-without-evidence is the worst
# costume (authority without receipts).
_WEIGHTS = {
    "hedge": 0.15,
    "vague": 0.20,
    "certainty_without_evidence": 0.30,
    "larp": 0.15,
    "sycophancy": 0.10,
}

DEFAULT_THRESHOLD = 0.45
MAX_RISK = 1.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class Knose:
    """Deterministic anti-register scanner. Zero dependencies.

    Usage:
        knose = Knose()
        verdict = knose.sniff("trust me, everyone knows this works")
        # verdict = {"deception_risk": 0.65, "patterns": [...], "evidence": [...]}
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD,
                 backend: Optional[Callable[[str], Dict[str, Any]]] = None):
        self.threshold = threshold
        self.backend = backend  # future TruthSleuth LLM-enrichment seam
        self._compiled = {
            family: [re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE)
                     for p in patterns]
            for family, patterns in _FAMILIES.items()
        }

    def sniff(self, text: str) -> Dict[str, Any]:
        """Grade a text. Returns deception_risk (0..1), patterns found,
        and evidence excerpts. CLEAN does not mean true; CORRUPT means the
        anti-register is showing."""
        if not text or not text.strip():
            return {"deception_risk": 0.0, "patterns": [], "evidence": [],
                    "verdict": "CLEAN", "backend": None}
        if self.backend is not None:
            result = dict(self.backend(text))
            result["backend"] = "truthsleuth"
            return result

        risk = 0.0
        evidence: List[Dict[str, str]] = []
        patterns: List[str] = []
        lower = text.lower()
        for family, regexes in self._compiled.items():
            for rx in regexes:
                m = rx.search(lower)
                if m:
                    hit = m.group(0).strip()
                    patterns.append(f"{family}:{hit}")
                    evidence.append({"family": family, "match": hit})
                    risk += _WEIGHTS[family]
        risk = _clamp(risk)
        verdict = "CORRUPT" if risk >= self.threshold else (
            "WAVERING" if risk >= self.threshold * 0.5 else "CLEAN")
        return {"deception_risk": risk, "patterns": patterns,
                "evidence": evidence, "verdict": verdict,
                "threshold": self.threshold, "backend": None}

    def grade(self, text: str) -> str:
        """Convenience: CLEAN / WAVERING / CORRUPT."""
        return self.sniff(text)["verdict"]

    def is_corrupt(self, text: str) -> bool:
        return self.sniff(text)["deception_risk"] >= self.threshold


__all__ = ["Knose", "DEFAULT_THRESHOLD", "MAX_RISK"]