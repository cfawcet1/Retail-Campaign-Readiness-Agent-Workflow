import pytest
from datetime import date
from app.orchestrator.pipeline import (
    run_pipeline,
    detect_conflicts,
    compute_completeness_score,
    extract_notes_excerpt
)
from app.ontology.models import Severity, ResolutionStatus


class TestPipeline:

    def test_run_pipeline_returns_context(self):
        context = run_pipeline(data_dir="data")
        assert context.launch_name == "Soft Lounge Spring Drop"
        assert context.launch_date == date(2026, 8, 22)
        assert len(context.signals) > 0
        assert context.data_completeness_score == 1.0

    def test_pipeline_detects_blockers(self):
        context = run_pipeline(data_dir="data")
        blockers = [s for s in context.signals if s.severity == Severity.BLOCKER]
        assert len(blockers) > 0

    def test_pipeline_detects_conflicts(self):
        context = run_pipeline(data_dir="data")
        assert len(context.conflicts) > 0

    def test_pipeline_conflict_includes_draft_sku(self):
        context = run_pipeline(data_dir="data")
        conflict_fields = [c.field for c in context.conflicts]
        assert "product_status" in conflict_fields

    def test_all_signals_have_evidence(self):
        context = run_pipeline(data_dir="data")
        for signal in context.signals:
            assert len(signal.evidence) > 0, (
                f"Signal {signal.signal_id} has no evidence"
            )

    def test_notes_excerpt_extracts_open_items(self):
        notes = """## Overview
Some overview text.

## Open Items
- Replenishment not confirmed. This is a potential launch blocker.
- SL-207 still in draft.

## Cross-Functional Notes
Some notes here.

## Risk Summary
Two areas of concern going into launch.
"""
        excerpt = extract_notes_excerpt(notes)
        assert "Open Items" in excerpt
        assert "Risk Summary" in excerpt
        assert "Cross-Functional Notes" not in excerpt

    def test_completeness_score_is_1_with_all_data(self):
        score = compute_completeness_score(
            catalog={"products": [{}]},
            inventory=[{}],
            feedback=[{}],
            checklist=[{}],
            notes_text="some notes"
        )
        assert score == 1.0

    def test_completeness_score_is_partial_with_missing_data(self):
        score = compute_completeness_score(
            catalog={"products": [{}]},
            inventory=[],
            feedback=[],
            checklist=[{}],
            notes_text="some notes"
        )
        assert score == 0.6