import asyncio
import os

from kintone_python_runtime import ApiTokenAuth, KintoneRuntime


async def main() -> None:
    base = os.environ["KINTONE_BASE_URL"]
    token = os.environ["KINTONE_API_TOKEN"]
    app_id = int(os.environ["KINTONE_APP_ID"])

    async with KintoneRuntime(base, auth=ApiTokenAuth(token=token)) as runtime:
        loaded = await runtime.records.get_records(app_id, fields=["$id"])
        print("first page size:", len(loaded.records))
        # up = await runtime.files.upload(filename="sample.txt", data=b"hello")
        # body = await runtime.files.download(up.fileKey)


if __name__ == "__main__":
    asyncio.run(main())
