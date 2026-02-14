"""Content registry manager for true content identity.

Prevents logical duplicates when the same content is uploaded
from different source_uri paths by mapping content_hash → canonical_doc_id.

Uses atomic upsert (INSERT ... ON CONFLICT) for race condition safety.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.db.graph_models import ContentRegistry

logger = logging.getLogger(__name__)


@dataclass
class ContentIdentity:
    """Result of content identity lookup."""
    content_hash: str
    canonical_doc_id: str
    is_duplicate: bool  # True if this content_hash was seen before
    alias_count: int  # Number of doc_ids pointing to this content


class ContentRegistryManager:
    """Manages content-to-canonical-doc-id mapping.
    
    Uses atomic upsert pattern for concurrency safety - if two ingests
    happen simultaneously with the same content, whoever wins the race
    becomes canonical, and subsequent inserts increment alias_count.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def resolve_or_register(
        self,
        content_hash: str,
        doc_id: str,
        source_uri: str,
        tenant_id: Optional[str] = None,
    ) -> ContentIdentity:
        """Resolve canonical doc_id for content, or register if new.

        Uses atomic upsert (INSERT ... ON CONFLICT) to handle race conditions.
        Whoever wins the race becomes canonical; subsequent calls increment alias_count.

        Args:
            content_hash: SHA256 hash of file content
            doc_id: Doc ID for this upload (based on source_uri)
            source_uri: Source URI of this upload
            tenant_id: Optional tenant ID (defaults to 'default')

        Returns:
            ContentIdentity with canonical_doc_id and duplicate status
        """
        # SECURITY ASSUMPTION:
        # Tenant defaulting must stay consistent with ingest duplicate checks; drift causes cross-tenant dedupe behavior changes.
        # Normalize tenant_id to 'default' when None for consistent lookups
        effective_tenant = tenant_id if tenant_id else 'default'

        # First, check if entry exists to determine if this is a duplicate
        # Always scope lookup by (tenant_id, content_hash)
        existing_query = self.db.query(ContentRegistry).filter(
            ContentRegistry.content_hash == content_hash,
            ContentRegistry.tenant_id == effective_tenant
        )
        existing_before = existing_query.first()

        was_existing = existing_before is not None

        # Atomic upsert: INSERT or UPDATE on conflict
        # This handles race conditions - whoever wins becomes canonical
        values = dict(
            tenant_id=effective_tenant,
            content_hash=content_hash,
            canonical_doc_id=doc_id,
            source_uri_first_seen=source_uri,
            latest_doc_id=doc_id,
            alias_count=1,
        )

        # Build upsert statement using composite PK (tenant_id, content_hash)
        insert_stmt = insert(ContentRegistry).values(**values)
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=['tenant_id', 'content_hash'],
            set_={
                'latest_doc_id': doc_id,
                'alias_count': ContentRegistry.alias_count + 1,
            },
        )
        stmt = stmt.returning(
            ContentRegistry.canonical_doc_id,
            ContentRegistry.alias_count,
        )
        
        result = self.db.execute(stmt).fetchone()
        # ORDER DEPENDENCY:
        # Registry write participates in caller transaction; committing here would break ingest atomicity.
        self.db.flush()
        
        canonical_doc_id = result[0]
        alias_count = result[1]
        
        # Determine if this is a duplicate based on whether:
        # 1. Entry existed before our upsert, OR
        # 2. The canonical_doc_id differs from our doc_id (we lost the race)
        # DATA INTEGRITY:
        # Keep both conditions; relying on one can misclassify races and create duplicate canonical ingests.
        is_duplicate = was_existing or (canonical_doc_id != doc_id)
        
        if is_duplicate:
            logger.info(
                f"Content hash {content_hash[:16]}... already registered. "
                f"canonical_doc_id={canonical_doc_id}, alias_count={alias_count}"
            )
        else:
            logger.info(
                f"Registered new content: hash={content_hash[:16]}..., "
                f"canonical_doc_id={canonical_doc_id}"
            )
        
        return ContentIdentity(
            content_hash=content_hash,
            canonical_doc_id=canonical_doc_id,
            is_duplicate=is_duplicate,
            alias_count=alias_count
        )
    
    def get_canonical_doc_id(
        self,
        content_hash: str,
        tenant_id: Optional[str] = None
    ) -> Optional[str]:
        """Get canonical doc_id for a content hash within a tenant.

        Args:
            content_hash: SHA256 hash of file content
            tenant_id: Optional tenant ID (defaults to 'default')

        Returns:
            Canonical doc_id if found, None otherwise
        """
        effective_tenant = tenant_id if tenant_id else 'default'
        entry = self.db.query(ContentRegistry).filter(
            ContentRegistry.content_hash == content_hash,
            ContentRegistry.tenant_id == effective_tenant
        ).first()

        return entry.canonical_doc_id if entry else None
    
    def get_all_aliases(self, canonical_doc_id: str) -> list[str]:
        """Get all doc_ids that share the same canonical content.
        
        Args:
            canonical_doc_id: The canonical doc_id
            
        Returns:
            List of all doc_ids (including canonical) for this content
        """
        from app.db.graph_models import DocumentGraph
        
        # FRAGILE COUPLING:
        # This lookup assumes canonical_doc_id is globally unique across tenants; add tenant scope if that invariant changes.
        docs = self.db.query(DocumentGraph.doc_id).filter(
            DocumentGraph.canonical_doc_id == canonical_doc_id
        ).all()
        
        return [d.doc_id for d in docs]
