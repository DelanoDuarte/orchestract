from app.domain.shared.exceptions import ConflictError, DomainError


class EmptyOrganizationNameError(DomainError):
    def __init__(self) -> None:
        super().__init__("organization name must not be empty")


class PlanLimitExceededError(ConflictError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
