"""Victim-facing projection of case state.

This module is the single place where internal assessment state is converted
into words a complainant sees. It exists because the most important safety
property of the whole system is negative: a person in distress must never be
shown a number, a band, or a label.

The projection is therefore *lossy by design*. `to_victim_view` accepts the
full internal state and returns a payload that provably contains no score, no
category, and no flag vocabulary. `tests/test_victim_view.py` asserts that.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config import CRISIS_RESOURCES, DISCLAIMER

#: Anything matching these must never reach a complainant-facing payload.
LEAK_PATTERNS = [
    re.compile(r"\bSVI\b", re.IGNORECASE),
    re.compile(r"\bStress\s+Vulnerability\b", re.IGNORECASE),
    re.compile(r"\brisk\b", re.IGNORECASE),
    re.compile(r"\bscore\b", re.IGNORECASE),
    re.compile(r"\bcategor", re.IGNORECASE),
    re.compile(r"\bCritical\b", re.IGNORECASE),
    re.compile(r"\boverride\b", re.IGNORECASE),
    re.compile(r"\bcomposite\b", re.IGNORECASE),
    re.compile(r"\bflag(?:ged|s)?\b", re.IGNORECASE),
    re.compile(r"\bdiagnos", re.IGNORECASE),
    re.compile(r"\bself[_ -]?harm\b", re.IGNORECASE),
    re.compile(r"\bdepress", re.IGNORECASE),
    re.compile(r"\b\d{1,3}\s*(?:/|out of)\s*100\b", re.IGNORECASE),
    re.compile(r"\bvulnerab", re.IGNORECASE),
]

#: Internal category -> what the complainant is told. Deliberately framed as
#: the *service commitment*, never as a judgement about the person.
CATEGORY_PROMISE = {
    "Low": {
        "headline_key": "done.heading",
        "next_key": "done.callback",
        "urgency": "routine",
    },
    "Moderate": {
        "headline_key": "done.heading",
        "next_key": "done.callback",
        "urgency": "soon",
    },
    "High": {
        "headline_key": "done.heading",
        "next_key": "done.callback",
        "urgency": "priority",
    },
    "Critical": {
        "headline_key": "done.bridge_live",
        "next_key": "done.bridge_live",
        "urgency": "immediate",
    },
}


@dataclass
class VictimView:
    reference: str
    stage: str
    next_step_key: str
    urgency: str
    resources: List[Dict[str, str]]
    disclaimer: str
    i18n_keys: List[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "reference": self.reference,
            "stage": self.stage,
            "next_step_key": self.next_step_key,
            "urgency": self.urgency,
            "resources": self.resources,
            "disclaimer": self.disclaimer,
            "i18n_keys": self.i18n_keys,
        }


def resources_for_victim(language: str = "en") -> List[Dict[str, str]]:
    """Always-visible crisis resources. Present on every victim screen."""
    from nlp import ui_strings

    out: List[Dict[str, str]] = []
    for key, entry in CRISIS_RESOURCES.items():
        name = entry["name_hi"] if language.startswith("hi") else entry["name"]
        out.append(
            {
                "id": key,
                "name": str(name),
                "numbers": [str(n) for n in entry["numbers"]],  # type: ignore[index]
                "description": str(entry["description"]),
            }
        )
    return out


def to_victim_view(
    case_ref: str,
    category: str,
    status: str,
    language: str = "en",
    first_response_at: Optional[dt.datetime] = None,
) -> VictimView:
    """Project internal state into a complainant-safe payload."""
    promise = CATEGORY_PROMISE.get(category, CATEGORY_PROMISE["Low"])
    stage = "received" if status in ("open", "assigned") else status

    return VictimView(
        reference=case_ref,
        stage=stage,
        next_step_key=str(promise["next_key"]),
        urgency=str(promise["urgency"]),
        resources=resources_for_victim(language),
        disclaimer=DISCLAIMER,
        # Keys only. The frontend resolves them through the curated string
        # table, so the server never has to guess which language to render.
        i18n_keys=[
            "done.heading",
            "done.body",
            "done.reference",
            str(promise["next_key"]),
            "done.resources",
            "done.save_reference",
        ],
    )


#: Exact legal text that is required to appear on every screen, verbatim.
#:
#: The mandated disclaimer says "Not a diagnostic tool" and "All risk flags are
#: reviewed by trained personnel", so it necessarily trips two of the patterns
#: above. It is not a leak - it is the opposite of one, and the brief requires it
#: byte-for-byte. The exemption is therefore an exact-match allowlist of approved
#: boilerplate, not a loosening of the patterns. A paraphrase of the disclaimer
#: would *not* be exempt and would correctly fail the check.
def _exempt_texts() -> frozenset:
    texts = {DISCLAIMER}
    for entry in CRISIS_RESOURCES.values():
        texts.add(str(entry.get("disclaimer", "")))
    return frozenset(t for t in texts if t)


EXEMPT_TEXTS = _exempt_texts()


def assert_no_leakage(payload: Dict[str, Any], path: str = "payload") -> List[str]:
    """Recursively assert a payload contains nothing assessment-shaped.

    Returns a list of violations; an empty list means the payload is safe.
    Exposed for the test suite and usable as a cheap runtime self-check.
    """
    violations: List[str] = []
    stack: List[Any] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if re.search(r"svi|score|categor|composite|override|risk", str(key), re.IGNORECASE):
                    violations.append(f"{path}: forbidden key '{key}'")
                stack.append(value)
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
        elif isinstance(node, str):
            if node in EXEMPT_TEXTS:
                continue
            for pattern in LEAK_PATTERNS:
                match = pattern.search(node)
                if match:
                    violations.append(f"{path}: leaked term '{match.group(0)}' in '{node[:80]}'")
    return violations
