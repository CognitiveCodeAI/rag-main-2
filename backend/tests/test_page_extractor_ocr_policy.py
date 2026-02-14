"""Unit tests for PageExtractor OCR policy decisions."""

from app.graph.page_extractor import PageExtractor


def test_ocr_disabled_for_text_layer_by_default():
    extractor = PageExtractor(skip_ocr=False, quality_threshold=0.3)
    extractor.settings.ocr_text_layer_fallback_enabled = False
    extractor.settings.ocr_text_layer_min_chars = 200

    assert extractor._should_use_ocr(
        has_text_layer=True,
        native_char_count=42,
        quality_score=0.01,
        force_ocr=False,
    ) is False


def test_ocr_enabled_for_pages_without_text_layer():
    extractor = PageExtractor(skip_ocr=False, quality_threshold=0.3)
    extractor.settings.ocr_text_layer_fallback_enabled = False

    assert extractor._should_use_ocr(
        has_text_layer=False,
        native_char_count=0,
        quality_score=0.0,
        force_ocr=False,
    ) is True


def test_ocr_text_layer_fallback_requires_low_chars_and_low_quality():
    extractor = PageExtractor(skip_ocr=False, quality_threshold=0.3)
    extractor.settings.ocr_text_layer_fallback_enabled = True
    extractor.settings.ocr_text_layer_min_chars = 200

    assert extractor._should_use_ocr(
        has_text_layer=True,
        native_char_count=120,
        quality_score=0.2,
        force_ocr=False,
    ) is True

    assert extractor._should_use_ocr(
        has_text_layer=True,
        native_char_count=420,
        quality_score=0.05,
        force_ocr=False,
    ) is False

    assert extractor._should_use_ocr(
        has_text_layer=True,
        native_char_count=80,
        quality_score=0.6,
        force_ocr=False,
    ) is False


def test_force_ocr_and_skip_ocr_precedence():
    extractor = PageExtractor(skip_ocr=True, quality_threshold=0.3)
    extractor.settings.ocr_text_layer_fallback_enabled = True

    assert extractor._should_use_ocr(
        has_text_layer=True,
        native_char_count=10,
        quality_score=0.0,
        force_ocr=False,
    ) is False

    assert extractor._should_use_ocr(
        has_text_layer=True,
        native_char_count=10,
        quality_score=0.0,
        force_ocr=True,
    ) is True
