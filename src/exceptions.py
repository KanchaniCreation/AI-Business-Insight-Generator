"""Custom exceptions so the UI can show friendly messages instead of crashing."""


class InsightGeneratorError(Exception):
    """Base class for all project errors."""


class DataValidationError(InsightGeneratorError):
    """Uploaded data is empty, unreadable, or missing required columns."""


class LLMError(InsightGeneratorError):
    """Generic LLM/API failure."""


class LLMConfigError(LLMError):
    """API key or provider settings are missing/invalid."""


class LLMRateLimitError(LLMError):
    """API returned HTTP 429 even after retries."""


class LLMResponseError(LLMError):
    """API answered, but the answer was not valid JSON / did not match our schema."""
