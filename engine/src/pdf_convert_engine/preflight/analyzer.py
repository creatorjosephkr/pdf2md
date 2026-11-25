"""Fast preflight diagnostics for PDF documents using pdfplumber and pypdfium2."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import pdfplumber

from pdf_convert_engine.ir.schema import MarginBox, PreflightReport

_CID_RE = re.compile(r"\(cid:\d+\)")


def detect_broken_unicode_text(text: str) -> bool:
    """Detect whether extracted PDF text has broken CMap / PUA / replacement garbling."""
    if not text:
        return False

    cid_matches = _CID_RE.findall(text)
    cleaned_len = max(1, len(re.sub(r"\s+", "", _CID_RE.sub("", text))))
    if len(cid_matches) >= 10 or (len(cid_matches) >= 3 and (len(cid_matches) / (cleaned_len + len(cid_matches))) > 0.03):
        return True

    non_ws = [ch for ch in text if not ch.isspace()]
    if not non_ws:
        return False

    bad_count = 0
    for ch in non_ws:
        code = ord(ch)
        if code == 0xFFFD:
            bad_count += 1
        elif 0xE000 <= code <= 0xF8FF:  # Private Use Area (often broken CMap glyphs)
            bad_count += 1
        elif code < 0x20:  # non-whitespace control char
            bad_count += 1

    return (bad_count / len(non_ws)) > 0.03


def detect_language_from_text(text: str) -> Literal["ko", "en", "mixed", "other"]:
    """Classify dominant script across Hangul syllables and Latin characters."""
    if not text:
        return "other"

    ko_count = 0
    en_count = 0
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3 or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F:
            ko_count += 1
        elif ("A" <= ch <= "Z") or ("a" <= ch <= "z"):
            en_count += 1

    total = ko_count + en_count
    if total == 0:
        return "other"
    ko_ratio = ko_count / total
    en_ratio = en_count / total

    if ko_ratio >= 0.15 and en_ratio >= 0.15:
        return "mixed"
    if ko_count > en_count:
        return "ko"
    if en_count >= ko_count:
        return "en"
    return "other"


def _clean_font_name(raw_name: str) -> str:
    if "+" in raw_name:
        prefix, rest = raw_name.split("+", 1)
        if len(prefix) == 6 and prefix.isalpha():
            return rest
    return raw_name


def _estimate_page_columns(words: list[dict], page_width: float, page_height: float) -> int:
    """Detect 2-column layout by verifying a persistent horizontal gutter across Y-rows."""
    if len(words) < 20 or page_width <= 0 or page_height <= 0:
        return 1

    body_top = page_height * 0.14
    body_bottom = page_height * 0.88
    body_words = [
        w for w in words
        if w["top"] >= body_top and w["bottom"] <= body_bottom
    ]
    if len(body_words) < 16:
        return 1

    # Group words into horizontal rows (Y-center within 4pt)
    sorted_w = sorted(body_words, key=lambda w: ((float(w["top"]) + float(w["bottom"])) / 2.0, float(w["x0"])))
    rows: list[list[dict]] = []
    cur: list[dict] = []
    cur_cy = 0.0
    for w in sorted_w:
        cy = (float(w["top"]) + float(w["bottom"])) / 2.0
        if not cur:
            cur = [w]
            cur_cy = cy
        elif abs(cy - cur_cy) <= 4.5:
            cur.append(w)
            cur_cy = sum((float(x["top"]) + float(x["bottom"])) / 2.0 for x in cur) / len(cur)
        else:
            rows.append(sorted(cur, key=lambda x: float(x["x0"])))
            cur = [w]
            cur_cy = cy
    if cur:
        rows.append(sorted(cur, key=lambda x: float(x["x0"])))

    mid = page_width / 2.0
    dual_rows = 0
    gutter_rows = 0
    gutter_min_pt = max(10.0, page_width * 0.018)

    for row in rows:
        # Check if any word physically straddles the page center
        straddling = any(float(w["x0"]) < mid - 2.0 and float(w["x1"]) > mid + 2.0 for w in row)
        left_part = [w for w in row if (float(w["x0"]) + float(w["x1"])) / 2.0 < mid]
        right_part = [w for w in row if (float(w["x0"]) + float(w["x1"])) / 2.0 >= mid]
        if not left_part or not right_part:
            continue

        dual_rows += 1
        if straddling:
            continue

        left_end = max(float(w["x1"]) for w in left_part)
        right_start = min(float(w["x0"]) for w in right_part)
        gap = right_start - left_end
        if gap >= gutter_min_pt and left_end <= mid + 6.0 and right_start >= mid - 6.0:
            gutter_rows += 1

    if dual_rows >= 4 and gutter_rows >= 4 and (gutter_rows / dual_rows) >= 0.65:
        return 2
    return 1


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(round((len(s) - 1) * pct))
    return s[max(0, min(len(s) - 1, idx))]


def _clamp_margin(val: float, default: float = 54.0) -> float:
    if val <= 0:
        return default
    return round(max(24.0, min(108.0, val)), 1)


def analyze_pdf(
    pdf_path: str | Path,
    page_range: tuple[int, int] | None = None,
) -> PreflightReport:
    """Analyze a PDF file and produce a PreflightReport without loading heavy ML models."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    page_sizes_pt: list[tuple[float, float]] = []
    digital_pages = 0
    scanned_pages = 0
    broken_cmap_pages: list[int] = []
    column_votes: list[int] = []
    fonts_set: set[str] = set()
    all_text_chunks: list[str] = []
    warnings: list[str] = []

    left_margins: list[float] = []
    right_margins: list[float] = []
    top_margins: list[float] = []
    bottom_margins: list[float] = []

    with pdfplumber.open(path) as pdf:
        total_pages = len(pdf.pages)
        start_idx = 0
        end_idx = total_pages
        if page_range is not None:
            start_idx = max(0, page_range[0] - 1)
            end_idx = min(total_pages, page_range[1])

        selected_pages = pdf.pages[start_idx:end_idx]
        for idx, page in enumerate(selected_pages, start=start_idx + 1):
            pw = float(page.width)
            ph = float(page.height)
            page_sizes_pt.append((round(pw, 2), round(ph, 2)))
            page_area = pw * ph

            chars = page.chars or []
            char_count = len(chars)
            for ch in chars:
                fname = ch.get("fontname")
                if fname:
                    fonts_set.add(_clean_font_name(str(fname)))

            text = page.extract_text() or ""
            if text:
                all_text_chunks.append(text)

            images = page.images or []
            img_area = sum(
                max(0.0, (float(im["x1"]) - float(im["x0"])))
                * max(0.0, (float(im["bottom"]) - float(im["top"])))
                for im in images
            )
            img_ratio = img_area / page_area if page_area > 0 else 0.0

            is_scanned = char_count < 25 and (img_ratio > 0.35 or (len(images) > 0 and len(text.strip()) < 15))
            if is_scanned:
                scanned_pages += 1
            else:
                digital_pages += 1

            if detect_broken_unicode_text(text):
                broken_cmap_pages.append(idx)

            words = page.extract_words(keep_blank_chars=False, use_text_flow=False) or []
            if not is_scanned:
                column_votes.append(_estimate_page_columns(words, pw, ph))

            # Collect bbox bounds for margin estimation
            element_boxes: list[tuple[float, float, float, float]] = [
                (float(w["x0"]), float(w["top"]), float(w["x1"]), float(w["bottom"]))
                for w in words
            ]
            for rect in page.rects or []:
                rw = float(rect["x1"]) - float(rect["x0"])
                rh = float(rect["bottom"]) - float(rect["top"])
                if rw * rh < page_area * 0.90:
                    element_boxes.append(
                        (float(rect["x0"]), float(rect["top"]), float(rect["x1"]), float(rect["bottom"]))
                    )
            if element_boxes:
                x0s = [b[0] for b in element_boxes]
                y0s = [b[1] for b in element_boxes]
                x1s = [b[2] for b in element_boxes]
                y1s = [b[3] for b in element_boxes]
                left_margins.append(_percentile(x0s, 0.03))
                top_margins.append(_percentile(y0s, 0.03))
                right_margins.append(pw - _percentile(x1s, 0.97))
                bottom_margins.append(ph - _percentile(y1s, 0.97))

    detected_columns = 2 if column_votes.count(2) >= max(1, len(column_votes) // 2) and column_votes.count(2) > 0 else 1
    combined_text = "\n".join(all_text_chunks)
    detected_language = detect_language_from_text(combined_text)

    if broken_cmap_pages:
        warnings.append(
            f"Broken Unicode/CMap detected on page(s) {broken_cmap_pages}; local OCR recommended."
        )
    if scanned_pages > 0:
        warnings.append(
            f"Detected {scanned_pages} scanned/image-only page(s); local OCR enabled."
        )

    recommended_ocr = scanned_pages > 0 or len(broken_cmap_pages) > 0

    estimated_margins = MarginBox(
        top=_clamp_margin(_percentile(top_margins, 0.5) if top_margins else 54.0),
        bottom=_clamp_margin(_percentile(bottom_margins, 0.5) if bottom_margins else 54.0),
        left=_clamp_margin(_percentile(left_margins, 0.5) if left_margins else 54.0),
        right=_clamp_margin(_percentile(right_margins, 0.5) if right_margins else 54.0),
    )

    return PreflightReport(
        file_path=str(path.resolve()),
        page_count=len(page_sizes_pt),
        page_sizes_pt=page_sizes_pt,
        digital_pages=digital_pages,
        scanned_pages=scanned_pages,
        broken_cmap_pages=broken_cmap_pages,
        detected_columns=detected_columns,
        detected_language=detected_language,
        fonts_found=sorted(fonts_set),
        estimated_margins_pt=estimated_margins,
        recommended_ocr=recommended_ocr,
        warnings=warnings,
    )
