from app.domain.shared.exceptions import DomainError


class EmptyDocumentNameError(DomainError):
    def __init__(self) -> None:
        super().__init__("document name must not be empty")
