"""Coverage and freshness are separate from source-presence completeness."""
import json
from pathlib import Path
from datetime import date
from app.ontology.models import LaunchSignal, EvidenceRecord, Domain, Severity, SignalType
from app.validation.inputs import require, iso_date, InputValidationError

SOURCES = ('product_catalog.json', 'inventory.csv', 'customer_feedback.md', 'campaign_checklist.json', 'launch_notes.md')


def finding(identifier, source, field, description, raw=None):
    return LaunchSignal(identifier, Domain.OPERATIONAL, Severity.HIGH, SignalType.MISSING_DATA,
                        'Data quality requires review', description,
                        [EvidenceRecord(source, field, raw, description)])


def analyze_data_quality(catalog, inventory, data_dir, as_of=None):
    as_of = as_of or date.today()
    signals = []
    for product in catalog['products']:
        base = product['sku_base']
        expected = {(color, size) for color in product['colors'] for size in product['sizes']}
        actual = {(r['color'], r['size']) for r in inventory if r['sku'].startswith(base + '-')}
        missing = sorted(expected - actual)
        if missing:
            signals.append(finding(f'DQ-COVERAGE-{base}', 'inventory.csv', base,
                                   f'{base}: {len(missing)} of {len(expected)} catalog-declared color/size combinations have no inventory record. Missing records are not treated as zero stock.', missing))
    for row in inventory:
        matches = [p for p in catalog['products'] if row['sku'].startswith(p['sku_base'] + '-')]
        if len(matches) != 1 or row['color'] not in matches[0]['colors'] or row['size'] not in matches[0]['sizes']:
            signals.append(finding(f"DQ-UNMATCHED-{row['sku']}", 'inventory.csv', row['sku'],
                                   f"{row['sku']}: inventory variant does not uniquely match a catalog-declared variant."))
    path = Path(data_dir) / 'source_metadata.json'
    metadata = {}
    if path.exists():
        try:
            metadata = json.loads(path.read_text())
        except (ValueError, OSError) as exc:
            raise InputValidationError('source_metadata.json: unable to read valid JSON') from exc
        require(isinstance(metadata, dict), 'source_metadata.json', 'expected an object keyed by source filename')
        require(set(metadata).issubset(SOURCES), 'source_metadata.json', 'unknown source filename')
    for source in SOURCES:
        entry = metadata.get(source)
        if entry is None:
            signals.append(finding('DQ-FRESHNESS-UNKNOWN-' + source, source, 'updated_at',
                                   f'{source}: freshness unknown; no explicit source metadata provided.'))
            continue
        require(isinstance(entry, dict), f'source_metadata.json.{source}', 'expected an object')
        updated = iso_date(entry.get('updated_at'), f'source_metadata.json.{source}.updated_at')
        max_age = entry.get('max_age_days')
        require(type(max_age) is int and max_age >= 0, f'source_metadata.json.{source}.max_age_days', 'required nonnegative integer')
        age = (as_of - updated).days
        if age < 0:
            signals.append(finding('DQ-FUTURE-' + source, source, 'updated_at', f'{source}: source timestamp is after assessment date {as_of}.', updated.isoformat()))
        elif age > max_age:
            signals.append(finding('DQ-STALE-' + source, source, 'updated_at', f'{source}: {age} days old at {as_of}; freshness limit is {max_age} days.', updated.isoformat()))
    return signals
