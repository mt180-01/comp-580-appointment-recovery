import json
import random
from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from slimconfig import build_output

from contract import BookBatchInput, BookingOutput, RecoveryInput, RecoveryOutput
from plugin.tools import book_slots, check_workspace, list_slots
from verifier import verify_task
from verifier.calendar import CALENDAR, read_calendar


def stamp(value):
    return value.isoformat(timespec="seconds") + "Z"


def generated_task(seed):
    rng = random.Random(seed)
    day = datetime(rng.choice([2000, 2028, 2100, 2400]), 2, 28, 23, 0)
    slots = []
    for i in range(rng.randrange(1, 15)):
        start = day + timedelta(minutes=15 * rng.randrange(12))
        slots.append(
            {
                "slot_id": f"S-{seed}-{i:02d}",
                "start": stamp(start),
                "end": stamp(start + timedelta(minutes=rng.choice([15, 30, 45, 60]))),
                "service": rng.choice(["consult", "imaging"]),
                "location": rng.choice(["north", "south"]),
            }
        )
    appointments = []
    for i in range(rng.randrange(1, 12)):
        start = day + timedelta(minutes=15 * rng.randrange(6))
        appointments.append(
            {
                "appointment_id": f"A-{seed}-{i:02d}",
                "priority": rng.randrange(3),
                "original_start": stamp(day - timedelta(days=1, minutes=15 * rng.randrange(4))),
                "earliest_start": stamp(start),
                "latest_end": stamp(start + timedelta(minutes=rng.choice([30, 60, 120]))),
                "service": rng.choice(["consult", "imaging"]),
                "duration_minutes": rng.choice([15, 30, 45]),
                "allowed_locations": rng.choice([[], ["north"], ["south"], ["north", "south"]]),
            }
        )
    rng.shuffle(slots)
    rng.shuffle(appointments)
    return {
        "disruption_id": f"generated-{seed}",
        "dataset": {
            "appointments": appointments,
            "slots": slots,
            "existing_bookings": [{"appointment_id": "EXISTING", "slot_id": slots[0]["slot_id"]}],
        },
    }


def independent_schedule(raw):
    data = raw["dataset"]
    calendar = {row["appointment_id"]: row["slot_id"] for row in data["existing_bookings"]}
    occupied = set(calendar.values())
    results = []
    for appointment in sorted(
        data["appointments"],
        key=lambda row: (row["priority"], datetime.fromisoformat(row["original_start"]), row["appointment_id"]),
    ):
        candidates = []
        for slot in data["slots"]:
            start, end = datetime.fromisoformat(slot["start"]), datetime.fromisoformat(slot["end"])
            if (
                slot["slot_id"] not in occupied
                and slot["service"] == appointment["service"]
                and slot["location"] in appointment["allowed_locations"]
                and start >= datetime.fromisoformat(appointment["earliest_start"])
                and end <= datetime.fromisoformat(appointment["latest_end"])
                and end - start >= timedelta(minutes=appointment["duration_minutes"])
            ):
                candidates.append((start, slot["slot_id"]))
        chosen = min(candidates)[1] if candidates else None
        if chosen is not None:
            calendar[appointment["appointment_id"]] = chosen
            occupied.add(chosen)
        results.append(
            {
                "appointment_id": appointment["appointment_id"],
                "slot_id": chosen,
                "reason": None if chosen is not None else "NO_ELIGIBLE_SLOT",
            }
        )
    return results, calendar


@pytest.mark.parametrize("seed", range(30))
def test_generated_unseen_schedules_and_tampering(seed, tmp_path):
    raw = generated_task(seed)
    task = build_output(raw, RecoveryInput)
    reference = check_workspace(task, tmp_path)
    assert len(list_slots(task, tmp_path).slots) == len(raw["dataset"]["slots"]) - 1
    expected, expected_calendar = independent_schedule(raw)
    request = BookBatchInput(
        disruption_id=task.disruption_id,
        dataset=task.dataset,
        bookings=[
            BookingOutput(row["appointment_id"], row["slot_id"]) for row in expected if row["slot_id"] is not None
        ],
    )
    book_slots(request, tmp_path)
    book_slots(request, tmp_path)
    assert read_calendar(tmp_path) == expected_calendar
    output = build_output({"results": expected}, RecoveryOutput)
    assert verify_task("recover-appointments", task, output, reference, tmp_path)["valid"]

    mutations = [expected[:-1], [*expected, expected[0]]]
    for field, value in [("slot_id", "UNKNOWN"), ("appointment_id", "UNKNOWN"), ("reason", "UNKNOWN")]:
        changed = deepcopy(expected)
        changed[0][field] = value
        mutations.append(changed)
    for changed in mutations:
        submission = build_output({"results": changed}, RecoveryOutput)
        assert not verify_task("recover-appointments", task, submission, reference, tmp_path)["valid"]
    damaged = dict(expected_calendar)
    damaged.pop("EXISTING")
    (tmp_path / CALENDAR).write_text(json.dumps(damaged), encoding="utf-8")
    assert not verify_task("recover-appointments", task, output, reference, tmp_path)["valid"]


def test_failed_batch_preserves_existing_calendar(tmp_path):
    raw = generated_task(1)
    # Use a single known eligible slot and two competing appointments.
    slot = raw["dataset"]["slots"][0]
    slot.update(service="consult", location="north", start="2028-01-01T10:00:00Z", end="2028-01-01T11:00:00Z")
    template = dict(
        raw["dataset"]["appointments"][0],
        service="consult",
        allowed_locations=["north"],
        earliest_start=slot["start"],
        latest_end=slot["end"],
        duration_minutes=30,
    )
    raw["dataset"]["appointments"] = [dict(template, appointment_id="X"), dict(template, appointment_id="Y")]
    raw["dataset"]["existing_bookings"] = []
    task = build_output(raw, RecoveryInput)
    first = BookBatchInput(
        disruption_id=task.disruption_id, dataset=task.dataset, bookings=[BookingOutput("X", slot["slot_id"])]
    )
    book_slots(first, tmp_path)
    before = (tmp_path / CALENDAR).read_bytes()
    conflict = BookBatchInput(
        disruption_id=task.disruption_id, dataset=task.dataset, bookings=[BookingOutput("Y", slot["slot_id"])]
    )
    with pytest.raises(ValueError):
        book_slots(conflict, tmp_path)
    assert (tmp_path / CALENDAR).read_bytes() == before
