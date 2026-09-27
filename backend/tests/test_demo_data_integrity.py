"""The synthetic demo data must keep agreeing with the live engine.

`seed_demo_data.py` carries an `expected_band` for every scenario so the demo
table reads sensibly. Those hints are only useful if they still match what the
engine actually computes. Promoting a lexicon entry to critical tier, or
retuning a weight, silently changes a scenario's band - and a demo table whose
hints lie is worse than no table.

These tests run the real seed against a throwaway database and read the bands
back out of the persisted SVI rows. An earlier version of this file
hand-mirrored `engine.ingest` to avoid the database, and got the recontact
count wrong - which would have made the test a false oracle. The seed is the
thing under test, so let the seed speak for itself.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import seed_demo_data
from engine import ingest
from models import AudioAnalysis


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    """Run the real seed script against its own SQLite file, once."""
    path = tmp_path_factory.mktemp("seed") / "demo.sqlite3"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    seed = seed_demo_data

    original_engine, original_session = seed.engine, seed.SessionLocal
    seed.engine = engine
    seed.SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

    def _reset_schema():
        # Not `seed.init_db()`: that closes over `database.engine`, not ours.
        from models import AuditLog  # noqa: F401  (import registers the mappers)

        seed.Base.metadata.drop_all(bind=engine)
        seed.Base.metadata.create_all(bind=engine)

    original_reset = seed.reset_schema
    seed.reset_schema = _reset_schema

    try:
        results = seed.run(reset=True)
        case_ids = [row["case"].id for row in results]

        db = seed.SessionLocal()
        try:
            persisted = []
            for case_id in case_ids:
                svi = ingest.current_svi(db, case_id)
                assert svi is not None, f"case {case_id} has no persisted SVI row"
                persisted.append(
                    {
                        "category": svi.category,
                        "composite": svi.composite_score,
                        "override": svi.override_reason,
                    }
                )
            voice = db.query(AudioAnalysis).all()
        finally:
            db.close()
    finally:
        seed.engine, seed.SessionLocal = original_engine, original_session
        seed.reset_schema = original_reset
        engine.dispose()

    assert len(results) == len(persisted)
    return {"cases": list(zip(results, persisted)), "audio": voice}


@pytest.fixture(scope="module")
def outcomes(seeded):
    """[(seed result row, persisted SVI row)] for every seeded case."""
    return seeded["cases"]


def test_the_voice_case_is_persisted_and_labelled_synthetic(seeded):
    """`run()` returns no result row for the voice case, so check the stored
    analysis directly: a demo voice must never look like a real measurement."""
    assert len(seeded["audio"]) == len(seed_demo_data.VOICE_CASES)
    for analysis in seeded["audio"]:
        assert analysis.vocal_stress_score is not None
        assert "synthetic" in (analysis.notes or "").lower()
        assert analysis.method != "trained-model"


def test_the_seed_ran_and_persisted_every_case(outcomes):
    assert len(outcomes) == len(seed_demo_data.SAMPLE_CASES)
    assert {row["summary"] for row, _ in outcomes} == {s["summary"] for s in seed_demo_data.SAMPLE_CASES}


def test_every_seeded_case_lands_in_its_authored_band(outcomes):
    """The whole point: the demo table must not lie about the engine."""
    mismatches = [
        (row["hint"], row["summary"], row["category"], row["composite"])
        for row, _ in outcomes
        if row["category"] != row["hint"]
    ]
    assert not mismatches, (
        "Demo scenarios drifted from the engine: "
        + "; ".join(
            f"{hint} ({summary!r}) -> {category} {composite}" for hint, summary, category, composite in mismatches
        )
    )


def test_the_seed_reports_no_band_mismatch_of_its_own(outcomes):
    assert all(row["hint"] == row["category"] for row, _ in outcomes)


def test_the_demo_set_covers_every_band():
    bands = {spec["expected_band"] for spec in seed_demo_data.SAMPLE_CASES}
    assert bands == {"Low", "Moderate", "High", "Critical"}


def test_the_voice_case_is_persisted_and_labelled_synthetic(seeded):
    """`run()` returns no result row for the voice case, so check the stored
    analysis directly: a demo voice must never look like a real measurement."""
    assert len(seeded["audio"]) == len(seed_demo_data.VOICE_CASES)
    for analysis in seeded["audio"]:
        assert analysis.vocal_stress_score is not None
        assert "synthetic" in (analysis.notes or "").lower()
        assert analysis.method != "trained-model"


def test_critical_is_in_practice_reached_through_the_override(outcomes):
    """A property of the design worth stating rather than hiding.

    Text-only weights are 0.6/0.4 and the behavioural component rarely exceeds
    ~20 in real conversations, so the composite reaches 75 only when the text
    score is near saturation. In practice the top band is entered through a
    critical-tier flag and the numeric threshold acts as a backstop.

    If this ever stops holding, a case reaches Critical on the composite alone
    and someone should decide deliberately whether the demo still shows that.
    """
    critical = [(row, svi) for row, svi in outcomes if svi["category"] == "Critical"]
    assert critical, "the demo should include Critical cases"
    score_only = [row["hint"] for row, svi in critical if not svi["override"]]
    assert not score_only, (
        f"{score_only} now reach Critical on the composite alone; decide deliberately "
        "whether the demo should still rely on the override"
    )


def test_the_composite_threshold_is_still_reachable_in_principle():
    """The backstop must not be dead code: saturating all three voice-weighted
    components has to land in Critical without any override."""
    from engine.svi import compute_svi

    result = compute_svi(
        text_score=100.0, vocal_score=100.0, behavioral_score=100.0, risk_flags=[], critical_occurrences=[]
    )
    assert result.composite_score == pytest.approx(100.0)
    assert result.category == "Critical"
    assert result.override_reason is None


def test_an_override_always_lands_in_critical(outcomes):
    for row, svi in outcomes:
        if svi["override"]:
            assert svi["category"] == "Critical", f"{row['hint']} overrode into {svi['category']}"


def test_every_composite_is_a_sane_number(outcomes):
    for row, svi in outcomes:
        assert 0.0 <= svi["composite"] <= 100.0, row["hint"]


def test_demo_voices_are_synthetic_and_named_as_such():
    assert seed_demo_data.VOICE_CASES, "the demo should include a voice case"
    for case in seed_demo_data.VOICE_CASES:
        assert case["provenance"] == "synthetic_demo"
        assert case["channel"] == "voice"


def test_every_staff_account_has_the_district_its_role_needs():
    for account in seed_demo_data.STAFF:
        if account["role"] in ("counsellor", "district_admin"):
            assert account["district"], f"{account['pseudonym_id']} has no district"
        if account["role"] == "state_admin":
            assert account["district"] is None, "a state admin scoped to one district is not state-wide"


def test_the_demo_password_is_obviously_a_demo_password():
    assert seed_demo_data.DEMO_PASSWORD == "demo-counsellor-14566"


def test_no_demo_scenario_contains_something_a_judge_should_not_read_aloud():
    """The scenarios are read on screen during a demo. Keep them non-graphic."""
    banned = ("graphic", "explicit", "pesticide", "hanging", "slit", "gun", "tablet")
    for spec in seed_demo_data.SAMPLE_CASES:
        blob = " ".join(t["text"] for t in spec["text_turns"]).lower()
        for term in banned:
            assert term not in blob, f"{spec['ref_hint']} contains {term!r}"


def test_the_synthetic_labels_survive_into_the_stored_records():
    """The disclaimer and the synthetic marker must be visible in the data a
    judge browses, not only in the console output."""
    for spec in seed_demo_data.SAMPLE_CASES:
        assert spec["ref_hint"] and spec["summary"]
