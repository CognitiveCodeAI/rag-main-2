"""PostgreSQL integration coverage for evidence chains and ACL boundaries."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import fitz
import pytest

from app.acl.enforcer import ACLEnforcer
from app.acl.models import Entitlements
from app.db.graph_models import DocumentGraph, Edge, EdgeType, Node, NodeType
from app.db.session import SessionLocal
from app.graph.context_packer import ContextPacker
from app.graph.chunker import PageBoundedChunker
from app.graph.expander import ExpandedContext
from app.graph.pipeline import GraphIngestionPipeline
from app.qa.evidence_chain import EvidenceChainConfig, EvidenceChainEngine
from app.services.highlighting import verify_evidence_span


pytestmark = pytest.mark.integration


def test_real_pdf_ingestion_builds_a_chain_ready_provenance_graph():
    """Exercise native PDF ingestion -> persisted nodes/edges -> chain search."""
    suffix = uuid.uuid4().hex[:10]
    source_uri = f"test://chain-ingest-{suffix}.pdf"
    pdf = fitz.open()
    try:
        page_texts = [
            "The agreement originally required thirty days written notice.",
            "The 2026 amendment replaces the original notice provision.",
            "The governing statute requires sixty days notice after the amendment.",
        ]
        for text in page_texts:
            page = pdf.new_page(width=612, height=792)
            page.insert_text((72, 100), text, fontsize=11)
        pdf_bytes = pdf.tobytes()
    finally:
        pdf.close()

    session = SessionLocal()
    try:
        pipeline = GraphIngestionPipeline(
            session,
            skip_ocr=True,
            tenant_id="chain-test-tenant",
            visibility="public",
        )
        pipeline.chunker = PageBoundedChunker(target_tokens=100, min_tokens=1)
        # Artifact storage is deliberately excluded from this PostgreSQL
        # representative-stack test; selector construction still runs.
        with patch(
            "app.graph.pipeline.get_storage_client",
            side_effect=RuntimeError("object storage intentionally disabled in test"),
        ):
            ingest = pipeline.ingest(pdf_bytes=pdf_bytes, source_uri=source_uri)

        nodes = (
            session.query(Node)
            .filter(Node.doc_id == ingest.doc_id, Node.version == ingest.version)
            .order_by(Node.page_no.asc(), Node.chunk_index_in_page.asc())
            .all()
        )
        edges = (
            session.query(Edge)
            .filter(Edge.doc_id == ingest.doc_id, Edge.version == ingest.version)
            .all()
        )
        assert ingest.total_pages == 3
        assert len(nodes) == 3
        assert len(edges) >= 2
        assert all((node.meta or {}).get("source_spans") for node in nodes)
        assert all((node.meta or {}).get("selector_bundle") for node in nodes)

        enforcer = ACLEnforcer(
            session,
            Entitlements(
                tenant_id="chain-test-tenant",
                user_id="alice",
                roles=frozenset(),
                groups=frozenset(),
            ),
        )
        chain = EvidenceChainEngine(
            session,
            acl_enforcer=enforcer,
            config=EvidenceChainConfig(mode="on", max_selected_nodes=6),
        ).build(
            ExpandedContext(
                seed_nodes=[nodes[0]],
                adjacent_nodes=[],
                referenced_nodes=[],
                explained_by_nodes=[],
                node_sources={nodes[0].node_id: "seed"},
            ),
            "How does the 2026 amendment affect notice under the governing statute?",
            {nodes[0].node_id: 1.0},
            doc_id=ingest.doc_id,
            version=ingest.version,
        )

        assert chain.applied is True
        assert {node.node_id for node in nodes}.issubset(chain.selected_node_ids)
        assert any(
            path.node_ids[0] == nodes[0].node_id
            and path.node_ids[-1] == nodes[-1].node_id
            for path in chain.paths
        )
    finally:
        session.close()


def test_postgres_chain_traversal_packing_and_node_acl_are_consistent():
    suffix = uuid.uuid4().hex[:10]
    doc_id = f"chain-int-{suffix}"
    seed_id = f"seed-{suffix}"
    bridge_id = f"bridge-{suffix}"
    target_id = f"target-{suffix}"
    denied_id = f"denied-{suffix}"
    session = SessionLocal()

    try:
        session.add(
            DocumentGraph(
                doc_id=doc_id,
                source_uri=f"test://{doc_id}",
                content_hash=uuid.uuid4().hex * 2,
                version=1,
                tenant_id="chain-test-tenant",
                visibility="public",
                policy_version=1,
            )
        )
        nodes = [
            Node(
                node_id=seed_id,
                doc_id=doc_id,
                version=1,
                node_type=NodeType.chunk,
                page_no=1,
                chunk_index_in_page=0,
                text_plain="The patient has renal impairment.",
                meta={},
            ),
            Node(
                node_id=bridge_id,
                doc_id=doc_id,
                version=1,
                node_type=NodeType.chunk,
                page_no=2,
                chunk_index_in_page=0,
                text_plain="Drug A is cleared through the kidneys.",
                meta={},
            ),
            Node(
                node_id=target_id,
                doc_id=doc_id,
                version=1,
                node_type=NodeType.chunk,
                page_no=3,
                chunk_index_in_page=0,
                text_plain="The current guideline lists renal impairment as a contraindication.",
                meta={},
            ),
            Node(
                node_id=denied_id,
                doc_id=doc_id,
                version=1,
                node_type=NodeType.chunk,
                page_no=4,
                chunk_index_in_page=0,
                text_plain="Node-level restricted evidence must never influence the chain.",
                meta={
                    "acl_override": {
                        "visibility": "restricted",
                        "allowed_users": ["bob"],
                    }
                },
            ),
        ]
        session.add_all(nodes)
        session.flush()
        session.add_all(
            [
                Edge(
                    doc_id=doc_id,
                    version=1,
                    from_node_id=seed_id,
                    to_node_id=bridge_id,
                    edge_type=EdgeType.references,
                    confidence=0.9,
                ),
                Edge(
                    doc_id=doc_id,
                    version=1,
                    from_node_id=bridge_id,
                    to_node_id=target_id,
                    edge_type=EdgeType.explained_by,
                    confidence=1.0,
                ),
                Edge(
                    doc_id=doc_id,
                    version=1,
                    from_node_id=seed_id,
                    to_node_id=denied_id,
                    edge_type=EdgeType.references,
                    confidence=1.0,
                ),
            ]
        )
        session.flush()

        enforcer = ACLEnforcer(
            session,
            Entitlements(
                tenant_id="chain-test-tenant",
                user_id="alice",
                roles=frozenset(),
                groups=frozenset(),
            ),
        )
        engine = EvidenceChainEngine(
            session,
            acl_enforcer=enforcer,
            config=EvidenceChainConfig(mode="on", max_selected_nodes=6),
        )
        expanded = ExpandedContext(
            seed_nodes=[nodes[0]],
            adjacent_nodes=[],
            referenced_nodes=[],
            explained_by_nodes=[],
            node_sources={seed_id: "seed"},
        )

        result = engine.build(
            expanded,
            "How does renal impairment affect Drug A under the current guideline?",
            {seed_id: 1.0},
            doc_id=doc_id,
            version=1,
        )

        assert result.applied is True
        assert {seed_id, bridge_id, target_id}.issubset(result.selected_node_ids)
        assert denied_id not in result.selected_node_ids
        assert denied_id not in str(result.to_audit_dict())
        assert any(
            path.node_ids == (seed_id, bridge_id, target_id)
            for path in result.paths
        )

        expanded.chain_nodes = result.additional_nodes
        for node in expanded.chain_nodes:
            expanded.node_sources[node.node_id] = "chain"
        packed = ContextPacker(max_tokens=500).pack(
            expanded,
            node_order=result.ordered_node_ids,
            allowed_node_ids=result.selected_node_ids,
        )
        packed_text = packed.to_text()
        assert f"[{seed_id}:1]" in packed_text
        assert f"[{bridge_id}:2]" in packed_text
        assert f"[{target_id}:3]" in packed_text
        assert denied_id not in packed_text
        assert any(
            entry["stage"].startswith("evidence_chain_hop_") and entry["denied"] == 1
            for entry in enforcer.get_audit_log()
        )

        # The chain ranking is not allowed to manufacture a locator.  Prove
        # that a selected leaf still resolves through the independent source
        # provenance verifier, and that a wrong-page request fails closed.
        quote = nodes[2].text_plain
        words = quote.split()
        source_spans = [
            {
                "span_id": f"p3:w{index}",
                "order": index,
                "text": word,
                "block_no": 0,
                "line_no": 0,
                "word_no": index,
                "normalized_bbox": {
                    "x0": 0.05 + index * 0.06,
                    "y0": 0.20,
                    "x1": 0.10 + index * 0.06,
                    "y1": 0.23,
                },
                "coordinate_system": "pdf_points_top_left",
                "extraction_source": "native_pdf",
                "verifiable": True,
            }
            for index, word in enumerate(words)
        ]
        source_map = {
            "doc_id": doc_id,
            "version": 1,
            "content_hash": "sha256:chain-source",
            "canonical_text": quote,
            "nodes": [
                {
                    "node_id": target_id,
                    "start": 0,
                    "end": len(quote),
                    "page_no": 3,
                    "page_rotation": 0,
                    "page_size": {"width": 612, "height": 792},
                    "source_spans": source_spans,
                }
            ],
        }
        verified = verify_evidence_span(
            doc_id=doc_id,
            document_version=1,
            node_id=target_id,
            page_index=3,
            quote_text=quote,
            locator=None,
            source_hash="sha256:chain-source",
            source_map=source_map,
        )
        wrong_page = verify_evidence_span(
            doc_id=doc_id,
            document_version=1,
            node_id=target_id,
            page_index=2,
            quote_text=quote,
            locator=None,
            source_hash="sha256:chain-source",
            source_map=source_map,
        )
        assert verified["status"] == "FOUND"
        assert verified["grade"] == "verified"
        assert verified["matched_locator"]["type"] == "rects"
        assert wrong_page["status"] == "NOT_FOUND"
        assert wrong_page["reason"] == "page_not_indexed"
    finally:
        session.rollback()
        session.close()
