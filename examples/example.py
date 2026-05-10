import asyncio
import os

from kintone_python_runtime import ApiTokenAuth, KintoneClient


async def main() -> None:
    base = os.environ["KINTONE_BASE_URL"]
    token = os.environ["KINTONE_API_TOKEN"]
    app_id = int(os.environ["KINTONE_APP_ID"])

    async with KintoneClient(base, auth=ApiTokenAuth(token=token)) as client:
        loaded = await client.records.get_records(app_id, fields=["$id"])
        print("first page size:", len(loaded.records))
        # up = await client.files.upload(filename="sample.txt", data=b"hello")
        # body = await client.files.download(up.fileKey)


if __name__ == "__main__":
    asyncio.run(main())
