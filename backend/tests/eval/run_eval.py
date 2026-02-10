#!/usr/bin/env python
"""Evaluation harness for Graph RAG retrieval.

Runs queries against fixtures and measures:
- Evidence recall@K (did we retrieve the expected figure/table?)
- Chunk keyword hit rate
- Edge coverage (were expected edge types used?)

Usage:
    python -m tests.eval.run_eval                    # Run full evaluation
    python -m tests.eval.run_eval --query q1        # Run specific query
    python -m tests.eval.run_eval --compare          # Compare with baseline
"""

import json
import sys
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
QUERIES_FILE = Path(__file__).parent / "queries.json"


@dataclass
class RetrievalResult:
    """Result from retrieval."""
    query_id: str
    retrieved_nodes: List[Dict[str, Any]]
    edges_traversed: List[str]
    context_text: str
    execution_time_ms: float


@dataclass
class EvalResult:
    """Evaluation result for a single query."""
    query_id: str
    query_text: str
    fixture_id: str
    difficulty: str
    
    # Recall metrics
    evidence_recall_at_1: bool = False
    evidence_recall_at_3: bool = False
    evidence_recall_at_5: bool = False
    evidence_recall_at_10: bool = False
    
    # Keyword metrics
    keyword_hits: int = 0
    keyword_total: int = 0
    keyword_hit_rate: float = 0.0
    
    # Edge metrics
    edge_coverage: float = 0.0
    edges_expected: List[str] = field(default_factory=list)
    edges_found: List[str] = field(default_factory=list)
    
    # Additional info
    notes: str = ""
    error: Optional[str] = None


@dataclass
class EvalSummary:
    """Summary of evaluation run."""
    total_queries: int = 0
    
    # Recall metrics
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    recall_at_10: float = 0.0
    
    # Keyword metrics
    avg_keyword_hit_rate: float = 0.0
    
    # Edge metrics
    avg_edge_coverage: float = 0.0
    
    # By difficulty
    easy_recall: float = 0.0
    medium_recall: float = 0.0
    hard_recall: float = 0.0
    
    results: List[EvalResult] = field(default_factory=list)


class MockRetriever:
    """Mock retriever for testing without full system."""
    
    def __init__(self, use_graph_expansion: bool = True):
        self.use_graph_expansion = use_graph_expansion
    
    def retrieve(
        self,
        query: str,
        fixture_id: str,
        top_k: int = 10
    ) -> RetrievalResult:
        """Mock retrieval for testing.
        
        In real implementation, this would:
        1. Embed the query
        2. Search Milvus for similar chunks
        3. Expand graph context
        4. Pack and return context
        """
        # Load fixture
        fixture_path = FIXTURES_DIR / f"{fixture_id}.txt"
        
        if not fixture_path.exists():
            return RetrievalResult(
                query_id="",
                retrieved_nodes=[],
                edges_traversed=[],
                context_text="",
                execution_time_ms=0
            )
        
        content = fixture_path.read_text()
        
        # Mock node detection from content
        nodes = []
        edges = []
        
        # Detect figures
        import re
        fig_matches = re.findall(r'(Figure|Fig\.?)\s*(\d+(?:\.\d+)?)', content)
        for _, num in fig_matches:
            label = f"Figure {num}"
            if not any(n.get("label") == label for n in nodes):
                nodes.append({
                    "node_type": "figure",
                    "label": label,
                    "text": f"[Figure {num} content]"
                })
        
        # Detect tables
        table_matches = re.findall(r'(Table|Tab\.?)\s*(\d+(?:\.\d+)?)', content)
        for _, num in table_matches:
            label = f"Table {num}"
            if not any(n.get("label") == label for n in nodes):
                nodes.append({
                    "node_type": "table",
                    "label": label,
                    "text": f"[Table {num} content]"
                })
        
        # Detect chunks (simplified)
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip() and not p.startswith('#')]
        for i, para in enumerate(paragraphs[:5]):  # First 5 paragraphs as chunks
            nodes.append({
                "node_type": "chunk",
                "label": f"chunk_{i}",
                "text": para[:200]
            })
        
        # Mock edge types based on content
        if "see Figure" in content or "shown in Figure" in content:
            edges.append("references")
        if "Figure" in content and "shows" in content:
            edges.append("explained_by")
        if self.use_graph_expansion:
            edges.extend(["adjacent_prev", "adjacent_next"])
        
        return RetrievalResult(
            query_id="",
            retrieved_nodes=nodes[:top_k],
            edges_traversed=edges,
            context_text=content[:2000],
            execution_time_ms=50.0
        )


