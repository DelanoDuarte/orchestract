from fastapi import APIRouter, Depends

from app.api.deps import get_organization_service
from app.api.schemas import OrganizationCreate, OrganizationOut
from app.application.organization_service import OrganizationService

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationOut, status_code=201)
async def create_organization(
    payload: OrganizationCreate, service: OrganizationService = Depends(get_organization_service)
):
    return await service.create_organization(payload.name)


@router.get("", response_model=list[OrganizationOut])
async def list_organizations(service: OrganizationService = Depends(get_organization_service)):
    return await service.list_organizations()


@router.get("/{slug}", response_model=OrganizationOut)
async def get_organization(slug: str, service: OrganizationService = Depends(get_organization_service)):
    return await service.get_by_slug(slug)
