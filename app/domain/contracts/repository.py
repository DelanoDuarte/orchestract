from typing import Protocol

from app.domain.contracts.models import Contract


class ContractRepository(Protocol):
    async def add(self, contract: Contract) -> None: ...

    async def get(self, contract_id: int) -> Contract | None: ...

    async def list_for_organization(self, organization_id: int) -> list[Contract]: ...
