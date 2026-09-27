"""Synthetic demo data for the NHAA 14566 prototype.

    python seed_demo_data.py            # populate
    python seed_demo_data.py --reset    # drop and recreate

=============================================================================
EVERYTHING IN THIS FILE IS SYNTHETIC. It was written by a developer for a
hackathon demo. It is not derived from, and does not resemble, any real
person, complaint or case. The text below is deliberately non-graphic: distress
is represented through tags and plain descriptions of *feelings and situations*,
never through written-out descriptions of violence, abuse or self-harm methods.

Case text is authored so the *scoring engine* produces a spread across all four
bands. It is a test fixture for a rules engine, not a dataset, and must never be
used to train or validate a model.
=============================================================================
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.orm import Session  # noqa: E402

from auth import hash_password  # noqa: E402
from config import CONSENT_VERSION, SLA_HOURS  # noqa: E402
from database import Base, SessionLocal, engine, init_db  # noqa: E402
from engine import ingest  # noqa: E402
from engine.recommendations import MANDATORY_BEFORE_CRITICAL_CLOSE  # noqa: E402
from models import (  # noqa: E402
    AuditLog,
    Case,
    CaseAction,
    CaseAssignment,
    ConsentRecord,
    IdentityDisclosure,
    Interaction,
    NotificationOutbox,
    Recommendation,
    SVIScore,
    TextAnalysis,
    User,
)
from nlp import text_analyzer  # noqa: E402
from utils import dumps, loads, utcnow  # noqa: E402

log = logging.getLogger("seed")

DEMO_PASSWORD = "demo-counsellor-14566"

# --------------------------------------------------------------------------
# Staff accounts
# --------------------------------------------------------------------------

STAFF: List[Dict[str, Any]] = [
    {"role": "counsellor", "pseudonym_id": "staff.counsellor.1", "display_name": "Counsellor A (demo)", "district": "Bhopal"},
    {"role": "counsellor", "pseudonym_id": "staff.counsellor.2", "display_name": "Counsellor B (demo)", "district": "Indore"},
    {"role": "district_admin", "pseudonym_id": "admin.district.mp", "display_name": "District Admin - MP (demo)", "district": "Bhopal"},
    {"role": "state_admin", "pseudonym_id": "admin.state.mp", "display_name": "State Admin - MP (demo)", "district": None},
    {"role": "law_enforcement", "pseudonym_id": "police.liaison.mp", "display_name": "Police Liaison (demo)", "district": None},
]

# --------------------------------------------------------------------------
# Synthetic cases
# --------------------------------------------------------------------------
# `expected_band` is an *authoring hint* for the demo table, not a test
# assertion: the live engine decides. `text_turns` are the messages a
# complainant would send. All are non-graphic.

SAMPLE_CASES: List[Dict[str, Any]] = [
    {
        "ref_hint": "LOW-1",
        "district": "Bhopal",
        "channel": "chat",
        "language": "en",
        "expected_band": "Low",
        "summary": "Wants information on legal options. No distress indicators.",
        "text_turns": [
            {"text": "Hello, I would like to know what options I have regarding a property dispute with my neighbours. Nothing urgent.", "latency_ms": 4200},
            {"text": "Thank you, that is helpful. I will read the information you shared.", "latency_ms": 3100},
        ],
        "self_report": {"safety": 0, "support": 3, "heard": 3, "rest": 2, "urgent": 0},
    },
    {
        "ref_hint": "LOW-2",
        "district": "Indore",
        "channel": "ivrs",
        "language": "hi",
        "expected_band": "Low",
        "summary": "Hindi-language IVRS enquiry about helpline numbers only.",
        "keypad_presses": "1,1,3",
        "text_turns": [
            {"text": "मुझे सिर्फ हेल्पलाइन नंबर चाहिए थे। धन्यवाद।", "latency_ms": 2600},
        ],
        "self_report": {"safety": 0, "support": 2, "heard": 2, "rest": 2, "urgent": 0},
    },
    {
        "ref_hint": "MOD-1",
        "district": "Bhopal",
        "channel": "chat",
        "language": "en",
        "expected_band": "Moderate",
        "summary": "Persistent stress, poor sleep and some hopelessness. Seeking someone to talk to.",
        "text_turns": [
            {"text": "I have not been able to sleep properly for a few weeks. I keep feeling anxious and my chest feels tight.", "latency_ms": 7400},
            {"text": "Work has been very stressful. Sometimes I feel there is no point in trying, and I have nobody to call after that.", "latency_ms": 11000},
        ],
        "self_report": {"safety": 1, "support": 2, "heard": 1, "rest": 1, "urgent": 0},
    },
    {
        "ref_hint": "MOD-2",
        "district": "Indore",
        "channel": "chat",
        "language": "hi",
        "expected_band": "Moderate",
        "summary": "Hindi - isolation and low mood, seeking a callback.",
        "text_turns": [
            {"text": "मैं अकेला हूँ, किसी से बात नहीं होती। नींद भी ठीक से नहीं आती।", "latency_ms": 9500},
            {"text": "काम बहुत तनावपूर्ण है। किसी से बात करना चाहता हूँ।", "latency_ms": 13000},
        ],
        "self_report": {"safety": 1, "support": 1, "heard": 1, "rest": 1, "urgent": 0},
    },
    {
        "ref_hint": "HIGH-1",
        "district": "Bhopal",
        "channel": "chat",
        "language": "en",
        "expected_band": "High",
        "summary": "Repeated threats and intimidation; distrust of support systems.",
        "text_turns": [
            {"text": "He keeps threatening me. He said if I tell anyone he will make things difficult for me.", "latency_ms": 19000},
            {"text": "I am afraid for my safety. I do not have anyone to call. I feel there is no hope in this situation.", "latency_ms": 26000},
            {"text": "I have not slept. My chest feels tight and I keep crying.", "latency_ms": 31000},
        ],
        "self_report": {"safety": 3, "support": 0, "heard": 0, "rest": 0, "urgent": 2},
    },
    {
        "ref_hint": "HIGH-2",
        "district": "Indore",
        "channel": "chat",
        "language": "hi",
        "expected_band": "High",
        "summary": "Hindi - economic coercion plus threats from a family member.",
        "text_turns": [
            {"text": "घर में पैसों के लिए बहुत तनाव है। मुझे धमकाया जाता है।", "latency_ms": 15000},
            {"text": "मेरी मेहनत का पैसा मुझे नहीं मिलता। मैं अकेला हूँ, कोई उम्मीद नहीं है।", "latency_ms": 21000},
        ],
        "self_report": {"safety": 3, "support": 1, "heard": 0, "rest": 1, "urgent": 2},
    },
    {
        # A child locked in a room is a critical-tier child-safety concern, so
        # this is expected to override to Critical even though the composite
        # sits in the High range. Kept as a deliberate demo of the override
        # working in the direction of caution.
        "ref_hint": "CRIT-4",
        "district": "Bhopal",
        "channel": "chat",
        "language": "en",
        "expected_band": "Critical",
        "summary": "Concern expressed about a child's safety at home.",
        "text_turns": [
            {"text": "I am worried about my child. He locks my son in the room and I am scared for him.", "latency_ms": 18000},
            {"text": "I do not know who to call. I feel helpless about this.", "latency_ms": 24000},
        ],
        "self_report": {"safety": 2, "support": 0, "heard": 1, "rest": 1, "urgent": 3},
    },
    {
        "ref_hint": "CRIT-1",
        "district": "Bhopal",
        "channel": "chat",
        "language": "en",
        "expected_band": "Critical",
        "summary": "Non-graphic reference to not wanting to be alive. Exercises the Critical Override.",
        "text_turns": [
            {"text": "I do not want to live any more. I keep thinking about killing myself.", "latency_ms": 22000},
            {"text": "There is no reason to live. I am completely alone and no one would notice.", "latency_ms": 28000},
        ],
        "self_report": {"safety": 3, "support": 0, "heard": 0, "rest": 0, "urgent": 3},
    },
    {
        "ref_hint": "CRIT-2",
        "district": "Indore",
        "channel": "chat",
        "language": "hi",
        "expected_band": "Critical",
        "summary": "Hindi - immediate danger stated plainly. Exercises the Critical Override.",
        "text_turns": [
            {"text": "मुझे अभी मदद चाहिए। वो अभी यहाँ है और मुझे डरा रहा है। मैं भाग नहीं पा रही।", "latency_ms": 12000},
            {"text": "मैं अब और नहीं रहना चाहती। सब छोड़ दूँगी।", "latency_ms": 16000},
        ],
        "self_report": {"safety": 3, "support": 0, "heard": 0, "rest": 0, "urgent": 3},
    },
    {
        "ref_hint": "CRIT-3",
        "district": "Bhopal",
        "channel": "chat",
        "language": "en",
        "expected_band": "Critical",
        "summary": "Ongoing harm plus a crisis statement. Two critical-tier flags on one case.",
        "text_turns": [
            {"text": "He keeps hitting me. I am scared he will hurt me tonight and I cannot get out.", "latency_ms": 11000},
            {"text": "I do not want to be alive. Nobody helps me and I have given up.", "latency_ms": 20000},
        ],
        "self_report": {"safety": 3, "support": 0, "heard": 0, "rest": 0, "urgent": 3},
    },
]


# --------------------------------------------------------------------------
# Seeding
# --------------------------------------------------------------------------


def reset_schema() -> None:
    log.info("Dropping all tables ...")
    Base.metadata.drop_all(bind=engine)
    init_db()


def seed_staff(db: Session) -> Dict[str, User]:
    out: Dict[str, User] = {}
    for spec in STAFF:
        existing = db.query(User).filter(User.pseudonym_id == spec["pseudonym_id"]).first()
        if existing:
            out[spec["role"] + ":" + (spec["district"] or "all")] = existing
            continue
        user = User(
            role=spec["role"],
            pseudonym_id=spec["pseudonym_id"],
            display_name=spec["display_name"],
            district=spec["district"],
            language_pref="en",
            password_hash=hash_password(DEMO_PASSWORD),
        )
        db.add(user)
        db.flush()
        out[spec["role"] + ":" + (spec["district"] or "all")] = user
    db.add(
        AuditLog(
            actor_role="system",
            action="seed_staff",
            target_type="user",
            target_id="seed",
            detail=f"{len(STAFF)} synthetic staff accounts created. DEMO CREDENTIALS ONLY.",
        )
    )
    log.info("Seeded %d staff accounts (password: %s)", len(STAFF), DEMO_PASSWORD)
    return out


def seed_case(
    db: Session,
    spec: Dict[str, Any],
    created_at: dt.datetime,
    rng: random.Random,
) -> Dict[str, Any]:
    user = User(
        role="complainant",
        language_pref=spec["language"],
        district=spec["district"],
    )
    db.add(user)
    db.flush()

    # Complainants are pseudonymous by construction: no identity fields.
    db.add(
        ConsentRecord(
            user_id=user.id,
            version=CONSENT_VERSION,
            channel=spec["channel"],
            granted_at=created_at - dt.timedelta(minutes=2),
        )
    )
    db.add(
        AuditLog(
            actor_id=user.id,
            actor_role="complainant",
            action="case_opened",
            target_type="case",
            target_id=spec["ref_hint"],
            detail="SYNTHETIC demo case",
        )
    )

    case = Case(
        user_id=user.id,
        district=spec["district"],
        channel=spec["channel"],
        language=spec["language"],
        consent_version=CONSENT_VERSION,
        status="open",
        created_at=created_at,
    )
    db.add(case)
    db.flush()

    for turn in spec["text_turns"]:
        interaction = Interaction(
            case_id=case.id,
            channel=spec["channel"],
            raw_text=turn["text"],
            response_latency_ms=turn.get("latency_ms"),
            keypad_presses=spec.get("keypad_presses") if turn is spec["text_turns"][0] else None,
            self_report=dumps(spec["self_report"]) if turn is spec["text_turns"][-1] else None,
            created_at=created_at + dt.timedelta(minutes=5 * (spec["text_turns"].index(turn) + 1)),
        )
        db.add(interaction)
        db.flush()
        result = text_analyzer.analyze_text(turn["text"], language=spec["language"])
        db.add(
            TextAnalysis(
                interaction_id=interaction.id,
                sentiment=result.sentiment,
                sentiment_score=result.sentiment_score,
                risk_flags=dumps(result.risk_flags),
                markers=dumps({**result.markers, "flag_details": result.flag_details}),
                text_risk_score=result.text_risk_score,
                method=result.method,
                confidence=result.confidence,
                lexicon_version=result.lexicon_version,
                created_at=interaction.created_at,
            )
        )
    db.flush()

    outcome = ingest.recompute_svi(db, case, actor=user)
    svi = ingest.current_svi(db, case.id)

    assignment: Optional[CaseAssignment] = None
    if outcome["category"] in ("High", "Critical"):
        ingest.escalate(db, case, outcome, actor=user)
        assignment = (
            db.query(CaseAssignment)
            .filter(CaseAssignment.case_id == case.id)
            .order_by(CaseAssignment.assigned_at.desc())
            .first()
        )
        # Spread SLA states so the admin dashboard shows real variation.
        if assignment is not None:
            if outcome["category"] == "High" and rng.random() < 0.4:
                assignment.sla_due_at = utcnow() - dt.timedelta(minutes=rng.randint(30, 180))
            elif outcome["category"] == "High":
                assignment.sla_due_at = utcnow() + dt.timedelta(minutes=rng.randint(20, 110))
            else:
                assignment.sla_due_at = utcnow() + dt.timedelta(minutes=rng.randint(2, 12))

    # One Critical case gets a recorded police referral so the restricted
    # law-enforcement view has something in it for the demo.
    if spec["ref_hint"] == "CRIT-3" and assignment is not None:
        officer = db.query(User).filter(User.role == "district_admin", User.district == spec["district"]).first()
        db.add(
            CaseAction(
                case_id=case.id,
                actor_id=officer.id if officer else None,
                action="police_liaison",
                note=(
                    "SYNTHETIC DEMO REFERRAL: ongoing harm reported and a crisis statement "
                    "present. Requesting district nodal officer assessment of "
                    "mandatory-reporting duties and an immediate welfare check."
                ),
                created_at=created_at + dt.timedelta(minutes=25),
            )
        )

    # One Critical case is left mid-response with a safety contact already
    # recorded, so the demo can show the human-in-the-loop gate refusing to
    # close it.
    if spec["ref_hint"] == "CRIT-2" and assignment is not None:
        db.add(
            CaseAction(
                case_id=case.id,
                actor_id=assignment.counsellor_id,
                action="safety_contact",
                note="SYNTHETIC DEMO: live counsellor confirmed the person is safe and is staying on the line.",
                created_at=created_at + dt.timedelta(minutes=18),
            )
        )

    db.add(
        AuditLog(
            actor_id=user.id,
            actor_role="system",
            action="seed_case",
            target_type="case",
            target_id=case.ref,
            detail=(
                f"SYNTHETIC DEMO CASE ({spec['ref_hint']}); author_hint={spec['expected_band']}; "
                f"engine={svi.category if svi else '?'}; override={bool(svi and svi.override_reason)}"
            ),
        )
    )
    db.flush()

    return {
        "case": case,
        "category": outcome["category"],
        "composite": outcome["composite_score"],
        "override": outcome["override_reason"],
        "hint": spec["expected_band"],
        "summary": spec["summary"],
    }


VOICE_CASES: List[Dict[str, Any]] = [
    {
        "ref_hint": "VOICE-1",
        "district": "Bhopal",
        "channel": "voice",
        "language": "en",
        # A computer-generated clip analysed by the heuristic demo extractor
        # lands in Low: the synthetic signal is far calmer than a real
        # distressed voice. The case exists to prove the *voice path* is wired
        # end to end, not to be a High example. The stored analysis is labelled
        # `synthetic_demo_signal` so nobody reads it as a measurement.
        "expected_band": "Low",
        "duration_sec": 13.0,
        "stressed": True,
        "provenance": "synthetic_demo",
        "summary": "Synthetic voice turn: fast, unstable pitch with long pauses.",
        "text_turns": [
            {
                "text": "I have not been able to sleep. Everything feels very heavy and I do not know what to do next.",
                "latency_ms": 14000,
            }
        ],
        "self_report": {"safety": 2, "support": 1, "heard": 0, "rest": 0, "urgent": 2},
    },
]


def seed_voice_demo(db: Session) -> None:
    """Seed a synthetic audio turn so the voice path has a stored analysis.

    The clip is computer-generated by `nlp.audio_analyzer.generate_demo_clip` and
    is labelled `synthetic_demo_signal` in the stored notes.
    """
    from nlp.audio_analyzer import generate_demo_clip
    from config import settings

    spec = dict(VOICE_CASES[0])

    user = User(role="complainant", language_pref="en", district=spec["district"])
    db.add(user)
    db.flush()
    db.add(ConsentRecord(user_id=user.id, version=CONSENT_VERSION, channel="voice"))
    case = Case(
        user_id=user.id,
        district=spec["district"],
        channel="voice",
        language="en",
        consent_version=CONSENT_VERSION,
        created_at=utcnow() - dt.timedelta(minutes=40),
    )
    db.add(case)
    db.flush()

    path = generate_demo_clip(
        settings.upload_dir / "seed_demo_voice.wav",
        duration_sec=spec["duration_sec"],
        stressed=spec["stressed"],
    )
    interaction = Interaction(
        case_id=case.id,
        channel="voice",
        audio_ref=str(path),
        transcribed_text=spec["text_turns"][0]["text"],
        response_latency_ms=spec["text_turns"][0]["latency_ms"],
        self_report=dumps(spec["self_report"]),
    )
    db.add(interaction)
    db.flush()
    ingest.persist_audio_analysis(db, interaction, str(path), provenance="synthetic_demo")
    result = text_analyzer.analyze_text(spec["text_turns"][0]["text"], language="en")
    db.add(
        TextAnalysis(
            interaction_id=interaction.id,
            sentiment=result.sentiment,
            sentiment_score=result.sentiment_score,
            risk_flags=dumps(result.risk_flags),
            markers=dumps({**result.markers, "flag_details": result.flag_details}),
            text_risk_score=result.text_risk_score,
            method=result.method,
            confidence=result.confidence,
            lexicon_version=result.lexicon_version,
        )
    )
    db.flush()

    outcome = ingest.recompute_svi(db, case, actor=user)
    if outcome["category"] in ("High", "Critical"):
        ingest.escalate(db, case, outcome, actor=user)

    db.add(
        AuditLog(
            actor_role="system",
            action="seed_voice_case",
            target_type="case",
            target_id=case.ref,
            detail="SYNTHETIC DEMO: computer-generated clip, provenance=synthetic_demo",
        )
    )
    db.flush()
    log.info("Seeded synthetic voice case -> %s (%s)", case.ref, outcome["category"])


def run(reset: bool = False, seed: int = 20260101) -> List[Dict[str, Any]]:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    rng = random.Random(seed)

    if reset:
        reset_schema()
    else:
        init_db()

    db = SessionLocal()
    try:
        existing = db.query(Case).count()
        if existing:
            log.warning(
                "Database already contains %d case(s). Re-run with --reset to rebuild. Skipping seed.",
                existing,
            )
            return []

        seed_staff(db)
        now = utcnow()
        results: List[Dict[str, Any]] = []
        for index, spec in enumerate(SAMPLE_CASES):
            created_at = now - dt.timedelta(hours=len(SAMPLE_CASES) - index, minutes=rng.randint(0, 50))
            results.append(seed_case(db, spec, created_at, rng))
        seed_voice_demo(db)
        db.commit()

        log.info("-" * 78)
        log.info("SYNTHETIC DEMO DATA - ALL CASES ARE FABRICATED. See DEMO_DATA.md.")
        log.info("-" * 78)
        log.info("%-10s %-10s %8s  %-9s %s", "HINT", "ENGINE", "SVI", "OVERRIDE", "CASE REF")
        for row in results:
            log.info(
                "%-10s %-10s %8.1f  %-9s %s",
                row["hint"],
                row["category"],
                row["composite"],
                "YES" if row["override"] else "-",
                row["case"].ref,
            )
        mismatches = [r for r in results if r["hint"] != r["category"]]
        if mismatches:
            log.info(
                "Note: %d case(s) landed in a different band from their authoring hint. "
                "The engine is authoritative; the hint is only a demo expectation.",
                len(mismatches),
            )
        log.info("-" * 78)
        log.info("Staff logins (pseudonym_id / password '%s'):", DEMO_PASSWORD)
        for spec in STAFF:
            log.info("  %-22s %s", spec["pseudonym_id"], spec["role"])
        log.info("-" * 78)
        return results
    finally:
        db.close()


def summarise(db: Optional[Session] = None) -> Dict[str, Any]:
    own = db is None
    session = db or SessionLocal()
    try:
        cases = session.query(Case).all()
        distribution: Dict[str, int] = {}
        overrides = 0
        for case in cases:
            svi = ingest.current_svi(session, case.id)
            if svi is None:
                continue
            distribution[svi.category] = distribution.get(svi.category, 0) + 1
            overrides += 1 if svi.override_reason else 0
        pending = session.query(CaseAction).filter(CaseAction.action.in_(MANDATORY_BEFORE_CRITICAL_CLOSE)).count()
        return {
            "cases": len(cases),
            "risk_distribution": distribution,
            "critical_overrides": overrides,
            "human_safety_actions_recorded": pending,
            "outbox_rows": session.query(NotificationOutbox).count(),
            "svi_rows": session.query(SVIScore).count(),
            "recommendation_rows": session.query(Recommendation).count(),
            "disclosure_rows": session.query(IdentityDisclosure).count(),
        }
    finally:
        if own:
            session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed synthetic demo data (never real personal data).")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables first.")
    parser.add_argument("--summarise", action="store_true", help="Print a summary and exit.")
    args = parser.parse_args()

    if args.summarise:
        import json

        print(json.dumps(summarise(), indent=2))
    else:
        run(reset=args.reset)
