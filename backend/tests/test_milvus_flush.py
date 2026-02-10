"""Quick test for Milvus insert + flush."""

from pymilvus import connections, Collection
from app.config import get_settings
import time

def test_insert_flush():
    settings = get_settings()
    connections.connect('default', host=settings.milvus_host, port=settings.milvus_port)

    print('=== Testing Insert + Flush with Fresh Collections ===')

    col = Collection('graph_chunks_v2')

    # Test record
    test_data = [
        ['test_node_002'],
        ['test_doc_002'],
        [1],
        [1],
        [[0.1] * 3072],
        [-1],
        [''],
        [''],
        [0],
    ]

    print('Inserting...')
    start = time.time()
    result = col.insert(test_data)
    print(f'Insert: {time.time() - start:.2f}s')

    print('Flushing...')
    flush_start = time.time()
    col.flush()
    print(f'Flush: {time.time() - flush_start:.2f}s')

    print(f'Entities: {col.num_entities}')

    # Cleanup
    print('Cleanup...')
    col.delete('node_id == "test_node_002"')
    col.flush()
    print('Done!')

if __name__ == "__main__":
    test_insert_flush()
