from datetime import date
import pytest
from app.ontology.models import (
    LaunchReadinessContext, LaunchSignal, ConflictRecord, Domain, Severity,
    SignalType, ResolutionStatus,
)
from app.policy.readiness import evaluate_readiness, enforce_readiness
from app.llms.mock_client import MockLLMClient


def context(score=1.0, signals=None, conflicts=None):
    return LaunchReadinessContext('Test launch', date(2026, 8, 22), signals or [], conflicts or [], score)


def signal(severity=Severity.BLOCKER, domain=Domain.INVENTORY, interpretation=False):
    return LaunchSignal('S1', domain, severity, SignalType.THRESHOLD_BREACH, 'Risk', 'Risk evidence', [], interpretation)


def response(**overrides):
    return dict(overall_status='Ready', confidence='High', human_review_required=False,
                human_review_reason=None, executive_summary='Model explanation', recommended_actions=[], **overrides)


def test_model_cannot_override_blocker_or_required_review():
    result = enforce_readiness(context(signals=[signal()]), response())
    assert result['overall_status'] == 'Not Ready'
    assert result['human_review_required'] is True
    assert 'blockers' in result['human_review_reason']


@pytest.mark.parametrize('resolution', [ResolutionStatus.UNRESOLVED, ResolutionStatus.NEEDS_HUMAN_REVIEW])
def test_pending_conflict_prevents_ready(resolution):
    c = context(conflicts=[ConflictRecord('status', 'a', 'active', 'b', 'draft', resolution)])
    assert enforce_readiness(c, response())['overall_status'] == 'At Risk'
    assert MockLLMClient().generate(c)['human_review_required'] is True


def test_resolved_conflict_does_not_block_ready():
    c = context(conflicts=[ConflictRecord('status', 'a', 'active', 'b', 'draft', ResolutionStatus.RESOLVED)])
    assert evaluate_readiness(c).overall_status == 'Ready'
    assert not evaluate_readiness(c).human_review_required
    assert MockLLMClient().generate(c)["human_review_required"] is False


@pytest.mark.parametrize('score,status,confidence,review', [
    (1.0, 'Ready', 'High', False), (0.8, 'Ready', 'High', False),
    (0.79, 'At Risk', 'Medium', False), (0.6, 'At Risk', 'Medium', False),
    (0.59, 'At Risk', 'Medium', True), (0.49, 'At Risk', 'Low', True),
    (0.0, 'At Risk', 'Low', True),
])
def test_completeness_boundaries(score, status, confidence, review):
    result = enforce_readiness(context(score), response())
    assert (result['overall_status'], result['confidence'], result['human_review_required']) == (status, confidence, review)
    mock = MockLLMClient().generate(context(score))
    assert mock['overall_status'] == status
    assert mock['human_review_required'] == review


def test_quality_feedback_requires_review():
    c = context(signals=[signal(Severity.MEDIUM, Domain.FEEDBACK, True)])
    decision = evaluate_readiness(c)
    assert decision.overall_status == 'At Risk'
    assert decision.human_review_required


def test_preserves_stricter_model_assessment_and_explanation():
    model = response()
    model.update(overall_status='Not Ready', confidence='Low', human_review_required=True,
                 human_review_reason='Needs specialist review')
    result = enforce_readiness(context(), model)
    assert result['overall_status'] == 'Not Ready'
    assert result['confidence'] == 'Low'
    assert result['human_review_required']
    assert result['executive_summary'] == model['executive_summary']
    assert result['recommended_actions'] == model['recommended_actions']


def test_unavailable_model_stays_unknown_and_requires_review():
    model = response()
    model.update(overall_status='Unknown', confidence='Low', human_review_required=True)
    result = enforce_readiness(context(), model)
    assert result['overall_status'] == 'Unknown'
    assert result['human_review_required']
    assert enforce_readiness(context(signals=[signal()]), model)['overall_status'] == 'Not Ready'


@pytest.mark.parametrize('score', [-0.1, 1.1, float('nan'), float('inf'), 'complete', True])
def test_invalid_completeness_is_rejected(score):
    with pytest.raises(ValueError, match='data_completeness_score'):
        evaluate_readiness(context(score))
