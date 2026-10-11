import os
import json
import anthropic
from app.llms.base import LLMClient
from app.validation.assessment import assessment_failure
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
            if message.stop_reason != "end_turn":
                return assessment_failure("Model response did not complete normally.")
            if not message.content or any(block.type != "text" for block in message.content):
                return assessment_failure("Model returned unexpected content blocks.")
            raw = "".join(block.text for block in message.content)
        except anthropic.APIError:
            return assessment_failure("Model API call failed.")

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return assessment_failure("Model returned invalid JSON.")
