"""Diagnose why q9 returned 'No chunks found'."""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from app.db.session import session_scope
from app.db.graph_models import Node, DocumentGraph
from app.qa.normalizer import normalize_query
from app.qa.constraint_parser import parse_constraints
from app.embeddings.client import get_embedding_client
from app.graph.vector_index import GraphVectorIndex
from pymilvus import connections, Collection, utility

doc_id = '37660ee55b1fb2aa63579e3aeb2aca97'
question = 'What happens to the franchise upon termination according to the agreement?'

print('=== Q9 DIAGNOSTIC DUMP ===')
print()

# 1. Document info
with session_scope() as db:
    doc = db.query(DocumentGraph).filter(DocumentGraph.doc_id == doc_id).first()
    print('1. DOCUMENT INFO')
    print(f'   doc_id: {doc_id}')
    print(f'   embedded_collection_version: {doc.embedded_collection_version if doc else "NOT FOUND"}')
    
    # Node counts
    chunks = db.query(Node).filter(Node.doc_id == doc_id, Node.node_type == 'chunk').count()
    figures = db.query(Node).filter(Node.doc_id == doc_id, Node.node_type == 'figure').count()
    tables = db.query(Node).filter(Node.doc_id == doc_id, Node.node_type == 'table').count()
    print(f'   Postgres nodes: {chunks} chunks, {figures} figures, {tables} tables')
    print()

# 2. Query normalization
print('2. QUERY NORMALIZATION')
normalized = normalize_query(question, doc_id)
print(f'   Original: {question}')
print(f'   Normalized queries: {normalized.normalized_queries}')
print(f'   Detected intent: {normalized.detected_intent}')
print()

# 3. Constraint parsing
print('3. CONSTRAINT PARSING')
constraints = parse_constraints(question)
filter_expr = constraints.get_milvus_filter_expr()
print(f'   Constraints: {constraints.to_dict()}')
print(f'   Milvus filter_expr: {filter_expr}')
print()

# 4. Milvus collection info
print('4. MILVUS COLLECTIONS')
host = os.getenv('MILVUS_HOST', '192.168.100.25')
port = os.getenv('MILVUS_PORT', '19530')
connections.connect('diag', host=host, port=port)

for coll_name in ['graph_chunks_v2', 'graph_figures_v2', 'graph_tables_v2']:
    if coll_name in utility.list_collections(using='diag'):
        col = Collection(coll_name, using='diag')
        col.load()
        # Count for this doc_id
        res = col.query(
            expr=f'doc_id == "{doc_id}"',
            output_fields=['node_id'],
            limit=10000,
            consistency_level='Eventually'
        )
        print(f'   {coll_name}: {len(res)} vectors for this doc_id')

connections.disconnect('diag')
print()

# 5. Embedding test
print('5. EMBEDDING TEST')
embed_client = get_embedding_client()
vec, tokens = embed_client.embed_single(question)
print(f'   Vector dim: {len(vec)}')
print(f'   Tokens: {tokens}')
print()

# 6. Direct vector search test
print('6. DIRECT VECTOR SEARCH TEST')
vi = GraphVectorIndex(collection_version='v2')

# Search without filter
results_no_filter = vi.search(
    node_type='chunk',
    query_vector=vec,
    top_k=5,
    doc_id_filter=doc_id,
    filter_expr=None
)
print(f'   Without filter_expr: {len(results_no_filter)} results')

if results_no_filter:
    print('   Top results:')
    for r in results_no_filter[:3]:
        print(f'     - {r["node_id"][:16]}... page={r.get("page_no")} score={r["score"]:.3f}')

# Search with filter
if filter_expr:
    results_with_filter = vi.search(
        node_type='chunk',
        query_vector=vec,
        top_k=5,
        doc_id_filter=doc_id,
        filter_expr=filter_expr
    )
    print(f'   With filter_expr ({filter_expr}): {len(results_with_filter)} results')
else:
    print(f'   No filter_expr to test')

print()

# 7. Check if "termination" content exists
print('7. CONTENT CHECK - Does "termination" exist in the document?')
with session_scope() as db:
    term_chunks = db.query(Node).filter(
        Node.doc_id == doc_id,
        Node.node_type == 'chunk',
        Node.text_plain.ilike('%termination%')
    ).limit(5).all()
    print(f'   Chunks containing "termination": {len(term_chunks)} found')
    for c in term_chunks[:3]:
        preview = (c.text_plain or '')[:100].replace('\n', ' ')
        print(f'     - Page {c.page_no}: {preview}...')

print()
print('=== END DIAGNOSTIC ===')
