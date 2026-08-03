import asyncio

import pytest

from app.application.social_auth_service import SocialAuthService
from app.domain.tenancy.models import Organization
from app.domain.users.exceptions import SocialLoginError
from app.domain.users.models import User
from app.infrastructure.auth.google_oidc import GoogleIdentity


class _IdAssigningRepo:
    """Mimics the real repos' add() + flush(): assigns an incrementing id the
    moment the entity is added, mirroring autoincrement-on-flush."""

    def __init__(self, counter: list[int]) -> None:
        self._counter = counter
        self.added: list = []

    async def add(self, entity) -> None:
        self._counter[0] += 1
        entity.id = self._counter[0]
        self.added.append(entity)


class _FakeUsersRepo(_IdAssigningRepo):
    def __init__(self, counter: list[int], existing_user: User | None = None) -> None:
        super().__init__(counter)
        self._existing = existing_user

    async def get_by_email(self, email: str) -> User | None:
        if self._existing is not None and self._existing.email == email.strip().lower():
            return self._existing
        return None


class _FakeUow:
    def __init__(self, existing_user: User | None = None) -> None:
        counter = [0]
        self.organizations = _IdAssigningRepo(counter)
        self.roles = _IdAssigningRepo(counter)
        self.users = _FakeUsersRepo(counter, existing_user)
        self.terms_acceptances = _IdAssigningRepo(counter)
        self.committed = False

    async def __aenter__(self) -> "_FakeUow":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def commit(self) -> None:
        self.committed = True


def _identity(**overrides) -> GoogleIdentity:
    base = dict(
        sub="google-sub-123",
        email="dana@example.com",
        email_verified=True,
        name="Dana Drafter",
        given_name="Dana",
    )
    base.update(overrides)
    return GoogleIdentity(**base)


def test_new_google_user_creates_org_role_verified_user_and_terms():
    uow = _FakeUow()
    service = SocialAuthService(lambda: uow)

    user = asyncio.run(
        service.login_or_register_google(_identity(), "2026-07-31", "203.0.113.7", "pytest-UA")
    )

    assert isinstance(user, User)
    assert user.google_sub == "google-sub-123"
    assert user.password_hash is None
    assert user.is_email_verified  # Google-asserted, so no verification email
    organization = uow.organizations.added[0]
    assert isinstance(organization, Organization)
    assert organization.name == "Dana's workspace"
    role = uow.roles.added[0]
    assert role.name == "Owner"
    assert user.role_id == role.id
    acceptance = uow.terms_acceptances.added[0]
    assert acceptance.user_id == user.id
    assert acceptance.organization_id == organization.id
    assert acceptance.version == "2026-07-31"
    assert acceptance.ip_address == "203.0.113.7"
    assert uow.committed


def test_existing_email_links_google_and_logs_in_without_new_org():
    existing = User.create(1, "Dana", "dana@example.com", "password123", role_id=1)
    existing.id = 1
    uow = _FakeUow(existing_user=existing)
    service = SocialAuthService(lambda: uow)

    user = asyncio.run(service.login_or_register_google(_identity(), "2026-07-31"))

    assert user is existing
    assert user.google_sub == "google-sub-123"  # backfilled
    assert user.is_email_verified  # linking marks the address verified
    assert uow.organizations.added == []  # no duplicate org for an existing account


def test_unverified_google_email_is_rejected():
    service = SocialAuthService(lambda: _FakeUow())
    with pytest.raises(SocialLoginError):
        asyncio.run(service.login_or_register_google(_identity(email_verified=False), "2026-07-31"))


def test_inactive_existing_account_is_rejected():
    existing = User.create(1, "Dana", "dana@example.com", "password123", role_id=1)
    existing.deactivate()
    service = SocialAuthService(lambda: _FakeUow(existing_user=existing))
    with pytest.raises(SocialLoginError):
        asyncio.run(service.login_or_register_google(_identity(), "2026-07-31"))


def test_org_name_derived_from_given_name_then_first_name_then_email():
    derive = SocialAuthService._derive_org_name
    assert derive(_identity(given_name="Dana")) == "Dana's workspace"
    assert derive(_identity(given_name=None, name="Bob Smith")) == "Bob's workspace"
    assert derive(_identity(given_name=None, name="", email="carol@example.com")) == "carol's workspace"


def test_social_user_cannot_password_login():
    """The nullable-password_hash guard: a social account never matches a
    password (would AttributeError before the guard in User.verify_password)."""
    user = User.create_social(1, "Dana", "dana@example.com", role_id=1, google_sub="s")
    assert user.password_hash is None
    assert user.verify_password("anything") is False
