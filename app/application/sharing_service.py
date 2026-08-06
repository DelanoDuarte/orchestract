from collections.abc import Callable, Iterable
from datetime import timedelta

from app.application.document_service import DocumentService
from app.domain.contracts.models import Contract
from app.domain.documents.models import Document, DocumentVersion
from app.domain.shared.exceptions import NotFoundError
from app.domain.sharing.exceptions import ShareLinkNotActiveError
from app.domain.sharing.models import ShareLink, ShareScope
from app.infrastructure.db.unit_of_work import UnitOfWork


class SharingService:
    """Manages ShareLinks: the external, unauthenticated review links for a
    contract's documents. Creation validates the requested documents against
    the live contract; viewing re-checks the link is still active on every
    request so a revoked/expired link stops working immediately. Streaming a
    shared file reuses DocumentService so storage-backend details stay in one
    place.
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWork], document_service: DocumentService) -> None:
        self._uow_factory = uow_factory
        self._document_service = document_service

    async def create_link(
        self,
        contract_id: int,
        scope: ShareScope,
        allow_download: bool,
        expires_in_hours: int,
        created_by: str,
        document_ids: Iterable[int] | None = None,
        raw_password: str | None = None,
    ) -> ShareLink:
        async with self._uow_factory() as uow:
            contract = await uow.contracts.get(contract_id)
            if contract is None:
                raise NotFoundError(f"contract {contract_id} not found")
            # Only ever persist references to documents that actually belong to
            # this contract -- ignore anything else a tampered form might send.
            valid_ids = {d.id for d in contract.documents}
            ids = [d for d in (document_ids or []) if d in valid_ids] if scope is ShareScope.DOCUMENTS else None
            link = ShareLink.issue(
                contract_id=contract_id,
                scope=scope,
                allow_download=allow_download,
                ttl=timedelta(hours=expires_in_hours),
                created_by=created_by,
                document_ids=ids,
                raw_password=raw_password,
            )
            await uow.share_links.add(link)
            await uow.commit()
            return link

    async def list_for_contract(self, contract_id: int) -> list[ShareLink]:
        async with self._uow_factory() as uow:
            return await uow.share_links.list_for_contract(contract_id)

    async def revoke(self, contract_id: int, link_id: int) -> None:
        async with self._uow_factory() as uow:
            link = await uow.share_links.get(link_id)
            if link is None or link.contract_id != contract_id:
                raise NotFoundError(f"share link {link_id} not found")
            link.revoke()
            await uow.commit()

    async def get_active_link(self, token: str) -> ShareLink:
        async with self._uow_factory() as uow:
            link = await uow.share_links.get_by_token(token)
            if link is None or not link.is_active():
                raise ShareLinkNotActiveError()
            return link

    async def mark_accessed(self, token: str) -> None:
        async with self._uow_factory() as uow:
            link = await uow.share_links.get_by_token(token)
            if link is not None:
                link.record_access()
                await uow.commit()

    async def resolve_shared_documents(self, link: ShareLink) -> tuple[Contract, list[Document]]:
        async with self._uow_factory() as uow:
            contract = await uow.contracts.get(link.contract_id)
            if contract is None:
                raise NotFoundError(f"contract {link.contract_id} not found")
            allowed = link.allowed_document_ids()
            documents = [d for d in contract.documents if allowed is None or d.id in allowed]
            return contract, documents

    async def get_shared_version(
        self, link: ShareLink, document_id: int, version_id: int
    ) -> tuple[DocumentVersion, bytes]:
        if not link.allows_document(document_id):
            raise NotFoundError("document not found")
        async with self._uow_factory() as uow:
            document = await uow.documents.get(document_id)
            if document is None or document.contract_id != link.contract_id:
                raise NotFoundError("document not found")
            version = next((v for v in document.versions if v.id == version_id), None)
            if version is None:
                raise NotFoundError("file version not found")
        return version, await self._document_service.download_version(version)
