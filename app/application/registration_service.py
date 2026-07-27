from collections.abc import Callable

from app.domain.tenancy.models import Organization
from app.domain.users.exceptions import DuplicateEmailError
from app.domain.users.models import Role, User, UserToken, UserTokenPurpose
from app.infrastructure.db.unit_of_work import UnitOfWork


class RegistrationService:
    """Creates a brand-new Organization + default "Owner" Role + User
    together in one transaction, exactly like ContractService creates a
    Contract + Document + WorkflowInstance together -- self-service signup
    is a cross-aggregate use case, not a single-aggregate one."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def register(
        self, organization_name: str, user_name: str, email: str, raw_password: str
    ) -> tuple[Organization, User, UserToken]:
        async with self._uow_factory() as uow:
            existing = await uow.users.get_by_email(email)
            if existing is not None:
                raise DuplicateEmailError(email)

            organization = Organization.create(organization_name)
            await uow.organizations.add(organization)

            role = Role.create(organization.id, "Owner")
            await uow.roles.add(role)

            user = User.create(organization.id, user_name, email, raw_password, role.id)
            await uow.users.add(user)

            token = UserToken.issue(user.id, UserTokenPurpose.EMAIL_VERIFICATION)
            await uow.user_tokens.add(token)

            await uow.commit()
            return organization, user, token
