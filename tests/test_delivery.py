from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from test_workflow import setup, ready, DAY
from app.llms.mock_client import MockLLMClient
from app.workflow.service import WorkflowService, WorkflowError
from app.workflow.delivery import DeliveryService, LocalTaskInbox


def approved(db, data):
    ready(data)
    workflow = WorkflowService(db)
    record = workflow.assess(data, MockLLMClient(), DAY)
    workflow.review(record['id'], data, 'Demo reviewer', 'approve', 'Follow-up agreed.', DAY)
    return workflow, record['id']


@pytest.mark.parametrize('decision', [None, 'reject'])
def test_unapproved_cannot_enqueue(setup, decision):
    db, data = setup
    ready(data)
    workflow = WorkflowService(db)
    record = workflow.assess(data, MockLLMClient(), DAY)
    if decision:
        workflow.review(record['id'], data, 'R', decision, 'Hold.', DAY)
    deliveries = DeliveryService(workflow)
    with pytest.raises(WorkflowError, match='current approved'):
        deliveries.enqueue(record['id'], data, DAY)
    assert deliveries.history() == []


def test_enqueue_and_dispatch_are_idempotent_across_restart(setup, tmp_path):
    db, data = setup
    workflow, identifier = approved(db, data)
    delivery = DeliveryService(workflow).enqueue(identifier, data, DAY)
    restarted = DeliveryService(WorkflowService(db))
    assert restarted.enqueue(identifier, data, DAY)['id'] == delivery['id']
    inbox = LocalTaskInbox(tmp_path / 'inbox.sqlite3')
    sent = restarted.dispatch(delivery['id'], data, inbox, DAY)
    assert sent['state'] == 'delivered'
    assert restarted.dispatch(delivery['id'], data, inbox, DAY) == sent
    tasks = LocalTaskInbox(inbox.db_path).tasks()
    assert len(tasks) == 1
    assert tasks[0]['payload']['review']['reviewer'] == 'Demo reviewer'
    assert tasks[0]['payload']['readiness_status'] == 'Ready'
    assert len(sent['attempts']) == 1


def test_timeout_after_acceptance_retry_creates_one_task(setup, tmp_path):
    db, data = setup
    workflow, identifier = approved(db, data)
    deliveries = DeliveryService(workflow)
    delivery = deliveries.enqueue(identifier, data, DAY)
    inbox = LocalTaskInbox(tmp_path / 'inbox.sqlite3')
    class LostResponse:
        def create_task(self, key, payload):
            inbox.create_task(key, payload)
            raise TimeoutError('secret must not appear in audit')
    failed = deliveries.dispatch(delivery['id'], data, LostResponse(), DAY)
    assert failed['state'] == 'failed'
    assert failed['attempts'][0]['error_type'] == 'TimeoutError'
    assert 'secret' not in str(failed)
    restarted = DeliveryService(WorkflowService(db))
    sent = restarted.dispatch(delivery['id'], data, inbox, DAY)
    assert sent['state'] == 'delivered'
    assert len(sent['attempts']) == 2
    assert len(inbox.tasks()) == 1


@pytest.mark.parametrize('change', ['source', 'date'])
def test_stale_pending_delivery_is_cancelled(setup, tmp_path, change):
    db, data = setup
    workflow, identifier = approved(db, data)
    deliveries = DeliveryService(workflow)
    delivery = deliveries.enqueue(identifier, data, DAY)
    day = DAY
    if change == 'source':
        (data / 'launch_notes.md').write_text('Changed source.')
    else:
        day += timedelta(days=1)
    inbox = LocalTaskInbox(tmp_path / 'inbox.sqlite3')
    cancelled = deliveries.dispatch(delivery['id'], data, inbox, day)
    assert cancelled['state'] == 'cancelled'
    assert inbox.tasks() == []
    with pytest.raises(WorkflowError):
        deliveries.enqueue(identifier, data, day)


def test_competing_workers_only_send_once(setup, tmp_path):
    db, data = setup
    workflow, identifier = approved(db, data)
    delivery = DeliveryService(workflow).enqueue(identifier, data, DAY)
    inbox = LocalTaskInbox(tmp_path / 'inbox.sqlite3')
    def send(_):
        return DeliveryService(WorkflowService(db)).dispatch(delivery['id'], data, inbox, DAY)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(r['state'] == 'delivered' for r in pool.map(send, range(2)))
    assert len(inbox.tasks()) == 1
    assert len(DeliveryService(workflow).get(delivery['id'])['attempts']) == 1


def test_receiver_rejects_key_reuse_with_changed_payload(tmp_path):
    inbox = LocalTaskInbox(tmp_path / 'inbox.sqlite3')
    inbox.create_task('same', {'value': 1})
    with pytest.raises(WorkflowError, match='different payload'):
        inbox.create_task('same', {'value': 2})
    assert inbox.tasks()[0]['payload'] == {'value': 1}


def test_invalid_receipt_is_retryable(setup):
    db, data = setup
    workflow, identifier = approved(db, data)
    deliveries = DeliveryService(workflow)
    delivery = deliveries.enqueue(identifier, data, DAY)
    class InvalidReceipt:
        def create_task(self, key, payload): return None
    failed = deliveries.dispatch(delivery['id'], data, InvalidReceipt(), DAY)
    assert failed['state'] == 'failed'
    assert failed['receipt'] is None


def test_process_interruption_after_acceptance_is_recoverable(setup, tmp_path):
    db, data = setup
    workflow, identifier = approved(db, data)
    deliveries = DeliveryService(workflow)
    delivery = deliveries.enqueue(identifier, data, DAY)
    inbox = LocalTaskInbox(tmp_path / 'inbox.sqlite3')
    class Interrupted:
        def create_task(self, key, payload):
            inbox.create_task(key, payload)
            raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        deliveries.dispatch(delivery['id'], data, Interrupted(), DAY)
    restarted = DeliveryService(WorkflowService(db))
    assert restarted.get(delivery['id'])['state'] == 'pending'
    assert restarted.dispatch(delivery['id'], data, inbox, DAY)['state'] == 'delivered'
    assert len(inbox.tasks()) == 1


def test_at_risk_task_preserves_readiness_status(setup, tmp_path):
    db, data = setup
    ready(data)
    (data / 'source_metadata.json').unlink()  # Unknown freshness requires review.
    workflow = WorkflowService(db)
    record = workflow.assess(data, MockLLMClient(), DAY)
    assert record['result']['overall_status'] == 'At Risk'
    workflow.review(record['id'], data, 'Reviewer', 'approve', 'Follow up on freshness.', DAY)
    deliveries = DeliveryService(workflow)
    delivery = deliveries.enqueue(record['id'], data, DAY)
    inbox = LocalTaskInbox(tmp_path / 'inbox.sqlite3')
    deliveries.dispatch(delivery['id'], data, inbox, DAY)
    assert inbox.tasks()[0]['payload']['readiness_status'] == 'At Risk'
    assert workflow.get(record['id'])['result']['overall_status'] == 'At Risk'
