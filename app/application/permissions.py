from app.application.contract_service import ContractService
from app.application.role_service import RoleService
from app.application.workflow_service import WorkflowService
from app.domain.users.exceptions import PermissionDeniedError
from app.domain.users.models import User


async def assert_can_edit_contract_step(
    contract_service: ContractService,
    workflow_service: WorkflowService,
    role_service: RoleService,
    contract_id: int,
    user: User,
) -> None:
    """Shared by the web layer (human actions) and AIService (the assistant
    acting on a user's behalf) -- both must apply the exact same rule: a step
    is only editable by a user whose role is linked to the step's agent, or
    by anyone if no role is linked to it at all."""
    instance = await contract_service.get_instance(contract_id)
    definition = await workflow_service.get(instance.workflow_definition_id)
    step = definition.get_step(instance.current_step_key)
    if not await role_service.can_edit_step(user, step.agent_id):
        raise PermissionDeniedError()
