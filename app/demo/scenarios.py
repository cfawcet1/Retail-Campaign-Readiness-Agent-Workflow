"""Synthetic source snapshots consumed by the real assessment workflow."""
import csv
import json
from datetime import date
from pathlib import Path

from app.analyzers.data_quality_analyzer import SOURCES
from app.llms.mock_client import MockLLMClient

DEMO_DATE = date(2026, 8, 8)
SCENARIOS = {
    'ready': ('Ready launch', 'Complete assortment, sufficient stock, current sources, and finished campaign tasks.'),
    'blocked': ('Blocked launch', 'The large variant has insufficient stock and no replenishment. Approval must be refused.'),
    'incomplete': ('Incomplete data', 'The large variant is missing from inventory. Source presence alone cannot prove coverage.'),
    'stale': ('Stale inventory', 'Stock coverage looks sufficient, but the inventory snapshot is too old to trust without review.'),
    'model_failure': ('Model failure', 'The simulated model returns malformed output. Review is required and approval is unavailable.'),
    'contradiction': ('Model contradicts a blocker', 'The simulated model says Ready despite low inventory. Python preserves Not Ready.'),
    'delivery_failure': ('Delivery response lost', 'The task is accepted, then the response is lost. Retry recovers without creating a duplicate.'),
}


def prepare_scenario(root, scenario):
    if scenario not in SCENARIOS:
        raise ValueError('Unknown demo scenario.')
    directory = Path(root) / scenario / 'data'
    marker = directory / '.initialized'
    if marker.exists():
        return directory
    directory.mkdir(parents=True, exist_ok=True)
    catalog = {
        'launch': 'Soft Lounge campaign', 'launch_date': '2026-08-22',
        'products': [{
            'sku_base': 'DEMO-100', 'name': 'Soft Lounge Tee', 'status': 'active',
            'description': 'A soft cotton tee.', 'care_instructions': 'Machine wash cold.',
            'pdp_ready': True, 'colors': ['onyx'], 'sizes': ['S', 'L'],
        }],
    }
    (directory / 'product_catalog.json').write_text(json.dumps(catalog, indent=2))
    with (directory / 'inventory.csv').open('w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['sku', 'product_name', 'color', 'size', 'units_available', 'expected_demand', 'replenishment_on_order'])
        writer.writerow(['DEMO-100-ONX-S', 'Soft Lounge Tee', 'onyx', 'S', 200, 100, 'false'])
        if scenario != 'incomplete':
            stock = 10 if scenario in ('blocked', 'contradiction') else 200
            writer.writerow(['DEMO-100-ONX-L', 'Soft Lounge Tee', 'onyx', 'L', stock, 100, 'false'])
    (directory / 'campaign_checklist.json').write_text(json.dumps({'campaign_checklist': [{
        'id': 'DEMO-EMAIL', 'category': 'email', 'item': 'Campaign email scheduled',
        'owner': 'CRM', 'required': True, 'status': 'complete',
    }]}, indent=2))
    (directory / 'customer_feedback.md').write_text('**Product:** Soft Lounge Tee\n**Rating:** 5/5\nComfortable fabric and a perfect fit.\n')
    (directory / 'launch_notes.md').write_text('Campaign creative approved. Product pages published.\n')
    metadata = {source: {'updated_at': DEMO_DATE.isoformat(), 'max_age_days': 7} for source in SOURCES}
    if scenario == 'stale':
        metadata['inventory.csv']['updated_at'] = '2026-07-01'
    (directory / 'source_metadata.json').write_text(json.dumps(metadata, indent=2))
    marker.write_text('scenario-v1\n')
    return directory


class DemoModel(MockLLMClient):
    def __init__(self, scenario):
        self.scenario = scenario

    def generate(self, context):
        if self.scenario == 'model_failure':
            return {'overall_status': 'Ready'}  # Deliberately violates the response contract.
        result = super().generate(context)
        if self.scenario == 'contradiction':
            result.update(overall_status='Ready', confidence='High',
                          executive_summary='The simulated model claims the campaign is ready.',
                          human_review_required=False, human_review_reason=None)
        return result


class LostDeliveryResponse:
    """Accept downstream, then fail: retry must use the receiver's existing key."""
    def __init__(self, inbox):
        self.inbox = inbox

    def create_task(self, key, payload):
        self.inbox.create_task(key, payload)
        raise TimeoutError('Simulated response loss after task acceptance.')


def change_sources(directory):
    """Append an explicit source change to demonstrate invalidation."""
    with (Path(directory) / 'launch_notes.md').open('a') as file:
        file.write('Campaign owner updated the source notes; reassessment is required.\n')
