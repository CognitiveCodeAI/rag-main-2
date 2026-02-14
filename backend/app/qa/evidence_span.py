"""Evidence span contract for deterministic citation highlighting.

Phase 1 contract:
- page_index is explicitly 1-based.
- locator is either text offsets or bbox coordinates.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ValidationError, model_validator


PAGE_INDEX_BASE = 1


class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class PageSize(BaseModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class TextOffsetsLocator(BaseModel):
    type: Literal["text_offsets"] = "text_offsets"
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_offsets(self) -> "TextOffsetsLocator":
        if self.end <= self.start:
            raise ValueError("text offset end must be greater than start")
        return self


class BBoxLocator(BaseModel):
    type: Literal["bbox"] = "bbox"
    bbox: BBox
    page_size: Optional[PageSize] = None


Locator = Union[TextOffsetsLocator, BBoxLocator]


class EvidenceSpan(BaseModel):
    doc_id: str = Field(min_length=1)
    page_index: int = Field(ge=1, description="1-based page index")
    page_index_base: Literal[1] = PAGE_INDEX_BASE
    quote_text: str = Field(min_length=1)
    locator: Locator
    confidence: float = Field(ge=0.0, le=1.0)
    source_section: Optional[str] = None


def normalize_page_index(page_index: int, page_index_base: int = PAGE_INDEX_BASE) -> int:
    """Normalize to a 1-based page index.

    Accepts 0-based and 1-based input indexes.
    """
    if page_index_base not in (0, 1):
        raise ValueError("page_index_base must be 0 or 1")
    normalized = page_index + 1 if page_index_base == 0 else page_index
    if normalized < 1:
        raise ValueError("page_index must be >= 1 after normalization")
    return normalized


def parse_evidence_span(
    payload: Dict[str, Any],
    *,
    fallback_doc_id: Optional[str] = None,
    fallback_page_index: Optional[int] = None,
    fallback_quote_text: Optional[str] = None,
    fallback_confidence: float = 1.0,
    fallback_source_section: Optional[str] = None,
) -> EvidenceSpan:
    """Parse and normalize an incoming evidence span payload."""
    working = dict(payload or {})
    page_index_base = int(working.pop("page_index_base", PAGE_INDEX_BASE))
    raw_page_index = working.get("page_index", fallback_page_index)
    if raw_page_index is None:
        raise ValueError("missing page_index")

    page_index = normalize_page_index(int(raw_page_index), page_index_base=page_index_base)
    doc_id = (working.get("doc_id") or fallback_doc_id or "").strip()
    quote_text = (working.get("quote_text") or fallback_quote_text or "").strip()
    confidence = float(working.get("confidence", fallback_confidence))
    source_section = working.get("source_section", fallback_source_section)

    return EvidenceSpan.model_validate(
        {
            "doc_id": doc_id,
            "page_index": page_index,
            "quote_text": quote_text,
            "locator": working.get("locator"),
            "confidence": confidence,
            "source_section": source_section,
        }
    )


def _locator_from_artifacts(
    *,
    selector_bundle: Optional[Dict[str, Any]],
    bbox: Optional[Dict[str, float]],
    page_size: Optional[Dict[str, float]],
) -> Optional[Dict[str, Any]]:
    if bbox:
        locator: Dict[str, Any] = {
            "type": "bbox",
            "bbox": bbox,
        }
        if page_size:
            locator["page_size"] = page_size
        return locator

    if selector_bundle:
        text_position = selector_bundle.get("text_position") or {}
        if isinstance(text_position.get("start"), int) and isinstance(text_position.get("end"), int):
            return {
                "type": "text_offsets",
                "start": text_position["start"],
                "end": text_position["end"],
            }

    return None


def build_evidence_spans(
    *,
    provided_spans: Optional[List[Dict[str, Any]]],
    doc_id: Optional[str],
    page_index: Optional[int],
    quote_text: Optional[str],
    selector_bundle: Optional[Dict[str, Any]],
    bbox: Optional[Dict[str, float]],
    page_size: Optional[Dict[str, float]],
    confidence: float,
    source_section: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build normalized EvidenceSpan payloads for API responses.

    If provided spans are present and valid, use those after normalization.
    Otherwise synthesize one span from selector/bbox artifacts when possible.
    """
    normalized: List[Dict[str, Any]] = []

    for raw in provided_spans or []:
        try:
            span = parse_evidence_span(
                raw,
                fallback_doc_id=doc_id,
                fallback_page_index=page_index,
                fallback_quote_text=quote_text,
                fallback_confidence=confidence,
                fallback_source_section=source_section,
            )
        except (ValidationError, ValueError, TypeError):
            continue
        normalized.append(span.model_dump())

    if normalized:
        return normalized

    if not doc_id or page_index is None:
        return []

    locator = _locator_from_artifacts(
        selector_bundle=selector_bundle,
        bbox=bbox,
        page_size=page_size,
    )
    if not locator:
        return []

    text_quote = quote_text or ""
    if not text_quote.strip():
        text_quote = (
            (selector_bundle or {})
            .get("text_quote", {})
            .get("exact", "")
        )
    if not text_quote.strip():
        return []

    span = EvidenceSpan.model_validate(
        {
            "doc_id": doc_id,
            "page_index": normalize_page_index(page_index, page_index_base=PAGE_INDEX_BASE),
            "quote_text": text_quote.strip(),
            "locator": locator,
            "confidence": confidence,
            "source_section": source_section,
        }
    )
    return [span.model_dump()]
