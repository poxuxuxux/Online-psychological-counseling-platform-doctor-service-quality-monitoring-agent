# 环节：后端测试层；用途：验证 Bucket 引用写入、旧数据迁移及失败时的原文保留。
import copy
import io
import json
from dataclasses import replace

import pytest

from app.config import Settings
from app.context.service import preprocess
from app.infrastructure.object_store import S3JsonStore
from app.infrastructure.repository import Repository
from app.rubrics.catalog import SkillKnowledgeSource
from app.workflow.service import EvaluationService
from tests.conftest import ScriptedModel


class MemoryStore:
    def __init__(self):
        self.objects = {}
        self.fail = False
        self.sequence = 0

    async def put(self, kind, identifier, value):
        if self.fail:
            raise RuntimeError("bucket_unavailable")
        key = f"{kind}/{identifier}/{self.sequence}"
        self.sequence += 1
        self.objects[key] = copy.deepcopy(value)
        return {"__object_store_v1__": True, "key": key, "sha256": "test"}

    async def get(self, reference):
        return copy.deepcopy(self.objects[reference["key"]])

    async def delete(self, reference):
        self.objects.pop(reference["key"])

    async def ping(self):
        if self.fail:
            raise RuntimeError("bucket_unavailable")


async def test_new_session_and_run_keep_only_bucket_references(tmp_path, session):
    store = MemoryStore()
    repo = Repository("sqlite:///" + str(tmp_path / "bucket.sqlite3"), object_store=store)
    await repo.initialize()
    normalized = preprocess(session)
    await repo.save_session(normalized)
    await repo.save_session(normalized)
    state = {"run_id": "run-1", "session": normalized, "status": "pending"}
    await repo.create_run(state)
    rows = await repo._transaction(
        [
            ("SELECT payload FROM team_sessions", ()),
            ("SELECT payload FROM team_runs", ()),
        ]
    )
    assert len(store.objects) == 2
    assert all("我最近很难过" not in payload for group in rows for (payload,) in group)
    assert all(json.loads(payload)["__object_store_v1__"] for group in rows for (payload,) in group)
    assert await repo.session(session.session_id) == normalized
    assert await repo.get_run("run-1") == state
    assert await repo.claim("run-1", "test", 60)
    revised = {**state, "status": "running"}
    await repo.checkpoint(revised, "test")
    assert await repo.get_run("run-1") == revised
    assert len(store.objects) == 2  # session plus current snapshot; old snapshot was removed
    listing = await repo.consultations(5, 0, "s1", public=False)
    assert listing["items"][0]["message_count"] == 2


async def test_migration_keeps_legacy_rows_readable_and_is_idempotent(tmp_path, session):
    url = "sqlite:///" + str(tmp_path / "migration.sqlite3")
    legacy = Repository(url)
    await legacy.initialize()
    normalized = preprocess(session)
    await legacy.save_session(normalized)
    state = {"run_id": "run-1", "session": normalized, "status": "pending"}
    await legacy.create_run(state)
    store = MemoryStore()
    upgraded = Repository(url, object_store=store)
    assert await upgraded.session(session.session_id) == normalized
    assert await upgraded.migrate_inline_payloads() == {"sessions": 1, "runs": 1}
    assert await upgraded.migrate_inline_payloads() == {"sessions": 0, "runs": 0}
    assert await upgraded.session(session.session_id) == normalized
    assert await upgraded.get_run("run-1") == state
    assert "我最近很难过" not in str(
        await upgraded._transaction([("SELECT payload FROM team_sessions", ())])
    )


async def test_failed_bucket_upload_never_replaces_database_payload(tmp_path, session):
    url = "sqlite:///" + str(tmp_path / "failed.sqlite3")
    legacy = Repository(url)
    await legacy.initialize()
    normalized = preprocess(session)
    await legacy.save_session(normalized)
    store = MemoryStore()
    store.fail = True
    upgraded = Repository(url, object_store=store)
    with pytest.raises(RuntimeError, match="bucket_unavailable"):
        await upgraded.migrate_inline_payloads()
    assert await legacy.session(session.session_id) == normalized
    assert (await upgraded.readiness())["bucket"] == {"configured": True, "connected": False}


async def test_s3_adapter_encrypts_compresses_and_checks_integrity(monkeypatch):
    import boto3
    from cryptography.fernet import Fernet

    class Client:
        def __init__(self):
            self.objects = {}

        def put_object(self, **kwargs):
            self.objects[kwargs["Key"]] = kwargs["Body"]

        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(self.objects[kwargs["Key"]])}

        def delete_object(self, **kwargs):
            del self.objects[kwargs["Key"]]

        def list_objects_v2(self, **kwargs):
            return {"Contents": []}

    client = Client()
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: client)
    store = S3JsonStore(
        "bucket", "https://s3.example", "auto", "access", "secret", Fernet.generate_key().decode()
    )
    value = {"session_id": "s1", "messages": [{"content": "仅在加密对象中保存的对话"}]}
    reference = await store.put("sessions", "s1", value)
    assert "仅在加密对象".encode() not in client.objects[reference["key"]]
    assert await store.get(reference) == value
    await store.ping()
    with pytest.raises(ValueError, match="checksum"):
        await store.get({**reference, "sha256": "0" * 64})
    with pytest.raises(ValueError, match="BUCKET_ENCRYPTION_KEY"):
        S3JsonStore("bucket", "https://s3.example", "auto", "access", "secret")


async def test_evaluation_completes_with_bucket_backed_snapshots(tmp_path, session, catalog):
    url = "sqlite:///" + str(tmp_path / "workflow.sqlite3")
    store = MemoryStore()
    repo = Repository(url, object_store=store)
    await repo.initialize()
    service = EvaluationService(
        replace(Settings(team_protocol="legacy"), database_url=url, seed_demo=False),
        repo,
        ScriptedModel(),
        catalog,
        SkillKnowledgeSource(catalog),
    )
    report = await service.evaluate(session)
    assert report["status"] == "completed"
    assert await repo.session("s1") == preprocess(session)
    assert (await repo.get_run(report["evaluation_id"]))["report"] == report
    assert len(store.objects) == 2
