"""Server-Sent Events stream — real-time push to the dashboard.

The frontend opens one ``EventSource('/events')`` and recolors patients the
instant a ``patient_status`` event arrives (e.g. an escalation flipping a patient
to urgent). A periodic comment heartbeat keeps the connection alive through
proxies and lets us notice client disconnects promptly.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .. import events

router = APIRouter(tags=["events"])

_HEARTBEAT_SECS = 20


@router.get("/events")
async def stream(request: Request) -> StreamingResponse:
    queue = events.register()

    async def gen():
        try:
            # Tell the client the stream is live straight away.
            yield "event: ready\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECS)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"  # comment frame — keeps the socket warm
        finally:
            events.unregister(queue)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        # Disable proxy buffering (nginx) so events flush immediately.
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
