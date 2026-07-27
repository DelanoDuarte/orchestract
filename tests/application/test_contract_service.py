import asyncio

import pytest

from app.application.contract_service import ContractService
from app.domain.contracts.exceptions import InvalidAIConfigError
from app.domain.contracts.models import Contract


class _FakeContractsRepo:
    def __init__(self, contract: Contract) -> None:
        self._contract = contract

    async def get(self, contract_id: int) -> Contract | None:
        return self._contract


class _FakeUow:
    def __init__(self, contract: Contract) -> None:
        self.contracts = _FakeContractsRepo(contract)

    async def __aenter__(self) -> "_FakeUow":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def commit(self) -> None:
        pass


def _service(contract: Contract) -> ContractService:
    return ContractService(lambda: _FakeUow(contract))


def test_set_ai_config_rejects_unsupported_model():
    contract = Contract.create(1, "MSA", "Services")
    service = _service(contract)

    with pytest.raises(InvalidAIConfigError):
        asyncio.run(service.set_ai_config(1, None, "gpt-4o", None, None))


def test_set_ai_config_rejects_unknown_tool_name():
    contract = Contract.create(1, "MSA", "Services")
    service = _service(contract)

    with pytest.raises(InvalidAIConfigError):
        asyncio.run(service.set_ai_config(1, None, None, None, ["delete_everything"]))


def test_set_ai_config_stores_a_valid_config():
    contract = Contract.create(1, "MSA", "Services")
    service = _service(contract)

    result = asyncio.run(
        service.set_ai_config(1, False, "claude-haiku-4-5", "Be careful", ["advance_workflow_step"])
    )

    assert result.ai_config == {
        "enabled": False,
        "model": "claude-haiku-4-5",
        "instructions": "Be careful",
        "allowed_tools": ["advance_workflow_step"],
    }


def test_set_ai_config_allows_clearing_back_to_defaults():
    contract = Contract.create(1, "MSA", "Services")
    contract.set_ai_config({"enabled": False, "model": "claude-haiku-4-5"})
    service = _service(contract)

    result = asyncio.run(service.set_ai_config(1, None, None, None, None))

    assert result.ai_config == {
        "enabled": None,
        "model": None,
        "instructions": None,
        "allowed_tools": None,
    }
