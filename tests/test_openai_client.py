import json
from datetime import date
from types import SimpleNamespace

import openai
import pytest

from app.llms.openai_client import OpenAIClient, ASSESSMENT_SCHEMA
from app.llms.factory import get_llm_client
from app.ontology.models import LaunchReadinessContext
from app.policy.readiness import enforce_readiness
from app.workflow.service import WorkflowService
from app.demo.scenarios import DEMO_DATE, prepare_scenario


def valid_response():
    return {'overall_status': 'Ready', 'executive_summary': 'No identified launch risks.',
            'recommended_actions': [], 'confidence': 'High',
            'human_review_required': False, 'human_review_reason': None}


def response(**overrides):
    values = {'id': 'resp_demo', 'status': 'completed', 'output_text': json.dumps(valid_response()),
              'output': [SimpleNamespace(type='message', content=[SimpleNamespace(type='output_text')])],
              'usage': SimpleNamespace(input_tokens=100, output_tokens=50, total_tokens=150)}
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def adapter(monkeypatch):
    captured = {}
    def create(**kwargs):
        captured['request'] = kwargs
        outcome = captured.get('outcome', response())
        if isinstance(outcome, Exception): raise outcome
        return outcome
    def init(**kwargs):
        captured['configuration'] = kwargs
        return SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr(openai, 'OpenAI', init)
    return OpenAIClient(api_key='test-private-key', model='test-model'), captured


def context():
    return LaunchReadinessContext('Test launch', date(2026, 8, 22), [], [], 1.0)


def test_structured_request_and_usage_metadata(adapter):
    client, captured = adapter
    assert client.generate(context()) == valid_response()
    request = captured['request']
    assert request['text']['format']['schema'] == ASSESSMENT_SCHEMA
    assert request['text']['format']['strict'] is True
    assert request['model'] == 'test-model'
    assert request['store'] is False
    assert request['max_output_tokens'] == 2048
    assert 'Test launch' in request['input'][1]['content']
    assert 'test-private-key' not in str(request)
    assert 'test-private-key' not in str(client.metadata)
    assert captured['configuration']['max_retries'] == 0
    assert captured['configuration']['timeout'] == 45
    assert client.metadata['usage']['total_tokens'] == 150
    assert client.metadata['response_id'] == 'resp_demo'


@pytest.mark.parametrize('outcome', [
    response(status='incomplete'), response(output_text=''), response(output_text='{bad json'),
    response(output=[SimpleNamespace(type='message', content=[SimpleNamespace(type='refusal')])]),
    response(output=[SimpleNamespace(type='function_call')]),
    response(output=[SimpleNamespace(type='message', content=[SimpleNamespace(type='unexpected')])]),
])
def test_invalid_provider_outcomes_require_review(adapter, outcome):
    client, captured = adapter
    captured['outcome'] = outcome
    result = enforce_readiness(context(), client.generate(context()))
    assert result['overall_status'] == 'Unknown'
    assert result['confidence'] == 'Low'
    assert result['recommended_actions'] == []
    assert result['human_review_required']


def test_api_failure_does_not_expose_raw_provider_message(adapter):
    client, captured = adapter
    captured['outcome'] = openai.APIConnectionError(message='test-private-key', request=None)
    result = client.generate(context())
    assert result['overall_status'] == 'Unknown'
    assert 'test-private-key' not in str(result)


@pytest.mark.parametrize('error_type,status', [(openai.AuthenticationError, 401), (openai.RateLimitError, 429), (openai.BadRequestError, 400)])
def test_provider_status_errors_are_sanitized(adapter, error_type, status):
    client, captured = adapter
    captured['outcome'] = error_type('test-private-key',
        response=SimpleNamespace(status_code=status, request=None, headers={}), body=None)
    result = enforce_readiness(context(), client.generate(context()))
    assert result['overall_status'] == 'Unknown'
    assert 'test-private-key' not in str(result)


def test_response_still_passes_application_contract_validation(adapter):
    client, captured = adapter
    bad = valid_response()
    bad['recommended_actions'] = [{'action': 'Invented action', 'signal_ids': ['invented'], 'conflict_fields': []}]
    captured['outcome'] = response(output_text=json.dumps(bad))
    assert enforce_readiness(context(), client.generate(context()))['overall_status'] == 'Unknown'


def test_model_cannot_override_blocker_and_inference_is_persisted(adapter, tmp_path):
    client, _ = adapter
    data = prepare_scenario(tmp_path, 'blocked')
    service = WorkflowService(tmp_path / 'workflow.sqlite3')
    record = service.assess(data, client, DEMO_DATE)
    assert record['model']['overall_status'] == 'Ready'
    assert record['result']['overall_status'] == 'Not Ready'
    restored = WorkflowService(service.db_path).get(record['id'])
    assert restored['inference']['backend'] == 'openai'
    assert restored['inference']['model'] == 'test-model'
    assert 'test-private-key' not in str(restored)


def test_missing_key_and_invalid_backend_never_fall_back(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(ValueError, match='not configured'):
        get_llm_client('openai')
    with pytest.raises(ValueError, match='Unsupported'):
        get_llm_client('typo')


def test_factory_selects_openai(adapter):
    client, captured = adapter
    selected = get_llm_client('openai', api_key='test-private-key', model='selected-model')
    assert isinstance(selected, OpenAIClient)
    assert selected.model == 'selected-model'