def load_queries() -> Dict[str, Any]:
    """Load evaluation queries."""
    with open(QUERIES_FILE) as f:
        return json.load(f)


def evaluate_query(
    query_config: Dict[str, Any],
    retriever,
) -> EvalResult:
    """Evaluate a single query.
    
    Args:
        query_config: Query configuration from queries.json
        retriever: Retriever instance
        
    Returns:
        EvalResult
    """
    result = EvalResult(
        query_id=query_config["id"],
        query_text=query_config["query"],
        fixture_id=query_config["fixture"],
        difficulty=query_config.get("difficulty", "unknown"),
        edges_expected=query_config.get("expected_edge_types", [])
    )
    
    try:
        # Retrieve
        retrieval = retriever.retrieve(
            query=query_config["query"],
            fixture_id=query_config["fixture"],
            top_k=10
        )
        
        # Check evidence recall
        expected_labels = query_config.get("expected_evidence_labels", [])
        if expected_labels:
            retrieved_labels = [
                n.get("label") for n in retrieval.retrieved_nodes
                if n.get("label")
            ]
            
            # Check at different K values
            for k, attr in [(1, "evidence_recall_at_1"), (3, "evidence_recall_at_3"),
                           (5, "evidence_recall_at_5"), (10, "evidence_recall_at_10")]:
                top_k_labels = retrieved_labels[:k]
                found = any(exp in top_k_labels for exp in expected_labels)
                setattr(result, attr, found)
        
        # Check keyword hits
        expected_keywords = query_config.get("expected_chunk_keywords", [])
        if expected_keywords:
            result.keyword_total = len(expected_keywords)
            for kw in expected_keywords:
                if kw.lower() in retrieval.context_text.lower():
                    result.keyword_hits += 1
            result.keyword_hit_rate = result.keyword_hits / result.keyword_total if result.keyword_total > 0 else 0.0
        
        # Check edge coverage
        expected_edges = query_config.get("expected_edge_types", [])
        if expected_edges:
            result.edges_expected = expected_edges
            result.edges_found = [e for e in retrieval.edges_traversed if e in expected_edges]
            result.edge_coverage = len(result.edges_found) / len(expected_edges)
        
        # Add notes
        if query_config.get("note"):
            result.notes = query_config["note"]
        
    except Exception as e:
        result.error = str(e)
        logger.error(f"Query {query_config['id']} failed: {e}")
    
    return result


