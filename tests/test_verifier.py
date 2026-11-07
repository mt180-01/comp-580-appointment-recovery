from dataclasses import asdict

import anyio
import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from slimconfig import build_output, plain_output

from contract import TOOLS, Assignment, BookInput, RecoveryInput, RecoveryOutput, Task, Tool, WorkspaceOutput
from plugin.__main__ import server
from plugin.tools import book_slot
from verifier import verify_output, verify_task
from verifier.calendar import CALENDAR
from verifier.data import task_digest

TASK = RecoveryInput("closure-001", None)
GOLD = [("A", "S-09"), ("B", "S-10"), ("C", "S-11"), ("D", "S-12"), ("E", None), ("F", None)]


def submission(rows=GOLD):
    return RecoveryOutput(
        [Assignment(appointment, slot, None if slot else "NO_ELIGIBLE_SLOT") for appointment, slot in rows]
    )


def verify(workspace, output):
    return verify_task(Task.RECOVER.value, TASK, output, WorkspaceOutput(True, task_digest(asdict(TASK))), workspace)


def book(workspace, rows=GOLD):
    for appointment, slot in rows:
        if slot:
            book_slot(
                BookInput(
                    disruption_id=TASK.disruption_id, dataset=TASK.dataset, appointment_id=appointment, slot_id=slot
                ),
                workspace,
            )


def test_competition_and_retry(tmp_path):
    book(tmp_path, GOLD[:1])
    book(tmp_path, GOLD[:1])
    with pytest.raises(ValueError, match="already booked"):
        book(tmp_path, [("B", "S-09")])
    book(tmp_path, GOLD[1:])
    assert verify(tmp_path, submission())["valid"]


def test_exact_tie(tmp_path):
    swapped = [*GOLD[:2], ("C", "S-12"), ("D", "S-11"), *GOLD[4:]]
    book(tmp_path, swapped)
    assert not verify(tmp_path, submission(swapped))["valid"]


def test_no_eligible_slot(tmp_path):
    book(tmp_path)
    output = submission()
    assert verify(tmp_path, output)["valid"]
    output.results[-1].reason = None
    assert not verify(tmp_path, output)["valid"]


def test_claimed_booking_absent(tmp_path):
    book(tmp_path, GOLD[:-3])
    assert "Calendar differs" in verify(tmp_path, submission())["message"]


def test_missing_and_malformed(tmp_path):
    assert "Missing" in verify(tmp_path, submission())["message"]
    (tmp_path / CALENDAR).write_text("corrupt", encoding="utf-8")
    assert "malformed calendar" in verify(tmp_path, submission())["message"]
    assert not verify(tmp_path, None)["valid"]
    assert not verify(tmp_path, submission(GOLD[:-1]))["valid"]


def test_mcp_run(tmp_path, monkeypatch):
    async def run():
        async with create_connected_server_and_client_session(server) as client:
            assert {tool.name for tool in (await client.list_tools()).tools} == {tool.value for tool in Tool}

            async def call(tool, **fields):
                arguments = {"disruption_id": TASK.disruption_id, "dataset": None, **fields}
                response = await client.call_tool(tool.value, arguments)
                assert not response.isError, response.content
                given, made = TOOLS[tool]
                data = response.structuredContent
                result = verify_output(tool.value, build_output(arguments, given), build_output(data, made), tmp_path)
                assert result["valid"], result
                return data

            appointments = (await call(Tool.APPOINTMENTS))["appointments"]
            slots = (await call(Tool.SLOTS))["slots"]
            assert len(appointments) == 6
            assert "S-08" not in {slot["slot_id"] for slot in slots}
            for appointment, slot in GOLD:
                if slot:
                    await call(Tool.BOOK, appointment_id=appointment, slot_id=slot)
            slots = (await call(Tool.SLOTS))["slots"]
            assert {slot["slot_id"] for slot in slots} == {"S-07", "S-13"}
            assert verify(tmp_path, submission())["valid"]

    monkeypatch.setenv("NANOAGENT_WORKSPACE", str(tmp_path))
    anyio.run(run)


