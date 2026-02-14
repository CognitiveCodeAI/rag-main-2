#!/usr/bin/env python
"""Smoke test for Ollama DeepSeek-OCR integration.

Usage:
    python tests/test_ocr_smoke.py [--full-page PATH] [--region PATH --bbox X0,Y0,X1,Y1]

Examples:
    python tests/test_ocr_smoke.py                          # Basic connectivity test
    python tests/test_ocr_smoke.py --full-page sample.png   # OCR a full page image
    python tests/test_ocr_smoke.py --region table.png --bbox 0,0,500,300  # OCR region
"""

import sys
import argparse
import base64
from pathlib import Path
import pytest

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from app.config import get_settings


def test_connectivity():
    """Test basic connectivity to Ollama server."""
    import requests
    
    settings = get_settings()
    base_url = settings.ollama_base_url
    
    print(f"\n=== Testing Ollama Connectivity ===")
    print(f"URL: {base_url}")
    
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=10)
        response.raise_for_status()
        print(f"✓ Connection successful (status: {response.status_code})")
        return True
    except requests.exceptions.RequestException as e:
        print(f"✗ Connection failed: {e}")
        return False


def test_model_available():
    """Check if DeepSeek-OCR model is available."""
    import requests
    
    settings = get_settings()
    base_url = settings.ollama_base_url
    model = settings.ollama_ocr_model
    
    print(f"\n=== Checking Model: {model} ===")
    
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=10)
        response.raise_for_status()
        data = response.json()
        
        models = data.get("models", [])
        model_names = [m.get("name", "") for m in models]
        
        if model in model_names:
            print(f"✓ Model '{model}' is available")
            return True
        else:
            print(f"✗ Model '{model}' not found")
            print(f"  Available models: {model_names[:5]}...")
            return False
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to check model: {e}")
        return False


def test_ocr_client_init():
    """Test OCR client initialization."""
    print(f"\n=== Testing OCR Client Init ===")
    
    try:
        from app.ocr.ollama_client import OllamaOCRClient
        
        client = OllamaOCRClient()
        print(f"✓ OCR client initialized")
        print(f"  Base URL: {client.base_url}")
        print(f"  Model: {client.model}")
        print(f"  Timeout: {client.timeout}s")
        print(f"  Max retries: {client.max_retries}")
        return client
    except Exception as e:
        print(f"✗ Failed to init client: {e}")
        return None


@pytest.fixture(scope="module")
def client():
    """Provide initialized OCR client or skip OCR-bound tests."""
    c = test_ocr_client_init()
    if c is None:
        pytest.skip("OCR client unavailable")
    return c


def test_health_check(client):
    """Test OCR client health check."""
    print(f"\n=== Testing Health Check ===")
    
    try:
        healthy = client.health_check()
        if healthy:
            print(f"✓ Health check passed")
        else:
            print(f"✗ Health check failed (model may not be available)")
        return healthy
    except Exception as e:
        print(f"✗ Health check error: {e}")
        return False


def test_full_page_ocr(client, image_path: str = None):
    """Test full page OCR."""
    print(f"\n=== Testing Full Page OCR ===")
    
    # Use provided image or create a simple test image
    if image_path and Path(image_path).exists():
        print(f"Using image: {image_path}")
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
    else:
        # Create a minimal test image (white PNG)
        print("Using synthetic test image")
        # This is a minimal valid 1x1 white PNG
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
    
    try:
        result = client.ocr_full_page(
            image_bytes=image_bytes,
            doc_id="smoke_test",
            page_no=1
        )
        
        print(f"✓ Full page OCR successful")
        print(f"  Output length: {len(result)} chars")
        if result:
            preview = result[:200].replace('\n', '\\n')
            print(f"  Preview: {preview}...")
        return True
    except Exception as e:
        print(f"✗ Full page OCR failed: {e}")
        return False


def test_region_ocr(client, image_path: str = None, bbox: dict = None):
    """Test region OCR."""
    print(f"\n=== Testing Region OCR ===")
    
    if image_path and Path(image_path).exists():
        print(f"Using image: {image_path}")
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
    else:
        print("Using synthetic test image")
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
    
    try:
        result = client.ocr_region(
            image_bytes=image_bytes,
            doc_id="smoke_test",
            page_no=1,
            region_type="table"
        )
        
        print(f"✓ Region OCR successful")
        print(f"  Output length: {len(result)} chars")
        if result:
            preview = result[:200].replace('\n', '\\n')
            print(f"  Preview: {preview}...")
        return True
    except Exception as e:
        print(f"✗ Region OCR failed: {e}")
        return False


def test_prompt_templates():
    """Test OCR prompt templates."""
    print(f"\n=== Testing Prompt Templates ===")
    
    try:
        from app.ocr.prompts import OCRPrompts, PROMPT_VERSION
        
        print(f"  Prompt version: {PROMPT_VERSION}")
        
        full_page = OCRPrompts.get_full_page_prompt()
        region = OCRPrompts.get_region_prompt()
        
        print(f"✓ Full page prompt: {len(full_page)} chars")
        print(f"✓ Region prompt: {len(region)} chars")
        
        # Verify prompts contain key instructions
        assert "markdown" in full_page.lower()
        assert "table" in region.lower()
        
        print(f"✓ Prompts contain expected keywords")
        return True
    except Exception as e:
        print(f"✗ Prompt test failed: {e}")
        return False


def run_smoke_test(args):
    """Run full smoke test suite."""
    print("=" * 60)
    print("  Ollama DeepSeek-OCR Smoke Test")
    print("=" * 60)
    
    results = {}
    
    # Basic tests
    results['connectivity'] = test_connectivity()
    results['model_available'] = test_model_available()
    results['prompts'] = test_prompt_templates()
    
    # Client tests
    client = test_ocr_client_init()
    results['client_init'] = client is not None
    
    if client:
        results['health_check'] = test_health_check(client)
        
        # OCR tests (only if health check passes)
        if results['health_check']:
            results['full_page_ocr'] = test_full_page_ocr(
                client, 
                args.full_page if hasattr(args, 'full_page') else None
            )
            
            bbox = None
            if hasattr(args, 'bbox') and args.bbox:
                parts = [int(x) for x in args.bbox.split(',')]
                bbox = {'x0': parts[0], 'y0': parts[1], 'x1': parts[2], 'y1': parts[3]}
            
            results['region_ocr'] = test_region_ocr(
                client,
                args.region if hasattr(args, 'region') else None,
                bbox
            )
    
    # Summary
    print("\n" + "=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)
    
    passed = 0
    failed = 0
    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        symbol = "✓" if result else "✗"
        print(f"  {symbol} {test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n  Total: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("\n  *** ALL SMOKE TESTS PASSED ***")
        return 0
    else:
        print(f"\n  *** {failed} TESTS FAILED ***")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Ollama OCR Smoke Test")
    parser.add_argument('--full-page', help='Path to full page image for OCR test')
    parser.add_argument('--region', help='Path to region image for OCR test')
    parser.add_argument('--bbox', help='Bounding box for region (X0,Y0,X1,Y1)')
    
    args = parser.parse_args()
    
    exit_code = run_smoke_test(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
