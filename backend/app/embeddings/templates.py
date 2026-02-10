"""Deterministic embedding template renderer.

Implements rendering for:
- doc.chunk.embed.v1
- doc.contextual_header.v1

Rules:
- Empty/null placeholders render as empty string
- Normalize whitespace before fingerprinting
- Template versions pinned
"""

import hashlib
import re
import unicodedata
from typing import Any


# Template definitions (pinned versions)
TEMPLATES = {
    "doc.chunk.embed.v1": {
        "version": "1.0",
        "content": """DOCUMENT_CHUNK
Title: {{doc_title}}
Type: {{doc_type}}
SectionPath: {{section_path}}
HeadingContext: {{heading_context}}
ChunkType: {{chunk_type}}

TEXT:
{{chunk_text}}

TABLE_TEXT:
{{table_text}}

CODE_TEXT:
{{code_text}}
""",
    },
    "doc.contextual_header.v1": {
        "version": "1.0",
        "content": """CONTEXT_HEADER
DocID: {{doc_id}}
VersionID: {{doc_version_id}}
SourceURI: {{source_uri}}
Title: {{doc_title}}
Type: {{doc_type}}
AuthorityTier: {{authority_tier}}
Recency: {{recency_bucket}}
SectionPath: {{section_path}}
HeadingContext: {{heading_context}}
Entities: {{entities_str}}
DocSummary: {{doc_summary}}
""",
    },
    "doc.title_heading.v1": {
        "version": "1.0",
        "content": """{{doc_title}}
{{heading_context}}
""",
    },
    "doc.entities.v1": {
        "version": "1.0",
        "content": """{{entities_str}}
""",
    },
}


