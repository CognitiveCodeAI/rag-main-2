"""Pure document/node metadata queries (E2 extraction from QARunner).

These are db-only helpers with no other QARunner coupling; QARunner keeps thin
wrappers that delegate here, so call sites and behavior are unchanged.
"""

from typing import Dict, List, Optional


def get_doc_total_pages(db, doc_id: str) -> int:
    """Total pages for a document (0 if unknown)."""
    from app.db.graph_models import DocumentGraph
    doc = db.query(DocumentGraph).filter(DocumentGraph.doc_id == doc_id).first()
    if doc and doc.meta:
        return doc.meta.get("total_pages", 0)
    return 0


def get_doc_collection_version(db, doc_id: Optional[str]) -> Optional[str]:
    """Milvus collection version a document was embedded into.

    Returns None when doc_id is None (search-all uses the default collection)
    or when the version is unknown.
    """
    if not doc_id:
        return None
    from app.db.graph_models import DocumentGraph
    doc = db.query(DocumentGraph).filter(DocumentGraph.doc_id == doc_id).first()
    if doc and doc.embedded_collection_version:
        return doc.embedded_collection_version
    return None


def get_nodes_metadata(db, node_ids: List[str]) -> Dict[str, Dict]:
    """Return {node_id -> meta dict} for the given node ids."""
    from app.db.graph_models import Node as NodeModel
    if not node_ids:
        return {}
    nodes = db.query(NodeModel).filter(NodeModel.node_id.in_(node_ids)).all()
    return {n.node_id: n.meta or {} for n in nodes}
