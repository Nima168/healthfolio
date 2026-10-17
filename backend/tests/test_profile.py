"""Health profile: personal values with history, allergies, conditions, and diagnoses suggested from documents.

Real test database, fake Groq client (no network, no cost).
"""

from datetime import date, timedelta

import pytest

from app.core.config import get_settings
from app.services.profile_service import bmi_category
from tests.ai_fakes import response
from tests.test_discharge import discharge, upload_discharge
from tests.test_extraction_flow import make_user, run_worker

pytestmark = pytest.mark.integration

URL = "/api/v1/profile"
GASTRO = "Acute gastroenteritis with moderate dehydration"


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


def profile(client, headers):
    response_ = client.get(URL, headers=headers)
    assert response_.status_code == 200, response_.text
    return response_.json()


def read_discharge(client, headers):
    document_id = upload_discharge(client, headers)
    run_worker(get_settings(), response(discharge()))
    return document_id


# ---------- personal values ----------


def test_empty_profile(client, asha):
    body = profile(client, asha)
    assert body["values"] == dict.fromkeys(["date_of_birth", "sex", "blood_group", "height", "weight"])
    assert (body["bmi"], body["bmi_category"]) == (None, None)
    for section in ("allergies", "conditions", "suggestions", "surgeries", "hospitalizations", "document_stays"):
        assert body[section] == []
    assert (body["family_history"], body["active_medications"]) == ([], [])


def test_set_change_and_clear_values_with_history(client, asha):
    first = client.patch(
        f"{URL}/values",
        headers=asha,
        json={
            "date_of_birth": "1985-04-12",
            "sex": "female",
            "blood_group": "b +",
            "height": "162.0",
            "weight": "61.5",
        },
    )
    assert first.status_code == 200, first.text
    values = first.json()["values"]
    assert {field: v["value"] for field, v in values.items() if v} == {
        "date_of_birth": "1985-04-12",
        "sex": "female",
        "blood_group": "B+",
        "height": "162",
        "weight": "61.5",
    }
    assert (values["height"]["unit"], values["weight"]["unit"]) == ("cm", "kg")

    client.patch(f"{URL}/values", headers=asha, json={"weight": "60", "height": "162"})  # height unchanged
    client.patch(f"{URL}/values", headers=asha, json={"blood_group": ""})  # cleared

    body = profile(client, asha)
    assert body["values"]["weight"]["value"] == "60" and body["values"]["blood_group"] is None
    history = client.get(f"{URL}/history", headers=asha).json()["items"]
    assert [(h["field"], h["change"], h["previous_value"], h["new_value"]) for h in history[:2]] == [
        ("blood_group", "removed", "B+", None),
        ("weight", "changed", "61.5", "60"),
    ]
    assert len(history) == 7  # five added, one changed, one removed; the unchanged height wrote nothing


@pytest.mark.parametrize(
    ("field", "value", "issue"),
    [
        ("date_of_birth", "2999-01-01", "The date of birth cannot be in the future."),
        ("date_of_birth", "12/04/1985", "Enter the date as YYYY-MM-DD."),
        ("sex", "unknown", "Choose one of the options."),
        ("blood_group", "C+", "Choose one of the blood groups."),
        ("height", "1700", "Enter a value between 30 and 272 cm."),
        ("weight", "heavy", "Enter a number."),
    ],
)
def test_invalid_values_are_explained_and_change_nothing(client, asha, field, value, issue):
    rejected = client.patch(f"{URL}/values", headers=asha, json={"weight": "70", field: value})

    assert rejected.status_code == 422
    assert rejected.json()["error"]["details"] == [{"field": field, "issue": issue}]
    assert profile(client, asha)["values"]["weight"] is None  # the valid field was not saved either


# ---------- allergies and conditions ----------


def test_allergies(client, asha):
    added = client.post(f"{URL}/allergies", headers=asha, json={"name": "  Penicillin "})
    assert added.status_code == 201 and added.json()["name"] == "Penicillin"
    assert client.post(f"{URL}/allergies", headers=asha, json={"name": "penicillin"}).status_code == 409

    assert client.delete(f"{URL}/allergies/{added.json()['id']}", headers=asha).status_code == 204
    assert profile(client, asha)["allergies"] == []
    changes = [h["change"] for h in client.get(f"{URL}/history", headers=asha).json()["items"]]
    assert changes == ["removed", "added"]


