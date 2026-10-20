# 环节：后端测试层；用途：验证接口、工作流、规则策略或数据持久化行为。
from dataclasses import replace

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import ScriptedModel


async def test_cors_allows_only_configured_frontend_origin():
    settings = replace(Settings(), frontend_origins=("https://frontend.example",))
    transport = httpx.ASGITransport(app=create_app(settings=settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        headers = {
            "Origin": "https://frontend.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        }
        allowed = await client.options("/api/v1/evaluations", headers=headers)
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "https://frontend.example"
        blocked = await client.options(
            "/api/v1/evaluations",
            headers={**headers, "Origin": "https://unknown.example"},
        )
        assert "access-control-allow-origin" not in blocked.headers


def test_api_auth_evaluation_audit_and_compatibility(tmp_path, catalog, session):
    settings = replace(
        Settings(),
        database_url="sqlite:///" + str(tmp_path / "api.sqlite3"),
        api_token="test-token-at-least-24-characters",
        seed_demo=True,
    )
    headers = {"Authorization": "Bearer " + settings.api_token}
    with TestClient(
        create_app(settings=settings, model=ScriptedModel(), catalog=catalog)
    ) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/ready").json()["database"]["connected"]
        assert len(client.get("/api/v1/demo/sessions").json()) == 3
        assert (
            client.post("/api/v1/evaluations", json=session.model_dump(mode="json")).status_code
            == 401
        )
        response = client.post(
            "/api/v1/evaluations", json=session.model_dump(mode="json"), headers=headers
        )
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["status"] == "completed"
        run = report["evaluation_id"]
        assert client.get(f"/api/v1/runs/{run}/audit").status_code == 401
        audit = client.get(f"/api/v1/runs/{run}/audit", headers=headers).json()
        assert audit["team"]["events"]
        assert client.get("/api/v1/evaluations/recent").json()["items"] == []
        assert (
            client.get("/api/v1/evaluations/recent", headers=headers).json()["items"][0][
                "evaluation_id"
            ]
            == run
        )
        assert client.get("/api/v1/consultations/s1").status_code == 401
        overview = client.get("/api/v1/evaluations/overview?days=7", headers=headers).json()
        assert overview["counts"]["scored"] == 1
        assert len(overview["trend"]) == 7
        payload = {
            "evaluation_id": run,
            "finding_id": report["agent_results"][0]["findings"][0]["finding_id"],
            "decision": "确认",
            "reason": "人工核对原文一致",
        }
        assert (
            client.post(
                f"/api/v1/evaluations/{run}/reviews", json=payload, headers=headers
            ).status_code
            == 201
        )
        assert (
            len(client.get(f"/api/v1/evaluations/{run}/reviews", headers=headers).json()["items"])
            == 1
        )
        assert client.post(f"/api/v1/runs/{run}/execute", headers=headers).json() == report


def test_public_demo_cannot_spoof_private_content(tmp_path, catalog):
    settings = replace(Settings(), database_url="sqlite:///" + str(tmp_path / "demo.sqlite3"))
    with TestClient(create_app(settings, model=ScriptedModel(), catalog=catalog)) as client:
        demo = client.get("/api/v1/demo/session").json()
        response = client.post("/api/v1/evaluations", json=demo)
        assert response.status_code == 200
        report = response.json()
        assert report["status"] == "completed"
        review = {
            "evaluation_id": report["evaluation_id"],
            "finding_id": report["agent_results"][0]["findings"][0]["finding_id"],
            "decision": "确认",
            "reason": "人工核对合成原文",
        }
        assert (
            client.post(
                f"/api/v1/evaluations/{report['evaluation_id']}/reviews", json=review
            ).status_code
            == 201
        )
        demo["messages"][0]["content"] = "private input claiming synthetic source"
        assert client.post("/api/v1/evaluations", json=demo).status_code == 401
