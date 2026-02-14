"""Cross-format source highlighting utilities.

Provides:
1. Canonical text normalization
2. Selector bundle generation (TextPosition + TextQuote)
3. Canonical view/source-map artifact generation
4. Strict selector resolution (fail-closed by default)
5. Lazy artifact backfill for legacy documents
"""

from __future__ import annotations

import html
import logging
import mimetypes
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.graph_models import DocumentGraph, Node
from app.services.document_identity import find_legacy_for_graph
from app.storage.minio_client import StorageClient, get_storage_client

logger = logging.getLogger(__name__)

NORMALIZATION_ID = "unicode_nfkc+ws_collapse"
_WS_RE = re.compile(r"\s+")


def normalize_text(value: Optional[str]) -> str:
    """Normalize text deterministically for selector generation/resolution."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = _WS_RE.sub(" ", normalized)
    return normalized.strip()


def _mime_from_source(source_type: Optional[str], filename: Optional[str]) -> str:
    source_type = (source_type or "").lower()
    by_type = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "html": "text/html",
        "md": "text/markdown",
        "csv": "text/csv",
        "txt": "text/plain",
    }
    if source_type in by_type:
        return by_type[source_type]
    guessed = mimetypes.guess_type(filename or "")[0]
    return guessed or "application/octet-stream"


def _node_sort_key(node: Node) -> tuple:
    chunk_idx = node.chunk_index_in_page if node.chunk_index_in_page is not None else 10**9
    node_type = node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)
    return (node.page_no or 0, chunk_idx, node_type, node.node_id)


def _node_text(node: Node) -> str:
    """Best-effort node text for selector anchoring."""
    candidates = [
        node.text_plain,
        node.caption_md,
        node.text_md,
        node.label,
    ]
    for candidate in candidates:
        normalized = normalize_text(candidate)
        if normalized:
            return normalized
    return ""


def _build_text_quote(canonical_text: str, start: int, end: int, window: int = 96) -> dict:
    exact = canonical_text[start:end]
    prefix = canonical_text[max(0, start - window):start]
    suffix = canonical_text[end:min(len(canonical_text), end + window)]
    return {
        "exact": exact,
        "prefix": prefix,
        "suffix": suffix,
    }


def build_selector_artifacts_for_nodes(
    doc: DocumentGraph,
    nodes: Iterable[Node],
    source_type: Optional[str],
    mime_type: Optional[str],
) -> dict:
    """Build selector bundles + canonical artifacts for a document."""
    canonical_parts: list[str] = []
    source_entries: list[dict] = []
    selector_bundles: list[dict] = []

    sorted_nodes = sorted(nodes, key=_node_sort_key)
    offset = 0

    for node in sorted_nodes:
        anchor_text = _node_text(node)
        if not anchor_text:
            continue

        if canonical_parts:
            canonical_parts.append("\n\n")
            offset += 2

        start = offset
        canonical_parts.append(anchor_text)
        offset += len(anchor_text)
        end = offset

        layout: dict[str, Any] = {}
        if node.page_no is not None:
            layout["page_no"] = node.page_no
        if node.bbox:
            layout["bbox"] = node.bbox
        if node.meta and node.meta.get("page_size"):
            layout["page_size"] = node.meta.get("page_size")

        structural = {
            "docling_self_ref": (node.meta or {}).get("docling_self_ref"),
            "block_id": (node.meta or {}).get("block_id"),
            "sheet": (node.meta or {}).get("sheet"),
            "slide": (node.meta or {}).get("slide"),
        }
        structural = {k: v for k, v in structural.items() if v is not None}

        bundle = {
            "schema_version": "1.0",
            "node_id": node.node_id,
            "doc_id": node.doc_id,
            "version": node.version,
            "source_type": (source_type or "txt").lower(),
            "text_position": {"start": start, "end": end},
            "text_quote": {},  # filled once canonical text is finalized
            "layout": layout or None,
            "structural": structural,
            "normalization": NORMALIZATION_ID,
            "source_state": {
                "content_hash": (
                    doc.content_hash
                    if (doc.content_hash or "").startswith("sha256:")
                    else f"sha256:{doc.content_hash}"
                ),
                "mime_type": mime_type or "application/octet-stream",
                "source_uri": doc.source_uri,
            },
        }

        source_entries.append(
            {
                "node_id": node.node_id,
                "start": start,
                "end": end,
                "page_no": node.page_no,
                "node_type": node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type),
                "label": node.label,
            }
        )
        selector_bundles.append(bundle)

    canonical_text = "".join(canonical_parts)

    # Fill text_quote now that canonical text is assembled.
    for bundle in selector_bundles:
        start = bundle["text_position"]["start"]
        end = bundle["text_position"]["end"]
        bundle["text_quote"] = _build_text_quote(canonical_text, start, end)

    now_iso = datetime.now(timezone.utc).isoformat()
    canonical_html = (
        "<!doctype html>\n"
        "<html>\n"
        "<head>\n"
        "  <meta charset=\"utf-8\" />\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
        f"  <meta name=\"x-normalization\" content=\"{NORMALIZATION_ID}\" />\n"
        "  <title>Canonical Source View</title>\n"
        "  <style>\n"
        "    body { margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background: #ffffff; color: #111827; }\n"
        "    main { max-width: 980px; margin: 0 auto; padding: 24px 20px 80px; }\n"
        "    #canonical-text { white-space: pre-wrap; line-height: 1.6; font-size: 14px; }\n"
        "    mark[data-highlight=\"active\"] { background: #fde68a; color: inherit; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <main>\n"
        "    <h1 style=\"margin:0 0 12px 0;font-size:18px;\">Canonical Source View</h1>\n"
        f"    <p style=\"margin:0 0 16px 0;color:#4b5563;font-size:12px;\">Generated {html.escape(now_iso)}</p>\n"
        f"    <pre id=\"canonical-text\">{html.escape(canonical_text)}</pre>\n"
        "    <p style=\"margin:20px 0 0 0;color:#6b7280;font-size:11px;opacity:0.75;\">© Cognitive Code — cognitiveCode.ai</p>\n"
        "  </main>\n"
        "</body>\n"
        "</html>\n"
    )

    source_map = {
        "schema_version": "1.0",
        "doc_id": doc.doc_id,
        "version": doc.version,
        "normalization": NORMALIZATION_ID,
        "generated_at": now_iso,
        "canonical_text": canonical_text,
        "nodes": source_entries,
    }

    return {
        "canonical_text": canonical_text,
        "canonical_html": canonical_html,
        "source_map": source_map,
        "selectors": selector_bundles,
        "nodes_with_selectors": len(selector_bundles),
        "total_nodes": len(sorted_nodes),
    }


def hydrate_nodes_with_selectors(
    nodes: Iterable[Node],
    selector_bundles: Iterable[dict],
) -> None:
    """Attach selector bundles to node meta in-memory before DB persistence."""
    by_node_id = {s["node_id"]: s for s in selector_bundles}
    for node in nodes:
        selector = by_node_id.get(node.node_id)
        if not selector:
            continue
        node.meta = dict(node.meta or {})
        node.meta["selector_bundle"] = selector
        node.meta["text_position"] = selector.get("text_position")
        node.meta["normalization"] = selector.get("normalization")


def persist_highlight_artifacts(
    storage: StorageClient,
    doc_id: str,
    version: int,
    canonical_html: str,
    source_map: dict,
    selectors: list[dict],
) -> None:
    """Store highlight artifacts in object storage."""
    storage.put_canonical_view(doc_id, str(version), canonical_html)
    storage.put_source_map(doc_id, str(version), source_map)
    storage.put_selectors(doc_id, str(version), selectors)


def _hash_matches(expected_hash: Optional[str], actual_hash: Optional[str]) -> bool:
    if not expected_hash or not actual_hash:
        return False
    expected_norm = expected_hash if expected_hash.startswith("sha256:") else f"sha256:{expected_hash}"
    actual_norm = actual_hash if actual_hash.startswith("sha256:") else f"sha256:{actual_hash}"
    return expected_norm == actual_norm


def resolve_selector_bundle(
    selector_bundle: dict,
    canonical_text: str,
    *,
    strict: bool = True,
    allow_fuzzy: bool = False,
) -> Tuple[str, Optional[str], Optional[dict], str]:
    """Resolve selector against canonical text.

    Returns:
        (resolve_status, exact_text, resolved_position, reason)
    """
    text_position = selector_bundle.get("text_position") or {}
    text_quote = selector_bundle.get("text_quote") or {}

    start = text_position.get("start")
    end = text_position.get("end")
    exact = text_quote.get("exact") or ""

    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        return "unresolved", None, None, "invalid_text_position"

    if end > len(canonical_text):
        return "unresolved", None, None, "position_out_of_bounds"

    extracted = canonical_text[start:end]
    if extracted == exact:
        return "exact", extracted, {"start": start, "end": end}, "position_and_quote_match"

    if strict and not allow_fuzzy:
        return "unresolved", None, None, "quote_mismatch_strict_mode"

    if allow_fuzzy and exact:
        fuzzy_idx = canonical_text.find(exact)
        if fuzzy_idx >= 0:
            fuzzy_end = fuzzy_idx + len(exact)
            return "fuzzy", exact, {"start": fuzzy_idx, "end": fuzzy_end}, "fuzzy_quote_match"

    return "unresolved", None, None, "no_match"


def ensure_highlight_artifacts(
    db: Session,
    doc: DocumentGraph,
    *,
    force: bool = False,
    storage: Optional[StorageClient] = None,
) -> dict:
    """Ensure canonical/source-map/selectors artifacts exist for a document version."""
    storage = storage or get_storage_client()
    version = str(doc.version)

    already_have = (
        storage.canonical_view_exists(doc.doc_id, version)
        and storage.source_map_exists(doc.doc_id, version)
        and storage.selectors_exist(doc.doc_id, version)
    )
    if already_have and not force:
        source_map = storage.get_source_map(doc.doc_id, version)
        nodes_with_selectors = len(source_map.get("nodes", []))
        return {
            "generated": False,
            "nodes_with_selectors": nodes_with_selectors,
            "total_nodes": nodes_with_selectors,
            "backfill_needed": False,
        }

    legacy = find_legacy_for_graph(db, doc.doc_id, doc.version)
    source_type = legacy.source_type if legacy else None
    mime_type = legacy.mime_type if legacy else _mime_from_source(source_type, doc.source_uri)

    nodes = (
        db.query(Node)
        .filter(Node.doc_id == doc.doc_id, Node.version == doc.version)
        .all()
    )

    artifacts = build_selector_artifacts_for_nodes(
        doc=doc,
        nodes=nodes,
        source_type=source_type,
        mime_type=mime_type,
    )
    persist_highlight_artifacts(
        storage=storage,
        doc_id=doc.doc_id,
        version=doc.version,
        canonical_html=artifacts["canonical_html"],
        source_map=artifacts["source_map"],
        selectors=artifacts["selectors"],
    )

    # Backfill node.meta selectors for future citation hydration.
    node_map = {n.node_id: n for n in nodes}
    for selector in artifacts["selectors"]:
        node = node_map.get(selector["node_id"])
        if not node:
            continue
        node.meta = dict(node.meta or {})
        node.meta["selector_bundle"] = selector
        node.meta["text_position"] = selector.get("text_position")
        node.meta["normalization"] = selector.get("normalization")
    db.commit()

    return {
        "generated": True,
        "nodes_with_selectors": artifacts["nodes_with_selectors"],
        "total_nodes": artifacts["total_nodes"],
        "backfill_needed": False,
    }


def build_source_manifest(
    storage: StorageClient,
    doc: DocumentGraph,
    *,
    mime_type: Optional[str],
) -> dict:
    """Build a source manifest payload for the frontend."""
    version = str(doc.version)
    canonical_available = storage.canonical_view_exists(doc.doc_id, version)
    source_map_available = storage.source_map_exists(doc.doc_id, version)
    selectors_available = storage.selectors_exist(doc.doc_id, version)

    selector_total = 0
    if source_map_available:
        try:
            source_map = storage.get_source_map(doc.doc_id, version)
            selector_total = len(source_map.get("nodes", []))
        except Exception:
            selector_total = 0

    return {
        "doc_id": doc.doc_id,
        "version": doc.version,
        "raw_url": f"/v1/documents/{doc.doc_id}/raw",
        "mime_type": mime_type or _mime_from_source(None, doc.source_uri),
        "canonical_view_available": canonical_available,
        "source_map_available": source_map_available,
        "selectors_available": selectors_available,
        "selector_coverage": {
            "nodes_with_selectors": selector_total,
        },
        "backfill_needed": not (canonical_available and source_map_available and selectors_available),
    }


def resolve_citation_selector(
    storage: StorageClient,
    doc: DocumentGraph,
    selector_bundle: Optional[dict],
    *,
    strict: bool = True,
    allow_fuzzy: bool = False,
) -> dict:
    """Resolve a citation selector against canonical document text."""
    if not selector_bundle:
        return {
            "resolve_status": "unresolved",
            "exact_text": None,
            "resolved_position": None,
            "reason": "missing_selector_bundle",
        }

    if not storage.source_map_exists(doc.doc_id, str(doc.version)):
        return {
            "resolve_status": "unresolved",
            "exact_text": None,
            "resolved_position": None,
            "reason": "missing_source_map",
        }

    source_state = selector_bundle.get("source_state") or {}
    expected_hash = source_state.get("content_hash")
    if not _hash_matches(expected_hash, doc.content_hash):
        return {
            "resolve_status": "unresolved",
            "exact_text": None,
            "resolved_position": None,
            "reason": "stale_content_hash",
        }

    source_map = storage.get_source_map(doc.doc_id, str(doc.version))
    canonical_text = source_map.get("canonical_text") or ""
    resolve_status, exact_text, resolved_position, reason = resolve_selector_bundle(
        selector_bundle=selector_bundle,
        canonical_text=canonical_text,
        strict=strict,
        allow_fuzzy=allow_fuzzy,
    )
    return {
        "resolve_status": resolve_status,
        "exact_text": exact_text,
        "resolved_position": resolved_position,
        "reason": reason,
    }


def _find_page_range(source_map: dict, page_index: int) -> Optional[Tuple[int, int]]:
    nodes = source_map.get("nodes") or []
    starts: list[int] = []
    ends: list[int] = []
    for node in nodes:
        if node.get("page_no") != page_index:
            continue
        start = node.get("start")
        end = node.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            continue
        starts.append(start)
        ends.append(end)
    if not starts or not ends:
        return None
    return min(starts), max(ends)


def _match_with_tight_fuzzy(page_text: str, quote_text: str, threshold: float) -> Optional[Tuple[int, int, float]]:
    """Return local page offsets for a high-threshold fuzzy match."""
    quote_norm = normalize_text(quote_text).casefold()
    if not quote_norm:
        return None

    quote_len = max(1, len(quote_text))
    page_len = len(page_text)
    if page_len == 0:
        return None

    # Deterministic candidate windows around occurrences of the quote's first token.
    first_token = quote_norm.split(" ")[0]
    haystack = normalize_text(page_text).casefold()
    anchor_positions: list[int] = []
    search_from = 0
    while True:
        idx = haystack.find(first_token, search_from)
        if idx < 0:
            break
        anchor_positions.append(idx)
        search_from = idx + max(1, len(first_token))
        if len(anchor_positions) >= 32:
            break

    if not anchor_positions:
        return None

    best: Optional[Tuple[int, int, float]] = None
    # Work on raw page text for stable offset output.
    for pos in anchor_positions:
        start = max(0, pos - 24)
        end = min(page_len, start + quote_len + 48)
        candidate = page_text[start:end]
        ratio = SequenceMatcher(
            None,
            normalize_text(candidate).casefold(),
            quote_norm,
        ).ratio()
        if ratio >= threshold and (best is None or ratio > best[2]):
            best = (start, end, ratio)

    return best


def verify_evidence_span(
    *,
    doc_id: str,
    page_index: int,
    quote_text: str,
    locator: Optional[dict],
    source_map: dict,
    allow_fuzzy: bool = False,
    fuzzy_threshold: float = 0.97,
) -> dict:
    """Verify evidence against the cited page only.

    Returns:
        {
          "status": "FOUND" | "NOT_FOUND",
          "matched_locator": Optional[dict],
          "confidence": float,
          "reason": str,
        }
    """
    canonical_text = source_map.get("canonical_text") or ""
    if not canonical_text:
        return {
            "status": "NOT_FOUND",
            "matched_locator": None,
            "confidence": 0.0,
            "reason": "missing_canonical_text",
        }

    quote = (quote_text or "").strip()
    if not quote:
        return {
            "status": "NOT_FOUND",
            "matched_locator": None,
            "confidence": 0.0,
            "reason": "empty_quote_text",
        }

    page_range = _find_page_range(source_map, page_index)
    if not page_range:
        return {
            "status": "NOT_FOUND",
            "matched_locator": None,
            "confidence": 0.0,
            "reason": "page_not_indexed",
        }
    page_start, page_end = page_range
    page_text = canonical_text[page_start:page_end]

    def found(matched_locator: dict, confidence: float, reason: str) -> dict:
        return {
            "status": "FOUND",
            "matched_locator": matched_locator,
            "confidence": confidence,
            "reason": reason,
            "doc_id": doc_id,
            "page_index": page_index,
        }

    def not_found(reason: str) -> dict:
        return {
            "status": "NOT_FOUND",
            "matched_locator": None,
            "confidence": 0.0,
            "reason": reason,
            "doc_id": doc_id,
            "page_index": page_index,
        }

    # 1) Prefer exact locator validation when text offsets are provided.
    if locator and locator.get("type") == "text_offsets":
        start = locator.get("start")
        end = locator.get("end")
        if (
            isinstance(start, int)
            and isinstance(end, int)
            and 0 <= start < end <= len(canonical_text)
            and page_start <= start < end <= page_end
        ):
            extracted = canonical_text[start:end]
            if normalize_text(extracted).casefold() == normalize_text(quote).casefold():
                return found(
                    {"type": "text_offsets", "start": start, "end": end},
                    1.0,
                    "exact_text_offsets_match",
                )
        else:
            return not_found("locator_outside_cited_page")

    # 2) Exact quote search on cited page.
    quote_idx = page_text.find(quote)
    if quote_idx >= 0:
        start = page_start + quote_idx
        end = start + len(quote)
        return found(
            {"type": "text_offsets", "start": start, "end": end},
            1.0,
            "exact_quote_match_on_page",
        )

    # 3) Whitespace-normalized exact check, still constrained to cited page.
    ws_pattern = r"\s+".join(re.escape(part) for part in quote.split())
    if ws_pattern:
        ws_match = re.search(ws_pattern, page_text)
        if ws_match:
            return found(
                {"type": "text_offsets", "start": page_start + ws_match.start(), "end": page_start + ws_match.end()},
                0.99,
                "exact_quote_match_on_page_whitespace_normalized",
            )

    # 4) Optional high-threshold fuzzy fallback.
    if allow_fuzzy:
        fuzzy = _match_with_tight_fuzzy(page_text, quote, threshold=fuzzy_threshold)
        if fuzzy:
            local_start, local_end, score = fuzzy
            return found(
                {"type": "text_offsets", "start": page_start + local_start, "end": page_start + local_end},
                float(score),
                "fuzzy_quote_match_on_page",
            )

    return not_found("evidence_not_found_on_cited_page")
