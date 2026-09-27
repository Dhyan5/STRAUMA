"""Scoring engine: SVI weights, bands, and the Critical Override."""

from __future__ import annotations

import pytest

from engine.recommendations import MANDATORY_BEFORE_CRITICAL_CLOSE, generate_recommendations
from engine.svi import (
    BANDS,
    MAX_REPEAT_BONUS,
    OVERRIDE_REASONS,
    WEIGHTS_TEXT_ONLY,
    WEIGHTS_WITH_VOICE,
    category_for,
    compute_svi,
)
from nlp.lexicons import TIER_CRITICAL
from nlp.text_analyzer import analyze_text


def test_voice_weights_match_the_brief():
    assert WEIGHTS_WITH_VOICE == {"text": 0.40, "vocal": 0.35, "behavioral": 0.25}


def test_text_only_weights_match_the_brief():
    assert WEIGHTS_TEXT_ONLY == {"text": 0.60, "behavioral": 0.40}


def test_voice_formula_is_the_documented_arithmetic():
    result = compute_svi(
        text_score=100.0,
        vocal_score=50.0,
        behavioral_score=0.0,
        lexical_confidence=1.0,
    )
    assert result.composite_score == pytest.approx(0.40 * 100 + 0.35 * 50)


def test_text_only_formula_is_the_documented_arithmetic():
    result = compute_svi(text_score=100.0, vocal_score=None, behavioral_score=50.0, lexical_confidence=1.0)
    assert result.composite_score == pytest.approx(0.60 * 100 + 0.40 * 50)


def test_bands_are_contiguous_and_cover_zero_to_one_hundred():
    assert BANDS[0]["min"] == 0
    assert BANDS[-1]["max"] == 100
    for current, following in zip(BANDS, BANDS[1:]):
        assert current["max"] + 1 == following["min"], f"gap or overlap at {current['category']}"


def test_band_sla_hours_match_the_brief():
    sla = {band["category"]: band["sla_hours"] for band in BANDS}
    assert sla == {"Low": 120, "Moderate": 48, "High": 2, "Critical": 0}


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, "Low"),
        (24, "Low"),
        (25, "Moderate"),
        (49, "Moderate"),
        (50, "High"),
        (74, "High"),
        (75, "Critical"),
        (100, "Critical"),
    ],
)
def test_band_boundaries(score, expected):
    assert category_for(score) == expected


def test_the_text_channel_alone_cannot_reach_the_critical_band():
    """With no behavioural or vocal signal the text channel contributes 60%.
    Reaching Critical on text alone is structurally impossible, which is the
    reason a critical-tier flag can force the band instead."""
    result = compute_svi(text_score=100.0, vocal_score=None, behavioral_score=0.0)
    assert result.composite_score == pytest.approx(60.0)
    assert result.category != "Critical"


def test_a_critical_flag_forces_critical_from_a_low_composite():
    """The override is the whole point: a low number must not hide a crisis."""
    result = compute_svi(
        text_score=3.0,
        vocal_score=None,
        behavioral_score=1.0,
        critical_occurrences=["self_harm_ideation"],
    )
    assert result.composite_score < 25
    assert result.category == "Critical"
    assert result.override_reason
    assert "self_harm_ideation" in result.critical_flags


def test_override_reason_is_mapped_to_plain_english():
    result = compute_svi(
        text_score=1.0,
        vocal_score=None,
        behavioral_score=1.0,
        critical_occurrences=["child_safety_concern"],
    )
    assert OVERRIDE_REASONS["child_safety_concern"] in result.override_reason
    # The UI-facing reason must not be the raw internal token.
    assert "child_safety_concern" not in result.override_reason


def test_no_override_without_a_critical_flag():
    result = compute_svi(
        text_score=99.0,
        vocal_score=None,
        behavioral_score=0.0,
        risk_flags=["hopelessness", "isolation"],
        critical_occurrences=[],
    )
    assert result.override_reason is None
    assert result.category == "High"  # 0.6 * 99 = 59.4


def test_high_tier_flags_do_not_trip_the_override():
    """`threat_language` is high-tier. It must not be able to force the top band."""
    result = compute_svi(
        text_score=10.0,
        vocal_score=None,
        behavioral_score=5.0,
        risk_flags=["threat_language"],
        critical_occurrences=[],
    )
    assert result.override_reason is None
    assert result.category != "Critical"


