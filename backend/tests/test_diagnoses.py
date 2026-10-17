"""Diagnoses and Conditions: health issues written in documents, tracked across them. Fake Groq, no network."""

import pytest

from app.core.config import get_settings
from app.services.diagnosis_service import is_normal_finding, issue_key
from tests.ai_fakes import response
from tests.test_discharge import discharge, upload_discharge
from tests.test_extraction_flow import make_user, run_worker
from tests.test_reports import consultation, imaging, upload

URL = "/api/v1/diagnoses"
AKI = "Acute kidney injury (pre-renal), improving at discharge"


def test_same_wording_ignores_case_spacing_and_full_stop():
    assert issue_key("Acute  kidney injury.") == issue_key("acute kidney injury")
    assert issue_key("Kidney injury") != issue_key("Acute kidney injury")


@pytest.mark.parametrize(
    ("text", "normal"),
    [
        ("Normal heart size.", True),
        ("No active cardiopulmonary abnormality.", True),
        ("No acute fracture.", True),
        ("Lungs are clear.", True),
        ("Negative for malignancy.", True),
        ("Normal sinus rhythm.", True),
        ("Liver within normal limits.", True),
        ("Unremarkable abdominal ultrasound.", True),
        ("No improvement in renal function.", False),  # about a problem's course
        ("No new lesions compared with prior.", False),
        ("No residual stone.", False),
        ("No significant change.", False),
        ("Normal heart size but mild pleural effusion.", False),  # a contrast may hide a problem
        ("Kidneys are normal in size; small cyst on left.", False),
        ("Mild degenerative changes in the mid-thoracic spine.", False),
        ("Borderline high blood pressure in clinic; home readings needed.", False),
        ("Not consistent with infection.", False),  # unclear wording stays a health issue
    ],
)
def test_normal_findings_are_recognised_cautiously(text, normal):
    assert is_normal_finding(text) is normal


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


def by_name(client, headers):
    return {item["name"]: item for item in client.get(URL, headers=headers).json()["items"]}


@pytest.mark.integration
def test_health_issues_from_documents_are_tracked_across_them(client, asha):
    settings = get_settings()
    upload_discharge(client, asha)
    run_worker(settings, response(discharge()))
    upload(client, asha, "consultation_note", "consultation")
    # The consultation repeats one discharge diagnosis, with different case and a full stop.
    run_worker(settings, response(consultation(assessment=[AKI.upper() + ".", "Mildly reduced kidney function"])))
    upload(client, asha, "imaging_report", "imaging")
    run_worker(settings, response(imaging()))

    issues = by_name(client, asha)

    kidney = issues[AKI.upper() + "."]  # one entry, named with the most recent wording (the consultation)
    assert kidney["kinds"] == ["assessment", "diagnosis"]
    assert [m["kind"] for m in kidney["mentions"]] == ["assessment", "diagnosis"]  # newest first
    assert (kidney["first_seen"], kidney["last_seen"]) == (kidney["mentions"][1]["date"], "2026-10-15")
    assert kidney["profile"] == "to_review"  # a discharge diagnosis is suggested in Health Profile

    assert not any(item["normal"] for item in issues.values())  # every statement here names a problem
    impression = issues["Early degenerative disc disease, L3-L4 to L5-S1"]
    assert (impression["kinds"], impression["last_seen"]) == (["impression"], "2026-09-18")
    assert impression["profile"] == "not_in_profile"
    assert issues["Mildly reduced kidney function"]["kinds"] == ["assessment"]
    assert "Acute gastroenteritis with moderate dehydration" in issues
    dates = [item["last_seen"] for item in client.get(URL, headers=asha).json()["items"]]
    assert dates == sorted(dates, reverse=True)  # most recently written first


@pytest.mark.integration
def test_issue_in_the_health_profile_is_marked_with_its_status(client, asha):
    upload(client, asha, "imaging_report", "imaging")
    run_worker(get_settings(), response(imaging()))
    name = "Early degenerative disc disease, L3-L4 to L5-S1"

    added = client.post("/api/v1/profile/conditions", headers=asha, json={"name": name.lower(), "status": "active"})
    assert added.status_code == 201

    issue = by_name(client, asha)[name]
    assert (issue["profile"], issue["condition_status"]) == ("in_profile", "active")


@pytest.mark.integration
def test_normal_findings_are_marked_but_a_written_diagnosis_never_is(client, asha):
    settings = get_settings()
    upload(client, asha, "imaging_report", "imaging")
    run_worker(settings, response(imaging(impression=["Normal heart size.", "Mild disc bulge at L4-L5"])))
    upload_discharge(client, asha)
    run_worker(settings, response(discharge(diagnoses=["No acute fracture"])))

    issues = by_name(client, asha)
    assert issues["Normal heart size."]["normal"] is True
    assert issues["Mild disc bulge at L4-L5"]["normal"] is False
    assert issues["No acute fracture"]["normal"] is False  # written as a diagnosis: always shown as one


@pytest.mark.integration
def test_only_the_users_own_documents(client, asha):
    upload(client, asha, "imaging_report", "imaging")
    run_worker(get_settings(), response(imaging()))
    ravi = make_user(client, "ravi@example.com")

    assert client.get(URL, headers=ravi).json()["items"] == []
    assert client.get(URL).status_code == 401
