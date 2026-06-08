"""Characterization tests for structured-target detection (E2 3/3)."""

from app.qa.structured_targets import detect_structured_targets


def test_detects_figures_and_tables():
    out = detect_structured_targets("Compare Figure 1.5 with Table 4 and Fig. 2")
    assert out["figures"] == ["Figure 1.5", "Figure 2"]
    assert out["tables"] == ["Table 4"]


def test_detects_appendix_uppercased():
    out = detect_structured_targets("See Appendix b for details")
    assert out["appendices"] == ["Appendix B"]


def test_detects_sections_titlecased_and_deduped():
    out = detect_structured_targets("the conclusion and the Conclusion and methodology")
    assert out["sections"] == ["Conclusion", "Methodology"]


def test_no_match_returns_empty_lists():
    out = detect_structured_targets("what is the revenue?")
    assert out == {"figures": [], "tables": [], "appendices": [], "sections": []}


def test_runner_method_delegates_identically():
    # The QARunner wrapper must produce the same result as the module function.
    from app.qa.runner import QARunner
    runner = QARunner.__new__(QARunner)
    q = "Explain Figure 3 in the Results section"
    assert runner._detect_structured_targets(q) == detect_structured_targets(q)
