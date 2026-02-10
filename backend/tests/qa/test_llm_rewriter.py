"""Tests for LLM Query Rewriter module.

Tests cover:
1. Unit tests (no LLM calls) - heuristics, passthrough, history formatting
2. Integration tests (mocked LLM) - coreference, pronoun, vague followup
3. Live tests (optional, real LLM) - full conversation flow

Run with: pytest tests/qa/test_llm_rewriter.py -v
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import asdict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.qa.llm_rewriter import (
    LLMQueryRewriter,
    RewriteResult,
    AMBIGUOUS_PATTERNS,
    SELF_CONTAINED_PATTERNS,
)


# =============================================================================
# MULTI-TURN CONVERSATION TEST FIXTURES
# =============================================================================

MULTI_TURN_CONVERSATIONS = [
    {
        "name": "fee_followup",
        "description": "User asks about fees, then follows up with pronouns",
        "turns": [
            {
                "user": "What is the initial franchise fee?",
                "assistant": "The initial franchise fee is $45,000 according to Item 5 of the FDD.",
                "next_query": "And what about the other fees?",
                "expected_rewrite": "What are the other fees besides the initial franchise fee?",
                "expected_references": ["the other -> other fees besides initial"]
            },
            {
                "user": "And what about the other fees?",
                "assistant": "There are several recurring fees including a 5% royalty and advertising fees.",
                "next_query": "Is that refundable?",
                "expected_rewrite": "Is the initial franchise fee refundable?",
                "expected_references": ["that -> initial franchise fee"]
            },
        ]
    },
    {
        "name": "pronoun_resolution",
        "description": "User discusses an entity and uses pronouns",
        "turns": [
            {
                "user": "Tell me about Rhino Linings",
                "assistant": "Rhino Linings is a partnership that provides protective coating products. The franchisor has a licensing agreement with them.",
                "next_query": "What products do they offer?",
                "expected_rewrite": "What products does Rhino Linings offer?",
                "expected_references": ["they -> Rhino Linings"]
            },
        ]
    },
    {
        "name": "vague_reference",
        "description": "User uses vague references like 'the minimum'",
        "turns": [
            {
                "user": "What's the royalty percentage?",
                "assistant": "The royalty is 5% of gross sales, with a minimum weekly royalty of $400.",
                "next_query": "the minimum for that",
                "expected_rewrite": "What is the minimum weekly royalty amount?",
                "expected_references": ["that -> royalty", "the minimum -> minimum weekly royalty"]
            },
        ]
    },
    {
        "name": "territory_followup",
        "description": "Multi-hop conversation about territory",
        "turns": [
            {
                "user": "Do I get an exclusive territory?",
                "assistant": "Yes, franchisees receive a protected territory based on population and geography.",
                "next_query": "How big is it?",
                "expected_rewrite": "How big is the exclusive/protected territory?",
                "expected_references": ["it -> territory"]
            },
            {
                "user": "How big is it?",
                "assistant": "The territory size varies but is typically based on a minimum population of 50,000.",
                "next_query": "Can they change it?",
                "expected_rewrite": "Can the franchisor change the territory?",
                "expected_references": ["they -> franchisor", "it -> territory"]
            },
        ]
    },
    {
        "name": "training_discussion",
        "description": "Conversation about training requirements",
        "turns": [
            {
                "user": "What training is required?",
                "assistant": "Franchisees must complete an initial training program of approximately 2 weeks.",
                "next_query": "Where does that take place?",
                "expected_rewrite": "Where does the franchisee training take place?",
                "expected_references": ["that -> training"]
            },
        ]
    },
]

# Self-contained queries that should NOT be rewritten
SELF_CONTAINED_QUERIES = [
    "What is the initial franchise fee?",
    "What are the royalty percentages in Item 6?",
    "List all state-specific addenda",
    "Who is the Chairman of the Board?",
    "How much is the estimated initial investment?",
    "What trademarks does Ziebart own?",
]

# Ambiguous queries that SHOULD be flagged for rewriting
AMBIGUOUS_QUERIES = [
    ("Is it refundable?", ["it"]),
    ("What about the other one?", ["the other one"]),
    ("Tell me more about that", ["that"]),
    ("They mentioned something about fees", ["they"]),
    ("What's the minimum for this?", ["this"]),
    ("the same as last time", ["same", "last"]),
]


# =============================================================================
# UNIT TESTS (No LLM calls)
# =============================================================================

class TestSelfContainedDetection:
    """Test the _is_self_contained() heuristic."""
    
    def test_self_contained_queries_detected(self):
        """Self-contained queries should be detected as such."""
        rewriter = LLMQueryRewriter(enabled=False)
        
        for query in SELF_CONTAINED_QUERIES:
            assert rewriter._is_self_contained(query), f"Query should be self-contained: {query}"
    
    def test_ambiguous_queries_detected(self):
        """Ambiguous queries should NOT be detected as self-contained."""
        rewriter = LLMQueryRewriter(enabled=False)
        
        for query, patterns in AMBIGUOUS_QUERIES:
            assert not rewriter._is_self_contained(query), f"Query should be ambiguous: {query}"
    
    def test_short_queries_flagged(self):
        """Very short queries without clear structure should be flagged."""
        rewriter = LLMQueryRewriter(enabled=False)
        
        short_queries = ["the fees", "costs?", "how much"]
        for query in short_queries:
            assert not rewriter._is_self_contained(query), f"Short query should be flagged: {query}"
    
    def test_patterns_coverage(self):
        """Verify AMBIGUOUS_PATTERNS catch expected cases."""
        test_cases = [
            ("Is it refundable?", True),
            ("What does that mean?", True),
            ("What about the other fee?", True),
            ("Do they offer financing?", True),
            ("What is the franchise fee?", False),  # Self-contained
        ]
        
        for query, should_match in test_cases:
            matched = any(p.search(query) for p in AMBIGUOUS_PATTERNS)
            assert matched == should_match, f"Pattern match mismatch for: {query}"


class TestPassthrough:
    """Test passthrough behavior when rewriting is disabled."""
    
    def test_passthrough_when_disabled(self):
        """When disabled, queries should pass through unchanged."""
        rewriter = LLMQueryRewriter(enabled=False)
        
        query = "Is it refundable?"
        result = rewriter.rewrite(query)
        
        assert result.original_query == query
        assert result.rewritten_query == query
        assert result.used_llm is False
        assert result.latency_ms == 0.0
    
    def test_passthrough_self_contained_no_history(self):
        """Self-contained queries without history should pass through."""
        rewriter = LLMQueryRewriter(enabled=True)
        
        query = "What is the initial franchise fee?"
        # Don't call LLM - use mock to ensure no call
        with patch.object(rewriter, '_call_llm_rewrite') as mock_call:
            result = rewriter.rewrite(query, chat_history=None)
        
        mock_call.assert_not_called()
        assert result.rewritten_query == query
        assert result.used_llm is False
    
    def test_force_overrides_disabled(self):
        """force=True should attempt rewrite even when disabled."""
        rewriter = LLMQueryRewriter(enabled=False)
        
        query = "What is the franchise fee?"
        
        # Mock the LLM call
        with patch.object(rewriter, '_call_llm_rewrite') as mock_call:
            mock_call.return_value = RewriteResult(
                original_query=query,
                rewritten_query=query,
                used_llm=True,
            )
            result = rewriter.rewrite(query, force=True)
        
        mock_call.assert_called_once()
        assert result.used_llm is True


class TestChatHistoryFormatting:
    """Test chat history formatting and truncation."""
    
    def test_empty_history(self):
        """Empty history should return placeholder text."""
        rewriter = LLMQueryRewriter(enabled=False)
        
        result = rewriter._format_chat_history(None)
        assert result == "(No previous conversation)"
        
        result = rewriter._format_chat_history([])
        assert result == "(No previous conversation)"
    
    def test_history_formatting(self):
        """History should be formatted as USER:/ASSISTANT: lines."""
        rewriter = LLMQueryRewriter(enabled=False)
        
        history = [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Answer 1"},
            {"role": "user", "content": "Question 2"},
            {"role": "assistant", "content": "Answer 2"},
        ]
        
        result = rewriter._format_chat_history(history)
        
        assert "USER: Question 1" in result
        assert "ASSISTANT: Answer 1" in result
        assert "USER: Question 2" in result
        assert "ASSISTANT: Answer 2" in result
    
    def test_history_truncation(self):
        """History should be truncated to max_history turns."""
        rewriter = LLMQueryRewriter(enabled=False, max_history=2)
        
        # Create 10 turns (20 messages)
        history = []
        for i in range(10):
            history.append({"role": "user", "content": f"Question {i}"})
            history.append({"role": "assistant", "content": f"Answer {i}"})
        
        result = rewriter._format_chat_history(history)
        
        # Should only have last 2 turns (4 messages)
        assert "Question 8" in result
        assert "Question 9" in result
        assert "Question 0" not in result  # Older messages truncated
    
    def test_long_message_truncation(self):
        """Long messages should be truncated with '...'."""
        rewriter = LLMQueryRewriter(enabled=False)
        
        long_content = "A" * 1000
        history = [{"role": "user", "content": long_content}]
        
        result = rewriter._format_chat_history(history)
        
        assert "..." in result
        assert len(result) < len(long_content)


# =============================================================================
# INTEGRATION TESTS (Mocked LLM)
# =============================================================================

class TestCoreferenceResolution:
    """Test coreference resolution with mocked LLM responses."""
    
    def _create_mock_response(self, rewritten: str, references: list, reasoning: str):
        """Create a mock OpenAI response."""
        json_content = json.dumps({
            "rewritten_query": rewritten,
            "search_terms": rewritten.lower().split()[:5],
            "resolved_references": references,
            "reasoning": reasoning,
        })
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json_content
        return mock_response
    
    def test_pronoun_it_resolution(self):
        """'it' should be resolved to the referent from history."""
        rewriter = LLMQueryRewriter(enabled=True)
        
        history = [
            {"role": "user", "content": "What is the initial franchise fee?"},
            {"role": "assistant", "content": "The initial franchise fee is $45,000."},
        ]
        query = "Is it refundable?"
        
        mock_response = self._create_mock_response(
            rewritten="Is the initial franchise fee refundable?",
            references=["it -> initial franchise fee"],
            reasoning="Resolved 'it' to 'initial franchise fee' from context"
        )
        
        with patch.object(rewriter.client.chat.completions, 'create', return_value=mock_response):
            result = rewriter.rewrite(query, chat_history=history)
        
        assert result.used_llm is True
        assert "franchise fee" in result.rewritten_query.lower()
        assert "refundable" in result.rewritten_query.lower()
        assert len(result.resolved_references) > 0
    
    def test_pronoun_they_resolution(self):
        """'they' should be resolved to the entity from history."""
        rewriter = LLMQueryRewriter(enabled=True)
        
        history = [
            {"role": "user", "content": "Tell me about Rhino Linings"},
            {"role": "assistant", "content": "Rhino Linings is a partnership..."},
        ]
        query = "What products do they offer?"
        
        mock_response = self._create_mock_response(
            rewritten="What products does Rhino Linings offer?",
            references=["they -> Rhino Linings"],
            reasoning="Resolved 'they' to 'Rhino Linings' from context"
        )
        
        with patch.object(rewriter.client.chat.completions, 'create', return_value=mock_response):
            result = rewriter.rewrite(query, chat_history=history)
        
        assert result.used_llm is True
        assert "rhino linings" in result.rewritten_query.lower()
    
    def test_vague_followup_resolution(self):
        """Vague followups like 'the minimum' should be expanded."""
        rewriter = LLMQueryRewriter(enabled=True)
        
        history = [
            {"role": "user", "content": "What's the royalty?"},
            {"role": "assistant", "content": "The royalty is 5% with a minimum weekly royalty of $400."},
        ]
        query = "the minimum for that"
        
        mock_response = self._create_mock_response(
            rewritten="What is the minimum weekly royalty amount?",
            references=["that -> royalty", "the minimum -> minimum weekly royalty"],
            reasoning="Expanded vague reference to specific royalty minimum"
        )
        
        with patch.object(rewriter.client.chat.completions, 'create', return_value=mock_response):
            result = rewriter.rewrite(query, chat_history=history)
        
        assert result.used_llm is True
        assert "minimum" in result.rewritten_query.lower()
        assert "royalty" in result.rewritten_query.lower()


class TestMultiTurnConversations:
    """Test full multi-turn conversation scenarios."""
    
    def _create_mock_response(self, rewritten: str, references: list):
        """Create a mock OpenAI response."""
        json_content = json.dumps({
            "rewritten_query": rewritten,
            "search_terms": rewritten.lower().split()[:5],
            "resolved_references": references,
            "reasoning": "Resolved references from context",
        })
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json_content
        return mock_response
    
    @pytest.mark.parametrize("conversation", MULTI_TURN_CONVERSATIONS, ids=lambda c: c["name"])
    def test_conversation_flow(self, conversation):
        """Test each multi-turn conversation scenario."""
        rewriter = LLMQueryRewriter(enabled=True)
        
        for turn in conversation["turns"]:
            # Build history up to this turn
            history = [
                {"role": "user", "content": turn["user"]},
                {"role": "assistant", "content": turn["assistant"]},
            ]
            
            query = turn["next_query"]
            expected = turn["expected_rewrite"]
            
            mock_response = self._create_mock_response(
                rewritten=expected,
                references=turn.get("expected_references", [])
            )
            
            with patch.object(rewriter.client.chat.completions, 'create', return_value=mock_response):
                result = rewriter.rewrite(query, chat_history=history)
            
            assert result.used_llm is True
            assert result.rewritten_query == expected, (
                f"Conversation '{conversation['name']}': "
                f"Expected '{expected}' but got '{result.rewritten_query}'"
            )


class TestErrorHandling:
    """Test error handling and fallback behavior."""
    
    def test_llm_timeout_fallback(self):
        """On timeout, should fall back to original query."""
        rewriter = LLMQueryRewriter(enabled=True)
        
        query = "Is it refundable?"
        history = [{"role": "user", "content": "What is the fee?"}]
        
        with patch.object(rewriter.client.chat.completions, 'create', side_effect=Exception("Timeout")):
            result = rewriter.rewrite(query, chat_history=history)
        
        assert result.rewritten_query == query
        assert result.error is not None
        assert "Timeout" in result.error
    
    def test_invalid_json_fallback(self):
        """On invalid JSON response, should fall back to original query."""
        rewriter = LLMQueryRewriter(enabled=True)
        
        query = "Is it refundable?"
        history = [{"role": "user", "content": "What is the fee?"}]
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is not valid JSON"
        
        with patch.object(rewriter.client.chat.completions, 'create', return_value=mock_response):
            result = rewriter.rewrite(query, chat_history=history)
        
        assert result.rewritten_query == query
        assert result.error is not None


# =============================================================================
# LIVE TESTS (Optional, requires OpenAI API key)
# =============================================================================

@pytest.mark.skipif(
    not pytest.importorskip("openai", reason="OpenAI not installed"),
    reason="OpenAI API required for live tests"
)
class TestLiveRewriting:
    """Live tests with real LLM calls. Skipped unless --live flag is passed."""
    
    @pytest.fixture
    def live_rewriter(self):
        """Create a rewriter configured for live testing."""
        return LLMQueryRewriter(enabled=True, timeout=10)
    
    @pytest.mark.skip(reason="Requires OpenAI API key and --live flag")
    def test_live_coreference_resolution(self, live_rewriter):
        """Live test: resolve coreference in multi-turn conversation."""
        history = [
            {"role": "user", "content": "What is the initial franchise fee?"},
            {"role": "assistant", "content": "The initial franchise fee is $45,000 according to the FDD."},
        ]
        query = "Is it refundable?"
        
        result = live_rewriter.rewrite(query, chat_history=history, force=True)
        
        assert result.used_llm is True
        assert "franchise fee" in result.rewritten_query.lower()
        assert "refundable" in result.rewritten_query.lower()
        print(f"\nLive rewrite: '{query}' -> '{result.rewritten_query}'")
        print(f"Resolved: {result.resolved_references}")


# =============================================================================
# DOCUMENT CONTEXT TESTS
# =============================================================================

class TestDocumentContext:
    """Test document context extraction and integration."""
    
    def test_entity_ambiguity_detection(self):
        """Queries with 'the company' should be flagged for context."""
        rewriter = LLMQueryRewriter(enabled=True)
        
        entity_queries = [
            "What products does the company offer?",
            "When was the franchisor established?",
            "How many locations does the business have?",
        ]
        
        for query in entity_queries:
            assert rewriter._needs_entity_context(query), f"Should need entity context: {query}"
    
    def test_no_entity_ambiguity_detection(self):
        """Queries with specific names should not need entity context."""
        rewriter = LLMQueryRewriter(enabled=True)
        
        specific_queries = [
            "What is the initial franchise fee?",
            "What products does Ziebart offer?",
            "Tell me about Item 5",
        ]
        
        for query in specific_queries:
            assert not rewriter._needs_entity_context(query), f"Should not need entity context: {query}"
    
    def test_rewrite_result_has_token_tracking(self):
        """RewriteResult should have token tracking fields."""
        result = RewriteResult(
            original_query="test",
            rewritten_query="test",
        )
        
        assert hasattr(result, 'context_tokens')
        assert hasattr(result, 'prompt_tokens')
        assert hasattr(result, 'completion_tokens')
        assert hasattr(result, 'prompt_version')
        assert hasattr(result, 'doc_context_used')
    
    def test_rewrite_result_to_dict_includes_tokens(self):
        """to_dict() should include token tracking fields."""
        result = RewriteResult(
            original_query="test",
            rewritten_query="test",
            context_tokens=150,
            prompt_tokens=1200,
            completion_tokens=100,
            prompt_version="v2",
            doc_context_used=True,
        )
        
        d = result.to_dict()
        assert d["context_tokens"] == 150
        assert d["prompt_tokens"] == 1200
        assert d["completion_tokens"] == 100
        assert d["prompt_version"] == "v2"
        assert d["doc_context_used"] is True


class TestDocumentContextProvider:
    """Test the DocumentContext provider module."""
    
    def test_document_context_dataclass(self):
        """DocumentContext should have expected fields."""
        from app.qa.doc_context import DocumentContext
        
        ctx = DocumentContext(
            doc_id="test-doc-123",
            doc_title="Test Document",
            doc_type="fdd",
            year=2025,
            primary_entity="Test Company Inc",
            key_entities=["Product A", "Location B"],
            sections=["Item 1", "Item 5", "Exhibit A"],
            domain_terms=["franchise fee", "royalty"],
        )
        
        assert ctx.doc_id == "test-doc-123"
        assert ctx.doc_type == "fdd"
        assert ctx.primary_entity == "Test Company Inc"
    
    def test_document_context_to_prompt_block(self):
        """to_prompt_block() should format context for LLM."""
        from app.qa.doc_context import DocumentContext
        
        ctx = DocumentContext(
            doc_id="test-doc-123",
            doc_title="Ziebart FDD",
            doc_type="fdd",
            year=2025,
            primary_entity="Ziebart International",
            key_entities=["Rhino Linings", "Z-Guard"],
            sections=["Items 1-23", "Exhibits A-H"],
        )
        
        block = ctx.to_prompt_block()
        
        assert "Ziebart FDD" in block
        assert "FDD" in block
        assert "2025" in block
        assert "Ziebart International" in block
        assert "Rhino Linings" in block
    
    def test_document_context_expiration(self):
        """Context should correctly report expiration."""
        from app.qa.doc_context import DocumentContext
        from datetime import datetime, timedelta, timezone
        
        # Fresh context should not be expired
        ctx = DocumentContext(doc_id="test", extracted_at=datetime.now(timezone.utc))
        assert not ctx.is_expired()
        
        # Old context should be expired
        old_ctx = DocumentContext(
            doc_id="test",
            extracted_at=datetime.now(timezone.utc) - timedelta(hours=2)
        )
        assert old_ctx.is_expired()
    
    def test_context_cache_operations(self):
        """Cache should store and retrieve contexts."""
        from app.qa.doc_context import DocumentContextCache, DocumentContext
        
        cache = DocumentContextCache(max_size=3)
        
        # Put and get
        ctx1 = DocumentContext(doc_id="doc1", doc_title="Doc 1")
        cache.put(ctx1)
        retrieved = cache.get("doc1")
        assert retrieved is not None
        assert retrieved.doc_title == "Doc 1"
        
        # Miss
        assert cache.get("nonexistent") is None
    
    def test_context_cache_eviction(self):
        """Cache should evict oldest when at capacity."""
        from app.qa.doc_context import DocumentContextCache, DocumentContext
        import time
        
        cache = DocumentContextCache(max_size=2)
        
        ctx1 = DocumentContext(doc_id="doc1")
        cache.put(ctx1)
        time.sleep(0.01)
        
        ctx2 = DocumentContext(doc_id="doc2")
        cache.put(ctx2)
        time.sleep(0.01)
        
        # This should evict doc1
        ctx3 = DocumentContext(doc_id="doc3")
        cache.put(ctx3)
        
        assert cache.get("doc1") is None  # Evicted
        assert cache.get("doc2") is not None
        assert cache.get("doc3") is not None


class TestContextAwareRewriting:
    """Test rewriting with document context."""
    
    def _create_mock_response_with_usage(self, rewritten: str, references: list):
        """Create a mock OpenAI response with token usage."""
        json_content = json.dumps({
            "rewritten_query": rewritten,
            "search_terms": rewritten.lower().split()[:5],
            "resolved_references": references,
            "reasoning": "Resolved entity from document context",
        })
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json_content
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 1200
        mock_response.usage.completion_tokens = 100
        return mock_response
    
    def test_entity_resolution_with_context(self):
        """'the company' should resolve to primary entity when context provided."""
        from app.qa.doc_context import DocumentContext
        
        rewriter = LLMQueryRewriter(enabled=True, use_doc_context=True)
        
        query = "What products does the company offer?"
        
        mock_context = DocumentContext(
            doc_id="test-doc",
            doc_title="Ziebart FDD",
            doc_type="fdd",
            year=2025,
            primary_entity="Ziebart International",
            key_entities=["Rhino Linings"],
            token_estimate=150,
        )
        
        mock_response = self._create_mock_response_with_usage(
            rewritten="What products does Ziebart International offer?",
            references=["the company -> Ziebart International"]
        )
        
        with patch.object(rewriter, '_get_document_context', return_value=mock_context):
            with patch.object(rewriter.client.chat.completions, 'create', return_value=mock_response):
                result = rewriter.rewrite(query, doc_id="test-doc", db=MagicMock())
        
        assert result.used_llm is True
        assert result.doc_context_used is True
        assert result.prompt_version == "v2"
        assert "Ziebart" in result.rewritten_query
    
    def test_no_context_uses_v1_prompt(self):
        """Without document context, should use v1 prompt."""
        rewriter = LLMQueryRewriter(enabled=True, use_doc_context=True)
        
        query = "Is it refundable?"
        history = [{"role": "user", "content": "What is the fee?"}]
        
        mock_response = self._create_mock_response_with_usage(
            rewritten="Is the franchise fee refundable?",
            references=["it -> franchise fee"]
        )
        
        # No doc_id provided, should use v1
        with patch.object(rewriter.client.chat.completions, 'create', return_value=mock_response):
            result = rewriter.rewrite(query, chat_history=history)
        
        assert result.used_llm is True
        assert result.doc_context_used is False
        assert result.prompt_version == "v1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
