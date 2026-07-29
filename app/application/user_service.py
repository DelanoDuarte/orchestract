from collections.abc import Callable

from app.domain.shared.exceptions import NotFoundError
from app.domain.tenancy.exceptions import PlanLimitExceededError
from app.domain.tenancy.plans import PLAN_LIMITS, Plan
from app.domain.users.exceptions import (
    DuplicateEmailError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidOrExpiredTokenError,
)
from app.domain.users.models import User, UserSession, UserToken, UserTokenPurpose
from app.infrastructure.db.unit_of_work import UnitOfWork


class UserService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def create_user(
        self, organization_id: int, name: str, email: str, raw_password: str, role_id: int
    ) -> User:
        async with self._uow_factory() as uow:
            organization = await uow.organizations.get(organization_id)
            if organization is None:
                raise NotFoundError(f"organization {organization_id} not found")
            limits = PLAN_LIMITS[Plan(organization.plan)]
            if limits.max_users is not None:
                existing_users = await uow.users.list_for_organization(organization_id)
                if len(existing_users) >= limits.max_users:
                    raise PlanLimitExceededError(
                        f"the {limits.display_name} plan is limited to {limits.max_users} users -- "
                        "upgrade to add more"
                    )
            existing = await uow.users.get_by_email(email)
            if existing is not None:
                raise DuplicateEmailError(email)
            user = User.create(organization_id, name, email, raw_password, role_id)
            await uow.users.add(user)
            await uow.commit()
            return user

    async def get(self, user_id: int) -> User:
        async with self._uow_factory() as uow:
            user = await uow.users.get(user_id)
            if user is None:
                raise NotFoundError(f"user {user_id} not found")
            return user

    async def list_users(self, organization_id: int) -> list[User]:
        async with self._uow_factory() as uow:
            return await uow.users.list_for_organization(organization_id)

    async def set_active(self, user_id: int, active: bool) -> User:
        async with self._uow_factory() as uow:
            user = await uow.users.get(user_id)
            if user is None:
                raise NotFoundError(f"user {user_id} not found")
            user.activate() if active else user.deactivate()
            await uow.commit()
            return user

    async def set_role(self, user_id: int, role_id: int) -> User:
        async with self._uow_factory() as uow:
            user = await uow.users.get(user_id)
            if user is None:
                raise NotFoundError(f"user {user_id} not found")
            user.set_role(role_id)
            await uow.commit()
            return user

    async def update_profile(self, user_id: int, name: str, role_id: int) -> User:
        """Updates a user's display name and role in a single commit (used by
        the admin "Edit user" form)."""
        async with self._uow_factory() as uow:
            user = await uow.users.get(user_id)
            if user is None:
                raise NotFoundError(f"user {user_id} not found")
            user.rename(name)
            user.set_role(role_id)
            await uow.commit()
            return user

    async def authenticate(self, email: str, raw_password: str) -> User:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_email(email)
            if user is None or not user.is_active or not user.verify_password(raw_password):
                raise InvalidCredentialsError()
            if not user.is_email_verified:
                raise EmailNotVerifiedError()
            return user

    async def create_session(self, user_id: int) -> UserSession:
        async with self._uow_factory() as uow:
            session = UserSession.issue(user_id)
            await uow.user_sessions.add(session)
            await uow.commit()
            return session

    async def get_user_by_session_token(self, token: str) -> User | None:
        async with self._uow_factory() as uow:
            session = await uow.user_sessions.get_by_token(token)
            if session is None or not session.is_valid():
                return None
            user = await uow.users.get(session.user_id)
            if user is None or not user.is_active:
                return None
            return user

    async def delete_session(self, token: str) -> None:
        async with self._uow_factory() as uow:
            await uow.user_sessions.delete(token)
            await uow.commit()

    async def force_verify(self, user_id: int) -> User:
        """Marks a user's email verified without a token -- used by the seed
        script so demo accounts can log in immediately."""
        async with self._uow_factory() as uow:
            user = await uow.users.get(user_id)
            if user is None:
                raise NotFoundError(f"user {user_id} not found")
            user.mark_email_verified()
            await uow.commit()
            return user

    async def rename(self, user_id: int, new_name: str) -> User:
        async with self._uow_factory() as uow:
            user = await uow.users.get(user_id)
            if user is None:
                raise NotFoundError(f"user {user_id} not found")
            user.rename(new_name)
            await uow.commit()
            return user

    async def change_password(self, user_id: int, current_password: str, new_password: str) -> User:
        async with self._uow_factory() as uow:
            user = await uow.users.get(user_id)
            if user is None:
                raise NotFoundError(f"user {user_id} not found")
            if not user.verify_password(current_password):
                raise InvalidCredentialsError()
            user.set_password(new_password)
            await uow.commit()
            return user

    async def create_email_verification_token(self, user_id: int) -> UserToken:
        async with self._uow_factory() as uow:
            await uow.user_tokens.delete_for_user(user_id, UserTokenPurpose.EMAIL_VERIFICATION)
            token = UserToken.issue(user_id, UserTokenPurpose.EMAIL_VERIFICATION)
            await uow.user_tokens.add(token)
            await uow.commit()
            return token

    async def resend_verification(self, email: str) -> tuple[User, UserToken] | None:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_email(email)
            if user is None or user.is_email_verified:
                return None
            await uow.user_tokens.delete_for_user(user.id, UserTokenPurpose.EMAIL_VERIFICATION)
            token = UserToken.issue(user.id, UserTokenPurpose.EMAIL_VERIFICATION)
            await uow.user_tokens.add(token)
            await uow.commit()
            return user, token

    async def verify_email(self, token: str) -> User:
        async with self._uow_factory() as uow:
            record = await uow.user_tokens.get_by_token(token, UserTokenPurpose.EMAIL_VERIFICATION)
            if record is None or not record.is_valid():
                raise InvalidOrExpiredTokenError()
            user = await uow.users.get(record.user_id)
            if user is None:
                raise InvalidOrExpiredTokenError()
            user.mark_email_verified()
            await uow.user_tokens.delete(token)
            await uow.commit()
            return user

    async def create_password_reset_token(self, email: str) -> tuple[User, UserToken] | None:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_email(email)
            if user is None or not user.is_active:
                return None
            await uow.user_tokens.delete_for_user(user.id, UserTokenPurpose.PASSWORD_RESET)
            token = UserToken.issue(user.id, UserTokenPurpose.PASSWORD_RESET)
            await uow.user_tokens.add(token)
            await uow.commit()
            return user, token

    async def reset_password(self, token: str, new_password: str) -> User:
        async with self._uow_factory() as uow:
            record = await uow.user_tokens.get_by_token(token, UserTokenPurpose.PASSWORD_RESET)
            if record is None or not record.is_valid():
                raise InvalidOrExpiredTokenError()
            user = await uow.users.get(record.user_id)
            if user is None:
                raise InvalidOrExpiredTokenError()
            user.set_password(new_password)
            await uow.user_tokens.delete(token)
            await uow.commit()
            return user
