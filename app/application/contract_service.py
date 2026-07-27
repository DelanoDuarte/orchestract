from collections.abc import Callable

from app.domain.contracts.models import Contract
from app.domain.documents.models import Document
from app.domain.shared.exceptions import NotFoundError
from app.domain.tenancy.exceptions import PlanLimitExceededError
from app.domain.tenancy.plans import PLAN_LIMITS, Plan
from app.domain.workflow.models import WorkflowTransition
from app.domain.workflow_instances.models import WorkflowInstance
from app.infrastructure.db.unit_of_work import UnitOfWork

_DEFAULT_DOCUMENT_NAME = "Main Document"


class ContractService:
    """Orchestrates the Contract and WorkflowInstance aggregates for use
    cases spanning both (creating a Contract also starts its
    WorkflowInstance) -- this cross-aggregate coordination belongs in the
    application layer, not in either aggregate's own domain methods.
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def create_contract(
        self,
        organization_id: int,
        title: str,
        contract_type: str,
        workflow_definition_id: int,
        actor: str,
        description: str | None = None,
    ) -> Contract:
        async with self._uow_factory() as uow:
            organization = await uow.organizations.get(organization_id)
            if organization is None:
                raise NotFoundError(f"organization {organization_id} not found")
            limits = PLAN_LIMITS[Plan(organization.plan)]
            if limits.max_contracts is not None:
                existing_contracts = await uow.contracts.list_for_organization(organization_id)
                if len(existing_contracts) >= limits.max_contracts:
                    raise PlanLimitExceededError(
                        f"the {limits.display_name} plan is limited to {limits.max_contracts} contracts -- "
                        "upgrade to add more"
                    )
            definition = await uow.workflow_definitions.get(workflow_definition_id)
            if definition is None:
                raise NotFoundError(f"workflow definition {workflow_definition_id} not found")
            contract = Contract.create(organization_id, title, contract_type, description)
            contract.add_document(_DEFAULT_DOCUMENT_NAME)
            await uow.contracts.add(contract)
            instance = WorkflowInstance.start(contract.id, definition, actor)
            await uow.workflow_instances.add(instance)
            await uow.commit()
            return contract

    async def get(self, contract_id: int) -> Contract:
        async with self._uow_factory() as uow:
            contract = await uow.contracts.get(contract_id)
            if contract is None:
                raise NotFoundError(f"contract {contract_id} not found")
            return contract

    async def list_for_organization(self, organization_id: int) -> list[Contract]:
        async with self._uow_factory() as uow:
            return await uow.contracts.list_for_organization(organization_id)

    async def set_summary(self, contract_id: int, summary: str) -> Contract:
        async with self._uow_factory() as uow:
            contract = await uow.contracts.get(contract_id)
            if contract is None:
                raise NotFoundError(f"contract {contract_id} not found")
            contract.set_summary(summary)
            await uow.commit()
            return contract

    async def add_document(self, contract_id: int, name: str) -> Document:
        async with self._uow_factory() as uow:
            contract = await uow.contracts.get(contract_id)
            if contract is None:
                raise NotFoundError(f"contract {contract_id} not found")
            document = contract.add_document(name)
            await uow.commit()
            return document

    async def get_instance(self, contract_id: int) -> WorkflowInstance:
        async with self._uow_factory() as uow:
            instance = await uow.workflow_instances.get_for_contract(contract_id)
            if instance is None:
                raise NotFoundError(f"no workflow instance for contract {contract_id}")
            return instance

    async def available_actions(self, contract_id: int) -> list[WorkflowTransition]:
        async with self._uow_factory() as uow:
            instance = await uow.workflow_instances.get_for_contract(contract_id)
            if instance is None:
                raise NotFoundError(f"no workflow instance for contract {contract_id}")
            definition = await uow.workflow_definitions.get(instance.workflow_definition_id)
            if definition is None:
                raise NotFoundError(f"workflow definition {instance.workflow_definition_id} not found")
            return instance.available_actions(definition)

    async def transition_contract(
        self, contract_id: int, action_name: str, actor: str, comment: str | None = None
    ) -> WorkflowInstance:
        async with self._uow_factory() as uow:
            instance = await uow.workflow_instances.get_for_contract(contract_id)
            if instance is None:
                raise NotFoundError(f"no workflow instance for contract {contract_id}")
            definition = await uow.workflow_definitions.get(instance.workflow_definition_id)
            if definition is None:
                raise NotFoundError(f"workflow definition {instance.workflow_definition_id} not found")
            instance.apply_transition(definition, action_name, actor, comment)
            await uow.commit()
            return instance
