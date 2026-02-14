"""MinIO storage client for NPR RAG.

Bucket layout:
  npr-corpus/
  ├── raw/{doc_id}/{version_id}/original          # Raw uploaded file
  ├── ir/{doc_id}/{version_id}/document_ir.json   # Parsed IR
  ├── chunks/{doc_id}/{version_id}/chunks.jsonl   # Chunk records
  ├── views/{doc_id}/{version_id}/canonical.html  # Canonical viewer artifact
  ├── views/{doc_id}/{version_id}/source_map.json # Canonical text + node offsets
  ├── anchors/{doc_id}/{version_id}/selectors.jsonl # Selector bundle index
  └── embeddings/{doc_id}/{version_id}/bundle.json # (Phase 2)

  npr-traces/
  └── {YYYY}/{MM}/{DD}/{trace_id}.json            # Flight recorder logs
"""

import io
import json
import os
from datetime import datetime
from typing import Any

from minio import Minio
from minio.error import S3Error
from app.config import get_settings


class StorageClient:
    """MinIO storage client for document artifacts and traces."""
    
    CORPUS_BUCKET = "npr-corpus"
    TRACES_BUCKET = "npr-traces"
    
    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        secure: bool = False,
    ):
        """Initialize MinIO client.
        
        Args:
            endpoint: MinIO server endpoint (default from env)
            access_key: Access key (default from env)
            secret_key: Secret key (default from env)
            secure: Use HTTPS (default False for local dev)
        """
        settings = get_settings()
        self.endpoint = endpoint or os.getenv("MINIO_ENDPOINT") or settings.minio_endpoint
        self.access_key = access_key or os.getenv("MINIO_ACCESS_KEY") or settings.minio_access_key
        self.secret_key = secret_key or os.getenv("MINIO_SECRET_KEY") or settings.minio_secret_key

        if not self.endpoint or not self.access_key or not self.secret_key:
            raise ValueError(
                "MinIO configuration is incomplete. "
                "Set MINIO_ENDPOINT, MINIO_ACCESS_KEY, and MINIO_SECRET_KEY."
            )
        
        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=secure,
        )
        
        # Ensure buckets exist
        self._ensure_buckets()
    
    def _ensure_buckets(self) -> None:
        """Create required buckets if they don't exist."""
        for bucket in [self.CORPUS_BUCKET, self.TRACES_BUCKET]:
            if not self.client.bucket_exists(bucket):
                self.client.make_bucket(bucket)
    
    # =========================================================================
    # Raw Document Storage
    # =========================================================================
    
    def put_raw(
        self,
        doc_id: str,
        version_id: str,
        content: bytes,
        filename: str,
        content_type: str | None = None,
    ) -> str:
        """Store raw uploaded document.
        
        Args:
            doc_id: Document ID
            version_id: Version ID
            content: Raw file bytes
            filename: Original filename
            content_type: MIME type (optional)
        
        Returns:
            S3 URI of stored object
        """
        object_name = f"raw/{doc_id}/{version_id}/{filename}"
        
        self.client.put_object(
            self.CORPUS_BUCKET,
            object_name,
            io.BytesIO(content),
            length=len(content),
            content_type=content_type or "application/octet-stream",
        )
        
        return f"s3://{self.CORPUS_BUCKET}/{object_name}"
    
    def get_raw(self, doc_id: str, version_id: str, filename: str) -> bytes:
        """Retrieve raw document content.
        
        Args:
            doc_id: Document ID
            version_id: Version ID
            filename: Original filename
        
        Returns:
            Raw file bytes
        """
        content, _ = self.get_raw_with_content_type(doc_id, version_id, filename)
        return content

    def get_raw_with_content_type(
        self,
        doc_id: str,
        version_id: str,
        filename: str,
    ) -> tuple[bytes, str | None]:
        """Retrieve raw document content and stored content type."""
        object_name = f"raw/{doc_id}/{version_id}/{filename}"
        response = self.client.get_object(self.CORPUS_BUCKET, object_name)
        try:
            content_type = None
            if response.headers:
                content_type = response.headers.get("Content-Type")
            return response.read(), content_type
        finally:
            response.close()
            response.release_conn()
    
    def list_raw_files(self, doc_id: str, version_id: str) -> list[str]:
        """List raw files for a document version."""
        prefix = f"raw/{doc_id}/{version_id}/"
        objects = self.client.list_objects(self.CORPUS_BUCKET, prefix=prefix)
        return [obj.object_name.split("/")[-1] for obj in objects]
    
    # =========================================================================
    # Document IR Storage
    # =========================================================================
    
    def put_ir(self, doc_id: str, version_id: str, ir: dict[str, Any]) -> str:
        """Store parsed DocumentIR.
        
        Args:
            doc_id: Document ID
            version_id: Version ID
            ir: DocumentIR as dict
        
        Returns:
            S3 URI of stored object
        """
        object_name = f"ir/{doc_id}/{version_id}/document_ir.json"
        content = json.dumps(ir, indent=2, ensure_ascii=False).encode("utf-8")
        
        self.client.put_object(
            self.CORPUS_BUCKET,
            object_name,
            io.BytesIO(content),
            length=len(content),
            content_type="application/json",
        )
        
        return f"s3://{self.CORPUS_BUCKET}/{object_name}"
    
    def get_ir(self, doc_id: str, version_id: str) -> dict[str, Any]:
        """Retrieve DocumentIR.
        
        Args:
            doc_id: Document ID
            version_id: Version ID
        
        Returns:
            DocumentIR as dict
        """
        object_name = f"ir/{doc_id}/{version_id}/document_ir.json"
        response = self.client.get_object(self.CORPUS_BUCKET, object_name)
        try:
            return json.loads(response.read().decode("utf-8"))
        finally:
            response.close()
            response.release_conn()
    
    def ir_exists(self, doc_id: str, version_id: str) -> bool:
        """Check if IR exists for document version."""
        object_name = f"ir/{doc_id}/{version_id}/document_ir.json"
        try:
            self.client.stat_object(self.CORPUS_BUCKET, object_name)
            return True
        except S3Error:
            return False
    
    # =========================================================================
    # Chunk Storage
    # =========================================================================
    
    def put_chunks(
        self,
        doc_id: str,
        version_id: str,
        chunks: list[dict[str, Any]],
    ) -> str:
        """Store chunk records as JSONL.
        
        Args:
            doc_id: Document ID
            version_id: Version ID
            chunks: List of ChunkRecord dicts
        
        Returns:
            S3 URI of stored object
        """
        object_name = f"chunks/{doc_id}/{version_id}/chunks.jsonl"
        
        # JSONL format - one JSON object per line
        lines = [json.dumps(chunk, ensure_ascii=False) for chunk in chunks]
        content = "\n".join(lines).encode("utf-8")
        
        self.client.put_object(
            self.CORPUS_BUCKET,
            object_name,
            io.BytesIO(content),
            length=len(content),
            content_type="application/x-ndjson",
        )
        
        return f"s3://{self.CORPUS_BUCKET}/{object_name}"
    
    def get_chunks(self, doc_id: str, version_id: str) -> list[dict[str, Any]]:
        """Retrieve chunk records.
        
        Args:
            doc_id: Document ID
            version_id: Version ID
        
        Returns:
            List of ChunkRecord dicts
        """
        object_name = f"chunks/{doc_id}/{version_id}/chunks.jsonl"
        response = self.client.get_object(self.CORPUS_BUCKET, object_name)
        try:
            content = response.read().decode("utf-8")
            return [json.loads(line) for line in content.strip().split("\n") if line]
        finally:
            response.close()
            response.release_conn()
    
    def chunks_exist(self, doc_id: str, version_id: str) -> bool:
        """Check if chunks exist for document version."""
        object_name = f"chunks/{doc_id}/{version_id}/chunks.jsonl"
        try:
            self.client.stat_object(self.CORPUS_BUCKET, object_name)
            return True
        except S3Error:
            return False

    # =========================================================================
    # Highlighting Artifacts Storage
    # =========================================================================

    def put_canonical_view(self, doc_id: str, version_id: str, html_content: str) -> str:
        """Store canonical HTML viewer artifact."""
        object_name = f"views/{doc_id}/{version_id}/canonical.html"
        content = html_content.encode("utf-8")

        self.client.put_object(
            self.CORPUS_BUCKET,
            object_name,
            io.BytesIO(content),
            length=len(content),
            content_type="text/html; charset=utf-8",
        )
        return f"s3://{self.CORPUS_BUCKET}/{object_name}"

    def get_canonical_view(self, doc_id: str, version_id: str) -> str:
        """Retrieve canonical HTML viewer artifact."""
        object_name = f"views/{doc_id}/{version_id}/canonical.html"
        response = self.client.get_object(self.CORPUS_BUCKET, object_name)
        try:
            return response.read().decode("utf-8")
        finally:
            response.close()
            response.release_conn()

    def canonical_view_exists(self, doc_id: str, version_id: str) -> bool:
        """Check whether canonical HTML artifact exists."""
        object_name = f"views/{doc_id}/{version_id}/canonical.html"
        try:
            self.client.stat_object(self.CORPUS_BUCKET, object_name)
            return True
        except S3Error:
            return False

    def put_source_map(self, doc_id: str, version_id: str, source_map: dict[str, Any]) -> str:
        """Store canonical source map artifact."""
        object_name = f"views/{doc_id}/{version_id}/source_map.json"
        content = json.dumps(source_map, ensure_ascii=False).encode("utf-8")

        self.client.put_object(
            self.CORPUS_BUCKET,
            object_name,
            io.BytesIO(content),
            length=len(content),
            content_type="application/json",
        )
        return f"s3://{self.CORPUS_BUCKET}/{object_name}"

    def get_source_map(self, doc_id: str, version_id: str) -> dict[str, Any]:
        """Retrieve canonical source map artifact."""
        object_name = f"views/{doc_id}/{version_id}/source_map.json"
        response = self.client.get_object(self.CORPUS_BUCKET, object_name)
        try:
            return json.loads(response.read().decode("utf-8"))
        finally:
            response.close()
            response.release_conn()

    def source_map_exists(self, doc_id: str, version_id: str) -> bool:
        """Check whether source map artifact exists."""
        object_name = f"views/{doc_id}/{version_id}/source_map.json"
        try:
            self.client.stat_object(self.CORPUS_BUCKET, object_name)
            return True
        except S3Error:
            return False

    def put_selectors(self, doc_id: str, version_id: str, selectors: list[dict[str, Any]]) -> str:
        """Store selector bundles as JSONL."""
        object_name = f"anchors/{doc_id}/{version_id}/selectors.jsonl"
        lines = [json.dumps(selector, ensure_ascii=False) for selector in selectors]
        content = "\n".join(lines).encode("utf-8")

        self.client.put_object(
            self.CORPUS_BUCKET,
            object_name,
            io.BytesIO(content),
            length=len(content),
            content_type="application/x-ndjson",
        )
        return f"s3://{self.CORPUS_BUCKET}/{object_name}"

    def get_selectors(self, doc_id: str, version_id: str) -> list[dict[str, Any]]:
        """Retrieve selector bundles."""
        object_name = f"anchors/{doc_id}/{version_id}/selectors.jsonl"
        response = self.client.get_object(self.CORPUS_BUCKET, object_name)
        try:
            content = response.read().decode("utf-8")
            return [json.loads(line) for line in content.splitlines() if line.strip()]
        finally:
            response.close()
            response.release_conn()

    def selectors_exist(self, doc_id: str, version_id: str) -> bool:
        """Check whether selector bundle artifact exists."""
        object_name = f"anchors/{doc_id}/{version_id}/selectors.jsonl"
        try:
            self.client.stat_object(self.CORPUS_BUCKET, object_name)
            return True
        except S3Error:
            return False

    # Backward-compatible alias for older call sites.
    def selectors_exists(self, doc_id: str, version_id: str) -> bool:
        return self.selectors_exist(doc_id, version_id)
    
    # =========================================================================
    # Embeddings Storage (Phase 2)
    # =========================================================================
    
    def put_embeddings(
        self,
        doc_id: str,
        version_id: str,
        embeddings: dict[str, Any],
    ) -> str:
        """Store embedding bundle.
        
        Args:
            doc_id: Document ID
            version_id: Version ID
            embeddings: Embedding bundle dict
        
        Returns:
            S3 URI of stored object
        """
        object_name = f"embeddings/{doc_id}/{version_id}/bundle.json"
        content = json.dumps(embeddings, ensure_ascii=False).encode("utf-8")
        
        self.client.put_object(
            self.CORPUS_BUCKET,
            object_name,
            io.BytesIO(content),
            length=len(content),
            content_type="application/json",
        )
        
        return f"s3://{self.CORPUS_BUCKET}/{object_name}"
    
    def get_embeddings(self, doc_id: str, version_id: str) -> dict[str, Any]:
        """Retrieve embedding bundle."""
        object_name = f"embeddings/{doc_id}/{version_id}/bundle.json"
        response = self.client.get_object(self.CORPUS_BUCKET, object_name)
        try:
            return json.loads(response.read().decode("utf-8"))
        finally:
            response.close()
            response.release_conn()
    
    def embeddings_exist(self, doc_id: str, version_id: str) -> bool:
        """Check if embeddings exist for document version."""
        object_name = f"embeddings/{doc_id}/{version_id}/bundle.json"
        try:
            self.client.stat_object(self.CORPUS_BUCKET, object_name)
            return True
        except S3Error:
            return False
    
    # =========================================================================
    # Trace Storage
    # =========================================================================
    
    def put_trace(self, trace_id: str, trace: dict[str, Any]) -> str:
        """Store flight recorder trace.
        
        Args:
            trace_id: Trace UUID
            trace: Trace object dict
        
        Returns:
            S3 URI of stored object
        """
        now = datetime.utcnow()
        object_name = f"{now.year}/{now.month:02d}/{now.day:02d}/{trace_id}.json"
        content = json.dumps(trace, indent=2, ensure_ascii=False).encode("utf-8")
        
        self.client.put_object(
            self.TRACES_BUCKET,
            object_name,
            io.BytesIO(content),
            length=len(content),
            content_type="application/json",
        )
        
        return f"s3://{self.TRACES_BUCKET}/{object_name}"
    
    def get_trace(self, trace_uri: str) -> dict[str, Any]:
        """Retrieve trace by URI.
        
        Args:
            trace_uri: Full S3 URI (s3://bucket/path)
        
        Returns:
            Trace object dict
        """
        # Parse s3://bucket/path
        parts = trace_uri.replace("s3://", "").split("/", 1)
        bucket = parts[0]
        object_name = parts[1] if len(parts) > 1 else ""
        
        response = self.client.get_object(bucket, object_name)
        try:
            return json.loads(response.read().decode("utf-8"))
        finally:
            response.close()
            response.release_conn()
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def delete_document(self, doc_id: str, version_id: str) -> None:
        """Delete all artifacts for a document version."""
        prefixes = [
            f"raw/{doc_id}/{version_id}/",
            f"ir/{doc_id}/{version_id}/",
            f"chunks/{doc_id}/{version_id}/",
            f"views/{doc_id}/{version_id}/",
            f"anchors/{doc_id}/{version_id}/",
            f"embeddings/{doc_id}/{version_id}/",
        ]
        
        for prefix in prefixes:
            objects = self.client.list_objects(self.CORPUS_BUCKET, prefix=prefix)
            for obj in objects:
                self.client.remove_object(self.CORPUS_BUCKET, obj.object_name)
    
    def get_document_size(self, doc_id: str, version_id: str) -> int:
        """Get total size of all artifacts for a document version."""
        prefixes = [
            f"raw/{doc_id}/{version_id}/",
            f"ir/{doc_id}/{version_id}/",
            f"chunks/{doc_id}/{version_id}/",
            f"views/{doc_id}/{version_id}/",
            f"anchors/{doc_id}/{version_id}/",
        ]
        
        total = 0
        for prefix in prefixes:
            objects = self.client.list_objects(self.CORPUS_BUCKET, prefix=prefix)
            for obj in objects:
                total += obj.size
        
        return total


# Singleton instance
_storage_client: StorageClient | None = None


def get_storage_client() -> StorageClient:
    """Get or create singleton storage client."""
    global _storage_client
    if _storage_client is None:
        _storage_client = StorageClient()
    return _storage_client
