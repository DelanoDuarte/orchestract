from app.domain.shared.exceptions import DomainError


class EmptyOrganizationNameError(DomainError):
    def __init__(self) -> None:
        super().__init__("organization name must not be empty")
