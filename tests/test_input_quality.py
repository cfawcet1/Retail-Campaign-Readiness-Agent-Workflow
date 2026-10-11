import json
import shutil
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pytest
from app.orchestrator.pipeline import run_pipeline
from app.validation.inputs import InputValidationError
from app.analyzers.data_quality_analyzer import analyze_data_quality, SOURCES
from app.policy.readiness import evaluate_readiness
from app.loaders.inventory_loader import load_inventory
from app.loaders.feedback_loader import load_feedback


@pytest.fixture
def inputs(tmp_path):
    for source in SOURCES:
        shutil.copy(Path('data') / source, tmp_path / source)
    return tmp_path


@pytest.mark.parametrize('mutation', ['date', 'missing_date', 'products', 'duplicate', 'boolean', 'colors'])
def test_invalid_catalog_stops_before_analysis(inputs, mutation):
    path = inputs / 'product_catalog.json'
    catalog = json.loads(path.read_text())
    if mutation == 'date': catalog['launch_date'] = '2026-02-30'
    elif mutation == 'missing_date': del catalog['launch_date']
    elif mutation == 'products': catalog['products'] = {}
    elif mutation == 'duplicate': catalog['products'].append(catalog['products'][0])
    elif mutation == 'boolean': catalog['products'][0]['pdp_ready'] = 'false'
    else: catalog['products'][0]['colors'] = 'onyx'
    path.write_text(json.dumps(catalog))
    with patch('app.orchestrator.pipeline.analyze_catalog') as analyzer:
        with pytest.raises(InputValidationError, match='product_catalog.json'):
            run_pipeline(str(inputs))
        analyzer.assert_not_called()


@pytest.mark.parametrize('source', SOURCES)
def test_missing_source_is_explicit_failure(inputs, source):
    (inputs / source).unlink()
    with pytest.raises(InputValidationError, match=source):
        run_pipeline(str(inputs))


def test_blank_business_field_is_a_finding(inputs):
    path = inputs / 'product_catalog.json'
    catalog = json.loads(path.read_text())
    catalog['products'][0]['care_instructions'] = ' '
    path.write_text(json.dumps(catalog))
    result = run_pipeline(str(inputs))
    assert any(s.signal_id == 'CAT-MISSING-SL-201-CARE_INSTRUCTIONS' for s in result.signals)


@pytest.mark.parametrize('value', ['-1', 'many'])
def test_invalid_inventory_quantity(inputs, value):
    path = inputs / 'inventory.csv'
    path.write_text(path.read_text().replace('320,300,false', f'{value},300,false', 1))
    with pytest.raises(InputValidationError, match='inventory.csv'):
        run_pipeline(str(inputs))


def test_invalid_csv_boolean_rejected(inputs):
    path = inputs / 'inventory.csv'
    path.write_text(path.read_text().replace('false', 'maybe', 1))
    with pytest.raises(InputValidationError): load_inventory(str(path))


def test_malformed_review_not_silently_dropped(inputs):
    path = inputs / 'customer_feedback.md'
    path.write_text('**Product:** Dress\n**Rating:** 6/5\nA review.')
    with pytest.raises(InputValidationError): load_feedback(str(path))


def quality(tmp_path, updated='2026-08-01', as_of=date(2026, 8, 8)):
    (tmp_path / 'source_metadata.json').write_text(json.dumps({
        source: {'updated_at': updated, 'max_age_days': 7} for source in SOURCES
    }))
    catalog = {'products': [{'sku_base': 'SL-1', 'colors': ['onyx'], 'sizes': ['S', 'M']}]}
    inventory = [{'sku': 'SL-1-ONX-S', 'color': 'onyx', 'size': 'S'}]
    return analyze_data_quality(catalog, inventory, str(tmp_path), as_of)


def test_coverage_records_missing_variants(tmp_path):
    signals = quality(tmp_path)
    assert len(signals) == 1
    assert signals[0].evidence[0].raw_value == [('onyx', 'M')]


def test_freshness_boundary_and_stale(tmp_path):
    assert not any('STALE' in s.signal_id for s in quality(tmp_path))
    assert len([s for s in quality(tmp_path, as_of=date(2026, 8, 9)) if 'STALE' in s.signal_id]) == 5


def test_future_timestamps_require_review(tmp_path):
    assert len([s for s in quality(tmp_path, updated='2026-08-09') if 'FUTURE' in s.signal_id]) == 5


def test_source_presence_does_not_hide_quality_gaps(inputs):
    c = run_pipeline(str(inputs), as_of=date(2026, 8, 8))
    assert c.data_completeness_score == 1.0
    assert sum('FRESHNESS-UNKNOWN' in s.signal_id for s in c.signals) == 5
    decision = evaluate_readiness(c)
    assert decision.confidence == 'Medium'
    assert decision.human_review_required


def test_invalid_metadata_is_explicit(inputs):
    (inputs / 'source_metadata.json').write_text('{bad json')
    with pytest.raises(InputValidationError, match='source_metadata.json'):
        run_pipeline(str(inputs))


def test_cli_stops_before_model_on_bad_input(inputs):
    import sys
    from app.main import main
    (inputs / 'product_catalog.json').write_text('{}')
    with patch.object(sys, 'argv', ['app', '--data-dir', str(inputs)]), patch('app.main.get_llm_client') as client:
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        client.assert_not_called()
