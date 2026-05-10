import httpx
import pytest
import respx

from kintone_python_runtime import ApiTokenAuth, KintoneClient


@pytest.mark.asyncio
async def test_default_user_agent_header():
    with respx.mock(base_url="https://x.cybozu.com", assert_all_called=False) as router:
        route = router.get("/k/v1/records.json").mock(
            return_value=httpx.Response(200, json={"records": []})
        )
        async with KintoneClient("https://x.cybozu.com", auth=ApiTokenAuth(token="t")) as client:
            await client.records.get_records(1)
    ua = route.calls.last.request.headers.get("User-Agent", "")
    assert "kintone_python_runtime" in ua


@pytest.mark.asyncio
async def test_custom_user_agent_header():
    with respx.mock(base_url="https://x.cybozu.com", assert_all_called=False) as router:
        route = router.get("/k/v1/records.json").mock(
            return_value=httpx.Response(200, json={"records": []})
        )
        async with KintoneClient(
            "https://x.cybozu.com",
            auth=ApiTokenAuth(token="t"),
            user_agent="custom-ua",
        ) as client:
            await client.records.get_records(1)
    assert route.calls.last.request.headers["User-Agent"] == "custom-ua"
