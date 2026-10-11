from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.ontology.models import LaunchReadinessContext, LaunchSignal, Domain, Severity, SignalType, ConflictRecord
from app.validation.assessment import validate_assessment, AssessmentValidationError
from app.policy.readiness import enforce_readiness
from app.llms.mock_client import MockLLMClient
from app.llms.anthropic_client import AnthropicClient
from app.report.formatter import format_report


def context():
    return LaunchReadinessContext('Test', date(2026, 8, 22), [
        LaunchSignal('INV-1', Domain.INVENTORY, Severity.BLOCKER, SignalType.THRESHOLD_BREACH, 'Low inventory', 'Low inventory', [])
    ], [ConflictRecord('product_status', 'catalog', 'active', 'notes', 'draft')], 1.0)


def valid():
    return {'overall_status': 'Not Ready', 'executive_summary': 'Inventory requires attention.',
            'recommended_actions': [{'action': 'Review inventory.', 'signal_ids': ['INV-1'], 'conflict_fields': []}],
            'confidence': 'High', 'human_review_required': True, 'human_review_reason': 'Known blocker.'}


@pytest.mark.parametrize('bad', [None, [], 'text', 5])
def test_non_object_rejected(bad):
    with pytest.raises(AssessmentValidationError):
        validate_assessment(context(), bad)


@pytest.mark.parametrize('field,value', [
    ('overall_status', []), ('overall_status', 'Go'), ('confidence', {}),
    ('executive_summary', ''), ('executive_summary', []), ('human_review_required', 'false'),
    ('human_review_required', 1), ('human_review_reason', None), ('recommended_actions', 'Do it'),
    ('recommended_actions', ['Review INV-1']),
    ('recommended_actions', [{'action': 'Review', 'signal_ids': ['INV-999'], 'conflict_fields': []}]),
    ('recommended_actions', [{'action': 'Review', 'signal_ids': [], 'conflict_fields': ['invented']}]),
    ('recommended_actions', [{'action': 'INV-1 needs attention', 'signal_ids': [], 'conflict_fields': []}]),
    ('recommended_actions', [{'action': 'Review', 'signal_ids': 'INV-1', 'conflict_fields': []}]),
    ('recommended_actions', [{'action': '', 'signal_ids': ['INV-1'], 'conflict_fields': []}]),
    ('recommended_actions', [{'action': 'Review', 'signal_ids': [[]], 'conflict_fields': []}]),
])
def test_invalid_fields_fail_closed(field, value):
    model = valid()
    model[field] = value
    result = enforce_readiness(context(), model)
    assert result['overall_status'] == 'Not Ready'
    assert result['human_review_required'] is True
    assert result['confidence'] == 'Low'
    assert result['recommended_actions'] == []
    assert 'validation failed' in result['human_review_reason']
    assert 'Model assessment unavailable' in format_report(context(), result)


def test_invalid_assessment_without_blocker_is_unknown():
    c = context()
    c.signals = []
    c.conflicts = []
    assert enforce_readiness(c, [])['overall_status'] == 'Unknown'


@pytest.mark.parametrize('change', ['missing', 'extra', 'unknown', 'review_reason'])
def test_exact_contract_and_consistency(change):
    model = valid()
    if change == 'missing':
        del model['confidence']
    elif change == 'extra':
        model['extra'] = True
    elif change == 'unknown':
        model['overall_status'] = 'Unknown'
    else:
        model['human_review_required'] = False
    with pytest.raises(AssessmentValidationError):
        validate_assessment(context(), model)


def test_valid_signal_and_conflict_references_render():
    model = valid()
    model['recommended_actions'][0]['conflict_fields'] = ['product_status']
    before = deepcopy(model)
    result = enforce_readiness(context(), model)
    assert model == before
    assert '[INV-1, product_status] Review inventory.' in format_report(context(), result)
    validate_assessment(context(), MockLLMClient().generate(context()))


@pytest.mark.parametrize('content,stop_reason', [
    ([SimpleNamespace(type='text', text='not JSON')], 'end_turn'),
    ([SimpleNamespace(type='text', text='{"overall_status": "Ready"}')], 'max_tokens'),
    ([], 'end_turn'),
    ([SimpleNamespace(type='tool_use')], 'end_turn'),
    ([SimpleNamespace(type='text', text='[]')], 'end_turn'),
])
def test_provider_failures_produce_reviewable_report(content, stop_reason):
    client = AnthropicClient.__new__(AnthropicClient)
    client.model = 'test-model'
    client.client = Mock()
    client.client.messages.create.return_value = SimpleNamespace(content=content, stop_reason=stop_reason)
    result = enforce_readiness(context(), client.generate(context()))
    assert result['human_review_required']
    assert result['recommended_actions'] == []
    assert result['overall_status'] == 'Not Ready'
    assert 'Model assessment unavailable' in format_report(context(), result)


def test_api_error_does_not_expose_provider_error_in_summary():
    import anthropic
    client = AnthropicClient.__new__(AnthropicClient)
    client.model = 'test-model'
    client.client = Mock()
    client.client.messages.create.side_effect = anthropic.APIError(
        'private provider detail', request=Mock(), body=None,
    )
    result = enforce_readiness(context(), client.generate(context()))
    assert result['human_review_required']
    assert result['recommended_actions'] == []
    assert 'private provider detail' not in format_report(context(), result)
