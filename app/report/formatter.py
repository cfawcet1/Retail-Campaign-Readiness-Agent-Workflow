from app.ontology.models import LaunchReadinessContext, Severity


def format_report(context: LaunchReadinessContext, llm_response: dict) -> str:

    lines = []

    lines.append("=" * 60)
    lines.append(f"LAUNCH READINESS REPORT: {context.launch_name.upper()}")
    lines.append(f"Launch Date: {context.launch_date.isoformat()}")
    lines.append(f"Data Completeness: {context.data_completeness_score:.0%}")
    lines.append("=" * 60)

    status = llm_response.get("overall_status", "Unknown")
    lines.append(f"\nOVERALL STATUS: {status.upper()}")

    lines.append("\nEXECUTIVE SUMMARY")
    lines.append("-" * 40)
    lines.append(llm_response.get("executive_summary", "No summary available."))

    lines.append("\nSIGNALS")
    lines.append("-" * 40)

    for severity in [Severity.BLOCKER, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
        severity_signals = [
            s for s in context.signals
            if s.severity == severity
        ]
        if not severity_signals:
            continue

        lines.append(f"\n[{severity.value.upper()}]")
        for signal in severity_signals:
            lines.append(f"  {signal.signal_id}: {signal.title}")
            lines.append(f"  {signal.description}")
            for evidence in signal.evidence:
                lines.append(f"    → {evidence.source_file} | {evidence.field_path}")
                lines.append(f"      \"{evidence.excerpt}\"")

    if context.conflicts:
        lines.append("\nCONFLICTS")
        lines.append("-" * 40)
        for conflict in context.conflicts:
            lines.append(f"\n  Field: {conflict.field}")
            lines.append(f"  {conflict.source_a}: {conflict.value_a}")
            lines.append(f"  {conflict.source_b}: {conflict.value_b}")
            lines.append(f"  Resolution: {conflict.resolution.value}")

    lines.append("\nRECOMMENDED ACTIONS")
    lines.append("-" * 40)
    actions = llm_response.get("recommended_actions", [])
    if actions:
        for i, action in enumerate(actions, 1):
            lines.append(f"  {i}. {action}")
    else:
        lines.append("  No actions recommended.")

    lines.append("\nASSESSMENT METADATA")
    lines.append("-" * 40)
    lines.append(f"  Confidence: {llm_response.get('confidence', 'Unknown')}")
    lines.append(
        f"  Human Review Required: "
        f"{'Yes' if llm_response.get('human_review_required') else 'No'}"
    )
    if llm_response.get("human_review_reason"):
        lines.append(f"  Reason: {llm_response.get('human_review_reason')}")

    lines.append("\n" + "=" * 60)

    return "\n".join(lines)