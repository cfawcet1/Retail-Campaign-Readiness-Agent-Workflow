import pytest
from app.analyzers.catalog_analyzer import analyze_catalog
from app.analyzers.inventory_analyzer import analyze_inventory
from app.analyzers.feedback_analyzer import analyze_feedback
from app.analyzers.checklist_analyzer import analyze_checklist
from app.analyzers.notes_analyzer import analyze_notes
from app.ontology.models import Severity, SignalType, Domain


class TestCatalogAnalyzer:

    def test_detects_missing_care_instructions(self):
        catalog = {"products": [{
            "sku_base": "SL-202",
            "name": "Soft Lounge Short Slip Dress",
            "status": "active",
            "description": "A dress.",
            "care_instructions": None,
            "pdp_ready": True
        }]}
        signals = analyze_catalog(catalog)
        signal_types = [s.signal_type for s in signals]
        assert SignalType.MISSING_DATA in signal_types

    def test_detects_draft_status(self):
        catalog = {"products": [{
            "sku_base": "SL-204",
            "name": "Soft Lounge Straight Leg Pant",
            "status": "draft",
            "description": "A pant.",
            "care_instructions": "Machine wash cold.",
            "pdp_ready": True
        }]}
        signals = analyze_catalog(catalog)
        blockers = [s for s in signals if s.severity == Severity.BLOCKER]
        assert len(blockers) == 1
        assert signals[0].signal_type == SignalType.STATUS_INVALID

    def test_detects_pdp_not_ready(self):
        catalog = {"products": [{
            "sku_base": "SL-204",
            "name": "Soft Lounge Straight Leg Pant",
            "status": "active",
            "description": "A pant.",
            "care_instructions": "Machine wash cold.",
            "pdp_ready": False
        }]}
        signals = analyze_catalog(catalog)
        signal_ids = [s.signal_id for s in signals]
        assert "CAT-PDP-SL-204" in signal_ids

    def test_clean_product_emits_no_signals(self):
        catalog = {"products": [{
            "sku_base": "SL-201",
            "name": "Soft Lounge Long Slip Dress",
            "status": "active",
            "description": "A dress.",
            "care_instructions": "Machine wash cold.",
            "pdp_ready": True
        }]}
        signals = analyze_catalog(catalog)
        assert len(signals) == 0

    def test_evidence_references_correct_source_file(self):
        catalog = {"products": [{
            "sku_base": "SL-202",
            "name": "Soft Lounge Short Slip Dress",
            "status": "active",
            "description": "A dress.",
            "care_instructions": None,
            "pdp_ready": True
        }]}
        signals = analyze_catalog(catalog)
        assert all(
            e.source_file == "product_catalog.json"
            for s in signals
            for e in s.evidence
        )

class TestInventoryAnalyzer:

    def test_detects_low_coverage_without_replenishment(self):
        inventory = [{
            "sku": "SL-203-DSR-2X",
            "product_name": "Soft Lounge Bralette",
            "color": "dusty rose",
            "size": "2X",
            "units_available": 22,
            "expected_demand": 150,
            "replenishment_on_order": False
        }]
        signals = analyze_inventory(inventory)
        assert len(signals) == 1
        assert signals[0].severity == Severity.BLOCKER

    def test_detects_low_coverage_with_replenishment_as_high(self):
        inventory = [{
            "sku": "SL-202-ONX-2X",
            "product_name": "Soft Lounge Short Slip Dress",
            "color": "onyx",
            "size": "2X",
            "units_available": 38,
            "expected_demand": 180,
            "replenishment_on_order": True
        }]
        signals = analyze_inventory(inventory)
        assert len(signals) == 1
        assert signals[0].severity == Severity.HIGH

    def test_adequate_coverage_emits_no_signals(self):
        inventory = [{
            "sku": "SL-201-ONX-S",
            "product_name": "Soft Lounge Long Slip Dress",
            "color": "onyx",
            "size": "S",
            "units_available": 320,
            "expected_demand": 300,
            "replenishment_on_order": False
        }]
        signals = analyze_inventory(inventory)
        assert len(signals) == 0

    def test_evidence_contains_correct_sku(self):
        inventory = [{
            "sku": "SL-203-DSR-2X",
            "product_name": "Soft Lounge Bralette",
            "color": "dusty rose",
            "size": "2X",
            "units_available": 22,
            "expected_demand": 150,
            "replenishment_on_order": False
        }]
        signals = analyze_inventory(inventory)
        assert "SL-203-DSR-2X" in signals[0].evidence[0].excerpt

