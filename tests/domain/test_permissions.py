from app.domain.users.models import Role
from app.domain.users.permissions import can_edit_step

DRAFTING_LEAD_ROLE_ID, SIGNATORY_LEAD_ROLE_ID, GENERAL_STAFF_ROLE_ID = 1, 2, 3
DRAFTING_AGENT_ID, SIGNATORY_AGENT_ID = 10, 20


def _role(role_id: int, agent_id: int) -> Role:
    return Role(id=role_id, organization_id=1, name=f"role-{role_id}", slug=f"role-{role_id}", agent_id=agent_id)


def test_step_is_open_to_anyone_when_no_role_is_linked_to_its_agent():
    assert can_edit_step(GENERAL_STAFF_ROLE_ID, roles_linked_to_agent=[]) is True


def test_matching_role_can_edit_a_gated_step():
    linked = [_role(DRAFTING_LEAD_ROLE_ID, DRAFTING_AGENT_ID)]
    assert can_edit_step(DRAFTING_LEAD_ROLE_ID, roles_linked_to_agent=linked) is True


def test_non_matching_role_cannot_edit_a_gated_step():
    linked = [_role(DRAFTING_LEAD_ROLE_ID, DRAFTING_AGENT_ID)]
    assert can_edit_step(GENERAL_STAFF_ROLE_ID, roles_linked_to_agent=linked) is False
    assert can_edit_step(SIGNATORY_LEAD_ROLE_ID, roles_linked_to_agent=linked) is False


def test_multiple_roles_can_be_linked_to_the_same_agent():
    linked = [_role(DRAFTING_LEAD_ROLE_ID, DRAFTING_AGENT_ID), _role(SIGNATORY_LEAD_ROLE_ID, DRAFTING_AGENT_ID)]
    assert can_edit_step(DRAFTING_LEAD_ROLE_ID, roles_linked_to_agent=linked) is True
    assert can_edit_step(SIGNATORY_LEAD_ROLE_ID, roles_linked_to_agent=linked) is True
    assert can_edit_step(GENERAL_STAFF_ROLE_ID, roles_linked_to_agent=linked) is False
