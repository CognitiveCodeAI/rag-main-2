"""Verify system is ready for testing."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pymilvus import connections, Collection, utility
from app.db.session import session_scope
from app.db.graph_models import Node, Edge, DocumentGraph

# Connection settings from environment (defaults match docker-compose.yml)
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))

def main():
    # Check Milvus
    connections.connect('default', host=MILVUS_HOST, port=MILVUS_PORT)
    print('=== MILVUS COLLECTIONS ===')
    
    for name in ['graph_chunks_v2', 'graph_figures_v2', 'graph_tables_v2']:
        if name in utility.list_collections():
            col = Collection(name)
            col.load()
            # Use query with Eventually consistency to see unflushed data
            res = col.query(
                expr='node_id != ""',
                output_fields=['node_id'],
                limit=1000,
                consistency_level='Eventually'
            )
            print(f'  {name}: {len(res)} vectors')
    
    connections.disconnect('default')
    
    # Check Database
    print()
    print('=== DATABASE ===')
    with session_scope() as db:
        docs = db.query(DocumentGraph).all()
        for d in docs:
            print(f'  Doc: {d.doc_id[:16]}...')
            print(f'    Collection Version: {d.embedded_collection_version}')
        
        nodes = db.query(Node).count()
        edges = db.query(Edge).count()
        chunks = db.query(Node).filter(Node.node_type == 'chunk').count()
        figures = db.query(Node).filter(Node.node_type == 'figure').count()
        print(f'  Nodes: {nodes} total ({chunks} chunks, {figures} figures)')
        print(f'  Edges: {edges}')
    
    print()
    print('=== READY FOR TESTING ===')

if __name__ == '__main__':
    main()
