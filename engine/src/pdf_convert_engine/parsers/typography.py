"""Precise typography, color, super/subscript, callout rect, and equation number extraction."""

from __future__ import annotations

import re
from statistics import median
from typing import Any

from pdf_convert_engine.ir.schema import Alignment, BBox, TextRun
from pdf_convert_engine.preflight.analyzer import detect_broken_unicode_text

_EQ_NUM_RE = re.compile(r"^\s*(\(\d+(?:\.\d+)*\)|\[\d+(?:\.\d+)*\])\s*$")
_EQ_TRAIL_RE = re.compile(r"\s+(\(\d+(?:\.\d+)*\)|\[\d+(?:\.\d+)*\])\s*$")


def color_to_hex(color: Any) -> str | None:
    """Convert pdfplumber stroking/non-stroking color tuple or float to 6-char uppercase hex."""
    if color is None:
        return None
    if isinstance(color, (int, float)):
        v = max(0, min(255, int(round(float(color) * 255))))
        return f"{v:02X}{v:02X}{v:02X}"
    if isinstance(color, (list, tuple)):
        if len(color) == 1:
            v = max(0, min(255, int(round(float(color[0]) * 255))))
            return f"{v:02X}{v:02X}{v:02X}"
        if len(color) == 3:
            r, g, b = (max(0, min(255, int(round(float(c) * 255)))) for c in color)
            return f"{r:02X}{g:02X}{b:02X}"
        if len(color) == 4:
            c, m, y, k = (float(x) for x in color)
            r = int(round(255 * (1.0 - c) * (1.0 - k)))
            g = int(round(255 * (1.0 - m) * (1.0 - k)))
            b = int(round(255 * (1.0 - y) * (1.0 - k)))
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            return f"{r:02X}{g:02X}{b:02X}"
    return None


def _is_white_or_none(hex_color: str | None) -> bool:
    if not hex_color:
        return True
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return r >= 252 and g >= 252 and b >= 252


def _clean_fontname(raw: str | None) -> str | None:
    if not raw:
        return None
    if "+" in raw:
        prefix, rest = raw.split("+", 1)
        if len(prefix) == 6 and prefix.isalpha():
            return rest
    return raw


def _font_flags(font_name: str | None) -> tuple[bool, bool, bool]:
    if not font_name:
        return False, False, False
    lower = font_name.lower()
    bold = any(tok in lower for tok in ("bold", "black", "heavy", "demi", "semibold", "cmbx"))
    italic = any(tok in lower for tok in ("italic", "oblique", "slant", "cmti", "cmsl"))
    is_code = any(tok in lower for tok in ("mono", "courier", "consolas", "cmtt", "menlo", "fira"))
    return bold, italic, is_code


def _cluster_chars_into_lines(chars: list[dict]) -> list[list[dict]]:
    if not chars:
        return []
    sizes = [float(c.get("size", 10.0) or 10.0) for c in chars]
    med_size = median(sizes) if sizes else 10.0
    y_tol = max(2.0, med_size * 0.45)

    sorted_chars = sorted(chars, key=lambda c: ((float(c["top"]) + float(c["bottom"])) / 2.0, float(c["x0"])))
    lines: list[list[dict]] = []
    current_line: list[dict] = []
    current_cy = 0.0

    for ch in sorted_chars:
        cy = (float(ch["top"]) + float(ch["bottom"])) / 2.0
        if not current_line:
            current_line = [ch]
            current_cy = cy
        elif abs(cy - current_cy) <= y_tol:
            current_line.append(ch)
            # running average center y
            current_cy = sum((float(x["top"]) + float(x["bottom"])) / 2.0 for x in current_line) / len(current_line)
        else:
            lines.append(sorted(current_line, key=lambda x: float(x["x0"])))
            current_line = [ch]
            current_cy = cy

    if current_line:
        lines.append(sorted(current_line, key=lambda x: float(x["x0"])))
    return lines


