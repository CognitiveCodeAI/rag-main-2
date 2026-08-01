"""E1: graph-expansion ACL choke point (audit — scattered enforcement / leak).

Verifies QARunner._acl_filter_expanded routes every expansion node list through
the ACL enforcer, so restricted neighbour content cannot reach the packed LLM
context. Pure unit test (QARunner built via __new__ with a mock enforcer).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.graph.expander import ExpandedContext
from app.qa.runner import QARunner


def _node(doc_id):
    return SimpleNamespace(doc_id=doc_id, node_id=f"{doc_id}-n")


def test_acl_filter_expanded_filters_every_node_list():
    runner = QARunner.__new__(QARunner)  # bypass heavy __init__
    enforcer = MagicMock()
    # Mock enforcement: only doc_id == "ok" is accessible.
    enforcer.filter_nodes.side_effect = lambda nodes, stage: [
        n for n in nodes if n.doc_id == "ok"
    ]
    runner.acl_enforcer = enforcer

    expanded = ExpandedContext(
        seed_nodes=[_node("ok"), _node("restricted")],
        adjacent_nodes=[_node("restricted")],
        referenced_nodes=[_node("ok"), _node("ok")],
        explained_by_nodes=[_node("restricted")],
        chain_nodes=[_node("ok"), _node("restricted")],
    )

    out = runner._acl_filter_expanded(expanded)

    assert [n.doc_id for n in out.seed_nodes] == ["ok"]
    assert out.adjacent_nodes == []                 # restricted neighbour dropped
    assert [n.doc_id for n in out.referenced_nodes] == ["ok", "ok"]
    assert out.explained_by_nodes == []             # restricted explainer dropped
    assert [n.doc_id for n in out.chain_nodes] == ["ok"]
    # All five lists were routed through the single choke point.
    assert enforcer.filter_nodes.call_count == 5


def test_acl_filter_expanded_is_passthrough_when_acl_off():
    runner = QARunner.__new__(QARunner)
    enforcer = MagicMock()
    enforcer.filter_nodes.side_effect = lambda nodes, stage: nodes  # ACL off
    runner.acl_enforcer = enforcer

    nodes = [_node("a"), _node("b")]
    expanded = ExpandedContext(
        seed_nodes=list(nodes), adjacent_nodes=list(nodes),
        referenced_nodes=list(nodes), explained_by_nodes=list(nodes),
    )
    out = runner._acl_filter_expanded(expanded)
    assert len(out.seed_nodes) == 2
    assert len(out.adjacent_nodes) == 2
