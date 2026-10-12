"""Vital sign readings: dated blood pressure and heart rate, the latest in the profile, each on the timeline."""

from datetime import date, timedelta

import pytest

from tests.test_extraction_flow import make_user

pytestmark = pytest.mark.integration

URL = "/api/v1/vitals"


@pytest.fixture
def asha(client, db, storage_dir):
    return make_user(client, "asha@example.com")


def add(client, headers, **body):
    return client.post(URL, headers=headers, json={"measured_on": "2026-10-10", **body})


def test_add_and_list_newest_first(client, asha):
    first = add(
        client, asha, systolic=128, diastolic=84, heart_rate=72, measured_time="08:30", context=" morning,  home "
    )
    assert first.status_code == 201, first.text
    assert first.json()["context"] == "morning, home"
    add(client, asha, measured_on="2026-10-12", heart_rate=80)
    add(client, asha, measured_on="2026-10-10", measured_time="20:15", systolic=122, diastolic=80)

    items = client.get(URL, headers=asha).json()["items"]

    assert [(r["measured_on"], r["measured_time"]) for r in items] == [
        ("2026-10-12", None),
        ("2026-10-10", "20:15:00"),
        ("2026-10-10", "08:30:00"),
    ]


def test_profile_shows_the_latest_of_each_with_its_date(client, asha):
    add(client, asha, measured_on="2026-10-01", systolic=130, diastolic=85, heart_rate=70)
    add(client, asha, measured_on="2026-10-05", heart_rate=76, measured_time="07:45")

    body = client.get("/api/v1/profile", headers=asha).json()

    assert body["latest_blood_pressure"] == {
        "value": "130/85",
        "unit": "mmHg",
        "measured_on": "2026-10-01",
        "measured_time": None,
    }
    assert body["latest_heart_rate"] == {
        "value": "76",
        "unit": "bpm",
        "measured_on": "2026-10-05",
        "measured_time": "07:45",
    }


def test_each_reading_is_its_own_timeline_entry_without_judgement(client, asha):
    add(client, asha, systolic=150, diastolic=95, heart_rate=110, measured_time="09:00", context="after walking")

    [entry] = client.get("/api/v1/timeline", headers=asha, params={"category": "vitals"}).json()["items"]

    assert (entry["date"], entry["title"]) == ("2026-10-10", "Blood pressure 150/95 mmHg · Heart rate 110 bpm")
    assert entry["lines"] == ["09:00 · after walking"]
    assert (entry["trust"], entry["tag"], entry["link"]) == ("added_by_you", None, "/profile#vitals-title")


@pytest.mark.parametrize(
    ("body", "field", "issue"),
    [
        ({}, "systolic", "Enter a blood pressure, a heart rate, or both."),
        ({"systolic": 120}, "diastolic", "Enter both blood pressure numbers, for example 120 and 80."),
        (
            {"systolic": 300, "diastolic": 80},
            "systolic",
            "Check the first (systolic) number: it should be between 50 and 260 mmHg.",
        ),
        (
            {"systolic": 80, "diastolic": 120},
            "diastolic",
            "The first number (systolic) should be higher than the second (diastolic).",
        ),
        ({"heart_rate": 5}, "heart_rate", "Check the heart rate: it should be between 20 and 250 bpm."),
        (
            {"heart_rate": 70, "measured_on": (date.today() + timedelta(days=2)).isoformat()},
            "measured_on",
            "The date cannot be in the future.",
        ),
    ],
)
def test_invalid_readings_are_explained(client, asha, body, field, issue):
    rejected = add(client, asha, **body)

    assert rejected.status_code == 422
    assert rejected.json()["error"]["details"] == [{"field": field, "issue": issue}]


def test_remove_and_ownership(client, asha):
    reading_id = add(client, asha, heart_rate=70).json()["id"]
    ravi = make_user(client, "ravi@example.com")

    assert client.get(URL, headers=ravi).json()["items"] == []
    assert client.delete(f"{URL}/{reading_id}", headers=ravi).status_code == 404
    assert client.delete(f"{URL}/{reading_id}", headers=asha).status_code == 204
    assert client.get(URL, headers=asha).json()["items"] == []
    assert client.get(URL).status_code == 401
