"""Safety guardrails. These are the tests that must never be relaxed.

Each one corresponds to a constraint in the brief, and several assert a
*negative*: that something is absent. A passing suite here is the evidence that
a complainant is never shown a score, that no Critical case closes on its own,
and that over-sharing with a third party requires a human decision.
"""

from __future__ import annotations

import pytest

from conftest import submit
from engine.victim_copy import assert_no_leakage
from nlp import ui_strings

pytestmark = pytest.mark.safety

CRITICAL_TEXT = "I want to kill myself and I cannot go on like this."
THREAT_TEXT = "He keeps threatening me and I am not safe at home."


# --------------------------------------------------------------------------
# Complainants never see a score
# --------------------------------------------------------------------------


def test_status_view_is_leak_free_for_every_band(client, complainant):
    """Walk one case through all four bands and check the payload each time."""
    headers = complainant["headers"]
    r = client.post("/api/cases", json={"channel": "chat", "language": "en"}, headers=headers)
    cid = r.json()["id"]

    samples = [
        ("Work has been been fine lately, thanks for asking.", 6000),
        ("I have not slept for days and I feel there is no point in trying.", 18000),
        (THREAT_TEXT, 26000),
        (CRITICAL_TEXT, 30000),
    ]
    for text, latency in samples:
        r = client.post(
            "/api/interactions",
            headers=headers,
            json={"case_id": cid, "channel": "chat", "text": text, "response_latency_ms": latency},
        )
        assert r.status_code == 201, r.text
        view = r.json()["view"]
        assert assert_no_leakage(view) == [], f"leak in view: {assert_no_leakage(view)}"

    r = client.get(f"/api/cases/{cid}/status", headers=headers)
    assert r.status_code == 200
    assert assert_no_leakage(r.json()) == []


def test_status_view_carries_no_scoring_keys(client, complainant, case_id):
    client.post(
        "/api/interactions",
        headers=complainant["headers"],
        json={"case_id": case_id, "channel": "chat", "text": CRITICAL_TEXT, "response_latency_ms": 30000},
    )
    r = client.get(f"/api/cases/{case_id}/status", headers=complainant["headers"])
    body = r.json()
    assert set(body) == {
        "reference",
        "stage",
        "next_step_key",
        "urgency",
        "resources",
        "disclaimer",
        "i18n_keys",
    }, f"unexpected keys in victim view: {sorted(body)}"
    assert "composite_score" not in body
    assert "category" not in body


def test_the_transcript_endpoint_carries_the_disclaimer(client, complainant, case_id):
    """This surface used to return a bare list with no notice on it. Every
    victim-facing response must carry the prototype disclaimer."""
    from config import DISCLAIMER

    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    r = client.get(f"/api/cases/{case_id}/interactions", headers=complainant["headers"])
    assert r.status_code == 200
    body = r.json()
    assert DISCLAIMER in body["disclaimer"]
    assert body["interactions"], "the transcript should contain the turn just submitted"
    # Still score-free.
    assert "text_analysis" not in body["interactions"][0]
    assert "audio_analysis" not in body["interactions"][0]


def test_interaction_history_exposes_no_analysis(client, complainant, case_id):
    """The transcript must be renderable without leaking the engine's output."""
    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    r = client.get(f"/api/cases/{case_id}/interactions", headers=complainant["headers"])
    assert r.status_code == 200
    rows = r.json()
    assert rows, "expected the submitted turn to come back"
    for row in rows:
        assert "text_analysis" not in row
        assert "audio_analysis" not in row
        assert "response_latency_ms" not in row
        assert "text_risk_score" not in row
        assert "vocal_stress_score" not in row


def test_urgent_urgency_is_allowed_even_though_it_is_not_a_score(client, complainant, case_id):
    """`urgency` is a service commitment, not an assessment. It must be allowed."""
    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    r = client.get(f"/api/cases/{case_id}/status", headers=complainant["headers"])
    assert r.json()["urgency"] == "immediate"


def test_curated_strings_contain_no_assessment_vocabulary():
    for name, table in ui_strings.TABLES.items():
        assert ui_strings.assert_no_score_leakage(name, table) == []


