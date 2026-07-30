from app.domain.shared.exceptions import DomainError


class AIUnavailableError(DomainError):
    """AI features are off for this contract -- either the org's plan doesn't
    include AI, the contract opted out, or the required provider isn't
    configured. The optional message lets callers say which provider is
    missing (Gemini for summaries, Anthropic for the assistant)."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or "AI features aren't available for this contract")


class NoVersionsError(DomainError):
    def __init__(self) -> None:
        super().__init__("this document has no uploaded versions yet")


class UnsupportedContentTypeError(DomainError):
    def __init__(self, content_type: str) -> None:
        super().__init__(
            f"can't summarize a '{content_type}' file -- supported types are "
            "plain text, Markdown, PDF, Word (.docx), and PNG/JPEG/WebP images"
        )
