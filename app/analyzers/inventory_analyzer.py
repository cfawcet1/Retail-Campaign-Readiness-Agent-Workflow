from app.ontology.models import (
    LaunchSignal, EvidenceRecord, Domain, Severity, SignalType
)

COVERAGE_THRESHOLD = 0.5


def analyze_inventory(inventory: list[dict]) -> list[LaunchSignal]:
    signals = []

    for row in inventory:
        sku = row["sku"]
        available = row["units_available"]
        demand = row["expected_demand"]
        replenishment = row["replenishment_on_order"]

        if demand == 0:
            continue

        coverage = available / demand

        if coverage < COVERAGE_THRESHOLD:
            severity = Severity.BLOCKER if not replenishment else Severity.HIGH
            signals.append(LaunchSignal(
                signal_id=f"INV-LOW-{sku}",
                domain=Domain.INVENTORY,
                severity=severity,
                signal_type=SignalType.THRESHOLD_BREACH,
                title=f"Low inventory coverage for {sku}",
                description=(
                    f"{sku} has {available} units available against "
                    f"{demand} expected demand "
                    f"({coverage:.0%} coverage). "
                    f"Replenishment on order: {replenishment}."
                ),
                evidence=[EvidenceRecord(
                    source_file="inventory.csv",
                    field_path=f"{sku}.units_available / expected_demand",
                    raw_value={"units_available": available, "expected_demand": demand},
                    excerpt=(
                        f"{sku} — {available} units available, "
                        f"{demand} expected demand, "
                        f"replenishment_on_order: {replenishment}"
                    )
                )],
                requires_llm_interpretation=False
            ))

    return signals