def _infer_alignment(lines: list[list[dict]], container_bbox: BBox) -> Alignment:
    if not lines or container_bbox.width <= 1.0:
        return Alignment.LEFT

    line_spans = [
        (float(ln[0]["x0"]), float(ln[-1]["x1"]))
        for ln in lines
        if ln
    ]
    if not line_spans:
        return Alignment.LEFT

    # Centered check: left and right margins within container are roughly balanced
    # and the lines are meaningfully narrower than container width or multiple centered lines
    left_gaps = [abs(x0 - container_bbox.x0) for x0, _ in line_spans]
    right_gaps = [abs(container_bbox.x1 - x1) for _, x1 in line_spans]

    if len(line_spans) == 1:
        x0, x1 = line_spans[0]
        line_w = x1 - x0
        left_gap = x0 - container_bbox.x0
        right_gap = container_bbox.x1 - x1
        if line_w < container_bbox.width * 0.85:
            if left_gap > 12 and right_gap > 12 and abs(left_gap - right_gap) <= max(12.0, container_bbox.width * 0.08):
                return Alignment.CENTER
            if left_gap > container_bbox.width * 0.35 and right_gap < 10:
                return Alignment.RIGHT
        return Alignment.LEFT

    # Multiple lines: check centered vs justify vs left
    centered_lines = sum(
        1 for (x0, x1) in line_spans
        if (x1 - x0) < container_bbox.width * 0.90
        and abs((x0 - container_bbox.x0) - (container_bbox.x1 - x1)) <= max(10.0, container_bbox.width * 0.07)
        and (x0 - container_bbox.x0) > 8.0
    )
    if centered_lines >= max(2, len(line_spans) * 0.6):
        return Alignment.CENTER

    # Justified check on body paragraphs (all lines except last end near container x1)
    if len(line_spans) >= 3:
        non_last = line_spans[:-1]
        near_left = sum(1 for x0, _ in non_last if abs(x0 - container_bbox.x0) <= 6.0)
        near_right = sum(1 for _, x1 in non_last if abs(container_bbox.x1 - x1) <= 8.0)
        if near_left == len(non_last) and near_right >= len(non_last) - 1:
            return Alignment.JUSTIFY

    # Right alignment check
    if all((x0 - container_bbox.x0) > 15.0 and abs(container_bbox.x1 - x1) <= 6.0 for x0, x1 in line_spans):
        return Alignment.RIGHT

    return Alignment.LEFT


