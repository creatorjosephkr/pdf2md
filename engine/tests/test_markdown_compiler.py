"""Tests for Academic MarkdownCompiler (2-col order, LaTeX math, HTML/GFM tables, callouts, images)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from pdf_convert_engine.compiler import MarkdownCompiler, MarkdownOptions
from pdf_convert_engine.ir.schema import (
    Alignment,
    BBox,
    BlockType,
    CalloutBoxBlock,
    DocumentIR,
    FigureBlock,
    FormulaBlock,
    LayoutBand,
    MarginBox,
    PageIR,
    PreflightReport,
    TableBlock,
    TableCellIR,
    TextBlock,
    TextRun,
)


def _build_ir(tmp_path: Path) -> DocumentIR:
    fig_png = tmp_path / "p1_fig_0.png"
    Image.new("RGB", (240, 100), color=(37, 99, 235)).save(fig_png, format="PNG")

    title = TextBlock(
        id="title",
        page_no=1,
        bbox=BBox(x0=54, y0=40, x1=558, y1=70),
        block_type=BlockType.TITLE,
        plain_text="Academic Markdown Synthesis",
        runs=[TextRun(text="Academic Markdown Synthesis", bold=True)],
    )
    left_p = TextBlock(
        id="l1",
        page_no=1,
        bbox=BBox(x0=54, y0=90, x1=297, y1=140),
        block_type=BlockType.PARAGRAPH,
        plain_text="Left column x2 bold text.",
        runs=[
            TextRun(text="Left column x"),
            TextRun(text="2", superscript=True),
            TextRun(text=" "),
            TextRun(text="bold", bold=True),
            TextRun(text=" text."),
        ],
    )
    right_p = TextBlock(
        id="r1",
        page_no=1,
        bbox=BBox(x0=315, y0=90, x1=558, y1=140),
        block_type=BlockType.PARAGRAPH,
        plain_text="Right column follows left.",
        runs=[TextRun(text="Right column follows "), TextRun(text="left.", italic=True)],
    )
    eq = FormulaBlock(
        id="eq1",
        page_no=1,
        bbox=BBox(x0=54, y0=160, x1=297, y1=200),
        latex=r"L(w) = \sum_i \|f(x_i) - y_i\|^2 \quad (1)",
        equation_number="(1)",
    )
    fig = FigureBlock(
        id="fig1",
        page_no=1,
        bbox=BBox(x0=54, y0=220, x1=558, y1=320),
        image_path=str(fig_png),
        image_width_pt=400,
        image_height_pt=120,
        caption_text="Figure 1: Benchmark Overview",
    )
    simple_tbl = TableBlock(
        id="t_simple",
        page_no=1,
        bbox=BBox(x0=54, y0=340, x1=558, y1=400),
        num_rows=2,
        num_cols=2,
        cells=[
            TableCellIR(row=0, col=0, text="Model", is_header=True),
            TableCellIR(row=0, col=1, text="Score", is_header=True),
            TableCellIR(row=1, col=0, text="Ours"),
            TableCellIR(row=1, col=1, text="97.5%"),
        ],
    )
    merged_tbl = TableBlock(
        id="t_merged",
        page_no=1,
        bbox=BBox(x0=54, y0=420, x1=558, y1=500),
        num_rows=3,
        num_cols=3,
        cells=[
            TableCellIR(row=0, col=0, row_span=2, col_span=1, text="Method", is_header=True),
            TableCellIR(row=0, col=1, row_span=1, col_span=2, text="Metrics", is_header=True),
            TableCellIR(row=1, col=1, text="SSIM", is_header=True),
            TableCellIR(row=1, col=2, text="Match", is_header=True),
            TableCellIR(row=2, col=0, text="Docling"),
            TableCellIR(row=2, col=1, text="96%"),
            TableCellIR(row=2, col=2, text="100%"),
        ],
    )
    callout = CalloutBoxBlock(
        id="c1",
        page_no=1,
        bbox=BBox(x0=54, y0=520, x1=558, y1=580),
        title="Theorem 2.2",
        blocks=[
            TextBlock(
                id="c1_h",
                page_no=1,
                bbox=BBox(x0=60, y0=525, x1=540, y1=540),
                block_type=BlockType.HEADING,
                plain_text="Theorem 2.2",
            ),
            TextBlock(
                id="c1_b",
                page_no=1,
                bbox=BBox(x0=60, y0=545, x1=540, y1=570),
                block_type=BlockType.PARAGRAPH,
                plain_text="Every local minimum is global.",
            ),
        ],
    )
    code = TextBlock(
        id="code1",
        page_no=1,
        bbox=BBox(x0=54, y0=600, x1=558, y1=650),
        block_type=BlockType.CODE_BLOCK,
        plain_text="def solve(x):\n    return x * 2",
    )

    page = PageIR(
        page_no=1,
        width_pt=612.0,
        height_pt=792.0,
        margins=MarginBox(),
        bands=[
            LayoutBand(columns=1, blocks=[title]),
            LayoutBand(
                columns=2,
                blocks=[left_p, eq, right_p],
                left_column_blocks=[left_p, eq],
                right_column_blocks=[right_p],
            ),
            LayoutBand(columns=1, blocks=[fig, simple_tbl, merged_tbl, callout, code]),
        ],
    )

    return DocumentIR(
        source_path="paper.pdf",
        parser_name="synthetic",
        preflight=PreflightReport(file_path="paper.pdf", page_count=1, detected_columns=2),
        pages=[page],
    )


def test_markdown_compiler_folder_mode(tmp_path: Path) -> None:
    ir = _build_ir(tmp_path)
    out_md = tmp_path / "out" / "paper.md"
    res = MarkdownCompiler().compile(ir, out_md, MarkdownOptions(image_mode="folder"))

    assert out_md.exists()
    assert res.assets_copied == 1
    assert (tmp_path / "out" / "paper_assets" / "p1_fig_0.png").exists()

    md = res.markdown_text
    assert 'title: "Academic Markdown Synthesis"' in md
    assert "# Academic Markdown Synthesis" in md
    # Left column must precede right column
    assert md.index("Left column x<sup>2</sup> **bold** text.") < md.index("Right column follows *left.*")
    # Equation tag normalized without duplicate (1)
    assert r"L(w) = \sum_i \|f(x_i) - y_i\|^2 \tag{1}" in md
    assert "![Figure 1: Benchmark Overview](./paper_assets/p1_fig_0.png)" in md
    # Simple GFM pipe table + merged HTML table
    assert "| Model | Score |" in md
    assert '<th colspan="2">Metrics</th>' in md
    assert '<th rowspan="2">Method</th>' in md
    # Callout & Code block
    assert "> [!IMPORTANT]\n> **Theorem 2.2**" in md
    assert "```python\ndef solve(x):" in md


def test_markdown_compiler_base64_mode(tmp_path: Path) -> None:
    ir = _build_ir(tmp_path)
    res = MarkdownCompiler().compile(ir, output_path=None, options=MarkdownOptions(image_mode="base64"))
    assert "![Figure 1: Benchmark Overview](data:image/png;base64," in res.markdown_text
