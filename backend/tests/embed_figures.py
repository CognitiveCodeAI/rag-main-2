"""Manually embed figure and table nodes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import session_scope
from app.db.graph_models import Node, NodeType
from app.embeddings.client import EmbeddingClient
from app.graph.vector_index import GraphVectorIndex, VectorRecord

doc_id = '93e7889b428b7579d8221db3b57a93b6'
version = 1

print(f"Embedding figures/tables for doc_id={doc_id} version={version}")
print()

with session_scope() as db:
    # Get figure and table nodes
    nodes = db.query(Node).filter(
        Node.doc_id == doc_id,
        Node.version == version,
        Node.node_type.in_([NodeType.figure, NodeType.table])
    ).all()
    
    print(f"Found {len(nodes)} figure/table nodes")
    
    # Get text for each
    valid_nodes = []
    texts = []
    
    for node in nodes:
        parts = []
        if node.label:
            parts.append(node.label)
        if node.caption_md:
            parts.append(node.caption_md)
        if node.text_plain:
            parts.append(node.text_plain)
        elif node.text_md:
            parts.append(node.text_md)
        
        text = "\n".join(parts).strip()
        
        if text:
            valid_nodes.append(node)
            texts.append(text)
            print(f"  {node.node_id[:16]}... {node.node_type.value} text_len={len(text)}")
    
    print(f"\nValid nodes with text: {len(valid_nodes)}")
    
    if not valid_nodes:
        print("No valid nodes to embed")
        sys.exit(0)
    
    # Embed
    print("\nGenerating embeddings...")
    embed_client = EmbeddingClient()
    embeddings, _ = embed_client.embed_texts(texts)
    print(f"Generated {len(embeddings)} embeddings")
    
    # Index
    print("\nIndexing vectors...")
    vector_index = GraphVectorIndex()
    vector_index.ensure_collections()
    
    for node_type in [NodeType.figure, NodeType.table]:
        type_name = node_type.value
        type_nodes = [n for n in valid_nodes if n.node_type == node_type]
        type_embeddings = [embeddings[valid_nodes.index(n)] for n in type_nodes]
        
        if not type_nodes:
            continue
        
        records = [
            VectorRecord(
                node_id=n.node_id,
                doc_id=doc_id,
                version=version,
                page_no=n.page_no,
                vector=emb
            )
            for n, emb in zip(type_nodes, type_embeddings)
        ]
        
        try:
            indexed = vector_index.insert(type_name, records)
            print(f"Indexed {indexed} {type_name} vectors")
        except Exception as e:
            print(f"Error indexing {type_name}: {e}")

print("\nDone!")
