"""Deterministic recommendation / escalation rules.

This is a rules engine, not a model. Every recommendation is a pure function of
(category, detected flags), the matching rule is reported by id, and the
plain-language summary is generated from the rule text. A reviewer can trace any
recommendation back to a line in this file.

Action tokens and the staff roles allowed to execute them:

    counselling           counsellor / district_admin / state_admin
    legal_aid             counsellor / district_admin / state_admin
    medical               counsellor / district_admin / state_admin
    emergency_bridge      counsellor / district_admin / state_admin  (Critical only)
    police_liaison        counsellor / district_admin / state_admin  (records the referral)
    witness_protection    counsellor / district_admin / state_admin
    safety_contact        counsellor / district_admin / state_admin  (mandatory before a Critical case may close)
    resource_information  auto
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set

from config import SLA_LABELS

RULESET_VERSION = "recommend-v1"

ACTION_LABELS: Dict[str, str] = {
    "counselling": "Counsellor follow-up",
    "legal_aid": "Legal aid referral",
    "medical": "Medical assistance referral",
    "emergency_bridge": "Live counsellor bridge (immediate)",
    "police_liaison": "Police liaison referral",
    "witness_protection": "Witness protection request",
    "safety_contact": "Confirm direct safety contact with the person",
    "resource_information": "Share helpline and resource information",
}

ACTION_DESCRIPTIONS: Dict[str, str] = {
    "counselling": "Route to a trained counsellor for a callback and support plan.",
    "legal_aid": "Connect with a District Legal Services Authority representative for advice on available remedies.",
    "medical": "Refer to a medical professional for a health check and documentation of injuries where relevant.",
    "emergency_bridge": "Open a live voice bridge to an on-duty counsellor. Do not end the contact until a human takes over.",
    "police_liaison": "Record a police-liaison referral so the district nodal officer can assess mandatory-reporting duties.",
    "witness_protection": "Raise a witness-protection request with the district nodal officer.",
    "safety_contact": "Confirm out loud that the person is safe right now and that support is on the way.",
    "resource_information": "Share the always-visible helpline list: Tele MANAS 14416 / 1800-891-4416, Women Helpline 181, Police 112, NHAA 14566.",
}

#: Which roles may execute each action. The API enforces this server-side.
ACTION_ROLES: Dict[str, Set[str]] = {
    "counselling": {"counsellor", "district_admin", "state_admin"},
    "legal_aid": {"counsellor", "district_admin", "state_admin"},
    "medical": {"counsellor", "district_admin", "state_admin"},
    "emergency_bridge": {"counsellor", "district_admin", "state_admin"},
    "police_liaison": {"counsellor", "district_admin", "state_admin"},
    "witness_protection": {"counsellor", "district_admin", "state_admin"},
    "safety_contact": {"counsellor", "district_admin", "state_admin"},
    "resource_information": {"counsellor", "district_admin", "state_admin"},
}

#: Actions that must be recorded by a human before a Critical case can close.
MANDATORY_BEFORE_CRITICAL_CLOSE = ("safety_contact", "emergency_bridge")

#: Actions that make a case visible in the restricted law-enforcement view.
LAW_ENFORCEMENT_ACTIONS = ("police_liaison",)


@dataclass
class Rule:
    id: str
    when_category: Optional[Set[str]]
    when_flags_any: Optional[Set[str]]
    actions: List[str]
    note: str


RULES: List[Rule] = [
    Rule(
        id="R00-always-resources",
        when_category=None,
        when_flags_any=None,
        actions=["resource_information"],
        note="Helpline and resource information is offered at every band, including Low.",
    ),
    Rule(
        id="R10-low",
        when_category={"Low"},
        when_flags_any=None,
        actions=["counselling"],
        note="Low band: optional counsellor callback; resources shared.",
    ),
    Rule(
        id="R20-moderate",
        when_category={"Moderate"},
        when_flags_any=None,
        actions=["counselling", "legal_aid"],
        note="Moderate band: counsellor callback within 24-48h plus legal-aid information.",
    ),
    Rule(
        id="R30-high",
        when_category={"High"},
        when_flags_any=None,
        actions=["counselling", "legal_aid", "medical"],
        note="High band: priority callback within 2h, legal-aid case worker assigned, medical referral offered.",
    ),
    Rule(
        id="R40-critical",
        when_category={"Critical"},
        when_flags_any=None,
        actions=[
            "emergency_bridge",
            "safety_contact",
            "counselling",
            "medical",
            "police_liaison",
            "witness_protection",
        ],
        note=(
            "Critical band: immediate live counsellor bridge, district nodal officer and "
            "police-liaison notified per applicable mandatory-reporting rules, "
            "witness-protection flag raised, emergency medical prompt shown. A human "
            "action is mandatory before this case may be closed."
        ),
    ),
    Rule(
        id="R50-child-safety",
        when_category=None,
        when_flags_any={"child_safety_concern"},
        actions=["legal_aid", "counselling"],
        note="A concern about a child's safety adds legal-aid and counselling regardless of band.",
    ),
    Rule(
        id="R51-immediate-danger-police",
        when_category=None,
        when_flags_any={"immediate_danger", "ongoing_violence"},
        actions=["police_liaison"],
        note="Immediate-danger or ongoing-violence indicators require a recorded police-liaison referral.",
    ),
    Rule(
        id="R52-self-harm-safety-contact",
        when_category=None,
        when_flags_any={"self_harm_ideation"},
        actions=["safety_contact", "medical", "emergency_bridge"],
        note=(
            "Suicidal-ideation indicators require an out-loud safety check and an immediate "
            "human bridge, independent of the composite band."
        ),
    ),
    Rule(
        id="R53-stalking-witness",
        when_category=None,
        when_flags_any={"stalking_surveillance"},
        actions=["witness_protection", "legal_aid"],
        note="Monitoring or stalking indicators raise a witness-protection request.",
    ),
    Rule(
        id="R54-financial-coercion",
        when_category=None,
        when_flags_any={"financial_coercion"},
        actions=["legal_aid", "counselling"],
        note="Economic abuse indicators route to legal aid and a support plan.",
    ),
    Rule(
        id="R55-medical-signs",
        when_category=None,
        when_flags_any={"somatic_distress"},
        actions=["medical"],
        note="Reported physical symptoms are referred for a medical check, not diagnosed here.",
    ),
]

#: Canonical order so the dashboard's one-click buttons always read the same way.
ACTION_ORDER = [
    "emergency_bridge",
    "safety_contact",
    "counselling",
    "legal_aid",
    "medical",
    "police_liaison",
    "witness_protection",
    "resource_information",
]


def _match(rule: Rule, category: str, flags: Set[str]) -> bool:
    if rule.when_category is not None and category not in rule.when_category:
        return False
    if rule.when_flags_any is not None and not (rule.when_flags_any & flags):
        return False
    return True


def generate_recommendations(
    category: str,
    flags: Optional[Sequence[str]] = None,
    override_reason: Optional[str] = None,
    sla_hours: Optional[int] = None,
) -> Dict[str, Any]:
    """Map (category, flags) to a deterministic, human-readable action set."""
    flag_set: Set[str] = set(flags or [])
    actions: List[str] = []
    matched: List[str] = []
    notes: List[str] = []

    for rule in RULES:
        if not _match(rule, category, flag_set):
            continue
        matched.append(rule.id)
        notes.append(f"{rule.id}: {rule.note}")
        for action in rule.actions:
            if action not in actions:
                actions.append(action)

    ordered = [a for a in ACTION_ORDER if a in actions]
    ordered += [a for a in actions if a not in ACTION_ORDER]  # keep unknown tokens visible

    lead = " + ".join(ACTION_LABELS.get(a, a) for a in ordered[:3])
    if len(ordered) > 3:
        lead += f" (+{len(ordered) - 3} more)"
    if category == "Critical":
        lead = f"Immediate human response required. {lead}"
    else:
        lead = f"Recommended: {lead}"

    return {
        "actions": ordered,
        "summary": lead,
        "matched_rules": matched,
        "rule_notes": notes,
        "ruleset_version": RULESET_VERSION,
        "sla_label": SLA_LABELS.get(category, ""),
        "sla_hours": sla_hours,
        "override_reason": override_reason,
        "requires_human_action": True,
        "action_details": [
            {
                "action": action,
                "label": ACTION_LABELS.get(action, action),
                "description": ACTION_DESCRIPTIONS.get(action, ""),
                "allowed_roles": sorted(ACTION_ROLES.get(action, set())),
            }
            for action in ordered
        ],
        "mandatory_before_critical_close": list(MANDATORY_BEFORE_CRITICAL_CLOSE),
        "note": (
            "Decision support for a trained counsellor. Nothing here is a diagnosis and "
            "no action is executed automatically."
        ),
    }


def action_allowed(action: str, role: str) -> bool:
    return role in ACTION_ROLES.get(action, set())


def exposes_to_law_enforcement(actions: Sequence[str]) -> bool:
    """A case enters the restricted police view only via an explicit referral."""
    return bool(set(actions) & set(LAW_ENFORCEMENT_ACTIONS))
