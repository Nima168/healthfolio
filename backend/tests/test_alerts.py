"""Safety alerts: the approved out-of-range rule, boundaries, the alert lifecycle, and keeping alerts in step.

Real test database, fake Groq client (no network, no cost).
"""

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.alerts import Alert
from tests.ai_fakes import payload, printed_lines, response, result
from tests.test_discharge import discharge, upload_discharge
from tests.test_extraction_flow import extraction, make_user, run_worker, upload_report
from tests.test_reports import ecg, upload

pytestmark = pytest.mark.integration

URL = "/api/v1/alerts"


def lab(name, value, range_text, unit="mg/dL", numeric=True, **overrides):
    return result(
        test_name=name,
        value_text=value,
        value_numeric=float(value) if numeric else None,
        unit=unit,
        reference_range_text=range_text,
        **overrides,
    )


LAB = payload(
    results=[
        lab("HbA1c", "6.1", "4.0 - 5.6", "%"),  # above: alert
        lab("Haemoglobin", "15.5", "12.0 - 15.5", "g/dL"),  # on the upper bound (inclusive): no alert
        lab("CRP", "5.0", "< 5.0", "mg/L"),  # "<" is exact: 5.0 is not below 5.0, so above: alert
        lab("Ferritin", "29", "30 - 400", "ng/mL"),  # below: alert
        lab("Vitamin B12", "<150", "200 - 900", "pg/mL", numeric=False),  # not a plain number: no alert
        lab("Uric acid", "9.1", None),  # no printed range: no alert
        lab("TSH", "9.9", "0.4 - 4.0", "mIU/L", confidence="low"),  # unclear reading: no alert
    ]
)


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


def alerts(client, headers):
    response_ = client.get(URL, headers=headers)
    assert response_.status_code == 200, response_.text
    return response_.json()["items"]


def read_lab(client, headers, reply=LAB, label="lab"):
    document_id = upload_report(client, headers, label, lines=printed_lines(reply))
    run_worker(get_settings(), response(reply))
    return document_id


def test_out_of_range_results_raise_alerts_and_boundaries_hold(client, asha, db):
    document_id = read_lab(client, asha)

    # Raised when the reading finished, before anyone looked.
    assert db.scalars(select(Alert)).all()

    items = alerts(client, asha)
    assert sorted(a["title"] for a in items) == [
        "CRP 5.0 mg/L is above the report's range (< 5.0)",
        "Ferritin 29 ng/mL is below the report's range (30 - 400)",
        "HbA1c 6.1 % is above the report's range (4.0 - 5.6)",
    ]
    hba1c = next(a for a in items if a["title"].startswith("HbA1c"))
    assert (hba1c["severity"], hba1c["status"], hba1c["rule_code"], hba1c["rule_version"]) == (
        "warning",
        "open",
        "RESULT_OUTSIDE_REPORT_RANGE",
        1,
    )
    assert "not a diagnosis" in hba1c["reason"]
    assert "Reference ranges differ" in hba1c["uncertainty"]
    assert "Do not start, stop, or change any treatment" in hba1c["next_steps"]
    assert hba1c["explanation_text"] is None  # no AI explanation is generated
    assert (hba1c["source_document_id"], hba1c["source_document_title"]) == (document_id, "Synthetic report lab")
    assert (hba1c["report_type"], hba1c["report_date"]) == ("lab_report", "2026-03-14")
    assert [(e["event"], e["actor"]) for e in hba1c["history"]] == [("raised", "system")]


def test_listing_twice_does_not_raise_twice(client, asha):
    read_lab(client, asha)
    assert len(alerts(client, asha)) == len(alerts(client, asha)) == 3


def test_acknowledge_then_resolve_and_invalid_transitions(client, asha):
    read_lab(client, asha)
    alert_id = alerts(client, asha)[0]["id"]

    acknowledged = client.patch(f"{URL}/{alert_id}", headers=asha, json={"status": "acknowledged"})
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "acknowledged" and acknowledged.json()["acknowledged_at"]
    assert client.patch(f"{URL}/{alert_id}", headers=asha, json={"status": "acknowledged"}).status_code == 409

    resolved = client.patch(
        f"{URL}/{alert_id}", headers=asha, json={"status": "resolved", "note": "Seen by Dr. Sample"}
    )
    body = resolved.json()
    assert (body["status"], body["resolved_by"], body["resolution_note"]) == ("resolved", "user", "Seen by Dr. Sample")
    assert [e["event"] for e in body["history"]] == ["raised", "acknowledged", "resolved"]
    assert client.patch(f"{URL}/{alert_id}", headers=asha, json={"status": "acknowledged"}).status_code == 409
    assert client.patch(f"{URL}/{alert_id}", headers=asha, json={"status": "open"}).status_code == 422


