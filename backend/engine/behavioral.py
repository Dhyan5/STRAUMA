"""Behavioural signal: response latency, session patterns, self-report.

None of this is a clinical instrument and none of it is presented to the
complainant as a result. The self-report items below were written from scratch
for this prototype, deliberately avoiding any copyrighted scale (no PHQ-9
phrasing, no GAD-7 phrasing, no Kessler-6 phrasing). A qualified mental-health
professional must review and approve these items before any real-world use -
they are a UX scaffold, not a validated measure.

The items are plain-language and answerable with a 0-3 response. They feed the
BehavioralScore as one of three equally-weighted components.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

log = logging.getLogger(__name__)

#: Ordered exactly as the portal asks them. `key` is what gets stored.
SELF_REPORT_ITEMS: List[Dict[str, str]] = [
    {"key": "safety", "i18n_key": "selfreport.q_safety", "invert": False},
    {"key": "support", "i18n_key": "selfreport.q_support", "invert": False},
    {"key": "heard", "i18n_key": "selfreport.q_heard", "invert": False},
    {"key": "rest", "i18n_key": "selfreport.q_rest", "invert": False},
    {"key": "urgent", "i18n_key": "selfreport.q_urgent", "invert": False},
]

#: Response scales per item. `urgent` is the only positively-keyed item.
SCALES: Dict[str, List[Dict[str, Any]]] = {
    "safety": [
        {"value": 0, "i18n_key": "option.a_lot"},
        {"value": 1, "i18n_key": "option.some"},
        {"value": 2, "i18n_key": "option.a_little"},
        {"value": 3, "i18n_key": "option.not_at_all"},
    ],
    "support": [
        {"value": 3, "i18n_key": "option.a_lot"},
        {"value": 2, "i18n_key": "option.some"},
        {"value": 1, "i18n_key": "option.a_little"},
        {"value": 0, "i18n_key": "option.not_at_all"},
    ],
    "heard": [
        {"value": 3, "i18n_key": "option.a_lot"},
        {"value": 2, "i18n_key": "option.some"},
        {"value": 1, "i18n_key": "option.a_little"},
        {"value": 0, "i18n_key": "option.not_at_all"},
    ],
    "rest": [
        {"value": 3, "i18n_key": "option.a_lot"},
        {"value": 2, "i18n_key": "option.some"},
        {"value": 1, "i18n_key": "option.a_little"},
        {"value": 0, "i18n_key": "option.not_at_all"},
    ],
    "urgent": [
        {"value": 0, "i18n_key": "option.no"},
        {"value": 1, "i18n_key": "option.a_little"},
        {"value": 2, "i18n_key": "option.some"},
        {"value": 3, "i18n_key": "option.a_lot"},
    ],
}

#: If fewer than this many items are answered we withhold the self-report
#: contribution rather than guessing from partial data.
MIN_ITEMS_FOR_SELF_REPORT = 3

#: Response-latency bands in milliseconds (time from prompt shown to send).
#: Fast replies can read as rehearsed, slow replies as hesitancy. Both ends
#: contribute a little; the middle is neutral.
LATENCY_BANDS: List[Sequence[float]] = [
    (0.0, 800.0),      # instant / possibly pre-typed
    (800.0, 2500.0),
    (2500.0, 8000.0),
    (8000.0, 20000.0),
    (20000.0, 60000.0),
    (60000.0, float("inf")),
]
#: Contribution to the behavioural score for each latency band.
LATENCY_CONTRIBUTION = [26.0, 8.0, 4.0, 14.0, 22.0, 30.0]

#: Re-contact within this window raises the behavioural score: someone coming
#: back repeatedly is often escalating rather than stabilising.
RECONTACT_WINDOW_HOURS = 48.0
RECONTACT_CONTRIBUTIONS = {0: 0.0, 1: 12.0, 2: 20.0, 3: 28.0, 4: 34.0}


@dataclass
class BehavioralResult:
    score: float
    confidence: float
    components: Dict[str, Any] = field(default_factory=dict)
    method: str = "heuristic"
    #: Plain-language note for the counsellor, never shown to the complainant.
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "confidence": self.confidence,
            "components": self.components,
            "method": self.method,
            "notes": self.notes,
        }


def normalize_self_report(answers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalise raw self-report answers to 0-100 (higher = more concern)."""
    if not answers:
        return {"answered": 0, "value": 0.0, "included": False, "reason": "no_answers"}

    cleaned: Dict[str, float] = {}
    for item in SELF_REPORT_ITEMS:
        key = item["key"]
        if key not in answers:
            continue
        scale = SCALES.get(key, [])
        valid = {entry["value"]: entry["value"] for entry in scale}
        raw = answers.get(key)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value in valid:
            cleaned[key] = float(value)

    answered = len(cleaned)
    if answered < MIN_ITEMS_FOR_SELF_REPORT:
        return {"answered": answered, "value": 0.0, "included": False, "reason": "insufficient_items"}

    # Each item contributes value/3 (0-1); the mean is scaled to 0-100.
    mean = statistics.fmean(cleaned.values()) / 3.0
    return {
        "answered": answered,
        "value": round(mean * 100.0, 2),
        "included": True,
        "items": cleaned,
    }