class TestFeedbackAnalyzer:

    def test_detects_sizing_theme(self):
        reviews = [
            {"product": "Soft Lounge Dress", "rating": 3,
             "text": "Sizing runs small, ordered up a size."},
            {"product": "Soft Lounge Dress", "rating": 3,
             "text": "Too small, inconsistent sizing across styles."}
        ]
        signals = analyze_feedback(reviews)
        signal_ids = [s.signal_id for s in signals]
        assert "FBK-SIZING" in signal_ids

    def test_single_review_does_not_trigger_theme(self):
        reviews = [
            {"product": "Soft Lounge Dress", "rating": 3,
             "text": "Sizing runs small."}
        ]
        signals = analyze_feedback(reviews)
        assert len(signals) == 0

    def test_fabric_opacity_theme_detected(self):
        reviews = [
            {"product": "Soft Lounge Dress", "rating": 2,
             "text": "Way too see-thru to wear alone."},
            {"product": "Soft Lounge Dress", "rating": 2,
             "text": "Fabric is completely see through, returned immediately."}
        ]
        signals = analyze_feedback(reviews)
        signal_ids = [s.signal_id for s in signals]
        assert "FBK-FABRIC_OPACITY" in signal_ids

    def test_feedback_signals_require_llm_interpretation(self):
        reviews = [
            {"product": "Soft Lounge Pants", "rating": 2,
             "text": "Waistband rolling constantly."},
            {"product": "Soft Lounge Pants", "rating": 2,
             "text": "Waistband rolls all day, frustrating."}
        ]
        signals = analyze_feedback(reviews)
        assert all(s.requires_llm_interpretation for s in signals)

    def test_positive_reviews_do_not_trigger_signals(self):
        reviews = [
            {"product": "Soft Lounge Bralette", "rating": 5,
             "text": "Perfect fit, perfect fabric. No notes."},
            {"product": "Soft Lounge Bralette", "rating": 5,
             "text": "Obsessed with this bralette."}
        ]
        signals = analyze_feedback(reviews)
        assert len(signals) == 0

class TestChecklistAnalyzer:

    def test_detects_incomplete_required_item(self):
        checklist = [{
            "id": "CC-003",
            "category": "sms",
            "item": "SMS drop notification scheduled",
            "owner": "CRM",
            "required": True,
            "status": "incomplete"
        }]
        signals = analyze_checklist(checklist)
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.CHECKLIST_INCOMPLETE

    def test_complete_item_emits_no_signal(self):
        checklist = [{
            "id": "CC-001",
            "category": "email",
            "item": "Coming Soon email scheduled",
            "owner": "CRM",
            "required": True,
            "status": "complete"
        }]
        signals = analyze_checklist(checklist)
        assert len(signals) == 0

    def test_incomplete_non_required_item_emits_no_signal(self):
        checklist = [{
            "id": "CC-010",
            "category": "paid_media",
            "item": "TikTok assets submitted",
            "owner": "Paid Media",
            "required": False,
            "status": "incomplete"
        }]
        signals = analyze_checklist(checklist)
        assert len(signals) == 0

    def test_signal_domain_is_campaign(self):
        checklist = [{
            "id": "CC-003",
            "category": "sms",
            "item": "SMS drop notification scheduled",
            "owner": "CRM",
            "required": True,
            "status": "incomplete"
        }]
        signals = analyze_checklist(checklist)
        assert signals[0].domain == Domain.CAMPAIGN

class TestNotesAnalyzer:

    def test_detects_explicit_blocker(self):
        notes = "Replenishment not confirmed. This is a potential launch blocker."
        signals = analyze_notes(notes)
        signal_ids = [s.signal_id for s in signals]
        assert "OPS-BLOCKER-NOTES" in signal_ids

    def test_detects_risk_keywords(self):
        notes = "Extended sizes have no ETA confirmed from supplier."
        signals = analyze_notes(notes)
        signal_ids = [s.signal_id for s in signals]
        assert "OPS-RISK-NOTES" in signal_ids

    def test_clean_notes_emit_no_signals(self):
        notes = "All systems go. Creative approved. Inventory confirmed."
        signals = analyze_notes(notes)
        assert len(signals) == 0

    def test_blocker_signal_is_blocker_severity(self):
        notes = "This is a potential launch blocker."
        signals = analyze_notes(notes)
        blocker_signals = [s for s in signals if s.signal_id == "OPS-BLOCKER-NOTES"]
        assert blocker_signals[0].severity == Severity.BLOCKER

    def test_blocker_requires_llm_interpretation(self):
        notes = "This is a potential launch blocker."
        signals = analyze_notes(notes)
        assert all(s.requires_llm_interpretation for s in signals)