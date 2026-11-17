from __future__ import annotations

import asyncio

from backend.streaming_manager import StreamingManager


def test_stop_cancels_and_joins_generation_task() -> None:
    async def run_test() -> None:
        manager = StreamingManager()
        job = manager.create("conversation")
        started = asyncio.Event()

        async def generate() -> None:
            started.set()
            await asyncio.Event().wait()

        job.task = asyncio.create_task(generate())
        await started.wait()

        assert await manager.stop(job.job_id)
        assert job.task.cancelled()
        assert not await manager.stop(job.job_id)

    asyncio.run(run_test())
