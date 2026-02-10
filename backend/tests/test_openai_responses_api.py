"""Test OpenAI Responses API with GPT-5.2."""

import os
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Ensure we're loading from the correct .env file
env_path = Path(__file__).parent.parent / ".env"
print(f"Loading .env from: {env_path}")

from dotenv import load_dotenv
load_dotenv(env_path, override=True)

print("\n=== Testing OpenAI Responses API (GPT-5.2) ===\n")

try:
    from app.llm.openai_client import OpenAIClient
    
    # Initialize client
    print("1. Initializing OpenAIClient...")
    client = OpenAIClient()
    print(f"   ✓ Client initialized with model: {client.model}")
    
    # Test basic answer generation
    print("\n2. Testing generate_answer() with default parameters...")
    test_context = """
    The study examined the effects of temperature on plant growth.
    Results showed that plants grew best at 22°C [study_001:3].
    Figure 1 [Figure 1:4] illustrates the growth patterns.
    """
    test_question = "What temperature is best for plant growth?"
    
    result = client.generate_answer(
        context=test_context,
        question=test_question
    )
    
    print(f"   ✓ Answer generated successfully")
    print(f"   - Answer length: {len(result.answer)} chars")
    print(f"   - Citations found: {len(result.citations)}")
    print(f"   - Model: {result.model_id}")
    print(f"   - Tokens: {result.total_tokens} (input: {result.prompt_tokens}, output: {result.completion_tokens})")
    print(f"   - Generation time: {result.generation_time_ms:.0f}ms")
    print(f"\n   Answer preview: {result.answer[:200]}...")
    
    if result.citations:
        print(f"\n   Citations:")
        for cit in result.citations:
            print(f"     - {cit.node_id}:{cit.page_no} ({cit.label})")
    
    # Test with different reasoning_effort
    print("\n3. Testing with reasoning_effort='low'...")
    result2 = client.generate_answer(
        context=test_context,
        question=test_question,
        reasoning_effort="low"
    )
    print(f"   ✓ Answer generated with reasoning_effort='low'")
    print(f"   - Tokens: {result2.total_tokens}")
    
    # Test with verbosity
    print("\n4. Testing with verbosity='medium'...")
    result3 = client.generate_answer(
        context=test_context,
        question=test_question,
        verbosity="medium"
    )
    print(f"   ✓ Answer generated with verbosity='medium'")
    print(f"   - Answer length: {len(result3.answer)} chars")
    
    # Test with temperature (should work when reasoning_effort='none')
    print("\n5. Testing with temperature=0.5 (reasoning_effort='none')...")
    result4 = client.generate_answer(
        context=test_context,
        question=test_question,
        temperature=0.5,
        reasoning_effort="none"
    )
    print(f"   ✓ Answer generated with temperature=0.5")
    print(f"   - Tokens: {result4.total_tokens}")
    
    print("\n" + "="*60)
    print("✓ ALL TESTS PASSED!")
    print("="*60)
    
except Exception as e:
    print(f"\n✗ ERROR: {type(e).__name__}")
    print(f"   {e}")
    
    import traceback
    print("\n=== Full traceback ===")
    traceback.print_exc()
    sys.exit(1)
