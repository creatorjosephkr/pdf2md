"""Post-pass helper shared by parser adapters to group callout boxes and plan layout bands."""

from __future__ import annotations

from typing import Any

from pdf_convert_engine.ir.schema import (
    BBox,
    BlockType,
    CalloutBoxBlock,
    DocumentBlock,
    MarginBox,
    PageIR,
    TextBlock,
)
from pdf_convert_engine.parsers.column_planner import plan_page_bands
from pdf_convert_engine.parsers.typography import detect_callout_rects


def _group_callout_blocks(
    page_no: int,
    blocks: list[DocumentBlock],
    plumber_page: Any,
    excluded_bboxes: list[BBox],
) -> list[DocumentBlock]:
    """Wrap TextBlocks falling inside colored/bordered callout rectangles into CalloutBoxBlock."""
    rects = detect_callout_rects(plumber_page, excluded_bboxes=excluded_bboxes)
    if not rects:
        return blocks

    consumed_ids: set[str] = set()
    callout_blocks: list[CalloutBoxBlock] = []

    for r_idx, rect_info in enumerate(rects):
        rbox: BBox = rect_info["bbox"]
        inner: list[TextBlock] = []
        for blk in blocks:
            if blk.id in consumed_ids:
                continue
            if isinstance(blk, TextBlock) and blk.block_type not in (
                BlockType.PAGE_HEADER,
                BlockType.PAGE_FOOTER,
            ):
                if rbox.contains(blk.bbox, tol=5.0) or blk.bbox.intersection_ratio(rbox) > 0.75:
                    inner.append(blk)

        if inner:
            inner.sort(key=lambda b: (b.bbox.y0, b.bbox.x0))
            for ib in inner:
                consumed_ids.add(ib.id)
            title = inner[0].plain_text if inner[0].block_type == BlockType.HEADING else None
            callout_blocks.append(
                CalloutBoxBlock(
                    id=f"p{page_no}_callout_{r_idx}",
                    page_no=page_no,
                    bbox=rbox,
                    title=title,
                    blocks=inner,
                    fill_hex=rect_info["fill_hex"],
                    border_hex=rect_info["border_hex"],
                    border_width_pt=rect_info["border_width_pt"],
                    accent_left_only=rect_info["accent_left_only"],
                    source=inner[0].source,
                )
            )

    remaining = [b for b in blocks if b.id not in consumed_ids]
    remaining.extend(callout_blocks)
    return remaining


def finalize_page_ir(
    page_no: int,
    width_pt: float,
    height_pt: float,
    margins: MarginBox,
    blocks: list[DocumentBlock],
    plumber_page: Any,
    excluded_callout_bboxes: list[BBox],
    is_scanned: bool = False,
    has_broken_unicode: bool = False,
    force_single_column: bool = False,
) -> PageIR:
    """Group callouts, separate marginalia, and plan 1-col / 2-col layout bands for a page."""
    grouped = _group_callout_blocks(page_no, blocks, plumber_page, excluded_callout_bboxes)
    bands, headers, footers, footnotes = plan_page_bands(
        grouped,
        page_width=width_pt,
        margins=margins,
        force_single_column=force_single_column,
    )
    return PageIR(
        page_no=page_no,
        width_pt=round(width_pt, 2),
        height_pt=round(height_pt, 2),
        margins=margins,
        is_scanned=is_scanned,
        has_broken_unicode=has_broken_unicode,
        bands=bands,
        headers=headers,
        footers=footers,
        footnotes=footnotes,
    )
