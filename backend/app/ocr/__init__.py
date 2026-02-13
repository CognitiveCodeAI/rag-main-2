"""OCR module with support for OpenAI and Ollama backends."""

from typing import Union

from app.config import get_settings
from .prompts import OCRPrompts, PROMPT_VERSION

# Type alias for any OCR client
OCRClient = Union["OpenAIOCRClient", "OllamaOCRClient"]


def get_ocr_client() -> OCRClient:
    """Get the configured OCR client based on settings.

    Returns:
        OCR client instance (OpenAI or Ollama based on ocr_provider setting)
    """
    settings = get_settings()

    if settings.ocr_provider == "openai":
        from .openai_client import OpenAIOCRClient
        return OpenAIOCRClient()
    elif settings.ocr_provider == "ollama":
        from .ollama_client import OllamaOCRClient
        return OllamaOCRClient()
    else:
        raise ValueError(f"Unknown OCR provider: {settings.ocr_provider}")


# Re-export for backwards compatibility
from .ollama_client import OllamaOCRClient
from .openai_client import OpenAIOCRClient
