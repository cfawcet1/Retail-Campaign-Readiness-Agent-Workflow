"""Runtime validation of the model assessment and its evidence references."""
from typing import Any
from app.ontology.models import LaunchReadinessContext


class AssessmentValidationError(ValueError):
    pass


def assessment_failure(reason: str) -> dict:
    return {
        "overall_status": "Unknown",
        "executive_summary": "Model assessment unavailable. Consult the deterministic findings and obtain human review.",
        "recommended_actions": [],
        "confidence": "Low",
        "human_review_required": True,
        "human_review_reason": reason,
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssessmentValidationError(message)


def validate_assessment(context: LaunchReadinessContext, response: Any) -> dict:
    _require(isinstance(response, dict), "assessment must be an object")
    fields = {"overall_status", "executive_summary", "recommended_actions", "confidence",
              "human_review_required", "human_review_reason"}
    _require(set(response) == fields, "assessment must contain exactly the six required fields")
    status = response['overall_status']
    _require(isinstance(status, str) and status in ('Ready', 'At Risk', 'Not Ready', 'Unknown'), "invalid overall_status")
    summary = response['executive_summary']
    _require(isinstance(summary, str) and bool(summary.strip()), "executive_summary must be nonempty text")
    confidence = response['confidence']
    _require(isinstance(confidence, str) and confidence in ('High', 'Medium', 'Low'), "invalid confidence")
    review = response['human_review_required']
    _require(type(review) is bool, "human_review_required must be a boolean")
    reason = response['human_review_reason']
    _require((review and isinstance(reason, str) and bool(reason.strip())) or (not review and reason is None),
             "human_review_reason must explain required review, or be null when review is not required")
    if status == 'Unknown':
        _require(review and confidence == 'Low', "Unknown assessments require human review and Low confidence")
    actions = response['recommended_actions']
    _require(isinstance(actions, list), "recommended_actions must be an array")
    signals = {s.signal_id for s in context.signals}
    conflicts = {c.field for c in context.conflicts}
    for i, action in enumerate(actions):
        label = f"recommended_actions[{i}]"
        _require(isinstance(action, dict) and set(action) == {'action', 'signal_ids', 'conflict_fields'},
                 f"{label} must contain action, signal_ids, and conflict_fields")
        _require(isinstance(action['action'], str) and bool(action['action'].strip()), f"{label}.action must be nonempty text")
        for field, allowed in [('signal_ids', signals), ('conflict_fields', conflicts)]:
            refs = action[field]
            _require(isinstance(refs, list) and all(isinstance(r, str) for r in refs), f"{label}.{field} must be an array of strings")
            _require(all(r in allowed for r in refs), f"{label}.{field} contains an unknown reference")
        _require(bool(action['signal_ids'] or action['conflict_fields']), f"{label} must reference at least one finding")
    return response