def extract_styled_runs(
    page: Any,
    bbox: BBox,
    fallback_text: str = "",
    container_bbox: BBox | None = None,
    preserve_line_breaks: bool = False,
) -> tuple[list[TextRun], Alignment]:
    """Extract styled TextRun spans and alignment from pdfplumber chars within `bbox`."""
    tol = 1.5
    chars = [
        ch for ch in (page.chars or [])
        if (
            bbox.x0 - tol <= (float(ch["x0"]) + float(ch["x1"])) / 2.0 <= bbox.x1 + tol
            and bbox.y0 - tol <= (float(ch["top"]) + float(ch["bottom"])) / 2.0 <= bbox.y1 + tol
        )
    ]

    if not chars:
        text = fallback_text.strip()
        if not text:
            return [], Alignment.LEFT
        est_size = max(8.0, min(20.0, round(bbox.height * 0.65, 1)))
        return [TextRun(text=text, font_size_pt=est_size)], Alignment.LEFT

    raw_text = "".join(str(ch.get("text", "")) for ch in chars)
    if detect_broken_unicode_text(raw_text) and fallback_text.strip():
        est_size = round(median([float(c.get("size", 10.0) or 10.0) for c in chars]), 1)
        return [TextRun(text=fallback_text.strip(), font_size_pt=est_size)], Alignment.LEFT

    lines = _cluster_chars_into_lines(chars)
    align_box = container_bbox or bbox
    alignment = _infer_alignment(lines, align_box)

    all_sizes = [float(c.get("size", 10.0) or 10.0) for c in chars]
    body_size = median(all_sizes) if all_sizes else 10.0

    runs: list[TextRun] = []

    def append_piece(
        piece: str,
        font_name: str | None,
        size_pt: float,
        bold: bool,
        italic: bool,
        superscript: bool,
        subscript: bool,
        color_hex: str | None,
        is_code: bool,
    ) -> None:
        if not piece:
            return
        if runs:
            last = runs[-1]
            if (
                last.font_name == font_name
                and abs(last.font_size_pt - size_pt) < 0.25
                and last.bold == bold
                and last.italic == italic
                and last.superscript == superscript
                and last.subscript == subscript
                and last.color_hex == color_hex
                and last.is_code == is_code
            ):
                last.text += piece
                return
        runs.append(
            TextRun(
                text=piece,
                font_name=font_name,
                font_size_pt=size_pt,
                bold=bold,
                italic=italic,
                superscript=superscript,
                subscript=subscript,
                color_hex=color_hex,
                is_code=is_code,
            )
        )

    for line_idx, line in enumerate(lines):
        if line_idx > 0:
            if preserve_line_breaks:
                append_piece(
                    "\n",
                    runs[-1].font_name if runs else None,
                    runs[-1].font_size_pt if runs else round(body_size, 1),
                    runs[-1].bold if runs else False,
                    runs[-1].italic if runs else False,
                    False,
                    False,
                    runs[-1].color_hex if runs else None,
                    runs[-1].is_code if runs else False,
                )
            else:
                # De-hyphenate wrapped English prose lines when ending with hyphen
                if runs and runs[-1].text.endswith("-") and len(runs[-1].text) >= 2 and runs[-1].text[-2].isalpha():
                    runs[-1].text = runs[-1].text[:-1]
                elif runs and not runs[-1].text.endswith((" ", "\n")):
                    runs[-1].text += " "

        line_sizes = [float(c.get("size", body_size) or body_size) for c in line]
        line_med_size = median(line_sizes) if line_sizes else body_size
        normal_chars = [c for c in line if float(c.get("size", line_med_size) or line_med_size) >= line_med_size * 0.85]
        line_cy = (
            median([(float(c["top"]) + float(c["bottom"])) / 2.0 for c in normal_chars])
            if normal_chars
            else median([(float(c["top"]) + float(c["bottom"])) / 2.0 for c in line])
        )

        prev_x1: float | None = None
        for ch in line:
            txt = str(ch.get("text", ""))
            if not txt:
                continue
            x0 = float(ch["x0"])
            x1 = float(ch["x1"])
            size = float(ch.get("size", line_med_size) or line_med_size)
            cy = (float(ch["top"]) + float(ch["bottom"])) / 2.0

            # Insert explicit space if pdfplumber omitted a space character between distant glyphs
            if prev_x1 is not None and txt != " ":
                gap = x0 - prev_x1
                if gap > max(1.5, size * 0.22):
                    if runs and not runs[-1].text.endswith((" ", "\n")):
                        runs[-1].text += " "

            fname = _clean_fontname(ch.get("fontname"))
            bold, italic, is_code = _font_flags(fname)

            is_super = False
            is_sub = False
            if size < line_med_size * 0.82 and txt.strip():
                if cy < line_cy - line_med_size * 0.12:
                    is_super = True
                elif cy > line_cy + line_med_size * 0.12:
                    is_sub = True

            hex_col = color_to_hex(ch.get("non_stroking_color"))
            if hex_col == "000000":
                hex_col = None  # keep default text color clean

            eff_size = round(line_med_size if (is_super or is_sub) else size, 1)
            append_piece(
                txt,
                fname,
                eff_size,
                bold,
                italic,
                is_super,
                is_sub,
                hex_col,
                is_code,
            )
            prev_x1 = x1

    # Clean redundant whitespace on non-code runs
    if not preserve_line_breaks:
        for r in runs:
            r.text = re.sub(r" {2,}", " ", r.text)
        if runs:
            runs[0].text = runs[0].text.lstrip()
            runs[-1].text = runs[-1].text.rstrip()
        runs = [r for r in runs if r.text]

    return runs, alignment


