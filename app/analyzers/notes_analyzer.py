from app.ontology.models import (
    LaunchSignal, EvidenceRecord, Domain, Severity, SignalType
)

BLOCKER_KEYWORDS = ["blocker"]
RISK_KEYWORDS = ["not yet confirmed", "no eta", "delay", "unresolved", "pending"]


def analyze_notes(notes_text: str) -> list[LaunchSignal]:
    signals = []
    lines = notes_text.splitlines()

    blocker_lines = []
    risk_lines = []

    for line in lines:
        lower = line.lower()
        if any(kw in lower for kw in BLOCKER_KEYWORDS):
            blocker_lines.append(line.strip())
        elif any(kw in lower for kw in RISK_KEYWORDS):
            risk_lines.append(line.strip())

    if blocker_lines:
        signals.append(LaunchSignal(
            signal_id="OPS-BLOCKER-NOTES",
            domain=Domain.OPERATIONAL,
            severity=Severity.BLOCKER,
            signal_type=SignalType.MISSING_DATA,
            title="Launch blocker flagged in launch notes",
            description="Launch notes explicitly identify one or more potential launch blockers.",
            evidence=[
                EvidenceRecord(
                    source_file="launch_notes.md",
                    field_path="launch_notes.open_items",
                    raw_value=line,
                    excerpt=line
                )
                for line in blocker_lines
            ],
            requires_llm_interpretation=True
        ))

    if risk_lines:
        signals.append(LaunchSignal(
            signal_id="OPS-RISK-NOTES",
            domain=Domain.OPERATIONAL,
            severity=Severity.HIGH,
            signal_type=SignalType.MISSING_DATA,
            title="Unresolved operational risks in launch notes",
            description="Launch notes reference unconfirmed or delayed items that may affect launch readiness.",
            evidence=[
                EvidenceRecord(
                    source_file="launch_notes.md",
                    field_path="launch_notes.open_items",
                    raw_value=line,
                    excerpt=line
                )
                for line in risk_lines
            ],
            requires_llm_interpretation=True
        ))

    return signals