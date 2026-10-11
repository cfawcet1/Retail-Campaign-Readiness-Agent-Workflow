import pytest
from datetime import date
from app.ontology.models import (
    LaunchReadinessContext, LaunchSignal, EvidenceRecord,
    Domain, Severity, SignalType
)
from app.prompts.readiness_prompt import build_prompt


def make_sample_context():
    return LaunchReadinessContext(
        launch_name="Soft Lounge Spring Drop",
        launch_date=date(2026, 8, 22),
        signals=[
            LaunchSignal(
                signal_id="TEST-001",
                domain=Domain.INVENTORY,
                severity=Severity.BLOCKER,
                signal_type=SignalType.THRESHOLD_BREACH,
                title="Low inventory for SL-203-DSR-2X",
                description="22 units available against 150 expected demand.",
                evidence=[EvidenceRecord(
                    source_file="inventory.csv",
                    field_path="SL-203-DSR-2X.units_available",
                    raw_value=22,
                    excerpt="SL-203-DSR-2X — 22 units available, 150 expected demand"
                )]
            )
        ],
        conflicts=[],
        data_completeness_score=1.0,
        notes="## Open Items\n- Replenishment not confirmed. This is a potential launch blocker."
    )


class TestPromptBuilder:

    def test_prompt_is_non_empty_string(self):
        context = make_sample_context()
        prompt = build_prompt(context)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_prompt_contains_launch_name(self):
        context = make_sample_context()
        prompt = build_prompt(context)
        assert "Soft Lounge Spring Drop" in prompt

    def test_prompt_contains_signal_id(self):
        context = make_sample_context()
        prompt = build_prompt(context)
        assert "TEST-001" in prompt

    def test_prompt_contains_launch_date(self):
        context = make_sample_context()
        prompt = build_prompt(context)
        assert "2026-08-22" in prompt

    def test_prompt_contains_notes_excerpt(self):
        context = make_sample_context()
        prompt = build_prompt(context)
        assert "potential launch blocker" in prompt

    def test_prompt_requests_json_output(self):
        context = make_sample_context()
        prompt = build_prompt(context)
        assert "overall_status" in prompt
        assert "executive_summary" in prompt
        assert "recommended_actions" in prompt
        assert "human_review_required" in prompt

    def test_prompt_with_no_notes_handles_gracefully(self):
        context = make_sample_context()
        context.notes = None
        prompt = build_prompt(context)
        assert "No launch notes available." in prompt