def run_evaluation(
    retriever,
    query_ids: Optional[List[str]] = None
) -> EvalSummary:
    """Run full evaluation.
    
    Args:
        retriever: Retriever instance
        query_ids: Optional list of specific query IDs to run
        
    Returns:
        EvalSummary
    """
    queries_data = load_queries()
    queries = queries_data["queries"]
    
    # Filter queries if specified
    if query_ids:
        queries = [q for q in queries if q["id"] in query_ids]
    
    summary = EvalSummary(total_queries=len(queries))
    
    # Run evaluations
    for query in queries:
        logger.info(f"Evaluating query: {query['id']}")
        result = evaluate_query(query, retriever)
        summary.results.append(result)
    
    # Calculate aggregate metrics
    if summary.results:
        summary.recall_at_1 = sum(1 for r in summary.results if r.evidence_recall_at_1) / len(summary.results)
        summary.recall_at_3 = sum(1 for r in summary.results if r.evidence_recall_at_3) / len(summary.results)
        summary.recall_at_5 = sum(1 for r in summary.results if r.evidence_recall_at_5) / len(summary.results)
        summary.recall_at_10 = sum(1 for r in summary.results if r.evidence_recall_at_10) / len(summary.results)
        
        keyword_rates = [r.keyword_hit_rate for r in summary.results if r.keyword_total > 0]
        summary.avg_keyword_hit_rate = sum(keyword_rates) / len(keyword_rates) if keyword_rates else 0.0
        
        edge_coverages = [r.edge_coverage for r in summary.results if r.edges_expected]
        summary.avg_edge_coverage = sum(edge_coverages) / len(edge_coverages) if edge_coverages else 0.0
        
        # By difficulty
        easy = [r for r in summary.results if r.difficulty == "easy"]
        medium = [r for r in summary.results if r.difficulty == "medium"]
        hard = [r for r in summary.results if r.difficulty == "hard"]
        
        summary.easy_recall = sum(1 for r in easy if r.evidence_recall_at_5) / len(easy) if easy else 0.0
        summary.medium_recall = sum(1 for r in medium if r.evidence_recall_at_5) / len(medium) if medium else 0.0
        summary.hard_recall = sum(1 for r in hard if r.evidence_recall_at_5) / len(hard) if hard else 0.0
    
    return summary


def print_report(summary: EvalSummary, baseline: Optional[EvalSummary] = None) -> None:
    """Print evaluation report."""
    print("\n" + "=" * 70)
    print("  GRAPH RAG EVALUATION REPORT")
    print("=" * 70)
    
    print(f"\n  Total Queries: {summary.total_queries}")
    
    print("\n  EVIDENCE RECALL (figure/table retrieved)")
    print("-" * 50)
    print(f"  Recall@1:  {summary.recall_at_1:.1%}")
    print(f"  Recall@3:  {summary.recall_at_3:.1%}")
    print(f"  Recall@5:  {summary.recall_at_5:.1%}")
    print(f"  Recall@10: {summary.recall_at_10:.1%}")
    
    if baseline:
        print("\n  COMPARISON WITH BASELINE (vector-only)")
        print("-" * 50)
        diff = summary.recall_at_5 - baseline.recall_at_5
        direction = "↑" if diff > 0 else "↓" if diff < 0 else "→"
        print(f"  Recall@5: {baseline.recall_at_5:.1%} → {summary.recall_at_5:.1%} ({direction} {abs(diff):.1%})")
    
    print("\n  CONTEXT QUALITY")
    print("-" * 50)
    print(f"  Avg Keyword Hit Rate: {summary.avg_keyword_hit_rate:.1%}")
    print(f"  Avg Edge Coverage:    {summary.avg_edge_coverage:.1%}")
    
    print("\n  BY DIFFICULTY (Recall@5)")
    print("-" * 50)
    print(f"  Easy:   {summary.easy_recall:.1%}")
    print(f"  Medium: {summary.medium_recall:.1%}")
    print(f"  Hard:   {summary.hard_recall:.1%}")
    
    print("\n  DETAILED RESULTS")
    print("-" * 50)
    for result in summary.results:
        status = "✓" if result.evidence_recall_at_5 else "✗"
        print(f"  {status} {result.query_id}: {result.query_text[:40]}...")
        if result.error:
            print(f"      ERROR: {result.error}")
        if result.notes:
            print(f"      Note: {result.notes}")
    
    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Graph RAG Evaluation Harness")
    parser.add_argument("--query", "-q", help="Run specific query ID")
    parser.add_argument("--compare", action="store_true", help="Compare with baseline")
    parser.add_argument("--no-expansion", action="store_true", help="Disable graph expansion (baseline)")
    
    args = parser.parse_args()
    
    # Create retriever
    retriever = MockRetriever(use_graph_expansion=not args.no_expansion)
    
    # Run evaluation
    query_ids = [args.query] if args.query else None
    summary = run_evaluation(retriever, query_ids)
    
    # Optionally run baseline comparison
    baseline = None
    if args.compare:
        baseline_retriever = MockRetriever(use_graph_expansion=False)
        baseline = run_evaluation(baseline_retriever, query_ids)
    
    # Print report
    print_report(summary, baseline)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
