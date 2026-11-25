"""Layout band and continuous-section column planner for Google Docs."""

from __future__ import annotations

from pdf_convert_engine.ir.schema import (
    BlockType,
    DocumentBlock,
    FigureBlock,
    LayoutBand,
    MarginBox,
    TextBlock,
)


def _classify_block_span(
    block: DocumentBlock,
    mid_x: float,
    content_w: float,
) -> str:
    if block.column_span == "full":
        return "FULL"
    if block.column_span == "single":
        return "LEFT" if block.bbox.center_x < mid_x else "RIGHT"

    if block.block_type == BlockType.TITLE:
        return "FULL"

    crosses_gutter = block.bbox.x0 < (mid_x - 10.0) and block.bbox.x1 > (mid_x + 10.0)
    is_wide = block.bbox.width > content_w * 0.56
    if crosses_gutter or is_wide:
        return "FULL"

    return "LEFT" if block.bbox.center_x < mid_x else "RIGHT"


def _bind_figure_captions(blocks: list[DocumentBlock]) -> None:
    """Attach adjacent caption metadata and set keep_with_next on figures."""
    for idx, blk in enumerate(blocks):
        if isinstance(blk, FigureBlock) and idx + 1 < len(blocks):
            nxt = blocks[idx + 1]
            if isinstance(nxt, TextBlock) and nxt.block_type == BlockType.CAPTION:
                blk.keep_with_next = True
                if not blk.caption_text:
                    blk.caption_text = nxt.plain_text


def plan_page_bands(
    blocks: list[DocumentBlock],
    page_width: float,
    margins: MarginBox,
    force_single_column: bool = False,
) -> tuple[list[LayoutBand], list[TextBlock], list[TextBlock], list[TextBlock]]:
    """Partition page blocks into contiguous 1-col / 2-col LayoutBands and marginalia."""
    headers: list[TextBlock] = []
    footers: list[TextBlock] = []
    footnotes: list[TextBlock] = []
    flow_blocks: list[DocumentBlock] = []

    for blk in blocks:
        if isinstance(blk, TextBlock) and blk.block_type == BlockType.PAGE_HEADER:
            headers.append(blk)
        elif isinstance(blk, TextBlock) and blk.block_type == BlockType.PAGE_FOOTER:
            footers.append(blk)
        elif isinstance(blk, TextBlock) and blk.block_type == BlockType.FOOTNOTE:
            footnotes.append(blk)
        else:
            flow_blocks.append(blk)

    headers.sort(key=lambda b: b.bbox.y0)
    footers.sort(key=lambda b: b.bbox.y0)
    footnotes.sort(key=lambda b: b.bbox.y0)

    if not flow_blocks:
        return [], headers, footers, footnotes

    if force_single_column:
        ordered = sorted(flow_blocks, key=lambda b: (b.bbox.y0, b.bbox.x0))
        _bind_figure_captions(ordered)
        return [LayoutBand(columns=1, blocks=ordered)], headers, footers, footnotes

    content_w = max(100.0, page_width - margins.left - margins.right)
    mid_x = margins.left + content_w / 2.0

    tagged: list[tuple[str, DocumentBlock]] = [
        (_classify_block_span(b, mid_x, content_w), b)
        for b in flow_blocks
    ]

    left_candidates = [b for role, b in tagged if role == "LEFT"]
    right_candidates = [b for role, b in tagged if role == "RIGHT"]

    # Check if there is genuine vertical overlap between left and right columns
    has_two_col = False
    if len(left_candidates) >= 1 and len(right_candidates) >= 1:
        overlap_pairs = 0
        for lb in left_candidates:
            for rb in right_candidates:
                v_overlap = min(lb.bbox.y1, rb.bbox.y1) - max(lb.bbox.y0, rb.bbox.y0)
                if v_overlap > 10.0:
                    overlap_pairs += 1
        if overlap_pairs >= 1 and (len(left_candidates) + len(right_candidates)) >= 2:
            has_two_col = True

    if not has_two_col:
        ordered = sorted(flow_blocks, key=lambda b: (b.bbox.y0, b.bbox.x0))
        _bind_figure_captions(ordered)
        return [LayoutBand(columns=1, blocks=ordered)], headers, footers, footnotes

    # Estimate column gutter
    max_left_x1 = max(b.bbox.x1 for b in left_candidates)
    min_right_x0 = min(b.bbox.x0 for b in right_candidates)
    gutter_pt = max(12.0, min(36.0, round(min_right_x0 - max_left_x1, 1)))

    # Partition vertical timeline using FULL blocks as split boundaries
    full_blocks = sorted([b for role, b in tagged if role == "FULL"], key=lambda b: (b.bbox.y0, b.bbox.x0))
    side_blocks = [(role, b) for role, b in tagged if role in ("LEFT", "RIGHT")]

    raw_bands: list[LayoutBand] = []
    prev_y = float("-inf")

    def emit_interval(y_start: float, y_end: float) -> None:
        lefts = sorted(
            [b for r, b in side_blocks if r == "LEFT" and y_start <= b.bbox.center_y < y_end],
            key=lambda b: b.bbox.y0,
        )
        rights = sorted(
            [b for r, b in side_blocks if r == "RIGHT" and y_start <= b.bbox.center_y < y_end],
            key=lambda b: b.bbox.y0,
        )
        if not lefts and not rights:
            return
        if lefts and rights:
            _bind_figure_captions(lefts)
            _bind_figure_captions(rights)
            raw_bands.append(
                LayoutBand(
                    columns=2,
                    gutter_pt=gutter_pt,
                    blocks=lefts + rights,
                    left_column_blocks=lefts,
                    right_column_blocks=rights,
                )
            )
        else:
            only = lefts if lefts else rights
            _bind_figure_captions(only)
            if lefts and not rights and all(b.bbox.width < content_w * 0.54 for b in lefts):
                raw_bands.append(
                    LayoutBand(
                        columns=2,
                        gutter_pt=gutter_pt,
                        blocks=lefts,
                        left_column_blocks=lefts,
                        right_column_blocks=[],
                    )
                )
            else:
                raw_bands.append(LayoutBand(columns=1, blocks=only))

    for fb in full_blocks:
        emit_interval(prev_y, fb.bbox.center_y)
        raw_bands.append(LayoutBand(columns=1, blocks=[fb]))
        prev_y = fb.bbox.center_y

    emit_interval(prev_y, float("inf"))

    # Merge adjacent 1-column bands (e.g., Title + Authors + Abstract)
    merged_bands: list[LayoutBand] = []
    for band in raw_bands:
        if merged_bands and band.columns == 1 and merged_bands[-1].columns == 1:
            merged_bands[-1].blocks.extend(band.blocks)
            merged_bands[-1].blocks.sort(key=lambda b: (b.bbox.y0, b.bbox.x0))
            _bind_figure_captions(merged_bands[-1].blocks)
        else:
            merged_bands.append(band)

    return merged_bands, headers, footers, footnotes
