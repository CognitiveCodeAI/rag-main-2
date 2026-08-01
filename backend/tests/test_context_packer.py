"""Unit tests for context marker formatting."""

from app.graph.context_packer import Citation, ContextBlock, PackedContext


def test_to_text_exposes_canonical_node_id_page_marker() -> None:
    """Each block should begin with [node_id:page] for direct LLM citation reuse."""
    packed = PackedContext(
        blocks=[
            ContextBlock(
                text="Chunk body",
                citation=Citation(
                    node_id="chunk_abc123",
                    doc_id="doc-1",
                    page_no=3,
                    label=None,
                    bbox=None,
                    source_type="seed",
                ),
                node_type="chunk",
                order=0,
            )
        ],
        total_chars=10,
        total_tokens_estimate=2,
    )

    text = packed.to_text(include_citations=True)
    assert text.startswith(
        "[chunk_abc123:3] node_id=chunk_abc123 page_no=3 source=seed\nChunk body"
    )


def test_to_text_keeps_metadata_outside_citation_brackets() -> None:
    """Aux metadata should stay outside [] so citation regex remains simple."""
    packed = PackedContext(
        blocks=[
            ContextBlock(
                text="Figure body",
                citation=Citation(
                    node_id="figure_def456",
                    doc_id="doc-1",
                    page_no=7,
                    label="Figure 1",
                    bbox=None,
                    source_type="referenced",
                ),
                node_type="figure",
                order=0,
            )
        ],
        total_chars=11,
        total_tokens_estimate=2,
    )

    text = packed.to_text(include_citations=True)
    assert text.startswith("[figure_def456:7]")
    assert " source=referenced label=Figure 1\n" in text