def test_repeated_critical_signals_add_a_capped_bonus():
    once = compute_svi(text_score=10.0, vocal_score=None, behavioral_score=10.0, critical_occurrences=["immediate_danger"])
    thrice = compute_svi(
        text_score=10.0,
        vocal_score=None,
        behavioral_score=10.0,
        critical_occurrences=["immediate_danger", "immediate_danger", "immediate_danger"],
    )
    assert thrice.composite_score > once.composite_score
    assert thrice.composite_score - once.composite_score <= MAX_REPEAT_BONUS


def test_child_safety_is_critical_tier_in_every_curated_lexicon():
    """`OVERRIDE_REASONS` promises this flag can force the override, so the
    lexicons have to agree that it is critical-tier."""
    from nlp.lexicons import TIER_CRITICAL, all_lexicons

    for code, lex in all_lexicons().items():
        spec = lex.flags.get("child_safety_concern")
        if spec is None:
            continue
        assert spec.get("tier") == TIER_CRITICAL, f"{code} has child_safety_concern as {spec.get('tier')}"


def test_every_override_reason_names_a_flag_the_lexicons_declare_critical():
    from nlp.lexicons import TIER_CRITICAL, all_lexicons

    declared = {
        name
        for lex in all_lexicons().values()
        for name, spec in lex.flags.items()
        if spec.get("tier") == TIER_CRITICAL
    }
    assert set(OVERRIDE_REASONS) <= declared, f"not critical-tier anywhere: {set(OVERRIDE_REASONS) - declared}"


def test_critical_tier_includes_the_indicators_we_care_about():
    for flag in ("self_harm_ideation", "immediate_danger", "ongoing_violence", "child_safety_concern"):
        assert flag in OVERRIDE_REASONS


# --------------------------------------------------------------------------
# The override is driven by the lexicon's own tier, not a duplicate list
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,language,expect_critical",
    [
        ("I want to kill myself.", "en", True),
        ("He is beating me right now.", "en", True),
        ("My child is locked in a room and I am scared.", "en", True),
        ("He keeps threatening me.", "en", False),
        ("I have not slept in three days.", "en", False),
        ("मैं खुद को मारना चाहता हूँ।", "hi", True),
        ("वो मुझ पर हमला कर रहा है।", "hi", True),
    ],
)
def test_only_critical_tier_language_triggers_the_override(text, language, expect_critical):
    result = analyze_text(text, language=language)
    tiers = {d["flag"]: d["tier"] for d in result.flag_details}
    critical_hits = [flag for flag, tier in tiers.items() if tier == TIER_CRITICAL]
    assert bool(critical_hits) is expect_critical, f"{text!r} -> {tiers}"


# --------------------------------------------------------------------------
# Recommendations
# --------------------------------------------------------------------------


def test_critical_always_requires_a_bridge_and_a_safety_contact():
    actions = generate_recommendations("Critical", ["self_harm_ideation"])["actions"]
    for required in MANDATORY_BEFORE_CRITICAL_CLOSE:
        assert required in actions


def test_low_band_asks_for_no_intervention_beyond_an_optional_callback():
    """Low means resources and an optional callback - never a referral."""
    actions = set(generate_recommendations("Low", [])["actions"])
    assert actions == {"resource_information", "counselling"}
    for escalated in ("emergency_bridge", "safety_contact", "medical", "legal_aid", "police_liaison", "witness_protection"):
        assert escalated not in actions


def test_recommendations_are_deterministic_and_order_independent():
    a = generate_recommendations("High", ["hopelessness", "isolation"])
    b = generate_recommendations("High", ["isolation", "hopelessness"])
    assert a["actions"] == b["actions"]
    assert a["summary"] == b["summary"]


def test_critical_summary_leads_with_the_human_requirement():
    assert generate_recommendations("Critical", [])["summary"].startswith("Immediate human response required.")


def test_every_recommendation_always_asks_for_a_human():
    """The system never recommends handling a case on its own."""
    for category in ("Low", "Moderate", "High", "Critical"):
        assert generate_recommendations(category, [])["requires_human_action"] is True
