# kintone-python-runtime

[![CI](https://github.com/yamaryu0508/kintone-python-runtime/actions/workflows/ci.yml/badge.svg)](https://github.com/yamaryu0508/kintone-python-runtime/actions/workflows/ci.yml)

**非同期のみ**の [kintone](https://www.kintone.com/) 向け Python Runtime です。  
2026 年の生成 AI 時代を前提に、**宣言的 Spec → 実行 Run → 構造化 Event ストリーム**を中心に設計しています。  
**Python 3.12+**、**HTTP/2 既定 ON**（[`httpx`](https://www.python-httpx.org/)）、型付きモデル（Pydantic v2）、制御（`aiolimiter` + `anyio`）に対応しています。

本パッケージは **サードパーティ製**であり、サイボウズ株式会社および kintone 公式製品とは関係ありません。API の正本は [kintone REST API ドキュメント](https://cybozu.dev/ja/kintone/docs/rest-api/) を参照してください。**kintone** はサイボウズ株式会社の登録商標です。

以前の当リポジトリにあった同期版とは **API 非互換** です（移行表は意図的に置いていません）。

## 対応範囲（現状）

| 領域 | 内容 |
|------|------|
| 実行モデル | 宣言的 `RunSpec` / `RecordOperationSpec` / `RunEvent` |
| バックエンド | `local`（標準、追加サービス不要）/ `redis`（オプション） |
| 認証 | API トークン（`X-Cybozu-API-Token`） |
| レコード | 取得・カーソル逐次取得・追加・更新・宣言的バッチ実行（insert/update/upsert） |
| ファイル | アップロード（multipart）・`fileKey` によるダウンロード |
| マルチテナント | **サブドメイン（ドメイン）単位で `KintoneClient` を分ける**想定。ゲストスペースは `guest_space_id` を指定 |

その他の API（アプリ設定、スペース等）は今後の拡張対象です。

## インストール（利用者向け）

Git から入れる場合（[**uv**](https://docs.astral.sh/uv/) の pip 互換コマンド）:

```bash
uv pip install git+https://github.com/yamaryu0508/kintone-python-runtime
```

**PyPI** への公開は別途予定です。利用方法が固まり次第、`pip` / `uv add` 向けの記載を追加します。

```python
from kintone_python_runtime import KintoneClient
```

## 開発（リポジトリを clone した場合）

**Dev Container 含め、パッケージ管理は uv を前提にしています。**

```bash
uv sync --extra dev
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright
uv run pytest -v
```

Redis バックエンドまで検証する場合:

```bash
uv sync --extra dev --extra redis
```

### なぜ local は SQLite なのか

`local` バックエンドで使っている `sqlite3` は **Python 標準ライブラリ**です。  
そのため、`local` 実行は **「Python本体 + Pythonライブラリのみ」**の条件を満たします（外部DB・外部サービス不要）。

## Redis バックエンドへのスイッチ手順

1. 依存を追加インストール

```bash
uv sync --extra dev --extra redis
```

2. Redis を起動（ローカル）

```bash
docker compose -f docker-compose.redis.yml up -d
```

3. `KintoneClient` に `redis_url` を渡し、`RunSpec.backend` を `REDIS` に変更

```python
from kintone_python_runtime import ExecutionBackend, RunSpec

client = KintoneClient(
    "https://YOUR_SUBDOMAIN.cybozu.com",
    auth=ApiTokenAuth(token="YOUR_API_TOKEN"),
    redis_url="redis://localhost:6379/0",
)

spec = RunSpec(
    backend=ExecutionBackend.REDIS,
    operations=[...],
)
run = client.run(spec)
```

4. 停止

```bash
docker compose -f docker-compose.redis.yml down
```

## Redis 実サーバー統合テスト（docker compose）

現時点のテストは `local` 中心です。Redis 実サーバー連携を確認する場合は次の手順で実施してください。

1. Redis 起動

```bash
docker compose -f docker-compose.redis.yml up -d
```

2. 依存同期

```bash
uv sync --extra dev --extra redis
```

3. 宣言的実行を `REDIS` で起動し、`run.events()` と Redis 側の run 状態（`krc:runs:<run_id>`）を確認

4. 後片付け

```bash
docker compose -f docker-compose.redis.yml down -v
```

## Redis バックエンドのワーカ分離（別プロセス実行）導入手順

現状の `redis` 実装は「状態保存を Redis に書く」段階です。  
**完全な分散実行**（producer/worker 分離）へ進める際は次の順で拡張します。

1. Queue 抽象を追加（`enqueue/dequeue/ack/retry`）
2. `RunSpec` をジョブにシリアライズして Redis Queue に投入
3. 別プロセス worker（`arq`）でジョブを実行
4. `RunEvent` を Redis Stream に出力
5. `run.events()` は Redis Stream を購読する実装へ切替

推奨スタック:

- Queue/Worker: `arq`
- Redis client: `redis.asyncio`
- Event stream: Redis Streams

## テスト確認手順（まとめ）

### 1) Local backend（標準）

```bash
uv sync --extra dev
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright
uv run pytest -v
```

### 2) Redis backend（追加）

```bash
uv sync --extra dev --extra redis
docker compose -f docker-compose.redis.yml up -d
uv run pytest -v -k declarative
docker compose -f docker-compose.redis.yml down -v
```

## Quick start（宣言的実行）

```python
import asyncio

from kintone_python_runtime import (
    ApiTokenAuth,
    ExecutionBackend,
    KintoneClient,
    RecordOperationSpec,
    RecordWriteMode,
    RunSpec,
)


async def main() -> None:
    async with KintoneClient(
        "https://YOUR_SUBDOMAIN.cybozu.com",
        auth=ApiTokenAuth(token="YOUR_API_TOKEN"),
        rate_limit_per_second=5,
        max_concurrent_requests=8,
        http2=True,
        state_dir=".kintone_runs",
        redis_url="redis://localhost:6379/0",  # local backendのみなら不要
    ) as client:
        spec = RunSpec(
            backend=ExecutionBackend.LOCAL,  # REDIS に切替可能
            operations=[
                RecordOperationSpec(
                    app=123,
                    mode=RecordWriteMode.UPSERT,
                    chunk_size=100,
                    concurrency=5,
                    records=[
                        {
                            "updateKey": {"field": "code", "value": "C-001"},
                            "record": {"title": {"value": "hello"}},
                        }
                    ],
                )
            ],
        )
        run = client.run(spec)
        async for event in run.events():
            print(event.type, event.operation_index, event.chunk_index, event.error)
        summary = await run.wait()
        print(summary.succeeded_records)


asyncio.run(main())
```

## 低レイヤー API（必要時）

宣言的実行に加えて、従来型の低レイヤー API も利用できます。

```python
page = await client.records.get_records(123, fields=["$id"])
async for rec in client.records.iterate_records_by_id(123):
    ...
```

## ファイル API（低レイヤー）

```python
from pathlib import Path

from kintone_python_runtime import ApiTokenAuth, KintoneClient


async def file_example(client: KintoneClient) -> None:
    up = await client.files.upload(filename="note.txt", data=b"hello")
    print(up.fileKey)

    up2 = await client.files.upload_path(Path("./logo.png"))

    body = await client.files.download(up.fileKey)
    print(len(body))
```

ゲストスペース利用時は、レコードと同様に `KintoneClient(..., guest_space_id=...)` を指定すると、`/k/guest/{id}/v1/file.json` などが組み立てられます。

## リリース・バージョン

- **現在のバージョン**は `pyproject.toml` および `kintone_python_runtime.__version__` と一致させています。
- **セマンティックバージョニング**を前提に、宣言的モデル強化に伴う破壊的変更は積極的に取り込みます。
- **GitHub Release**（タグ付け）は公開手順の正とし、変更内容はコミット履歴とリリースノートで追えるようにします。
- リリース一覧: [GitHub Releases](https://github.com/yamaryu0508/kintone-python-runtime/releases)

不具合・要望は [GitHub Issues](https://github.com/yamaryu0508/kintone-python-runtime/issues) へどうぞ。

## 例

- [examples/example.py](https://github.com/yamaryu0508/kintone-python-runtime/blob/main/examples/example.py)

## ライセンス

[The MIT License (MIT)](https://github.com/yamaryu0508/kintone-python-runtime/blob/main/LICENSE)
