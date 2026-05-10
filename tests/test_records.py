import json

import httpx
import pytest
import respx

from kintone_python_runtime import ApiTokenAuth, KintoneAPIError, KintoneRuntime

BASE = "https://example.cybozu.com"


@pytest.fixture
def api():
    return respx.mock(base_url=BASE, assert_all_called=False)


@pytest.mark.asyncio
async def test_get_records_empty(api):
    route = api.get("/k/v1/records.json").mock(
        return_value=httpx.Response(200, json={"records": []})
    )
    with api:
        async with KintoneRuntime(BASE, auth=ApiTokenAuth(token="tok")) as runtime:
            r = await runtime.records.get_records(42, query='f = "x"', fields=["a", "b"])
        assert r.records == []
        sent = route.calls.last.request
    assert sent.method == "GET"
    assert "app=42" in str(sent.url)
    assert "query=" in str(sent.url)


@pytest.mark.asyncio
async def test_guest_space_path(api):
    route = api.get("/k/guest/7/v1/records.json").mock(
        return_value=httpx.Response(200, json={"records": []})
    )
    with api:
        async with KintoneRuntime(
            BASE,
            auth=ApiTokenAuth(token="tok"),
            guest_space_id=7,
        ) as runtime:
            await runtime.records.get_records(1)
        assert route.calls.last.request.url.path == "/k/guest/7/v1/records.json"


@pytest.mark.asyncio
async def test_kintone_error_message(api):
    api.get("/k/v1/records.json").mock(
        return_value=httpx.Response(
            400,
            json={"code": "CB_IL02", "message": "invalid", "errors": {}},
        )
    )
    with api:
        async with KintoneRuntime(BASE, auth=ApiTokenAuth(token="t")) as runtime:
            with pytest.raises(KintoneAPIError) as exc:
                await runtime.records.get_records(1)
    assert exc.value.status_code == 400
    assert "invalid" in str(exc.value)


@pytest.mark.asyncio
async def test_iterate_records_pages(api):
    calls = {"n": 0}

    def side_effect(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            payload = {"records": [{"$id": {"value": str(i)}} for i in range(1, 501)]}
        else:
            payload = {"records": [{"$id": {"value": "501"}}]}
        return httpx.Response(200, json=payload)

    api.get("/k/v1/records.json").mock(side_effect=side_effect)
    with api:
        async with KintoneRuntime(BASE, auth=ApiTokenAuth(token="t")) as runtime:
            rows = [r async for r in runtime.records.iterate_records_by_id(9)]
    assert len(rows) == 501


@pytest.mark.asyncio
async def test_add_and_update_record(api):
    api.post("/k/v1/record.json").mock(
        return_value=httpx.Response(200, json={"id": "1", "revision": "2"})
    )
    api.put("/k/v1/record.json").mock(return_value=httpx.Response(200, json={"revision": "3"}))
    with api:
        async with KintoneRuntime(BASE, auth=ApiTokenAuth(token="t")) as runtime:
            a = await runtime.records.add_record(1, {"Name": {"value": "x"}})
            assert a.id == "1"
            u = await runtime.records.update_record(1, 10, {"Name": {"value": "y"}}, revision=2)
            assert u.revision == "3"


@pytest.mark.asyncio
async def test_add_records_chunked(api):
    bodies: list[dict] = []

    def capture(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content.decode())
        bodies.append(data)
        n = len(data["records"])
        ids = [str(i) for i in range(n)]
        revs = ["1"] * n
        return httpx.Response(200, json={"ids": ids, "revisions": revs})

    api.post("/k/v1/records.json").mock(side_effect=capture)
    with api:
        async with KintoneRuntime(BASE, auth=ApiTokenAuth(token="t")) as runtime:
            records = [{"x": {"value": str(i)}} for i in range(150)]
            r = await runtime.records.add_records_chunked(5, records, chunk_size=100, concurrency=2)
    assert len(r.ids) == 150
    assert len(bodies) == 2
    assert len(bodies[0]["records"]) == 100
    assert len(bodies[1]["records"]) == 50
