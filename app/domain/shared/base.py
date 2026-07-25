from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all domain aggregates/entities.

    Lives in the domain layer (not infrastructure) because the mapped
    classes themselves are the domain model in this codebase: SQLAlchemy
    is used to persist rich domain objects directly rather than through a
    separate mapping layer. Infrastructure only owns the engine/session
    and reads this class's metadata to create tables / drive migrations.
    """
