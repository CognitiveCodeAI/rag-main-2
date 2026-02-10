"""Clear Milvus vectors for a specific document."""

import os
import sys
from dotenv import load_dotenv
from pymilvus import connections, Collection, utility

load_dotenv()

doc_id = sys.argv[1] if len(sys.argv) > 1 else '37660ee55b1fb2aa63579e3aeb2aca97'

# Connection settings from environment (defaults match docker-compose.yml)
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")

connections.connect(alias='default', host=MILVUS_HOST, port=MILVUS_PORT)

for coll_name in ['graph_chunks_v2', 'graph_figures_v2', 'graph_tables_v2']:
    if utility.has_collection(coll_name):
        coll = Collection(coll_name)
        coll.load()
        expr = f'doc_id == "{doc_id}"'
        result = coll.delete(expr)
        print(f'{coll_name}: deleted vectors for {doc_id}')

connections.disconnect('default')
print('Done')
