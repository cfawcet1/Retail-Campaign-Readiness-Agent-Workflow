from app.llms.base import LLMClient
from app.ontology.models import LaunchReadinessContext, Severity


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

        if blockers:
            overall_status = "Not Ready"
        elif high:
            overall_status = "At Risk"
        else:
            overall_status = "Ready"

        blocker_titles = [s.title for s in blockers]
        high_titles = [s.title for s in high[:2]]
        conflict_count = len(context.conflicts)

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
            actions.append(
                f"[{signal.signal_id}] Resolve: {signal.title}"
            )
        for conflict in context.conflicts:
            actions.append(
                f"[CONFLICT] Review discrepancy in '{conflict.field}' "
                f"between {conflict.source_a} and {conflict.source_b}."
            )

        if context.data_completeness_score >= 0.8:
            confidence = "High"
        elif context.data_completeness_score >= 0.5:
            confidence = "Medium"
        else:
            confidence = "Low"

        human_review_required = bool(blockers) or bool(context.conflicts)
        human_review_reason = None
        if human_review_required:
            reasons = []
            if blockers:
                reasons.append("one or more launch blockers detected")
            if context.conflicts:
                reasons.append("unresolved cross-domain conflicts present")
            human_review_reason = "Human review required: " + ", ".join(reasons) + "."

        return {
            "overall_status": overall_status,
            "executive_summary": executive_summary,
            "recommended_actions": actions,
            "confidence": confidence,
            "human_review_required": human_review_required,
            "human_review_reason": human_review_reason
        }