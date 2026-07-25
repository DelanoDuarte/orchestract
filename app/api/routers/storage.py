from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_organization_from_header, get_storage_service
from app.api.schemas import (
    ExternalFileOut,
    OAuthStartOut,
    StorageConnectionCreate,
    StorageConnectionOut,
)
from app.application.storage_service import StorageService
from app.domain.storage.models import StorageProvider
from app.domain.tenancy.models import Organization

router = APIRouter(prefix="/storage-connections", tags=["storage"])


@router.post("", response_model=StorageConnectionOut, status_code=201)
async def connect_bucket(
    payload: StorageConnectionCreate,
    organization: Organization = Depends(get_current_organization_from_header),
    service: StorageService = Depends(get_storage_service),
):
    return await service.connect_bucket(
        organization.id, payload.provider, payload.display_name, payload.config, payload.credentials
    )


@router.get("", response_model=list[StorageConnectionOut])
async def list_connections(
    organization: Organization = Depends(get_current_organization_from_header),
    service: StorageService = Depends(get_storage_service),
):
    return await service.list_connections(organization.id)


@router.get("/oauth/{provider}/start", response_model=OAuthStartOut)
async def start_oauth(
    provider: StorageProvider,
    organization: Organization = Depends(get_current_organization_from_header),
    service: StorageService = Depends(get_storage_service),
):
    url = await service.start_oauth_connection(organization.id, provider)
    return OAuthStartOut(authorization_url=url)


@router.get("/oauth/{provider}/callback", response_model=StorageConnectionOut)
async def oauth_callback(
    provider: StorageProvider,
    code: str,
    state: str,
    service: StorageService = Depends(get_storage_service),
):
    return await service.complete_oauth_connection(state, code)


@router.post("/{connection_id}/primary", response_model=StorageConnectionOut)
async def set_primary(connection_id: int, service: StorageService = Depends(get_storage_service)):
    return await service.set_primary(connection_id)


@router.delete("/{connection_id}", response_model=StorageConnectionOut)
async def disconnect(connection_id: int, service: StorageService = Depends(get_storage_service)):
    return await service.disconnect(connection_id)


@router.get("/{connection_id}/files", response_model=list[ExternalFileOut])
async def browse_files(
    connection_id: int,
    folder_id: str | None = Query(default=None),
    service: StorageService = Depends(get_storage_service),
):
    return await service.browse_external_files(connection_id, folder_id)
