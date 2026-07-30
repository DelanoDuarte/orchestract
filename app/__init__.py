# Load .env into the process environment as early as possible -- before any
# submodule (app.config, the AI gates, the Google/Anthropic SDKs) reads it.
#
# pydantic-settings (app.config.Settings) reads .env only for its own
# ORCHESTRACT_-prefixed fields; it never populates os.environ. But several
# consumers read *unprefixed* variables straight from os.environ:
# GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_CLOUD_PROJECT (gemini_enabled), the google
# and anthropic SDKs, and ANTHROPIC_API_KEY (ai_enabled). The VS Code debugger
# injects .env into the real environment for us, so AI looks configured there --
# but `fastapi dev` (and plain uvicorn) do not, leaving those reads empty and
# making AI silently look "not configured". Loading here makes every launcher
# behave the same. Real env vars still win (override=False), and it's a no-op
# when .env is absent (e.g. production, where Docker sets the environment).
from dotenv import load_dotenv

load_dotenv()