def test_reading_again_keeps_the_same_alerts_and_the_users_actions(client, asha):
    document_id = read_lab(client, asha)
    first = {a["title"]: a for a in alerts(client, asha)}
    hba1c, crp = (
        first["HbA1c 6.1 % is above the report's range (4.0 - 5.6)"],
        first["CRP 5.0 mg/L is above the report's range (< 5.0)"],
    )
    client.patch(f"{URL}/{hba1c['id']}", headers=asha, json={"status": "acknowledged"})
    client.patch(f"{URL}/{crp['id']}", headers=asha, json={"status": "resolved"})

    assert client.post(f"/api/v1/documents/{document_id}/extract", headers=asha).status_code == 202
    run_worker(get_settings(), response(LAB))

    again = {a["title"]: a for a in alerts(client, asha)}
    assert len(again) == 3
    assert again[hba1c["title"]]["id"] == hba1c["id"] and again[hba1c["title"]]["status"] == "acknowledged"
    assert again[crp["title"]]["status"] == "resolved"  # the user's resolution stays


def test_alerts_follow_the_records(client, asha):
    document_id = read_lab(client, asha)
    acknowledged_id = alerts(client, asha)[0]["id"]
    client.patch(f"{URL}/{acknowledged_id}", headers=asha, json={"status": "acknowledged"})

    # Read again and the result is gone: the system resolves the alert.
    client.post(f"/api/v1/documents/{document_id}/extract", headers=asha)
    run_worker(get_settings(), response(payload(results=[lab("Haemoglobin", "13.0", "12.0 - 15.5", "g/dL")])))
    gone = alerts(client, asha)
    assert {(a["status"], a["resolved_by"]) for a in gone} == {("resolved", "system")}
    assert gone[0]["resolution_note"].startswith("The result is no longer in your records")

    # Read again and it is back: reopened, and the earlier acknowledgement is kept.
    client.post(f"/api/v1/documents/{document_id}/extract", headers=asha)
    run_worker(get_settings(), response(LAB))
    back = {a["id"]: a for a in alerts(client, asha)}
    assert back[acknowledged_id]["status"] == "acknowledged"
    assert [e["event"] for e in back[acknowledged_id]["history"]] == ["raised", "acknowledged", "resolved", "reopened"]


def test_deleting_the_document_deletes_its_alerts(client, asha):
    document_id = read_lab(client, asha)
    assert alerts(client, asha)

    assert client.delete(f"/api/v1/documents/{document_id}", headers=asha).status_code == 204

    assert alerts(client, asha) == []  # with their history (decision 2026-10-17)


def test_discharge_summaries_alert_only_on_each_tests_last_value(client, asha):
    upload_discharge(client, asha)
    run_worker(get_settings(), response(discharge()))

    titles = sorted(a["title"] for a in alerts(client, asha))

    # Creatinine 1.31 (last of four), Hemoglobin 12.8 (last of three), CRP 6.2 (last of two); Sodium ends at 137.
    assert titles == [
        "C-Reactive Protein 6.2 mg/L is above the report's range (< 5.0)",
        "Hemoglobin 12.8 g/dL is below the report's range (13.0 – 17.0)",
        "Serum Creatinine 1.31 mg/dL is above the report's range (0.70 – 1.30)",
    ]
    assert all("last value recorded before discharge" in a["uncertainty"] for a in alerts(client, asha))


def test_test_report_measurements_outside_their_printed_range(client, asha):
    document_id = upload(client, asha, "other", "ecg")
    run_worker(get_settings(), response({"document_type": "test_report"}), response(ecg()))

    flagged = [m for m in extraction(client, asha, document_id)["test_report"]["measurements"] if m["flag"]]
    titles = [a["title"] for a in alerts(client, asha)]
    assert len(titles) == len(flagged)
    for measurement in flagged:
        assert any(title.startswith(f"{measurement['name']} {measurement['value_text']}") for title in titles)


def test_only_the_owner_sees_and_changes_alerts(client, asha):
    read_lab(client, asha)
    alert_id = alerts(client, asha)[0]["id"]
    ravi = make_user(client, "ravi@example.com")

    assert alerts(client, ravi) == []
    assert client.patch(f"{URL}/{alert_id}", headers=ravi, json={"status": "resolved"}).status_code == 404
    assert client.get(URL).status_code == 401