def test_leakage_detector_actually_catches_a_leak():
    """A green leakage test is worthless if the detector is broken."""
    assert assert_no_leakage({"score": 72}) != []
    assert assert_no_leakage({"text": "Your SVI is 72"}) != []
    assert assert_no_leakage({"text": "This is a high risk case"}) != []
    assert assert_no_leakage({"text": "You may be depressed"}) != []
    assert assert_no_leakage({"text": "This looks like a diagnosis"}) != []


def test_the_exemption_is_exact_not_a_loophole():
    """The mandated disclaimer is exempt. A paraphrase is not."""
    from config import DISCLAIMER
    from engine.victim_copy import EXEMPT_TEXTS

    assert DISCLAIMER in EXEMPT_TEXTS
    assert assert_no_leakage({"disclaimer": DISCLAIMER}) == []
    assert assert_no_leakage({"text": "This tool is not a diagnosis or a doctor."}) != []


def test_disclaimer_is_present_on_every_public_and_victim_surface(client, complainant, case_id):
    from config import DISCLAIMER

    surfaces = [
        client.get("/"),
        client.get("/api/health"),
        client.get("/api/crisis-resources"),
        client.get("/api/portal/config"),
        client.get("/api/version"),
        client.get(f"/api/cases/{case_id}/status", headers=complainant["headers"]),
    ]
    for r in surfaces:
        assert r.status_code == 200, r.text
        assert DISCLAIMER in r.text, f"missing disclaimer on a surface: {r.request.url}"
        assert "Not a diagnostic tool" in r.text

    r = client.post("/api/auth/register", json={"role": "complainant"})
    assert r.status_code == 201
    assert r.json()["disclaimer"] == DISCLAIMER


# --------------------------------------------------------------------------
# A Critical case never closes on its own
# --------------------------------------------------------------------------


def test_critical_close_is_refused_before_human_actions(client, complainant, case_id, counsellor):
    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    r = client.post(f"/api/counsellor/cases/{case_id}/resolve", headers=counsellor["headers"])
    assert r.status_code == 409
    assert "Critical" in r.json()["detail"]


def test_critical_close_is_refused_with_a_partial_ledger(client, complainant, case_id, counsellor):
    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    r = client.post(
        f"/api/counsellor/cases/{case_id}/actions",
        headers=counsellor["headers"],
        json={"action": "safety_contact"},
    )
    assert r.status_code == 200
    assert r.json()["still_open_actions"] == ["emergency_bridge"]
    r = client.post(f"/api/counsellor/cases/{case_id}/resolve", headers=counsellor["headers"])
    assert r.status_code == 409


def test_counsellor_cannot_sign_off_a_critical_close(client, complainant, case_id, counsellor):
    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    for action in ("safety_contact", "emergency_bridge"):
        r = client.post(
            f"/api/counsellor/cases/{case_id}/actions",
            headers=counsellor["headers"],
            json={"action": action},
        )
        assert r.status_code == 200, r.text
    r = client.post(f"/api/counsellor/cases/{case_id}/resolve", headers=counsellor["headers"])
    assert r.status_code == 403


