import os
import json
import anthropic
from app.llms.base import LLMClient
from app.ontology.models import LaunchReadinessContext
from app.prompts.readiness_prompt import build_prompt


class AnthropicClient(LLMClient):

    def __init__(self, model: str = "claude-sonnet-4-5"):
        self.model = model
        self.client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )

    def generate(self, context: LaunchReadinessContext) -> dict:
        prompt = build_prompt(context)

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            raw = message.content[0].text
        except anthropic.APIError as e:
            return {
                "overall_status": "Unknown",
                "executive_summary": f"LLM call failed: {e}",
                "recommended_actions": [],
                "confidence": "Low",
                "human_review_required": True,
                "human_review_reason": "LLM call failed — human review required."
            }

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {
                "overall_status": "Unknown",
                "executive_summary": raw,
                "recommended_actions": [],
                "confidence": "Low",
                "human_review_required": True,
                "human_review_reason": "LLM returned unparseable response — human review required."
            }