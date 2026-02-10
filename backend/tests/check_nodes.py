"""Check nodes in database for the test document."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import session_scope
from app.db.graph_models import Node, NodeType

doc_id = '93e7889b428b7579d8221db3b57a93b6'
version = 1

print(f"Checking nodes for doc_id={doc_id} version={version}")
print()

with session_scope() as db:
    for node_type in NodeType:
        count = db.query(Node).filter(
            Node.doc_id == doc_id,
            Node.version == version,
            Node.node_type == node_type
        ).count()
        print(f'{node_type.value}: {count} nodes')
    
    # Show a sample figure/table if exists
    fig_nodes = db.query(Node).filter(
        Node.doc_id == doc_id,
        Node.version == version,
        Node.node_type.in_([NodeType.figure, NodeType.table])
    ).limit(3).all()
    
    if fig_nodes:
        print("\nSample figure/table nodes:")
        for n in fig_nodes:
            text_len = len(n.text_plain or n.text_md or "")
            print(f"  - {n.node_id[:16]}... type={n.node_type.value} label={n.label} text_len={text_len}")
