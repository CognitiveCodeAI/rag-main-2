"""Tests for structured claim-level citations returned by the answer model."""

from types import SimpleNamespace

from app.llm.openai_client import OpenAIClient


def test_parse_grounded_response_with_stable_ids_and_exact_quotes():
    parsed = OpenAIClient._parse_grounded_response(
        """
        {
          "answer": "The fee is $45,000 [C1].",
          "citations": [
            {
              "citation_id": "C1",
              "node_id": "fee-node",
              "page_no": 5,
              "exact_quote": "The fee is $45,000.",
              "label": null
            }
          ]
        }
        """
    )

    assert parsed is not None
    answer, citations = parsed
    assert answer == "The fee is $45,000 [C1]."
    assert citations[0].citation_id == "C1"
    assert citations[0].exact_quote == "The fee is $45,000."


def test_parse_grounded_response_rejects_missing_citation_payload():
    assert OpenAIClient._parse_grounded_response(
        '{"answer":"The fee is $45,000 [C1].","citations":[]}'
    ) is None


def test_parse_grounded_response_rejects_duplicate_ids():
    assert OpenAIClient._parse_grounded_response(
        """
        {
          "answer": "One [C1]. Two [C1].",
          "citations": [
            {"citation_id":"C1","node_id":"n1","page_no":1,"exact_quote":"One.","label":null},
            {"citation_id":"C1","node_id":"n2","page_no":2,"exact_quote":"Two.","label":null}
          ]
        }
        """
    ) is None


def test_generate_answer_requests_strict_schema_and_returns_structured_citations():
    client = object.__new__(OpenAIClient)
    client.model = "test-model"
    captured = {}

    def fake_create(request, _timeout):
        captured.update(request)
        return SimpleNamespace(
            output_text=(
                '{"answer":"The fee is $45,000 [C1].","citations":['
                '{"citation_id":"C1","node_id":"n1","page_no":1,'
                '"exact_quote":"The fee is $45,000.","label":null}]}'
            ),
            usage=SimpleNamespace(input_tokens=10, output_tokens=20, total_tokens=30),
            model="test-model",
        )

    client._responses_create_with_retry = fake_create
    result = client.generate_answer(
        context="[n1:1] The fee is $45,000.",
        question="What is the fee?",
    )

    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["text"]["format"]["strict"] is True
    citation_schema = captured["text"]["format"]["schema"]["properties"]["citations"]["items"]
    assert set(citation_schema["required"]) == set(citation_schema["properties"])
    assert result.answer == "The fee is $45,000 [C1]."
    assert result.citations[0].citation_id == "C1"


def test_validate_grounded_citations_checks_node_page_and_verbatim_quote():
    context = "[n1:5] source=seed\nThe filing fee is $250."
    parsed = OpenAIClient._parse_grounded_response(
        '{"answer":"The filing fee is $250 [C1].","citations":['
        '{"citation_id":"C1","node_id":"n1","page_no":5,'
        '"exact_quote":"The filing fee is $250.","label":null}]}'
    )
    assert parsed is not None
    assert OpenAIClient._validate_grounded_citations(context, *parsed) == []

    parsed_bad = OpenAIClient._parse_grounded_response(
        '{"answer":"The filing fee is $250 [C1].","citations":['
        '{"citation_id":"C1","node_id":"made-up","page_no":8,'
        '"exact_quote":"A paraphrased filing fee.","label":null}]}'
    )
    assert parsed_bad is not None
    errors = OpenAIClient._validate_grounded_citations(context, *parsed_bad)
    assert any("unknown node_id" in error for error in errors)


def test_canonicalize_citation_reference_only_strips_matching_page_suffix():
    context = "[fee:5] node_id=fee page_no=5 source=seed\nThe filing fee is $250."
    parsed = OpenAIClient._parse_grounded_response(
        '{"answer":"The filing fee is $250 [C1].","citations":['
        '{"citation_id":"C1","node_id":"fee:5","page_no":5,'
        '"exact_quote":"The filing fee is $250.","label":null}]}'
    )
    assert parsed is not None
    OpenAIClient._canonicalize_citation_references(context, parsed[1])
    assert parsed[1][0].node_id == "fee"
    assert OpenAIClient._validate_grounded_citations(context, *parsed) == []

    parsed_wrong_page = OpenAIClient._parse_grounded_response(
        '{"answer":"The filing fee is $250 [C1].","citations":['
        '{"citation_id":"C1","node_id":"fee:9","page_no":9,'
        '"exact_quote":"The filing fee is $250.","label":null}]}'
    )
    assert parsed_wrong_page is not None
    OpenAIClient._canonicalize_citation_references(context, parsed_wrong_page[1])
    assert parsed_wrong_page[1][0].node_id == "fee:9"


def test_generate_answer_repairs_invalid_citation_metadata_before_returning():
    client = object.__new__(OpenAIClient)
    client.model = "test-model"
    responses = [
        '{"answer":"The fee is $250 [C1].","citations":['
        '{"citation_id":"C1","node_id":"wrong","page_no":9,'
        '"exact_quote":"The fee is $250.","label":null}]}',
        '{"answer":"The fee is $250 [C1].","citations":['
        '{"citation_id":"C1","node_id":"fee","page_no":1,'
        '"exact_quote":"The fee is $250.","label":null}]}',
    ]
    requests = []

    def fake_create(request, _timeout):
        requests.append(request)
        return SimpleNamespace(
            output_text=responses.pop(0),
            usage=SimpleNamespace(input_tokens=10, output_tokens=20, total_tokens=30),
            model="test-model",
        )

    client._responses_create_with_retry = fake_create
    result = client.generate_answer(
        context="[fee:1] source=seed\nThe fee is $250.",
        question="What is the fee?",
    )

    assert len(requests) == 2
    assert "CITATION_VALIDATION_FEEDBACK" in requests[1]["input"]
    assert result.citations[0].node_id == "fee"
