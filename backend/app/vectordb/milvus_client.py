"""Milvus vector database client.

Creates and manages two collections:
- chunks_vec_content_v1: Semantic body similarity
- chunks_vec_contextual_v1: Structure-aware retrieval
"""

import json
import logging
import os
import re
from typing import Any, List

from pymilvus import (
    connections,
    utility,
    Collection,
    FieldSchema,
    CollectionSchema,
    DataType,
)

logger = logging.getLogger(__name__)


def _sanitize_string(value: str) -> str:
    """Sanitize a string value for safe use in Milvus expressions.
    
    Escapes backslashes and double quotes to prevent injection attacks.
    
    Args:
        value: The string to sanitize
        
    Returns:
        Sanitized string safe for use in expressions
    """
    if not isinstance(value, str):
        raise ValueError(f"Expected string, got {type(value)}")
    
    # Escape backslashes first, then double quotes
    sanitized = value.replace('\\', '\\\\').replace('"', '\\"')
    
    # Additional safety: remove/escape any control characters
    sanitized = re.sub(r'[\x00-\x1f]', '', sanitized)
    
    return sanitized


def _format_string_list(values: List[str]) -> str:
    """Format a list of strings for safe use in Milvus 'in' expressions.
    
    Args:
        values: List of string values
        
    Returns:
        Properly formatted string like '["val1", "val2"]'
    """
    sanitized = [_sanitize_string(v) for v in values]
    # Use json.dumps to ensure proper escaping
    return json.dumps(sanitized)

# Configuration (defaults match docker-compose.yml for local development)
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 19530
DEFAULT_DIM = 3072
ALIAS = "default"

# Collection names
COLLECTION_VEC_CONTENT = "chunks_vec_content_v1"
COLLECTION_VEC_CONTEXTUAL = "chunks_vec_contextual_v1"

# Index parameters
INDEX_PARAMS = {
    "metric_type": "COSINE",
    "index_type": "IVF_FLAT",
    "params": {"nlist": 256},
}

SEARCH_PARAMS = {
    "metric_type": "COSINE",
    "params": {"nprobe": 16},
}


