"""Consultation browsing: source scope, pagination, no-report cases, and safe errors."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.evaluations import build_demo_session
from app.domain.models import EvaluationReport
from app.infrastructure.repositories.evaluations import PostgresEvaluationStore
from app.main import app


class Connection:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.queries = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def execute(self, sql, params):
        self.queries.append((sql, params))
        cursor = AsyncMock()
        cursor.fetchone.return_value = next(self.answers)
        cursor.fetchall.return_value = cursor.fetchone.return_value
        return cursor


def test_unconfigured_database_is_explicit_and_detail_is_not_invented():
    with TestClient(app) as client:
        assert client.get('/api/v1/consultations').json() == {
            'database_configured': False, 'total': 0, 'items': []}
        assert client.get('/api/v1/consultations/unknown').status_code == 404


def test_pagination_validation_and_safe_failure(monkeypatch):
    monkeypatch.setattr(PostgresEvaluationStore, 'list_consultations',
                        AsyncMock(side_effect=RuntimeError('secret-database-credentials')))
    with TestClient(app) as client:
        assert client.get('/api/v1/consultations?limit=51').status_code == 422
        assert client.get('/api/v1/consultations?offset=-1').status_code == 422
        response = client.get('/api/v1/consultations')
        assert response.status_code == 503
        assert 'secret' not in response.text


@pytest.mark.asyncio
async def test_list_includes_unscored_sessions_and_parameterizes_search(monkeypatch):
    session = build_demo_session()
    needle = "' OR TRUE --"
    connection = Connection([(2,), [(session.session_id, session.model_dump(mode='json'),
                                     datetime.now(UTC), None)]])
    store = PostgresEvaluationStore('postgresql://unused')
    monkeypatch.setattr(store, '_connect', AsyncMock(return_value=connection))
    result = await store.list_consultations(5, 5, needle)
    assert result['total'] == 2
    assert result['items'][0]['evaluation_status'] is None
    assert result['items'][0]['message_count'] == 6
    sql, params = connection.queries[1]
    assert needle not in sql
    assert params == (needle, 5, 5)
    assert "source_id = 'synthetic-demo'" in sql
    assert 'LEFT JOIN LATERAL' in sql


@pytest.mark.asyncio
async def test_detail_keeps_missing_report_empty(monkeypatch):
    session = build_demo_session()
    connection = Connection([(session.model_dump(mode='json'), None)])
    store = PostgresEvaluationStore('postgresql://unused')
    monkeypatch.setattr(store, '_connect', AsyncMock(return_value=connection))
    result = await store.consultation_detail(session.session_id)
    assert result['session']['session_id'] == session.session_id
    assert result['report'] is None
    assert connection.queries[0][1] == (session.session_id,)
    assert "source_id = 'synthetic-demo'" in connection.queries[0][0]


@pytest.mark.asyncio
async def test_detail_rejects_mismatched_storage_ids(monkeypatch):
    connection = Connection([(build_demo_session().model_dump(mode='json'), None)])
    store = PostgresEvaluationStore('postgresql://unused')
    monkeypatch.setattr(store, '_connect', AsyncMock(return_value=connection))
    with pytest.raises(ValueError, match='mismatch'):
        await store.consultation_detail('different-id')


def test_detail_endpoint_returns_stored_report_without_re_evaluation(monkeypatch):
    session = build_demo_session().model_dump(mode='json')
    stored = {'session': session, 'report': {'session_id': session['session_id'],
                                           'evaluation_id': 'stored-evaluation'}}
    method = AsyncMock(return_value=stored)
    monkeypatch.setattr(PostgresEvaluationStore, 'consultation_detail', method)
    with TestClient(app) as client:
        response = client.get('/api/v1/consultations/' + session['session_id'])
    assert response.status_code == 200
    assert response.json() == stored
    method.assert_awaited_once_with(session['session_id'])


@pytest.mark.asyncio
async def test_detail_returns_saved_report_and_preserves_discussion_fields(monkeypatch):
    session = build_demo_session()
    report = EvaluationReport(evaluation_id='saved-report', session_id=session.session_id,
                              status='completed').model_dump(mode='json')
    report['discussions'] = [{'finding_id': 'f-1', 'text': 'stored discussion'}]
    connection = Connection([(session.model_dump(mode='json'), report)])
    store = PostgresEvaluationStore('postgresql://unused')
    monkeypatch.setattr(store, '_connect', AsyncMock(return_value=connection))
    result = await store.consultation_detail(session.session_id)
    assert result['report'] == report
    assert 'ORDER BY created_at DESC, evaluation_id DESC LIMIT 1' in connection.queries[0][0]


@pytest.mark.asyncio
async def test_detail_blocks_another_sessions_report(monkeypatch):
    session = build_demo_session()
    report = EvaluationReport(evaluation_id='bad-report', session_id='another-session',
                              status='completed').model_dump(mode='json')
    connection = Connection([(session.model_dump(mode='json'), report)])
    store = PostgresEvaluationStore('postgresql://unused')
    monkeypatch.setattr(store, '_connect', AsyncMock(return_value=connection))
    with pytest.raises(ValueError, match='report/session mismatch'):
        await store.consultation_detail(session.session_id)
