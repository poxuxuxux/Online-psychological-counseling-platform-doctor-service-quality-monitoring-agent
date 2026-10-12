"""Validate the production HTML/assets and existing demo API as one shipping contract."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_frontend_assets_are_served_and_no_dev_entry_is_shipped():
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "心衡" in response.text
        assert "/src/main.ts" not in response.text
        assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', response.text)
        assert len(assets) >= 2
        for asset in assets:
            assert client.get(asset).status_code == 200


def test_existing_demo_evaluation_contract_remains_available():
    with TestClient(app) as client:
        session = client.get("/api/v1/demo/session").json()
        result = client.post("/api/v1/evaluations", json=session)
        assert result.status_code == 200
        report = result.json()
        assert report["session_id"] == session["session_id"]
        assert len(report["agent_results"]) == 3
        assert sum(len(a["findings"]) for a in report["agent_results"]) == 7


def test_offline_preview_is_self_contained():
    preview = (Path(__file__).parents[1] / "frontend-preview.html").read_text(encoding="utf-8")
    assert "<script>" in preview
    assert "<style>" in preview
    assert not re.search(r"<script[^>]*src=", preview)
    assert "/src/main.ts" not in preview
    assert "离线交互样例" in preview
