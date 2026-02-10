"""Tests for JSON parsing and schema validation.

Ensures all structured LLM outputs parse correctly and conform to schemas.
"""

import pytest
import json
from app.prompts.json_utils import (
    extract_json_from_response,
    parse_json_strict,
    parse_and_validate,
    PlannerOutput,
    VerifierOutput,
    SynthesizerOutput,
    RerankerOutput,
)


class TestJSONExtraction:
    """Test JSON extraction from various response formats."""
    
    def test_extract_raw_json_object(self):
        """Extract JSON object from clean response."""
        text = '{"answer": "test", "citations": []}'
        result = extract_json_from_response(text)
        assert result == text
    
    def test_extract_json_from_markdown_block(self):
        """Extract JSON from markdown code block."""
        text = '''Here is the response:

```json
{"answer": "test", "citations": []}
```

Hope this helps!'''
        result = extract_json_from_response(text)
        assert result == '{"answer": "test", "citations": []}'
    
    def test_extract_json_from_plain_code_block(self):
        """Extract JSON from plain code block (no json tag)."""
        text = '''```
{"needs_clarification": false, "sub_questions": []}
```'''
        result = extract_json_from_response(text)
        assert result == '{"needs_clarification": false, "sub_questions": []}'
    
    def test_extract_json_with_surrounding_text(self):
        """Extract JSON when surrounded by explanation."""
        text = '''I'll analyze the question and provide the answer.

{"answer": "The value is 42", "citations": [{"node_id": "abc", "page_no": 5}]}

Let me know if you need more details.'''
        result = extract_json_from_response(text)
        parsed = json.loads(result)
        assert parsed["answer"] == "The value is 42"
    
    def test_extract_json_array(self):
        """Extract JSON array."""
        text = '[{"id": "sq1", "text": "test"}]'
        result = extract_json_from_response(text)
        assert result == text
    
    def test_extract_returns_none_for_no_json(self):
        """Return None when no JSON found."""
        text = "This is just plain text with no JSON."
        result = extract_json_from_response(text)
        assert result is None
    
    def test_extract_handles_empty_input(self):
        """Handle empty input."""
        assert extract_json_from_response("") is None
        assert extract_json_from_response(None) is None


class TestJSONParsing:
    """Test JSON parsing with various inputs."""
    
    def test_parse_valid_json(self):
        """Parse valid JSON."""
        text = '{"answer": "test", "confidence": 0.9}'
        result = parse_json_strict(text)
        assert result["answer"] == "test"
        assert result["confidence"] == 0.9
    
    def test_parse_json_with_nested_objects(self):
        """Parse JSON with nested structures."""
        text = '''{"citations": [{"node_id": "abc", "page_no": 5}]}'''
        result = parse_json_strict(text)
        assert len(result["citations"]) == 1
        assert result["citations"][0]["page_no"] == 5
    
    def test_parse_invalid_json_returns_none(self):
        """Return None for invalid JSON."""
        text = '{"answer": "missing bracket"'
        result = parse_json_strict(text)
        assert result is None
    
    def test_parse_json_with_trailing_comma(self):
        """Handle trailing comma (common LLM error)."""
        # Note: Standard json.loads doesn't allow trailing commas
        # This tests that we get None for malformed JSON
        text = '{"answer": "test",}'
        result = parse_json_strict(text)
        assert result is None  # Should fail - needs repair


class TestSchemaValidation:
    """Test schema validation with Pydantic models."""
    
    def test_validate_planner_output(self):
        """Validate planner output schema."""
        text = '''{
            "needs_clarification": false,
            "sub_questions": [
                {"id": "sq1", "text": "What is X?", "why_needed": "core question", "must_answer": true}
            ]
        }'''
        result = parse_and_validate(text, PlannerOutput)
        assert result is not None
        assert result.needs_clarification == False
        assert len(result.sub_questions) == 1
    
    def test_validate_verifier_output(self):
        """Validate verifier output schema."""
        text = '''{
            "answer": "The value is 42",
            "citations": [{"node_id": "abc123", "page_no": 5}],
            "confidence": 0.85,
            "insufficient_evidence": false,
            "conflict_notes": ""
        }'''
        result = parse_and_validate(text, VerifierOutput)
        assert result is not None
        assert result.answer == "The value is 42"
        assert result.confidence == 0.85
    
    def test_validate_synthesizer_output(self):
        """Validate synthesizer output schema."""
        text = '''{
            "answer": "The combined answer is...",
            "citations": [],
            "conflicts_summary": ""
        }'''
        result = parse_and_validate(text, SynthesizerOutput)
        assert result is not None
        assert "combined" in result.answer
    
    def test_validate_reranker_output(self):
        """Validate reranker output schema."""
        text = '''{
            "ranked": [
                {"node_id": "abc", "score": 95, "must_include": true, "why": "exact match"},
                {"node_id": "def", "score": 60, "must_include": false, "why": "partial match"}
            ]
        }'''
        result = parse_and_validate(text, RerankerOutput)
        assert result is not None
        assert len(result.ranked) == 2
        assert result.ranked[0]["score"] == 95
    
    def test_validate_with_missing_optional_fields(self):
        """Validate with missing optional fields uses defaults."""
        text = '{"answer": "test"}'  # Missing optional fields
        result = parse_and_validate(text, VerifierOutput)
        assert result is not None
        assert result.answer == "test"
        assert result.confidence == 0.5  # default
        assert result.insufficient_evidence == False  # default
    
    def test_validate_fails_for_missing_required_fields(self):
        """Validation fails when required fields are missing."""
        text = '{"citations": []}'  # Missing required "answer"
        result = parse_and_validate(text, VerifierOutput)
        assert result is None


class TestRealWorldResponses:
    """Test with realistic LLM response patterns."""
    
    def test_planner_real_response(self):
        """Test realistic planner response."""
        text = '''Based on the question, I'll decompose it into sub-questions:

```json
{
  "needs_clarification": false,
  "sub_questions": [
    {
      "id": "sq1",
      "text": "What is the initial franchise fee?",
      "why_needed": "Direct answer to main question",
      "must_answer": true
    },
    {
      "id": "sq2", 
      "text": "Is the fee refundable?",
      "why_needed": "Important detail for completeness",
      "must_answer": false
    }
  ]
}
```'''
        result = parse_and_validate(text, PlannerOutput)
        assert result is not None
        assert len(result.sub_questions) == 2
    
    def test_verifier_insufficient_evidence(self):
        """Test verifier response with insufficient evidence."""
        text = '''{
            "answer": "Insufficient evidence in provided snippets.",
            "citations": [],
            "confidence": 0.0,
            "insufficient_evidence": true,
            "conflict_notes": ""
        }'''
        result = parse_and_validate(text, VerifierOutput)
        assert result is not None
        assert result.insufficient_evidence == True
        assert result.confidence == 0.0
    
    def test_verifier_with_conflict(self):
        """Test verifier response with conflicting evidence."""
        text = '''{
            "answer": "The fee is either $40,000 or $45,000 depending on the source.",
            "citations": [
                {"node_id": "abc", "page_no": 10},
                {"node_id": "def", "page_no": 15}
            ],
            "confidence": 0.6,
            "insufficient_evidence": false,
            "conflict_notes": "Page 10 states $40,000 while page 15 states $45,000"
        }'''
        result = parse_and_validate(text, VerifierOutput)
        assert result is not None
        assert len(result.citations) == 2
        assert result.conflict_notes != ""  # Has some conflict note


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
