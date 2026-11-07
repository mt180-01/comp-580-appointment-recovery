import json

CALENDAR = "recovery-calendar.json"


def read_calendar(workspace):
    calendar = json.loads((workspace / CALENDAR).read_text(encoding="utf-8"))
    if not isinstance(calendar, dict) or any(not isinstance(slot, str) for slot in calendar.values()):
        raise ValueError("Expected a calendar mapping appointment IDs to slot IDs")
    if len(set(calendar.values())) != len(calendar):
        raise ValueError("Calendar contains a repeated slot")
    return calendar