def test_conditions(client, asha):
    added = client.post(f"{URL}/conditions", headers=asha, json={"name": "Type 2 diabetes"})
    assert added.status_code == 201
    condition = added.json()
    assert (condition["status"], condition["origin"]) == ("active", "user_entered")
    assert client.post(f"{URL}/conditions", headers=asha, json={"name": "type 2  diabetes"}).status_code == 409

    updated = client.patch(f"{URL}/conditions/{condition['id']}", headers=asha, json={"status": "resolved"})
    assert updated.json()["status"] == "resolved"
    assert client.delete(f"{URL}/conditions/{condition['id']}", headers=asha).status_code == 204
    assert profile(client, asha)["conditions"] == []


# ---------- suggestions from documents ----------


def test_diagnoses_from_documents_are_suggestions_until_reviewed(client, asha):
    document_id = read_discharge(client, asha)

    body = profile(client, asha)
    assert body["conditions"] == []  # nothing is added to the profile on its own
    assert [s["name"] for s in body["suggestions"]][0] == GASTRO
    assert body["suggestions"][0]["source_document_id"] == document_id


def test_accept_correct_and_reject(client, asha):
    document_id = read_discharge(client, asha)
    suggestions = {s["name"]: s["id"] for s in profile(client, asha)["suggestions"]}
    names = list(suggestions)

    accepted = client.post(f"{URL}/suggestions/{suggestions[names[0]]}", headers=asha, json={"action": "accept"})
    assert accepted.status_code == 200
    client.post(
        f"{URL}/suggestions/{suggestions[names[1]]}",
        headers=asha,
        json={"action": "correct", "name": "Acute kidney injury", "status": "resolved"},
    )
    client.post(f"{URL}/suggestions/{suggestions[names[2]]}", headers=asha, json={"action": "reject"})

    body = profile(client, asha)
    assert [(c["name"], c["status"], c["origin"]) for c in body["conditions"]] == [
        (GASTRO, "unknown", "suggestion_accepted"),
        ("Acute kidney injury", "resolved", "suggestion_accepted"),
    ]
    assert body["conditions"][0]["source_document_id"] == document_id
    assert body["suggestions"] == []
    again = client.post(f"{URL}/suggestions/{suggestions[names[0]]}", headers=asha, json={"action": "reject"})
    assert again.status_code == 409
    assert (
        client.post(f"{URL}/suggestions/{suggestions[names[1]]}", headers=asha, json={"action": "correct"}).status_code
        == 409
    )


def test_correct_needs_a_name(client, asha):
    read_discharge(client, asha)
    suggestion_id = profile(client, asha)["suggestions"][0]["id"]

    assert (
        client.post(f"{URL}/suggestions/{suggestion_id}", headers=asha, json={"action": "correct"}).status_code == 422
    )


def test_reviewed_suggestions_stay_reviewed_after_read_again_and_deletion(client, asha):
    document_id = read_discharge(client, asha)
    suggestions = profile(client, asha)["suggestions"]
    client.post(f"{URL}/suggestions/{suggestions[0]['id']}", headers=asha, json={"action": "accept"})
    client.post(f"{URL}/suggestions/{suggestions[1]['id']}", headers=asha, json={"action": "reject"})
    remaining = len(suggestions) - 2

    client.post(f"/api/v1/documents/{document_id}/extract", headers=asha)
    run_worker(get_settings(), response(discharge()))
    body = profile(client, asha)
    assert len(body["suggestions"]) == remaining  # accepted and rejected ones are not suggested again
    assert len(body["conditions"]) == 1

    client.delete(f"/api/v1/documents/{document_id}", headers=asha)
    body = profile(client, asha)
    assert body["suggestions"] == []
    assert body["conditions"] == []  # accepted from the document, so deleted with it (decision 2026-10-17)


def test_accepting_a_condition_already_in_the_profile_does_not_duplicate_it(client, asha):
    client.post(f"{URL}/conditions", headers=asha, json={"name": GASTRO.upper()})
    read_discharge(client, asha)

    assert GASTRO not in [s["name"] for s in profile(client, asha)["suggestions"]]


def test_only_the_owner(client, asha):
    condition_id = client.post(f"{URL}/conditions", headers=asha, json={"name": "Asthma"}).json()["id"]
    ravi = make_user(client, "ravi@example.com")

    assert profile(client, ravi)["conditions"] == []
    assert (
        client.patch(f"{URL}/conditions/{condition_id}", headers=ravi, json={"status": "resolved"}).status_code == 404
    )
    assert client.get(URL).status_code == 401


# ---------- vitals, medical history, active medicines, family history ----------


def test_bmi_and_its_adult_category(client, asha):
    saved = client.patch(f"{URL}/values", headers=asha, json={"height": "160", "weight": "64"}).json()

    assert (saved["bmi"], saved["bmi_category"]) == (25.0, "overweight")  # 64 / 1.6^2


