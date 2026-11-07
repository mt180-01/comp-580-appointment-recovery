import json
from dataclasses import asdict
from pathlib import Path

import pytest
from slimconfig import build_output

from contract import BookBatchInput, BookingOutput, RecoveryInput, RecoveryOutput
from plugin.tools import book_slots, check_workspace, list_appointments, list_slots
from verifier import verify_output, verify_task
from verifier.data import load_data
from verifier.rules import utc_seconds

EXAMPLE = Path(__file__).parent / "fixtures" / "unseen-input.json"


def example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8-sig"))


def test_new_disruption_across_midnight_and_leap_day(tmp_path):
    value = example()
    task = build_output(value, RecoveryInput)
    reference = check_workspace(task, tmp_path)
    assert len(list_appointments(task, tmp_path).appointments) == 3
    available = list_slots(task, tmp_path)
    assert {row.slot_id for row in available.slots} == {"EARLY", "LONG"}
    request = BookBatchInput(
        disruption_id=task.disruption_id,
        dataset=task.dataset,
        bookings=[BookingOutput("B-new", "EARLY"), BookingOutput("A-new", "LONG")],
    )
    result = book_slots(request, tmp_path)
    assert verify_output("book_slots", request, result, tmp_path)["valid"]
    summary = build_output(
        {
            "results": [
                {"appointment_id": "B-new", "slot_id": "EARLY", "reason": None},
                {"appointment_id": "A-new", "slot_id": "LONG", "reason": None},
                {"appointment_id": "C-new", "slot_id": None, "reason": "NO_ELIGIBLE_SLOT"},
            ]
        },
        RecoveryOutput,
    )
    assert verify_task("recover-appointments", task, summary, reference, tmp_path)["valid"]
    changed = example()
    changed["dataset"]["appointments"][0]["duration_minutes"] = 60
    assert not verify_task("recover-appointments", build_output(changed, RecoveryInput), summary, reference, tmp_path)[
        "valid"
    ]
    summary.results[1].slot_id = "EARLY"
    assert not verify_task("recover-appointments", task, summary, reference, tmp_path)["valid"]


@pytest.mark.parametrize("empty_appointments", [False, True])
def test_no_available_slots_and_empty_disruption(tmp_path, empty_appointments):
    value = example()
    value["dataset"]["slots"] = []
    value["dataset"]["existing_bookings"] = []
    if empty_appointments:
        value["dataset"]["appointments"] = []
    task = build_output(value, RecoveryInput)
    reference = check_workspace(task, tmp_path)
    book_slots(BookBatchInput(disruption_id=task.disruption_id, dataset=task.dataset, bookings=[]), tmp_path)
    appointments = sorted(
        value["dataset"]["appointments"],
        key=lambda row: (row["priority"], row["original_start"], row["appointment_id"]),
    )
    summary = build_output(
        {
            "results": [
                {"appointment_id": row["appointment_id"], "slot_id": None, "reason": "NO_ELIGIBLE_SLOT"}
                for row in appointments
            ]
        },
        RecoveryOutput,
    )
    assert verify_task("recover-appointments", task, summary, reference, tmp_path)["valid"]
    assert asdict(task)["disruption_id"] == "new-closure"


@pytest.mark.parametrize(
    "timestamp",
    [
        "2100-02-29T00:00:00Z",
        "٢٠٢٨-02-29T00:00:00Z",
        "2028-02-30T00:00:00Z",
        "0000-01-01T00:00:00Z",
        "2028-03-01T24:00:00Z",
        "2028-03-01T00:00:00+00:00",
    ],
)
def test_invalid_dates(timestamp):
    with pytest.raises(ValueError):
        utc_seconds(timestamp)


@pytest.mark.parametrize("change", ["slot_id", "appointment_id", "reservation", "window", "duration"])
def test_invalid_new_data(change):
    value = example()
    data = value["dataset"]
    if change == "slot_id":
        data["slots"][1]["slot_id"] = data["slots"][0]["slot_id"]
    elif change == "appointment_id":
        data["appointments"][1]["appointment_id"] = data["appointments"][0]["appointment_id"]
    elif change == "reservation":
        data["existing_bookings"][0]["slot_id"] = "UNKNOWN"
    elif change == "window":
        data["appointments"][0]["latest_end"] = "2028-02-28T00:00:00Z"
    else:
        data["appointments"][0]["duration_minutes"] = 0
    with pytest.raises(ValueError):
        load_data(value)


def test_calendar_arithmetic_matches_standard_library():
    from datetime import datetime

    for year in (1, 4, 100, 400, 1900, 2000, 2028, 2100, 2400, 9999):
        for month in range(1, 13):
            value = f"{year:04d}-{month:02d}-01T23:59:59Z"
            date = datetime(year, month, 1, 23, 59, 59)
            expected = (date.toordinal() - 1) * 86400 + 23 * 3600 + 59 * 60 + 59
            assert utc_seconds(value) == expected
