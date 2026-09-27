"""Complainant-facing endpoints: intake, status, self-report.

Nothing in this router ever returns an SVI, a band, or a flag. The projection
runs through `engine/victim_copy.to_victim_view`, which the test suite asserts
is leak-free.

Access control here is ownership-based: a complainant can only read and write
their own cases, enforced server-side.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from config import CONSENT_VERSION, DISCLAIMER, settings
from database import get_db
from engine import ingest, victim_copy
from engine.behavioral import self_report_schema
from models import Case, ConsentRecord, Interaction, User
from nlp import ui_strings
from nlp.audio_analyzer import generate_demo_clip
from schemas import (
    ActionResponse,
    CaseCreateRequest,
    CaseOut,
    InteractionCreateRequest,
    InteractionEchoOut,
    SelfReportItem,
    VictimCaseView,
)
from security import get_current_user, record
from services import queue
from utils import dumps, loads

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["portal"])

MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def _active_consent(db: Session, user: User) -> Optional[ConsentRecord]:
    return (
        db.query(ConsentRecord)
        .filter(ConsentRecord.user_id == user.id, ConsentRecord.withdrawn_at.is_(None))
        .order_by(ConsentRecord.granted_at.desc())
        .first()
    )


def _own_case(db: Session, user: User, case_id: int) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if case.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your case")
    return case


# --------------------------------------------------------------------------
# Portal bootstrap
# --------------------------------------------------------------------------


@router.get("/portal/config")
def portal_config(language: str = "en") -> Dict[str, Any]:
    """Everything the victim portal needs for its first render.

    Served without authentication on purpose: a person in distress must be able
    to reach the helpline numbers before creating anything.
    """
    return {
        "disclaimer": DISCLAIMER,
        "languages": ui_strings.available_languages(),
        "consent_version": CONSENT_VERSION,
        "quick_exit_url": "https://www.google.com",
        "crisis_resources": victim_copy.resources_for_victim(language),
        "self_report_items": self_report_schema(),
        "channels": [
            {"id": "chat", "label_key": "channel.chat"},
            {"id": "voice", "label_key": "channel.voice"},
            {"id": "ivrs", "label_key": "channel.ivrs"},
        ],
        "strings": {
            language: {key: ui_strings.t(key, language) for key in ui_strings.EN}
            if ui_strings.has_curated_copy(language)
            else {}
            for language in ("en", "hi")
        },
    }


# --------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------


@router.post("/cases", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Case:
    """Open a case. Requires current consent - the API enforces the same rule
    the UI shows."""
    consent = _active_consent(db, user)
    if consent is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Consent must be recorded before a case can be opened",
        )

    case = Case(
        user_id=user.id,
        district=payload.district,
        channel=payload.channel,
        language=payload.language or user.language_pref,
        consent_version=consent.version,
        status="open",
    )
    db.add(case)
    db.flush()
    record(db, user, "case_opened", "case", case.ref, {"channel": case.channel})
    db.commit()
    db.refresh(case)
    return case


@router.get("/cases/{case_id}/status", response_model=VictimCaseView)
def case_status(
    case_id: int,
    language: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VictimCaseView:
    """The complainant's view of their own case. No assessment data."""
    case = _own_case(db, user, case_id)
    svi = ingest.current_svi(db, case.id)
    category = svi.category if svi else "Low"
    view = victim_copy.to_victim_view(
        case_ref=case.ref,
        category=category,
        status=case.status,
        language=language or case.language,
    )
    return VictimCaseView(**view.as_dict())


@router.get("/cases/{case_id}/interactions", response_model=List[InteractionEchoOut])
def list_interactions(
    case_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Interaction]:
    """The complainant's own turns, and nothing the engine made of them.

    This deliberately returns `InteractionEchoOut` rather than `InteractionOut`.
    `InteractionOut` embeds the text and audio analyses, i.e. numeric scores, and
    it is staff-only. The echo keeps the chat transcript renderable while making
    the leak structurally impossible rather than merely filtered out.
    """
    _own_case(db, user, case_id)
    return db.query(Interaction).filter(Interaction.case_id == case_id).order_by(Interaction.created_at).all()


