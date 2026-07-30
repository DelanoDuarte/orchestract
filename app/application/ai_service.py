from anthropic import beta_async_tool
from anthropic.lib.tools import ToolError
from google.genai import types

from app.application.contract_service import ContractService
from app.application.document_service import DocumentService
from app.application.permissions import assert_can_edit_contract_step
from app.application.role_service import RoleService
from app.application.workflow_service import WorkflowService
from app.domain.ai.exceptions import AIUnavailableError, NoVersionsError, UnsupportedContentTypeError
from app.domain.contracts.models import Contract
from app.domain.documents.models import Document
from app.domain.shared.exceptions import DomainError
from app.domain.tenancy.models import Organization
from app.domain.tenancy.plans import PLAN_LIMITS, Plan
from app.domain.users.models import User
from app.infrastructure.ai.client import AI_MODEL, ASSISTANT_TOOL_NAMES, ai_enabled, get_anthropic_client
from app.infrastructure.ai.gemini import (
    SUMMARIZABLE_MIME_TYPES,
    build_document_part,
    gemini_enabled,
    generate_summary,
)

_MAX_ASSISTANT_TURNS = 12

# Gemini (Vertex AI) handles summarization; the multimodal model reads the
# uploaded files directly, so the prompt just frames the reviewer's goal.
_SUMMARY_SYSTEM_PROMPT = """You summarize contract documents for a busy contract manager. Be \
accurate and concise, prefer the document's own wording for key terms, and never invent facts \
that aren't in the material you're given. Call out obligations, parties, effective/expiry dates, \
amounts, and anything unusual. If a document is unreadable or empty, say so plainly. Keep every \
summary to at most 8 lines of plain prose (roughly 6-8 short sentences): write a single tight \
paragraph with no bullet points, headings, or markdown, and don't pad it out to reach the limit."""

_ASSISTANT_SYSTEM_PROMPT = """You are an assistant that helps manage a single contract moving \
through a workflow. Use get_contract_state first to see its current step, available actions, \
and documents before doing anything else. Only advance the workflow, add documents, or upload \
versions when the user actually asks you to -- for a question, just answer from the state you \
fetched. Every action you take is attributed to you as an AI assistant acting on the user's \
behalf, and is only permitted if that user is allowed to act on the contract's current step; if \
a tool reports a permission error, explain that to the user in your reply rather than retrying \
the same action."""


