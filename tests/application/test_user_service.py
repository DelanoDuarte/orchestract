import asyncio

import pytest

from app.application.user_service import UserService
from app.domain.tenancy.exceptions import PlanLimitExceededError
from app.domain.tenancy.models import Organization
from app.domain.tenancy.plans import Plan
from app.domain.users.exceptions import EmailNotVerifiedError, InvalidCredentialsError
from app.domain.users.models import User


class _FakeOrganizationsRepo:
    def __init__(self, organization: Organization) -> None:
        self._organization = organization

    async def get(self, organization_id: int) -> Organization:
        return self._organization


class _FakeUsersRepo:
    def __init__(self, users: list[User]) -> None:
        self._users = users
        self.added: list[User] = []

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._users if u.email == email), None)

    async def list_for_organization(self, organization_id: int) -> list[User]:
        return self._users

    async def add(self, user: User) -> None:
        self.added.append(user)


class _FakeUow:
    def __init__(self, organization: Organization, users: list[User]) -> None:
        self.organizations = _FakeOrganizationsRepo(organization)
        self.users = _FakeUsersRepo(users)

    async def __aenter__(self) -> "_FakeUow":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def commit(self) -> None:
        pass


def _service(organization: Organization, users: list[User]) -> UserService:
    return UserService(lambda: _FakeUow(organization, users))


def test_authenticate_rejects_unverified_users_even_with_correct_password():
    organization = Organization.create("Acme")
    user = User.create(1, "Dana", "dana@example.com", "password123", role_id=1)
    service = _service(organization, [user])

    with pytest.raises(EmailNotVerifiedError):
        asyncio.run(service.authenticate("dana@example.com", "password123"))


def test_authenticate_succeeds_once_verified():
    organization = Organization.create("Acme")
    user = User.create(1, "Dana", "dana@example.com", "password123", role_id=1)
    user.mark_email_verified()
    service = _service(organization, [user])

    result = asyncio.run(service.authenticate("dana@example.com", "password123"))

    assert result is user


def test_authenticate_rejects_wrong_password_before_checking_verification():
    organization = Organization.create("Acme")
    user = User.create(1, "Dana", "dana@example.com", "password123", role_id=1)
    service = _service(organization, [user])

    with pytest.raises(InvalidCredentialsError):
        asyncio.run(service.authenticate("dana@example.com", "wrong-password"))


def test_create_user_rejects_beyond_free_plan_user_limit():
    organization = Organization.create("Acme")
    organization.set_plan(Plan.FREE)
    existing_users = [
        User.create(1, f"User {i}", f"user{i}@example.com", "password123", role_id=1) for i in range(3)
    ]
    service = _service(organization, existing_users)

    with pytest.raises(PlanLimitExceededError):
        asyncio.run(service.create_user(1, "New User", "new@example.com", "password123", role_id=1))


def test_create_user_allows_room_under_the_limit():
    organization = Organization.create("Acme")
    organization.set_plan(Plan.FREE)
    existing_users = [User.create(1, "User 0", "user0@example.com", "password123", role_id=1)]
    service = _service(organization, existing_users)

    user = asyncio.run(service.create_user(1, "New User", "new@example.com", "password123", role_id=1))

    assert user.email == "new@example.com"
