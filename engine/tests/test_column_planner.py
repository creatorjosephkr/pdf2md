"""Tests for 1-column / 2-column LayoutBand partitioning and adjacent 1-col merging."""

from __future__ import annotations

from pdf_convert_engine.ir.schema import (
    BBox,
    BlockType,
    FigureBlock,
    MarginBox,
    TextBlock,
    TextRun,
)
from pdf_convert_engine.parsers.column_planner import plan_page_bands


def _txt(bid: str, x0: float, y0: float, x1: float, y1: float, btype: BlockType = BlockType.PARAGRAPH, span: str = "auto") -> TextBlock:
    return TextBlock(
        id=bid,
        page_no=1,
        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
        block_type=btype,
        column_span=span,  # type: ignore[arg-type]
        runs=[TextRun(text=bid)],
        plain_text=bid,
    )


def test_1col_title_2col_body_1col_wide_fig_2col_body(tmp_path) -> None:
    img = tmp_path / "fig.png"
    img.write_bytes(b"png")

    blocks = [
        # Consecutive 1-col header blocks (should merge into a single 1-col band)
        _txt("title", 80, 50, 530, 80, BlockType.TITLE),
        _txt("authors", 140, 88, 470, 108, BlockType.PARAGRAPH, span="full"),
        _txt("abstract", 54, 120, 558, 175, BlockType.PARAGRAPH),
        # Upper 2-col body
        _txt("l1", 54, 190, 297, 290),
        _txt("r1", 315, 190, 558, 290),
        # Wide spanning figure + caption
        FigureBlock(
            id="wide_fig",
            page_no=1,
            bbox=BBox(x0=54, y0=310, x1=558, y1=430),
            image_path=str(img),
            image_width_pt=504,
            image_height_pt=120,
        ),
        _txt("wide_cap", 90, 435, 520, 452, BlockType.CAPTION),
        # Lower 2-col body
        _txt("l2", 54, 470, 297, 620),
        _txt("r2", 315, 470, 558, 620),
        # Marginalia
        _txt("hdr", 200, 15, 400, 28, BlockType.PAGE_HEADER),
        _txt("ftr", 200, 765, 400, 778, BlockType.PAGE_FOOTER),
    ]

    bands, headers, footers, footnotes = plan_page_bands(
        blocks,
        page_width=612.0,
        margins=MarginBox(top=54, bottom=54, left=54, right=54),
    )

    assert len(headers) == 1
    assert len(footers) == 1
    assert footnotes == []

    # Expected bands: [1-col (title+authors+abstract), 2-col (l1/r1), 1-col (wide_fig+wide_cap), 2-col (l2/r2)]
    assert [b.columns for b in bands] == [1, 2, 1, 2]
    assert [blk.id for blk in bands[0].blocks] == ["title", "authors", "abstract"]
    assert [blk.id for blk in bands[1].left_column_blocks] == ["l1"]
    assert [blk.id for blk in bands[1].right_column_blocks] == ["r1"]
    assert [blk.id for blk in bands[2].blocks] == ["wide_fig", "wide_cap"]
    assert bands[2].blocks[0].keep_with_next is True
    assert [blk.id for blk in bands[3].left_column_blocks] == ["l2"]
    assert [blk.id for blk in bands[3].right_column_blocks] == ["r2"]


def test_force_single_column_flattens_bands() -> None:
    blocks = [
        _txt("l1", 54, 190, 297, 290),
        _txt("r1", 315, 190, 558, 290),
    ]
    bands, _, _, _ = plan_page_bands(
        blocks,
        page_width=612.0,
        margins=MarginBox(top=54, bottom=54, left=54, right=54),
        force_single_column=True,
    )
    assert len(bands) == 1
    assert bands[0].columns == 1
    assert len(bands[0].blocks) == 2
