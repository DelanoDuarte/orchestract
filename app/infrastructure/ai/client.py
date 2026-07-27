import os
from functools import lru_cache

from anthropic import AsyncAnthropic

# The Anthropic SDK resolves credentials from the environment on its own
# (ANTHROPIC_API_KEY, or an `ant auth login` profile) -- no key is threaded
# through app settings so there's nothing to accidentally log or hardcode.
AI_MODEL = "claude-opus-5"


def ai_enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


@lru_cache
def get_anthropic_client() -> AsyncAnthropic:
    return AsyncAnthropic()
