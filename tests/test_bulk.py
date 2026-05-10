import pytest

from kintone_python_runtime import run_in_chunks


@pytest.mark.asyncio
async def test_run_in_chunks_concurrency():
    running = 0
    peak = 0

    async def proc(chunk: list[int]) -> tuple[int, ...]:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        try:
            return tuple(chunk)
        finally:
            running -= 1

    items = list(range(25))
    out = await run_in_chunks(items, chunk_size=10, processor=proc, concurrency=2)
    flat = [x for part in out for x in part]
    assert flat == items
    assert peak <= 2


@pytest.mark.asyncio
async def test_run_in_chunks_empty():
    async def proc(_chunk: list[int]) -> int:
        return 0

    assert await run_in_chunks([], chunk_size=5, processor=proc, concurrency=3) == []
