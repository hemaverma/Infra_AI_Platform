"""FieldExtractionExecutor: real LLM call producing balanced extraction fields."""

import logging

from agent_framework import Executor, WorkflowContext, handler
from pydantic import ValidationError

from workflow.agent import build_default_agent, extraction_agent_enabled
from workflow.clients.blob_client import upload_json_artifact
from workflow.executors.extraction.fallback import build_fallback_extraction
from workflow.executors.extraction.llm_logging import log_llm_request, log_llm_response
from workflow.executors.extraction.prompt_input import (
    build_extraction_prompt_input,
    extraction_candidate_hints_enabled,
)
from workflow.executors.extraction.prompty import (
    configured_extraction_prompty_path,
    extraction_instructions,
    render_extraction_prompt,
)
from workflow.extraction_schema import (
    MaintenanceEmailFields,
    validate_maintenance_email_fields,
)
from workflow.messages import (
    ExtractedFields,
    SafeEmail,
)
from workflow.state_snapshots import stash_json_state

logger = logging.getLogger(__name__)


class FieldExtractionExecutor(Executor):
    """Extract structured schema maintenance fields from email content via LLM."""

    def __init__(self) -> None:
        """Initialize with executor id and deferred agent construction."""
        super().__init__(id="field_extraction")
        self._agent = None
        self._instructions: str | None = None

    def _ensure_agent(self):
        if self._agent is None:
            if self._instructions is None:
                self._instructions = extraction_instructions()
            self._agent = build_default_agent(
                name="field_extractor",
                instructions=self._instructions,
                response_format=MaintenanceEmailFields,
            )
        return self._agent

    async def _emit_extracted_fields(
        self,
        safe: SafeEmail,
        fields: MaintenanceEmailFields,
        ctx: WorkflowContext[ExtractedFields],
    ) -> None:
        extracted_fields = ExtractedFields(
            workflow_instance_id=safe.workflow_instance_id,
            internet_message_id=safe.internet_message_id,
            received_at=safe.received_at,
            storage_prefix=safe.storage_prefix,
            subject=safe.subject,
            sender=safe.sender,
            fields=fields,
        )
        stash_json_state(ctx, "extracted_fields", extracted_fields)
        upload_json_artifact(safe.storage_prefix, "extraction-result.json", extracted_fields)
        await ctx.send_message(extracted_fields)

    @handler
    async def extract(self, safe: SafeEmail, ctx: WorkflowContext[ExtractedFields]) -> None:
        """Extract fields from the safe email."""
        include_candidate_hints = extraction_candidate_hints_enabled()
        prompt_message_input = build_extraction_prompt_input(
            safe,
            include_candidate_hints=include_candidate_hints,
        )
        prompt_input = render_extraction_prompt(prompt_message_input)
        if extraction_agent_enabled():
            agent = self._ensure_agent()
            log_llm_request(
                logger,
                "field_extraction",
                agent_name="field_extractor",
                instructions=self._instructions or "",
                prompt=prompt_input,
                response_format=MaintenanceEmailFields,
                metadata={
                    "workflow_instance_id": safe.workflow_instance_id,
                    "internet_message_id": safe.internet_message_id,
                    "sender": safe.sender,
                    "subject": safe.subject,
                    "prompty_path": str(configured_extraction_prompty_path()),
                    "candidate_hints_enabled": include_candidate_hints,
                },
                sections={
                    "original_email": safe.model_dump(mode="json"),
                    "message_input": prompt_message_input,
                },
            )
            result = await agent.run(prompt_input)
            fields = _validate_extraction_response(result.value)
            log_llm_response(logger, "field_extraction", response=fields)
            await self._emit_extracted_fields(safe, fields, ctx)
        else:
            logger.info(
                "field_extraction: live llm disabled; using deterministic fallback message_id=%s",
                safe.internet_message_id,
            )
            fields = _validate_extraction_response(build_fallback_extraction(safe))
            await self._emit_extracted_fields(safe, fields, ctx)


def _validate_extraction_response(value: object) -> MaintenanceEmailFields:
    """Revalidate extraction output against the current schema and log failures."""
    try:
        return validate_maintenance_email_fields(value)
    except ValidationError:
        logger.exception(
            "field_extraction: llm response failed schema validation for model=%s",
            MaintenanceEmailFields.__name__,
        )
        raise
