"""Helpers for resolving canonical graph document identity."""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.db.graph_models import DocumentGraph
from app.db.models import Document


@dataclass
class GraphIdentity:
    """Resolved graph identity (with optional linked legacy identity)."""

    graph_doc_id: str
    graph_version: int
    legacy_doc_id: Optional[str] = None
    legacy_version_id: Optional[str] = None


def parse_graph_version(version_id: Optional[str]) -> Optional[int]:
    """Parse graph version from API version_id string."""
    if version_id is None:
        return None
    try:
        return int(version_id)
    except (TypeError, ValueError):
        return None


def find_legacy_for_graph(
    db: Session,
    graph_doc_id: str,
    graph_version: int,
) -> Optional[Document]:
    """Find legacy document row linked to a graph identity."""
    return (
        db.query(Document)
        .filter(
            Document.graph_doc_id == graph_doc_id,
            Document.graph_version == graph_version,
        )
        .order_by(Document.updated_at.desc())
        .first()
    )


def resolve_for_embed(
    db: Session,
    requested_doc_id: str,
    requested_version_id: str,
) -> Optional[GraphIdentity]:
    """Resolve embed request identity to canonical graph doc/version.

    Priority:
    1. Direct graph identity (numeric version_id + matching documents_graph row)
    2. Explicit legacy mapping via documents.graph_doc_id/graph_version
    3. Backward-compatible source_uri fallback for pre-mapping rows
    """
    requested_graph_version = parse_graph_version(requested_version_id)

    # 1) Direct graph request path (doc_id is already graph ID)
    if requested_graph_version is not None:
        doc = (
            db.query(DocumentGraph)
            .filter(
                DocumentGraph.doc_id == requested_doc_id,
                DocumentGraph.version == requested_graph_version,
            )
            .first()
        )
        if doc:
            return GraphIdentity(
                graph_doc_id=doc.doc_id,
                graph_version=doc.version,
            )

    # 2) Resolve via explicit legacy mapping (exact doc_id + version_id)
    legacy = (
        db.query(Document)
        .filter(
            Document.doc_id == requested_doc_id,
            Document.version_id == requested_version_id,
        )
        .first()
    )
    if not legacy:
        legacy = db.query(Document).filter(Document.doc_id == requested_doc_id).first()

    if legacy and legacy.graph_doc_id and legacy.graph_version is not None:
        return GraphIdentity(
            graph_doc_id=legacy.graph_doc_id,
            graph_version=legacy.graph_version,
            legacy_doc_id=legacy.doc_id,
            legacy_version_id=legacy.version_id,
        )

    # 3) Backward-compatible fallback for old rows not yet mapped
    if legacy and legacy.source_uri:
        query = db.query(DocumentGraph).filter(DocumentGraph.source_uri == legacy.source_uri)
        if requested_graph_version is not None:
            query = query.filter(DocumentGraph.version == requested_graph_version)
        doc = query.order_by(DocumentGraph.version.desc()).first()
        if doc:
            return GraphIdentity(
                graph_doc_id=doc.doc_id,
                graph_version=doc.version,
                legacy_doc_id=legacy.doc_id,
                legacy_version_id=legacy.version_id,
            )

    return None
