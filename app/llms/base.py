from abc import ABC, abstractmethod
from app.ontology.models import LaunchReadinessContext


class LLMClient(ABC):

    @abstractmethod
    def generate(self, context: LaunchReadinessContext) -> dict:
        """
        Accept a LaunchReadinessContext and return a structured
        response dict with the following keys:

            overall_status: str        # "Ready" | "At Risk" | "Not Ready"
            executive_summary: str
            recommended_actions: list[str]
            confidence: str            # "High" | "Medium" | "Low"
            human_review_required: bool
            human_review_reason: str | None
        """
        pass