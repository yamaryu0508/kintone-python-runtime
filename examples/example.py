"""
kintone-python-runtime の利用例（宣言的実行 + ファイル API）。

必要な環境変数:
  KINTONE_BASE_URL  例: https://example.cybozu.com
  KINTONE_API_TOKEN アプリの API トークン
  KINTONE_APP_ID    対象アプリのアプリ ID（整数）

任意（レコードの追加・更新デモを有効にする場合）:
  KINTONE_MUTATE=1
  KINTONE_TEXT_FIELD   文字列1行フィールドのフィールドコード（追加・更新に使用）
  KINTONE_UPDATE_RECORD_ID  更新だけ試す場合のレコード番号（未設定なら QUERY 結果の先頭を使用）
"""

from __future__ import annotations

import asyncio
import os

from kintone_python_runtime import (
    ApiTokenAuth,
    ExecutionBackend,
    KintoneRuntime,
    RecordOperationSpec,
    RecordWriteMode,
    RunSpec,
)


async def main() -> None:
    base = os.environ["KINTONE_BASE_URL"]
    token = os.environ["KINTONE_API_TOKEN"]
    app_id = int(os.environ["KINTONE_APP_ID"])
    mutate = os.environ.get("KINTONE_MUTATE") == "1"
    text_field = os.environ.get("KINTONE_TEXT_FIELD")
    state_dir = os.environ.get("KINTONE_STATE_DIR", ".kintone_runs")

    async with KintoneRuntime(base, auth=ApiTokenAuth(token=token), state_dir=state_dir) as runtime:
        # --- 宣言的実行: レコード取得（QUERY）---
        read_spec = RunSpec(
            backend=ExecutionBackend.LOCAL,
            operations=[
                RecordOperationSpec(
                    app=app_id,
                    mode=RecordWriteMode.QUERY,
                    query="order by $id desc limit 3",
                    fields=["$id"],
                    total_count=False,
                )
            ],
        )
        handle = runtime.run(read_spec)
        async for event in handle.events():
            if event.type == "chunk_succeeded" and event.data is not None:
                print(
                    "declarative QUERY:",
                    event.data.get("records"),
                    "rows (totalCount=",
                    event.data.get("totalCount"),
                    ")",
                )
        summary = await handle.wait()
        print("run summary:", summary.model_dump())

        # --- ファイル: アップロード → ダウンロード（宣言的パイプライン外の低レベル API）---
        up = await runtime.files.upload(
            filename="sample.txt",
            data=b"hello from kintone-python-runtime\n",
        )
        print("upload fileKey:", up.fileKey)
        body = await runtime.files.download(up.fileKey)
        print("download bytes:", len(body))

        if not mutate:
            print(
                "skip INSERT/UPDATE "
                "(set KINTONE_MUTATE=1 and KINTONE_TEXT_FIELD to run write demos)"
            )
            return

        if not text_field:
            raise SystemExit("KINTONE_MUTATE=1 requires KINTONE_TEXT_FIELD")

        # --- 宣言的実行: レコード追加 ---
        insert_spec = RunSpec(
            backend=ExecutionBackend.LOCAL,
            operations=[
                RecordOperationSpec(
                    app=app_id,
                    mode=RecordWriteMode.INSERT,
                    records=[
                        {
                            "record": {
                                text_field: {"value": "inserted via RunSpec INSERT"},
                            }
                        }
                    ],
                    chunk_size=100,
                    concurrency=1,
                )
            ],
        )
        ins_handle = runtime.run(insert_spec)
        async for _ in ins_handle.events():
            pass
        ins_summary = await ins_handle.wait()
        print("INSERT run:", ins_summary.model_dump())

        # --- 宣言的実行: レコード更新（既存 1 件の文字列フィールドを上書き）---
        update_id_str = os.environ.get("KINTONE_UPDATE_RECORD_ID")
        if update_id_str is None:
            page = await runtime.records.get_records(
                app_id,
                query="order by $id desc limit 1",
                fields=["$id"],
            )
            if not page.records:
                raise SystemExit("no records to update; create one or set KINTONE_UPDATE_RECORD_ID")
            update_id_str = page.records[0]["$id"]["value"]

        update_spec = RunSpec(
            backend=ExecutionBackend.LOCAL,
            operations=[
                RecordOperationSpec(
                    app=app_id,
                    mode=RecordWriteMode.UPDATE,
                    records=[
                        {
                            "id": update_id_str,
                            "record": {
                                text_field: {"value": "updated via RunSpec UPDATE"},
                            },
                        }
                    ],
                    chunk_size=100,
                    concurrency=1,
                )
            ],
        )
        upd_handle = runtime.run(update_spec)
        async for _ in upd_handle.events():
            pass
        upd_summary = await upd_handle.wait()
        print("UPDATE run:", upd_summary.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
