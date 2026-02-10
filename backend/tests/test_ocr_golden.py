"""Golden test validation for OCR prompts.

Validates that OCR output meets expected patterns and structure
based on golden test fixtures.
"""

import json
import re
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ocr.prompts import OCRPrompts, PROMPT_VERSION

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "ocr"


def load_fixture(name: str) -> dict:
    """Load a golden fixture."""
    path = FIXTURES_DIR / f"{name}.json"
    with open(path) as f:
        return json.load(f)


def validate_against_rules(text: str, rules: dict) -> tuple[bool, list]:
    """Validate OCR output against validation rules.
    
    Args:
        text: OCR output text
        rules: Validation rules dict
        
    Returns:
        (passed, errors) tuple
    """
    errors = []
    
    # must_contain rules
    if "must_contain" in rules:
        for required in rules["must_contain"]:
            if required not in text:
                errors.append(f"Missing required content: '{required}'")
    
    # must_contain_one_of rules
    if "must_contain_one_of" in rules:
        found = any(opt in text for opt in rules["must_contain_one_of"])
        if not found:
            errors.append(f"Missing one of: {rules['must_contain_one_of']}")
    
    # must_match_pattern rules
    if "must_match_pattern" in rules:
        pattern = rules["must_match_pattern"]
        if not re.search(pattern, text):
            errors.append(f"Pattern not matched: '{pattern}'")
    
    # should_not_contain rules
    if "should_not_contain" in rules:
        for forbidden in rules["should_not_contain"]:
            if forbidden.lower() in text.lower():
                errors.append(f"Contains forbidden content: '{forbidden}'")
    
    # min_lines rules
    if "min_lines" in rules:
        lines = [l for l in text.split('\n') if l.strip()]
        if len(lines) < rules["min_lines"]:
            errors.append(f"Too few lines: {len(lines)} < {rules['min_lines']}")
    
    # min_paragraphs rules
    if "min_paragraphs" in rules:
        paragraphs = [p for p in text.split('\n\n') if p.strip()]
        if len(paragraphs) < rules["min_paragraphs"]:
            errors.append(f"Too few paragraphs: {len(paragraphs)} < {rules['min_paragraphs']}")
    
    # should_contain_numbers rules
    if rules.get("should_contain_numbers"):
        if not re.search(r'\d+', text):
            errors.append("Expected numbers but found none")
    
    return len(errors) == 0, errors


class TestGoldenTableOCR:
    """Test OCR table output against golden fixture."""
    
    def test_sample_output_is_valid(self):
        """The sample expected output should pass validation."""
        fixture = load_fixture("golden_table")
        sample = fixture["sample_expected_output"]
        rules = fixture["validation_rules"]
        
        passed, errors = validate_against_rules(sample, rules)
        
        assert passed, f"Sample failed validation: {errors}"
    
    def test_prompt_version_matches(self):
        """Fixture prompt version matches current prompts."""
        fixture = load_fixture("golden_table")
        assert fixture["prompt_version"] == PROMPT_VERSION
    
    def test_region_prompt_mentions_tables(self):
        """Region prompt should mention table handling."""
        prompt = OCRPrompts.get_region_prompt()
        assert "table" in prompt.lower()


class TestGoldenFullPageOCR:
    """Test OCR full page output against golden fixture."""
    
    def test_sample_output_is_valid(self):
        """The sample expected output should pass validation."""
        fixture = load_fixture("golden_full_page")
        sample = fixture["sample_expected_output"]
        rules = fixture["validation_rules"]
        
        passed, errors = validate_against_rules(sample, rules)
        
        assert passed, f"Sample failed validation: {errors}"
    
    def test_prompt_version_matches(self):
        """Fixture prompt version matches current prompts."""
        fixture = load_fixture("golden_full_page")
        assert fixture["prompt_version"] == PROMPT_VERSION
    
    def test_full_page_prompt_mentions_markdown(self):
        """Full page prompt should mention markdown."""
        prompt = OCRPrompts.get_full_page_prompt()
        assert "markdown" in prompt.lower()
    
    def test_full_page_prompt_mentions_headings(self):
        """Full page prompt should mention headings."""
        prompt = OCRPrompts.get_full_page_prompt()
        assert "heading" in prompt.lower()


class TestGoldenChartOCR:
    """Test OCR chart output against golden fixture."""
    
    def test_sample_output_is_valid(self):
        """The sample expected output should pass validation."""
        fixture = load_fixture("golden_chart")
        sample = fixture["sample_expected_output"]
        rules = fixture["validation_rules"]
        
        passed, errors = validate_against_rules(sample, rules)
        
        assert passed, f"Sample failed validation: {errors}"
    
    def test_prompt_version_matches(self):
        """Fixture prompt version matches current prompts."""
        fixture = load_fixture("golden_chart")
        assert fixture["prompt_version"] == PROMPT_VERSION
    
    def test_region_prompt_mentions_charts(self):
        """Region prompt should mention chart handling."""
        prompt = OCRPrompts.get_region_prompt()
        # Should mention labels, legend, or axis
        assert any(word in prompt.lower() for word in ["label", "legend", "axis", "chart"])


def test_all_fixtures_load():
    """All fixtures should load without errors."""
    fixtures = ["golden_table", "golden_full_page", "golden_chart"]
    
    for name in fixtures:
        fixture = load_fixture(name)
        assert "description" in fixture
        assert "validation_rules" in fixture
        assert "sample_expected_output" in fixture
        print(f"  ✓ {name}.json loaded")


if __name__ == "__main__":
    print("=" * 60)
    print("OCR Golden Tests")
    print("=" * 60)
    
    # Load test
    print("\n=== Loading Fixtures ===")
    test_all_fixtures_load()
    
    # Run test classes
    test_classes = [
        TestGoldenTableOCR,
        TestGoldenFullPageOCR,
        TestGoldenChartOCR,
    ]
    
    for test_class in test_classes:
        print(f"\n=== {test_class.__name__} ===")
        instance = test_class()
        
        for method_name in dir(instance):
            if method_name.startswith("test_"):
                try:
                    getattr(instance, method_name)()
                    print(f"  ✓ {method_name}")
                except Exception as e:
                    print(f"  ✗ {method_name}: {e}")
    
    print("\n" + "=" * 60)
    print("Golden tests complete")
