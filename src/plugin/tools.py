import json
import os
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile

from contract import (
    Appointment,
    AppointmentsOutput,
    BookBatchOutput,
    BookingOutput,
    Slot,
    SlotsOutput,
    Tool,
    WorkspaceOutput,
)
from verifier.calendar import CALENDAR, read_calendar
from verifier.data import load_data, task_digest
from verifier.rules import eligible


def list_appointments(value, workspace):
    return AppointmentsOutput([Appointment(**row) for row in load_data(asdict(value))["appointments"]])


def current_calendar(workspace, initial):
    try:
        return read_calendar(workspace)
    except FileNotFoundError:
        return initial.copy()


def list_slots(value, workspace):
    data = load_data(asdict(value))
    booked = current_calendar(workspace, data["initial"])
    occupied = set(booked.values())
    return SlotsOutput([Slot(**row) for row in data["slots"] if row["slot_id"] not in occupied])


def save_bookings(bookings, workspace, task):
    data = load_data(asdict(task))
    appointments = {row["appointment_id"]: row for row in data["appointments"]}
    slots = {row["slot_id"]: row for row in data["slots"]}
    booked = current_calendar(workspace, data["initial"])
    ids = [row.appointment_id for row in bookings]
    if len(set(ids)) != len(ids):
        raise ValueError("Expected distinct appointment IDs")
    for value in bookings:
        appointment = appointments.get(value.appointment_id)
        slot = slots.get(value.slot_id)
        if appointment is None or slot is None or not eligible(appointment, slot):
            raise ValueError("Unknown appointment, unknown slot, or ineligible slot")
        if booked.get(value.appointment_id) != value.slot_id:
            if value.appointment_id in booked or value.slot_id in booked.values():
                raise ValueError("Appointment or slot is already booked")
            booked[value.appointment_id] = value.slot_id
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=workspace, delete=False) as temporary:
        path = Path(temporary.name)
        try:
            json.dump(booked, temporary)
            temporary.close()
            os.replace(path, workspace / CALENDAR)
        finally:
            path.unlink(missing_ok=True)


def book_slot(value, workspace):
    save_bookings([value], workspace, value)
    return BookingOutput(value.appointment_id, value.slot_id)


def book_slots(value, workspace):
    save_bookings(value.bookings, workspace, value)
    return BookBatchOutput(value.bookings)


def checked(implementation):
    def call(value, workspace):
        load_data(asdict(value))
        return implementation(value, workspace)

    return call


def check_workspace(value, workspace):
    return WorkspaceOutput(clean=not (workspace / CALENDAR).exists(), dataset_digest=task_digest(asdict(value)))


IMPLEMENTATIONS = {
    Tool.CHECK: check_workspace,
    Tool.APPOINTMENTS: checked(list_appointments),
    Tool.SLOTS: checked(list_slots),
    Tool.BOOK: checked(book_slot),
    Tool.BOOK_BATCH: checked(book_slots),
}