# --------------------------------------------------------------------------
# Intake: text / chat / IVRS
# --------------------------------------------------------------------------


def _finish_ingest(
    db: Session,
    case: Case,
    interaction: Interaction,
    user: User,
    audio_provenance: Optional[str] = None,
) -> Dict[str, Any]:
    """Shared tail for every intake channel: analyse, score, route, notify."""
    case.updated_at = interaction.created_at

    ingest.seed_analysis_for_interaction(db, interaction, case.language)
    if interaction.audio_ref:
        ingest.persist_audio_analysis(db, interaction, interaction.audio_ref, provenance=audio_provenance or "real")

    result = ingest.recompute_svi(db, case, actor=user)
    if result["category"] in ("High", "Critical"):
        ingest.escalate(db, case, result, actor=user)
        from models import CaseAssignment

        assignment = (
            db.query(CaseAssignment)
            .filter(CaseAssignment.case_id == case.id, CaseAssignment.status.in_(("open", "in_progress")))
            .order_by(CaseAssignment.assigned_at.desc())
            .first()
        )
        sla_state_value = ingest.sla_state(assignment, result["category"])
        queue.publish_queue_entry(
            case.ref,
            result["category"],
            sla_state_value,
            bool(result.get("override_reason")),
        )

    record(db, user, "interaction_submitted", "interaction", interaction.id, {"channel": interaction.channel})
    db.commit()

    view = victim_copy.to_victim_view(
        case_ref=case.ref,
        category=result["category"],
        status=case.status,
        language=case.language,
    )
    # The internal result is logged server-side but deliberately NOT returned
    # to a complainant. Staff read it from the staff endpoints.
    log.info(
        "case=%s channel=%s category=%s composite=%s override=%s",
        case.ref,
        interaction.channel,
        result["category"],
        result["composite_score"],
        bool(result.get("override_reason")),
    )
    return {
        "interaction_id": interaction.id,
        "reference": case.ref,
        "view": view.as_dict(),
    }


@router.post("/interactions", status_code=status.HTTP_201_CREATED)
def submit_interaction(
    payload: InteractionCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """The single intake endpoint behind chat, IVRS and text-in-voice.

    All three channels post here, which is what makes channel parity provable
    rather than aspirational.
    """
    case = _own_case(db, user, payload.case_id)
    if _active_consent(db, user) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Consent is required before any message is analysed",
        )
    if not (payload.text or payload.transcribed_text or payload.keypad_presses):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide text, transcribed_text or keypad_presses",
        )

    language = payload.language or case.language
    interaction = Interaction(
        case_id=case.id,
        channel=payload.channel,
        raw_text=payload.text,
        transcribed_text=payload.transcribed_text,
        keypad_presses=payload.keypad_presses,
        response_latency_ms=payload.response_latency_ms,
        self_report=dumps(payload.self_report) if payload.self_report else None,
    )
    db.add(interaction)
    db.flush()
    return _finish_ingest(db, case, interaction, user)


# --------------------------------------------------------------------------
# Intake: voice
# --------------------------------------------------------------------------


