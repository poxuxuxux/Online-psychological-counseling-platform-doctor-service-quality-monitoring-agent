# 环节：网络故障回归；用途：保留可定位的传输类型，避免泄漏密钥/代理地址/供应商响应。
import json
import socket
import ssl

import httpx
import pytest

from app.domain.ports import ModelUnavailable
from app.infrastructure.model import JsonModelGateway, transport_diagnostics
from app.infrastructure.telemetry import model_usage
from app.team.post_initial_protocol import PROTOCOL_V2
from tests.test_post_initial import PostInitialModel


@pytest.mark.parametrize(('error', 'category'), [
    (httpx.ProxyError('secret-proxy'), 'proxy'),
    (httpx.RemoteProtocolError('secret-body'), 'remote_protocol'),
    (httpx.ReadError('secret-key'), 'read_write'),
    (httpx.ConnectTimeout('secret-url'), 'timeout'),
    (httpx.ConnectError('secret-url'), 'connect'),
])
def test_exception_categories_do_not_include_messages(error, category):
    detail = transport_diagnostics(error, 'example.test')
    assert detail['category'] == category
    assert 'secret' not in json.dumps(detail)


def test_dns_and_certificate_causes_are_identified():
    for cause, expected in [(socket.gaierror('secret-dns'), 'dns'),
                            (ssl.SSLCertVerificationError('secret-cert'), 'tls')]:
        error = httpx.ConnectError('secret')
        error.__cause__ = cause
        assert transport_diagnostics(error, 'example.test')['category'] == expected


async def test_gateway_preserves_safe_transport_detail_in_telemetry_and_error(monkeypatch, caplog):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'secret-api-key')
    def fail(request):
        raise httpx.RemoteProtocolError('secret-remote-response')
    gateway = JsonModelGateway(httpx.MockTransport(fail))
    records = []
    token = model_usage.set(records)
    try:
        with pytest.raises(ModelUnavailable, match='model_connection_failed') as result:
            await gateway.json('JSON', {}, {})
        assert result.value.diagnostics['exception_type'] == 'RemoteProtocolError'
        assert records[0]['transport_error']['category'] == 'remote_protocol'
        assert 'secret' not in caplog.text
        assert 'secret' not in json.dumps(result.value.diagnostics)
    finally:
        model_usage.reset(token)


async def test_failed_stage_report_keeps_transport_type(make_service, session):
    class Broken(PostInitialModel):
        async def json(self, system, payload, schema):
            if payload['purpose'] == 'leader_weight_scenario':
                error = ModelUnavailable('model_connection_failed')
                error.diagnostics = transport_diagnostics(httpx.ReadError('secret'), 'example.test')
                raise error
            return await super().json(system, payload, schema)
    service, _ = await make_service(Broken(), team_protocol=PROTOCOL_V2)
    report = await service.evaluate(session)
    assert report['team']['stop_reason'] == 'model_connection_failed'
    detail = report['execution_issues'][-1]
    assert detail['stage'] == 'leader_weight_scenario'
    assert detail['transport']['exception_type'] == 'ReadError'
    assert 'secret' not in json.dumps(detail)
