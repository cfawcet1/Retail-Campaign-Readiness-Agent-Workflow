"""Business rules enforced independently of model instructions."""
from dataclasses import dataclass
import math
from typing import Any
from app.validation.assessment import validate_assessment, assessment_failure, AssessmentValidationError

from app.ontology.models import LaunchReadinessContext, ResolutionStatus, Severity, Domain


@dataclass(frozen=True)
class ReadinessDecision:
    overall_status: str
    confidence: str
    review_reasons: tuple[str, ...]

    @property
    def human_review_required(self) -> bool:
        return bool(self.review_reasons)


def evaluate_readiness(context: LaunchReadinessContext) -> ReadinessDecision:
    score = context.data_completeness_score
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("data_completeness_score must be a finite number between 0 and 1")

    blockers = any(s.severity == Severity.BLOCKER for s in context.signals)
    high = any(s.severity == Severity.HIGH for s in context.signals)
    conflicts = any(c.resolution != ResolutionStatus.RESOLVED for c in context.conflicts)
    quality_review = any(
        s.domain == Domain.FEEDBACK and s.requires_llm_interpretation
        for s in context.signals
    )
    data_quality = any(s.signal_id.startswith("DQ-") for s in context.signals)
    reasons = []
    if blockers:
        reasons.append("one or more launch blockers detected")
    if conflicts:
        reasons.append("unresolved cross-domain conflicts present")
    if score < 0.6:
        reasons.append("source completeness below 60%")
    if data_quality:
        reasons.append("source freshness or product coverage requires review")
    if quality_review:
        reasons.append("customer feedback requires product quality review")

    status = "Not Ready" if blockers else "At Risk" if high or conflicts or score < 0.8 or quality_review else "Ready"
    confidence = "High" if score >= 0.8 else "Medium" if score >= 0.5 else "Low"
    if data_quality and confidence == "High":
        confidence = "Medium"
    return ReadinessDecision(status, confidence, tuple(reasons))


def enforce_readiness(context: LaunchReadinessContext, response: Any) -> dict:
    """Apply policy floors, preserving model uncertainty and stricter recommendations.

    Invalid assessments are replaced with an explicit failure before policy enforcement.
    """
    decision = evaluate_readiness(context)
    try:
        response = validate_assessment(context, response)
    except AssessmentValidationError as exc:
        response = assessment_failure(f"Assessment validation failed: {exc}")
    result = dict(response)
    ranks = {"Ready": 0, "At Risk": 1, "Not Ready": 2}
    model_status = response.get("overall_status")
    invalid_status = model_status not in ranks
    if invalid_status:
        result["overall_status"] = "Not Ready" if decision.overall_status == "Not Ready" else "Unknown"
    else:
        result["overall_status"] = max((model_status, decision.overall_status), key=ranks.get)

    confidence_ranks = {"Low": 0, "Medium": 1, "High": 2}
    model_confidence = response.get("confidence")
    result["confidence"] = min(
        (model_confidence if model_confidence in confidence_ranks else "Low", decision.confidence),
        key=confidence_ranks.get,
    )
    reasons = list(decision.review_reasons)
    if invalid_status:
        reasons.append("model assessment unavailable or status invalid")
    model_review = response.get("human_review_required") is True
    if model_review:
        reason = response.get("human_review_reason")
        reasons.append(reason if isinstance(reason, str) and reason.strip() else "model requested human review")
    result["human_review_required"] = bool(reasons)
    result["human_review_reason"] = "Human review required: " + "; ".join(reasons) + "." if reasons else None
    return result
