"""Tests for citation coverage in QA responses.

Ensures answers are properly grounded with citations.
"""

import pytest
import re
from typing import List, Tuple


def extract_citations(text: str) -> List[str]:
    """Extract citations from answer text.
    
    Looks for patterns like:
    - [node_id:PAGE]
    - [LABEL:PAGE]
    - [seed:PAGE]
    - [adjacent:PAGE]
    """
    # Match various citation formats
    patterns = [
        r'\[([a-f0-9]{32}):(\d+)\]',           # node_id:page
        r'\[seed:(\d+)\]',                      # seed:page
        r'\[adjacent:(\d+)\]',                  # adjacent:page
        r'\[(Figure \d+):(\d+)\]',              # Figure X:page
        r'\[(Table \d+):(\d+)\]',               # Table X:page
        r'\[([^:\]]+):(\d+)\]',                 # generic label:page
    ]
    
    citations = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        citations.extend(matches)
    
    return citations


def count_factual_sentences(text: str) -> int:
    """Count sentences that likely contain factual claims.
    
    A sentence is considered factual if it contains:
    - Numbers (quantities, percentages, dates)
    - Named entities (proper nouns)
    - Specific claims (is, was, are, has, have)
    
    Excludes:
    - Questions
    - Meta-statements ("I cannot find...", "According to...")
    """
    # Split into sentences
    sentences = re.split(r'[.!?]+', text)
    
    factual_count = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        # Skip questions
        if sentence.endswith('?') or sentence.startswith(('What', 'How', 'Why', 'When', 'Where', 'Who')):
            continue
        
        # Skip meta-statements
        meta_phrases = [
            "I cannot find",
            "insufficient information",
            "not enough context",
            "according to the",
            "based on",
            "as mentioned",
        ]
        if any(phrase.lower() in sentence.lower() for phrase in meta_phrases):
            continue
        
        # Check for factual indicators
        has_numbers = bool(re.search(r'\d+', sentence))
        has_specific_claim = bool(re.search(
            r'\b(is|are|was|were|has|have|had|costs?|equals?|requires?)\b',
            sentence.lower()
        ))
        has_proper_noun = bool(re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', sentence))
        
        if has_numbers or has_specific_claim or has_proper_noun:
            factual_count += 1
    
    return max(1, factual_count)  # At least 1 to avoid division by zero


def calculate_citation_coverage(text: str) -> Tuple[float, int, int]:
    """Calculate citation coverage for an answer.
    
    Returns:
        (coverage_ratio, cited_count, factual_count)
    """
    citations = extract_citations(text)
    factual_sentences = count_factual_sentences(text)
    
    # Count paragraphs/sentences with citations
    paragraphs = text.split('\n\n')
    cited_paragraphs = sum(1 for p in paragraphs if extract_citations(p))
    
    # For simplicity, treat each citation as covering ~1 factual claim
    coverage = min(1.0, len(citations) / factual_sentences)
    
    return coverage, len(citations), factual_sentences


class TestCitationExtraction:
    """Test citation extraction from various formats."""
    
    def test_extract_node_id_citation(self):
        """Extract node_id:page format."""
        text = "The fee is $45,000 [abc123def456789012345678901234:14]"
        citations = extract_citations(text)
        assert len(citations) > 0
    
    def test_extract_seed_citation(self):
        """Extract seed:page format."""
        text = "The answer is yes [seed:5] and confirmed [seed:10]"
        citations = extract_citations(text)
        assert len(citations) >= 2  # At least 2 seed citations
    
    def test_extract_figure_citation(self):
        """Extract Figure X:page format."""
        text = "As shown in [Figure 1:15], the data indicates..."
        citations = extract_citations(text)
        assert len(citations) >= 1
    
    def test_extract_table_citation(self):
        """Extract Table X:page format."""
        text = "See [Table 2:7] for details"
        citations = extract_citations(text)
        assert len(citations) >= 1
    
    def test_extract_multiple_citations(self):
        """Extract multiple citations from paragraph."""
        text = """The initial fee is $45,000 [seed:14; seed:82]. 
        This includes training [adjacent:15] and is non-refundable [seed:14]."""
        citations = extract_citations(text)
        assert len(citations) >= 3


class TestFactualSentenceCounting:
    """Test identification of factual sentences."""
    
    def test_count_sentence_with_number(self):
        """Sentence with number is factual."""
        text = "The fee is $45,000."
        count = count_factual_sentences(text)
        assert count >= 1
    
    def test_count_sentence_with_claim(self):
        """Sentence with claim verb is factual."""
        text = "The program requires completion within 30 days."
        count = count_factual_sentences(text)
        assert count >= 1
    
    def test_skip_question(self):
        """Questions are not counted."""
        text = "What is the fee?"
        count = count_factual_sentences(text)
        # Should be 1 (minimum) since no factual content
        assert count == 1
    
    def test_skip_meta_statement(self):
        """Meta-statements are not counted."""
        text = "I cannot find sufficient information to answer this question."
        count = count_factual_sentences(text)
        assert count == 1  # minimum


class TestCitationCoverage:
    """Test citation coverage calculations."""
    
    def test_high_coverage_answer(self):
        """Answer with good citation coverage."""
        text = """The initial franchise fee is $45,000 [seed:14]. 
        This fee is paid in a lump sum [seed:14] and is non-refundable [seed:82]. 
        Training is included [adjacent:15]."""
        
        coverage, cited, factual = calculate_citation_coverage(text)
        assert coverage >= 0.75  # 75%+ coverage
        assert cited >= 3
    
    def test_low_coverage_answer(self):
        """Answer with poor citation coverage."""
        text = """The franchise fee is approximately $45,000. 
        This includes initial training and support services.
        The program takes about 30 days to complete.
        There are additional ongoing fees as well."""
        
        coverage, cited, factual = calculate_citation_coverage(text)
        assert coverage < 0.5  # Less than 50% coverage
        assert cited == 0
    
    def test_perfect_coverage(self):
        """Answer where every claim is cited."""
        text = "The fee is $45,000 [seed:14]."
        coverage, cited, factual = calculate_citation_coverage(text)
        assert coverage >= 0.9


class TestRealWorldAnswers:
    """Test with realistic QA system outputs."""
    
    def test_good_fdd_answer(self):
        """Test a good FDD-style answer with citations."""
        text = """The initial franchise fee for a Ziebart® franchise is **$45,000**, 
        paid in a lump sum when you sign the Franchise Agreement, and it is 
        **non-refundable** [seed:14; seed:82].
        
        This fee includes initial training [adjacent:15] and the right to use 
        the Ziebart trademarks [seed:16]."""
        
        coverage, cited, factual = calculate_citation_coverage(text)
        assert coverage >= 0.5  # At least 50% coverage
        assert cited >= 2
    
    def test_insufficient_info_answer(self):
        """Test an abstention answer (should have low factual count)."""
        text = """I cannot find sufficient information in the provided context 
        to answer this question about environmental compliance requirements."""
        
        coverage, cited, factual = calculate_citation_coverage(text)
        # Should not fail coverage because factual count is low
        assert factual <= 2


class TestCitationRequirements:
    """Verify prompts require proper citations."""
    
    def test_qa_prompt_requires_citations(self):
        """QA prompt explicitly requires citations."""
        from app.prompts import get_prompt
        
        prompt = get_prompt("qa_answer")
        prompt_lower = prompt.lower()
        
        assert "cite" in prompt_lower or "citation" in prompt_lower
        assert "[" in prompt  # Shows citation format
    
    def test_verifier_prompt_requires_citations(self):
        """Verifier prompt requires citations."""
        from app.prompts import get_prompt
        
        prompt = get_prompt("verifier", sub_question="test", snippets_text="test")
        prompt_lower = prompt.lower()
        
        assert "cite" in prompt_lower
        assert "must" in prompt_lower


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