def test_admin_can_close_a_critical_case_once_the_ledger_is_complete(
    client, complainant, case_id, counsellor, district_admin
):
    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    for action in ("safety_contact", "emergency_bridge"):
        client.post(
            f"/api/counsellor/cases/{case_id}/actions",
            headers=counsellor["headers"],
            json={"action": action},
        )
    r = client.post(f"/api/counsellor/cases/{case_id}/actions", headers=district_admin["headers"], json={"action": "resolve"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "resolved"


def test_a_non_critical_case_closes_without_the_gate(client, complainant, case_id, counsellor):
    submit(client, complainant["headers"], case_id, "Work has been stressful but I am managing.", 7000)
    r = client.post(f"/api/counsellor/cases/{case_id}/resolve", headers=counsellor["headers"])
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------
# Law-enforcement visibility is opt-in
# --------------------------------------------------------------------------


def _refer(client, case_id, counsellor):
    r = client.post(
        f"/api/counsellor/cases/{case_id}/actions",
        headers=counsellor["headers"],
        json={"action": "police_liaison", "note": "Referred to the district nodal officer."},
    )
    assert r.status_code == 200, r.text


def _le_refs(client, law_enforcement):
    return {item["case_ref"] for item in client.get("/api/law-enforcement/cases", headers=law_enforcement["headers"]).json()}


def _case_ref(client, headers, case_id):
    return client.get(f"/api/cases/{case_id}/status", headers=headers).json()["reference"]


def test_critical_alone_does_not_expose_a_case_to_police(client, complainant, case_id, law_enforcement):
    """A Critical band is not a reason to share with a third party."""
    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    r = client.get("/api/law-enforcement/cases", headers=law_enforcement["headers"])
    assert r.status_code == 200
    ref = _case_ref(client, complainant["headers"], case_id)
    assert ref not in _le_refs(client, law_enforcement)


def test_police_see_nothing_before_a_referral(client, complainant, case_id, counsellor, law_enforcement):
    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    ref = _case_ref(client, complainant["headers"], case_id)
    before = _le_refs(client, law_enforcement)
    assert ref not in before

    _refer(client, case_id, counsellor)
    after = _le_refs(client, law_enforcement)
    # The referral added exactly this case and nothing else appeared on the way.
    assert after - before == {ref}


def test_police_projection_is_minimal(client, complainant, case_id, counsellor, law_enforcement):
    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    _refer(client, case_id, counsellor)
    ref = _case_ref(client, complainant["headers"], case_id)
    item = next(
        i for i in client.get("/api/law-enforcement/cases", headers=law_enforcement["headers"]).json() if i["case_ref"] == ref
    )
    assert set(item) == {
        "case_ref",
        "district",
        "category",
        "override_reason",
        "immediate_action_required",
        "contact_via",
        "recorded_by_role",
        "recorded_at",
        "disclaimer",
    }
    # The referral note, not the engine's internal vocabulary.
    assert item["override_reason"] == "Referred to the district nodal officer."


def test_a_complainant_cannot_opt_themselves_into_police_visibility(client, complainant, case_id, law_enforcement):
    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    ref = _case_ref(client, complainant["headers"], case_id)
    assert ref not in _le_refs(client, law_enforcement)


def test_staff_cannot_reach_the_law_enforcement_view(client, complainant, case_id, counsellor):
    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    for path in ("/api/law-enforcement/cases", "/api/law-enforcement/policy"):
        r = client.get(path, headers=counsellor["headers"])
        assert r.status_code == 403, f"{path} was reachable by a counsellor"


# --------------------------------------------------------------------------
# Consent gates every write
# --------------------------------------------------------------------------


def test_no_case_without_consent(client, raw_complainant):
    r = client.post("/api/cases", json={"channel": "chat", "language": "en"}, headers=raw_complainant["headers"])
    assert r.status_code == 400
    assert "onsent" in r.json()["detail"]


def test_no_analysis_without_consent(client, complainant):
    headers = complainant["headers"]
    r = client.post("/api/cases", json={"channel": "chat", "language": "en"}, headers=headers)
    cid = r.json()["id"]
    assert client.delete("/api/consent/status", headers=headers).status_code == 200
    r = client.post(
        "/api/interactions",
        headers=headers,
        json={"case_id": cid, "channel": "chat", "text": CRITICAL_TEXT},
    )
    assert r.status_code == 400
    assert "onsent" in r.json()["detail"]


# --------------------------------------------------------------------------
# Ownership
# --------------------------------------------------------------------------


def test_a_complainant_cannot_read_another_persons_case(client, complainant, case_id):
    other = client.post("/api/auth/register", json={"role": "complainant"}).json()
    headers = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get(f"/api/cases/{case_id}/status", headers=headers).status_code == 403
    assert client.get(f"/api/cases/{case_id}/interactions", headers=headers).status_code == 403


def test_a_complainant_cannot_write_to_another_persons_case(client, complainant, case_id):
    other = client.post("/api/auth/register", json={"role": "complainant"}).json()
    headers = {"Authorization": f"Bearer {other['access_token']}"}
    r = client.post(
        "/api/interactions",
        headers=headers,
        json={"case_id": case_id, "channel": "chat", "text": "let me in"},
    )
    assert r.status_code == 403
