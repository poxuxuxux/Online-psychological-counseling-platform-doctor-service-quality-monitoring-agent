import time
from dataclasses import replace

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import ScriptedModel


def test_guest_job_capability_and_result_survive_app_restart(tmp_path, catalog, session):
    settings = replace(Settings(), database_url="sqlite:///" + str(tmp_path / "host.sqlite3"),
                       team_protocol="legacy", seed_demo=False)
    def app():
        return create_app(settings=settings, catalog=catalog, model=ScriptedModel())

    with TestClient(app()) as client:
        created = client.post('/api/v1/guest/jobs', json=session.model_dump(mode='json'))
        assert created.status_code == 202
        job = created.json()
        path = '/api/v1/guest/jobs/' + job['job_id']
        headers = {'X-Guest-Token': job['token']}
        assert client.get(path).status_code == 404
        assert client.get(path, headers={'X-Guest-Token': 'wrong'}).status_code == 404
        for _ in range(200):
            status = client.get(path, headers=headers).json()
            if status['report']:
                break
            time.sleep(.01)
        assert status['status'] == 'completed'
        assert status['report']['session_id'] == session.session_id
        assert client.get('/api/v1/evaluations/recent').json()['items'] == []
        assert client.get('/api/v1/consultations').json()['total'] == 0
    with TestClient(app()) as client:
        restored = client.get(path, headers=headers).json()
        assert restored['report'] == status['report']


def test_guest_job_request_returns_before_model_finishes(tmp_path, catalog, session):
    import asyncio

    class Slow(ScriptedModel):
        async def json(self, *args):
            await asyncio.sleep(10)
            return await super().json(*args)

    settings = replace(Settings(), database_url="sqlite:///" + str(tmp_path / "host.sqlite3"), seed_demo=False)
    app = create_app(settings=settings, catalog=catalog, model=Slow())
    with TestClient(app) as client:
        job = client.post('/api/v1/guest/jobs', json=session.model_dump(mode='json')).json()
        path = '/api/v1/guest/jobs/' + job['job_id']
        headers = {'X-Guest-Token': job['token']}
        state = client.get(path, headers=headers).json()
        assert state['status'] == 'running'
        assert state['report'] is None
    with TestClient(create_app(settings=settings, catalog=catalog, model=Slow())) as client:
        assert client.get(path, headers=headers).json()['status'] == 'interrupted'
        assert client.post(path + '/resume', headers=headers).status_code == 202
        assert client.post(path + '/resume', headers=headers).status_code == 202
        assert client.get(path, headers=headers).json()['status'] == 'running'
