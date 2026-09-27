"""Channel parity, determinism, language handling, and response contracts.

Channel parity is the claim that chat, voice and IVRS are first-class rather
than chat with a voice button bolted on. The way to make that testable is to
drive the same underlying case through all three channels and assert the
pipeline treats them identically.
"""

from __future__ import annotations

import pytest

from conftest import submit
from nlp.lexicons import supported_languages


def _open(client, headers, channel="chat", language="en"):
    r = client.post("/api/cases", json={"channel": channel, "language": language}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --------------------------------------------------------------------------
# Channel parity
# --------------------------------------------------------------------------


@pytest.mark.parametrize("channel", ["chat", "ivrs", "voice"])
def test_every_channel_is_accepted_at_case_creation(client, complainant, channel):
    r = client.post("/api/cases", json={"channel": channel, "language": "en"}, headers=complainant["headers"])
    assert r.status_code == 201
    assert r.json()["channel"] == channel


def test_an_unknown_channel_is_refused(client, complainant):
    r = client.post("/api/cases", json={"channel": "telepathy", "language": "en"}, headers=complainant["headers"])
    assert r.status_code == 422


def test_chat_and_ivrs_reach_the_same_pipeline(client, complainant, counsellor):
    """Same words, two channels, same band. If these diverge, one channel is a
    second-class citizen."""
    chat_case = _open(client, complainant["headers"], "chat")
    ivrs_case = _open(client, complainant["headers"], "ivrs")
    text = "I want to kill myself and I cannot go on like this."

    submit(client, complainant["headers"], chat_case, text, 30000)
    r = client.post(
        "/api/interactions",
        headers=complainant["headers"],
        json={
            "case_id": ivrs_case,
            "channel": "ivrs",
            "transcribed_text": text,
            "keypad_presses": "1#0#9",
            "response_latency_ms": 30000,
        },
    )
    assert r.status_code == 201, r.text

    queue = {item["case_ref"]: item for item in client.get("/api/counsellor/queue", headers=counsellor["headers"]).json()}
    chat_ref = client.get(f"/api/cases/{chat_case}/status", headers=complainant["headers"]).json()["reference"]
    ivrs_ref = client.get(f"/api/cases/{ivrs_case}/status", headers=complainant["headers"]).json()["reference"]

    assert queue[chat_ref]["category"] == queue[ivrs_ref]["category"] == "Critical"
    assert queue[chat_ref]["is_critical_override"] is queue[ivrs_ref]["is_critical_override"] is True


def test_a_voice_turn_is_analysed_and_labelled_synthetic(client, complainant, counsellor):
    case_id = _open(client, complainant["headers"], "voice")
    r = client.post(
        "/api/interactions/demo-voice",
        headers=complainant["headers"],
        params={"case_id": case_id, "stressed": "true", "transcript": "I am not coping"},
    )
    assert r.status_code == 201, r.text
    detail = client.get(f"/api/counsellor/queue/{case_id}", headers=counsellor["headers"]).json()
    voice_turn = detail["interactions"][0]
    assert voice_turn["channel"] == "voice"
    analysis = voice_turn["audio_analysis"]
    assert analysis is not None
    # A computer-generated signal must never be presented as a measurement.
    assert analysis["method"] == "heuristic-demo"
    assert analysis["vocal_stress_score"] is not None
    assert "synthetic_demo" in (analysis["notes"] or "")


def test_an_uploaded_voice_turn_is_accepted_and_analysed(client, complainant):
    from config import settings
    from nlp.audio_analyzer import generate_demo_clip

    case_id = _open(client, complainant["headers"], "voice")
    clip = generate_demo_clip(settings.upload_dir / "pytest_upload.wav", 4.0, True)
    with open(clip, "rb") as handle:
        r = client.post(
            "/api/interactions/audio",
            headers=complainant["headers"],
            data={"case_id": case_id, "channel": "voice", "provenance": "synthetic_demo", "transcript": "I need help"},
            files={"audio": ("clip.wav", handle.read(), "audio/wav")},
        )
    assert r.status_code == 201, r.text
    assert r.json()["reference"]


def test_an_empty_upload_is_refused(client, complainant):
    case_id = _open(client, complainant["headers"], "voice")
    r = client.post(
        "/api/interactions/audio",
        headers=complainant["headers"],
        data={"case_id": case_id, "channel": "voice", "provenance": "synthetic_demo"},
        files={"audio": ("clip.wav", b"", "audio/wav")},
    )
    assert r.status_code == 422


def test_an_oversized_upload_is_refused(client, complainant):
    case_id = _open(client, complainant["headers"], "voice")
    r = client.post(
        "/api/interactions/audio",
        headers=complainant["headers"],
        data={"case_id": case_id, "channel": "voice", "provenance": "synthetic_demo"},
        files={"audio": ("clip.wav", b"RIFF" + b"0" * (13 * 1024 * 1024), "audio/wav")},
    )
    assert r.status_code == 413


def test_a_mislabelled_provenance_is_refused(client, complainant):
    case_id = _open(client, complainant["headers"], "voice")
    r = client.post(
        "/api/interactions/demo-voice",
        headers=complainant["headers"],
        params={"case_id": case_id},
    )
    assert r.status_code == 201
    # and the explicit one
    r = client.post(
        "/api/interactions/audio",
        headers=complainant["headers"],
        data={"case_id": case_id, "channel": "voice", "provenance": "genuinely-measured"},
        files={"audio": ("clip.wav", b"RIFF0000WAVEfmt ", "audio/wav")},
    )
    assert r.status_code == 422


def test_an_empty_message_is_refused(client, complainant, case_id):
    r = client.post(
        "/api/interactions",
        headers=complainant["headers"],
        json={"case_id": case_id, "channel": "chat"},
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_the_same_words_score_the_same_way_twice(client, complainant):
    first = _open(client, complainant["headers"])
    second = _open(client, complainant["headers"])
    text = "I have not slept in three days and I feel hopeless."
    submit(client, complainant["headers"], first, text, 20000)
    submit(client, complainant["headers"], second, text, 20000)
    views = [
        client.get(f"/api/cases/{cid}/status", headers=complainant["headers"]).json()["urgency"]
        for cid in (first, second)
    ]
    assert views[0] == views[1]


def test_a_peak_signal_is_not_diluted_by_a_later_calm_message(client, complainant, counsellor):
    """A distress signal that was expressed is expressed. A later 'sorry,
    never mind' must not drop the case out of the queue."""
    case_id = _open(client, complainant["headers"])
    submit(client, complainant["headers"], case_id, "I want to kill myself.", 30000)
    submit(client, complainant["headers"], case_id, "Sorry, that was nothing. I am fine.", 5000)

    ref = client.get(f"/api/cases/{case_id}/status", headers=complainant["headers"]).json()["reference"]
    item = next(
        i for i in client.get("/api/counsellor/queue", headers=counsellor["headers"]).json() if i["case_ref"] == ref
    )
    assert item["category"] == "Critical"
    assert item["is_critical_override"] is True


def test_the_repeat_critical_bonus_does_not_run_away(client, complainant, counsellor):
    case_id = _open(client, complainant["headers"])
    for _ in range(6):
        submit(client, complainant["headers"], case_id, "I want to kill myself.", 30000)
    ref = client.get(f"/api/cases/{case_id}/status", headers=complainant["headers"]).json()["reference"]
    item = next(
        i for i in client.get("/api/counsellor/queue", headers=counsellor["headers"]).json() if i["case_ref"] == ref
    )
    assert 0 <= item["composite_score"] <= 100


# --------------------------------------------------------------------------
# Languages
# --------------------------------------------------------------------------


def test_all_six_languages_are_advertised():
    codes = {entry["code"] for entry in supported_languages()}
    assert codes == {"en", "hi", "bn", "mr", "ta", "te"}


def test_english_and_hindi_have_curated_copy(client):
    for language in ("en", "hi"):
        r = client.get(f"/api/i18n/strings?language={language}")
        body = r.json()
        assert body["curated"] is True
        assert body["fallback"] is False
        assert body["language"] == language
        assert body["strings"], language


@pytest.mark.parametrize("language", ["bn", "mr", "ta", "te"])
def test_stub_languages_fall_back_loudly_rather_than_guessing(client, language):
    """The caller must learn that it did not get the language it asked for,
    otherwise a frontend would label English text as Bengali."""
    body = client.get(f"/api/i18n/strings?language={language}").json()
    assert body["curated"] is False
    assert body["fallback"] is True
    assert body["language"] == "en"
    assert body["requested_language"] == language
    assert language in body["fallback_reason"]


def test_a_case_can_be_opened_in_hindi(client, complainant):
    case_id = _open(client, complainant["headers"], "chat", "hi")
    r = client.post(
        "/api/interactions",
        headers=complainant["headers"],
        json={"case_id": case_id, "channel": "chat", "text": "मैं बहुत अकेला हूँ और नींद नहीं आती।", "response_latency_ms": 15000},
    )
    assert r.status_code == 201
    assert r.json()["view"]["urgency"] in ("routine", "soon")


def test_hindi_critical_language_is_detected_end_to_end(client, complainant, counsellor):
    case_id = _open(client, complainant["headers"], "chat", "hi")
    submit(client, complainant["headers"], case_id, "मैं खुद को मारना चाहता हूँ।", 30000)
    ref = client.get(f"/api/cases/{case_id}/status", headers=complainant["headers"]).json()["reference"]
    item = next(
        i for i in client.get("/api/counsellor/queue", headers=counsellor["headers"]).json() if i["case_ref"] == ref
    )
    assert item["category"] == "Critical"
    assert item["is_critical_override"] is True


def test_an_unsupported_language_is_refused_at_registration(client):
    r = client.post("/api/auth/register", json={"role": "complainant", "language_pref": "xx"})
    assert r.status_code == 422


# --------------------------------------------------------------------------
# Response contracts
# --------------------------------------------------------------------------


def test_staff_case_detail_decodes_its_json_columns(client, complainant, case_id, counsellor):
    submit(client, complainant["headers"], case_id, "I want to kill myself.", 30000)
    body = client.get(f"/api/counsellor/queue/{case_id}", headers=counsellor["headers"]).json()
    assert isinstance(body["svi"]["weights"], dict) and body["svi"]["weights"]
    assert isinstance(body["recommendation"]["actions"], list) and body["recommendation"]["actions"]
    assert isinstance(body["interactions"][0]["text_analysis"]["risk_flags"], list)
    assert body["disclaimer"]
    assert body["method_note"]
    assert "Text engine:" in body["method_note"]


def test_self_report_is_stored_and_reaches_the_behavioural_score(client, complainant, case_id, counsellor):
    schema = client.get("/api/self-report/schema").json()
    answers = {item["key"]: item["options"][-1]["value"] for item in schema}
    r = client.post(
        "/api/interactions",
        headers=complainant["headers"],
        json={
            "case_id": case_id,
            "channel": "chat",
            "text": "I am not doing well.",
            "response_latency_ms": 20000,
            "self_report": answers,
        },
    )
    assert r.status_code == 201, r.text
    body = client.get(f"/api/counsellor/queue/{case_id}", headers=counsellor["headers"]).json()
    assert body["behavioral"]["score"] > 0
    assert body["behavioral"]["components"]


def test_the_openapi_document_is_served_and_documents_the_guardrails(client):
    doc = client.get("/openapi.json").json()
    assert doc["info"]["title"].startswith("NHAA 14566")
    assert "Not a diagnostic tool" in doc["info"]["description"]
    for path in ("/api/cases", "/api/counsellor/queue", "/api/law-enforcement/cases", "/api/engines/status"):
        assert path in doc["paths"], path


def test_the_engine_status_endpoint_does_not_overstate_itself(client):
    body = client.get("/api/engines/status").json()
    assert body["audio"]["method_label"] == "heuristic-demo"
    assert "not a trained classifier" in body["audio"]["note"]
    assert body["sentiment"]["method_label"] in ("ml-model", "heuristic")
    assert body["lexicons"]["en"]["requires_professional_signoff"] is True
    assert body["lexicons"]["bn"]["curation_status"] == "STUB"


def test_health_reports_the_active_backends(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["queue_backend"] in ("in-memory", "redis")
    assert body["sentiment_backend"] in ("heuristic", "ml", "auto")


def test_the_rules_endpoint_publishes_the_deterministic_engine(client, state_admin):
    body = client.get("/api/admin/rules", headers=state_admin["headers"]).json()
    assert body["svi_weights"]["with_voice"] == {"text": 0.40, "vocal": 0.35, "behavioral": 0.25}
    assert body["svi_weights"]["text_only"] == {"text": 0.60, "behavioral": 0.40}
    assert body["recommendation_rules"]
    assert all("id" in rule for rule in body["recommendation_rules"])
