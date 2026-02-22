import asyncio

_queue: "asyncio.Queue[int]" = asyncio.Queue()

async def enqueue(job_id: int):
    await _queue.put(job_id)

async def dequeue() -> int:
    return await _queue.get()
