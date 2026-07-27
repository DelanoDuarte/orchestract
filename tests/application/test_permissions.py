import asyncio

import pytest

from app.application.permissions import assert_can_edit_contract_step
from app.domain.users.exceptions import PermissionDeniedError

GATED_AGENT_ID = 42


class _FakeInstance:
    workflow_definition_id = 1
    current_step_key = "draft"


class _FakeStep:
    agent_id = GATED_AGENT_ID


class _FakeDefinition:
    def get_step(self, key: str) -> _FakeStep:
        return _FakeStep()


class _FakeContractService:
    async def get_instance(self, contract_id: int) -> _FakeInstance:
        return _FakeInstance()


class _FakeWorkflowService:
    async def get(self, definition_id: int) -> _FakeDefinition:
        return _FakeDefinition()


class _FakeRoleService:
    def __init__(self, allowed: bool) -> None:
        self._allowed = allowed

    async def can_edit_step(self, user: object, agent_id: int) -> bool:
        assert agent_id == GATED_AGENT_ID
        return self._allowed


def test_assert_can_edit_contract_step_raises_when_role_denies():
    with pytest.raises(PermissionDeniedError):
        asyncio.run(
            assert_can_edit_contract_step(
                _FakeContractService(), _FakeWorkflowService(), _FakeRoleService(False), 1, user=object()
            )
        )


def test_assert_can_edit_contract_step_passes_when_role_allows():
    asyncio.run(
        assert_can_edit_contract_step(
            _FakeContractService(), _FakeWorkflowService(), _FakeRoleService(True), 1, user=object()
        )
    )
