"""Backfill Evidence Highlighting V2 provenance for one stored native PDF.

Usage from ``backend/``:
    venv/bin/python -m scripts.backfill_evidence_v2 <graph_doc_id> [--version N]
"""

from __future__ import annotations

import argparse

from app.db.graph_models import DocumentGraph
from app.db.session import session_scope
from app.services.document_identity import find_legacy_for_graph
from app.services.highlighting import backfill_pdf_source_provenance
from app.storage.minio_client import get_storage_client


def _load_raw_pdf(db, doc: DocumentGraph) -> bytes:
    storage = get_storage_client()

    graph_files = storage.list_raw_files(doc.doc_id, str(doc.version))
    if graph_files:
        raw, _ = storage.get_raw_with_content_type(
            doc.doc_id,
            str(doc.version),
            graph_files[0],
        )
        return raw

    legacy = find_legacy_for_graph(db, doc.doc_id, doc.version)
    if legacy:
        legacy_files = storage.list_raw_files(legacy.doc_id, legacy.version_id)
        if legacy_files:
            raw, _ = storage.get_raw_with_content_type(
                legacy.doc_id,
                legacy.version_id,
                legacy_files[0],
            )
            return raw

    raise FileNotFoundError(f"original stored file not found for {doc.doc_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("doc_id", help="Canonical graph document ID")
    parser.add_argument(
        "--version",
        type=int,
        help="Document version to upgrade (defaults to the latest version)",
    )
    args = parser.parse_args()

    with session_scope() as db:
        query = db.query(DocumentGraph).filter(DocumentGraph.doc_id == args.doc_id)
        if args.version is not None:
            query = query.filter(DocumentGraph.version == args.version)
        doc = query.order_by(DocumentGraph.version.desc()).first()
        if not doc:
            version_suffix = (
                f" version {args.version}" if args.version is not None else ""
            )
            raise SystemExit(
                f"graph document not found: {args.doc_id}{version_suffix}"
            )
        raw_pdf = _load_raw_pdf(db, doc)
        result = backfill_pdf_source_provenance(db, doc, raw_pdf)
        print(
            "Evidence V2 backfill complete: "
            f"doc={result['doc_id']} v{result['version']} "
            f"exact={result['exact_nodes']} "
            f"approximate={result['approximate_nodes']} "
            f"unavailable={result['unavailable_nodes']}"
        )


if __name__ == "__main__":
    main()
