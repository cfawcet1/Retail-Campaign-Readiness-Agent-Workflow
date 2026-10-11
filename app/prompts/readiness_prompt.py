import json
from app.ontology.models import LaunchReadinessContext, Severity


def build_prompt(context: LaunchReadinessContext) -> str:

    signals_payload = []
    for s in context.signals:
        signals_payload.append({
            "signal_id": s.signal_id,
            "domain": s.domain.value,
            "severity": s.severity.value,
            "signal_type": s.signal_type.value,
            "title": s.title,
            "description": s.description,
            "requires_llm_interpretation": s.requires_llm_interpretation,
            "evidence": [
                {
                    "source_file": e.source_file,
                    "field_path": e.field_path,
                    "excerpt": e.excerpt
                }
                for e in s.evidence
            ]
        })

    conflicts_payload = []
    for c in context.conflicts:
        conflicts_payload.append({
            "field": c.field,
            "source_a": c.source_a,
            "value_a": c.value_a,
            "source_b": c.source_b,
            "value_b": c.value_b,
            "resolution": c.resolution.value
        })

    blocker_count = sum(
        1 for s in context.signals
        if s.severity == Severity.BLOCKER
    )

    prompt = f"""You are a launch readiness analyst for The Retail Company, a premium intimates and loungewear brand.

You have been given a structured LaunchReadinessContext produced by a deterministic analysis pipeline. Your job is to reason over this context and produce a launch readiness assessment.

## Your Constraints

- Reason only over the signals and conflicts provided. Do not infer risks that are not present in the data.
- Every recommended action must include explicit signal_ids and conflict_fields arrays. At least one array must be nonempty; every reference must exist in the provided context. Do not put references only in the action text.
- Unresolved conflicts must be named explicitly in your response — do not synthesize past them.
- Signals marked requires_llm_interpretation: true need your judgment on severity and business impact. Signals marked false are established facts — communicate them clearly, do not reinterpret them.
- If data_completeness_score is below 0.8, reflect that uncertainty in your confidence level.

## Launch Context

- Launch Name: {context.launch_name}
- Launch Date: {context.launch_date.isoformat()}
- Data Completeness Score: {context.data_completeness_score:.0%}
- Blocker Count: {blocker_count}

## Signals

{json.dumps(signals_payload, indent=2)}

## Conflicts

{json.dumps(conflicts_payload, indent=2)}

## Launch Notes Excerpt

{context.notes or "No launch notes available."}

## Your Task

Produce a JSON response with exactly these keys:

{{
  "overall_status": "Ready" | "At Risk" | "Not Ready",
  "executive_summary": "2-3 sentence summary of the launch readiness picture. Be direct. Name the most critical risks.",
  "recommended_actions": [
    {{"action": "Action to take", "signal_ids": ["existing signal_id"], "conflict_fields": []}},
    ...
  ],
  "confidence": "High" | "Medium" | "Low",
  "human_review_required": true | false,
  "human_review_reason": "One sentence explaining why human review is needed, or null if not required."
}}

## Rules for Overall Status

- Not Ready: any blocker-severity signal exists
- At Risk: no blockers but one or more high-severity signals, unresolved conflicts, data_completeness_score below 0.8, or customer feedback requiring product quality review
- Ready: no blockers, no high-severity signals, no unresolved conflicts, data_completeness_score at least 0.8, and no customer feedback requiring product quality review

- Source-presence completeness does not establish freshness or product coverage. Any DQ- signal requires human review and caps confidence at Medium.

## Rules for Human Review

- Required if: any blocker exists, any unresolved conflict exists, or data_completeness_score is below 0.6
- Required if: requires_llm_interpretation signals are present and point to a potential product quality issue

Return valid JSON only. No prose outside the JSON object.
"""

    return prompt