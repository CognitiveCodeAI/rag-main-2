"""Runner contract tests for evidence-chain fallback and ACL scrubbing."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.graph.expander import ExpandedContext
from app.qa.evidence_chain import (
    ChainNodeScore,
    EvidenceChainResult,
    RouteDecision,
)
from app.qa.runner import QARunner


def empty_context() -> ExpandedContext:
    return ExpandedContext(
        seed_nodes=[],
        adjacent_nodes=[],
        referenced_nodes=[],
        explained_by_nodes=[],
    )


def test_disabled_feature_does_not_call_engine_or_change_context():
    runner = QARunner.__new__(QARunner)
    runner.evidence_chain_enabled = False
    runner.evidence_chain_mode = "off"
    runner.evidence_chain_engine = MagicMock()
    runner.evidence_chain_engine.config.route_threshold = 0.55
    expanded = empty_context()

    output, result, elapsed_ms = runner._apply_evidence_chain(
        expanded,
        "Compare two clauses",
        {},
        None,
        None,
    )

    assert output is expanded
    assert result.applied is False
    assert result.route.reasons == ("mode_off",)
    assert elapsed_ms == 0.0
    runner.evidence_chain_engine.build.assert_not_called()


def test_engine_error_falls_back_without_exposing_exception_message():
    runner = QARunner.__new__(QARunner)
    runner.evidence_chain_enabled = True
    runner.evidence_chain_mode = "on"
    runner.evidence_chain_engine = MagicMock()
    runner.evidence_chain_engine.config.route_threshold = 0.55
    runner.evidence_chain_engine.build.side_effect = RuntimeError(
        "secret restricted-node-id"
    )
    expanded = empty_context()

    output, result, elapsed_ms = runner._apply_evidence_chain(
        expanded,
        "Compare two clauses",
        {},
        None,
        None,
    )

    assert output is expanded
    assert result.applied is False
    assert result.fallback_used is True
    assert result.fallback_reason == "engine_error:RuntimeError"
    assert "secret" not in str(result.to_audit_dict())
    assert elapsed_ms >= 0.0


def test_final_acl_choke_point_scrubs_engine_selection_and_audit():
    runner = QARunner.__new__(QARunner)
    runner.evidence_chain_enabled = True
    runner.evidence_chain_mode = "on"
    runner.evidence_chain_engine = MagicMock()
    runner.evidence_chain_engine.config.route_threshold = 0.55
    allowed = SimpleNamespace(
        node_id="allowed",
        doc_id="doc",
        text_plain="Allowed",
    )
    denied = SimpleNamespace(
        node_id="denied",
        doc_id="doc",
        text_plain="Denied",
    )
    chain_result = EvidenceChainResult(
        route=RouteDecision(True, "on", 1.0, ("forced_on",)),
        applied=True,
        selected_scores=[
            ChainNodeScore("allowed", 0.9, 0.8, 1.0, 1.0, True),
            ChainNodeScore("denied", 0.8, 0.7, 1.0, 0.0, False),
        ],
        ordered_node_ids=["allowed", "denied"],
        selected_node_ids={"allowed", "denied"},
        additional_nodes=[allowed, denied],
    )
    runner.evidence_chain_engine.build.return_value = chain_result
    runner.acl_enforcer = MagicMock()
    runner.acl_enforcer.filter_nodes.side_effect = lambda nodes, stage: [
        node for node in nodes if node.node_id != "denied"
    ]

    output, result, _ = runner._apply_evidence_chain(
        empty_context(),
        "Compare two clauses",
        {"allowed": 1.0},
        "doc",
        1,
    )

    assert [node.node_id for node in output.chain_nodes] == ["allowed"]
    assert result.selected_node_ids == {"allowed"}
    assert result.ordered_node_ids == ["allowed"]
    assert "denied" not in str(result.to_audit_dict())