class AIService:
    """Two capabilities on top of the Contract/Document aggregates: one-shot
    summarization (a plain Messages API call) and an autonomous assistant
    (the SDK's Tool Runner) that can drive a contract through its workflow
    when asked to. The assistant's tools are thin wrappers around
    ContractService/DocumentService and re-run the exact same permission
    check the human web UI does -- it never has more power than the user
    who invoked it.
    """

    def __init__(
        self,
        contract_service: ContractService,
        document_service: DocumentService,
        role_service: RoleService,
        workflow_service: WorkflowService,
    ) -> None:
        self._contract_service = contract_service
        self._document_service = document_service
        self._role_service = role_service
        self._workflow_service = workflow_service

    def is_available(self, organization: Organization, contract: Contract) -> bool:
        """The org/plan gate is a hard ceiling a contract can never opt back
        into (a contract can only turn AI *off*, never turn it on beyond
        what the org's plan allows); `ai_config["enabled"] is False` is a
        per-contract escape hatch for cases too sensitive for AI regardless
        of plan."""
        if not PLAN_LIMITS[Plan(organization.plan)].ai_enabled:
            return False
        if not (gemini_enabled() or ai_enabled()):
            return False
        return contract.ai_config.get("enabled") is not False

    def unavailable_reason(self, organization: Organization, contract: Contract) -> str | None:
        """Human-readable explanation of *why* AI is off for this contract, or
        None when it's available. Mirrors `is_available`'s gates in the same
        order so the UI can tell the user why the AI controls are hidden instead
        of just showing nothing."""
        plan = PLAN_LIMITS[Plan(organization.plan)]
        if not plan.ai_enabled:
            return (
                f"AI features aren't included in the {plan.display_name} plan. "
                "Upgrade to Team or Business to enable contract summaries and the assistant."
            )
        if not (gemini_enabled() or ai_enabled()):
            return "AI isn't set up on this server yet. Contact your administrator to enable it."
        if contract.ai_config.get("enabled") is False:
            return "AI has been turned off for this contract in its AI settings below."
        return None

    def _require_enabled(self, organization: Organization, contract: Contract) -> None:
        """Plan/contract gate shared by every capability. Provider-specific
        checks (Gemini for summaries, Anthropic for the assistant) live in the
        methods themselves so each can report exactly what's missing."""
        if not self.is_available(organization, contract):
            raise AIUnavailableError()

    def _require_summaries(self, organization: Organization, contract: Contract) -> None:
        self._require_enabled(organization, contract)
        if not gemini_enabled():
            raise AIUnavailableError(
                "Summarization isn't configured -- set GOOGLE_GENAI_USE_VERTEXAI=true and "
                "GOOGLE_CLOUD_PROJECT (Vertex AI via ADC) to enable it"
            )

    def _resolve_model(self, contract: Contract) -> str:
        # Assistant only: the per-contract override is validated against the
        # Anthropic model list. Summaries run on the Gemini model instead.
        return contract.ai_config.get("model") or AI_MODEL

    def _append_instructions(self, prompt: str, contract: Contract) -> str:
        instructions = contract.ai_config.get("instructions")
        if not instructions:
            return prompt
        return f"{prompt}\n\nAdditional instructions for this contract: {instructions}"

    async def summarize_document(self, document_id: int, organization: Organization) -> Document:
        document = await self._document_service.get(document_id)
        contract = await self._contract_service.get(document.contract_id)
        self._require_summaries(organization, contract)
        version = document.latest_version()
        if version is None:
            raise NoVersionsError()
        if version.content_type not in SUMMARIZABLE_MIME_TYPES:
            raise UnsupportedContentTypeError(version.content_type)
        content = await self._document_service.download_version(version)
        part = build_document_part(content, version.content_type, document.name)
        prompt = self._append_instructions(
            f"Summarize the attached document '{document.name}' for someone managing the contract "
            "it belongs to. Ground the summary in the document's actual contents, and keep it to "
            "at most 8 lines.",
            contract,
        )
        summary = await generate_summary([part, prompt], _SUMMARY_SYSTEM_PROMPT)
        return await self._document_service.set_summary(document_id, summary)

    async def summarize_contract(self, contract_id: int, organization: Organization) -> Contract:
        contract = await self._contract_service.get(contract_id)
        self._require_summaries(organization, contract)
        instance = await self._contract_service.get_instance(contract_id)
        contents: list[types.Part | str] = [
            "Contract metadata:\n"
            f"Title: {contract.title} ({contract.contract_type})\n"
            f"Description: {contract.description or 'none'}\n"
            f"Workflow status: {instance.status.value}, current step: {instance.current_step_key}",
        ]
        for document in contract.documents:
            version = document.latest_version()
            if version is None:
                contents.append(f"Document '{document.name}': no versions uploaded yet.")
            elif version.content_type not in SUMMARIZABLE_MIME_TYPES:
                contents.append(f"Document '{document.name}': [{version.content_type}, not summarizable]")
            else:
                content = await self._document_service.download_version(version)
                contents.append(f"Document '{document.name}':")
                contents.append(build_document_part(content, version.content_type, document.name))
        prompt = self._append_instructions(
            "Using the contract metadata and the attached documents above, summarize this contract "
            "for someone managing it. Base the summary on the actual document contents, not just "
            "the metadata: cover its purpose, current status, and the notable terms found in the "
            "documents (parties, effective/expiry dates, amounts, obligations, and anything "
            "unusual). Keep it to at most 8 lines.",
            contract,
        )
        contents.append(prompt)
        summary = await generate_summary(contents, _SUMMARY_SYSTEM_PROMPT)
        return await self._contract_service.set_summary(contract_id, summary)

    async def run_assistant(
        self, contract_id: int, instruction: str, current_user: User, organization: Organization
    ) -> dict:
        contract = await self._contract_service.get(contract_id)
        self._require_enabled(organization, contract)
        if not ai_enabled():
            raise AIUnavailableError(
                "The AI assistant isn't configured -- set ANTHROPIC_API_KEY to enable it"
            )
        client = get_anthropic_client()
        actor = f"AI Assistant (on behalf of {current_user.name})"
        allowed_tools = contract.ai_config.get("allowed_tools")
        if allowed_tools is None:
            allowed_tools = list(ASSISTANT_TOOL_NAMES)
        system_prompt = self._append_instructions(_ASSISTANT_SYSTEM_PROMPT, contract)

        async def _assert_can_edit() -> None:
            try:
                await assert_can_edit_contract_step(
                    self._contract_service, self._workflow_service, self._role_service, contract_id, current_user
                )
            except DomainError as exc:
                raise ToolError(str(exc)) from exc

        @beta_async_tool
        async def get_contract_state() -> str:
            """Get the contract's current workflow step, status, available actions, its
            documents (with IDs, names, and version counts), and recent history. Call this
            first, before anything else."""
            contract = await self._contract_service.get(contract_id)
            instance = await self._contract_service.get_instance(contract_id)
            actions = await self._contract_service.available_actions(contract_id)
            lines = [
                f"Contract: {contract.title} ({contract.contract_type}), status: {instance.status.value}",
                f"Current step: {instance.current_step_key}",
                "Available actions: " + (", ".join(a.action_name for a in actions) or "none"),
                "Documents:",
            ]
            for document in contract.documents:
                lines.append(f"  - id={document.id} name={document.name!r} versions={len(document.versions)}")
            lines.append("Recent history:")
            for entry in instance.history[-5:]:
                lines.append(
                    f"  - {entry.occurred_at.isoformat()} {entry.actor}: "
                    f"{entry.from_step_key or 'start'} -> {entry.to_step_key} ({entry.action_name or 'started'})"
                )
            return "\n".join(lines)

        @beta_async_tool
        async def advance_workflow_step(action_name: str, comment: str = "") -> str:
            """Advance the contract to its next step by executing one of the action names
            listed by get_contract_state's "Available actions".

            Args:
                action_name: The exact action name to execute.
                comment: Optional comment to record in the contract's history.
            """
            await _assert_can_edit()
            try:
                await self._contract_service.transition_contract(contract_id, action_name, actor, comment or None)
            except DomainError as exc:
                raise ToolError(str(exc)) from exc
            return f"Advanced the contract via '{action_name}'."

        @beta_async_tool
        async def add_document_to_contract(name: str) -> str:
            """Add a new, empty document to the contract, e.g. an exhibit or addendum.

            Args:
                name: A short name for the new document, e.g. "Exhibit B".
            """
            await _assert_can_edit()
            try:
                document = await self._contract_service.add_document(contract_id, name)
            except DomainError as exc:
                raise ToolError(str(exc)) from exc
            return f"Added document '{document.name}' (id={document.id})."

        @beta_async_tool
        async def upload_document_version(
            document_id: int, content_text: str, filename: str, notes: str = ""
        ) -> str:
            """Upload a new plain-text version of one of the contract's documents.

            Args:
                document_id: The id of the document (from get_contract_state) to version.
                content_text: The full plain-text content of the new version.
                filename: A filename for the version, e.g. "draft-v2.txt".
                notes: Optional notes about this version.
            """
            await _assert_can_edit()
            try:
                await self._document_service.upload_version(
                    document_id, content_text.encode("utf-8"), filename, "text/plain", actor, notes or None
                )
            except DomainError as exc:
                raise ToolError(str(exc)) from exc
            return f"Uploaded a new version of document {document_id}."

        mutating_tools = {
            "advance_workflow_step": advance_workflow_step,
            "add_document_to_contract": add_document_to_contract,
            "upload_document_version": upload_document_version,
        }
        tools = [get_contract_state] + [mutating_tools[name] for name in ASSISTANT_TOOL_NAMES if name in allowed_tools]

        runner = client.beta.messages.tool_runner(
            model=self._resolve_model(contract),
            max_tokens=4096,
            max_iterations=_MAX_ASSISTANT_TURNS,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            tools=tools,
            messages=[{"role": "user", "content": instruction}],
        )

        transcript: list[dict] = []
        last_message = None
        async for message in runner:
            last_message = message
            for block in message.content:
                if block.type == "text" and block.text.strip():
                    transcript.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    transcript.append({"type": "tool_call", "name": block.name, "input": block.input})

        stopped_early = bool(last_message is not None and last_message.stop_reason == "tool_use")
        return {"transcript": transcript, "stopped_early": stopped_early}
