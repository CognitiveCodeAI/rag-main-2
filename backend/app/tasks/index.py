"""Vector indexing Celery task."""

import logging
from datetime import datetime
from typing import Any

from app.worker import celery_app
from app.storage.minio_client import get_storage_client
from app.vectordb.milvus_client import (
    get_milvus_client,
    COLLECTION_VEC_CONTENT,
    COLLECTION_VEC_CONTEXTUAL,
)
from app.db.session import session_scope
from app.db.models import VectorIndexVersion

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def index_vectors_task(
    self,
    doc_id: str,
    version_id: str,
) -> dict[str, Any]:
    """Index vectors from embedding bundle into Milvus.
    
    Steps:
    1. Load embedding bundle from MinIO
    2. For vec_content and vec_contextual views:
       - Upsert vectors into respective Milvus collection
    3. Track version in Postgres
    
    Args:
        doc_id: Document ID
        version_id: Version ID
    
    Returns:
        Dict with status and results
    """
    storage = get_storage_client()
    milvus = get_milvus_client()
    
    try:
        logger.info(f"Starting vector indexing: doc={doc_id}, version={version_id}")
        
        # 1. Load embedding bundle from MinIO
        bundle = storage.get_embeddings(doc_id, version_id)
        records = bundle.get("records", [])
        bundle_version = bundle.get("bundle_version", "1.0")
        
        logger.info(f"Loaded bundle: {len(records)} records, version={bundle_version}")
        
        if not records:
            return {
                "status": "completed",
                "doc_id": doc_id,
                "version_id": version_id,
                "message": "No records to index",
            }
        
        # Check if already indexed with same bundle version
        with session_scope() as session:
            existing = session.query(VectorIndexVersion).filter_by(
                doc_id=doc_id,
                version_id=version_id,
                collection_name=COLLECTION_VEC_CONTENT,
                bundle_version=bundle_version,
            ).first()
            
            if existing:
                logger.info(f"Already indexed with bundle version {bundle_version}")
                return {
                    "status": "completed",
                    "doc_id": doc_id,
                    "version_id": version_id,
                    "message": "Already indexed",
                    "bundle_version": bundle_version,
                }
        
        # 2. Index each view into its collection
        results = {}
        
        for view_id, collection_name in [
            ("vec_content", COLLECTION_VEC_CONTENT),
            ("vec_contextual", COLLECTION_VEC_CONTEXTUAL),
        ]:
            chunk_ids = []
            doc_ids = []
            version_ids = []
            authority_tiers = []
            embeddings = []
            
            for record in records:
                chunk_ref = record.get("chunk_ref", {})
                views = record.get("views", {})
                
                if view_id not in views:
                    continue
                
                view = views[view_id]
                vector = view.get("vector", [])
                
                if not vector:
                    continue
                
                chunk_ids.append(chunk_ref.get("chunk_id", ""))
                doc_ids.append(chunk_ref.get("doc_id", ""))
                version_ids.append(chunk_ref.get("version_id", ""))
                
                # Get authority tier from metadata if available
                # Default to empty string for Phase 2
                authority_tiers.append("")
                embeddings.append(vector)
            
            if chunk_ids:
                # Upsert vectors
                count = milvus.upsert_vectors(
                    collection_name=collection_name,
                    chunk_ids=chunk_ids,
                    doc_ids=doc_ids,
                    version_ids=version_ids,
                    authority_tiers=authority_tiers,
                    embeddings=embeddings,
                )
                results[view_id] = count
                
                # 3. Track version in Postgres
                with session_scope() as session:
                    index_record = VectorIndexVersion(
                        doc_id=doc_id,
                        version_id=version_id,
                        collection_name=collection_name,
                        bundle_version=bundle_version,
                        vector_count=count,
                    )
                    session.merge(index_record)
                
                logger.info(f"Indexed {count} vectors into {collection_name}")
        
        return {
            "status": "completed",
            "doc_id": doc_id,
            "version_id": version_id,
            "bundle_version": bundle_version,
            "indexed": results,
        }
    
    except Exception as e:
        logger.error(f"Vector indexing failed: doc={doc_id}, error={e}")
        
        # Retry with exponential backoff
        try:
            self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            return {
                "status": "failed",
                "doc_id": doc_id,
                "version_id": version_id,
                "error": str(e),
            }
