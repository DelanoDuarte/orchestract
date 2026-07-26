from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.users.models import Role


def can_edit_step(user_role_id: int, roles_linked_to_agent: Sequence["Role"]) -> bool:
    """Whether a user holding `user_role_id` may act on a workflow step
    owned by a given agent.

    `roles_linked_to_agent` is every Role in the organization whose
    `agent_id` points at that step's agent. If none do, the step carries no
    special permission and is open to anyone; otherwise only a user whose
    role is one of those roles may act.
    """
    if not roles_linked_to_agent:
        return True
    return any(role.id == user_role_id for role in roles_linked_to_agent)
