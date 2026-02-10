#!/usr/bin/env python
"""Backfill script for graph node embeddings.

Finds documents that have nodes but no embeddings in Milvus and
queues/runs embedding tasks for them.

Usage:
    # Dry run - show what would be backfilled
    python -m app.scripts.backfill_graph_embeddings --dry-run

    # Run synchronously (for debugging)
    python -m app.scripts.backfill_graph_embeddings --sync

    # Queue tasks via Celery
    python -m app.scripts.backfill_graph_embeddings

    # Limit to specific documents
    python -m app.scripts.backfill_graph_embeddings --doc-id abc123
"""

import argparse
import sys
import logging
from pathlib import Path
from typing import List, Tuple, Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from app.db.session import get_session
from app.db.graph_models import DocumentGraph, Node, NodeType
from app.graph.vector_index import GraphVectorIndex, NODE_TYPE_COLLECTIONS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_docs_needing_backfill(
    doc_id_filter: Optional[str] = None
) -> List[Tuple[str, int, int]]:
    """Find documents that need embedding backfill.
    
    Args:
        doc_id_filter: Optional specific doc_id
        
    Returns:
        List of (doc_id, version, node_count) tuples
    """
    db = next(get_session())
    
    try:
        # Get all doc versions with nodes
        query = db.query(
            Node.doc_id,
            Node.version,
        ).distinct()
        
        if doc_id_filter:
            query = query.filter(Node.doc_id == doc_id_filter)
        
        doc_versions = query.all()
        
        logger.info(f"Found {len(doc_versions)} doc-version pairs with nodes")
        
        # Check which ones have embeddings in Milvus
        vector_index = GraphVectorIndex()
        vector_index.connect()
        
        need_backfill = []
        
        for doc_id, version in doc_versions:
            # Count nodes for this doc version
            node_count = db.query(Node).filter(
                Node.doc_id == doc_id,
                Node.version == version
            ).count()
            
            # Check if any vectors exist in Milvus for this doc
            has_vectors = False
            for node_type in NODE_TYPE_COLLECTIONS.keys():
                try:
                    collection_name = NODE_TYPE_COLLECTIONS[node_type]
                    
                    from pymilvus import Collection, utility
                    if utility.has_collection(collection_name):
                        collection = Collection(collection_name)
                        collection.load()
                        
                        results = collection.query(
                            expr=f'doc_id == "{doc_id}" and version == {version}',
                            output_fields=["count(*)"]
                        )
                        
                        if results and results[0].get("count(*)", 0) > 0:
                            has_vectors = True
                            break
                except Exception as e:
                    logger.warning(f"Error checking {node_type}: {e}")
            
            if not has_vectors:
                need_backfill.append((doc_id, version, node_count))
        
        return need_backfill
        
    finally:
        db.close()


def run_backfill(
    docs: List[Tuple[str, int, int]],
    sync: bool = False,
    dry_run: bool = False
) -> None:
    """Run backfill for documents.
    
    Args:
        docs: List of (doc_id, version, node_count) tuples
        sync: Run synchronously instead of queueing
        dry_run: Just print what would be done
    """
    logger.info(f"Backfill: {len(docs)} documents need embedding")
    
    if not docs:
        logger.info("Nothing to backfill")
        return
    
    for i, (doc_id, version, node_count) in enumerate(docs, 1):
        logger.info(f"[{i}/{len(docs)}] {doc_id} v{version}: {node_count} nodes")
        
        if dry_run:
            continue
        
        if sync:
            # Run synchronously
            from app.tasks.embed_nodes import embed_document_nodes_sync
            
            try:
                result = embed_document_nodes_sync(doc_id, version)
                logger.info(f"  Result: {result}")
            except Exception as e:
                logger.error(f"  Failed: {e}")
        else:
            # Queue via Celery
            from app.tasks.embed_nodes import embed_nodes_task
            
            try:
                task = embed_nodes_task.delay(doc_id, version)
                logger.info(f"  Queued task: {task.id}")
            except Exception as e:
                logger.error(f"  Failed to queue: {e}")
    
    if dry_run:
        logger.info("Dry run complete - no changes made")
    else:
        logger.info("Backfill complete")


def main():
    parser = argparse.ArgumentParser(description="Backfill graph node embeddings")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Run synchronously instead of queueing tasks"
    )
    parser.add_argument(
        "--doc-id",
        help="Only backfill specific document"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Graph Node Embedding Backfill")
    logger.info("=" * 60)
    
    # Find docs needing backfill
    docs = get_docs_needing_backfill(args.doc_id)
    
    if not docs:
        logger.info("All documents already have embeddings")
        return 0
    
    logger.info(f"Found {len(docs)} documents needing backfill:")
    for doc_id, version, count in docs[:10]:  # Show first 10
        logger.info(f"  - {doc_id} v{version}: {count} nodes")
    
    if len(docs) > 10:
        logger.info(f"  ... and {len(docs) - 10} more")
    
    # Run backfill
    run_backfill(docs, sync=args.sync, dry_run=args.dry_run)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
