from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.workflow.service import WorkflowService
from app.workflow.delivery import DeliveryService, LocalTaskInbox

APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'


@pytest.fixture
def ui(tmp_path, monkeypatch):
    monkeypatch.setenv('READINESS_DEMO_DIR', str(tmp_path))
    monkeypatch.setenv('READINESS_UI_BACKEND', 'mock')
    return AppTest.from_file(str(APP), default_timeout=15).run(), tmp_path


def click(at, label):
    next(button for button in at.button if button.label == label).click().run()
    assert not at.exception


def assess(at, scenario):
    at.selectbox(key='scenario').select(scenario).run()
    click(at, 'Run assessment')


def approve(at):
    at.text_input(key='reviewer').input('Demo reviewer')
    at.text_area(key='review_reason').input('Verified findings and agreed follow-up.')
    click(at, 'Approve assessment')


def test_ready_ui_review_delivery_and_restart(ui):
    at, root = ui
    assert not at.exception
    assess(at, 'ready')
    assert at.metric[0].value == 'Ready'
    approve(at)
    click(at, 'Queue follow-up task')
    click(at, 'Deliver task')
    assert len(LocalTaskInbox(root / 'ready' / 'inbox.sqlite3').tasks()) == 1
    fresh = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not fresh.exception
    assert fresh.metric[0].value == 'Ready'
    record = WorkflowService(root / 'ready' / 'workflow.sqlite3').history()[0]
    assert record['review']['reviewer'] == 'Demo reviewer'
    assert DeliveryService(WorkflowService(root / 'ready' / 'workflow.sqlite3')).history()[0]['state'] == 'delivered'


@pytest.mark.parametrize('scenario,status', [('blocked', 'Not Ready'), ('model_failure', 'Unknown'), ('contradiction', 'Not Ready')])
def test_ui_disables_approval_for_blocked_or_failed_assessments(ui, scenario, status):
    at, root = ui
    assess(at, scenario)
    assert at.metric[0].value == status
    assert next(button for button in at.button if button.label == 'Approve assessment').disabled
    assert at.button(key='queue').disabled
    at.text_input(key='reviewer').input('Reviewer')
    at.text_area(key='review_reason').input('Resolve the findings.')
    click(at, 'Reject assessment')
    assert WorkflowService(root / scenario / 'workflow.sqlite3').history()[0]['review']['decision'] == 'reject'


@pytest.mark.parametrize('scenario', ['incomplete', 'stale'])
def test_ui_shows_quality_gaps_despite_full_source_presence(ui, scenario):
    at, root = ui
    assess(at, scenario)
    assert at.metric[0].value == 'At Risk'
    assert at.metric[2].value == '1'
    assert at.metric[3].value == 'Medium'
    assert at.warning
    record = WorkflowService(root / scenario / 'workflow.sqlite3').history()[0]
    assert record['context']['data_completeness_score'] == 1
    assert record['result']['human_review_required']
    assert 'Data quality requires review' in record['result']['executive_summary']


def test_ui_requires_review_reason(ui):
    at, root = ui
    assess(at, 'ready')
    at.text_input(key='reviewer').input('Reviewer')
    click(at, 'Approve assessment')
    assert at.error[0].value == 'Reviewer and reason are required.'
    assert WorkflowService(root / 'ready' / 'workflow.sqlite3').history()[0]['review'] is None


def test_ui_lost_response_retry_leaves_one_task(ui):
    at, root = ui
    assess(at, 'delivery_failure')
    approve(at)
    click(at, 'Queue follow-up task')
    click(at, 'Deliver task')
    workflow = WorkflowService(root / 'delivery_failure' / 'workflow.sqlite3')
    assert DeliveryService(workflow).history()[0]['state'] == 'failed'
    assert len(LocalTaskInbox(root / 'delivery_failure' / 'inbox.sqlite3').tasks()) == 1
    click(at, 'Retry delivery')
    delivery = DeliveryService(workflow).history()[0]
    assert delivery['state'] == 'delivered'
    assert len(delivery['attempts']) == 2
    assert len(LocalTaskInbox(root / 'delivery_failure' / 'inbox.sqlite3').tasks()) == 1


def test_ui_source_update_invalidates_review_and_stops_pending_delivery(ui):
    at, root = ui
    assess(at, 'ready')
    approve(at)
    click(at, 'Queue follow-up task')
    click(at, 'Simulate a source update')
    assert at.warning
    assert at.button(key='queue').disabled
    click(at, 'Deliver task')
    workflow = WorkflowService(root / 'ready' / 'workflow.sqlite3')
    assert DeliveryService(workflow).history()[0]['state'] == 'cancelled'
    assert LocalTaskInbox(root / 'ready' / 'inbox.sqlite3').tasks() == []
    click(at, 'Run assessment')
    assert len(workflow.history()) == 2


def test_scenario_switch_keeps_histories_separate(ui):
    at, root = ui
    assess(at, 'ready')
    at.selectbox(key='scenario').select('blocked').run()
    assert not at.exception
    assert not at.metric
    assess(at, 'blocked')
    at.selectbox(key='scenario').select('ready').run()
    assert at.metric[0].value == 'Ready'


def test_live_ui_requires_key_without_mock_fallback(ui, monkeypatch):
    at, root = ui
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    at.selectbox(key='inference_backend').select('openai').run()
    assert not at.exception
    assert at.button(key='assess').disabled
    assert any('Configure OPENAI_API_KEY' in warning.value for warning in at.warning)
    assert WorkflowService(root / 'live-openai' / 'ready' / 'workflow.sqlite3').history() == []
    at.selectbox(key='scenario').select('model_failure').run()
    assert not at.button(key='assess').disabled
    click(at, 'Run assessment')
    assert at.metric[0].value == 'Unknown'
    assert WorkflowService(root / 'model_failure' / 'workflow.sqlite3').history()[0]['inference']['mode'] == 'simulated'


def test_live_ui_uses_provider_and_separates_saved_history(ui, monkeypatch):
    import json
    from types import SimpleNamespace
    import openai
    at, root = ui
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key-not-for-network')
    called = []
    def create(**kwargs):
        called.append(kwargs)
        payload = {'overall_status': 'Ready', 'executive_summary': 'Live adapter test response.',
                   'recommended_actions': [], 'confidence': 'High',
                   'human_review_required': False, 'human_review_reason': None}
        return SimpleNamespace(id='resp_ui', status='completed', output=[], usage=None,
                               output_text=json.dumps(payload))
    monkeypatch.setattr(openai, 'OpenAI', lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(create=create)))
    assess(at, 'ready')  # Save a mock assessment first.
    at.selectbox(key='inference_backend').select('openai').run()
    assert not at.metric  # The existing mock result cannot appear as a live result.
    click(at, 'Run assessment')
    assert len(called) == 1
    record = WorkflowService(root / 'live-openai' / 'ready' / 'workflow.sqlite3').history()[0]
    assert record['inference']['mode'] == 'live'
    assert record['inference']['response_id'] == 'resp_ui'
    assert 'test-key-not-for-network' not in str(record)
    assert len(WorkflowService(root / 'ready' / 'workflow.sqlite3').history()) == 1
