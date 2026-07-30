import io
import os
from functools import lru_cache

from docx import Document as DocxDocument
from google import genai
from google.genai import types
from google.genai.types import HttpOptions

# Default Gemini model used for document/contract summarization. Kept as a
# module constant (mirroring AI_MODEL for the Anthropic assistant) so the model
# string can't be smuggled in from user input; overridable via env for ops.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Word .docx. Gemini can't read this inline (it's a zip of XML, not a media
# type the model ingests), so we extract its text locally first -- see
# build_document_part / extract_docx_text below.
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# MIME types we can hand straight to Gemini as an inline file part. Gemini is
# natively multimodal, so real uploaded contracts (PDFs, scans) can be
# summarized without a local text-extraction step -- a big step up from the
# text-only summarizer this replaces.
_INLINE_MIME_TYPES = frozenset(
    {
        "text/plain",
        "text/markdown",
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/webp",
    }
)

# Everything we can summarize: types Gemini reads inline, plus .docx which we
# convert to text ourselves. The application layer gates on this set.
SUMMARIZABLE_MIME_TYPES = _INLINE_MIME_TYPES | {DOCX_MIME}


def extract_docx_text(data: bytes) -> str:
    """Pull the readable text out of a .docx: paragraphs in order, plus table
    rows flattened to pipe-separated cells (contracts often keep pricing and
    party details in tables). Returns '' for an empty document."""
    document = DocxDocument(io.BytesIO(data))
    lines = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                lines.append(" | ".join(cells))
    return "\n".join(lines).strip()


def build_document_part(data: bytes, content_type: str, name: str) -> types.Part | str:
    """Turn raw document bytes into a piece of model input: an inline Part for
    natively-supported media, or extracted plain text for .docx. Returns a
    string so callers can drop it straight into a `contents` list."""
    if content_type == DOCX_MIME:
        text = extract_docx_text(data)
        return f"Contents of '{name}':\n{text}" if text else f"'{name}' is an empty document."
    return types.Part.from_bytes(data=data, mime_type=content_type)


def _use_vertexai() -> bool:
    return os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in {"1", "true", "yes"}


def gemini_enabled() -> bool:
    """True when the process is configured to reach Vertex AI via ADC.

    We deliberately don't look at ADC credentials themselves here (google-auth
    resolves those lazily at call time from the environment/metadata server);
    we only require the Vertex opt-in and a project so a half-configured
    environment surfaces a clear "not configured" error instead of a cryptic
    auth failure deep in the SDK.
    """
    return _use_vertexai() and bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))


@lru_cache
def get_gemini_client() -> genai.Client:
    # No project/location/credentials threaded through here on purpose: with
    # GOOGLE_GENAI_USE_VERTEXAI=true the SDK reads GOOGLE_CLOUD_PROJECT /
    # GOOGLE_CLOUD_LOCATION and authenticates via Application Default
    # Credentials, so there's no key in app config to log or leak.
    return genai.Client(http_options=HttpOptions(api_version="v1"), vertexai=True)


async def generate_summary(contents: list[types.Part | str], system_instruction: str) -> str:
    """One-shot summarization under a fixed system prompt. `contents` interleaves
    inline file parts (the actual uploaded documents) with text instructions.
    Async so it doesn't block the event loop (uses the SDK's `aio` surface)."""
    client = get_gemini_client()
    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system_instruction),
    )
    return (response.text or "").strip()
