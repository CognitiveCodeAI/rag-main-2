"""A/B comparison: native vs Docling ingestion backends.

Ingests the same document through both backends and compares:
- Page count, character count per page
- Chunk count and sizes
- Figure/table detection count
- Word-level Jaccard similarity
- Section hint coverage

Usage:
    python -m tests.eval.eval_docling_ab path/to/document.pdf

Outputs a markdown report to tests/eval/report_docling_ab.md
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _jaccard_words(text_a: str, text_b: str) -> float:
    """Compute word-level Jaccard similarity between two texts."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a and not words_b:
        return 1.0
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def run_native(raw_bytes: bytes, filename: str, source_type: str, doc_id: str) -> Dict[str, Any]:
    """Run the native extraction pipeline."""
    from app.graph.page_extractor import PageExtractor
    from app.graph.figure_detector import FigureDetector
    from app.graph.chunker import PageBoundedChunker

    extractor = PageExtractor(skip_ocr=True)
    detector = FigureDetector()
    chunker = PageBoundedChunker()

    extraction = extractor.extract_pages(pdf_bytes=raw_bytes, doc_id=doc_id)
    figures = detector.detect_in_document(pdf_bytes=raw_bytes, doc_id=doc_id)

    pages_for_chunking = [(p.page_no, p.text_plain) for p in extraction.pages]
    chunks = chunker.chunk_pages(
        pages=pages_for_chunking,
        doc_id=doc_id,
        version=1,
        page_data_list=extraction.pages,
    )

    return {
        "backend": "native",
        "total_pages": extraction.total_pages,
        "page_char_counts": [len(p.text_plain) for p in extraction.pages],
        "page_texts": [p.text_plain for p in extraction.pages],
        "total_chunks": len(chunks),
        "chunk_sizes": [len(c.text_plain) for c in chunks],
        "total_figures": sum(1 for f in figures if f.figure_type == "figure"),
        "total_tables": sum(1 for f in figures if f.figure_type == "table"),
        "section_hints": sum(
            1 for c in chunks if c.meta and c.meta.get("section_hint")
        ),
    }


def run_docling(raw_bytes: bytes, filename: str, source_type: str, doc_id: str) -> Dict[str, Any]:
    """Run the Docling extraction pipeline."""
    from app.graph.docling_adapter import convert_with_docling
    from app.graph.chunker import PageBoundedChunker
    from app.config import get_settings

    settings = get_settings()
    extraction, figures, provenance = convert_with_docling(
        raw_bytes=raw_bytes,
        filename=filename,
        source_type=source_type,
        doc_id=doc_id,
        max_pages=settings.docling_max_pages,
        max_file_size_mb=settings.docling_max_file_size_mb,
    )

    chunker = PageBoundedChunker()
    pages_for_chunking = [(p.page_no, p.text_plain) for p in extraction.pages]
    chunks = chunker.chunk_pages(
        pages=pages_for_chunking,
        doc_id=doc_id,
        version=1,
        page_data_list=extraction.pages,
    )

    return {
        "backend": "docling",
        "total_pages": extraction.total_pages,
        "page_char_counts": [len(p.text_plain) for p in extraction.pages],
        "page_texts": [p.text_plain for p in extraction.pages],
        "total_chunks": len(chunks),
        "chunk_sizes": [len(c.text_plain) for c in chunks],
        "total_figures": sum(1 for f in figures if f.figure_type == "figure"),
        "total_tables": sum(1 for f in figures if f.figure_type == "table"),
        "section_hints": sum(
            1 for c in chunks if c.meta and c.meta.get("section_hint")
        ),
    }


