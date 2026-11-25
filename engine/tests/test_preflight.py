"""Tests for Preflight Analyzer (columns, language, broken CMap, fonts, margins)."""

from __future__ import annotations

from pathlib import Path

from fixtures_generator import (
    generate_academic_2col_en,
    generate_korean_academic,
    generate_textbook_math_callout,
)
from pdf_convert_engine.preflight import (
    analyze_pdf,
    detect_broken_unicode_text,
    detect_language_from_text,
)


def test_preflight_2col_english_paper(tmp_path: Path) -> None:
    pdf = generate_academic_2col_en(tmp_path / "academic_2col_en.pdf")
    report = analyze_pdf(pdf)

    assert report.page_count == 2
    assert report.digital_pages == 2
    assert report.scanned_pages == 0
    assert report.broken_cmap_pages == []
    assert report.detected_columns == 2
    assert report.detected_language == "en"
    assert report.recommended_ocr is False
    assert len(report.fonts_found) >= 2
    assert 30.0 <= report.estimated_margins_pt.left <= 80.0


def test_preflight_1col_textbook(tmp_path: Path) -> None:
    pdf = generate_textbook_math_callout(tmp_path / "textbook.pdf")
    report = analyze_pdf(pdf)

    assert report.page_count == 2
    assert report.digital_pages == 2
    assert report.detected_columns == 1
    assert report.detected_language == "en"
    assert report.recommended_ocr is False


def test_preflight_korean_academic(tmp_path: Path) -> None:
    pdf = generate_korean_academic(tmp_path / "korean_academic.pdf")
    report = analyze_pdf(pdf)

    assert report.page_count == 2
    assert report.digital_pages == 2
    assert report.detected_language in ("ko", "mixed")
    assert report.broken_cmap_pages == []


def test_broken_unicode_and_language_heuristics() -> None:
    assert detect_broken_unicode_text("(cid:12)(cid:45)(cid:88) broken") is True
    assert detect_broken_unicode_text("\ue001\ue002\ue003\ue004\ue005 test") is True
    assert detect_broken_unicode_text("정상적인 한국어 학술 논문 문장입니다.") is False

    assert detect_language_from_text("학술 문서 변환 엔진 설계") == "ko"
    assert detect_language_from_text("Academic PDF layout reconstruction") == "en"
    assert detect_language_from_text("학술 논문 Abstract 및 Continuous Section Break 기법") == "mixed"
