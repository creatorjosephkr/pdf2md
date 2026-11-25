"""Zero-ML heuristic fallback parser built on pdfplumber + pypdfium2."""

from __future__ import annotations

from pathlib import Path
from statistics import median

import pdfplumber

from pdf_convert_engine.ir.schema import (
    Alignment,
    BBox,
    BlockType,
    DocumentBlock,
    DocumentIR,
    FigureBlock,
    PageIR,
    PreflightReport,
    TableBlock,
    TableCellIR,
    TextBlock,
)
from pdf_convert_engine.parsers.base import ParseOptions, ParserAdapter
from pdf_convert_engine.parsers.cropper import PageCropper
from pdf_convert_engine.parsers.postprocess import finalize_page_ir
from pdf_convert_engine.parsers.typography import extract_styled_runs


def _cluster_words_into_blocks(
    words: list[dict],
    page_width: float,
    page_height: float,
) -> list[BBox]:
    """Group pdfplumber words into paragraph/heading bounding boxes respecting columns."""
    if not words:
        return []

    # First cluster words into lines (y-proximity + small horizontal gap or column separation)
    sizes = [max(4.0, float(w["bottom"]) - float(w["top"])) for w in words]
    med_h = median(sizes) if sizes else 10.0
    y_tol = max(2.5, med_h * 0.45)

    sorted_w = sorted(words, key=lambda w: ((float(w["top"]) + float(w["bottom"])) / 2.0, float(w["x0"])))
    raw_lines: list[list[dict]] = []
    cur: list[dict] = []
    cur_cy = 0.0

    for w in sorted_w:
        cy = (float(w["top"]) + float(w["bottom"])) / 2.0
        if not cur:
            cur = [w]
            cur_cy = cy
        elif abs(cy - cur_cy) <= y_tol:
            cur.append(w)
            cur_cy = sum((float(x["top"]) + float(x["bottom"])) / 2.0 for x in cur) / len(cur)
        else:
            raw_lines.append(sorted(cur, key=lambda x: float(x["x0"])))
            cur = [w]
            cur_cy = cy
    if cur:
        raw_lines.append(sorted(cur, key=lambda x: float(x["x0"])))

    # Split horizontal lines across large column gutters (> 22pt gap)
    line_boxes: list[BBox] = []
    gutter_gap = max(22.0, med_h * 2.0)
    for ln in raw_lines:
        seg: list[dict] = [ln[0]]
        for w in ln[1:]:
            prev_x1 = float(seg[-1]["x1"])
            if float(w["x0"]) - prev_x1 > gutter_gap:
                line_boxes.append(
                    BBox(
                        x0=min(float(x["x0"]) for x in seg),
                        y0=min(float(x["top"]) for x in seg),
                        x1=max(float(x["x1"]) for x in seg),
                        y1=max(float(x["bottom"]) for x in seg),
                    )
                )
                seg = [w]
            else:
                seg.append(w)
        if seg:
            line_boxes.append(
                BBox(
                    x0=min(float(x["x0"]) for x in seg),
                    y0=min(float(x["top"]) for x in seg),
                    x1=max(float(x["x1"]) for x in seg),
                    y1=max(float(x["bottom"]) for x in seg),
                )
            )

    # Merge vertically adjacent line_boxes sharing horizontal column overlap into paragraph blocks
    line_boxes.sort(key=lambda b: (b.y0, b.x0))
    blocks: list[BBox] = []
    used = [False] * len(line_boxes)

    for i, lb in enumerate(line_boxes):
        if used[i]:
            continue
        used[i] = True
        cur_box = lb
        lh = max(8.0, lb.height)

        changed = True
        while changed:
            changed = False
            for j, cand in enumerate(line_boxes):
                if used[j]:
                    continue
                v_gap = cand.y0 - cur_box.y1
                if -2.0 <= v_gap <= lh * 0.85:
                    h_overlap = min(cur_box.x1, cand.x1) - max(cur_box.x0, cand.x0)
                    min_w = max(1.0, min(cur_box.width, cand.width))
                    if h_overlap > 0.25 * min_w and abs(cur_box.height / max(1.0, cand.height) - 1.0) < 0.65:
                        cur_box = BBox(
                            x0=min(cur_box.x0, cand.x0),
                            y0=min(cur_box.y0, cand.y0),
                            x1=max(cur_box.x1, cand.x1),
                            y1=max(cur_box.y1, cand.y1),
                        )
                        used[j] = True
                        changed = True
        blocks.append(cur_box)

    return blocks


