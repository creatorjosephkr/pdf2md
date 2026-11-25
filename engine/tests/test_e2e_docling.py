"""End-to-end integration tests with FallbackHeuristicAdapter and DoclingAdapter -> Markdown."""

from __future__ import annotations

from pathlib import Path

from fixtures_generator import (
    generate_academic_2col_en,
    generate_korean_academic,
    generate_textbook_math_callout,
)
from pdf_convert_engine.compiler import MarkdownCompiler, MarkdownOptions
from pdf_convert_engine.parsers import DoclingAdapter, FallbackHeuristicAdapter, ParseOptions
from pdf_convert_engine.preflight import analyze_pdf


def test_fallback_adapter_markdown_e2e(tmp_path: Path) -> None:
    pdf = generate_academic_2col_en(tmp_path / "academic_2col_en.pdf")
    preflight = analyze_pdf(pdf)
    ir = FallbackHeuristicAdapter().parse(
        pdf,
        preflight,
        ParseOptions(assets_dir=tmp_path / "assets_fb"),
    )
    assert len(ir.pages) == 2

    out_md = tmp_path / "academic_fb.md"
    res = MarkdownCompiler().compile(ir, out_md, MarkdownOptions(image_mode="folder"))
    assert out_md.exists()
    assert "High-Fidelity Layout Reconstruction" in res.markdown_text
    assert res.headings >= 1


def test_docling_e2e_academic_2col_en_markdown(tmp_path: Path) -> None:
    pdf = generate_academic_2col_en(tmp_path / "academic_2col_en.pdf")
    preflight = analyze_pdf(pdf)
    ir = DoclingAdapter().parse(
        pdf,
        preflight,
        ParseOptions(assets_dir=tmp_path / "assets_2col"),
    )
    assert len(ir.pages) == 2

    band_cols = [band.columns for page in ir.pages for band in page.bands]
    assert 1 in band_cols
    assert 2 in band_cols

    out_md = tmp_path / "academic_2col_en.md"
    res = MarkdownCompiler().compile(ir, out_md, MarkdownOptions(image_mode="folder"))
    assert out_md.exists()
    assert res.tables >= 1
    assert res.figures >= 1
    assert res.formulas >= 1
    assert res.assets_copied >= 1
    assert r"\tag{1}" in res.markdown_text
    assert "<table>" in res.markdown_text


def test_docling_e2e_textbook_math_callout_markdown(tmp_path: Path) -> None:
    pdf = generate_textbook_math_callout(tmp_path / "textbook_math_callout.pdf")
    preflight = analyze_pdf(pdf)
    ir = DoclingAdapter().parse(
        pdf,
        preflight,
        ParseOptions(assets_dir=tmp_path / "assets_tb"),
    )
    assert len(ir.pages) == 2

    out_md = tmp_path / "textbook_math_callout.md"
    res = MarkdownCompiler().compile(ir, out_md)
    assert out_md.exists()
    assert res.callouts >= 1
    assert "> [!" in res.markdown_text


def test_docling_e2e_korean_academic_markdown(tmp_path: Path) -> None:
    pdf = generate_korean_academic(tmp_path / "korean_academic.pdf")
    preflight = analyze_pdf(pdf)
    ir = DoclingAdapter().parse(
        pdf,
        preflight,
        ParseOptions(assets_dir=tmp_path / "assets_ko"),
    )
    assert len(ir.pages) == 2

    out_md = tmp_path / "korean_academic.md"
    res = MarkdownCompiler().compile(ir, out_md)
    assert out_md.exists()
    assert res.tables >= 1
    assert "학술 문서 PDF" in res.markdown_text
