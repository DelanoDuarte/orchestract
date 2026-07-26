from collections.abc import Callable

from app.domain.shared.exceptions import NotFoundError
from app.domain.users.exceptions import DuplicateEmailError, InvalidCredentialsError
from app.domain.users.models import User, UserSession
from app.infrastructure.db.unit_of_work import UnitOfWork


class UserService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def create_user(
        self, organization_id: int, name: str, email: str, raw_password: str, role_id: int
    ) -> User:
        async with self._uow_factory() as uow:
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

    async def authenticate(self, email: str, raw_password: str) -> User:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_email(email)
            if user is None or not user.is_active or not user.verify_password(raw_password):
                raise InvalidCredentialsError()
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
