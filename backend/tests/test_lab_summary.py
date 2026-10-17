"""The lab-result summary rules (app/services/lab_summary.py). No database, no AI."""

from decimal import Decimal

import pytest

from app.models.extraction import Observation
from app.services.lab_summary import classify, summarise


def obs(value_text="13.8", range_text="12.0 - 15.5", *, unit="g/dL", name="Haemoglobin", **overrides) -> Observation:
    """An extracted result; value_numeric is the plain number in value_text, if there is one."""
    try:
        numeric = Decimal(value_text.replace(",", ""))
    except ArithmeticError:
        numeric = None
    return Observation(
        name=name,
        value_text=value_text,
        value_numeric=numeric,
        unit=unit,
        reference_range_text=range_text,
        confidence=overrides.pop("confidence", "high"),
        validation_findings=overrides.pop("findings", []),
    )


not_a_number = 'The value "{}" is not a single number, so it was not compared.'.format
unreadable_range = 'The reference range "{}" could not be read.'.format


@pytest.mark.parametrize(
    ("value", "range_text", "expected"),
    [
        ("13.8", "12.0 - 15.5", "within"),
        ("12.0", "12.0 - 15.5", "within"),  # both ends included
        ("15.5", "12.0-15.5", "within"),
        ("11.9", "12.0 - 15.5", "below"),
        ("15.6", "12.0 – 15.5 g/dL", "above"),  # en dash and a trailing unit
        ("8", "4 to 11", "within"),
        ("199", "< 200", "within"),
        ("200", "< 200", "above"),  # "< X" applied exactly as written
        ("200", "<= 200", "within"),
        ("200", "≤200", "within"),
        ("40", "> 40", "below"),  # "> X": 40 itself is outside
        ("40", ">= 40", "within"),
        ("39", "≥ 40", "below"),
        ("1,250", "150 - 1,000", "above"),
    ],
)
def test_values_are_compared_with_the_printed_range_exactly(value, range_text, expected):
    assert classify(obs(value_text=value, range_text=range_text)) == (expected, None)


CHOLESTEROL = "Desirable < 200; Borderline 200-239; High >= 240"
LDL = "Optimal < 100; Near optimal 100-129: Borderline 130-159"  # ":" between bands, as scanned
HDL = "Low < 40; High >= 60"


@pytest.mark.parametrize(
    ("value", "range_text", "expected"),
    [
        ("190", CHOLESTEROL, "within"),  # Desirable
        ("224", CHOLESTEROL, "above"),  # Borderline counts as above the range
        ("250", CHOLESTEROL, "above"),  # High
        ("90", LDL, "within"),  # Optimal
        ("115", LDL, "within"),  # Near optimal
        ("149", LDL, "above"),  # Borderline
        ("182", "Normal < 150; Borderline 150-199; High 200-499", "above"),
        ("39", HDL, "below"),  # Low
        ("50", HDL, "within"),  # in no band, and every band printed is abnormal
        ("65", HDL, "above"),  # High, as printed
    ],
)
def test_a_tiered_range_is_judged_by_the_band_the_value_is_in(value, range_text, expected):
    assert classify(obs(value_text=value, range_text=range_text, unit="mg/dL")) == (expected, None)


@pytest.mark.parametrize(
    ("value", "range_text", "reason"),
    [
        ("15", "Deficient < 20; Insufficient 20-29; Sufficient 30-100", 'The value is in the "Deficient" band'),
        ("239.5", CHOLESTEROL, "could not be read"),  # between two bands
        ("13.8", "Male: 13-17, Female: 12-15", "could not be read"),  # in two bands
        ("224", "Desirable < 200 (fasting); Borderline 200-239", "could not be read"),  # other text: not read
    ],
)
def test_a_tiered_range_that_cannot_be_settled_is_not_judged(value, range_text, reason):
    status, why = classify(obs(value_text=value, range_text=range_text, unit="mg/dL"))
    assert status == "invalid" and reason in why


@pytest.mark.parametrize(
    ("observation", "reason"),
    [
        (obs(range_text=None), "No reference range is printed for this test."),
        (obs(range_text="  "), "No reference range is printed for this test."),
        (obs(value_text="<150"), not_a_number("<150")),
        (obs(value_text="Positive"), not_a_number("Positive")),
        (obs(range_text="Male: 13-17, Female: 12-15"), unreadable_range("Male: 13-17, Female: 12-15")),
        (obs(range_text="15.5 - 12.0"), unreadable_range("15.5 - 12.0")),
        (obs(range_text="Up to 200"), unreadable_range("Up to 200")),
        (obs(findings=["missing_unit"], unit=None), "The unit is missing or unclear."),
        (obs(findings=["numeric_value_mismatch"]), "The value may have been misread."),
        (obs(confidence="low"), "The value, unit, or range was not clearly legible."),
        (obs(confidence="medium"), "The value, unit, or range was not clearly legible."),
    ],
)
def test_unclear_results_are_not_judged(observation, reason):
    assert classify(observation) == ("invalid", reason)


def test_report_date_from_the_report_is_irrelevant_to_judging():
    # A result date finding alone does not stop a clear value from being compared.
    assert classify(obs(value_text="16", findings=["date_from_report"]))[0] == "above"


def test_summary_groups_results_in_report_order():
    summary = summarise(
        [
            obs(name="Haemoglobin", value_text="10.1"),
            obs(name="Glucose", value_text="130", range_text="70 - 99", unit="mg/dL"),
            obs(name="Platelets", value_text="250", range_text="150 - 400", unit="10^3/uL"),
            obs(name="Vitamin B12", value_text="<150", range_text="200 - 900"),
            obs(name="LDL", value_text="180", range_text="< 100", unit="mg/dL"),
        ],
        "14-Mar-2026",
    )

    assert summary.report_date == "14-Mar-2026"
    assert [(line.name, line.value_text, line.unit, line.reference_range_text) for line in summary.above] == [
        ("Glucose", "130", "mg/dL", "70 - 99"),
        ("LDL", "180", "mg/dL", "< 100"),
    ]
    assert [line.name for line in summary.below] == ["Haemoglobin"]
    assert [line.name for line in summary.normal] == ["Platelets"]
    assert [(line.name, line.value_text, line.reference_range_text) for line in summary.invalid] == [
        ("Vitamin B12", "<150", "200 - 900")
    ]
