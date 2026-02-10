"""Multi-view vector record builder.

Builds schema-compliant records with all 4 views:
- vec_content: Semantic body (doc.chunk.embed.v1)
- vec_contextual: Structure-aware (header + chunk)
- vec_title_heading: Hierarchical (title + heading_context)
- vec_entities: Entity-based (entities_str)
"""

import logging
from datetime import datetime, timezone
from typing import Any

from .templates import TemplateRenderer
from .client import EmbeddingClient

logger = logging.getLogger(__name__)

# Configuration
EMBEDDING_BUNDLE_VERSION = "1.0"
NORMALIZATION_ID = "npr-v1"
DEFAULT_MODEL = "text-embedding-3-large"
DEFAULT_DIM = 3072


class MultiViewVectorRecordBuilder:
    """Builder for multi-view vector records."""
    
    def __init__(
        self,
        embedding_client: EmbeddingClient | None = None,
        bundle_version: str = EMBEDDING_BUNDLE_VERSION,
    ):
        """Initialize builder.
        
        Args:
            embedding_client: EmbeddingClient instance (created if not provided)
            bundle_version: Embedding bundle version
        """
        self.embedding_client = embedding_client or EmbeddingClient()
        self.bundle_version = bundle_version
        self.model_id = self.embedding_client.model
        self.dim = self.embedding_client.dim
    
    def build_record(
        self,
        chunk: dict[str, Any],
        ir: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a multi-view vector record for a single chunk.
        
        Args:
            chunk: ChunkRecord dict
            ir: Optional DocumentIR dict
        
        Returns:
            MultiViewVectorRecord dict conforming to schema
        """
        chunk_ref = chunk.get("chunk_ref", {})
        chunk_id = chunk_ref.get("chunk_id", "unknown")
        doc_id = chunk_ref.get("doc_id", "unknown")
        version_id = chunk_ref.get("version_id", "unknown")
        
        # Render all views
        rendered_views = TemplateRenderer.render_all_views(chunk, ir)
        
        # Collect texts for batch embedding
        view_texts = []
        view_ids = []
        view_metadata = {}
        
        for view_id, (rendered, fingerprint, template_version) in rendered_views.items():
            view_texts.append(rendered)
            view_ids.append(view_id)
            view_metadata[view_id] = {
                "fingerprint": fingerprint,
                "template_version": template_version,
                "rendered_bytes": len(rendered.encode("utf-8")),
            }
        
        # Batch embed all views
        embeddings, embed_meta = self.embedding_client.embed_texts(view_texts)
        
        # Build views dict
        views = {}
        for i, view_id in enumerate(view_ids):
            meta = view_metadata[view_id]
            
            # Determine template ID based on view
            if view_id == "vec_content":
                template_id = "doc.chunk.embed.v1"
            elif view_id == "vec_contextual":
                template_id = "doc.contextual.v1"
            elif view_id == "vec_title_heading":
                template_id = "doc.title_heading.v1"
            elif view_id == "vec_entities":
                template_id = "doc.entities.v1"
            else:
                template_id = "unknown"
            
            views[view_id] = {
                "view_id": view_id,
                "embedding_model_id": self.model_id,
                "dim": self.dim,
                "normalize": self.embedding_client.normalize,
                "input_template_id": template_id,
                "input_template_version": meta["template_version"],
                "input_fingerprint": meta["fingerprint"],
                "rendering": {
                    "rendered_input_bytes": meta["rendered_bytes"],
                },
                "vector": embeddings[i],
            }
        
        # Build record
        record_id = f"vec:{chunk_id}:{self.bundle_version}"
        created_at = datetime.now(timezone.utc).isoformat()
        
        record = {
            "schema_version": "1.0",
            "record_id": record_id,
            "created_at": created_at,
            "chunk_ref": {
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "version_id": version_id,
                "section_path": chunk_ref.get("section_path", []),
                "chunk_type": chunk_ref.get("chunk_type", "text"),
                "start_offset": chunk_ref.get("start_offset", 0),
                "end_offset": chunk_ref.get("end_offset", 0),
            },
            "embedding_bundle_version": self.bundle_version,
            "preprocessing": {
                "normalization_id": NORMALIZATION_ID,
                "language": None,
                "tokenizer_hint": "cl100k_base",
            },
            "views": views,
        }
        
        return record
    
    def build_bundle(
        self,
        chunks: list[dict[str, Any]],
        ir: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build embedding bundle for multiple chunks.
        
        Args:
            chunks: List of ChunkRecord dicts
            ir: Optional DocumentIR dict
        
        Returns:
            Bundle dict with all vector records
        """
        if not chunks:
            return {
                "schema_version": "1.0",
                "bundle_version": self.bundle_version,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "model_id": self.model_id,
                "dim": self.dim,
                "records": [],
            }
        
        # Get doc info from first chunk
        first_ref = chunks[0].get("chunk_ref", {})
        doc_id = first_ref.get("doc_id", "unknown")
        version_id = first_ref.get("version_id", "unknown")
        
        logger.info(f"Building embedding bundle: doc={doc_id}, chunks={len(chunks)}")
        
        # Batch all texts for efficient embedding
        all_texts = []
        chunk_view_map = []  # (chunk_idx, view_id, fingerprint, template_version, rendered_bytes)
        
        for chunk_idx, chunk in enumerate(chunks):
            rendered_views = TemplateRenderer.render_all_views(chunk, ir)
            for view_id, (rendered, fingerprint, template_version) in rendered_views.items():
                all_texts.append(rendered)
                chunk_view_map.append((
                    chunk_idx,
                    view_id,
                    fingerprint,
                    template_version,
                    len(rendered.encode("utf-8")),
                ))
        
        # Batch embed all at once
        logger.info(f"Embedding {len(all_texts)} texts ({len(chunks)} chunks x 4 views)")
        all_embeddings, embed_meta = self.embedding_client.embed_texts(all_texts)
        
        # Organize embeddings by chunk
        chunk_embeddings: dict[int, dict[str, Any]] = {i: {} for i in range(len(chunks))}
        
        for i, (chunk_idx, view_id, fingerprint, template_version, rendered_bytes) in enumerate(chunk_view_map):
            chunk_embeddings[chunk_idx][view_id] = {
                "embedding": all_embeddings[i],
                "fingerprint": fingerprint,
                "template_version": template_version,
                "rendered_bytes": rendered_bytes,
            }
        
        # Build records
        records = []
        created_at = datetime.now(timezone.utc).isoformat()
        
        for chunk_idx, chunk in enumerate(chunks):
            chunk_ref = chunk.get("chunk_ref", {})
            chunk_id = chunk_ref.get("chunk_id", "unknown")
            
            views = {}
            for view_id, view_data in chunk_embeddings[chunk_idx].items():
                # Determine template ID
                if view_id == "vec_content":
                    template_id = "doc.chunk.embed.v1"
                elif view_id == "vec_contextual":
                    template_id = "doc.contextual.v1"
                elif view_id == "vec_title_heading":
                    template_id = "doc.title_heading.v1"
                elif view_id == "vec_entities":
                    template_id = "doc.entities.v1"
                else:
                    template_id = "unknown"
                
                views[view_id] = {
                    "view_id": view_id,
                    "embedding_model_id": self.model_id,
                    "dim": self.dim,
                    "normalize": self.embedding_client.normalize,
                    "input_template_id": template_id,
                    "input_template_version": view_data["template_version"],
                    "input_fingerprint": view_data["fingerprint"],
                    "rendering": {
                        "rendered_input_bytes": view_data["rendered_bytes"],
                    },
                    "vector": view_data["embedding"],
                }
            
            record = {
                "schema_version": "1.0",
                "record_id": f"vec:{chunk_id}:{self.bundle_version}",
                "created_at": created_at,
                "chunk_ref": {
                    "chunk_id": chunk_id,
                    "doc_id": chunk_ref.get("doc_id", ""),
                    "version_id": chunk_ref.get("version_id", ""),
                    "section_path": chunk_ref.get("section_path", []),
                    "chunk_type": chunk_ref.get("chunk_type", "text"),
                    "start_offset": chunk_ref.get("start_offset", 0),
                    "end_offset": chunk_ref.get("end_offset", 0),
                },
                "embedding_bundle_version": self.bundle_version,
                "preprocessing": {
                    "normalization_id": NORMALIZATION_ID,
                    "language": None,
                    "tokenizer_hint": "cl100k_base",
                },
                "views": views,
            }
            records.append(record)
        
        bundle = {
            "schema_version": "1.0",
            "bundle_version": self.bundle_version,
            "created_at": created_at,
            "doc_id": doc_id,
            "version_id": version_id,
            "model_id": self.model_id,
            "dim": self.dim,
            "record_count": len(records),
            "total_tokens": embed_meta.get("total_tokens", 0),
            "records": records,
        }
        
        logger.info(
            f"Built bundle: {len(records)} records, "
            f"{embed_meta.get('total_tokens', 0)} tokens"
        )
        
        return bundle
