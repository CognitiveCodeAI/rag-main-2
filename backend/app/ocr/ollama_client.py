"""Ollama OCR client for DeepSeek-OCR integration.

Provides OCR capabilities for full pages and cropped regions
using the DeepSeek-OCR model via Ollama's vision API.
"""

import base64
import logging
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import get_settings
from .prompts import OCRPrompts, PROMPT_VERSION

logger = logging.getLogger(__name__)


class OCRError(Exception):
    """OCR operation failed."""
    pass


class OllamaOCRClient:
    """Client for OCR using Ollama DeepSeek-OCR."""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None
    ):
        """Initialize OCR client.
        
        Args:
            base_url: Ollama server URL (default from config)
            model: Model name (default from config)
            timeout: Request timeout in seconds (default from config)
            max_retries: Max retry attempts (default from config)
        """
        settings = get_settings()
        
        self.base_url = (base_url or settings.ollama_base_url).rstrip('/')
        self.model = model or settings.ollama_ocr_model
        self.timeout = timeout or settings.ocr_timeout
        self.region_timeout = settings.ocr_region_timeout
        self.max_retries = max_retries or settings.ocr_max_retries
        
        # Setup session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        logger.info(f"OCR client initialized: {self.base_url}, model={self.model}")
    
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
            OCRError: If OCR fails after retries
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
            OCRError: If OCR fails after retries
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
        """Call Ollama vision API using /api/chat endpoint.
        
        Args:
            image_bytes: PNG image bytes
            prompt: Text prompt
            timeout: Request timeout
            doc_id: Document ID for logging
            page_no: Page number for logging
            operation: Operation type for logging
            
        Returns:
            Generated text response
            
        Raises:
            OCRError: If API call fails
        """
        # Encode image as base64
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Use /api/chat with images INSIDE the message object (required for vision models)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],  # Images must be in messages[].images
                }
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for consistent output
            }
        }
        
        url = f"{self.base_url}/api/chat"
        
        start_time = time.time()
        
        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=timeout
            )
            response.raise_for_status()
            
            duration = time.time() - start_time
            
            result = response.json()
            # /api/chat returns message.content instead of response
            text = result.get("message", {}).get("content", "").strip()
            
            logger.info(
                f"[{doc_id}] OCR {operation} page={page_no} "
                f"duration={duration:.1f}s chars={len(text)} "
                f"prompt_version={PROMPT_VERSION}"
            )
            
            return text
            
        except requests.exceptions.Timeout:
            duration = time.time() - start_time
            logger.error(
                f"[{doc_id}] OCR timeout {operation} page={page_no} "
                f"duration={duration:.1f}s timeout={timeout}s"
            )
            raise OCRError(f"OCR timeout after {duration:.1f}s")
            
        except requests.exceptions.RequestException as e:
            duration = time.time() - start_time
            logger.error(
                f"[{doc_id}] OCR error {operation} page={page_no} "
                f"duration={duration:.1f}s error={e}"
            )
            raise OCRError(f"OCR request failed: {e}")
    
    def health_check(self) -> bool:
        """Check if Ollama server is healthy.
        
        Returns:
            True if server is reachable and model is available
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/tags",
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            
            if self.model in models:
                logger.info(f"OCR health check passed: model {self.model} available")
                return True
            else:
                logger.warning(f"OCR model {self.model} not found. Available: {models}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"OCR health check failed: {e}")
            return False
