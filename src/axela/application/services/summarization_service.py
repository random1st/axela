"""AI summarization service using AWS Bedrock."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import boto3  # type: ignore[import-untyped]
import structlog
from botocore.config import Config as BotoConfig  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from axela.config import get_settings

if TYPE_CHECKING:
    from axela.domain.models import DigestItem, Project

logger = structlog.get_logger()


class SummarizationService:
    """Service for AI-powered digest summarization using AWS Bedrock."""

    def __init__(self) -> None:
        """Initialize the summarization service."""
        settings = get_settings()
        self._enabled = settings.bedrock_enabled
        self._model_id = settings.bedrock_model_id
        self._client: Any = None

        if self._enabled:
            boto_config = BotoConfig(
                region_name=settings.bedrock_region,
                retries={"max_attempts": 3, "mode": "adaptive"},
            )
            self._client = boto3.client("bedrock-runtime", config=boto_config)
            logger.info(
                "Bedrock summarization enabled",
                region=settings.bedrock_region,
                model=self._model_id,
            )

    @property
    def is_enabled(self) -> bool:
        """Check if summarization is enabled."""
        return self._enabled and self._client is not None

    async def summarize_project_items(
        self,
        project: Project,
        items: list[DigestItem],
        language: str = "ru",
    ) -> str | None:
        """Summarize items for a single project.

        Args:
            project: Project the items belong to.
            items: List of digest items to summarize.
            language: Language for the summary (ru/en).

        Returns:
            Summary text or None if summarization failed/disabled.

        """
        if not self.is_enabled or not items:
            return None

        log = logger.bind(project=project.name, item_count=len(items))

        # Build context from items
        items_text = self._format_items_for_prompt(items)

        # Create prompt
        prompt = self._build_prompt(project.name, items_text, language)

        try:
            summary = await self._invoke_model(prompt)
        except Exception as e:
            log.warning("Failed to summarize project", error=str(e))
            return None
        else:
            log.info("Project summarized successfully", summary_length=len(summary) if summary else 0)
            return summary

    def _format_items_for_prompt(self, items: list[DigestItem]) -> str:
        """Format items into text for the prompt."""
        lines = []
        for item in items:
            # Include title, type, and relevant content
            item_type = item.item_type.value if item.item_type else "item"
            line = f"- [{item_type}] {item.title or 'Untitled'}"

            # Extract description from content dict if available
            content = item.content or {}
            description = content.get("description") or content.get("summary") or content.get("body")
            if description and isinstance(description, str):
                # Truncate long descriptions
                desc = description[:200] + "..." if len(description) > 200 else description
                line += f": {desc}"

            # Extract author from content or metadata
            author = content.get("author") or content.get("assignee") or content.get("sender")
            if author:
                line += f" (by {author})"

            lines.append(line)
        return "\n".join(lines)

    def _build_prompt(self, project_name: str, items_text: str, language: str) -> str:
        """Build the summarization prompt."""
        lang_instruction = "на русском языке" if language == "ru" else "in English"

        return f"""Summarize the following updates for project "{project_name}" {lang_instruction}.
Keep the summary concise (2-3 sentences max). Focus on the most important changes and their impact.
Do not use markdown formatting. Write plain text suitable for Telegram.

Updates:
{items_text}

Summary:"""

    async def _invoke_model(self, prompt: str) -> str | None:
        """Invoke the Bedrock model.

        Args:
            prompt: The prompt to send to the model.

        Returns:
            Model response text or None if failed.

        """
        if not self._client:
            return None

        try:
            # Amazon Nova models use the messages API format
            request_body = {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ],
                "inferenceConfig": {
                    "maxTokens": 300,
                    "temperature": 0.3,
                    "topP": 0.9,
                },
            }

            response = self._client.invoke_model(
                modelId=self._model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json",
            )

            response_body = json.loads(response["body"].read())
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.warning(
                "Bedrock API error",
                error_code=error_code,
                error=str(e),
            )
            return None
        except Exception as e:
            logger.warning("Failed to invoke Bedrock model", error=str(e))
            return None

        # Extract text from Nova response format
        if "output" in response_body and "message" in response_body["output"]:
            content = response_body["output"]["message"].get("content", [])
            if content and isinstance(content, list):
                text = content[0].get("text", "")
                return str(text).strip() if text else None

        return None
