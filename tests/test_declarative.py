import json

import httpx
import pytest
import respx

from kintone_python_runtime import (
    ApiTokenAuth,
    ExecutionBackend,
    KintoneClient,
    RecordOperationSpec,
    RecordWriteMode,
    RunSpec,
)

BASE = "https://example.cybozu.com"


@pytest.fixture
def api():
    return respx.mock(base_url=BASE, assert_all_called=False)


@pytest.mark.asyncio
async def test_run_spec_local_upsert(api, tmp_path):
    bodies: list[dict] = []

    def capture(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content.decode())
        bodies.append(data)
        return httpx.Response(200, json={"records": []})

    api.put("/k/v1/records.json").mock(side_effect=capture)
    spec = RunSpec(
        backend=ExecutionBackend.LOCAL,
        operations=[
            RecordOperationSpec(
                app=7,
                mode=RecordWriteMode.UPSERT,
                records=[
                    {"updateKey": {"field": "code", "value": f"C{i}"}, "record": {}}
                    for i in range(150)
                ],
                chunk_size=100,
                concurrency=2,
            )
        ],
    )
    with api:
        async with KintoneClient(
            BASE,
            auth=ApiTokenAuth(token="t"),
            state_dir=str(tmp_path),
        ) as client:
            handle = client.run(spec)
            events = [event async for event in handle.events()]
            summary = await handle.wait()

    assert summary.succeeded_chunks == 2
    assert summary.succeeded_records == 150
    assert summary.failed_chunks == 0
    assert len(bodies) == 2
    assert all(body.get("upsert") is True for body in bodies)
    assert events[0].type == "run_started"
    assert events[-1].type == "run_finished"


@pytest.mark.asyncio
async def test_run_spec_redis_requires_url(tmp_path):
    spec = RunSpec(
        backend=ExecutionBackend.REDIS,
        operations=[
            RecordOperationSpec(
                app=1,
                records=[{"record": {}}],
                mode=RecordWriteMode.INSERT,
            )
        ],
    )
    async with KintoneClient(
        BASE,
        auth=ApiTokenAuth(token="t"),
        state_dir=str(tmp_path),
    ) as client:
        with pytest.raises(ValueError, match="redis_url"):
            client.run(spec)
