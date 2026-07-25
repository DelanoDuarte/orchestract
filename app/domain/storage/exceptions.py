from app.domain.shared.exceptions import ConflictError, DomainError


class ReadOnlyProviderCannotBePrimaryError(DomainError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"'{provider}' is a read-only source and cannot be the primary storage backend")
        self.provider = provider


class NoPrimaryStorageConnectionError(ConflictError):
    def __init__(self, organization_id: int) -> None:
        super().__init__(
            f"organization {organization_id} has no primary storage connection configured yet"
        )
        self.organization_id = organization_id


class DuplicateProviderConnectionError(ConflictError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"a '{provider}' connection already exists for this organization")
        self.provider = provider
