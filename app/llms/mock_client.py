from app.llms.base import LLMClient
from app.policy.readiness import evaluate_readiness
from app.ontology.models import LaunchReadinessContext, Severity, ResolutionStatus


class MockLLMClient(LLMClient):

    def generate(self, context: LaunchReadinessContext) -> dict:
        blockers = [
            s for s in context.signals
            if s.severity == Severity.BLOCKER
        ]
        high = [
            s for s in context.signals
            if s.severity == Severity.HIGH
        ]

        decision = evaluate_readiness(context)
        overall_status = decision.overall_status
        pending_conflicts = [c for c in context.conflicts if c.resolution != ResolutionStatus.RESOLVED]

        blocker_titles = [s.title for s in blockers]
        high_titles = [s.title for s in high[:2]]
        conflict_count = len(pending_conflicts)

        summary_parts = []
        if blockers:
            summary_parts.append(
                f"The following blockers must be resolved before launch: "
                f"{'; '.join(blocker_titles)}."
            )
        if high_titles:
            summary_parts.append(
                f"High severity risks include: {'; '.join(high_titles)}."
            )
        if conflict_count:
            summary_parts.append(
                f"{conflict_count} cross-domain conflict(s) were detected "
                f"and require human review."
            )

        executive_summary = " ".join(summary_parts) or "No significant risks detected."

        actions = []
        for signal in blockers + high:
            actions.append({
                "action": f"Resolve: {signal.title}",
                "signal_ids": [signal.signal_id],
                "conflict_fields": [],
            })
        for conflict in pending_conflicts:
            actions.append({
                "action": f"Review discrepancy between {conflict.source_a} and {conflict.source_b}.",
                "signal_ids": [],
                "conflict_fields": [conflict.field],
            })

        confidence = decision.confidence
        human_review_required = decision.human_review_required
        human_review_reason = "; ".join(decision.review_reasons) or None

        return {
            "overall_status": overall_status,
            "executive_summary": executive_summary,
            "recommended_actions": actions,
            "confidence": confidence,
            "human_review_required": human_review_required,
            "human_review_reason": human_review_reason
        }
