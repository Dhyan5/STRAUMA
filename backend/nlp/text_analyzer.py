"""Text risk engine: lexicon matching + sentiment + linguistic markers.

The output is a *routing* signal, not a clinical assessment. It exists to help
a counsellor decide which conversation to pick up first, and to make sure
nobody in immediate danger is left sitting in a queue.

Scoring is fully deterministic and every contribution is itemised in
`markers.explain` so a reviewer can reproduce the number by hand. Nothing
here is a diagnosis and no flag should ever be surfaced to a complainant as
a label - see `engine/victim_copy.py` for the plain-language layer.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nlp import lexicons, sentiment

log = logging.getLogger(__name__)

#: Cap on the corroboration bonus for several distinct flags co-occurring.
MAX_CORROBORATION_BONUS = 24.0
CORROBORATION_STEP = 6.0

#: Cap on linguistic-marker contributions.
MAX_MARKER_BONUS = 17.0

#: Beyond this many words the marker ratios stop adding signal and only add
#: noise, so we cap the length used for marker computation.
MARKER_WORD_LIMIT = 400

WORD_RE = re.compile(r"[\w'ऀ-ॿঀ-৿଀-࿿஀-௿ఀ-౿]+", re.UNICODE)
EXCLAIM_RE = re.compile(r"!")
QUESTION_RE = re.compile(r"\?")
FIRST_PERSON = {
    "en": {"i", "me", "my", "mine", "myself", "i'm"},
    "hi": {"मैं", "मेरा", "मेरी", "मुझे", "मुझ", "हूं", "हूँ", "में"},
    "bn": {"আমি", "আমার", "আমাকে", "আমি", "আমি"},
    "mr": {"मी", "माझा", "मला", "मी", "मी"},
    "ta": {"நான்", "என்", "எனக்கு", "நான்", "நான்"},
    "te": {"నేను", "నా", "నన్ను", "నేను", "నేను"},
}


@dataclass
class TextRiskResult:
    sentiment: str
    sentiment_score: float
    sentiment_method: str
    sentiment_confidence: float
    risk_flags: List[str] = field(default_factory=list)
    flag_details: List[Dict[str, Any]] = field(default_factory=list)
    text_risk_score: float = 0.0
    method: str = "heuristic"
    confidence: float = 0.0
    markers: Dict[str, Any] = field(default_factory=dict)
    lexicon_version: str = ""
    lexicon_status: Dict[str, str] = field(default_factory=dict)
    languages_considered: List[str] = field(default_factory=list)
    script_detected: str = "en"
    critical_tier_hits: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "sentiment": self.sentiment,
            "sentiment_score": self.sentiment_score,
            "sentiment_method": self.sentiment_method,
            "risk_flags": self.risk_flags,
            "flag_details": self.flag_details,
            "text_risk_score": self.text_risk_score,
            "method": self.method,
            "confidence": self.confidence,
            "markers": self.markers,
            "lexicon_version": self.lexicon_version,
            "lexicon_status": self.lexicon_status,
            "languages_considered": self.languages_considered,
            "script_detected": self.script_detected,
            "critical_tier_hits": self.critical_tier_hits,
        }


def _markers_for(normalized: str, lex: Optional[lexicons.Lexicon]) -> Dict[str, Any]:
    """Linguistic markers. These describe *how* someone wrote, never what
    happened to them."""
    words = WORD_RE.findall(normalized[: MARKER_WORD_LIMIT * 8])
    word_count = max(1, len(words))

    if lex is not None:
        absolutist = lex.count_cues(lex.absolutist, normalized)
        negation = lex.count_cues(lex.negation, normalized)
        hedge = lex.count_cues(lex.hedge, normalized)
        disfluent = lex.count_cues(lex.disfluent, normalized)
    else:
        absolutist = negation = hedge = disfluent = 0

    first_person_set = FIRST_PERSON.get(lex.language if lex else "en", FIRST_PERSON["en"])
    first_person = sum(1 for w in words if w.lower() in first_person_set)
    exclamations = len(EXCLAIM_RE.findall(normalized))
    questions = len(QUESTION_RE.findall(normalized))
    sentences = max(1, len(re.findall(r"[.!?।।]", normalized)))

    return {
        "word_count": word_count,
        "sentence_count": sentences,
        "absolutist_terms": absolutist,
        "absolutist_rate": round(absolutist / word_count, 4),
        "negation_count": negation,
        "negation_density": round(negation / word_count, 4),
        "hedge_count": hedge,
        "hedge_density": round(hedge / word_count, 4),
        # High filler/hedge ratio with low hedging value reads as hesitancy in
        # disclosure. It is a weak signal on purpose.
        "disfluent_cues": disfluent,
        "disfluent_rate": round(disfluent / word_count, 4),
        "first_person_ratio": round(first_person / word_count, 4),
        "exclamation_count": exclamations,
        "exclamation_rate": round(exclamations / word_count, 4),
        "question_count": questions,
    }


def _marker_bonus(markers: Dict[str, Any]) -> tuple[float, List[str]]:
    """Turn marker counts into a bounded score bonus, itemised."""
    bonus = 0.0
    reasons: List[str] = []

    absolutist = markers.get("absolutist_terms", 0)
    if absolutist >= 2:
        bonus += 6.0
        reasons.append(f"absolutist_language x{absolutist}")

    negation_density = markers.get("negation_density", 0.0)
    if negation_density >= 0.06:
        bonus += 4.0
        reasons.append("elevated_negation_density")

    disfluent_rate = markers.get("disfluent_rate", 0.0)
    if disfluent_rate >= 0.04:
        bonus += 3.0
        reasons.append("hesitant_disclosure_cues")

    if markers.get("exclamation_rate", 0.0) >= 0.08:
        bonus += 4.0
        reasons.append("high_excitement_intensity")

    if markers.get("first_person_ratio", 0.0) >= 0.09 and markers.get("word_count", 0) >= 12:
        bonus += 2.0
        reasons.append("self_focused_statement")

    return min(bonus, MAX_MARKER_BONUS), reasons


def analyze_text(
    text: str,
    language: str = "en",
    extra_languages: Optional[List[str]] = None,
) -> TextRiskResult:
    """Analyse one message. `language` is the session language; the actual
    script is detected independently so a Hindi-speaking user typing English
    is still routed through the file that can actually match them."""
    normalized = lexicons.normalize(text)
    if not normalized:
        return TextRiskResult(
            sentiment="neutral",
            sentiment_score=0.0,
            sentiment_method="heuristic",
            sentiment_confidence=0.2,
            text_risk_score=0.0,
            method="heuristic",
            confidence=0.15,
            markers={"word_count": 0},
        )

    hits, languages_used, script = lexicons.match(normalized, extra_languages)

    # A Latin-script message from a Hindi session may be Romanised Hindi, so
    # consult the session language's file as well when the scripts differ.
    session_lex = lexicons.get_lexicon(language)
    if session_lex and language not in languages_used and script != language:
        for hit in session_lex.match(normalized):
            if all(h.flag != hit.flag or h.lexicon_language != hit.lexicon_language for h in hits):
                hits.append(hit)
        if session_lex.language not in languages_used:
            languages_used = languages_used + [session_lex.language]
        hits.sort(key=lambda h: (lexicons.TIER_ORDER.get(h.tier, 9), -h.weight))

    primary_lex = session_lex or lexicons.get_lexicon(script)
    markers = _markers_for(normalized, primary_lex)
    marker_bonus, marker_reasons = _marker_bonus(markers)

    sentiment_result = sentiment.analyze(normalized, language=primary_lex.language if primary_lex else script)

    # --- Composite text risk score (deterministic, itemised) -------------
    weights = sorted((hit.weight for hit in hits), reverse=True)
    dominant = weights[0] if weights else 0.0
    corroboration = min(
        MAX_CORROBORATION_BONUS, CORROBORATION_STEP * max(0, len(weights) - 1)
    )
    sentiment_bonus = 0.0
    if sentiment_result.label in ("negative",):
        sentiment_bonus = 8.0
    elif sentiment_result.label == "mildly_negative":
        sentiment_bonus = 5.0
    if sentiment_result.score <= -0.6:
        sentiment_bonus = max(sentiment_bonus, 8.0)

    score = dominant + corroboration + marker_bonus + sentiment_bonus
    score = max(0.0, min(100.0, score))

    # --- Confidence ------------------------------------------------------
    # Confidence is about *our* evidence, not about the person. A stub lexicon
    # or a one-word message is low confidence, and we say so.
    confidence = 0.35
    curated_hits = [h for h in hits if h.curated]
    if curated_hits:
        confidence += 0.3
    elif hits:
        confidence += 0.05
    confidence += min(0.2, markers.get("word_count", 0) / 200.0)
    if not primary_lex or not primary_lex.is_curated:
        confidence -= 0.15
    confidence = round(max(0.05, min(0.95, confidence)), 3)

    methods = {"ml-model" if sentiment_result.method == "ml-model" else "heuristic"}
    method = "ml-model" if methods == {"ml-model"} else ("mixed" if "ml-model" in methods else "heuristic")

    lexicon_status = {
        code: (lexicons.get_lexicon(code).curation_status if lexicons.get_lexicon(code) else "missing")
        for code in languages_used
    }

    critical_tier_hits = [h.flag for h in hits if h.tier == lexicons.TIER_CRITICAL]

    return TextRiskResult(
        sentiment=sentiment_result.label,
        sentiment_score=sentiment_result.score,
        sentiment_method=sentiment_result.method,
        sentiment_confidence=sentiment_result.confidence,
        risk_flags=[h.flag for h in hits],
        flag_details=[h.as_dict() for h in hits],
        text_risk_score=round(score, 2),
        method=method,
        confidence=confidence,
        markers={
            **markers,
            "explain": {
                "dominant_flag_weight": round(dominant, 1),
                "corroborating_flags": max(0, len(weights) - 1),
                "corroboration_bonus": round(corroboration, 1),
                "sentiment_bonus": round(sentiment_bonus, 1),
                "marker_bonus": round(marker_bonus, 1),
                "marker_reasons": marker_reasons,
                "formula": (
                    "text_risk = max(flag weight) + 6*min(extra flags,4) "
                    "+ marker_bonus + sentiment_bonus, capped at 100"
                ),
            },
        },
        lexicon_version=(primary_lex.version if primary_lex else ""),
        lexicon_status=lexicon_status,
        languages_considered=languages_used,
        script_detected=script,
        critical_tier_hits=critical_tier_hits,
    )
