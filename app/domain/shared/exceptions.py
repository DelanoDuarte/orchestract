class DomainError(Exception):
    """Base class for all domain-layer errors. Maps to HTTP 422 by default."""


class NotFoundError(DomainError):
    """An aggregate could not be found. Maps to HTTP 404."""


class ConflictError(DomainError):
    """A requested operation conflicts with the aggregate's current state. Maps to HTTP 409."""
