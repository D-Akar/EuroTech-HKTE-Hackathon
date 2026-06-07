"""APScheduler wiring for scheduled check-in calls.

A single AsyncIOScheduler is started/stopped via the FastAPI lifespan. Each
``ScheduledCall`` becomes one job (job id == schedule id):
  - one-off   -> a ``date`` trigger that fires once at ``scheduled_at``
  - recurring -> a daily ``cron`` trigger at ``scheduled_at``'s time
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from . import call_store, checkin_agent, data
from .models import ScheduledCall
from .services import telephony

scheduler = AsyncIOScheduler()


def _job_id(schedule_id: int) -> str:
    return f"schedule-{schedule_id}"


async def _run_schedule(schedule_id: int) -> None:
    """Fire a scheduled call: resolve patient + questions, then place the call."""
    schedule = call_store.get_schedule(schedule_id)
    if schedule is None or schedule.status != "pending":
        return
    patient = data.get_patient(schedule.patient_id)
    if patient is None:
        return
    # Re-resolve at fire time so a recurring daily call always asks the freshest
    # personalised questions; falls back to config if none have been generated.
    questions = telephony.resolve_questions(schedule.patient_id)
    # Same consent-gated persona as the instant "Call now" path, unless the patient
    # has a custom prompt/greeting configured.
    config = call_store.get_config(schedule.patient_id)
    system_prompt = None if config.system_prompt else checkin_agent.system_prompt(patient)
    first_message = None if config.greeting else checkin_agent.first_message(patient)
    await telephony.place_call(
        patient,
        to_number=patient.phone_number,
        questions=questions,
        kind="scheduled",
        system_prompt=system_prompt,
        first_message=first_message,
    )
    # A one-off has done its job; hide it from the upcoming list.
    if not schedule.recurring:
        call_store.cancel_schedule(schedule_id)


def schedule_call(schedule: ScheduledCall) -> None:
    """Register a job for a newly created schedule."""
    if schedule.recurring:
        trigger = CronTrigger(
            hour=schedule.scheduled_at.hour, minute=schedule.scheduled_at.minute
        )
    else:
        trigger = DateTrigger(run_date=schedule.scheduled_at)
    scheduler.add_job(
        _run_schedule,
        trigger=trigger,
        args=[schedule.id],
        id=_job_id(schedule.id),
        replace_existing=True,
    )


def unschedule_call(schedule_id: int) -> None:
    """Remove a schedule's job if it is still registered."""
    if scheduler.get_job(_job_id(schedule_id)) is not None:
        scheduler.remove_job(_job_id(schedule_id))


def schedule_retention() -> None:
    """Register a daily data-retention purge (PRIVACY.md §10). No-op work when all
    retention periods are 0 (the default), so it is safe to always schedule."""
    from . import retention

    scheduler.add_job(
        retention.run,
        trigger=CronTrigger(hour=3, minute=30),  # quiet hour
        id="data-retention",
        replace_existing=True,
    )


def start() -> None:
    if not scheduler.running:
        scheduler.start()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
