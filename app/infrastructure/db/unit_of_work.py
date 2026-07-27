from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.repositories.agents import SqlAlchemyAgentRepository
from app.infrastructure.db.repositories.contracts import SqlAlchemyContractRepository
from app.infrastructure.db.repositories.documents import SqlAlchemyDocumentRepository
from app.infrastructure.db.repositories.organizations import SqlAlchemyOrganizationRepository
from app.infrastructure.db.repositories.roles import SqlAlchemyRoleRepository
from app.infrastructure.db.repositories.storage_connections import SqlAlchemyStorageConnectionRepository
from app.infrastructure.db.repositories.user_sessions import SqlAlchemyUserSessionRepository
from app.infrastructure.db.repositories.users import SqlAlchemyUserRepository
from app.infrastructure.db.repositories.workflow_definitions import SqlAlchemyWorkflowDefinitionRepository
from app.infrastructure.db.repositories.workflow_instances import SqlAlchemyWorkflowInstanceRepository


class UnitOfWork:
    """Async context manager bundling one AsyncSession with all repositories.

    Application services open one UnitOfWork per use case, call repository
    methods and domain model methods against it, then commit once -- so a
    use case that spans multiple aggregates (e.g. creating a Document and
    starting its WorkflowInstance) persists atomically.
    """

    session: AsyncSession
    organizations: SqlAlchemyOrganizationRepository
    agents: SqlAlchemyAgentRepository
    workflow_definitions: SqlAlchemyWorkflowDefinitionRepository
    workflow_instances: SqlAlchemyWorkflowInstanceRepository
    contracts: SqlAlchemyContractRepository
    documents: SqlAlchemyDocumentRepository
    storage_connections: SqlAlchemyStorageConnectionRepository
    roles: SqlAlchemyRoleRepository
    users: SqlAlchemyUserRepository
    user_sessions: SqlAlchemyUserSessionRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> "UnitOfWork":
        self.session = self._session_factory()
        self.organizations = SqlAlchemyOrganizationRepository(self.session)
        self.agents = SqlAlchemyAgentRepository(self.session)
        self.workflow_definitions = SqlAlchemyWorkflowDefinitionRepository(self.session)
        self.workflow_instances = SqlAlchemyWorkflowInstanceRepository(self.session)
        self.contracts = SqlAlchemyContractRepository(self.session)
        self.documents = SqlAlchemyDocumentRepository(self.session)
        self.storage_connections = SqlAlchemyStorageConnectionRepository(self.session)
        self.roles = SqlAlchemyRoleRepository(self.session)
        self.users = SqlAlchemyUserRepository(self.session)
        self.user_sessions = SqlAlchemyUserSessionRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