class FallbackHeuristicAdapter(ParserAdapter):
    """Lightweight deterministic parser using pdfplumber + pypdfium2 (no ML models required)."""

    name = "fallback"

    def parse(
        self,
        pdf_path: Path,
        preflight: PreflightReport,
        options: ParseOptions,
    ) -> DocumentIR:
        assets_dir = options.assets_dir or (pdf_path.parent / f".{pdf_path.stem}_assets")
        assets_dir.mkdir(parents=True, exist_ok=True)

        pages: list[PageIR] = []

        with pdfplumber.open(pdf_path) as pdf, PageCropper(pdf_path) as cropper:
            total = len(pdf.pages)
            start_idx = max(0, (options.page_range[0] - 1) if options.page_range else 0)
            end_idx = min(total, options.page_range[1] if options.page_range else total)

            for page_no in range(start_idx + 1, end_idx + 1):
                p_page = pdf.pages[page_no - 1]
                pw = float(p_page.width)
                ph = float(p_page.height)
                margins = preflight.estimated_margins_pt
                blocks: list[DocumentBlock] = []
                masked_bboxes: list[BBox] = []
                excluded_callout_bboxes: list[BBox] = []

                # 1. Tables via pdfplumber
                tables = p_page.find_tables() or []
                for t_idx, tbl in enumerate(tables):
                    tx0, ty0, tx1, ty1 = tbl.bbox
                    tbox = BBox(x0=float(tx0), y0=float(ty0), x1=float(tx1), y1=float(ty1))
                    masked_bboxes.append(tbox)
                    excluded_callout_bboxes.append(tbox)
                    extracted = tbl.extract() or []
                    if not extracted:
                        continue
                    num_rows = len(extracted)
                    num_cols = max((len(r) for r in extracted), default=1)
                    col_w = round(tbox.width / max(1, num_cols), 2)
                    cells: list[TableCellIR] = []
                    for r_i, row in enumerate(extracted):
                        for c_i in range(num_cols):
                            cell_text = (row[c_i] or "").strip() if c_i < len(row) else ""
                            cells.append(
                                TableCellIR(
                                    row=r_i,
                                    col=c_i,
                                    text=cell_text,
                                    is_header=(r_i == 0),
                                    alignment=Alignment.LEFT,
                                )
                            )
                    blocks.append(
                        TableBlock(
                            id=f"p{page_no}_tbl_{t_idx}",
                            page_no=page_no,
                            bbox=tbox,
                            num_rows=num_rows,
                            num_cols=num_cols,
                            col_widths_pt=[col_w] * num_cols,
                            cells=cells,
                            style_hint="booktabs",
                        )
                    )

                # 2. Embedded raster images -> FigureBlock
                for f_idx, im in enumerate(p_page.images or []):
                    fbox = BBox(
                        x0=float(im["x0"]),
                        y0=float(im["top"]),
                        x1=float(im["x1"]),
                        y1=float(im["bottom"]),
                    )
                    if fbox.width < 24.0 or fbox.height < 24.0:
                        continue
                    masked_bboxes.append(fbox)
                    excluded_callout_bboxes.append(fbox)
                    img_out = assets_dir / f"p{page_no}_fig_{f_idx}.png"
                    w_pt, h_pt = cropper.crop_bbox(
                        page_no, fbox, img_out, dpi=options.crop_dpi, pad_pt=1.0
                    )
                    blocks.append(
                        FigureBlock(
                            id=f"p{page_no}_fig_{f_idx}",
                            page_no=page_no,
                            bbox=fbox,
                            image_path=str(img_out),
                            image_width_pt=w_pt,
                            image_height_pt=h_pt,
                        )
                    )

                # 3. Remaining words outside tables/figures -> TextBlocks
                all_words = p_page.extract_words(keep_blank_chars=False, use_text_flow=False) or []
                free_words = []
                for w in all_words:
                    wbox = BBox(
                        x0=float(w["x0"]),
                        y0=float(w["top"]),
                        x1=float(w["x1"]),
                        y1=float(w["bottom"]),
                    )
                    if any(wbox.intersection_ratio(mb) > 0.45 for mb in masked_bboxes):
                        continue
                    free_words.append(w)

                text_boxes = _cluster_words_into_blocks(free_words, pw, ph)
                body_sizes = [float(c.get("size", 10.0) or 10.0) for c in (p_page.chars or [])]
                med_font = median(body_sizes) if body_sizes else 10.0

                for b_idx, tbox in enumerate(text_boxes):
                    runs, align = extract_styled_runs(p_page, tbox)
                    plain = "".join(r.text for r in runs).strip()
                    if not plain:
                        continue
                    avg_size = median([r.font_size_pt for r in runs]) if runs else med_font
                    all_bold = all(r.bold for r in runs if r.text.strip())
                    all_code = all(r.is_code for r in runs if r.text.strip())

                    btype = BlockType.PARAGRAPH
                    h_level = None
                    if page_no == 1 and b_idx == 0 and avg_size >= med_font * 1.35:
                        btype = BlockType.TITLE
                    elif tbox.y0 < ph * 0.06 and avg_size <= med_font * 0.9:
                        btype = BlockType.PAGE_HEADER
                    elif tbox.y1 > ph * 0.94 and avg_size <= med_font * 0.9:
                        btype = BlockType.PAGE_FOOTER
                    elif all_code:
                        btype = BlockType.CODE_BLOCK
                        runs, align = extract_styled_runs(p_page, tbox, preserve_line_breaks=True)
                    elif (avg_size >= med_font * 1.12 or all_bold) and len(plain) < 120:
                        btype = BlockType.HEADING
                        h_level = 1 if avg_size >= med_font * 1.25 else 2
                    elif plain.lower().startswith(("figure ", "fig.", "table ", "표 ", "그림 ")):
                        btype = BlockType.CAPTION

                    blocks.append(
                        TextBlock(
                            id=f"p{page_no}_txt_{b_idx}",
                            page_no=page_no,
                            bbox=tbox,
                            block_type=btype,
                            runs=runs,
                            plain_text=plain,
                            alignment=align,
                            heading_level=h_level,
                            keep_with_next=(btype == BlockType.HEADING),
                        )
                    )

                pages.append(
                    finalize_page_ir(
                        page_no=page_no,
                        width_pt=pw,
                        height_pt=ph,
                        margins=margins,
                        blocks=blocks,
                        plumber_page=p_page,
                        excluded_callout_bboxes=excluded_callout_bboxes,
                        is_scanned=(preflight.scanned_pages > 0 and len(p_page.chars or []) < 25),
                        has_broken_unicode=(page_no in preflight.broken_cmap_pages),
                    )
                )

        return DocumentIR(
            source_path=str(pdf_path.resolve()),
            parser_name=self.name,
            preflight=preflight,
            pages=pages,
            assets_dir=str(assets_dir),
        )
