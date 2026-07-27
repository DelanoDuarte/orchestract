from app.domain.shared.exceptions import DomainError


class EmptyContractTitleError(DomainError):
    def __init__(self) -> None:
        super().__init__("contract title must not be empty")
