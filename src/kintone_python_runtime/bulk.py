from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


async def run_in_chunks[T, R](
    items: list[T],
    chunk_size: int,
    processor: Callable[[list[T]], Awaitable[R]],
    *,
    concurrency: int,
) -> list[R]:
    """
    Process items in fixed-size chunks with a maximum number of concurrent chunk jobs.

    Semantics match the common asyncio.Semaphore + asyncio.gather pattern (similar to p-limit).
    """
    if chunk_size < 1:
        msg = "chunk_size must be >= 1"
        raise ValueError(msg)
    if concurrency < 1:
        msg = "concurrency must be >= 1"
        raise ValueError(msg)
    if not items:
        return []
    chunks = [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]
    semaphore = asyncio.Semaphore(concurrency)

    async def worker(chunk: list[T]) -> R:
        async with semaphore:
            return await processor(chunk)

    return await asyncio.gather(*(worker(c) for c in chunks))
