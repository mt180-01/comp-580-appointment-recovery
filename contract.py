from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    CHECK = "check_workspace"
    APPOINTMENTS = "list_appointments"
    SLOTS = "list_slots"
    BOOK = "book_slot"
    BOOK_BATCH = "book_slots"


class Task(Enum):
    RECOVER = "recover-appointments"


@dataclass
class Appointment(Output):
    appointment_id: Annotated[str, "Appointment ID from list_appointments"]
    priority: Annotated[int, "Process lower numbers first"]
    original_start: Annotated[str, "Original UTC start, used to break priority ties"]
    earliest_start: Annotated[str, "Inclusive earliest permitted UTC start"]
    latest_end: Annotated[str, "Inclusive latest permitted UTC end"]
    service: Annotated[str, "Required service, compared exactly"]
    duration_minutes: Annotated[int, "Minimum slot duration in whole minutes"]
    allowed_locations: Annotated[list[str], "Permitted location IDs"]


@dataclass
class Slot(Output):
    slot_id: Annotated[str, "Slot ID from list_slots"]
    start: Annotated[str, "Slot start in UTC"]
    end: Annotated[str, "Slot end in UTC"]
    service: Annotated[str, "Required service, compared exactly"]
    location: Annotated[str, "Location ID"]


@dataclass
class AppointmentsOutput(Output):
    appointments: Annotated[list[Appointment], "Affected appointments, not sorted by priority"]


@dataclass
class SlotsOutput(Output):
    slots: Annotated[list[Slot], "Currently unbooked slots, not sorted by start"]


@dataclass
class BookingOutput(Output):
    appointment_id: Annotated[str, "Appointment ID from list_appointments"]
    slot_id: Annotated[str, "Slot ID from list_slots"]


@dataclass
class RecoveryData(Output):
    appointments: Annotated[list[Appointment], "New affected appointments with unique IDs"]
    slots: Annotated[list[Slot], "Candidate slots with unique IDs"]
    existing_bookings: Annotated[list[BookingOutput], "Existing reservations to preserve, using distinct slots"]


@dataclass
class RecoveryInput(Output):
    disruption_id: Annotated[str, "Disruption label; closure-001 loads the bundled example when dataset is null"]
    dataset: Annotated[RecoveryData | None, "Supply new appointments, slots, and reservations, or null for the example"]


@dataclass
class BookInput(RecoveryInput):
    appointment_id: Annotated[str, "Appointment ID from list_appointments"]
    slot_id: Annotated[str, "Slot ID from list_slots"]


@dataclass
class Assignment(Output):
    appointment_id: Annotated[str, "Appointment ID from list_appointments"]
    slot_id: Annotated[str | None, "Booked slot ID or null"]
    reason: Annotated[str | None, "NO_ELIGIBLE_SLOT when unbooked, otherwise null"]


@dataclass
class RecoveryOutput(Output):
    results: Annotated[list[Assignment], "One result per affected appointment, in processing order"]


@dataclass
class WorkspaceOutput(Output):
    clean: Annotated[bool, "True only when the task workspace has no previous saved result"]
    dataset_digest: Annotated[str, "SHA256 fingerprint of the validated task and source dataset"]


@dataclass
class BookBatchInput(RecoveryInput):
    bookings: Annotated[list[BookingOutput], "Chosen appointment and slot pairs in priority order"]


@dataclass
class BookBatchOutput(Output):
    bookings: Annotated[list[BookingOutput], "Confirmed bookings from this atomic batch"]


TOOLS = {
    Tool.BOOK_BATCH: (BookBatchInput, BookBatchOutput),
    Tool.CHECK: (RecoveryInput, WorkspaceOutput),
    Tool.APPOINTMENTS: (RecoveryInput, AppointmentsOutput),
    Tool.SLOTS: (RecoveryInput, SlotsOutput),
    Tool.BOOK: (BookInput, BookingOutput),
}
TASKS = {Task.RECOVER: (RecoveryInput, RecoveryOutput)}
