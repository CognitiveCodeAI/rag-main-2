"""Base document parser interface and registry."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Block:
    """A content block within a document."""
    type: str  # heading, paragraph, table, figure, code, list
    text: str | None = None
    level: int | None = None  # For headings
    cells: list[list[str]] | None = None  # For tables
    code_lang: str | None = None  # For code blocks
    list_items: list[str] | None = None  # For lists
    bbox: dict[str, float] | None = None  # Bounding box
    start_offset: int = 0
    end_offset: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "type": self.type,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
        }
        if self.text is not None:
            result["text"] = self.text
        if self.level is not None:
            result["level"] = self.level
        if self.cells is not None:
            result["cells"] = self.cells
        if self.code_lang is not None:
            result["code_lang"] = self.code_lang
        if self.list_items is not None:
            result["list_items"] = self.list_items
        if self.bbox is not None:
            result["bbox"] = self.bbox
        return result


@dataclass
class Page:
    """A page within a document."""
    page_num: int
    blocks: list[Block] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "page_num": self.page_num,
            "blocks": [b.to_dict() for b in self.blocks],
        }


@dataclass
class Section:
    """A logical section within a document."""
    section_id: str
    heading: str
    level: int
    block_refs: list[int] = field(default_factory=list)  # Indices into blocks
    section_path: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "section_id": self.section_id,
            "heading": self.heading,
            "level": self.level,
            "block_refs": self.block_refs,
            "section_path": self.section_path,
        }


@dataclass
class ParseQuality:
    """Quality metrics for a parsed document."""
    parse_confidence: float = 1.0
    ocr_used: bool = False
    ocr_confidence: float | None = None
    table_confidence: float | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {"parse_confidence": self.parse_confidence}
        if self.ocr_used:
            result["ocr_used"] = self.ocr_used
        if self.ocr_confidence is not None:
            result["ocr_confidence"] = self.ocr_confidence
        if self.table_confidence is not None:
            result["table_confidence"] = self.table_confidence
        return result


@dataclass
class DocumentIR:
    """Canonical intermediate representation of a parsed document."""
    doc_ref: dict[str, Any]
    title: str | None = None
    language: str | None = None
    pages: list[Page] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    offset_map: dict[str, Any] | None = None
    quality: ParseQuality = field(default_factory=ParseQuality)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "schema_version": "1.0",
            "doc_ref": self.doc_ref,
            "title": self.title,
            "language": self.language,
            "pages": [p.to_dict() for p in self.pages],
            "sections": [s.to_dict() for s in self.sections],
            "offset_map": self.offset_map,
            "quality": self.quality.to_dict(),
        }


class DocumentParser(ABC):
    """Abstract base class for document parsers."""
    
    @abstractmethod
    def parse(self, raw_bytes: bytes, doc_ref: dict[str, Any]) -> DocumentIR:
        """Parse raw document bytes into canonical DocumentIR.
        
        Args:
            raw_bytes: Raw file bytes
            doc_ref: DocumentRef dict with metadata
        
        Returns:
            DocumentIR instance
        """
        pass
    
    @property
    @abstractmethod
    def supported_types(self) -> list[str]:
        """Return list of source_type values this parser handles."""
        pass


class ParserRegistry:
    """Registry for document parsers."""
    
    _parsers: dict[str, DocumentParser] = {}
    
    @classmethod
    def register(cls, parser: DocumentParser) -> None:
        """Register a parser for its supported types."""
        for source_type in parser.supported_types:
            cls._parsers[source_type] = parser
    
    @classmethod
    def get_parser(cls, source_type: str) -> DocumentParser | None:
        """Get parser for a source type."""
        return cls._parsers.get(source_type)
    
    @classmethod
    def parse(cls, raw_bytes: bytes, doc_ref: dict[str, Any]) -> DocumentIR:
        """Parse document using appropriate parser.
        
        Args:
            raw_bytes: Raw file bytes
            doc_ref: DocumentRef dict (must have source_type)
        
        Returns:
            DocumentIR instance
        
        Raises:
            ValueError: If no parser available for source_type
        """
        source_type = doc_ref.get("source_type")
        parser = cls.get_parser(source_type)
        if parser is None:
            raise ValueError(f"No parser registered for source_type: {source_type}")
        return parser.parse(raw_bytes, doc_ref)
