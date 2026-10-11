from app.ontology.models import (
    LaunchSignal, EvidenceRecord, Domain, Severity, SignalType
)

REQUIRED_FIELDS = ["name", "status", "description", "care_instructions", "pdp_ready"]
VALID_STATUSES = ["active"]


def analyze_catalog(catalog: dict) -> list[LaunchSignal]:
    signals = []
    products = catalog.get("products", [])

    for product in products:
        sku = product.get("sku_base", "unknown")
        name = product.get("name", "unknown")

        for field in REQUIRED_FIELDS:
            if product.get(field) is None:
                signals.append(LaunchSignal(
                    signal_id=f"CAT-MISSING-{sku}-{field.upper()}",
                    domain=Domain.CATALOG,
                    severity=Severity.HIGH,
                    signal_type=SignalType.MISSING_DATA,
                    title=f"Missing {field} for {name}",
                    description=f"{sku} is missing required field '{field}' in product catalog.",
                    evidence=[EvidenceRecord(
                        source_file="product_catalog.json",
                        field_path=f"products[{sku}].{field}",
                        raw_value=None,
                        excerpt=f"{sku} — {field}: null"
                    )],
                    requires_llm_interpretation=False
                ))

        if product.get("status") not in VALID_STATUSES:
            signals.append(LaunchSignal(
                signal_id=f"CAT-STATUS-{sku}",
                domain=Domain.CATALOG,
                severity=Severity.BLOCKER,
                signal_type=SignalType.STATUS_INVALID,
                title=f"{name} is not active",
                description=f"{sku} has status '{product.get('status')}' and is not ready for launch.",
                evidence=[EvidenceRecord(
                    source_file="product_catalog.json",
                    field_path=f"products[{sku}].status",
                    raw_value=product.get("status"),
                    excerpt=f"{sku} — status: {product.get('status')}"
                )],
                requires_llm_interpretation=False
            ))

        if product.get("pdp_ready") is False:
            signals.append(LaunchSignal(
                signal_id=f"CAT-PDP-{sku}",
                domain=Domain.CATALOG,
                severity=Severity.HIGH,
                signal_type=SignalType.STATUS_INVALID,
                title=f"PDP not ready for {name}",
                description=f"{sku} is marked pdp_ready: false in product catalog.",
                evidence=[EvidenceRecord(
                    source_file="product_catalog.json",
                    field_path=f"products[{sku}].pdp_ready",
                    raw_value=False,
                    excerpt=f"{sku} — pdp_ready: false"
                )],
                requires_llm_interpretation=False
            ))

    return signals