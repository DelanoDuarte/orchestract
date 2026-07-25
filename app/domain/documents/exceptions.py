from app.domain.shared.exceptions import DomainError


class EmptyDocumentTitleError(DomainError):
    def __init__(self) -> None:
        super().__init__("document title must not be empty")
