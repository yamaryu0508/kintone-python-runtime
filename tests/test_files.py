import httpx
import pytest
import respx

from kintone_python_runtime import ApiTokenAuth, KintoneRuntime

BASE = "https://example.cybozu.com"


@pytest.fixture
def api():
    return respx.mock(base_url=BASE, assert_all_called=False)


@pytest.mark.asyncio
async def test_upload_file(api):
    route = api.post("/k/v1/file.json").mock(
        return_value=httpx.Response(200, json={"fileKey": "abc123"})
    )
    with api:
        async with KintoneRuntime(BASE, auth=ApiTokenAuth(token="t")) as runtime:
            r = await runtime.files.upload(filename="hello.txt", data=b"hello")
        assert r.fileKey == "abc123"
        req = route.calls.last.request
    assert req.method == "POST"
    assert "multipart/form-data" in req.headers.get("content-type", "").lower()


@pytest.mark.asyncio
async def test_upload_guest_space(api):
    route = api.post("/k/guest/3/v1/file.json").mock(
        return_value=httpx.Response(200, json={"fileKey": "k"})
    )
    with api:
        async with KintoneRuntime(
            BASE,
            auth=ApiTokenAuth(token="t"),
            guest_space_id=3,
        ) as runtime:
            await runtime.files.upload(filename="a.png", data=b"\x89PNG")
        assert route.calls.last.request.url.path == "/k/guest/3/v1/file.json"


@pytest.mark.asyncio
async def test_download_file(api):
    route = api.get("/k/v1/file.json").mock(
        return_value=httpx.Response(200, content=b"binary-payload")
    )
    with api:
        async with KintoneRuntime(BASE, auth=ApiTokenAuth(token="t")) as runtime:
            data = await runtime.files.download("file-key-1")
        assert data == b"binary-payload"
        assert "fileKey=file-key-1" in str(route.calls.last.request.url)