def test_stdio_run(tmp_path):
    import os
    import sys

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "plugin"],
            env={**os.environ, "NANOAGENT_WORKSPACE": str(tmp_path)},
        )
        async with stdio_client(parameters) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            for tool in (Tool.APPOINTMENTS, Tool.SLOTS):
                response = await client.call_tool(tool.value, {"disruption_id": TASK.disruption_id, "dataset": None})
                assert not response.isError, response.content
            response = await client.call_tool(
                Tool.BOOK_BATCH.value,
                {
                    "disruption_id": TASK.disruption_id,
                    "dataset": None,
                    "bookings": [{"appointment_id": a, "slot_id": s} for a, s in GOLD if s],
                },
            )
            assert not response.isError, response.content
            given = build_output(plain_output(TASK), RecoveryInput)
            made = build_output(plain_output(submission()), RecoveryOutput)
            assert verify_task(
                Task.RECOVER.value, given, made, WorkspaceOutput(True, task_digest(asdict(TASK))), tmp_path
            )["valid"]

    anyio.run(run)


def test_batch_is_atomic_and_retry_safe(tmp_path):
    from contract import BookBatchInput, BookingOutput
    from plugin.tools import book_slots
    from verifier.calendar import read_calendar

    invalid = BookBatchInput(
        disruption_id=TASK.disruption_id,
        dataset=TASK.dataset,
        bookings=[BookingOutput("A", "S-09"), BookingOutput("B", "S-09")],
    )
    with pytest.raises(ValueError, match="already booked"):
        book_slots(invalid, tmp_path)
    assert not (tmp_path / CALENDAR).exists()
    request = BookBatchInput(
        disruption_id=TASK.disruption_id, dataset=TASK.dataset, bookings=[BookingOutput(a, s) for a, s in GOLD if s]
    )
    book_slots(request, tmp_path)
    book_slots(request, tmp_path)
    assert read_calendar(tmp_path)["existing-001"] == "S-08"
    assert verify(tmp_path, submission())["valid"]


def test_reused_workspace_is_rejected(tmp_path):
    from plugin.tools import check_workspace

    assert check_workspace(TASK, tmp_path).clean
    book(tmp_path)
    reference = check_workspace(TASK, tmp_path)
    assert not reference.clean
    assert not verify_task(Task.RECOVER.value, TASK, submission(), reference, tmp_path)["valid"]
    assert not verify_task(Task.RECOVER.value, TASK, submission(), None, tmp_path)["valid"]


def test_boundaries_and_ineligible_slots():
    from verifier.fixture import APPOINTMENT_BY_ID, SLOT_BY_ID
    from verifier.rules import eligible

    appointment = APPOINTMENT_BY_ID["A"]
    slot = SLOT_BY_ID["S-09"]
    assert eligible(appointment, slot)  # Exact earliest start, latest end, and duration.
    for changed in [
        dict(slot, start="2026-12-08T08:59:00Z"),
        dict(slot, end="2026-12-08T09:31:00Z"),
        dict(slot, end="2026-12-08T09:29:00Z"),
        dict(slot, location="east"),
        dict(slot, service="imaging"),
    ]:
        assert not eligible(appointment, changed)


def test_every_assignment_and_existing_reservation_is_checked(tmp_path):
    import json

    from verifier.calendar import read_calendar

    book(tmp_path)
    for index in range(len(GOLD)):
        output = submission()
        output.results[index].slot_id = "S-99"
        assert not verify(tmp_path, output)["valid"]
    output = submission()
    output.results.reverse()
    assert not verify(tmp_path, output)["valid"]
    calendar = read_calendar(tmp_path)
    calendar.pop("existing-001")
    (tmp_path / CALENDAR).write_text(json.dumps(calendar), encoding="utf-8")
    assert not verify(tmp_path, submission())["valid"]
