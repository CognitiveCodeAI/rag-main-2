"""OpenAI OCR client using GPT-5-mini vision capabilities.

Provides OCR capabilities for full pages and cropped regions
using OpenAI's Responses API with vision input.
"""

import base64
import logging
import time
from typing import Optional

from openai import OpenAI

from app.config import get_settings
from .prompts import OCRPrompts, PROMPT_VERSION

logger = logging.getLogger(__name__)


class OCRError(Exception):
    """OCR operation failed."""
    pass


class OpenAIOCRClient:
    """Client for OCR using OpenAI GPT-5-mini vision."""

    def __init__(
        self,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        """Initialize OCR client.

        Args:
            model: Model name (default: gpt-5-mini)
            timeout: Request timeout in seconds (default from config)
        """
        settings = get_settings()

        self.model = model or settings.ocr_openai_model
        self.timeout = timeout or settings.ocr_timeout
        self.region_timeout = settings.ocr_region_timeout

        # Initialize OpenAI client
        self.client = OpenAI()

        logger.info(f"OpenAI OCR client initialized: model={self.model}")

    def ocr_full_page(
        self,
        image_bytes: bytes,
        doc_id: str = "unknown",
        page_no: int = 0
    ) -> str:
        """OCR a full page image.

        Args:
            image_bytes: PNG image bytes
            doc_id: Document ID for logging
            page_no: Page number for logging

        Returns:
            Extracted text as markdown

        Raises:
            OCRError: If OCR fails
        """
        prompt = OCRPrompts.get_full_page_prompt()

        return self._call_vision_api(
            image_bytes=image_bytes,
            prompt=prompt,
            timeout=self.timeout,
            doc_id=doc_id,
            page_no=page_no,
            operation="full_page"
        )

    def ocr_region(
        self,
        image_bytes: bytes,
        doc_id: str = "unknown",
        page_no: int = 0,
        region_type: str = "figure"
    ) -> str:
        """OCR a cropped region (figure/table).

        Args:
            image_bytes: PNG image bytes of cropped region
            doc_id: Document ID for logging
            page_no: Page number for logging
            region_type: Type of region (figure/table) for logging

        Returns:
            Extracted text as markdown

        Raises:
            OCRError: If OCR fails
        """
        prompt = OCRPrompts.get_region_prompt()

        return self._call_vision_api(
            image_bytes=image_bytes,
            prompt=prompt,
            timeout=self.region_timeout,
            doc_id=doc_id,
            page_no=page_no,
            operation=f"region_{region_type}"
        )

    def extract_caption(
        self,
        image_bytes: bytes,
        doc_id: str = "unknown",
        page_no: int = 0
    ) -> Optional[str]:
        """Extract caption from an image region.

        Args:
            image_bytes: PNG image bytes
            doc_id: Document ID for logging
            page_no: Page number for logging

        Returns:
            Caption text or None if no caption found
        """
        prompt = OCRPrompts.get_caption_prompt()

        result = self._call_vision_api(
            image_bytes=image_bytes,
            prompt=prompt,
            timeout=self.region_timeout,
            doc_id=doc_id,
            page_no=page_no,
            operation="caption"
        )

        if result.strip().upper() == "NO_CAPTION":
            return None
        return result.strip()

    def _call_vision_api(
        self,
        image_bytes: bytes,
        prompt: str,
        timeout: int,
        doc_id: str,
        page_no: int,
        operation: str
    ) -> str:
        """Call OpenAI Responses API with vision input.

        Args:
            image_bytes: PNG image bytes
            prompt: Text prompt
            timeout: Request timeout (not directly used, OpenAI handles internally)
            doc_id: Document ID for logging
            page_no: Page number for logging
            operation: Operation type for logging

        Returns:
            Generated text response

        Raises:
            OCRError: If API call fails
        """
        # Encode image as base64 data URL
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        image_url = f"data:image/png;base64,{image_b64}"

        start_time = time.time()

        try:
            # Use the Responses API with vision input
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {"type": "input_image", "image_url": image_url},
                        ],
                    }
                ],
            )

            duration = time.time() - start_time

            # Extract text from response
            text = response.output_text.strip() if response.output_text else ""

            logger.info(
                f"[{doc_id}] OCR {operation} page={page_no} "
                f"duration={duration:.1f}s chars={len(text)} "
                f"model={self.model} prompt_version={PROMPT_VERSION}"
            )

            return text

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"[{doc_id}] OCR error {operation} page={page_no} "
                f"duration={duration:.1f}s error={e}"
            )
            raise OCRError(f"OCR request failed: {e}")

    def health_check(self) -> bool:
        """Check if OpenAI API is accessible.

        Returns:
            True if API is reachable
        """
        try:
            # Simple models list check
            models = self.client.models.list()
            model_ids = [m.id for m in models.data]

            if self.model in model_ids or any(self.model in m for m in model_ids):
                logger.info(f"OpenAI OCR health check passed: model {self.model} available")
                return True
            else:
                logger.warning(f"OpenAI OCR model {self.model} not found in available models")
                return True  # API is reachable, model might still work

        except Exception as e:
            logger.error(f"OpenAI OCR health check failed: {e}")
            return False
