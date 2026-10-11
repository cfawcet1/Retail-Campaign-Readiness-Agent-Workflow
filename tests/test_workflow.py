import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
import pytest
from app.analyzers.data_quality_analyzer import SOURCES
from app.llms.mock_client import MockLLMClient
from app.workflow.service import WorkflowService, WorkflowError

DAY = date(2026, 8, 8)


@pytest.fixture
def setup(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    for source in SOURCES:
        shutil.copy(Path('data') / source, data / source)
    return tmp_path / 'workflow.sqlite3', data


def ready(data):
    catalog = json.loads((data / 'product_catalog.json').read_text())
    lines = ['sku,product_name,color,size,units_available,expected_demand,replenishment_on_order']
    for p in catalog['products']:
        p.update(status='active', care_instructions='Wash cold', pdp_ready=True)
        for i, color in enumerate(p['colors']):
            for size in p['sizes']:
                lines.append(f"{p['sku_base']}-C{i}-{size},{p['name']},{color},{size},100,100,false")
    (data / 'product_catalog.json').write_text(json.dumps(catalog))
    (data / 'inventory.csv').write_text('\n'.join(lines))
    checklist = json.loads((data / 'campaign_checklist.json').read_text())
    for task in checklist['campaign_checklist']: task['status'] = 'complete'
    (data / 'campaign_checklist.json').write_text(json.dumps(checklist))
    (data / 'launch_notes.md').write_text('All systems go.')
    (data / 'customer_feedback.md').write_text('**Product:** Dress\n**Rating:** 5/5\nPerfect fit.')
    (data / 'source_metadata.json').write_text(json.dumps({s: {'updated_at': DAY.isoformat(), 'max_age_days': 7} for s in SOURCES}))


def test_persistence_and_approval_survive_restart(setup):
    db, data = setup
    ready(data)
    service = WorkflowService(db)
    saved = service.assess(data, MockLLMClient(), DAY)
    assert saved['result']['overall_status'] == 'Ready'
    assert saved['review_state'] == 'pending_review'
    reviewed = service.review(saved['id'], data, 'Demo reviewer', 'approve', 'Verified source findings.', DAY)
    assert reviewed['review_state'] == 'approved'
    restarted = WorkflowService(db).get(saved['id'], data, DAY)
    assert restarted['review'] == reviewed['review']
    assert restarted['context'] == saved['context']
    assert restarted['model'] == saved['model']
    assert len(WorkflowService(db).history(data, DAY)) == 1


def test_blockers_cannot_be_approved_but_can_be_rejected(setup):
    db, data = setup
    service = WorkflowService(db)
    saved = service.assess(data, MockLLMClient(), DAY)
    with pytest.raises(WorkflowError, match='Cannot approve'):
        service.review(saved['id'], data, 'Reviewer', 'approve', 'Override', DAY)
    assert service.review(saved['id'], data, 'Reviewer', 'reject', 'Resolve blockers.', DAY)['review_state'] == 'rejected'


def test_invalid_model_cannot_be_approved(setup):
    db, data = setup
    ready(data)
    class InvalidClient:
        def generate(self, context): return []
    service = WorkflowService(db)
    saved = service.assess(data, InvalidClient(), DAY)
    assert saved['result']['overall_status'] == 'Unknown'
    with pytest.raises(WorkflowError, match='Cannot approve'):
        service.review(saved['id'], data, 'Reviewer', 'approve', 'Go', DAY)


@pytest.mark.parametrize('change', ['source', 'metadata', 'date'])
def test_changed_snapshot_requires_reassessment(setup, change):
    db, data = setup
    ready(data)
    service = WorkflowService(db)
    saved = service.assess(data, MockLLMClient(), DAY)
    day = DAY
    if change == 'date': day += timedelta(days=1)
    elif change == 'metadata': (data / 'source_metadata.json').unlink()
    else: (data / 'launch_notes.md').write_text('Updated source.')
    assert service.get(saved['id'], data, day)['review_state'] == 'reassessment_required'
    with pytest.raises(WorkflowError, match='reassessment required'):
        service.review(saved['id'], data, 'Reviewer', 'approve', 'Go', day)


def test_previous_approval_retained_but_no_longer_current(setup):
    db, data = setup
    ready(data)
    service = WorkflowService(db)
    saved = service.assess(data, MockLLMClient(), DAY)
    service.review(saved['id'], data, 'Reviewer', 'approve', 'Go', DAY)
    (data / 'launch_notes.md').write_text('New source information.')
    record = service.get(saved['id'], data, DAY)
    assert record['review']['decision'] == 'approve'
    assert record['review_state'] == 'reassessment_required'
    assert record['snapshot_current'] is False


def test_source_change_during_inference_is_not_saved(setup):
    db, data = setup
    class ChangingClient:
        def generate(self, context):
            (data / 'launch_notes.md').write_text('Changed during inference.')
            return MockLLMClient().generate(context)
    service = WorkflowService(db)
    with pytest.raises(WorkflowError, match='during assessment'):
        service.assess(data, ChangingClient(), DAY)
    assert service.history() == []


def test_competing_reviews_only_record_one_decision(setup):
    db, data = setup
    ready(data)
    service = WorkflowService(db)
    saved = service.assess(data, MockLLMClient(), DAY)
    def review(decision):
        try:
            WorkflowService(db).review(saved['id'], data, 'Reviewer', decision, 'Reviewed.', DAY)
            return 'recorded'
        except WorkflowError: return 'refused'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(review, ['approve', 'reject'])) == ['recorded', 'refused']


@pytest.mark.parametrize('reviewer,decision,reason', [('', 'approve', 'Go'), ('R', 'approve', ''), ('R', 'other', 'Go')])
def test_review_requires_attribution_and_reason(setup, reviewer, decision, reason):
    db, data = setup
    service = WorkflowService(db)
    saved = service.assess(data, MockLLMClient(), DAY)
    with pytest.raises(WorkflowError):
        service.review(saved['id'], data, reviewer, decision, reason, DAY)
    assert service.get(saved['id'])['review'] is None
