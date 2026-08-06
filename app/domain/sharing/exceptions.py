from app.domain.shared.exceptions import DomainError


class ShareLinkNotActiveError(DomainError):
    """The share link is revoked or past its expiry -- treated as gone."""

    def __init__(self) -> None:
        super().__init__("This share link is no longer active.")


class InvalidSharePasswordError(DomainError):
    """The password submitted for a protected share link is wrong."""

    def __init__(self) -> None:
        super().__init__("Incorrect password.")


class NoSharedDocumentsError(DomainError):
    """A documents-scoped link was created without naming any document."""

    def __init__(self) -> None:
        super().__init__("Select at least one document to share.")
