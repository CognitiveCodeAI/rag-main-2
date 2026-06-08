"""Embedding reconciliation (D4 / audit H-5).

Ingestion persists graph nodes to Postgres but does NOT embed; embedding is a
separate async step (embed_nodes_task). If that step never runs or fails, a
document looks ingested but is un-queryable (its nodes have no Milvus vectors)
with no signal. ``DocumentGraph.embedded_collection_version`` is NULL until a
successful embed sets it, so it doubles as the embedding-status marker.

This module finds canonical documents that have nodes but were never embedded
and (on demand) re-enqueues embedding for them — closing the silent-gap.
"""

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def doc_needs_embedding(
    embedded_collection_version: Optional[str],
    canonical_doc_id: Optional[str],
    has_nodes: bool,
) -> bool:
    """Pure predicate: a canonical document with nodes but no embeddings.

    Aliases (canonical_doc_id set) reuse the canonical doc's vectors and are
    skipped. A doc that already has an embedded_collection_version is done.
    """
    if canonical_doc_id:
        return False
    if embedded_collection_version:
        return False
    return has_nodes


def find_unembedded_docs(db, limit: Optional[int] = 100) -> list:
    """Return canonical DocumentGraph rows that have nodes but no embeddings."""
    from sqlalchemy import exists

    from app.db.graph_models import DocumentGraph, Node

    query = (
        db.query(DocumentGraph)
        .filter(DocumentGraph.embedded_collection_version.is_(None))
        .filter(DocumentGraph.canonical_doc_id.is_(None))
        .filter(exists().where(Node.doc_id == DocumentGraph.doc_id))
        .order_by(DocumentGraph.ingested_at)
    )
    if limit:
        query = query.limit(limit)
    return query.all()


def reconcile_unembedded(
    db,
    enqueue: Callable[[str, int], None],
    limit: int = 50,
) -> dict:
    """Find un-embedded docs and re-enqueue embedding for each.

    ``enqueue(doc_id, version)`` schedules the embedding work (e.g. a Celery
    ``.delay``). Returns a summary of what was found and enqueued.
    """
    docs = find_unembedded_docs(db, limit=limit)
    enqueued = []
    for doc in docs:
        try:
            enqueue(doc.doc_id, doc.version)
            enqueued.append({"doc_id": doc.doc_id, "version": doc.version})
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to enqueue embedding for %s: %s", doc.doc_id, exc)
    if enqueued:
        logger.info("Embedding reconciliation enqueued %d document(s)", len(enqueued))
    return {"found": len(docs), "enqueued": enqueued}
