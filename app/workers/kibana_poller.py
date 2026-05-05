from __future__ import annotations

import asyncio
import contextlib

from app.config import Settings
from app.services.detection_service import DetectionService


class KibanaPollingWorker:
    def __init__(self, *, settings: Settings, detection_service: DetectionService) -> None:
        self._settings = settings
        self._detection_service = detection_service
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="kibana-polling-worker")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def poll_once(self) -> None:
        try:
            await self._detection_service.poll_all_enabled_sources()
        except Exception:
            # The poller must never take down the admin/API server.
            return

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            await self.poll_once()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._settings.kibana_poll_interval_seconds,
                )