@router.post("/interactions/audio", status_code=status.HTTP_201_CREATED)
async def submit_audio(
    request: Request,
    case_id: int = Form(...),
    channel: str = Form("voice"),
    provenance: str = Form("real"),
    transcript: Optional[str] = Form(None),
    response_latency_ms: Optional[int] = Form(None),
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Accept a voice turn.

    `provenance` must be "real" or "synthetic_demo". A synthetic clip is
    labelled as such in the stored analysis and never presented as a
    measurement of a person.
    """
    if channel != "voice":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="channel must be 'voice'")
    if provenance not in ("real", "synthetic_demo"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="provenance must be real|synthetic_demo")

    case = _own_case(db, user, case_id)
    if _active_consent(db, user) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent is required before analysis")

    content = await audio.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Audio exceeds 12 MB limit")
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty audio upload")

    suffix = ".wav" if content[:4] == b"RIFF" else (Path(audio.filename or "clip").suffix or ".bin")
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    target = settings.upload_dir / safe_name
    target.write_bytes(content)

    interaction = Interaction(
        case_id=case.id,
        channel="voice",
        # Absolute path on purpose. A path relative to the project root only
        # resolves when the process happens to be started from that directory,
        # which differs between `uvicorn` in `backend/`, Docker, and the seed
        # script. The stored reference is dereferenced once, at analysis time.
        audio_ref=str(target.resolve()),
        transcribed_text=transcript,
        response_latency_ms=response_latency_ms,
    )
    db.add(interaction)
    db.flush()
    return _finish_ingest(db, case, interaction, user, audio_provenance=provenance)


@router.post("/interactions/demo-voice", status_code=status.HTTP_201_CREATED)
def submit_demo_voice(
    case_id: int,
    stressed: bool = True,
    duration_sec: float = 12.0,
    transcript: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Generate a synthetic clip server-side and run it through the pipeline.

    This exists so a judge demo is never blocked by microphone permissions.
    The signal is computer-generated; the analysis labels it accordingly.
    """
    case = _own_case(db, user, case_id)
    if _active_consent(db, user) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consent is required before analysis")

    path = generate_demo_clip(
        settings.upload_dir / f"demo_{uuid.uuid4().hex}.wav",
        duration_sec=max(2.0, min(30.0, duration_sec)),
        stressed=stressed,
    )
    interaction = Interaction(
        case_id=case.id,
        channel="voice",
        audio_ref=str(path),
        transcribed_text=transcript,
        response_latency_ms=9000 if stressed else 6000,
    )
    db.add(interaction)
    db.flush()
    return _finish_ingest(db, case, interaction, user, audio_provenance="synthetic_demo")


# --------------------------------------------------------------------------
# Self-report
# --------------------------------------------------------------------------


@router.get("/self-report/schema", response_model=List[SelfReportItem])
def self_report_items() -> List[Dict[str, Any]]:
    """The plain-language items, defined in exactly one place on the server."""
    return self_report_schema()


@router.post("/cases/{case_id}/stop")
def stop_contact(
    case_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Honour a request to stop.

    Per the consent copy, stopping means no further messages are analysed. The
    case is left with a human still responsible for it - stopping the portal
    session is not the same as withdrawing a complaint, and we do not
    auto-resolve anything here.
    """
    case = _own_case(db, user, case_id)
    record(db, user, "contact_stopped_by_complainant", "case", case.ref, {"status": case.status})
    db.commit()
    return {
        "reference": case.ref,
        "message": ui_strings.t("done.body", case.language),
        "disclaimer": DISCLAIMER,
        "note": "Your request has been noted. A counsellor may still contact you about what you already shared.",
    }


# --------------------------------------------------------------------------
# Human-in-the-loop confirmations
# --------------------------------------------------------------------------


@router.get("/cases/{case_id}/confirmations", response_model=ActionResponse)
def confirmations(
    case_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActionResponse:
    """What a counsellor still owes this person, in plain terms.

    For a Critical case the portal shows this as "a counsellor is being
    connected now". It is read-only for the complainant: they can see that a
    human step is outstanding, but they cannot tick it off.
    """
    case = _own_case(db, user, case_id)
    svi = ingest.current_svi(db, case.id)
    recommendation = ingest.current_recommendation(db, case.id)
    from engine.recommendations import MANDATORY_BEFORE_CRITICAL_CLOSE

    recorded = {a.action for a in case.actions}
    outstanding = [
        action
        for action in (loads(recommendation.actions, []) if recommendation else [])
        if action in MANDATORY_BEFORE_CRITICAL_CLOSE and action not in recorded
    ]
    return ActionResponse(
        case_ref=case.ref,
        recorded=sorted(recorded),
        status=case.status,
        still_open_actions=outstanding,
        message=ui_strings.t("done.bridge_live" if svi and svi.category == "Critical" else "done.callback", case.language),
    )
