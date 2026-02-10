"""Embed all documents in the database."""

import sys
import os
from pathlib import Path

# Unbuffered output
sys.stdout.reconfigure(line_buffering=True)

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

print("Starting embedding script...", flush=True)

from app.db.session import get_session
from app.db.graph_models import DocumentGraph
from app.tasks.embed_nodes import embed_document_nodes_sync

print("Imports complete", flush=True)


def main():
    print("Getting database session...", flush=True)
    db = next(get_session())
    
    try:
        # Get all documents
        docs = db.query(DocumentGraph).all()
        print(f"Found {len(docs)} documents to embed", flush=True)
        
        total_embedded = 0
        total_indexed = 0
        
        for doc in docs:
            print(f"\nEmbedding: {doc.doc_id[:16]}... (v{doc.version})", flush=True)
            try:
                result = embed_document_nodes_sync(doc.doc_id, doc.version, db)
                
                embedded = result.get("embedded", 0)
                indexed = result.get("indexed", 0)
                tokens = result.get("tokens", "N/A")
                
                print(f"  Embedded: {embedded}", flush=True)
                print(f"  Indexed: {indexed}", flush=True)
                print(f"  Tokens: {tokens}", flush=True)
                
                total_embedded += embedded
                total_indexed += indexed
            except Exception as e:
                print(f"  ERROR: {e}", flush=True)
                import traceback
                traceback.print_exc()
        
        print(f"\n{'='*60}", flush=True)
        print(f"TOTAL: {total_embedded} embedded, {total_indexed} indexed", flush=True)
        print(f"{'='*60}", flush=True)
        
    finally:
        db.close()


if __name__ == "__main__":
    main()
