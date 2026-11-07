import hashlib
import json

from .fixture import APPOINTMENTS, DISRUPTION, INITIAL, SLOTS
from .rules import utc_seconds


def require_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def unique_rows(rows, id_field):
    indexed = {}
    for row in rows:
        require_text(row[id_field], id_field)
        if row[id_field] in indexed:
            raise ValueError(f"{id_field} values must be unique")
        indexed[row[id_field]] = row
    return indexed


def load_data(task):
    require_text(task["disruption_id"], "disruption_id")
    dataset = task.get("dataset")
    if dataset is None:
        if task["disruption_id"] != DISRUPTION:
            raise ValueError("Unknown disruption; supply dataset for a new disruption")
        return {"disruption_id": DISRUPTION, "appointments": APPOINTMENTS, "slots": SLOTS, "initial": INITIAL}
    appointments = dataset["appointments"]
    slots = dataset["slots"]
    appointment_ids = unique_rows(appointments, "appointment_id")
    slot_ids = unique_rows(slots, "slot_id")
    for appointment in appointments:
        for key in ("priority", "duration_minutes"):
            value = appointment[key]
            if type(value) is not int or value < (1 if key == "duration_minutes" else 0):
                raise ValueError(f"{key} is outside its supported range")
        require_text(appointment["service"], "service")
        locations = appointment["allowed_locations"]
        for location in locations:
            require_text(location, "allowed location")
        if len(set(locations)) != len(locations):
            raise ValueError("Allowed locations must be distinct")
        for key in ("original_start", "earliest_start", "latest_end"):
            utc_seconds(appointment[key])
        if appointment["earliest_start"] > appointment["latest_end"]:
            raise ValueError("Appointment window is reversed")
    for slot in slots:
        require_text(slot["service"], "service")
        require_text(slot["location"], "location")
        if utc_seconds(slot["end"]) <= utc_seconds(slot["start"]):
            raise ValueError("Slot end must be after its start")
    initial = {}
    occupied = set()
    for booking in dataset["existing_bookings"]:
        appointment_id, slot_id = booking["appointment_id"], booking["slot_id"]
        require_text(appointment_id, "existing appointment ID")
        if appointment_id in appointment_ids or appointment_id in initial:
            raise ValueError("Existing appointments must be distinct from affected appointments")
        if slot_id not in slot_ids or slot_id in occupied:
            raise ValueError("Existing reservations must reference distinct, known slots")
        initial[appointment_id] = slot_id
        occupied.add(slot_id)
    return {
        "disruption_id": task["disruption_id"],
        "appointments": appointments,
        "slots": slots,
        "initial": initial,
    }


def task_digest(task):
    return hashlib.sha256(
        json.dumps(load_data(task), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
