from anthropic import beta_async_tool
from anthropic.lib.tools import ToolError

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
from app.infrastructure.ai.client import AI_MODEL, ai_enabled, get_anthropic_client

_SUMMARIZABLE_CONTENT_TYPES = {"text/plain", "text/markdown"}
_MAX_ASSISTANT_TURNS = 12

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

    def _require_enabled(self, organization: Organization) -> None:
        if not ai_enabled() or not PLAN_LIMITS[Plan(organization.plan)].ai_enabled:
            raise AIUnavailableError()

    async def _complete(self, prompt: str) -> str:
        client = get_anthropic_client()
        response = await client.messages.create(
            model=AI_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return next((block.text for block in response.content if block.type == "text"), "").strip()

    async def summarize_document(self, document_id: int, organization: Organization) -> Document:
        self._require_enabled(organization)
        document = await self._document_service.get(document_id)
        version = document.latest_version()
        if version is None:
            raise NoVersionsError()
        if version.content_type not in _SUMMARIZABLE_CONTENT_TYPES:
            raise UnsupportedContentTypeError(version.content_type)
        content = await self._document_service.download_version(version)
        text = content.decode("utf-8", errors="replace")
        summary = await self._complete(
            "Summarize this document in 3-5 sentences for someone managing the contract it "
            f"belongs to.\n\nDocument: {document.name}\n\n{text}"
        )
        return await self._document_service.set_summary(document_id, summary)

    async def summarize_contract(self, contract_id: int, organization: Organization) -> Contract:
        self._require_enabled(organization)
        contract = await self._contract_service.get(contract_id)
        instance = await self._contract_service.get_instance(contract_id)
        sections = [
            f"Contract: {contract.title} ({contract.contract_type})",
            f"Description: {contract.description or 'none'}",
            f"Workflow status: {instance.status.value}, current step: {instance.current_step_key}",
        ]
        for document in contract.documents:
            version = document.latest_version()
            if version is None:
                sections.append(f"Document '{document.name}': no versions uploaded yet.")
            elif version.content_type not in _SUMMARIZABLE_CONTENT_TYPES:
                sections.append(f"Document '{document.name}': [{version.content_type}, skipped for now]")
            else:
                content = await self._document_service.download_version(version)
                sections.append(f"Document '{document.name}':\n{content.decode('utf-8', errors='replace')}")
        summary = await self._complete(
            "Summarize this contract in a short paragraph for someone managing it -- cover its "
            "purpose, current status, and any notable terms from its documents:\n\n" + "\n\n".join(sections)
        )
        return await self._contract_service.set_summary(contract_id, summary)

    async def run_assistant(
        self, contract_id: int, instruction: str, current_user: User, organization: Organization
    ) -> dict:
        self._require_enabled(organization)
        client = get_anthropic_client()
        actor = f"AI Assistant (on behalf of {current_user.name})"

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

        runner = client.beta.messages.tool_runner(
            model=AI_MODEL,
            max_tokens=4096,
            max_iterations=_MAX_ASSISTANT_TURNS,
            system=[{"type": "text", "text": _ASSISTANT_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=[get_contract_state, advance_workflow_step, add_document_to_contract, upload_document_version],
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
