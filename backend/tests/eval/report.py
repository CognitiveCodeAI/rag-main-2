#!/usr/bin/env python
"""Generate comparison reports for Graph RAG evaluation.

Generates reports comparing:
- Vector-only baseline vs Graph-expanded retrieval
- Before/after improvements

Usage:
    python -m tests.eval.report                  # Generate report
    python -m tests.eval.report --format html    # HTML output
    python -m tests.eval.report --output report  # Save to file
"""

import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.eval.run_eval import (
    MockRetriever,
    run_evaluation,
    EvalSummary,
)
from tests.eval.benchmark_contract import (
    ContractRunInfo,
    ContractValidationError,
    enforce_retrieval_benchmark_contract,
)


def generate_markdown_report(
    graph_summary: EvalSummary,
    baseline_summary: EvalSummary,
    contract: Optional[ContractRunInfo] = None,
) -> str:
    """Generate markdown comparison report."""
    
    lines = [
        "# Graph RAG Evaluation Report",
        "",
        f"Generated: {datetime.now().isoformat()}",
        "",
    ]
    if contract:
        lines.extend(
            [
                f"Contract: `{contract.contract_id}` v{contract.contract_version}",
                f"Contract SHA256: `{contract.contract_sha256}`",
                f"Contract File: `{contract.contract_path}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Summary",
            "",
            "| Metric | Baseline (Vector-Only) | Graph-Expanded | Improvement |",
            "|--------|------------------------|----------------|-------------|",
        ]
    )
    
    # Recall metrics
    metrics = [
        ("Recall@1", baseline_summary.recall_at_1, graph_summary.recall_at_1),
        ("Recall@3", baseline_summary.recall_at_3, graph_summary.recall_at_3),
        ("Recall@5", baseline_summary.recall_at_5, graph_summary.recall_at_5),
        ("Recall@10", baseline_summary.recall_at_10, graph_summary.recall_at_10),
        ("Keyword Hit Rate", baseline_summary.avg_keyword_hit_rate, graph_summary.avg_keyword_hit_rate),
        ("Edge Coverage", baseline_summary.avg_edge_coverage, graph_summary.avg_edge_coverage),
    ]
    
    for name, base, graph in metrics:
        diff = graph - base
        direction = "↑" if diff > 0 else "↓" if diff < 0 else "→"
        lines.append(f"| {name} | {base:.1%} | {graph:.1%} | {direction} {abs(diff):.1%} |")
    
    lines.extend([
        "",
        "## By Difficulty",
        "",
        "| Difficulty | Baseline | Graph | Improvement |",
        "|------------|----------|-------|-------------|",
        f"| Easy | {baseline_summary.easy_recall:.1%} | {graph_summary.easy_recall:.1%} | {graph_summary.easy_recall - baseline_summary.easy_recall:+.1%} |",
        f"| Medium | {baseline_summary.medium_recall:.1%} | {graph_summary.medium_recall:.1%} | {graph_summary.medium_recall - baseline_summary.medium_recall:+.1%} |",
        f"| Hard | {baseline_summary.hard_recall:.1%} | {graph_summary.hard_recall:.1%} | {graph_summary.hard_recall - baseline_summary.hard_recall:+.1%} |",
        "",
        "## Detailed Results",
        "",
    ])
    
    for result in graph_summary.results:
        status = "✅" if result.evidence_recall_at_5 else "❌"
        lines.append(f"### {status} {result.query_id}")
        lines.append(f"")
        lines.append(f"**Query:** {result.query_text}")
        lines.append(f"")
        lines.append(f"- Difficulty: {result.difficulty}")
        lines.append(f"- Recall@5: {'Yes' if result.evidence_recall_at_5 else 'No'}")
        lines.append(f"- Keyword Hit Rate: {result.keyword_hit_rate:.1%}")
        lines.append(f"- Edge Coverage: {result.edge_coverage:.1%}")
        
        if result.edges_expected:
            lines.append(f"- Expected Edges: {', '.join(result.edges_expected)}")
            lines.append(f"- Found Edges: {', '.join(result.edges_found) if result.edges_found else 'None'}")
        
        if result.notes:
            lines.append(f"- Note: {result.notes}")
        
        if result.error:
            lines.append(f"- **Error:** {result.error}")
        
        lines.append("")
    
    return "\n".join(lines)


