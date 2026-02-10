"""Test OpenAI API connection and embedding generation."""

import os
import sys
from pathlib import Path

# Ensure we're loading from the correct .env file
env_path = Path(__file__).parent.parent / ".env"
print(f"Loading .env from: {env_path}")
print(f"File exists: {env_path.exists()}")

# Read the .env file manually first to debug
if env_path.exists():
    print("\n=== Raw .env contents (OPENAI lines) ===")
    with open(env_path, 'r') as f:
        for line in f:
            if 'OPENAI' in line:
                # Show first/last chars only for security
                if '=' in line:
                    key, val = line.strip().split('=', 1)
                    print(f"  {key}={val[:20]}...{val[-10:]}")
                    print(f"  Value length: {len(val)}")

# Now load with dotenv
from dotenv import load_dotenv
load_dotenv(env_path, override=True)

print("\n=== Environment after load_dotenv ===")
api_key = os.getenv('OPENAI_API_KEY')
print(f"OPENAI_API_KEY loaded: {api_key is not None}")
if api_key:
    print(f"  Length: {len(api_key)}")
    print(f"  Starts with: {api_key[:20]}...")
    print(f"  Ends with: ...{api_key[-10:]}")

print("\n=== Testing OpenAI Connection ===")

try:
    from openai import OpenAI
    
    # Create client with explicit key
    client = OpenAI(api_key=api_key)
    
    print("Client created successfully")
    print(f"Using API key: {api_key[:20]}...{api_key[-10:]}")
    
    # Test embedding
    print("\nCalling embeddings.create()...")
    response = client.embeddings.create(
        model="text-embedding-3-large",
        input="Hello, this is a test."
    )
    
    print(f"SUCCESS!")
    print(f"  Model: {response.model}")
    print(f"  Embedding dimension: {len(response.data[0].embedding)}")
    print(f"  Usage: {response.usage.total_tokens} tokens")
    
except Exception as e:
    print(f"\nERROR: {type(e).__name__}")
    print(f"  {e}")
    
    # Additional debug info
    import traceback
    print("\n=== Full traceback ===")
    traceback.print_exc()