def detect_callout_rects(
    page: Any,
    excluded_bboxes: list[BBox],
) -> list[dict[str, Any]]:
    """Find shaded or bordered rectangular callout boxes on a PDF page."""
    pw = float(page.width)
    ph = float(page.height)
    page_area = pw * ph
    candidates: list[dict[str, Any]] = []

    for rect in page.rects or []:
        bbox = BBox(
            x0=float(rect["x0"]),
            y0=float(rect["top"]),
            x1=float(rect["x1"]),
            y1=float(rect["bottom"]),
        )
        if bbox.width < 110.0 or bbox.height < 26.0:
            continue
        if bbox.area > page_area * 0.85:
            continue

        fill_hex = color_to_hex(rect.get("non_stroking_color")) if rect.get("fill") else None
        stroke_hex = color_to_hex(rect.get("stroking_color")) if rect.get("stroke") else None
        has_visible_fill = not _is_white_or_none(fill_hex)
        has_visible_stroke = stroke_hex is not None and float(rect.get("linewidth", 0) or 0) > 0

        if not has_visible_fill and not has_visible_stroke:
            continue

        # Skip if rect is part of a table or figure
        if any(bbox.intersection_ratio(ex) > 0.35 or ex.intersection_ratio(bbox) > 0.35 for ex in excluded_bboxes):
            continue

        # Check whether there is actual text inside this rectangle
        inside_chars = [
            ch for ch in (page.chars or [])
            if bbox.x0 <= (float(ch["x0"]) + float(ch["x1"])) / 2.0 <= bbox.x1
            and bbox.y0 <= (float(ch["top"]) + float(ch["bottom"])) / 2.0 <= bbox.y1
        ]
        if len(inside_chars) < 8:
            continue

        candidates.append(
            {
                "bbox": bbox,
                "fill_hex": fill_hex if has_visible_fill else "F6F8FA",
                "border_hex": stroke_hex or "3B6EA5",
                "border_width_pt": max(0.75, float(rect.get("linewidth", 1.0) or 1.0)),
                "accent_left_only": has_visible_fill and not has_visible_stroke,
            }
        )

    # Check if a tall thin vertical accent line sits directly along the left edge of a fill rect
    for line in page.lines or []:
        lx0 = float(line["x0"])
        lx1 = float(line["x1"])
        ly0 = float(line["top"])
        ly1 = float(line["bottom"])
        if abs(lx1 - lx0) <= 4.0 and abs(ly1 - ly0) >= 24.0:
            lcol = color_to_hex(line.get("stroking_color"))
            lw = float(line.get("linewidth", 1.5) or 1.5)
            for cand in candidates:
                cb: BBox = cand["bbox"]
                if abs(lx0 - cb.x0) <= 4.0 and ly0 >= cb.y0 - 4.0 and ly1 <= cb.y1 + 4.0:
                    if lcol:
                        cand["border_hex"] = lcol
                    cand["border_width_pt"] = max(cand["border_width_pt"], lw)
                    cand["accent_left_only"] = True

    # Deduplicate overlapping rects (keep largest outer box)
    candidates.sort(key=lambda c: c["bbox"].area, reverse=True)
    deduped: list[dict[str, Any]] = []
    for cand in candidates:
        if any(cand["bbox"].intersection_ratio(prev["bbox"]) > 0.7 for prev in deduped):
            continue
        deduped.append(cand)
    return deduped


def detect_equation_number(
    page: Any,
    formula_bbox: BBox,
    column_right_x: float,
) -> tuple[str | None, BBox]:
    """Detect equation label like `(1)` on the same horizontal band and trim it from crop bbox."""
    y_tol = 6.0
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False) or []

    # 1. Check words to the right of formula_bbox in the same horizontal band up to column_right_x
    band_words = [
        w for w in words
        if float(w["top"]) >= formula_bbox.y0 - y_tol
        and float(w["bottom"]) <= formula_bbox.y1 + y_tol
        and float(w["x0"]) >= formula_bbox.x0
        and float(w["x1"]) <= column_right_x + 12.0
    ]
    band_words.sort(key=lambda w: float(w["x0"]))

    for w in reversed(band_words):
        txt = str(w.get("text", "")).strip()
        if _EQ_NUM_RE.match(txt):
            wx0 = float(w["x0"])
            # If the equation number was inside formula_bbox, trim it cleanly
            if wx0 >= formula_bbox.center_x:
                new_x1 = min(formula_bbox.x1, max(formula_bbox.x0 + 12.0, wx0 - 6.0))
                trimmed = BBox(x0=formula_bbox.x0, y0=formula_bbox.y0, x1=new_x1, y1=formula_bbox.y1)
                return txt, trimmed
    return None, formula_bbox
