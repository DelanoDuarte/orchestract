import asyncio

import pytest

from app.application.registration_service import RegistrationService
from app.domain.tenancy.models import Organization
from app.domain.users.exceptions import DuplicateEmailError
from app.domain.users.models import Role, User, UserToken, UserTokenPurpose


class _IdAssigningRepo:
    """Mimics the real repos' add() + flush(): assigns an incrementing id
    the moment the entity is added, mirroring autoincrement-on-flush."""

    def __init__(self, counter: list[int]) -> None:
        self._counter = counter
        self.added: list = []

    async def add(self, entity) -> None:
        self._counter[0] += 1
        entity.id = self._counter[0]
        self.added.append(entity)


class _FakeUsersRepo(_IdAssigningRepo):
    def __init__(self, counter: list[int], existing_email: str | None = None) -> None:
        super().__init__(counter)
        self._existing_email = existing_email

    async def get_by_email(self, email: str) -> User | None:
        if email == self._existing_email:
            return User.create(1, "Existing", email, "password123", role_id=1)
        return None


class _FakeUow:
    def __init__(self, existing_email: str | None = None) -> None:
        counter = [0]
        self.organizations = _IdAssigningRepo(counter)
        self.roles = _IdAssigningRepo(counter)
        self.users = _FakeUsersRepo(counter, existing_email)
        self.user_tokens = _IdAssigningRepo(counter)
        self.terms_acceptances = _IdAssigningRepo(counter)

    async def __aenter__(self) -> "_FakeUow":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def commit(self) -> None:
        pass


def test_register_creates_organization_role_user_and_token_atomically():
    uow = _FakeUow()
    service = RegistrationService(lambda: uow)

    organization, user, token = asyncio.run(
        service.register(
            "Acme Corp", "Dana Drafter", "dana@example.com", "password123", "2026-07-28", "203.0.113.7", "pytest-UA"
        )
    )

    assert isinstance(organization, Organization)
    assert organization.name == "Acme Corp"
    assert isinstance(user, User)
    assert user.organization_id == organization.id
    assert not user.is_email_verified
    assert isinstance(token, UserToken)
    assert token.purpose is UserTokenPurpose.EMAIL_VERIFICATION
    assert token.user_id == user.id
    role = uow.roles.added[0]
    assert isinstance(role, Role)
    assert role.name == "Owner"
    assert user.role_id == role.id
    acceptance = uow.terms_acceptances.added[0]
    assert acceptance.user_id == user.id
    assert acceptance.organization_id == organization.id
    assert acceptance.version == "2026-07-28"
    assert acceptance.ip_address == "203.0.113.7"


def test_register_rejects_duplicate_email():
    uow = _FakeUow(existing_email="dana@example.com")
    service = RegistrationService(lambda: uow)

    with pytest.raises(DuplicateEmailError):
        asyncio.run(
            service.register("Acme Corp", "Dana Drafter", "dana@example.com", "password123", "2026-07-28")
        )
