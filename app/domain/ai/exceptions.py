from app.domain.shared.exceptions import DomainError


class AIUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__("AI features aren't configured -- set ANTHROPIC_API_KEY to enable them")


class NoVersionsError(DomainError):
    def __init__(self) -> None:
        super().__init__("this document has no uploaded versions yet")


class UnsupportedContentTypeError(DomainError):
    def __init__(self, content_type: str) -> None:
        super().__init__(
            f"can't summarize a '{content_type}' file yet -- only plain text or Markdown are supported"
        )
