from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field


@dataclass
class StreamJob:
    job_id: str
    conversation_id: str
    events: list[dict[str, object]] = field(default_factory=list)
    task: asyncio.Task[None] | None = None
    done: bool = False

    def emit(self, event: dict[str, object]) -> None:
        self.events.append(event)


class StreamingManager:
    def __init__(self) -> None:
        self.jobs: dict[str, StreamJob] = {}

    def create(self, conversation_id: str) -> StreamJob:
        job = StreamJob(str(uuid.uuid4()), conversation_id)
        self.jobs[job.job_id] = job
        if len(self.jobs) > 200:
            completed = [key for key, value in self.jobs.items() if value.done]
            for key in completed[: len(self.jobs) - 200]:
                self.jobs.pop(key, None)
        return job

    def get(self, job_id: str) -> StreamJob | None:
        return self.jobs.get(job_id)

    async def stop(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or job.done or job.task is None or job.task.done():
            return False
        job.task.cancel()
        try:
            await job.task
        except asyncio.CancelledError:
            pass
        return True