@pytest.mark.parametrize(
    ("bmi", "category"),
    [
        (18.4, "underweight"),
        (18.5, "healthy"),
        (24.9, "healthy"),
        (25.0, "overweight"),
        (29.9, "overweight"),
        (30.0, "obesity_1"),
        (34.9, "obesity_1"),
        (35.0, "obesity_2"),
        (39.9, "obesity_2"),
        (40.0, "obesity_3"),
        (52.3, "obesity_3"),
    ],
)
def test_bmi_category_edges(bmi, category):
    assert bmi_category(bmi, None) == category


def test_no_adult_category_under_18(client, asha):
    young = (date.today() - timedelta(days=365 * 15)).isoformat()
    body = client.patch(
        f"{URL}/values", headers=asha, json={"date_of_birth": young, "height": "160", "weight": "64"}
    ).json()

    assert (body["bmi"], body["bmi_category"]) == (25.0, None)


def test_blood_pressure_and_heart_rate_are_not_profile_values(client, asha):
    for field in ("blood_pressure", "heart_rate"):
        assert client.patch(f"{URL}/values", headers=asha, json={field: "72"}).status_code == 422
    assert set(profile(client, asha)["values"]) == {"date_of_birth", "sex", "blood_group", "height", "weight"}


def test_allergy_type_and_reaction(client, asha):
    added = client.post(
        f"{URL}/allergies", headers=asha, json={"name": "Penicillin", "category": "drug", "reaction": "  Hives "}
    ).json()
    assert (added["category"], added["reaction"]) == ("drug", "Hives")
    assert client.post(f"{URL}/allergies", headers=asha, json={"name": "Dust", "category": "pollen"}).status_code == 422


def test_surgeries_hospitalizations_and_family_history(client, asha):
    surgery = client.post(
        f"{URL}/records", headers=asha, json={"kind": "surgery", "name": "Appendectomy", "occurred_on": "2015-06-01"}
    )
    assert surgery.status_code == 201
    client.post(f"{URL}/records", headers=asha, json={"kind": "hospitalization", "name": "Dengue fever"})
    family = client.post(
        f"{URL}/records",
        headers=asha,
        json={"kind": "family", "name": "Heart disease", "relation": "Father", "occurred_on": "2000-01-01"},
    ).json()
    assert (family["relation"], family["occurred_on"]) == ("Father", None)  # no date for family history

    body = profile(client, asha)
    assert [(r["name"], r["occurred_on"]) for r in body["surgeries"]] == [("Appendectomy", "2015-06-01")]
    assert [r["name"] for r in body["hospitalizations"]] == ["Dengue fever"]
    assert [(r["name"], r["relation"]) for r in body["family_history"]] == [("Heart disease", "Father")]

    assert client.delete(f"{URL}/records/{family['id']}", headers=asha).status_code == 204
    assert profile(client, asha)["family_history"] == []


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"kind": "family", "name": "Stroke", "relation": "Neighbour"}, "relation"),
        ({"kind": "surgery", "name": "Knee", "occurred_on": "2999-01-01"}, "occurred_on"),
    ],
)
def test_invalid_records(client, asha, body, field):
    rejected = client.post(f"{URL}/records", headers=asha, json=body)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["details"][0]["field"] == field


def test_hospital_stays_from_discharge_summaries(client, asha):
    document_id = read_discharge(client, asha)

    [stay] = profile(client, asha)["document_stays"]

    assert (stay["source_document_id"], stay["admitted_on"], stay["discharged_on"]) == (
        document_id,
        "2026-08-10",
        "2026-08-13",
    )
    assert stay["facility_name"] == "SAMPLEVILLE GENERAL HOSPITAL (FICTIONAL)"
    assert stay["diagnoses"][0] == GASTRO


def test_active_medications_are_only_those_marked_as_taking(client, asha):
    read_discharge(client, asha)  # its medicines stay "not confirmed"
    client.post("/api/v1/medications", headers=asha, json={"name": "Vitamin D3", "kind": "supplement"})
    client.post("/api/v1/medications", headers=asha, json={"name": "Old pill", "status": "stopped"})

    active = profile(client, asha)["active_medications"]

    assert [(m["name"], m["kind"]) for m in active] == [("Vitamin D3", "supplement")]


def test_records_belong_to_their_owner(client, asha):
    item_id = client.post(f"{URL}/records", headers=asha, json={"kind": "surgery", "name": "Appendectomy"}).json()["id"]
    ravi = make_user(client, "ravi@example.com")

    assert profile(client, ravi)["surgeries"] == []
    assert client.delete(f"{URL}/records/{item_id}", headers=ravi).status_code == 404
