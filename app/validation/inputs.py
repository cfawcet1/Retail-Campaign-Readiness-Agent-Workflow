"""Input contracts: invalid structure stops assessment; business gaps remain findings."""
from datetime import date


class InputValidationError(ValueError):
    pass


def require(condition, location, message):
    if not condition:
        raise InputValidationError(f"{location}: {message}")


def text(value):
    return isinstance(value, str) and bool(value.strip())


def iso_date(value, location):
    require(isinstance(value, str), location, 'expected an ISO date (YYYY-MM-DD)')
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise InputValidationError(f'{location}: invalid ISO date') from exc
    require(result.isoformat() == value, location, 'expected YYYY-MM-DD')
    return result


def validate_inputs(catalog, inventory, feedback, checklist, notes):
    require(isinstance(catalog, dict), 'product_catalog.json', 'expected an object')
    require(text(catalog.get('launch')), 'product_catalog.json.launch', 'required nonempty text')
    launch_date = iso_date(catalog.get('launch_date'), 'product_catalog.json.launch_date')
    products = catalog.get('products')
    require(isinstance(products, list), 'product_catalog.json.products', 'expected an array')
    seen = set()
    for i, p in enumerate(products):
        loc = f'product_catalog.json.products[{i}]'
        require(isinstance(p, dict), loc, 'expected an object')
        sku = p.get('sku_base')
        require(text(sku), loc + '.sku_base', 'required nonempty text')
        require(sku not in seen, loc + '.sku_base', 'duplicate product identifier')
        seen.add(sku)
        for field in ('name', 'status', 'description', 'care_instructions'):
            require(p.get(field) is None or isinstance(p[field], str), loc + '.' + field, 'expected text or null')
        require(p.get('pdp_ready') is None or type(p['pdp_ready']) is bool, loc + '.pdp_ready', 'expected boolean or null')
        for field in ('colors', 'sizes'):
            values = p.get(field)
            require(isinstance(values, list) and bool(values) and all(text(v) for v in values), loc + '.' + field, 'required nonempty array of text')
            require(len(set(values)) == len(values), loc + '.' + field, 'duplicate values')
    seen = set()
    for i, row in enumerate(inventory):
        loc = f'inventory.csv.row[{i + 2}]'
        require(row['sku'] not in seen, loc + '.sku', 'duplicate variant identifier')
        seen.add(row['sku'])
        for field in ('sku', 'product_name', 'color', 'size'):
            require(text(row[field]), loc + '.' + field, 'required nonempty text')
        for field in ('units_available', 'expected_demand'):
            require(type(row[field]) is int and row[field] >= 0, loc + '.' + field, 'required nonnegative integer')
    require(isinstance(checklist, list), 'campaign_checklist.json.campaign_checklist', 'expected an array')
    seen = set()
    for i, item in enumerate(checklist):
        loc = f'campaign_checklist.json.campaign_checklist[{i}]'
        require(isinstance(item, dict), loc, 'expected an object')
        for field in ('id', 'item', 'owner'):
            require(text(item.get(field)), loc + '.' + field, 'required nonempty text')
        require(item['id'] not in seen, loc + '.id', 'duplicate task identifier')
        seen.add(item['id'])
        require(type(item.get('required')) is bool, loc + '.required', 'required boolean')
        require(item.get('status') in ('complete', 'incomplete'), loc + '.status', 'expected complete or incomplete')
    return launch_date
