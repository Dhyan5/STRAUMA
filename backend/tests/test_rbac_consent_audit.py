"""Server-side RBAC, consent versioning, and the audit trail.

The brief requires that *every* endpoint enforce authorisation server-side. A
frontend that hides a button is not a control, so these tests check the HTTP
status codes an unauthorised caller actually receives.
"""

from __future__ import annotations

import pytest

from conftest import DEMO_PASSWORD, make_staff, submit

CRITICAL_TEXT = "I want to kill myself."


def _open_case(client, headers, channel="chat", language="en"):
    r = client.post(
        "/api/cases", json={"channel": channel, "language": language}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------


def test_anonymous_callers_cannot_reach_protected_endpoints(client):
    protected = [
        ("GET", "/api/cases/1/status"),
        ("GET", "/api/cases/1/interactions"),
        ("POST", "/api/cases"),
        ("POST", "/api/interactions"),
        ("GET", "/api/counsellor/queue"),
        ("GET", "/api/counsellor/queue/1"),
        ("GET", "/api/admin/analytics"),
        ("GET", "/api/admin/audit"),
        ("GET", "/api/admin/rules"),
        ("GET", "/api/admin/notifications"),
        ("GET", "/api/law-enforcement/cases"),
        ("GET", "/api/law-enforcement/policy"),
        ("GET", "/api/auth/me"),
    ]
    for method, path in protected:
        r = client.request(method, path, json={})
        assert r.status_code in (401, 403), f"{method} {path} returned {r.status_code}"


def test_a_forged_token_is_rejected(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_a_complainant_token_cannot_be_used_as_a_staff_token(client, complainant):
    for path in ("/api/counsellor/queue", "/api/admin/analytics", "/api/law-enforcement/cases"):
        assert client.get(path, headers=complainant["headers"]).status_code == 403


def test_staff_registration_requires_a_password(client):
    r = client.post("/api/auth/register", json={"role": "counsellor"})
    assert r.status_code == 400
    assert "password" in r.json()["detail"].lower()


def test_complainants_cannot_choose_a_staff_role_at_registration_with_a_weak_password(client):
    r = client.post("/api/auth/register", json={"role": "counsellor", "password": "short"})
    assert r.status_code == 422


def test_login_rejects_a_wrong_password(client):
    r = client.post("/api/auth/register", json={"role": "counsellor", "password": DEMO_PASSWORD})
    pid = r.json()["pseudonym_id"]
    r = client.post("/api/auth/login", json={"pseudonym_id": pid, "password": "not-the-password"})
    assert r.status_code == 401


def test_a_complainant_cannot_log_in_because_they_have_no_password(client):
    """Structural, not a policy: there is no credential to present."""
    r = client.post("/api/auth/register", json={"role": "complainant"})
    pid = r.json()["pseudonym_id"]
    r = client.post("/api/auth/login", json={"pseudonym_id": pid, "password": ""})
    assert r.status_code == 401


# --------------------------------------------------------------------------
# Role separation
# --------------------------------------------------------------------------


def test_counsellors_cannot_reach_admin_analytics(client, counsellor):
    for path in ("/api/admin/analytics", "/api/admin/audit", "/api/admin/rules", "/api/admin/notifications"):
        assert client.get(path, headers=counsellor["headers"]).status_code == 403, path


def test_counsellors_cannot_reach_the_police_view(client, counsellor):
    for path in ("/api/law-enforcement/cases", "/api/law-enforcement/policy"):
        assert client.get(path, headers=counsellor["headers"]).status_code == 403, path


def test_admins_cannot_reach_the_police_view_either(client, district_admin, state_admin):
    """Police visibility is recorded by a counsellor or admin, but the police
    *view* belongs to the police role alone."""
    for admin in (district_admin, state_admin):
        assert client.get("/api/law-enforcement/cases", headers=admin["headers"]).status_code == 403


def test_district_admin_is_confined_to_their_district(client, complainant, district_admin):
    client.post("/api/auth/register", json={"role": "district_admin", "password": DEMO_PASSWORD, "district": "Kerala"})
    scoped = make_staff(client, "district_admin", district="Kerala")
    r = _open_case(client, complainant["headers"])
    assert client.get(f"/api/counsellor/queue/{r}", headers=scoped["headers"]).status_code == 403
    assert client.get("/api/admin/analytics", headers=scoped["headers"]).json()["scope"] == "district:Kerala"


def test_an_unscoped_district_admin_sees_the_whole_state(client, complainant, district_admin):
    _open_case(client, complainant["headers"])
    r = client.get("/api/admin/analytics", headers=district_admin["headers"])
    assert r.json()["scope"] == "state"
    assert r.json()["total_cases"] >= 1


# --------------------------------------------------------------------------
# Action permissions
# --------------------------------------------------------------------------


def test_the_action_catalogue_tells_the_ui_what_each_role_may_do(client, counsellor):
    r = client.get("/api/counsellor/actions/catalogue", headers=counsellor["headers"])
    assert r.status_code == 200
    body = r.json()
    assert set(body["mandatory_before_critical_close"]) == {"safety_contact", "emergency_bridge"}
    assert all("allowed" in entry for entry in body["actions"])


def test_an_unknown_action_is_refused(client, case_id, counsellor):
    r = client.post(
        f"/api/counsellor/cases/{case_id}/actions",
        headers=counsellor["headers"],
        json={"action": "close_everything_and_forget"},
    )
    assert r.status_code == 422


def test_an_action_on_a_missing_case_is_a_404(client, counsellor):
    r = client.post(
        "/api/counsellor/cases/999999/actions", headers=counsellor["headers"], json={"action": "note"}
    )
    assert r.status_code == 404


# --------------------------------------------------------------------------
# Consent
# --------------------------------------------------------------------------


def test_consent_status_is_404_before_any_consent(client, raw_complainant):
    r = client.get("/api/consent/status", headers=raw_complainant["headers"])
    assert r.status_code == 404
    assert "consent" in r.json()["detail"].lower()


def test_the_case_records_the_consent_version_it_was_opened_under(client, complainant):
    r = client.post("/api/cases", json={"channel": "chat", "language": "en"}, headers=complainant["headers"])
    assert r.json()["consent_version"] == "v1.0-demo"


def test_withdrawing_consent_keeps_the_record_but_marks_it(client, complainant):
    r = client.delete("/api/consent/status", headers=complainant["headers"])
    assert r.status_code == 200
    assert r.json()["withdrawn_at"] is not None
    # A second withdrawal has nothing to withdraw.
    assert client.delete("/api/consent/status", headers=complainant["headers"]).status_code == 404


def test_consent_can_be_granted_again_after_withdrawal(client, raw_complainant):
    headers = raw_complainant["headers"]
    assert client.post("/api/consent", json={"version": "v1.0-demo"}, headers=headers).status_code == 201
    assert client.delete("/api/consent/status", headers=headers).status_code == 200
    assert client.post("/api/consent", json={"version": "v1.0-demo"}, headers=headers).status_code == 201
    assert client.post("/api/cases", json={"channel": "chat"}, headers=headers).status_code == 201


@pytest.mark.parametrize("channel", ["chat", "voice", "ivrs"])
def test_consent_can_be_given_per_channel(client, raw_complainant, channel):
    r = client.post(
        "/api/consent", json={"version": "v1.0-demo", "channel": channel}, headers=raw_complainant["headers"]
    )
    assert r.status_code == 201
    assert r.json()["channel"] == channel


def test_an_invalid_consent_channel_is_refused(client, raw_complainant):
    r = client.post("/api/consent", json={"version": "v1.0-demo", "channel": "telepathy"}, headers=raw_complainant["headers"])
    assert r.status_code == 422


# --------------------------------------------------------------------------
# Audit trail
# --------------------------------------------------------------------------


def test_reading_a_case_is_audited(client, complainant, case_id, counsellor, state_admin):
    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    assert client.get(f"/api/counsellor/queue/{case_id}", headers=counsellor["headers"]).status_code == 200
    rows = client.get("/api/admin/audit?limit=500", headers=state_admin["headers"]).json()
    views = [r for r in rows if r["action"] == "view_case"]
    assert views, "viewing a case must leave an audit row"
    assert views[0]["target_id"]
    assert views[0]["actor_role"] == "counsellor"


def test_reading_the_queue_is_audited(client, counsellor, state_admin):
    client.get("/api/counsellor/queue", headers=counsellor["headers"])
    rows = client.get("/api/admin/audit?limit=500", headers=state_admin["headers"]).json()
    assert any(r["action"] == "view_queue" for r in rows)


def test_a_human_action_is_audited_with_a_timestamp(client, case_id, counsellor, state_admin):
    client.post(
        f"/api/counsellor/cases/{case_id}/actions",
        headers=counsellor["headers"],
        json={"action": "note", "note": "Called, left a voicemail."},
    )
    rows = client.get("/api/admin/audit?limit=500", headers=state_admin["headers"]).json()
    assert any(r["action"] == "case_action:note" for r in rows)
    assert all(r["created_at"] for r in rows)


def test_the_audit_trail_is_itself_audited(client, state_admin):
    client.get("/api/admin/audit", headers=state_admin["headers"])
    rows = client.get("/api/admin/audit?limit=500", headers=state_admin["headers"]).json()
    assert any(r["action"] == "view_audit" for r in rows)


def test_a_law_enforcement_read_is_audited(client, complainant, case_id, counsellor, law_enforcement, state_admin):
    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    client.post(
        f"/api/counsellor/cases/{case_id}/actions",
        headers=counsellor["headers"],
        json={"action": "police_liaison", "note": "Referred."},
    )
    assert client.get("/api/law-enforcement/cases", headers=law_enforcement["headers"]).status_code == 200
    rows = client.get("/api/admin/audit?limit=500", headers=state_admin["headers"]).json()
    assert any(r["action"] == "view_law_enforcement_cases" for r in rows)


def test_the_audit_trail_never_holds_message_text(client, complainant, case_id, counsellor, state_admin):
    """An audit log that copies case content would double the exposure."""
    submit(client, complainant["headers"], case_id, CRITICAL_TEXT, 30000)
    client.get(f"/api/counsellor/queue/{case_id}", headers=counsellor["headers"])
    rows = client.get("/api/admin/audit?limit=500", headers=state_admin["headers"]).json()
    blob = str(rows)
    assert "kill myself" not in blob
