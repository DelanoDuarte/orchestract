import os
from functools import lru_cache

from anthropic import AsyncAnthropic

# The Anthropic SDK resolves credentials from the environment on its own
# (ANTHROPIC_API_KEY, or an `ant auth login` profile) -- no key is threaded
# through app settings so there's nothing to accidentally log or hardcode.
AI_MODEL = "claude-opus-5"

# The curated set of models a Contract's ai_config["model"] may select --
# deliberately not free text, so a typo or unsupported model string can't
# reach the Messages API. Lets a KYC case pick e.g. a cheaper/faster model
# for low-risk retail triage vs. the default for higher-rigor review. Lives
# here (not in ai_service.py) so both AIService and ContractService can
# import it without a circular dependency between the two.
SUPPORTED_AI_MODELS = ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5")

# The mutating tools a Contract's ai_config["allowed_tools"] may restrict.
# get_contract_state is read-only and always available -- it's the
# assistant's entry point and excluding it would leave it unable to do
# anything at all, including answer questions.
ASSISTANT_TOOL_NAMES = ("advance_workflow_step", "add_document_to_contract", "upload_document_version")


def ai_enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


@lru_cache
def get_anthropic_client() -> AsyncAnthropic:
    return AsyncAnthropic()
