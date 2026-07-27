import asyncio

import pytest

from app.application.ai_service import AIService
from app.domain.ai.exceptions import AIUnavailableError, NoVersionsError, UnsupportedContentTypeError
from app.domain.contracts.models import Contract
from app.domain.documents.models import Document
from app.domain.tenancy.models import Organization
from app.domain.tenancy.plans import Plan


class _FakeDocumentService:
    def __init__(self, document: Document) -> None:
        self._document = document

    async def get(self, document_id: int) -> Document:
        return self._document


class _FakeContractService:
    def __init__(self, contract: Contract) -> None:
        self._contract = contract

    async def get(self, contract_id: int) -> Contract:
        return self._contract


def _contract(ai_config: dict | None = None) -> Contract:
    contract = Contract.create(1, "MSA", "Services")
    if ai_config is not None:
        contract.ai_config = ai_config
    return contract


def _service_for(document: Document, contract: Contract | None = None) -> AIService:
    return AIService(
        contract_service=_FakeContractService(contract or _contract()),
        document_service=_FakeDocumentService(document),
        role_service=None,
        workflow_service=None,
    )


def _org(plan: Plan = Plan.BUSINESS) -> Organization:
    return Organization(plan=plan.value)


def test_summarize_document_requires_an_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    document = Document.create(name="MSA")
    service = _service_for(document)

    with pytest.raises(AIUnavailableError):
        asyncio.run(service.summarize_document(1, _org()))


def test_summarize_document_requires_a_plan_with_ai_enabled(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    document = Document.create(name="MSA")
    service = _service_for(document)

    with pytest.raises(AIUnavailableError):
        asyncio.run(service.summarize_document(1, _org(Plan.FREE)))


def test_summarize_document_rejects_a_document_with_no_versions(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    document = Document.create(name="MSA")
    service = _service_for(document)

    with pytest.raises(NoVersionsError):
        asyncio.run(service.summarize_document(1, _org()))


def test_summarize_document_rejects_unsupported_content_types(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    document = Document.create(name="MSA")
    document.add_version(
        storage_connection_id=1,
        storage_key="org-1/contract-1/doc-1/v1-msa.pdf",
        original_filename="msa.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        uploaded_by="alice",
    )
    service = _service_for(document)

    with pytest.raises(UnsupportedContentTypeError):
        asyncio.run(service.summarize_document(1, _org()))


def test_is_available_org_plan_gate_beats_contract_level_force_on(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    service = _service_for(Document.create(name="MSA"))
    contract = _contract(ai_config={"enabled": True})

    assert not service.is_available(_org(Plan.FREE), contract)


def test_is_available_contract_level_force_off_beats_allowing_org_plan(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    service = _service_for(Document.create(name="MSA"))
    contract = _contract(ai_config={"enabled": False})

    assert not service.is_available(_org(Plan.BUSINESS), contract)


def test_is_available_defaults_to_org_plan_when_config_absent(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    service = _service_for(Document.create(name="MSA"))

    assert service.is_available(_org(Plan.BUSINESS), _contract())
    assert not service.is_available(_org(Plan.FREE), _contract())


def test_summarize_document_uses_contract_model_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    document = Document.create(name="MSA")
    document.add_version(
        storage_connection_id=1,
        storage_key="org-1/contract-1/doc-1/v1-msa.txt",
        original_filename="msa.txt",
        content_type="text/plain",
        size_bytes=10,
        uploaded_by="alice",
    )
    contract = _contract(ai_config={"model": "claude-haiku-4-5"})
    service = _service_for(document, contract)

    captured = {}

    class _FakeBlock:
        type = "text"
        text = "a summary"

    class _FakeResponse:
        content = [_FakeBlock()]

    class _FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeResponse()

    class _FakeClient:
        messages = _FakeMessages()

    class _FakeDocumentServiceWithDownload(_FakeDocumentService):
        async def download_version(self, version):
            return b"contents"

        async def set_summary(self, document_id, summary):
            return document

    service._document_service = _FakeDocumentServiceWithDownload(document)
    monkeypatch.setattr("app.application.ai_service.get_anthropic_client", lambda: _FakeClient())

    asyncio.run(service.summarize_document(1, _org()))

    assert captured["model"] == "claude-haiku-4-5"


class _FakeToolRunner:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def __aiter__(self):
        async def _empty():
            return
            yield  # pragma: no cover

        return _empty()


class _FakeBetaMessages:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    def tool_runner(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeToolRunner(**kwargs)


class _FakeBeta:
    def __init__(self) -> None:
        self.messages = _FakeBetaMessages()


class _FakeAssistantClient:
    def __init__(self) -> None:
        self.beta = _FakeBeta()


class _FakeUser:
    name = "Dana"


def test_run_assistant_restricts_tools_and_resolves_model_from_contract_config(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    contract = _contract(ai_config={"model": "claude-sonnet-5", "allowed_tools": []})
    contract_service = _FakeContractService(contract)
    service = AIService(
        contract_service=contract_service, document_service=None, role_service=None, workflow_service=None
    )
    fake_client = _FakeAssistantClient()
    monkeypatch.setattr("app.application.ai_service.get_anthropic_client", lambda: fake_client)

    asyncio.run(service.run_assistant(1, "do something", _FakeUser(), _org()))

    kwargs = fake_client.beta.messages.last_kwargs
    assert kwargs["model"] == "claude-sonnet-5"
    assert [t.name for t in kwargs["tools"]] == ["get_contract_state"]