class MilvusClient:
    """Milvus vector database client."""
    
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        dim: int = DEFAULT_DIM,
    ):
        """Initialize Milvus client.
        
        Args:
            host: Milvus host (defaults to env MILVUS_HOST)
            port: Milvus port (defaults to env MILVUS_PORT)
            dim: Vector dimension
        """
        self.host = host or os.getenv("MILVUS_HOST", DEFAULT_HOST)
        self.port = port or int(os.getenv("MILVUS_PORT", DEFAULT_PORT))
        self.dim = dim
        self._connected = False
        
        self.connect()
        self.ensure_collections()
    
    def connect(self) -> None:
        """Connect to Milvus."""
        if self._connected:
            return
        
        connections.connect(
            alias=ALIAS,
            host=self.host,
            port=self.port,
        )
        self._connected = True
        
        version = utility.get_server_version()
        logger.info(f"Connected to Milvus {version} at {self.host}:{self.port}")
    
    def disconnect(self) -> None:
        """Disconnect from Milvus."""
        if self._connected:
            connections.disconnect(ALIAS)
            self._connected = False
    
    def _create_collection_schema(self) -> CollectionSchema:
        """Create schema for chunk vector collections."""
        fields = [
            FieldSchema(
                name="chunk_id",
                dtype=DataType.VARCHAR,
                max_length=256,
                is_primary=True,
            ),
            FieldSchema(
                name="doc_id",
                dtype=DataType.VARCHAR,
                max_length=256,
            ),
            FieldSchema(
                name="version_id",
                dtype=DataType.VARCHAR,
                max_length=256,
            ),
            FieldSchema(
                name="authority_tier",
                dtype=DataType.VARCHAR,
                max_length=32,
            ),
            FieldSchema(
                name="embedding",
                dtype=DataType.FLOAT_VECTOR,
                dim=self.dim,
            ),
        ]
        return CollectionSchema(
            fields=fields,
            description="NPR chunk vectors",
        )
    
    def ensure_collections(self) -> None:
        """Ensure required collections exist."""
        schema = self._create_collection_schema()
        
        for collection_name in [COLLECTION_VEC_CONTENT, COLLECTION_VEC_CONTEXTUAL]:
            if not utility.has_collection(collection_name):
                logger.info(f"Creating collection: {collection_name}")
                collection = Collection(
                    name=collection_name,
                    schema=schema,
                )
                # Create index
                collection.create_index(
                    field_name="embedding",
                    index_params=INDEX_PARAMS,
                )
                logger.info(f"Created index on {collection_name}")
            else:
                logger.debug(f"Collection exists: {collection_name}")
    
    def insert_vectors(
        self,
        collection_name: str,
        chunk_ids: list[str],
        doc_ids: list[str],
        version_ids: list[str],
        authority_tiers: list[str],
        embeddings: list[list[float]],
    ) -> int:
        """Insert vectors into a collection.
        
        Args:
            collection_name: Target collection
            chunk_ids: List of chunk IDs (PKs)
            doc_ids: List of document IDs
            version_ids: List of version IDs
            authority_tiers: List of authority tiers
            embeddings: List of embedding vectors
        
        Returns:
            Number of vectors inserted
        """
        if not chunk_ids:
            return 0
        
        collection = Collection(collection_name)
        
        # Prepare data
        data = [
            chunk_ids,
            doc_ids,
            version_ids,
            authority_tiers,
            embeddings,
        ]
        
        # Insert
        result = collection.insert(data)
        logger.info(f"Inserted {len(chunk_ids)} vectors into {collection_name}")
        
        return len(chunk_ids)
    
    def upsert_vectors(
        self,
        collection_name: str,
        chunk_ids: list[str],
        doc_ids: list[str],
        version_ids: list[str],
        authority_tiers: list[str],
        embeddings: list[list[float]],
    ) -> int:
        """Upsert vectors into a collection (delete existing + insert).
        
        Args:
            collection_name: Target collection
            chunk_ids: List of chunk IDs (PKs)
            doc_ids: List of document IDs
            version_ids: List of version IDs
            authority_tiers: List of authority tiers
            embeddings: List of embedding vectors
        
        Returns:
            Number of vectors upserted
        """
        if not chunk_ids:
            return 0
        
        collection = Collection(collection_name)
        
        # Delete existing - use safe formatting to prevent injection
        safe_ids = _format_string_list(chunk_ids)
        expr = f'chunk_id in {safe_ids}'
        collection.delete(expr)
        
        # Insert new
        return self.insert_vectors(
            collection_name,
            chunk_ids,
            doc_ids,
            version_ids,
            authority_tiers,
            embeddings,
        )
    
    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar vectors.
        
        Args:
            collection_name: Target collection
            query_vector: Query embedding vector
            top_k: Number of results to return
            filters: Optional filters (e.g., {"doc_id": "..."})
        
        Returns:
            List of results with chunk_id, doc_id, score
        """
        collection = Collection(collection_name)
        collection.load()
        
        # Build filter expression with safe value handling
        expr = None
        if filters:
            conditions = []
            for key, value in filters.items():
                # Validate key is a valid field name (alphanumeric + underscore only)
                if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', key):
                    logger.warning(f"Skipping invalid filter key: {key}")
                    continue
                
                if isinstance(value, str):
                    # Sanitize string value to prevent injection
                    safe_value = _sanitize_string(value)
                    conditions.append(f'{key} == "{safe_value}"')
                elif isinstance(value, list):
                    # Use safe list formatting
                    safe_list = _format_string_list([str(v) for v in value])
                    conditions.append(f'{key} in {safe_list}')
            if conditions:
                expr = " && ".join(conditions)
        
        # Search
        results = collection.search(
            data=[query_vector],
            anns_field="embedding",
            param=SEARCH_PARAMS,
            limit=top_k,
            expr=expr,
            output_fields=["chunk_id", "doc_id", "version_id", "authority_tier"],
        )
        
        # Format results
        formatted = []
        for hits in results:
            for hit in hits:
                formatted.append({
                    "chunk_id": hit.entity.get("chunk_id"),
                    "doc_id": hit.entity.get("doc_id"),
                    "version_id": hit.entity.get("version_id"),
                    "authority_tier": hit.entity.get("authority_tier"),
                    "score": hit.score,
                })
        
        return formatted
    
    def get_collection_stats(self, collection_name: str) -> dict[str, Any]:
        """Get collection statistics with accurate entity count."""
        try:
            collection = Collection(collection_name)
            collection.load()
            # Use query with count to get accurate entity count
            # Milvus num_entities can be stale without flush
            results = collection.query(
                expr="",
                output_fields=["count(*)"],
            )
            if results and len(results) > 0:
                row_count = results[0].get("count(*)", 0)
            else:
                row_count = collection.num_entities
        except Exception as e:
            logger.warning(f"Failed to get accurate count for {collection_name}: {e}")
            try:
                collection = Collection(collection_name)
                row_count = collection.num_entities
            except Exception:
                row_count = 0
        return {
            "name": collection_name,
            "num_entities": row_count,
        }
    
    def delete_by_doc(
        self,
        collection_name: str,
        doc_id: str,
        version_id: str | None = None,
    ) -> None:
        """Delete vectors by document ID.
        
        Args:
            collection_name: Target collection
            doc_id: Document ID
            version_id: Optional version ID (all versions if None)
        """
        collection = Collection(collection_name)
        
        # Sanitize inputs to prevent injection
        safe_doc_id = _sanitize_string(doc_id)
        
        if version_id:
            safe_version_id = _sanitize_string(version_id)
            expr = f'doc_id == "{safe_doc_id}" && version_id == "{safe_version_id}"'
        else:
            expr = f'doc_id == "{safe_doc_id}"'
        
        collection.delete(expr)
        logger.info(f"Deleted vectors: doc_id={doc_id} from {collection_name}")


# Singleton instance
_milvus_client: MilvusClient | None = None


def get_milvus_client() -> MilvusClient:
    """Get or create singleton Milvus client."""
    global _milvus_client
    if _milvus_client is None:
        _milvus_client = MilvusClient()
    return _milvus_client
