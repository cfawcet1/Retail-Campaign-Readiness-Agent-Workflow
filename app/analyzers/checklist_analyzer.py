from app.ontology.models import (
    LaunchSignal, EvidenceRecord, Domain, Severity, SignalType
)


def analyze_checklist(checklist: list[dict]) -> list[LaunchSignal]:
    signals = []

    for item in checklist:
        if item.get("required") and item.get("status") == "incomplete":
            signals.append(LaunchSignal(
                signal_id=f"CAM-{item['id']}",
                domain=Domain.CAMPAIGN,
                severity=Severity.HIGH,
                signal_type=SignalType.CHECKLIST_INCOMPLETE,
                title=f"Campaign checklist incomplete: {item['item']}",
                description=(
                    f"Required campaign item '{item['item']}' "
                    f"owned by {item['owner']} is not yet complete."
                ),
                evidence=[EvidenceRecord(
                    source_file="campaign_checklist.json",
                    field_path=f"campaign_checklist[{item['id']}].status",
                    raw_value="incomplete",
                    excerpt=f"{item['id']} — {item['item']} ({item['owner']}): incomplete"
                )],
                requires_llm_interpretation=False
            ))

    return signals