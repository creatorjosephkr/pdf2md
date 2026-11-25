"""Docling AI + pdfplumber typography + pypdfium2 cropper hybrid parser adapter."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pdfplumber
from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import (
    CodeItem,
    CoordOrigin,
    DocItemLabel,
    FormulaItem,
    ListItem,
    PictureItem,
    SectionHeaderItem,
    TableItem,
    TextItem,
    TitleItem,
)

from pdf_convert_engine.ir.schema import (
    Alignment,
    BBox,
    BlockType,
    DocumentBlock,
    DocumentIR,
    FigureBlock,
    FormulaBlock,
    PageIR,
    PreflightReport,
    TableBlock,
    TableCellIR,
    TextBlock,
    TextRun,
)
from pdf_convert_engine.parsers.base import ParseOptions, ParserAdapter
from pdf_convert_engine.parsers.cropper import PDFIUM_LOCK, PageCropper
from pdf_convert_engine.parsers.postprocess import finalize_page_ir
from pdf_convert_engine.parsers.typography import detect_equation_number, extract_styled_runs

logger = logging.getLogger(__name__)

_LABEL_TO_BLOCK_TYPE: dict[DocItemLabel, BlockType] = {
    DocItemLabel.TITLE: BlockType.TITLE,
    DocItemLabel.SECTION_HEADER: BlockType.HEADING,
    DocItemLabel.TEXT: BlockType.PARAGRAPH,
    DocItemLabel.PARAGRAPH: BlockType.PARAGRAPH,
    DocItemLabel.REFERENCE: BlockType.PARAGRAPH,
    DocItemLabel.CAPTION: BlockType.CAPTION,
    DocItemLabel.LIST_ITEM: BlockType.LIST_ITEM,
    DocItemLabel.CODE: BlockType.CODE_BLOCK,
    DocItemLabel.FOOTNOTE: BlockType.FOOTNOTE,
    DocItemLabel.PAGE_HEADER: BlockType.PAGE_HEADER,
    DocItemLabel.PAGE_FOOTER: BlockType.PAGE_FOOTER,
}


def _to_ir_bbox(bbox: Any, page_height: float) -> BBox:
    if bbox.coord_origin != CoordOrigin.TOPLEFT:
        bbox = bbox.to_top_left_origin(page_height)
    return BBox(x0=float(bbox.l), y0=float(bbox.t), x1=float(bbox.r), y1=float(bbox.b))


def _detect_table_style(p_page: Any, tbox: BBox) -> str:
    """Distinguish clean academic booktabs (horizontal-only rules) from full grids."""
    vertical_interior = 0
    for line in p_page.lines or []:
        x0, x1 = float(line["x0"]), float(line["x1"])
        y0, y1 = float(line["top"]), float(line["bottom"])
        if abs(x1 - x0) <= 2.5 and abs(y1 - y0) > 12.0:
            if tbox.x0 + 6.0 < x0 < tbox.x1 - 6.0 and tbox.y0 - 4.0 <= y0 and y1 <= tbox.y1 + 4.0:
                vertical_interior += 1
    return "grid" if vertical_interior >= 1 else "booktabs"


def _compute_col_widths(
    table_cells: list[Any],
    num_cols: int,
    table_bbox: BBox,
    page_height: float,
) -> list[float]:
    col_samples: dict[int, list[float]] = {i: [] for i in range(num_cols)}
    for cell in table_cells:
        if cell.col_span == 1 and cell.bbox is not None:
            cbox = _to_ir_bbox(cell.bbox, page_height)
            if cbox.width > 4.0 and 0 <= cell.start_col_offset_idx < num_cols:
                col_samples[cell.start_col_offset_idx].append(cbox.width)

    total_w = max(40.0, table_bbox.width)
    raw_widths: list[float | None] = [
        (sum(col_samples[c]) / len(col_samples[c])) if col_samples[c] else None
        for c in range(num_cols)
    ]
    known = [w for w in raw_widths if w is not None]
    missing_count = sum(1 for w in raw_widths if w is None)

    if missing_count == 0 and sum(known) > 0:
        scale = total_w / sum(known)
        return [round(max(18.0, w * scale), 2) for w in raw_widths if w is not None]

    remaining = max(18.0 * missing_count, total_w - sum(known))
    fallback = remaining / max(1, missing_count) if missing_count else total_w / max(1, num_cols)
    widths = [w if w is not None else fallback for w in raw_widths]
    w_sum = sum(widths) or total_w
    scale = total_w / w_sum
    return [round(max(18.0, w * scale), 2) for w in widths]


def _column_container_bbox(
    item_bbox: BBox,
    page_width: float,
    margins_left: float,
    margins_right: float,
    detected_columns: int,
) -> BBox:
    content_x0 = margins_left
    content_x1 = page_width - margins_right
    mid_x = (content_x0 + content_x1) / 2.0
    if detected_columns == 2 and item_bbox.width < (content_x1 - content_x0) * 0.56:
        if item_bbox.center_x < mid_x:
            return BBox(x0=content_x0, y0=item_bbox.y0, x1=mid_x - 6.0, y1=item_bbox.y1)
        return BBox(x0=mid_x + 6.0, y0=item_bbox.y0, x1=content_x1, y1=item_bbox.y1)
    return BBox(x0=content_x0, y0=item_bbox.y0, x1=content_x1, y1=item_bbox.y1)


class DoclingAdapter(ParserAdapter):
    """Primary AI layout/table/formula parser using IBM Docling (MIT)."""

    name = "docling"

    def _build_converter(self, use_ocr: bool, enable_formula_enrichment: bool) -> DocumentConverter:
        pipeline_options = PdfPipelineOptions(
            do_ocr=use_ocr,
            do_table_structure=True,
            do_formula_enrichment=enable_formula_enrichment,
            generate_page_images=False,
            generate_picture_images=False,
            accelerator_options=AcceleratorOptions(device=AcceleratorDevice.AUTO),
        )
        if use_ocr:
            pipeline_options.ocr_options = RapidOcrOptions()

        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )

    def parse(
        self,
        pdf_path: Path,
        preflight: PreflightReport,
        options: ParseOptions,
    ) -> DocumentIR:
        assets_dir = options.assets_dir or (pdf_path.parent / f".{pdf_path.stem}_assets")
        assets_dir.mkdir(parents=True, exist_ok=True)

        use_ocr = bool(options.force_ocr or preflight.recommended_ocr)
        converter = self._build_converter(
            use_ocr=use_ocr,
            enable_formula_enrichment=options.enable_formula_enrichment,
        )

        convert_kwargs: dict[str, Any] = {}
        if options.page_range is not None:
            convert_kwargs["page_range"] = options.page_range

        with PDFIUM_LOCK:
            result = converter.convert(pdf_path, **convert_kwargs)
        dl_doc = result.document

        # Group Docling items by page number with canonical TOPLEFT bboxes
        items_by_page: dict[int, list[tuple[Any, BBox]]] = {}
        for item, _level in dl_doc.iterate_items():
            provs = getattr(item, "prov", None)
            if not provs:
                continue
            prov = provs[0]
            page_no = int(prov.page_no)
            page_meta = dl_doc.pages.get(page_no)
            page_height = float(page_meta.size.height) if page_meta is not None else (
                preflight.page_sizes_pt[page_no - 1][1]
                if 1 <= page_no <= len(preflight.page_sizes_pt)
                else 792.0
            )
            ir_bbox = _to_ir_bbox(prov.bbox, page_height)
            items_by_page.setdefault(page_no, []).append((item, ir_bbox))

        pages: list[PageIR] = []
        margins = preflight.estimated_margins_pt

        with pdfplumber.open(pdf_path) as pdf, PageCropper(pdf_path) as cropper:
            total = len(pdf.pages)
            start_page = options.page_range[0] if options.page_range else 1
            end_page = min(total, options.page_range[1]) if options.page_range else total

            for page_no in range(start_page, end_page + 1):
                p_page = pdf.pages[page_no - 1]
                pw = float(p_page.width)
                ph = float(p_page.height)
                page_items = items_by_page.get(page_no, [])

                # Mask-First pass: identify Figures, Tables, and Formulas so inner text never leaks
                masked_bboxes: list[BBox] = []
                excluded_callout_bboxes: list[BBox] = []
                for item, bbox in page_items:
                    label = getattr(item, "label", None)
                    if isinstance(item, PictureItem) or label in (DocItemLabel.PICTURE, DocItemLabel.CHART):
                        masked_bboxes.append(bbox)
                        excluded_callout_bboxes.append(bbox)
                    elif isinstance(item, TableItem) or label == DocItemLabel.TABLE:
                        masked_bboxes.append(bbox)
                        excluded_callout_bboxes.append(bbox)
                    elif isinstance(item, FormulaItem) or label == DocItemLabel.FORMULA:
                        masked_bboxes.append(bbox)

                blocks: list[DocumentBlock] = []
                fig_idx = 0
                tbl_idx = 0
                eq_idx = 0
                txt_idx = 0

                for item, ir_bbox in page_items:
                    label = getattr(item, "label", None)

                    if isinstance(item, PictureItem) or label in (DocItemLabel.PICTURE, DocItemLabel.CHART):
                        img_out = assets_dir / f"p{page_no}_fig_{fig_idx}.png"
                        w_pt, h_pt = cropper.crop_bbox(
                            page_no, ir_bbox, img_out, dpi=options.crop_dpi, pad_pt=2.0
                        )
                        blocks.append(
                            FigureBlock(
                                id=f"p{page_no}_fig_{fig_idx}",
                                page_no=page_no,
                                bbox=ir_bbox,
                                image_path=str(img_out),
                                image_width_pt=w_pt,
                                image_height_pt=h_pt,
                                source="hybrid",
                            )
                        )
                        fig_idx += 1
                        continue

                    if isinstance(item, TableItem) or label == DocItemLabel.TABLE:
                        tdata = item.data
                        num_rows = max(1, int(tdata.num_rows))
                        num_cols = max(1, int(tdata.num_cols))
                        col_widths = _compute_col_widths(
                            list(tdata.table_cells), num_cols, ir_bbox, ph
                        )
                        has_explicit_headers = any(bool(c.column_header) for c in tdata.table_cells)
                        cells: list[TableCellIR] = []
                        for c in tdata.table_cells:
                            c_text = (c.text or "").strip()
                            runs: list[TextRun] = []
                            align = Alignment.LEFT
                            if c.bbox is not None and not use_ocr:
                                cbox = _to_ir_bbox(c.bbox, ph)
                                runs, align = extract_styled_runs(
                                    p_page, cbox, fallback_text=c_text
                                )
                            if not runs and c_text:
                                runs = [TextRun(text=c_text, font_size_pt=9.0, bold=bool(c.column_header))]
                            is_hdr = bool(c.column_header) or (not has_explicit_headers and c.start_row_offset_idx == 0)
                            cells.append(
                                TableCellIR(
                                    row=int(c.start_row_offset_idx),
                                    col=int(c.start_col_offset_idx),
                                    row_span=max(1, int(c.row_span)),
                                    col_span=max(1, int(c.col_span)),
                                    text=c_text,
                                    runs=runs,
                                    is_header=is_hdr,
                                    alignment=align,
                                )
                            )
                        blocks.append(
                            TableBlock(
                                id=f"p{page_no}_tbl_{tbl_idx}",
                                page_no=page_no,
                                bbox=ir_bbox,
                                num_rows=num_rows,
                                num_cols=num_cols,
                                col_widths_pt=col_widths,
                                cells=cells,
                                style_hint=_detect_table_style(p_page, ir_bbox),
                                source="ocr" if use_ocr else "hybrid",
                            )
                        )
                        tbl_idx += 1
                        continue

                    if isinstance(item, FormulaItem) or label == DocItemLabel.FORMULA:
                        col_box = _column_container_bbox(
                            ir_bbox, pw, margins.left, margins.right, preflight.detected_columns
                        )
                        eq_num, crop_box = detect_equation_number(p_page, ir_bbox, col_box.x1)
                        img_out = assets_dir / f"p{page_no}_eq_{eq_idx}.png"
                        w_pt, h_pt = cropper.crop_bbox(
                            page_no,
                            crop_box,
                            img_out,
                            dpi=options.formula_crop_dpi,
                            pad_pt=1.5,
                            trim_whitespace=True,
                        )
                        raw_txt = str(getattr(item, "orig", None) or getattr(item, "text", "") or "").strip()
                        latex_txt = str(getattr(item, "text", "") or "").strip() or None
                        blocks.append(
                            FormulaBlock(
                                id=f"p{page_no}_eq_{eq_idx}",
                                page_no=page_no,
                                bbox=ir_bbox,
                                latex=latex_txt,
                                raw_text=raw_txt,
                                equation_number=eq_num,
                                is_display=True,
                                image_path=str(img_out),
                                image_width_pt=w_pt,
                                image_height_pt=h_pt,
                                source="hybrid",
                            )
                        )
                        eq_idx += 1
                        continue

                    # Skip text items that overlap masked figure/table/formula boxes (vector figure label guard)
                    if any(ir_bbox.intersection_ratio(mb) > 0.55 for mb in masked_bboxes):
                        continue

                    if isinstance(item, (TextItem, TitleItem, SectionHeaderItem, ListItem, CodeItem)) or hasattr(item, "text"):
                        raw_text = str(getattr(item, "text", "") or "").strip()
                        if not raw_text:
                            continue

                        if isinstance(item, TitleItem) or label == DocItemLabel.TITLE:
                            btype = BlockType.TITLE
                        elif isinstance(item, SectionHeaderItem) or label == DocItemLabel.SECTION_HEADER:
                            btype = BlockType.HEADING
                        elif isinstance(item, ListItem) or label == DocItemLabel.LIST_ITEM:
                            btype = BlockType.LIST_ITEM
                        elif isinstance(item, CodeItem) or label == DocItemLabel.CODE:
                            btype = BlockType.CODE_BLOCK
                        else:
                            btype = _LABEL_TO_BLOCK_TYPE.get(label, BlockType.PARAGRAPH) if label else BlockType.PARAGRAPH

                        col_box = _column_container_bbox(
                            ir_bbox, pw, margins.left, margins.right, preflight.detected_columns
                        )
                        preserve_lb = btype == BlockType.CODE_BLOCK
                        if use_ocr or page_no in preflight.broken_cmap_pages:
                            runs = [TextRun(text=raw_text, font_size_pt=10.0, is_code=(btype == BlockType.CODE_BLOCK))]
                            align = Alignment.CENTER if btype == BlockType.TITLE else Alignment.LEFT
                        else:
                            runs, align = extract_styled_runs(
                                p_page,
                                ir_bbox,
                                fallback_text=raw_text,
                                container_bbox=col_box,
                                preserve_line_breaks=preserve_lb,
                            )
                        if not runs:
                            runs = [TextRun(text=raw_text, font_size_pt=10.0)]

                        plain = "".join(r.text for r in runs).strip() or raw_text
                        h_level = None
                        if btype == BlockType.HEADING:
                            h_level = int(getattr(item, "level", 1) or 1)
                        marker = str(getattr(item, "marker", "") or "").strip() or None if btype == BlockType.LIST_ITEM else None

                        blocks.append(
                            TextBlock(
                                id=f"p{page_no}_txt_{txt_idx}",
                                page_no=page_no,
                                bbox=ir_bbox,
                                block_type=btype,
                                runs=runs,
                                plain_text=plain,
                                alignment=align,
                                heading_level=h_level,
                                list_marker=marker,
                                keep_with_next=(btype in (BlockType.TITLE, BlockType.HEADING)),
                                source="ocr" if use_ocr else "hybrid",
                            )
                        )
                        txt_idx += 1

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
