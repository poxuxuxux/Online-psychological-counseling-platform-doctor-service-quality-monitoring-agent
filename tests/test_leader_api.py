# 环节：新版API回归；用途：确认新运行默认进入Leader协议，且完整报告/审计使用已有权限保护。
from dataclasses import replace

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.test_leader_protocol import ProtocolModel


def test_v1_api_still_protects_its_audit(tmp_path, catalog, session):
    settings = replace(Settings(team_protocol="leader-review-v1"), seed_demo=False,
                       database_url="sqlite:///" + str(tmp_path / "leader.sqlite3"),
                       api_token="test-token-at-least-24-characters")
    assert settings.team_protocol == "leader-review-v1"
    with TestClient(create_app(settings, model=ProtocolModel(), catalog=catalog)) as client:
        headers = {"Authorization": "Bearer " + settings.api_token}
        response = client.post('/api/v1/evaluations', headers=headers, json=session.model_dump(mode='json'))
        assert response.status_code == 200, response.text
        report = response.json()
        assert report['collaboration']['protocol'] == settings.team_protocol
        assert report['quality_profile']['overall_score'] == 4
        assert client.get(report['team']['audit_url']).status_code == 401
        assert client.get(report['team']['audit_url'], headers=headers).json()['team']['reports']


def test_guest_new_protocol_report_is_returned_without_persisting_source(tmp_path, catalog, session):
    settings = replace(Settings(team_protocol="leader-review-v1"), seed_demo=False,
                       database_url="sqlite:///" + str(tmp_path / "guest.sqlite3"))
    with TestClient(create_app(settings, model=ProtocolModel(), catalog=catalog)) as client:
        response = client.post('/api/v1/guest/evaluations', json=session.model_dump(mode='json'))
        assert response.status_code == 200
        assert response.json()['collaboration']['protocol'] == settings.team_protocol
        assert client.get('/api/v1/evaluations/recent').json()['items'] == []
