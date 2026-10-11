import pytest
from datetime import date
from app.ontology.models import (
    LaunchSignal, EvidenceRecord, ConflictRecord,
    LaunchReadinessContext, Domain, Severity,
    SignalType, ResolutionStatus
)


class TestOntologyModels:

    def test_launch_signal_instantiates(self):
        signal = LaunchSignal(
            signal_id="TEST-001",
            domain=Domain.INVENTORY,
            severity=Severity.HIGH,
            signal_type=SignalType.THRESHOLD_BREACH,
            title="Test signal",
            description="A test signal.",
            evidence=[]
        )
        assert signal.signal_id == "TEST-001"
        assert signal.requires_llm_interpretation is False

    def test_evidence_record_instantiates(self):
        evidence = EvidenceRecord(
            source_file="inventory.csv",
            field_path="SL-203-DSR-2X.units_available",
            raw_value=22,
            excerpt="SL-203-DSR-2X — 22 units available, 150 expected demand"
        )
        assert evidence.source_file == "inventory.csv"

    def test_conflict_record_defaults_to_unresolved(self):
        conflict = ConflictRecord(
            field="product_status",
            source_a="product_catalog.json",
            value_a="draft",
            source_b="inventory.csv",
            value_b="present in inventory"
        )
        assert conflict.resolution == ResolutionStatus.UNRESOLVED

    def test_launch_readiness_context_instantiates(self):
        context = LaunchReadinessContext(
            launch_name="Soft Lounge Spring Drop",
            launch_date=date(2026, 8, 22),
            signals=[],
            conflicts=[],
            data_completeness_score=1.0
        )
        assert context.launch_name == "Soft Lounge Spring Drop"
        assert context.notes is None