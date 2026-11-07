DISRUPTION = "closure-001"


def timestamp(time):
    return f"2026-12-08T{time}:00Z"


def appointment(appointment_id, priority, original, earliest, latest, service="consult", duration=30):
    return {
        "appointment_id": appointment_id,
        "priority": priority,
        "original_start": f"2026-12-07T{original}:00Z",
        "earliest_start": timestamp(earliest),
        "latest_end": timestamp(latest),
        "service": service,
        "duration_minutes": duration,
        "allowed_locations": ["north", "south"],
    }


def slot(slot_id, start, end, location="north", service="consult"):
    return {
        "slot_id": slot_id,
        "start": timestamp(start),
        "end": timestamp(end),
        "location": location,
        "service": service,
    }


# Deliberately unsorted tool data.
APPOINTMENTS = [
    appointment("D", 2, "10:00", "09:00", "10:30"),
    appointment("B", 1, "08:30", "09:00", "10:00"),
    appointment("F", 2, "11:00", "09:00", "11:00", "imaging", 45),
    appointment("A", 0, "11:00", "09:00", "09:30"),
    appointment("E", 2, "10:30", "09:00", "10:00"),
    appointment("C", 2, "10:00", "09:00", "10:30"),
]
SLOTS = [
    slot("S-12", "10:00", "10:30", "south"),
    slot("S-09", "09:00", "09:30"),
    slot("S-11", "10:00", "10:30"),
    slot("S-08", "09:00", "09:30", "south"),
    slot("S-10", "09:30", "10:00"),
    slot("S-07", "09:00", "09:30", "east"),
    slot("S-13", "10:00", "10:30", service="imaging"),
]
INITIAL = {"existing-001": "S-08"}
APPOINTMENT_BY_ID = {row["appointment_id"]: row for row in APPOINTMENTS}
SLOT_BY_ID = {row["slot_id"]: row for row in SLOTS}
