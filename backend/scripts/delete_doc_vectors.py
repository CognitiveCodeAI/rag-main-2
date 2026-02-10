"""Delete vectors for a document from Milvus."""
import os
import sys
from dotenv import load_dotenv
from pymilvus import connections, Collection, utility

load_dotenv()

doc_id = sys.argv[1] if len(sys.argv) > 1 else '37660ee55b1fb2aa63579e3aeb2aca97'

# Connection settings from environment (defaults match docker-compose.yml)
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")

# Connect to Milvus
connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)

# Delete from both chunk collections (v1 and v2)
for coll_name in ['graph_chunks_v1', 'graph_chunks_v2']:
    if utility.has_collection(coll_name):
        coll = Collection(coll_name)
        coll.load()
        expr = f'doc_id == "{doc_id}"'
        result = coll.delete(expr)
        print(f'{coll_name}: Deleted, result={result}')
    else:
        print(f'{coll_name}: Does not exist')

print('Milvus vectors cleared!')
