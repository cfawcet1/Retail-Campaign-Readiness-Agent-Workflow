from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional


class Domain(str, Enum):
    INVENTORY = "inventory"
    CATALOG = "catalog"
    CAMPAIGN = "campaign"
    FEEDBACK = "feedback"
    OPERATIONAL = "operational"


class Severity(str, Enum):
    BLOCKER = "blocker"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SignalType(str, Enum):
    MISSING_DATA = "missing_data"
    THRESHOLD_BREACH = "threshold_breach"
    CONFLICT = "conflict"
    SENTIMENT_THEME = "sentiment_theme"
    CHECKLIST_INCOMPLETE = "checklist_incomplete"
    STATUS_INVALID = "status_invalid"


class ResolutionStatus(str, Enum):
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


@dataclass
class EvidenceRecord:
    source_file: str
    field_path: str
    raw_value: Any
    excerpt: str


@dataclass
class ConflictRecord:
    field: str
    source_a: str
    value_a: Any
    source_b: str
    value_b: Any
    resolution: ResolutionStatus = ResolutionStatus.UNRESOLVED


@dataclass
class LaunchSignal:
    signal_id: str
    domain: Domain
    severity: Severity
    signal_type: SignalType
    title: str
    description: str
    evidence: list[EvidenceRecord]
    requires_llm_interpretation: bool = False


@dataclass
class LaunchReadinessContext:
    launch_name: str
    launch_date: date
    signals: list[LaunchSignal]
    conflicts: list[ConflictRecord]
    data_completeness_score: float
    notes: Optional[str] = None