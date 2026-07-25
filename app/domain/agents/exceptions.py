from app.domain.shared.exceptions import DomainError


class EmptyAgentNameError(DomainError):
    def __init__(self) -> None:
        super().__init__("agent name must not be empty")
