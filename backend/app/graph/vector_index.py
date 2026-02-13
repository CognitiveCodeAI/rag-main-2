"""Milvus vector indexing for graph nodes.

Creates and manages separate collections for different node types:
- graph_chunks_v2: Chunk node embeddings (with metadata fields)
- graph_figures_v2: Figure node embeddings (with metadata fields)
- graph_tables_v2: Table node embeddings (with metadata fields)

V2 collections include metadata fields for filtered search:
- year (int, -1 = unknown)
- doc_type (string, "" = unknown)
- department (string, "" = unknown)
- authority_tier (int, 0 = unknown)
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from pymilvus import (
    connections,
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

# Version configuration - switch between v1 and v2 collections
ACTIVE_COLLECTION_VERSION = "v2"  # "v1" or "v2"

# V1 Collection names (legacy, no metadata fields)
COLLECTION_CHUNKS_V1 = "graph_chunks_v1"
COLLECTION_FIGURES_V1 = "graph_figures_v1"
COLLECTION_TABLES_V1 = "graph_tables_v1"

# V2 Collection names (with metadata fields)
COLLECTION_CHUNKS_V2 = "graph_chunks_v2"
COLLECTION_FIGURES_V2 = "graph_figures_v2"
COLLECTION_TABLES_V2 = "graph_tables_v2"

# V1 node type to collection mapping
NODE_TYPE_COLLECTIONS_V1 = {
    "chunk": COLLECTION_CHUNKS_V1,
    "figure": COLLECTION_FIGURES_V1,
    "table": COLLECTION_TABLES_V1,
}

# V2 node type to collection mapping
NODE_TYPE_COLLECTIONS_V2 = {
    "chunk": COLLECTION_CHUNKS_V2,
    "figure": COLLECTION_FIGURES_V2,
    "table": COLLECTION_TABLES_V2,
}

# V3 Collection names (with ACL fields)
COLLECTION_CHUNKS_V3 = "graph_chunks_v3"
COLLECTION_FIGURES_V3 = "graph_figures_v3"
COLLECTION_TABLES_V3 = "graph_tables_v3"

NODE_TYPE_COLLECTIONS_V3 = {
    "chunk": COLLECTION_CHUNKS_V3,
    "figure": COLLECTION_FIGURES_V3,
    "table": COLLECTION_TABLES_V3,
}

# Default to active version
NODE_TYPE_COLLECTIONS = (
    NODE_TYPE_COLLECTIONS_V2 if ACTIVE_COLLECTION_VERSION == "v2"
    else NODE_TYPE_COLLECTIONS_V1
)

# Sentinel values for unknown metadata
UNKNOWN_YEAR = -1
UNKNOWN_AUTHORITY_TIER = 0
UNKNOWN_STRING = ""


@dataclass
class VectorRecord:
    """A vector record for indexing.
    
    V2 adds metadata fields for filtered search.
    """
    node_id: str
    doc_id: str
    version: int
    page_no: Optional[int]
    vector: List[float]
    
    # V2 metadata fields (use sentinels for unknowns)
    year: int = UNKNOWN_YEAR
    doc_type: str = UNKNOWN_STRING
    department: str = UNKNOWN_STRING
    authority_tier: int = UNKNOWN_AUTHORITY_TIER

    # V3 ACL fields
    tenant_id: str = ""
    visibility: str = "public"
    policy_version: int = 1


class GraphVectorIndex:
    """Milvus vector index for graph nodes.
    
    Supports v1 (basic) and v2 (with metadata fields) collection schemas.
    V2 collections include year, doc_type, department, authority_tier for filtering.
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        dim: Optional[int] = None,
        collection_version: str = ACTIVE_COLLECTION_VERSION
    ):
        """Initialize vector index.
        
        Args:
            host: Milvus host (default from config)
            port: Milvus port (default from config)
            dim: Vector dimension (default from config)
            collection_version: "v1" or "v2" (default: ACTIVE_COLLECTION_VERSION)
        """
        settings = get_settings()
        
        self.host = host or settings.milvus_host
        self.port = port or settings.milvus_port
        self.dim = dim or settings.embedding_dim
        self.collection_version = collection_version
        
        # Select collection mapping based on version
        if collection_version == "v3":
            self.node_type_collections = NODE_TYPE_COLLECTIONS_V3
        elif collection_version == "v2":
            self.node_type_collections = NODE_TYPE_COLLECTIONS_V2
        else:
            self.node_type_collections = NODE_TYPE_COLLECTIONS_V1
        
        self._connected = False
        self._collections: Dict[str, Collection] = {}
    
    def connect(self) -> None:
        """Connect to Milvus."""
        if self._connected:
            return
        
        try:
            connections.connect(
                alias="default",
                host=self.host,
                port=self.port
            )
            self._connected = True
            logger.info(f"Connected to Milvus at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            raise
    
    def ensure_collections(self) -> None:
        """Ensure all collections exist with proper schema."""
        self.connect()
        
        for node_type, collection_name in self.node_type_collections.items():
            self._ensure_collection(collection_name, node_type)
    
    def _ensure_collection(self, name: str, node_type: str) -> Collection:
        """Ensure a collection exists.
        
        Args:
            name: Collection name
            node_type: Node type for logging
            
        Returns:
            Collection object
        """
        if name in self._collections:
            return self._collections[name]
        
        if utility.has_collection(name):
            logger.info(f"Collection {name} already exists")
            collection = Collection(name)
        else:
            logger.info(f"Creating collection {name} for {node_type} nodes")
            collection = self._create_collection(name)
        
        # Ensure index exists
        self._ensure_index(collection)
        
        # Load collection for search
        collection.load()
        
        self._collections[name] = collection
        return collection
    
    def _create_collection(self, name: str) -> Collection:
        """Create a new collection with appropriate schema.
        
        V1 collections have basic fields.
        V2 collections have additional metadata fields for filtered search.
        
        Args:
            name: Collection name
            
        Returns:
            Collection object
        """
        # Base fields (v1 and v2)
        fields = [
            FieldSchema(name="node_id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
            FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="version", dtype=DataType.INT32),
            FieldSchema(name="page_no", dtype=DataType.INT32),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=self.dim),
        ]
        
        # V2 adds metadata fields for filtering
        if self.collection_version in ("v2", "v3"):
            fields.extend([
                # year=-1 means unknown, allows filtering like "year == 2020"
                FieldSchema(name="year", dtype=DataType.INT32),
                # Empty string means unknown
                FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="department", dtype=DataType.VARCHAR, max_length=64),
                # authority_tier=0 means unknown, 1=highest, 2=medium, 3=low
                FieldSchema(name="authority_tier", dtype=DataType.INT32),
            ])

        # V3 adds ACL fields for access control pre-filtering
        if self.collection_version == "v3":
            fields.extend([
                FieldSchema(name="tenant_id", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="visibility", dtype=DataType.VARCHAR, max_length=16),
                FieldSchema(name="policy_version", dtype=DataType.INT32),
            ])
        
        schema = CollectionSchema(
            fields=fields,
            description=f"Graph RAG node vectors - {name} ({self.collection_version})"
        )
        
        collection = Collection(name=name, schema=schema)
        
        logger.info(
            f"Created collection {name} with dim={self.dim}, "
            f"version={self.collection_version}, fields={len(fields)}"
        )
        
        return collection
    
    def _ensure_index(self, collection: Collection) -> None:
        """Ensure vector index exists on collection.
        
        Args:
            collection: Collection object
        """
        # Check if index exists
        indexes = collection.indexes
        has_vector_index = any(idx.field_name == "vector" for idx in indexes)
        
        if not has_vector_index:
            logger.info(f"Creating IVF_FLAT index on {collection.name}")
            
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
            
            collection.create_index(
                field_name="vector",
                index_params=index_params
            )
    
    def insert(
        self,
        node_type: str,
        records: List[VectorRecord]
    ) -> int:
        """Insert vector records into the appropriate collection.
        
        V2 collections store additional metadata fields.
        
        Args:
            node_type: Type of nodes (chunk, figure, table)
            records: List of VectorRecord to insert
            
        Returns:
            Number of records inserted
        """
        if not records:
            return 0
        
        collection_name = self.node_type_collections.get(node_type)
        if not collection_name:
            raise ValueError(f"Unknown node type: {node_type}")
        
        self.connect()
        collection = self._ensure_collection(collection_name, node_type)
        
        # Prepare base data (v1 and v2)
        data = [
            [r.node_id for r in records],
            [r.doc_id for r in records],
            [r.version for r in records],
            [r.page_no or 0 for r in records],
            [r.vector for r in records],
        ]
        
        # V2/V3 adds metadata fields
        if self.collection_version in ("v2", "v3"):
            data.extend([
                [r.year if r.year is not None else UNKNOWN_YEAR for r in records],
                [r.doc_type if r.doc_type else UNKNOWN_STRING for r in records],
                [r.department if r.department else UNKNOWN_STRING for r in records],
                [r.authority_tier if r.authority_tier is not None else UNKNOWN_AUTHORITY_TIER for r in records],
            ])

        # V3 adds ACL fields
        if self.collection_version == "v3":
            data.extend([
                [r.tenant_id or "" for r in records],
                [r.visibility or "public" for r in records],
                [r.policy_version if r.policy_version is not None else 1 for r in records],
            ])
        
        # Insert without explicit flush (Milvus server has flush issues)
        result = collection.insert(data)
        logger.info(f"Inserted {len(records)} vectors into {collection_name} (auto-flush pending)")
        
        return len(records)
    
    def build_acl_filter(self, entitlements) -> Optional[str]:
        """Build Milvus boolean expression for ACL pre-filtering.

        IMPORTANT: This is an OPTIMIZATION only, not the authorization gate.
        Postgres (via ACLEnforcer) is always the final check.

        Args:
            entitlements: Entitlements object (or None if ACL disabled)

        Returns:
            Milvus boolean expression string, or None
        """
        if entitlements is None or self.collection_version != "v3":
            return None

        parts = [f'tenant_id == "{entitlements.tenant_id}"']

        # For non-admins, exclude restricted docs at vector level.
        # Internal/restricted will still be caught by Postgres gate.
        if not entitlements.is_admin:
            parts.append('visibility != "restricted"')

        return " && ".join(parts)

    def search(
        self,
        node_type: str,
        query_vector: List[float],
        top_k: int = 10,
        doc_id_filter: Optional[str] = None,
        filter_expr: Optional[str] = None,
        acl_filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors with optional metadata filtering.

        Args:
            node_type: Type of nodes to search
            query_vector: Query vector
            top_k: Number of results to return
            doc_id_filter: Optional filter by doc_id
            filter_expr: Optional Milvus filter expression for metadata
                         e.g., 'year == 2020', 'year >= 2019 && year <= 2021'
            acl_filter_expr: Optional ACL pre-filter (optimization, not security gate)

        Returns:
            List of search results with node_id, score, metadata
        """
        collection_name = self.node_type_collections.get(node_type)
        if not collection_name:
            raise ValueError(f"Unknown node type: {node_type}")
        
        self.connect()
        collection = self._ensure_collection(collection_name, node_type)
        
        # Build expression filter
        expr_parts = []
        if doc_id_filter:
            expr_parts.append(f'doc_id == "{doc_id_filter}"')
        if filter_expr:
            expr_parts.append(f'({filter_expr})')
        if acl_filter_expr:
            expr_parts.append(f'({acl_filter_expr})')

        expr = " && ".join(expr_parts) if expr_parts else None
        
        # Search params
        search_params = {
            "metric_type": "COSINE",
            "params": {"nprobe": 10}
        }
        
        # Output fields depend on collection version
        output_fields = ["node_id", "doc_id", "version", "page_no"]
        if self.collection_version in ("v2", "v3"):
            output_fields.extend(["year", "doc_type", "department", "authority_tier"])
        if self.collection_version == "v3":
            output_fields.extend(["tenant_id", "visibility", "policy_version"])
        
        results = collection.search(
            data=[query_vector],
            anns_field="vector",
            param=search_params,
            limit=top_k,
            expr=expr,
            output_fields=output_fields,
            consistency_level="Eventually"  # Find unflushed data
        )
        
        # Format results
        hits = []
        for result in results[0]:
            hit = {
                "node_id": result.entity.get("node_id"),
                "doc_id": result.entity.get("doc_id"),
                "version": result.entity.get("version"),
                "page_no": result.entity.get("page_no"),
                "score": result.score,
                "node_type": node_type,
            }
            
            # V2/V3 includes metadata fields
            if self.collection_version in ("v2", "v3"):
                year = result.entity.get("year")
                hit["year"] = year if year != UNKNOWN_YEAR else None

                doc_type = result.entity.get("doc_type")
                hit["doc_type"] = doc_type if doc_type != UNKNOWN_STRING else None

                department = result.entity.get("department")
                hit["department"] = department if department != UNKNOWN_STRING else None

                authority_tier = result.entity.get("authority_tier")
                hit["authority_tier"] = authority_tier if authority_tier != UNKNOWN_AUTHORITY_TIER else None

            # V3 includes ACL fields
            if self.collection_version == "v3":
                hit["tenant_id"] = result.entity.get("tenant_id", "")
                hit["visibility"] = result.entity.get("visibility", "public")
            
            hits.append(hit)
        
        return hits
    
    def search_with_fallback(
        self,
        node_type: str,
        query_vector: List[float],
        top_k: int = 10,
        doc_id_filter: Optional[str] = None,
        filter_expr: Optional[str] = None,
        acl_filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search with automatic fallback to alternate collection version.

        If the current version returns no results, tries the other version.
        This handles cases where document was indexed in a different version
        than the current default.

        Args:
            node_type: Type of nodes to search
            query_vector: Query vector
            top_k: Number of results to return
            doc_id_filter: Optional filter by doc_id
            filter_expr: Optional Milvus filter expression for metadata
            acl_filter_expr: Optional ACL pre-filter (optimization, not security gate)

        Returns:
            List of search results with node_id, score, metadata
        """
        # Try primary collection
        results = self.search(node_type, query_vector, top_k, doc_id_filter, filter_expr, acl_filter_expr)

        if results:
            return results

        # Fallback to alternate version
        fallback_version = "v1" if self.collection_version in ("v2", "v3") else "v2"
        logger.info(
            f"[VectorIndex] No results in {self.collection_version}, "
            f"trying {fallback_version} fallback"
        )
        
        try:
            fallback_index = GraphVectorIndex(collection_version=fallback_version)
            # Note: filter_expr may not work on v1 collections (no metadata fields)
            fallback_filter = None if fallback_version == "v1" else filter_expr
            results = fallback_index.search(
                node_type, query_vector, top_k, doc_id_filter, fallback_filter
            )
            
            if results:
                logger.info(
                    f"[VectorIndex] Found {len(results)} results in {fallback_version} fallback"
                )
        except Exception as e:
            logger.warning(f"[VectorIndex] Fallback search failed: {e}")
        
        return results
    
    def search_all_types(
        self,
        query_vector: List[float],
        top_k: int = 10,
        node_types: Optional[List[str]] = None,
        filter_expr: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search across multiple node type collections.
        
        Args:
            query_vector: Query vector
            top_k: Number of results per collection
            node_types: Types to search (default: all)
            filter_expr: Optional Milvus filter expression for metadata
            
        Returns:
            Combined and sorted results
        """
        if node_types is None:
            node_types = list(self.node_type_collections.keys())
        
        all_results = []
        
        for node_type in node_types:
            try:
                results = self.search(
                    node_type, 
                    query_vector, 
                    top_k,
                    filter_expr=filter_expr
                )
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Search failed for {node_type}: {e}")
        
        # Sort by score (higher is better for COSINE)
        all_results.sort(key=lambda x: x["score"], reverse=True)
        
        return all_results[:top_k]
    
    def delete_by_doc(
        self,
        doc_id: str,
        version: Optional[int] = None
    ) -> Dict[str, int]:
        """Delete vectors for a document.
        
        Args:
            doc_id: Document ID
            version: Optional version (deletes all versions if None)
            
        Returns:
            Dict of collection_name -> deleted count
        """
        self.connect()
        
        deleted = {}
        
        for node_type, collection_name in self.node_type_collections.items():
            collection = self._ensure_collection(collection_name, node_type)
            
            if version is not None:
                expr = f'doc_id == "{doc_id}" and version == {version}'
            else:
                expr = f'doc_id == "{doc_id}"'
            
            # Get count before delete
            before_count = collection.query(expr, output_fields=["count(*)"])
            
            collection.delete(expr)
            collection.flush()
            
            deleted[collection_name] = before_count[0].get("count(*)", 0) if before_count else 0
        
        logger.info(f"Deleted vectors for doc {doc_id}: {deleted}")
        
        return deleted
    
    def get_collection_stats(self, node_type: str) -> Dict[str, Any]:
        """Get statistics for a collection.
        
        Args:
            node_type: Node type
            
        Returns:
            Dict with collection statistics
        """
        collection_name = self.node_type_collections.get(node_type)
        if not collection_name:
            raise ValueError(f"Unknown node type: {node_type}")
        
        self.connect()
        collection = self._ensure_collection(collection_name, node_type)

        # Prefer count(*) query because Milvus num_entities can remain stale
        # when inserts are not explicitly flushed.
        num_entities = collection.num_entities
        try:
            query_results = collection.query(
                expr="",
                output_fields=["count(*)"],
            )
            if query_results and len(query_results) > 0:
                queried_count = query_results[0].get("count(*)")
                if isinstance(queried_count, int):
                    num_entities = queried_count
        except Exception as e:
            logger.warning(
                f"Failed to query exact count for {collection_name}; using num_entities. "
                f"error={e}"
            )

        return {
            "name": collection_name,
            "num_entities": num_entities,
            "index_status": "indexed" if collection.indexes else "no_index",
            "version": self.collection_version,
        }
    
    def verify_v2_schema(self) -> Dict[str, Any]:
        """Verify v2 collections exist and have required metadata fields.
        
        Performs startup health check to fail fast if Milvus is misconfigured.
        V2 collections MUST have: year, doc_type, department, authority_tier fields.
        
        Returns:
            Dict with verification results
            
        Raises:
            RuntimeError: If v2 collections are missing or misconfigured
        """
        if self.collection_version != "v2":
            return {
                "status": "skipped",
                "reason": f"Not v2 collections (version={self.collection_version})"
            }
        
        self.connect()
        
        required_fields = {'year', 'doc_type', 'department', 'authority_tier'}
        v2_collections = [COLLECTION_CHUNKS_V2, COLLECTION_FIGURES_V2, COLLECTION_TABLES_V2]
        
        results = {
            "status": "ok",
            "version": "v2",
            "collections_verified": [],
            "errors": []
        }
        
        for collection_name in v2_collections:
            # Check collection exists
            if not utility.has_collection(collection_name):
                error = f"V2 collection missing: {collection_name}"
                results["errors"].append(error)
                logger.error(error)
                continue
            
            # Check schema has required fields
            collection = Collection(collection_name)
            field_names = {f.name for f in collection.schema.fields}
            
            missing = required_fields - field_names
            if missing:
                error = f"{collection_name} missing required metadata fields: {missing}"
                results["errors"].append(error)
                logger.error(error)
            else:
                results["collections_verified"].append(collection_name)
                logger.info(f"V2 schema verified: {collection_name} has all required fields")
        
        if results["errors"]:
            results["status"] = "failed"
            error_msg = (
                f"V2 schema verification failed: {results['errors']}. "
                f"Ensure Milvus collections have been created with v2 schema."
            )
            raise RuntimeError(error_msg)
        
        logger.info(
            f"V2 schema verification passed: {len(results['collections_verified'])} collections verified"
        )
        
        return results


class MilvusSchemaError(Exception):
    """Raised when Milvus schema verification fails."""
    pass


def get_graph_vector_index(collection_version: str = ACTIVE_COLLECTION_VERSION) -> GraphVectorIndex:
    """Get a GraphVectorIndex instance.

    Args:
        collection_version: "v1", "v2", or "v3" (default: ACTIVE_COLLECTION_VERSION)

    Returns:
        GraphVectorIndex instance
    """
    return GraphVectorIndex(collection_version=collection_version)
