"""Stress Vulnerability Index (SVI) computation and the Critical Override.

SVI is a 0-100 *routing* score. It is a weighted blend of three signals, with
a rule-based override that can force the top band regardless of the blend.

    voice present:  SVI = 0.40*Text + 0.35*Vocal + 0.25*Behavioural
    text/IVRS only:  SVI = 0.60*Text + 0.40*Behavioural

Critical Override
-----------------
If any *critical-tier* lexicon flag fires (suicidal-ideation language,
immediate-danger language, reports of harm happening now) the case is forced
to `Critical` and `override_reason` records exactly which flag fired. The
composite is still computed and stored, because the counsellor needs to see
how much the *non-override* signals also said - but the band never moves.

Two safeguards around the override:
* Hits from a STUB (not-yet-signed-off) lexicon still escalate, but
  `override_reason` is suffixed with `:needs-verification` and the case is
  never auto-actioned on the strength of an unverified lexicon.
* Absence of a critical flag is NOT evidence of safety. `override_checked`
  is recorded so a reviewer can see the rule ran.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from nlp import lexicons

log = logging.getLogger(__name__)

WEIGHTS_WITH_VOICE = {"text": 0.40, "vocal": 0.35, "behavioral": 0.25}
WEIGHTS_TEXT_ONLY = {"text": 0.60, "behavioral": 0.40}

#: Band edges from the module specification.
BANDS: List[Dict[str, Any]] = [
    {"category": "Low", "min": 0, "max": 24, "sla_hours": 120, "colour_token": "low"},
    {"category": "Moderate", "min": 25, "max": 49, "sla_hours": 48, "colour_token": "moderate"},
    {"category": "High", "min": 50, "max": 74, "sla_hours": 2, "colour_token": "high"},
    {"category": "Critical", "min": 75, "max": 100, "sla_hours": 0, "colour_token": "critical"},
]

#: Critical-tier flags that can force the override, with the reason string the
#: counsellor sees. Keeping the reason human-readable is deliberate: this text
#: ends up on a duty officer's screen.
OVERRIDE_REASONS: Dict[str, str] = {
    "self_harm_ideation": "Language suggesting thoughts of not wanting to be alive (suicidal-ideation lexicon)",
    "immediate_danger": "Language indicating immediate danger to the person right now",
    "ongoing_violence": "Report of harm occurring now or repeatedly",
    "child_safety_concern": "Concern raised about a child's safety",
}

#: Flags that also require law-enforcement liaison. Deliberately a separate
#: list from the override list: a child-safety concern escalates to a human but
#: does not by itself mean police should see the case.
LAW_ENFORCEMENT_FLAGS = {"immediate_danger", "ongoing_violence"}

#: Extra weight applied when the same critical flag appears in more than one
#: interaction - repetition of the signal matters, but the cap stops it from
#: running away.
REPEAT_CRITICAL_BONUS = 6.0
MAX_REPEAT_BONUS = 12.0


@dataclass
class SVIResult:
    text_score: float
    vocal_score: float
    behavioral_score: float
    composite_score: float
    category: str
    override_reason: Optional[str] = None
    weights: Dict[str, float] = field(default_factory=dict)
    sla_hours: int = 120
    risk_flags: List[str] = field(default_factory=list)
    critical_flags: List[str] = field(default_factory=list)
    law_enforcement_recommended: bool = False
    voice_present: bool = False
    method: str = "heuristic"
    confidence: float = 0.0
    explain: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "text_score": self.text_score,
            "vocal_score": self.vocal_score,
            "behavioral_score": self.behavioral_score,
            "composite_score": self.composite_score,
            "category": self.category,
            "override_reason": self.override_reason,
            "weights": self.weights,
            "sla_hours": self.sla_hours,
            "risk_flags": self.risk_flags,
            "critical_flags": self.critical_flags,
            "law_enforcement_recommended": self.law_enforcement_recommended,
            "voice_present": self.voice_present,
            "method": self.method,
            "confidence": self.confidence,
            "explain": self.explain,
        }


def band_for(score: float) -> Dict[str, Any]:
    for band in BANDS:
        if band["min"] <= score <= band["max"]:
            return band
    return BANDS[-1] if score > 100 else BANDS[0]


def category_for(score: float) -> str:
    return str(band_for(score)["category"])


def compute_svi(
    text_score: float,
    vocal_score: Optional[float] = None,
    behavioral_score: float = 0.0,
    risk_flags: Optional[Sequence[str]] = None,
    flag_details: Optional[Sequence[Dict[str, Any]]] = None,
    critical_occurrences: Optional[Sequence[str]] = None,
    lexical_confidence: float = 0.5,
) -> SVIResult:
    """Blend the three signals and apply the Critical Override.

    `critical_occurrences` is the per-interaction list of critical-tier flags
    that fired, concatenated across the case's interactions. This is what the
    override rule consumes - a critical flag in *any* interaction escalates.
    """
    flags = list(dict.fromkeys(risk_flags or []))
    # Keep the duplicate count for the repetition bonus, but de-duplicate the
    # list that drives the override *reason*. `critical_occurrences` is built
    # one entry per occurrence across the case's interactions, so de-duplicating
    # it before the bonus made the bonus unreachable - the same person
    # repeating a critical statement could never raise the composite.
    occurrence_list = list(critical_occurrences or [])
    critical_flags = list(dict.fromkeys(occurrence_list))
    voice_present = vocal_score is not None

    weights = dict(WEIGHTS_WITH_VOICE if voice_present else WEIGHTS_TEXT_ONLY)
    text_component = max(0.0, min(100.0, float(text_score or 0.0)))
    behavioral_component = max(0.0, min(100.0, float(behavioral_score or 0.0)))
    vocal_component = max(0.0, min(100.0, float(vocal_score))) if voice_present else 0.0

    composite = (
        weights["text"] * text_component
        + weights["behavioral"] * behavioral_component
        + (weights.get("vocal", 0.0) * vocal_component if voice_present else 0.0)
    )

    # Repetition of a critical indicator nudges the composite up. This is a
    # nudge only: the override below is what actually sets the band.
    if len(occurrence_list) > 1:
        bonus = min(MAX_REPEAT_BONUS, REPEAT_CRITICAL_BONUS * (len(occurrence_list) - 1))
        composite += bonus
    composite = max(0.0, min(100.0, composite))

    band = band_for(composite)
    category = str(band["category"])
    override_reason: Optional[str] = None

    if critical_flags:
        # Report the most severe flag first; lexicons.py already sorted by tier
        # then weight, so the first entry is the most serious signal present.
        primary = critical_flags[0]
        reason = OVERRIDE_REASONS.get(primary, f"Critical-tier indicator: {primary.replace('_', ' ')}")
        unverified = [
            hit
            for hit in (flag_details or [])
            if hit.get("flag") == primary and not hit.get("curated", True)
        ]
        if unverified:
            reason += " [needs-verification: matched an uncurated stub lexicon]"
        override_reason = reason
        category = "Critical"
        band = band_for(100)

    sla_hours = int(band["sla_hours"])
    law_enforcement = bool(set(critical_flags) & LAW_ENFORCEMENT_FLAGS)

    method = "heuristic"
    if voice_present and vocal_score is not None:
        method = "heuristic+audio-features"

    confidence = round(max(0.05, min(0.95, 0.5 * lexical_confidence + 0.25 + (0.1 if voice_present else 0.0))), 3)

    return SVIResult(
        text_score=round(text_component, 2),
        vocal_score=round(vocal_component, 2) if voice_present else 0.0,
        behavioral_score=round(behavioral_component, 2),
        composite_score=round(composite, 2),
        category=category,
        override_reason=override_reason,
        weights=weights,
        sla_hours=sla_hours,
        risk_flags=flags,
        critical_flags=critical_flags,
        law_enforcement_recommended=law_enforcement,
        voice_present=voice_present,
        method=method,
        confidence=confidence,
        explain={
            "formula": (
                "SVI = 0.40*Text + 0.35*Vocal + 0.25*Behavioural (voice present); "
                "SVI = 0.60*Text + 0.40*Behavioural (text/IVRS only)"
            ),
            "weighted_contributions": {
                "text": round(weights["text"] * text_component, 2),
                "vocal": round(weights.get("vocal", 0.0) * vocal_component, 2) if voice_present else 0.0,
                "behavioral": round(weights["behavioral"] * behavioral_component, 2),
            },
            "critical_override_applied": bool(override_reason),
            "override_checked": True,
            "override_candidate_flags": critical_flags,
            "band_edges": BANDS,
            "lexicon_version": lexicons.LEXICON_VERSION if hasattr(lexicons, "LEXICON_VERSION") else "",
            "interpretation_note": (
                "Routing priority only. Not a clinical assessment, not a diagnosis, "
                "and not a substitute for counsellor judgement."
            ),
        },
    )
