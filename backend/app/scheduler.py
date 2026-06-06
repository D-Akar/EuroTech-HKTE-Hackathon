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

from . import call_store, data
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
    await telephony.place_call(
        patient,
        to_number=patient.phone_number,
        questions=schedule.questions,
        kind="scheduled",
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


def start() -> None:
    if not scheduler.running:
        scheduler.start()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
