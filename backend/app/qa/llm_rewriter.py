"""LLM-enhanced query rewriting for multi-turn conversations.

Based on 2025 research including:
- ICR (Iterative Clarification & Rewriting) for ambiguity resolution
- Coreference resolution for pronoun/reference handling
- Query optimization for better retrieval
- Document-aware context injection for entity resolution

This module is OPTIONAL and controlled via ENABLE_LLM_QUERY_REWRITE in .env.
Disabled by default - enable only for human chat interfaces.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import get_settings
from app.prompts import get_prompt
from app.prompts.json_utils import extract_json_from_response, parse_json_strict

logger = logging.getLogger(__name__)


@dataclass
class RewriteResult:
    """Result from LLM query rewriting."""
    original_query: str
    rewritten_query: str
    search_terms: List[str] = field(default_factory=list)
    resolved_references: List[str] = field(default_factory=list)
    reasoning: str = ""
    latency_ms: float = 0.0
    used_llm: bool = False  # False if disabled, skipped, or passthrough
    error: Optional[str] = None
    
    # Token tracking for cost monitoring
    context_tokens: int = 0  # Tokens used for document context
    prompt_tokens: int = 0  # Total input tokens
    completion_tokens: int = 0  # Total output tokens
    prompt_version: str = "v1"  # Which prompt version was used
    doc_context_used: bool = False  # Whether document context was injected
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_query": self.original_query,
            "rewritten_query": self.rewritten_query,
            "search_terms": self.search_terms,
            "resolved_references": self.resolved_references,
            "reasoning": self.reasoning,
            "latency_ms": self.latency_ms,
            "used_llm": self.used_llm,
            "error": self.error,
            "context_tokens": self.context_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "prompt_version": self.prompt_version,
            "doc_context_used": self.doc_context_used,
        }


# Patterns indicating ambiguous references that need resolution
AMBIGUOUS_PATTERNS = [
    re.compile(r'\b(it|its)\b', re.IGNORECASE),
    re.compile(r'\bthat\b(?!\s+(?:is|are|was|were|the))', re.IGNORECASE),  # "that" but not "that is"
    re.compile(r'\bthis\b(?!\s+(?:is|document|fdd))', re.IGNORECASE),
    re.compile(r'\bthe\s+other\s+(?:one|fee|thing|item)\b', re.IGNORECASE),
    re.compile(r'\b(they|them|their)\b', re.IGNORECASE),
    re.compile(r'\b(same|previous|last)\s+(?:one|thing|fee|item|time)\b', re.IGNORECASE),
    re.compile(r'\bthe\s+same\s+as\b', re.IGNORECASE),
    re.compile(r'\bwhat\s+about\b', re.IGNORECASE),
]

# Patterns indicating entity ambiguity (benefit from document context)
ENTITY_AMBIGUOUS_PATTERNS = [
    re.compile(r'\bthe\s+company\b', re.IGNORECASE),
    re.compile(r'\bthe\s+franchisor\b', re.IGNORECASE),
    re.compile(r'\bthe\s+franchisee\b', re.IGNORECASE),
    re.compile(r'\bthe\s+business\b', re.IGNORECASE),
    re.compile(r'\bthe\s+organization\b', re.IGNORECASE),
]

# Patterns indicating the query is likely self-contained
SELF_CONTAINED_PATTERNS = [
    re.compile(r'\bwhat\s+is\s+the\s+\w+', re.IGNORECASE),  # "What is the X"
    re.compile(r'\bwhat\s+are\s+the\s+\w+', re.IGNORECASE),  # "What are the X"
    re.compile(r'\bhow\s+much\s+is\b', re.IGNORECASE),
    re.compile(r'\blist\s+(?:all\s+)?the\b', re.IGNORECASE),
    re.compile(r'\bwho\s+is\b', re.IGNORECASE),
]

# Patterns for section references (preserve these)
SECTION_REFERENCE_PATTERN = re.compile(r'\bItem\s+\d+\b|\bExhibit\s+[A-Z]\b', re.IGNORECASE)


class LLMQueryRewriter:
    """LLM-enhanced query rewriter for multi-turn conversations.
    
    Features:
    - Coreference resolution (pronouns -> referents)
    - Ambiguity resolution (vague -> specific)
    - Search optimization (keyword extraction)
    - Document-aware entity resolution (with v2 prompt)
    
    Controlled by ENABLE_LLM_QUERY_REWRITE setting (disabled by default).
    """
    
    def __init__(
        self,
        client: Optional[OpenAI] = None,
        enabled: Optional[bool] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        max_history: Optional[int] = None,
        use_doc_context: bool = True,
    ):
        """Initialize the LLM query rewriter.
        
        Args:
            client: OpenAI client (creates default if None)
            enabled: Override enable setting (uses config if None)
            model: Override model setting (uses config if None)
            timeout: Override timeout setting (uses config if None)
            max_history: Override max_history setting (uses config if None)
            use_doc_context: Whether to use document context for rewriting
        """
        settings = get_settings()
        
        self.client = client or OpenAI(api_key=settings.openai_api_key)
        self.enabled = enabled if enabled is not None else settings.enable_llm_query_rewrite
        self.model = model or settings.llm_rewrite_model
        self.timeout = timeout or settings.llm_rewrite_timeout
        self.max_history = max_history or settings.llm_rewrite_max_history
        self.use_doc_context = use_doc_context
        
        logger.info(
            f"[LLMRewriter] Initialized: enabled={self.enabled}, "
            f"model={self.model}, timeout={self.timeout}s, doc_context={use_doc_context}"
        )
    
    def rewrite(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        force: bool = False,
        doc_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> RewriteResult:
        """Rewrite a query using LLM if enabled and beneficial.
        
        Args:
            query: The user's current query
            chat_history: List of {"role": "user"|"assistant", "content": "..."} dicts
            force: Force LLM rewrite even if disabled
            doc_id: Document ID for context extraction (enables v2 prompt)
            db: Database session for context extraction
            
        Returns:
            RewriteResult with rewritten query and metadata
        """
        # Skip if disabled and not forced
        if not self.enabled and not force:
            logger.debug("[LLMRewriter] Disabled, passing through query")
            return self._passthrough(query, reason="Rewriting disabled")
        
        # Determine if we need document context
        needs_entity_context = self._needs_entity_context(query)
        
        # Skip if no history, no entity ambiguity, and query is self-contained (unless forced)
        if not force and not chat_history and not needs_entity_context and self._is_self_contained(query):
            logger.debug("[LLMRewriter] Query is self-contained, skipping rewrite")
            return self._passthrough(query, reason="Query is self-contained")
        
        # Get document context if available and beneficial
        doc_context = None
        if self.use_doc_context and doc_id and db and (needs_entity_context or chat_history):
            doc_context = self._get_document_context(db, doc_id)
        
        # Call LLM for rewrite
        return self._call_llm_rewrite(query, chat_history, doc_context)
    
    def _needs_entity_context(self, query: str) -> bool:
        """Check if query would benefit from document entity context.
        
        Args:
            query: The user's query
            
        Returns:
            True if query has entity ambiguity patterns
        """
        for pattern in ENTITY_AMBIGUOUS_PATTERNS:
            if pattern.search(query):
                return True
        return False
    
    def _get_document_context(self, db: Session, doc_id: str):
        """Get document context for the rewriter.
        
        Args:
            db: Database session
            doc_id: Document ID
            
        Returns:
            DocumentContext or None
        """
        try:
            from app.qa.doc_context import get_document_context
            return get_document_context(db, doc_id)
        except Exception as e:
            logger.warning(f"[LLMRewriter] Failed to get document context: {e}")
            return None
    
    def should_rewrite(self, query: str) -> bool:
        """Quick check if a query likely needs rewriting.
        
        Args:
            query: The user's query
            
        Returns:
            True if query contains ambiguous patterns
        """
        return not self._is_self_contained(query)
    
    def _is_self_contained(self, query: str) -> bool:
        """Check if a query is self-contained (no ambiguous references).
        
        Uses heuristics to detect:
        - Pronouns like "it", "they", "that"
        - Vague references like "the other one"
        - Follow-up patterns like "what about"
        
        Args:
            query: The user's query
            
        Returns:
            True if query appears self-contained
        """
        # Check for ambiguous patterns
        for pattern in AMBIGUOUS_PATTERNS:
            if pattern.search(query):
                logger.debug(f"[LLMRewriter] Found ambiguous pattern: {pattern.pattern}")
                return False
        
        # Short queries without entities are often ambiguous
        words = query.split()
        if len(words) < 4:
            # But check if it has a self-contained structure
            for pattern in SELF_CONTAINED_PATTERNS:
                if pattern.search(query):
                    return True
            return False
        
        return True
    
    def _passthrough(self, query: str, reason: str = "") -> RewriteResult:
        """Return the original query without modification.
        
        Args:
            query: The original query
            reason: Why the query was passed through
            
        Returns:
            RewriteResult with original query
        """
        return RewriteResult(
            original_query=query,
            rewritten_query=query,
            search_terms=[],
            resolved_references=[],
            reasoning=reason or "Passthrough",
            latency_ms=0.0,
            used_llm=False,
        )
    
    def _format_chat_history(
        self,
        chat_history: Optional[List[Dict[str, str]]]
    ) -> str:
        """Format chat history for the prompt.
        
        Args:
            chat_history: List of message dicts
            
        Returns:
            Formatted string for prompt
        """
        if not chat_history:
            return "(No previous conversation)"
        
        # Truncate to max_history turns
        truncated = chat_history[-self.max_history * 2:]  # *2 for user+assistant pairs
        
        lines = []
        for msg in truncated:
            role = msg.get("role", "").upper()
            content = msg.get("content", "")
            # Truncate long messages
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"{role}: {content}")
        
        return "\n".join(lines)
    
    def _call_llm_rewrite(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]],
        doc_context: Optional[Any] = None,
    ) -> RewriteResult:
        """Call LLM to rewrite the query.
        
        Args:
            query: The user's current query
            chat_history: Previous conversation turns
            doc_context: Optional DocumentContext for entity resolution
            
        Returns:
            RewriteResult with LLM-rewritten query
        """
        start_time = time.time()
        
        # Determine which prompt version to use
        use_v2 = doc_context is not None
        prompt_version = "v2" if use_v2 else "v1"
        
        try:
            # Get prompt template
            if use_v2:
                # Format document context block
                context_block = doc_context.to_prompt_block()
                system_prompt = get_prompt("query_rewrite", version="v2", document_context=context_block)
                context_tokens = doc_context.token_estimate
            else:
                system_prompt = get_prompt("query_rewrite", version="v1")
                context_tokens = 0
            
            # Format user message
            history_str = self._format_chat_history(chat_history)
            user_message = f"""CHAT HISTORY:
{history_str}