def generate_html_report(
    graph_summary: EvalSummary,
    baseline_summary: EvalSummary,
    contract: Optional[ContractRunInfo] = None,
) -> str:
    """Generate HTML comparison report."""
    
    def metric_row(name: str, base: float, graph: float) -> str:
        diff = graph - base
        color = "#4CAF50" if diff > 0 else "#f44336" if diff < 0 else "#999"
        arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
        return f"""
        <tr>
            <td>{name}</td>
            <td>{base:.1%}</td>
            <td>{graph:.1%}</td>
            <td style="color: {color}">{arrow} {abs(diff):.1%}</td>
        </tr>"""
    
    metrics_rows = "".join([
        metric_row("Recall@1", baseline_summary.recall_at_1, graph_summary.recall_at_1),
        metric_row("Recall@3", baseline_summary.recall_at_3, graph_summary.recall_at_3),
        metric_row("Recall@5", baseline_summary.recall_at_5, graph_summary.recall_at_5),
        metric_row("Recall@10", baseline_summary.recall_at_10, graph_summary.recall_at_10),
        metric_row("Keyword Hit Rate", baseline_summary.avg_keyword_hit_rate, graph_summary.avg_keyword_hit_rate),
        metric_row("Edge Coverage", baseline_summary.avg_edge_coverage, graph_summary.avg_edge_coverage),
    ])
    
    results_html = ""
    for result in graph_summary.results:
        status_color = "#4CAF50" if result.evidence_recall_at_5 else "#f44336"
        results_html += f"""
        <div class="result" style="border-left: 4px solid {status_color}; padding-left: 12px; margin: 12px 0;">
            <h4>{result.query_id}</h4>
            <p><strong>Query:</strong> {result.query_text}</p>
            <p>Difficulty: {result.difficulty} | 
               Recall@5: {'✅' if result.evidence_recall_at_5 else '❌'} |
               Keywords: {result.keyword_hit_rate:.0%}</p>
        </div>"""

    contract_html = ""
    if contract:
        contract_html = (
            f"<p><strong>Contract:</strong> {contract.contract_id} v{contract.contract_version}<br/>"
            f"<strong>Contract SHA256:</strong> {contract.contract_sha256}<br/>"
            f"<strong>Contract File:</strong> {contract.contract_path}</p>"
        )
    
    return f"""<!DOCTYPE html>
<html>
<head>
    <title>Graph RAG Evaluation Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #f5f5f5; }}
        .result {{ background: #fafafa; padding: 12px; border-radius: 4px; }}
    </style>
</head>
<body>
    <h1>📊 Graph RAG Evaluation Report</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    {contract_html}
    
    <h2>Summary Metrics</h2>
    <table>
        <tr>
            <th>Metric</th>
            <th>Baseline</th>
            <th>Graph-Expanded</th>
            <th>Change</th>
        </tr>
        {metrics_rows}
    </table>
    
    <h2>Detailed Results</h2>
    {results_html}
</body>
</html>"""


def generate_json_report(
    graph_summary: EvalSummary,
    baseline_summary: EvalSummary,
    contract: Optional[ContractRunInfo] = None,
) -> str:
    """Generate JSON report for programmatic use."""
    
    def summary_to_dict(s: EvalSummary, name: str) -> Dict[str, Any]:
        return {
            "name": name,
            "total_queries": s.total_queries,
            "recall_at_1": s.recall_at_1,
            "recall_at_3": s.recall_at_3,
            "recall_at_5": s.recall_at_5,
            "recall_at_10": s.recall_at_10,
            "avg_keyword_hit_rate": s.avg_keyword_hit_rate,
            "avg_edge_coverage": s.avg_edge_coverage,
            "by_difficulty": {
                "easy": s.easy_recall,
                "medium": s.medium_recall,
                "hard": s.hard_recall,
            }
        }
    
    report = {
        "generated_at": datetime.now().isoformat(),
        "contract": {
            "contract_id": contract.contract_id,
            "contract_version": contract.contract_version,
            "contract_sha256": contract.contract_sha256,
            "contract_path": contract.contract_path,
        } if contract else None,
        "baseline": summary_to_dict(baseline_summary, "vector_only"),
        "graph_expanded": summary_to_dict(graph_summary, "graph_expanded"),
        "improvement": {
            "recall_at_5": graph_summary.recall_at_5 - baseline_summary.recall_at_5,
            "keyword_hit_rate": graph_summary.avg_keyword_hit_rate - baseline_summary.avg_keyword_hit_rate,
            "edge_coverage": graph_summary.avg_edge_coverage - baseline_summary.avg_edge_coverage,
        },
        "results": [
            {
                "query_id": r.query_id,
                "query": r.query_text,
                "difficulty": r.difficulty,
                "recall_at_5": r.evidence_recall_at_5,
                "keyword_hit_rate": r.keyword_hit_rate,
                "edge_coverage": r.edge_coverage,
            }
            for r in graph_summary.results
        ]
    }
    
    return json.dumps(report, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Generate Graph RAG Evaluation Report")
    parser.add_argument("--format", "-f", choices=["md", "html", "json"], default="md",
                       help="Output format")
    parser.add_argument("--output", "-o", help="Output file (without extension)")
    parser.add_argument(
        "--contract",
        default=str(Path(__file__).parent / "benchmark_contract.json"),
        help="Path to benchmark contract JSON",
    )
    
    args = parser.parse_args()
    
    print("Running evaluations...")
    try:
        contract_run = enforce_retrieval_benchmark_contract(
            query_subset_requested=False,
            contract_path=args.contract,
        )
    except ContractValidationError as e:
        raise SystemExit(f"Benchmark contract validation failed: {e}") from e
    
    # Run baseline (vector-only)
    baseline_retriever = MockRetriever(use_graph_expansion=False)
    baseline_summary = run_evaluation(baseline_retriever, contract=contract_run)
    
    # Run graph-expanded
    graph_retriever = MockRetriever(use_graph_expansion=True)
    graph_summary = run_evaluation(graph_retriever, contract=contract_run)
    
    # Generate report
    if args.format == "md":
        report = generate_markdown_report(graph_summary, baseline_summary, contract=contract_run)
        ext = ".md"
    elif args.format == "html":
        report = generate_html_report(graph_summary, baseline_summary, contract=contract_run)
        ext = ".html"
    else:
        report = generate_json_report(graph_summary, baseline_summary, contract=contract_run)
        ext = ".json"
    
    # Output
    if args.output:
        output_path = Path(args.output).with_suffix(ext)
        output_path.write_text(report)
        print(f"Report saved to: {output_path}")
    else:
        print(report)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
