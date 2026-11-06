# 环节：后端测试层；用途：验证接口、工作流、规则策略或数据持久化行为。
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain.ports import ModelUnavailable
from app.main import create_app
from tests.conftest import ScriptedModel


def test_retry_requires_access_preserves_original_and_returns_new_run(tmp_path, catalog, session):
    class Unavailable(ScriptedModel):
        async def json(self, *args):
            raise ModelUnavailable("model_timeout")

    settings = replace(Settings(team_protocol="legacy"), seed_demo=False,
                       database_url="sqlite:///" + str(tmp_path / "retry.sqlite3"),
                       api_token="test-token-at-least-24-characters")
    with TestClient(create_app(settings=settings, model=Unavailable(), catalog=catalog)) as client:
        headers = {"Authorization": "Bearer " + settings.api_token}
        original = client.post("/api/v1/evaluations", json=session.model_dump(mode="json"),
                               headers=headers).json()
        path = f"/api/v1/runs/{original['evaluation_id']}/retry"
        assert client.post(path).status_code == 401
        created = client.post(path, headers=headers)
        assert created.status_code == 201
        new_id = created.json()["run_id"]
        assert new_id != original["evaluation_id"]
        assert client.get(f"/api/v1/runs/{new_id}", headers=headers).json()["status"] == "pending"
        assert client.get(f"/api/v1/runs/{original['evaluation_id']}",
                          headers=headers).json()["report"] == original


def test_guest_evaluation_needs_no_token_and_is_not_published(tmp_path, catalog, session):
    settings = replace(
        Settings(team_protocol="legacy"), database_url="sqlite:///" + str(tmp_path / "guest-host.sqlite3"),
        api_token="test-token-at-least-24-characters", seed_demo=False,
    )
    with TestClient(create_app(settings=settings, model=ScriptedModel(), catalog=catalog)) as client:
        response = client.post(
            "/api/v1/guest/evaluations", json=session.model_dump(mode="json")
        )
        assert response.status_code == 200, response.text
        assert response.json()["session_id"] == session.session_id
        assert client.get("/api/v1/consultations").json()["total"] == 0
        assert client.get("/api/v1/evaluations/recent").json()["items"] == []
        assert client.get("/api/v1/consultations/" + session.session_id).status_code == 404


def test_private_consultation_catalog_requires_token_and_excludes_demo(tmp_path, catalog, session):
    settings = replace(
        Settings(team_protocol="legacy"), database_url="sqlite:///" + str(tmp_path / "listing.sqlite3"),
        api_token="test-token-at-least-24-characters", seed_demo=True,
    )
    headers = {"Authorization": "Bearer " + settings.api_token}
    with TestClient(create_app(settings=settings, model=ScriptedModel(), catalog=catalog)) as client:
        assert client.get("/api/v1/consultations?scope=private").status_code == 401
        assert client.get("/api/v1/consultations?scope=private", headers=headers).json()["total"] == 0
        imported = client.post("/api/v1/sessions", json=session.model_dump(mode="json"), headers=headers)
        assert imported.status_code == 201
        listing = client.get("/api/v1/consultations?scope=private", headers=headers).json()
        assert listing["total"] == 1
        assert [item["session_id"] for item in listing["items"]] == [session.session_id]
        in_range = client.get(
            "/api/v1/consultations?scope=private&start_date=2026-01-01&end_date=2026-01-01",
            headers=headers,
        ).json()
        out_of_range = client.get(
            "/api/v1/consultations?scope=private&start_date=2025-12-31&end_date=2025-12-31",
            headers=headers,
        ).json()
        assert in_range["total"] == 1
        assert out_of_range["total"] == 0
        assert client.get(
            "/api/v1/consultations?scope=private&start_date=2026-01-02", headers=headers
        ).status_code == 422


async def test_cors_allows_only_configured_frontend_origin():
    settings = replace(Settings(team_protocol="legacy"), frontend_origins=("https://frontend.example",))
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
        Settings(team_protocol="legacy"),
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
        assert client.get("/api/v1/consultations?scope=private").status_code == 401
        private_list = client.get("/api/v1/consultations?scope=private", headers=headers).json()
        assert private_list["total"] == 1
        assert [item["session_id"] for item in private_list["items"]] == ["s1"]
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        overview = client.get(
            f"/api/v1/evaluations/overview?start_date={today}&end_date={today}",
            headers=headers,
        ).json()
        assert overview["counts"]["scored"] == 1
        assert len(overview["trend"]) == 1
        assert overview["period_start"] == overview["period_end"] == str(today)
        previous = today - timedelta(days=1)
        empty_overview = client.get(
            f"/api/v1/evaluations/overview?start_date={previous}&end_date={previous}",
            headers=headers,
        ).json()
        assert empty_overview["counts"]["scored"] == 0
        doctors = client.get(
            f"/api/v1/monitoring/doctors?start_date={today}&end_date={today}",
            headers=headers,
        ).json()
        assert doctors["days"] == 1
        assert [doctor["doctor_id"] for doctor in doctors["doctors"]] == ["d1"]
        profile = client.get(
            f"/api/v1/monitoring/doctors/d1?start_date={today}&end_date={today}",
            headers=headers,
        ).json()
        assert profile["days"] == 1
        assert profile["period_start"] == profile["period_end"] == str(today)
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
    settings = replace(Settings(team_protocol="legacy"), database_url="sqlite:///" + str(tmp_path / "demo.sqlite3"))
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
