from dataclasses import asdict
from pathlib import Path

from contract import Task, Tool

from .calendar import CALENDAR, read_calendar
from .data import load_data, task_digest
from .rules import eligible


def verdict(valid, message):
    return {"valid": valid, "score": float(valid), "message": message, "details": {}}


def verify_input(tool, value):
    try:
        data = load_data(asdict(value))
    except ValueError as error:
        return verdict(False, str(error))
    appointment_by_id = {row["appointment_id"]: row for row in data["appointments"]}
    slot_by_id = {row["slot_id"]: row for row in data["slots"]}
    if Tool(tool) == Tool.BOOK_BATCH:
        ids = [row.appointment_id for row in value.bookings]
        valid = len(set(ids)) == len(ids) and all(
            row.appointment_id in appointment_by_id
            and row.slot_id in slot_by_id
            and eligible(appointment_by_id[row.appointment_id], slot_by_id[row.slot_id])
            for row in value.bookings
        )
        return verdict(valid, "Booking batch checked")
    if Tool(tool) == Tool.BOOK:
        appointment = appointment_by_id.get(value.appointment_id)
        slot = slot_by_id.get(value.slot_id)
        if appointment is None or slot is None or not eligible(appointment, slot):
            return verdict(False, "Unknown appointment, unknown slot, or ineligible slot")
    return verdict(True, "Tool input accepted")


def verify_output(tool, input_value, output_value, workspace):
    if Tool(tool) == Tool.CHECK:
        clean = not (Path(workspace) / "recovery-calendar.json").exists()
        return verdict(
            output_value.clean == clean and output_value.dataset_digest == task_digest(asdict(input_value)),
            "Workspace check verified",
        )
    try:
        data = load_data(asdict(input_value))
        match Tool(tool):
            case Tool.APPOINTMENTS:
                valid = asdict(output_value) == {"appointments": data["appointments"]}
            case Tool.SLOTS:
                path = Path(workspace)
                booked = read_calendar(path) if (path / CALENDAR).exists() else data["initial"]
                occupied = set(booked.values())
                valid = asdict(output_value) == {
                    "slots": [row for row in data["slots"] if row["slot_id"] not in occupied]
                }
            case Tool.BOOK_BATCH:
                booked = read_calendar(Path(workspace))
                valid = output_value.bookings == input_value.bookings and all(
                    booked.get(row.appointment_id) == row.slot_id for row in input_value.bookings
                )
            case Tool.BOOK:
                booked = read_calendar(Path(workspace))
                valid = (
                    output_value.appointment_id == input_value.appointment_id
                    and output_value.slot_id == input_value.slot_id
                    and booked.get(input_value.appointment_id) == input_value.slot_id
                )
    except (OSError, ValueError):
        return verdict(False, "Calendar could not be read")
    return verdict(valid, "Tool output verified" if valid else "Tool output differs from fixture or calendar")


def reference_schedule(data):
    calendar = data["initial"].copy()
    results = []
    appointments = sorted(
        data["appointments"], key=lambda row: (row["priority"], row["original_start"], row["appointment_id"])
    )
    slots = sorted(data["slots"], key=lambda row: (row["start"], row["slot_id"]))
    occupied = set(calendar.values())
    for appointment in appointments:
        appointment_id = appointment["appointment_id"]
        slot_id = next(
            (slot["slot_id"] for slot in slots if slot["slot_id"] not in occupied and eligible(appointment, slot)),
            None,
        )
        if slot_id is not None:
            calendar[appointment_id] = slot_id
            occupied.add(slot_id)
        results.append(
            {
                "appointment_id": appointment_id,
                "slot_id": slot_id,
                "reason": "NO_ELIGIBLE_SLOT" if slot_id is None else None,
            }
        )
    return results, calendar


def verify_task(task, arguments, output, reference, workspace):
    if reference is None or not reference.clean:
        return verdict(False, "A fresh workspace is required; an earlier result cannot pass this run")
    if task != Task.RECOVER.value:
        return verdict(False, "Unknown task")
    try:
        data = load_data(asdict(arguments))
        if reference.dataset_digest != task_digest(asdict(arguments)):
            return verdict(False, "Reference dataset fingerprint does not match the task input")
    except ValueError as error:
        return verdict(False, str(error))
    expected_results, expected_calendar = reference_schedule(data)
    try:
        submitted = asdict(output)
    except (TypeError, ValueError):
        return verdict(False, "Malformed or missing submission")
    if submitted != {"results": expected_results}:
        return verdict(False, "Submitted results differ from the reference schedule or processing order")
    try:
        calendar = read_calendar(Path(workspace))
    except (OSError, ValueError):
        return verdict(False, "Missing or malformed calendar")
    if calendar != expected_calendar:
        return verdict(False, "Calendar differs from the reference bookings")
    return verdict(True, "All assignments and calendar bookings match the reference")
