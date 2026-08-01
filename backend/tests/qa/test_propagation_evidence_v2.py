"""Evidence V2 behavior in propagation-safety mode."""

from app.qa.propagation.synthesizer import _prepare_grounded_citations
from app.qa.propagation.types import EvidencePacket, EvidenceSnippet, SubAnswer
from app.qa.propagation.verifier import Verifier
from app.qa.runner import QARunner


def test_verifier_accepts_only_verbatim_citations_from_the_named_snippet():
    snippets = [
        EvidenceSnippet(
            node_id="n1",
            page_no=4,
            text="The patient consent form must be signed before treatment.",
        )
    ]

    valid = Verifier._validate_citations(
        [
            {
                "node_id": "n1",
                "page_no": 4,
                "label": None,
                "exact_quote": "The patient consent form must be signed before treatment.",
            }
        ],
        snippets,
    )
    invalid = Verifier._validate_citations(
        [
            {
                "node_id": "n1",
                "page_no": 4,
                "label": None,
                "exact_quote": "Consent is required.",
            }
        ],
        snippets,
    )

    assert valid[0]["exact_quote"].startswith("The patient")
    assert invalid == []


def test_synthesizer_converts_legacy_refs_to_stable_ids_and_preserves_quote():
    sub_answers = [
        SubAnswer(
            subq_id="sq1",
            answer="The fee is $45,000.",
            citations=[
                {
                    "node_id": "fee-node",
                    "page_no": 5,
                    "label": None,
                    "exact_quote": "The fee is $45,000.",
                }
            ],
            confidence=1.0,
        )
    ]

    answer, citations = _prepare_grounded_citations(
        "The fee is $45,000 [fee-node:5].",
        [{"node_id": "fee-node", "page_no": 5, "label": None}],
        sub_answers,
    )

    assert answer == "The fee is $45,000 [C1]."
    assert citations == [
        {
            "citation_id": "C1",
            "node_id": "fee-node",
            "page_no": 5,
            "label": None,
            "exact_quote": "The fee is $45,000.",
        }
    ]


def test_propagation_context_ids_are_stable_deduplicated_and_groundable():
    packets = [
        EvidencePacket(
            subq_id="sq1",
            subq_text="first",
            snippets=[
                EvidenceSnippet(node_id="n1", page_no=1, text="one"),
                EvidenceSnippet(node_id="n2", page_no=2, text="two"),
            ],
        ),
        EvidencePacket(
            subq_id="sq2",
            subq_text="second",
            snippets=[
                EvidenceSnippet(node_id="n2", page_no=2, text="two"),
                EvidenceSnippet(node_id="n3", page_no=3, text="three"),
            ],
        ),
    ]

    assert QARunner._collect_packet_node_ids(packets) == ["n1", "n2", "n3"]