class TemplateRenderer:
    """Deterministic template renderer for embeddings."""
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize text for consistent fingerprinting.
        
        - Unicode NFKC normalization
        - Collapse multiple whitespace to single space
        - Strip leading/trailing whitespace from lines
        - Preserve newlines
        """
        if not text:
            return ""
        
        # Unicode normalize
        text = unicodedata.normalize("NFKC", text)
        
        # Process line by line to preserve structure
        lines = text.split("\n")
        normalized_lines = []
        for line in lines:
            # Collapse multiple spaces to single space
            line = re.sub(r"[ \t]+", " ", line)
            # Strip leading/trailing whitespace
            line = line.strip()
            normalized_lines.append(line)
        
        return "\n".join(normalized_lines)
    
    @staticmethod
    def compute_fingerprint(rendered: str) -> str:
        """Compute SHA256 fingerprint of rendered text."""
        normalized = TemplateRenderer.normalize_text(rendered)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    
    @staticmethod
    def _render_template(template_content: str, placeholders: dict[str, Any]) -> str:
        """Render a template with placeholder substitution.
        
        Args:
            template_content: Template string with {{placeholder}} markers
            placeholders: Dict of placeholder values
        
        Returns:
            Rendered string with placeholders substituted
        """
        result = template_content
        
        # Find all placeholders in template
        placeholder_pattern = re.compile(r"\{\{(\w+)\}\}")
        
        for match in placeholder_pattern.finditer(template_content):
            placeholder_name = match.group(1)
            value = placeholders.get(placeholder_name)
            
            # Convert value to string, empty string if None/missing
            if value is None:
                str_value = ""
            elif isinstance(value, list):
                str_value = " > ".join(str(v) for v in value)
            else:
                str_value = str(value)
            
            result = result.replace(f"{{{{{placeholder_name}}}}}", str_value)
        
        return result
    
    @classmethod
    def build_placeholders_from_chunk(
        cls,
        chunk: dict[str, Any],
        ir: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build placeholder dict from chunk and IR data.
        
        Args:
            chunk: ChunkRecord dict
            ir: Optional DocumentIR dict for additional context
        
        Returns:
            Dict of placeholder values
        """
        chunk_ref = chunk.get("chunk_ref", {})
        fields = chunk.get("fields", {})
        metadata = chunk.get("metadata", {})
        
        doc_ref = ir.get("doc_ref", {}) if ir else {}
        
        # Determine text fields based on chunk type
        chunk_type = chunk_ref.get("chunk_type", "text")
        chunk_text = ""
        table_text = ""
        code_text = ""
        
        body = fields.get("body", "")
        if chunk_type == "text":
            chunk_text = body
        elif chunk_type == "table":
            table_text = body
            if fields.get("table_struct"):
                # Convert table struct to text if available
                rows = fields.get("table_struct", [])
                table_text = "\n".join(["\t".join(row) for row in rows])
        elif chunk_type == "code":
            code_text = body
        else:
            chunk_text = body
        
        return {
            # Document context
            "doc_id": chunk_ref.get("doc_id", ""),
            "doc_version_id": chunk_ref.get("version_id", ""),
            "source_uri": doc_ref.get("source_uri", ""),
            "doc_title": ir.get("title", "") if ir else fields.get("title", ""),
            "doc_type": metadata.get("doc_type", ""),
            "authority_tier": metadata.get("authority_tier", ""),
            "recency_bucket": metadata.get("recency_score", ""),
            
            # Chunk context
            "section_path": chunk_ref.get("section_path", []),
            "heading_context": fields.get("heading_context", ""),
            "entities_str": fields.get("entities_str", ""),
            "doc_summary": "",  # Not available in Phase 2
            
            # Content
            "chunk_type": chunk_type,
            "chunk_text": chunk_text,
            "table_text": table_text,
            "code_text": code_text,
        }
    
    @classmethod
    def render_doc_chunk_v1(
        cls,
        chunk: dict[str, Any],
        ir: dict[str, Any] | None = None,
    ) -> tuple[str, str, str]:
        """Render doc.chunk.embed.v1 template.
        
        Args:
            chunk: ChunkRecord dict
            ir: Optional DocumentIR dict
        
        Returns:
            Tuple of (rendered_text, fingerprint, template_version)
        """
        template = TEMPLATES["doc.chunk.embed.v1"]
        placeholders = cls.build_placeholders_from_chunk(chunk, ir)
        
        rendered = cls._render_template(template["content"], placeholders)
        fingerprint = cls.compute_fingerprint(rendered)
        
        return rendered, fingerprint, template["version"]
    
    @classmethod
    def render_contextual_header_v1(
        cls,
        chunk: dict[str, Any],
        ir: dict[str, Any] | None = None,
    ) -> tuple[str, str, str]:
        """Render doc.contextual_header.v1 template.
        
        Args:
            chunk: ChunkRecord dict
            ir: Optional DocumentIR dict
        
        Returns:
            Tuple of (rendered_text, fingerprint, template_version)
        """
        template = TEMPLATES["doc.contextual_header.v1"]
        placeholders = cls.build_placeholders_from_chunk(chunk, ir)
        
        rendered = cls._render_template(template["content"], placeholders)
        fingerprint = cls.compute_fingerprint(rendered)
        
        return rendered, fingerprint, template["version"]
    
    @classmethod
    def render_contextual_v1(
        cls,
        chunk: dict[str, Any],
        ir: dict[str, Any] | None = None,
    ) -> tuple[str, str, str]:
        """Render contextual view (header + chunk).
        
        Contextual embedding = contextual_header + "\\n" + doc_chunk
        
        Args:
            chunk: ChunkRecord dict
            ir: Optional DocumentIR dict
        
        Returns:
            Tuple of (rendered_text, fingerprint, template_version)
        """
        header, _, header_version = cls.render_contextual_header_v1(chunk, ir)
        doc_chunk, _, chunk_version = cls.render_doc_chunk_v1(chunk, ir)
        
        rendered = header + "\n" + doc_chunk
        fingerprint = cls.compute_fingerprint(rendered)
        version = f"{header_version}+{chunk_version}"
        
        return rendered, fingerprint, version
    
    @classmethod
    def render_title_heading_v1(
        cls,
        chunk: dict[str, Any],
        ir: dict[str, Any] | None = None,
    ) -> tuple[str, str, str]:
        """Render title + heading context view.
        
        Args:
            chunk: ChunkRecord dict
            ir: Optional DocumentIR dict
        
        Returns:
            Tuple of (rendered_text, fingerprint, template_version)
        """
        template = TEMPLATES["doc.title_heading.v1"]
        placeholders = cls.build_placeholders_from_chunk(chunk, ir)
        
        rendered = cls._render_template(template["content"], placeholders)
        fingerprint = cls.compute_fingerprint(rendered)
        
        return rendered, fingerprint, template["version"]
    
    @classmethod
    def render_entities_v1(
        cls,
        chunk: dict[str, Any],
        ir: dict[str, Any] | None = None,
    ) -> tuple[str, str, str]:
        """Render entities view.
        
        Args:
            chunk: ChunkRecord dict
            ir: Optional DocumentIR dict
        
        Returns:
            Tuple of (rendered_text, fingerprint, template_version)
        """
        template = TEMPLATES["doc.entities.v1"]
        placeholders = cls.build_placeholders_from_chunk(chunk, ir)
        
        rendered = cls._render_template(template["content"], placeholders)
        fingerprint = cls.compute_fingerprint(rendered)
        
        return rendered, fingerprint, template["version"]
    
    @classmethod
    def render_all_views(
        cls,
        chunk: dict[str, Any],
        ir: dict[str, Any] | None = None,
    ) -> dict[str, tuple[str, str, str]]:
        """Render all 4 embedding views.
        
        Args:
            chunk: ChunkRecord dict
            ir: Optional DocumentIR dict
        
        Returns:
            Dict mapping view_id to (rendered_text, fingerprint, template_version)
        """
        return {
            "vec_content": cls.render_doc_chunk_v1(chunk, ir),
            "vec_contextual": cls.render_contextual_v1(chunk, ir),
            "vec_title_heading": cls.render_title_heading_v1(chunk, ir),
            "vec_entities": cls.render_entities_v1(chunk, ir),
        }
