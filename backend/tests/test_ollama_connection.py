"""Test Ollama API connection and model availability."""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Ollama configuration (from environment, defaults for local development)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("OLLAMA_OCR_MODEL", "deepseek-ocr:latest")


def test_connection():
    """Test basic connectivity to Ollama."""
    print(f"\n=== Testing Ollama Connection ===")
    print(f"URL: {OLLAMA_BASE_URL}")
    
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
        response.raise_for_status()
        print(f"✓ Connection successful (status: {response.status_code})")
        return True
    except requests.exceptions.RequestException as e:
        print(f"✗ Connection failed: {e}")
        return False


def test_list_models():
    """List all available models on Ollama."""
    print(f"\n=== Available Models ===")
    
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
        response.raise_for_status()
        data = response.json()
        
        models = data.get("models", [])
        if models:
            for model in models:
                name = model.get("name", "unknown")
                size = model.get("size", 0) / (1024**3)  # Convert to GB
                print(f"  - {name} ({size:.2f} GB)")
        else:
            print("  No models found")
        
        return models
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to list models: {e}")
        return []


def test_model_available():
    """Check if the target model is available."""
    print(f"\n=== Checking Model: {MODEL_NAME} ===")
    
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
        response.raise_for_status()
        data = response.json()
        
        models = data.get("models", [])
        model_names = [m.get("name", "") for m in models]
        
        if MODEL_NAME in model_names:
            print(f"✓ Model '{MODEL_NAME}' is available")
            return True
        else:
            print(f"✗ Model '{MODEL_NAME}' not found")
            print(f"  Available models: {model_names}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to check model: {e}")
        return False


def test_model_generate():
    """Test a simple generation with the model."""
    print(f"\n=== Testing Model Generation ===")
    
    try:
        payload = {
            "model": MODEL_NAME,
            "prompt": "Say hello in one word.",
            "stream": False
        }
        
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        
        generated = data.get("response", "")
        print(f"✓ Generation successful")
        print(f"  Response: {generated[:100]}...")
        return True
    except requests.exceptions.RequestException as e:
        print(f"✗ Generation failed: {e}")
        return False


if __name__ == "__main__":
    print("="*60)
    print("  Ollama Connection Test")
    print("="*60)
    
    conn_ok = test_connection()
    
    if conn_ok:
        test_list_models()
        model_ok = test_model_available()
        
        if model_ok:
            test_model_generate()
    
    print("\n" + "="*60)