CURRENT QUERY:
{query}

Rewrite the query to be self-contained. Return JSON only."""
            
            # Call LLM
            logger.info(
                f"[LLMRewriter] Calling {self.model} for query rewrite "
                f"(prompt={prompt_version}, context_tokens={context_tokens})"
            )
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.0,  # Deterministic
                max_tokens=500,
                timeout=self.timeout,
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Extract token usage
            usage = response.usage
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else 0
            
            # Parse response
            raw_response = response.choices[0].message.content or ""
            logger.debug(f"[LLMRewriter] Raw response: {raw_response[:200]}...")
            
            # Extract and parse JSON
            json_str = extract_json_from_response(raw_response)
            parsed = parse_json_strict(json_str)
            
            if not parsed:
                logger.warning("[LLMRewriter] Failed to parse JSON, using original query")
                return RewriteResult(
                    original_query=query,
                    rewritten_query=query,
                    reasoning="JSON parse failed, using original",
                    latency_ms=latency_ms,
                    used_llm=True,
                    error="JSON parse failed",
                    context_tokens=context_tokens,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    prompt_version=prompt_version,
                    doc_context_used=use_v2,
                )
            
            rewritten = parsed.get("rewritten_query", query)
            
            logger.info(
                f"[LLMRewriter] Rewrote query in {latency_ms:.0f}ms "
                f"(tokens: {prompt_tokens}+{completion_tokens}): "
                f"'{query[:40]}...' -> '{rewritten[:40]}...'"
            )
            
            return RewriteResult(
                original_query=query,
                rewritten_query=rewritten,
                search_terms=parsed.get("search_terms", []),
                resolved_references=parsed.get("resolved_references", []),
                reasoning=parsed.get("reasoning", ""),
                latency_ms=latency_ms,
                used_llm=True,
                context_tokens=context_tokens,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                prompt_version=prompt_version,
                doc_context_used=use_v2,
            )
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"[LLMRewriter] Error: {e}, using original query")
            
            return RewriteResult(
                original_query=query,
                rewritten_query=query,
                reasoning="LLM call failed, using original",
                latency_ms=latency_ms,
                used_llm=True,
                error=str(e),
                prompt_version=prompt_version,
                doc_context_used=doc_context is not None,
            )


def get_llm_rewriter() -> LLMQueryRewriter:
    """Get a configured LLM query rewriter instance."""
    return LLMQueryRewriter()