def generate_report(
    native: Dict[str, Any],
    docling: Dict[str, Any],
    filename: str,
) -> str:
    """Generate a markdown comparison report."""
    lines: List[str] = []
    lines.append(f"# A/B Comparison Report: Native vs Docling")
    lines.append(f"")
    lines.append(f"**Document:** `{filename}`")
    lines.append(f"")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Native | Docling | Delta |")
    lines.append("|--------|--------|---------|-------|")

    metrics = [
        ("Pages", native["total_pages"], docling["total_pages"]),
        ("Chunks", native["total_chunks"], docling["total_chunks"]),
        ("Figures", native["total_figures"], docling["total_figures"]),
        ("Tables", native["total_tables"], docling["total_tables"]),
        ("Section hints", native["section_hints"], docling["section_hints"]),
    ]

    for name, n_val, d_val in metrics:
        delta = d_val - n_val
        sign = "+" if delta > 0 else ""
        lines.append(f"| {name} | {n_val} | {d_val} | {sign}{delta} |")

    # Total chars
    n_chars = sum(native["page_char_counts"])
    d_chars = sum(docling["page_char_counts"])
    delta = d_chars - n_chars
    sign = "+" if delta > 0 else ""
    lines.append(f"| Total chars | {n_chars:,} | {d_chars:,} | {sign}{delta:,} |")

    # Per-page character comparison
    lines.append("")
    lines.append("## Per-Page Character Counts")
    lines.append("")
    max_pages = max(native["total_pages"], docling["total_pages"])
    if max_pages <= 50:  # Only show table for reasonable page counts
        lines.append("| Page | Native | Docling | Jaccard |")
        lines.append("|------|--------|---------|---------|")

        for i in range(max_pages):
            n_cc = native["page_char_counts"][i] if i < len(native["page_char_counts"]) else 0
            d_cc = docling["page_char_counts"][i] if i < len(docling["page_char_counts"]) else 0
            n_text = native["page_texts"][i] if i < len(native["page_texts"]) else ""
            d_text = docling["page_texts"][i] if i < len(docling["page_texts"]) else ""
            jaccard = _jaccard_words(n_text, d_text)
            lines.append(f"| {i + 1} | {n_cc:,} | {d_cc:,} | {jaccard:.3f} |")
    else:
        lines.append(f"*{max_pages} pages — table omitted. See aggregate stats above.*")

    # Overall Jaccard
    all_native_text = " ".join(native["page_texts"])
    all_docling_text = " ".join(docling["page_texts"])
    overall_jaccard = _jaccard_words(all_native_text, all_docling_text)
    lines.append("")
    lines.append(f"## Overall Word-Level Jaccard Similarity: **{overall_jaccard:.3f}**")

    # Chunk size distribution
    lines.append("")
    lines.append("## Chunk Size Distribution")
    lines.append("")
    for backend, data in [("Native", native), ("Docling", docling)]:
        sizes = data["chunk_sizes"]
        if sizes:
            avg = sum(sizes) / len(sizes)
            mn = min(sizes)
            mx = max(sizes)
            lines.append(f"- **{backend}**: {len(sizes)} chunks, avg={avg:.0f}, min={mn}, max={mx}")
        else:
            lines.append(f"- **{backend}**: 0 chunks")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="A/B comparison: native vs Docling")
    parser.add_argument("filepath", help="Path to the document to compare")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent / "report_docling_ab.md"),
        help="Output report path (default: tests/eval/report_docling_ab.md)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    filepath = Path(args.filepath)
    if not filepath.exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    raw_bytes = filepath.read_bytes()
    filename = filepath.name
    source_type = filepath.suffix.lstrip(".").lower()
    doc_id = f"eval-{filename}"

    print(f"Running native extraction...")
    try:
        native_result = run_native(raw_bytes, filename, source_type, doc_id)
    except Exception as e:
        print(f"Native extraction failed: {e}")
        native_result = None

    print(f"Running Docling extraction...")
    try:
        docling_result = run_docling(raw_bytes, filename, source_type, doc_id)
    except ImportError:
        print("Docling is not installed. Install with: pip install docling>=2.72.0")
        sys.exit(1)
    except Exception as e:
        print(f"Docling extraction failed: {e}")
        docling_result = None

    if native_result and docling_result:
        report = generate_report(native_result, docling_result, filename)
        output_path = Path(args.output)
        output_path.write_text(report, encoding="utf-8")
        print(f"\nReport written to: {output_path}")
        print(report)
    else:
        print("Cannot generate comparison — one or both backends failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
