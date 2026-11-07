# Appointment Recovery

An offline NanoAgent plugin for rebooking appointments displaced by a fictional location closure.

## Tools

The recover-appointments task exposes list_appointments, list_slots, and book_slots. The standalone book_slot tool remains available for individual bookings. The hidden check_workspace reference tool enforces a fresh workspace.

## Layout

The manifest and contract define the task. The MCP server lives in src/plugin.
The verifier package contains the fixed fixture and the reference scheduler.

## Develop and run

Use Python 3.12 or newer and uv. From the plugin directory:

    uv sync --locked --extra dev
    uv run --frozen pytest
    uv run --frozen ruff check .

Run the NanoAgent task `recover-appointments` with `{"disruption_id":"closure-001","dataset":null}` in a fresh task workspace. NanoAgent supplies `NANOAGENT_WORKSPACE` to the MCP server. The fixture is bundled in the plugin and requires no network access at runtime.

## Scheduling and verification

Lower priority numbers come first. Break appointment ties by original start and then appointment ID. A slot must match the service and allowed locations, fit entirely inside the inclusive time window, and have sufficient duration. Reserve the whole slot, choosing the earliest eligible start and then the lexicographically lowest slot ID. Report `NO_ELIGIBLE_SLOT` when no eligible slot remains.

The booking tool writes to a workspace JSON calendar with unique appointment and slot IDs. Repeating an identical booking is safe. The task saves its chosen bookings atomically with book_slots. A conflict rejects the whole batch. Tool calls within one task run are sequential. Use a separate workspace for concurrent runs. The verifier starts with the bundled original reservations and independently allocates slots in processing order. It checks every submitted row and compares the entire saved calendar with the expected state, including preexisting bookings.

The bundled example has one disruption. New datasets can supply any valid UTC dates and IDs. A reused workspace is rejected by the reference check, including when it contains a correct result from an earlier run. Slots are independent units of capacity and all timestamps are UTC. The verifier checks final state and submitted order. It does not inspect the chronology of booking calls.



## New input datasets

Version 0.2.0 accepts new records in the required dataset field. Set dataset to null
to use the original demo. For a new disruption, supply a disruption_id label and
dataset containing appointments, slots, and existing_bookings.
tests/fixtures/unseen-input.json is a complete runnable input using new IDs and
appointments spanning midnight on a leap day.

Use canonical UTC timestamps YYYY-MM-DDTHH:MM:SSZ. Cross-day and cross-year slots
are supported. IDs must be unique, duration_minutes must be a positive integer,
and priority must be a nonnegative integer. Slots must have a positive duration.
Existing bookings must reference distinct known slots and appointment IDs outside
the affected set. Empty appointment and slot lists are supported.

The hidden reference pins a SHA256 fingerprint of the validated dataset and
disruption label. The verifier independently recomputes the priority allocation
for that input, checks the fingerprint, and verifies the saved calendar preserves
all supplied existing reservations.

Supply the full JSON input to the task in RUSH Lab. Keep datasets small enough
to fit the platform's model context, output, and runtime limits. Each run requires
a fresh workspace.


## RUSH Lab publication

Upload this version's files to the plugin's existing GitHub repository, including the updated uv.lock. Version 0.2.0 must be submitted again on RUSH Lab after pushing.
Include the hidden .env and .gitignore files and uv.lock. Exclude .venv,
Python caches, test caches, run reports, and validation logs.

Submit the repository URL in the RUSH Lab course workspace marketplace.
After installation, run the task using the example input above in a fresh
workspace. Keep the exact input, test logs, and platform verdicts for the
milestone report. A scripted MCP test establishes the tool and verifier
workflow. A live model run on RUSH Lab remains part of final validation.
