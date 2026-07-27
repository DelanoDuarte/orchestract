import asyncio

import pytest

from app.application.ai_service import AIService
from app.domain.ai.exceptions import AIUnavailableError, NoVersionsError, UnsupportedContentTypeError
from app.domain.documents.models import Document


class _FakeDocumentService:
    def __init__(self, document: Document) -> None:
        self._document = document

    async def get(self, document_id: int) -> Document:
        return self._document


def _service_for(document: Document) -> AIService:
    return AIService(
        contract_service=None,
        document_service=_FakeDocumentService(document),
        role_service=None,
        workflow_service=None,
    )


def test_summarize_document_requires_an_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    document = Document.create(name="MSA")
    service = _service_for(document)

    with pytest.raises(AIUnavailableError):
        asyncio.run(service.summarize_document(1))


def test_summarize_document_rejects_a_document_with_no_versions(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    document = Document.create(name="MSA")
    service = _service_for(document)

    with pytest.raises(NoVersionsError):
        asyncio.run(service.summarize_document(1))


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
        asyncio.run(service.summarize_document(1))
