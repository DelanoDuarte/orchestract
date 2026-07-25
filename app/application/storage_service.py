from collections.abc import Callable
from datetime import datetime

from app.domain.shared.exceptions import NotFoundError
from app.domain.storage.exceptions import DuplicateProviderConnectionError
from app.domain.storage.models import StorageConnection, StorageProvider
from app.domain.storage.ports import ExternalFile, OAuthTokens
from app.infrastructure.db.unit_of_work import UnitOfWork
from app.infrastructure.storage.factory import build_file_connector

OAUTH_PROVIDERS = {StorageProvider.GOOGLE_DRIVE, StorageProvider.ONEDRIVE}


def _tokens_to_secrets(tokens: OAuthTokens) -> dict:
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_at": tokens.expires_at.isoformat() if tokens.expires_at else None,
    }


def _secrets_to_tokens(secrets: dict) -> OAuthTokens:
    expires_at = datetime.fromisoformat(secrets["expires_at"]) if secrets.get("expires_at") else None
    return OAuthTokens(
        access_token=secrets["access_token"], refresh_token=secrets.get("refresh_token"), expires_at=expires_at
    )


class StorageService:
    """Manages per-organization StorageConnections: the config-based write
    backends (S3/GCS/MinIO/Local) and the OAuth-based read-only connectors
    (Google Drive/OneDrive).

    "Only one connection per (org, provider)" and "only one primary
    connection per org" are cross-aggregate-instance invariants -- enforced
    here, not inside StorageConnection itself, since they depend on sibling
    rows (see StorageConnection's docstring).
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def connect_bucket(
        self,
        organization_id: int,
        provider: StorageProvider,
        display_name: str,
        config: dict,
        credentials: dict,
    ) -> StorageConnection:
        async with self._uow_factory() as uow:
            existing = await uow.storage_connections.get_by_org_and_provider(organization_id, provider)
            if existing is not None:
                raise DuplicateProviderConnectionError(provider.value)
            connection = StorageConnection.create(organization_id, provider, display_name, config)
            connection.set_credential(credentials)
            connection.mark_connected()
            await self._promote(uow, connection)
            await uow.storage_connections.add(connection)
            await uow.commit()
            return connection

    async def start_oauth_connection(self, organization_id: int, provider: StorageProvider) -> str:
        connector = build_file_connector(provider)
        # `state` round-trips org/provider through the redirect; this is a
        # dev-grade simplification (no signed/expiring nonce) -- a production
        # deployment should add CSRF-hardening on top of this.
        state = f"{organization_id}:{provider.value}"
        return connector.get_authorization_url(state)

    async def complete_oauth_connection(self, state: str, code: str) -> StorageConnection:
        org_id_str, provider_value = state.split(":", 1)
        organization_id = int(org_id_str)
        provider = StorageProvider(provider_value)
        connector = build_file_connector(provider)
        tokens = await connector.exchange_code_for_tokens(code)

        async with self._uow_factory() as uow:
            connection = await uow.storage_connections.get_by_org_and_provider(organization_id, provider)
            if connection is None:
                connection = StorageConnection.create(
                    organization_id, provider, display_name=provider.value.replace("_", " ").title()
                )
                await uow.storage_connections.add(connection)
            connection.set_credential(_tokens_to_secrets(tokens))
            connection.mark_connected()
            await uow.commit()
            return connection

    async def set_primary(self, connection_id: int) -> StorageConnection:
        async with self._uow_factory() as uow:
            connection = await uow.storage_connections.get(connection_id)
            if connection is None:
                raise NotFoundError(f"storage connection {connection_id} not found")
            await self._promote(uow, connection)
            await uow.commit()
            return connection

    async def _promote(self, uow: UnitOfWork, connection: StorageConnection) -> None:
        current_primary = await uow.storage_connections.get_primary_for_organization(connection.organization_id)
        if current_primary is not None and current_primary.id != connection.id:
            current_primary.unmark_primary()
        connection.mark_primary()

    async def disconnect(self, connection_id: int) -> StorageConnection:
        async with self._uow_factory() as uow:
            connection = await uow.storage_connections.get(connection_id)
            if connection is None:
                raise NotFoundError(f"storage connection {connection_id} not found")
            connection.disconnect()
            await uow.commit()
            return connection

    async def list_connections(self, organization_id: int) -> list[StorageConnection]:
        async with self._uow_factory() as uow:
            return await uow.storage_connections.list_for_organization(organization_id)

    async def get(self, connection_id: int) -> StorageConnection:
        async with self._uow_factory() as uow:
            connection = await uow.storage_connections.get(connection_id)
            if connection is None:
                raise NotFoundError(f"storage connection {connection_id} not found")
            return connection

    async def browse_external_files(
        self, connection_id: int, folder_id: str | None = None
    ) -> list[ExternalFile]:
        async with self._uow_factory() as uow:
            connection = await uow.storage_connections.get(connection_id)
            if connection is None:
                raise NotFoundError(f"storage connection {connection_id} not found")
            tokens = _secrets_to_tokens(connection.credential.secrets)
            connector = build_file_connector(connection.provider)
        return await connector.list_files(tokens, folder_id)

    async def import_external_file(self, connection_id: int, external_file_id: str) -> tuple[bytes, str, str]:
        async with self._uow_factory() as uow:
            connection = await uow.storage_connections.get(connection_id)
            if connection is None:
                raise NotFoundError(f"storage connection {connection_id} not found")
            tokens = _secrets_to_tokens(connection.credential.secrets)
            connector = build_file_connector(connection.provider)
        return await connector.download_file(tokens, external_file_id)