def _latency_component(latencies_ms: Sequence[int]) -> Dict[str, Any]:
    if not latencies_ms:
        return {"value": 0.0, "included": False, "reason": "no_latency_data", "samples": 0}
    median = statistics.median(latencies_ms)
    for (low, high), contribution in zip(LATENCY_BANDS, LATENCY_CONTRIBUTION):
        if low <= median < high:
            return {
                "value": contribution,
                "included": True,
                "samples": len(latencies_ms),
                "median_ms": median,
                "band": f"{int(low)}-{('inf' if high == float('inf') else int(high))}ms",
            }
    return {"value": 0.0, "included": False, "reason": "unbanded", "samples": len(latencies_ms)}


def _recontact_component(recontact_count: int) -> Dict[str, Any]:
    return {
        "value": RECONTACT_CONTRIBUTIONS.get(recontact_count, 34.0),
        "included": True,
        "recontacts": recontact_count,
        "window_hours": RECONTACT_WINDOW_HOURS,
    }


#: Weights for the behavioural composite. Self-report is optional, so when it
#: is missing the remaining two components are re-weighted rather than counted
#: as a reassuring zero.
COMPONENT_WEIGHTS = {"latency": 0.30, "recontact": 0.35, "self_report": 0.35}


def compute_behavioral_score(
    latencies_ms: Optional[Sequence[int]] = None,
    recontact_count: int = 0,
    self_report_answers: Optional[Dict[str, Any]] = None,
) -> BehavioralResult:
    """Normalised 0-100 behavioural score, with every contribution itemised."""
    latency = _latency_component([l for l in (latencies_ms or []) if l is not None and l >= 0])
    recontact = _recontact_component(max(0, int(recontact_count or 0)))
    self_report = normalize_self_report(self_report_answers)

    parts: Dict[str, float] = {}
    if latency.get("included"):
        parts["latency"] = float(latency["value"])
    parts["recontact"] = float(recontact["value"])
    if self_report.get("included"):
        parts["self_report"] = float(self_report["value"])

    notes: List[str] = []
    if not parts:
        return BehavioralResult(
            score=0.0,
            confidence=0.1,
            components={"latency": latency, "recontact": recontact, "self_report": self_report},
            notes=["No behavioural signal available yet."],
        )

    total_weight = sum(COMPONENT_WEIGHTS[k] for k in parts)
    score = sum(COMPONENT_WEIGHTS[k] * v for k, v in parts.items()) / total_weight

    if latency.get("included") and latency.get("band", "").startswith(("0-800", "20000")):
        notes.append("Response latency outside the conversational range.")
    if recontact["recontacts"] >= 2:
        notes.append(f"Re-contacted {recontact['recontacts']}x within {int(RECONTACT_WINDOW_HOURS)}h.")
    if self_report.get("included"):
        notes.append(f"Self-report: {self_report['answered']} of {len(SELF_REPORT_ITEMS)} items answered.")
    else:
        notes.append("Self-report incomplete; weight re-balanced across available signals.")

    included = len(parts)
    confidence = round(min(0.75, 0.28 + 0.16 * included), 3)

    return BehavioralResult(
        score=round(max(0.0, min(100.0, score)), 2),
        confidence=confidence,
        components={"latency": latency, "recontact": recontact, "self_report": self_report},
        notes=notes,
    )


def self_report_schema() -> List[Dict[str, Any]]:
    """Sent to the frontend so the item list is defined in exactly one place."""
    return [
        {
            "key": item["key"],
            "i18n_key": item["i18n_key"],
            "options": SCALES.get(item["key"], []),
        }
        for item in SELF_REPORT_ITEMS
    ]
