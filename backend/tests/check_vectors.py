"""Check vectors in Milvus for the test document."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.graph.vector_index import GraphVectorIndex, NODE_TYPE_COLLECTIONS
from pymilvus import Collection, utility

doc_id = '93e7889b428b7579d8221db3b57a93b6'
version = 1

vector_index = GraphVectorIndex()
vector_index.connect()

print(f"Checking vectors for doc_id={doc_id} version={version}")
print()

for node_type, collection_name in NODE_TYPE_COLLECTIONS.items():
    if utility.has_collection(collection_name):
        collection = Collection(collection_name)
        collection.load()
        results = collection.query(
            expr=f'doc_id == "{doc_id}" and version == {version}',
            output_fields=['node_id', 'page_no']
        )
        print(f'{node_type}: {len(results)} vectors')
    else:
        print(f'{node_type}: collection does not exist')
