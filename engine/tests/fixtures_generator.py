"""Generate realistic academic benchmark PDFs for testing and evaluation."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle


def _register_korean_fonts() -> tuple[str, str]:
    """Register Korean TTF fonts if present; return (gothic_name, myungjo_name)."""
    gothic_path = Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf")
    myungjo_path = Path("/System/Library/Fonts/Supplemental/AppleMyungjo.ttf")

    gothic_name = "Helvetica"
    myungjo_name = "Times-Roman"

    if gothic_path.exists():
        if "AppleGothic" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("AppleGothic", str(gothic_path)))
        gothic_name = "AppleGothic"
    if myungjo_path.exists():
        if "AppleMyungjo" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("AppleMyungjo", str(myungjo_path)))
        myungjo_name = "AppleMyungjo"

    return gothic_name, myungjo_name


def _draw_para(c: canvas.Canvas, html_text: str, style: ParagraphStyle, x: float, top_y: float, width: float) -> float:
    """Draw a ReportLab Paragraph whose top edge is at `top_y` (canvas Y). Returns new bottom Y."""
    p = Paragraph(html_text, style)
    _w, h = p.wrapOn(c, width, 1000)
    p.drawOn(c, x, top_y - h)
    return top_y - h


def generate_academic_2col_en(out_path: str | Path) -> Path:
    """Create a 2-page IEEE/ArXiv-style 2-column English academic paper with spanning figure and booktabs table."""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _gothic, myungjo = _register_korean_fonts()
    math_font = myungjo if myungjo != "Times-Roman" else "Times-Italic"
    pw, ph = letter  # 612 x 792 pt
    margin = 54.0
    content_w = pw - 2 * margin  # 504 pt
    gutter = 18.0
    col_w = (content_w - gutter) / 2.0  # 243 pt
    left_x = margin
    right_x = margin + col_w + gutter

    title_style = ParagraphStyle(
        "Title", fontName="Times-Bold", fontSize=16, leading=20, alignment=TA_CENTER
    )
    author_style = ParagraphStyle(
        "Author", fontName="Times-Roman", fontSize=10, leading=13, alignment=TA_CENTER
    )
    affil_style = ParagraphStyle(
        "Affil", fontName="Times-Italic", fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.HexColor("#475569")
    )
    h1_style = ParagraphStyle(
        "H1", fontName="Times-Bold", fontSize=11.5, leading=14, alignment=TA_LEFT
    )
    h2_style = ParagraphStyle(
        "H2", fontName="Times-BoldItalic", fontSize=10.5, leading=13, alignment=TA_LEFT
    )
    body_style = ParagraphStyle(
        "Body", fontName="Times-Roman", fontSize=9.5, leading=12.5, alignment=TA_JUSTIFY
    )
    cap_style = ParagraphStyle(
        "Caption", fontName="Times-Italic", fontSize=9, leading=11.5, alignment=TA_CENTER
    )

    c = canvas.Canvas(str(path), pagesize=letter)

    # ---------------- Page 1 ----------------
    y = ph - margin
    y = _draw_para(c, "High-Fidelity Layout Reconstruction for Academic PDFs", title_style, left_x, y, content_w)
    y -= 6
    y = _draw_para(c, "Minjun Kim<sup>1</sup>, Elena Rostova<sup>2</sup>, and Alex Chen<sup>1</sup>", author_style, left_x, y, content_w)
    y -= 2
    y = _draw_para(c, "<sup>1</sup>Seoul National University  |  <sup>2</sup>ETH Zurich", affil_style, left_x, y, content_w)
    y -= 10
    y = _draw_para(
        c,
        "<b>Abstract—</b>Reconstructing fixed-coordinate academic PDF files into editable Google Docs "
        "requires recovering multi-column reading order, mathematical formulas, and vector figures without "
        "breaking reflow constraints. In this paper, we introduce a local hybrid compilation architecture that "
        "combines semantic AI layout parsing with Docs-Safe OpenXML continuous section planning.",
        body_style,
        left_x,
        y,
        content_w,
    )
    y -= 14

    col_top = y

    # Left column
    ly = col_top
    ly = _draw_para(c, "1. Introduction", h1_style, left_x, ly, col_w)
    ly -= 5
    ly = _draw_para(
        c,
        "Modern scholarly publishing relies heavily on PDF typesetting engines such as LaTeX. While PDF preserves "
        "exact visual appearance across platforms, naive conversion into word processors destroys <i>two-column</i> "
        "alignment, splits figure labels into body paragraphs, and drops complex equations<sup>[1]</sup>.",
        body_style,
        left_x,
        ly,
        col_w,
    )
    ly -= 8
    ly = _draw_para(
        c,
        "To resolve these structural failures, our pipeline separates vector diagrams via mask-first cropping "
        "and replaces fragile floating text boxes with fixed-grid OpenXML primitives. Experimental evaluations "
        "confirm substantial improvements in visual similarity across diverse benchmark papers<sup>[2]</sup>.",
        body_style,
        left_x,
        ly,
        col_w,
    )
    ly -= 12

    # Equation (1) in left column
    c.setFont(math_font, 10.0)
    c.drawCentredString(left_x + col_w * 0.44, ly - 12, "L(w) = ∑ || f(x_i; w) - y_i ||² + λ R(w)")
    c.setFont("Times-Roman", 9.5)
    c.drawRightString(left_x + col_w, ly - 12, "(1)")
    ly -= 28

    ly = _draw_para(
        c,
        "Equation (1) defines our regularized layout reconstruction loss where <b>lambda</b> balances boundary "
        "fidelity against paragraph continuity across narrow column gutters.",
        body_style,
        left_x,
        ly,
        col_w,
    )

    # Right column
    ry = col_top
    ry = _draw_para(c, "2. Methodology", h1_style, right_x, ry, col_w)
    ry -= 5
    ry = _draw_para(
        c,
        "Our hybrid compiler inspects each page in four sequential stages: preflight diagnosis, semantic block "
        "segmentation, continuous section band planning, and Google Docs-Safe OOXML emission.",
        body_style,
        right_x,
        ry,
        col_w,
    )
    ry -= 8
    ry = _draw_para(c, "2.1 Core Compilation Principles", h2_style, right_x, ry, col_w)
    ry -= 4
    ry = _draw_para(
        c,
        "1) <b>Mask-First Figures:</b> Vector chart labels inside figure regions are masked before prose extraction.",
        body_style,
        right_x,
        ry,
        col_w,
    )
    ry -= 4
    ry = _draw_para(
        c,
        "2) <b>Zero Floating TextBoxes:</b> All callouts and numbered equations compile to borderless or shaded tables.",
        body_style,
        right_x,
        ry,
        col_w,
    )
    ry -= 10
    c.setFont(math_font, 10.0)
    c.drawCentredString(right_x + col_w * 0.44, ry - 12, "Score = α · SSIM + (1 - α) · PageMatch")
    c.setFont("Times-Roman", 9.5)
    c.drawRightString(right_x + col_w, ry - 12, "(2)")
    ry -= 28

    ry = _draw_para(
        c,
        "As shown in (2), page count preservation carries explicit weight during Google Docs roundtrip self-healing.",
        body_style,
        right_x,
        ry,
        col_w,
    )

    c.setFont("Times-Roman", 8.5)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawCentredString(pw / 2.0, 28, "IEEE Academic Layout Benchmark — Page 1")
    c.showPage()

    # ---------------- Page 2: Wide Spanning Figure + 2-Col Text + Wide Booktabs Table ----------------
    y = ph - margin

    # Wide vector chart spanning both columns (x = left_x .. left_x + content_w)
    fig_h = 130.0
    fig_bottom = y - fig_h
    c.setFillColor(colors.HexColor("#F8FAFC"))
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(0.8)
    c.rect(left_x, fig_bottom, content_w, fig_h, fill=1, stroke=1)

    # Chart axes & bars inside wide figure
    ax_x0 = left_x + 55
    ax_y0 = fig_bottom + 26
    ax_w = content_w - 90
    ax_h = fig_h - 46
    c.setStrokeColor(colors.HexColor("#334155"))
    c.setLineWidth(1.0)
    c.line(ax_x0, ax_y0, ax_x0, ax_y0 + ax_h)
    c.line(ax_x0, ax_y0, ax_x0 + ax_w, ax_y0)

    bars = [
        ("Text-Only", 0.34, "#94A3B8"),
        ("LibreOffice", 0.58, "#64748B"),
        ("Direct Drive", 0.49, "#F59E0B"),
        ("Docs-Safe Hybrid", 0.94, "#2563EB"),
    ]
    bar_w = 54.0
    step = ax_w / len(bars)
    for i, (lbl, val, col_hex) in enumerate(bars):
        bx = ax_x0 + i * step + (step - bar_w) / 2.0
        bh = val * (ax_h - 10)
        c.setFillColor(colors.HexColor(col_hex))
        c.rect(bx, ax_y0, bar_w, bh, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#0F172A"))
        c.setFont("Helvetica-Bold", 8.5)
        c.drawCentredString(bx + bar_w / 2.0, ax_y0 + bh + 4, f"{int(val * 100)}%")
        c.setFont("Helvetica", 8)
        c.drawCentredString(bx + bar_w / 2.0, ax_y0 - 13, lbl)

    c.setFillColor(colors.HexColor("#334155"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(ax_x0 + 8, fig_bottom + fig_h - 16, "Visual Fidelity Comparison (SSIM %)")

    y = fig_bottom - 6
    y = _draw_para(
        c,
        "<b>Figure 1:</b> End-to-end Google Docs layout similarity comparison across conversion strategies.",
        cap_style,
        left_x,
        y,
        content_w,
    )
    y -= 14

    # 2-column body below wide figure
    col2_top = y
    ly = _draw_para(c, "3. Experimental Results", h1_style, left_x, col2_top, col_w)
    ly -= 5
    ly = _draw_para(
        c,
        "Across 40 multi-column papers, our continuous-section compiler preserves visual alignment without "
        "introducing orphan break paragraphs or clipped charts. Table 1 summarizes the measured quality metrics.",
        body_style,
        left_x,
        ly,
        col_w,
    )

    ry = _draw_para(c, "4. Conclusion", h1_style, right_x, col2_top, col_w)
    ry -= 5
    ry = _draw_para(
        c,
        "Combining local AI parsing with Docs-Safe OpenXML compilation achieves reliable layout fidelity while "
        "keeping sensitive research manuscripts completely offline prior to export.",
        body_style,
        right_x,
        ry,
        col_w,
    )

    y = min(ly, ry) - 18
    y = _draw_para(
        c,
        "<b>Table 1:</b> Quantitative layout preservation comparison on 2-column academic papers.",
        cap_style,
        left_x,
        y,
        content_w,
    )
    y -= 6

    # Wide Booktabs table with merged header cells
    tbl_data = [
        ["Method", "Layout Metrics", "", "Equation & Figure"],
        ["", "Column Fidelity", "Page Match", "Alt-Text LaTeX"],
        ["Direct Drive Import", "42.1%", "51.0%", "Dropped"],
        ["Generic PDF-to-DOCX", "68.5%", "74.2%", "Partial"],
        ["Docs-Safe Hybrid (Ours)", "96.4%", "98.0%", "Preserved"],
    ]
    tbl = Table(tbl_data, colWidths=[150, 115, 115, 124])
    tbl.setStyle(
        TableStyle(
            [
                ("SPAN", (1, 0), (2, 0)),
                ("SPAN", (0, 0), (0, 1)),
                ("SPAN", (3, 0), (3, 1)),
                ("FONTNAME", (0, 0), (-1, 1), "Times-Bold"),
                ("FONTNAME", (0, 2), (-1, -1), "Times-Roman"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("ALIGN", (0, 2), (0, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEABOVE", (0, 0), (-1, 0), 1.3, colors.black),
                ("LINEBELOW", (1, 0), (2, 0), 0.6, colors.grey),
                ("LINEBELOW", (0, 1), (-1, 1), 0.9, colors.black),
                ("LINEBELOW", (0, -1), (-1, -1), 1.3, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    _tw, th = tbl.wrapOn(c, content_w, 400)
    tbl.drawOn(c, left_x, y - th)

    c.setFont("Times-Roman", 8.5)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawCentredString(pw / 2.0, 28, "IEEE Academic Layout Benchmark — Page 2")
    c.save()
    return path


def generate_textbook_math_callout(out_path: str | Path) -> Path:
    """Create a 2-page 1-column math/CS textbook chapter with shaded callouts, code block, and equations."""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _gothic, myungjo = _register_korean_fonts()
    math_font = myungjo if myungjo != "Times-Roman" else "Times-Italic"
    pw, ph = letter
    margin = 64.0
    content_w = pw - 2 * margin  # 484 pt

    title_style = ParagraphStyle("ChTitle", fontName="Helvetica-Bold", fontSize=16, leading=21)
    h1_style = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=12.5, leading=16)
    body_style = ParagraphStyle("Body", fontName="Times-Roman", fontSize=10.5, leading=14.5, alignment=TA_JUSTIFY)
    box_title_style = ParagraphStyle("BoxTitle", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=colors.HexColor("#1E3A8A"))
    box_body_style = ParagraphStyle("BoxBody", fontName="Times-Roman", fontSize=10, leading=13.5)
    list_style = ParagraphStyle("List", fontName="Times-Roman", fontSize=10, leading=14, leftIndent=14)

    c = canvas.Canvas(str(path), pagesize=letter)

    # ---------------- Page 1 ----------------
    y = ph - margin
    y = _draw_para(c, "Chapter 2. Convex Optimization Foundations", title_style, margin, y, content_w)
    y -= 14

    y = _draw_para(
        c,
        "Convex optimization provides a unified mathematical framework for analyzing continuous minimization "
        "problems. In contrast to general non-convex optimization, every local minimum of a convex function "
        "over a convex set is guaranteed to be a <b>global minimum</b>.",
        body_style,
        margin,
        y,
        content_w,
    )
    y -= 14

    # Callout Box 1: Definition 2.1 (light blue shaded rect + left accent line)
    box1_h = 84.0
    box1_y0 = y - box1_h
    c.setFillColor(colors.HexColor("#EEF4FA"))
    c.rect(margin, box1_y0, content_w, box1_h, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#2563EB"))
    c.setLineWidth(3.0)
    c.line(margin, box1_y0, margin, box1_y0 + box1_h)

    by = y - 10
    by = _draw_para(c, "Definition 2.1 (Convex Function)", box_title_style, margin + 12, by, content_w - 22)
    by -= 4
    _draw_para(
        c,
        "A function f : R<sup>n</sup> &rarr; R is <i>convex</i> if its domain is a convex set and for all "
        "x, y in dom f and θ &isin; [0, 1], f(θx + (1 − θ)y) &le; θf(x) + (1 − θ)f(y).",
        box_body_style,
        margin + 12,
        by,
        content_w - 22,
    )
    y = box1_y0 - 16

    y = _draw_para(c, "2.1 First-Order Optimality Condition", h1_style, margin, y, content_w)
    y -= 6
    y = _draw_para(
        c,
        "When f is differentiable, convexity yields a first-order lower bound constructed from the tangent "
        "hyperplane at any point x<sub>0</sub>:",
        body_style,
        margin,
        y,
        content_w,
    )
    y -= 10

    c.setFont(math_font, 10.5)
    c.drawCentredString(margin + content_w * 0.46, y - 14, "f(y) ≥ f(x₀) + ∇f(x₀)ᵀ (y - x₀)")
    c.setFont("Times-Roman", 10)
    c.drawRightString(margin + content_w, y - 14, "(2.1)")
    y -= 32

    # Callout Box 2: Theorem 2.2 (amber border)
    box2_h = 76.0
    box2_y0 = y - box2_h
    c.setFillColor(colors.HexColor("#FEF7E6"))
    c.setStrokeColor(colors.HexColor("#D97706"))
    c.setLineWidth(1.2)
    c.rect(margin, box2_y0, content_w, box2_h, fill=1, stroke=1)

    by = y - 10
    box2_title = ParagraphStyle("Box2Title", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=colors.HexColor("#92400E"))
    by = _draw_para(c, "Theorem 2.2 (Zero-Gradient Optimality)", box2_title, margin + 12, by, content_w - 22)
    by -= 4
    _draw_para(
        c,
        "If f is convex and differentiable over an unconstrained domain R<sup>n</sup>, then x<sup>*</sup> is a "
        "global minimizer if and only if grad f(x<sup>*</sup>) = 0.",
        box_body_style,
        margin + 12,
        by,
        content_w - 22,
    )

    c.showPage()

    # ---------------- Page 2 ----------------
    y = ph - margin
    y = _draw_para(c, "2.2 Gradient Descent Implementation", h1_style, margin, y, content_w)
    y -= 8
    y = _draw_para(
        c,
        "The following reference implementation illustrates fixed-step gradient descent for smooth objectives.",
        body_style,
        margin,
        y,
        content_w,
    )
    y -= 10

    code_lines = [
        "def gradient_descent(grad_fn, x0, lr=0.05, steps=100):",
        "    x = x0.copy()",
        "    for _ in range(steps):",
        "        x = x - lr * grad_fn(x)",
        "    return x",
    ]
    code_h = 84.0
    code_y0 = y - code_h
    c.setFillColor(colors.HexColor("#F1F5F9"))
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(0.8)
    c.rect(margin, code_y0, content_w, code_h, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Courier", 9.5)
    cy = y - 16
    for ln in code_lines:
        c.drawString(margin + 12, cy, ln)
        cy -= 14

    y = code_y0 - 18
    y = _draw_para(c, "Exercises", h1_style, margin, y, content_w)
    y -= 6
    for item in [
        "1. Prove that f(x) = x<sup>2</sup> + e<sup>x</sup> is strictly convex on R.",
        "2. Derive the step-size bound 0 &lt; &eta; &lt; 2 / L for L-smooth convex functions.",
        "3. Implement backtracking line search and compare convergence curves against fixed step size.",
    ]:
        y = _draw_para(c, item, list_style, margin, y, content_w)
        y -= 4

    c.save()
    return path


def generate_korean_academic(out_path: str | Path) -> Path:
    """Create a 2-page Korean+English academic paper with 2-column body and Korean merged-header table."""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    gothic, myungjo = _register_korean_fonts()

    pw, ph = A4  # 595.28 x 841.89 pt
    margin = 54.0
    content_w = pw - 2 * margin
    gutter = 18.0
    col_w = (content_w - gutter) / 2.0
    left_x = margin
    right_x = margin + col_w + gutter

    title_style = ParagraphStyle("KoTitle", fontName=gothic, fontSize=15, leading=21, alignment=TA_CENTER)
    author_style = ParagraphStyle("KoAuthor", fontName=gothic, fontSize=9.5, leading=13, alignment=TA_CENTER)
    h1_style = ParagraphStyle("KoH1", fontName=gothic, fontSize=11, leading=15, alignment=TA_LEFT)
    body_style = ParagraphStyle("KoBody", fontName=myungjo, fontSize=9.5, leading=14.5, alignment=TA_LEFT)
    cap_style = ParagraphStyle("KoCap", fontName=gothic, fontSize=9, leading=12.5, alignment=TA_CENTER)

    c = canvas.Canvas(str(path), pagesize=A4)

    # ---------------- Page 1 ----------------
    y = ph - margin
    y = _draw_para(c, "학술 문서 PDF의 Google Docs 레이아웃 보존 변환 기법", title_style, left_x, y, content_w)
    y -= 6
    y = _draw_para(c, "김민준 · 이서연 (한국AI문서연구소)", author_style, left_x, y, content_w)
    y -= 10
    y = _draw_para(
        c,
        "요약 (Abstract): 학술 논문과 교재 PDF는 다단 편집, 수식, 병합된 표 및 벡터 도표를 포함하고 있어 "
        "단순 텍스트 추출 방식으로는 원본의 시각적 구조를 유지할 수 없다. 본 논문에서는 로컬 AI 레이아웃 분석과 "
        "Google Docs 친화적 OOXML 컴파일러를 결합하여 한글·영문 혼합 학술 문서를 안정적으로 변환하는 방법을 제안한다.",
        body_style,
        left_x,
        y,
        content_w,
    )
    y -= 16

    col_top = y
    ly = _draw_para(c, "1. 서론", h1_style, left_x, col_top, col_w)
    ly -= 5
    ly = _draw_para(
        c,
        "국내외 대학 및 연구기관에서는 PDF 문서를 Google Docs로 변환하여 공동 연구를 진행하는 사례가 증가하고 있다. "
        "그러나 기존의 무료 변환 도구는 2단 본문의 읽기 순서를 뒤섞거나 부동 텍스트 상자를 남발하여 "
        "Google Docs 임포트 과정에서 레이아웃이 심각하게 붕괴되는 한계를 보인다.",
        body_style,
        left_x,
        ly,
        col_w,
    )
    ly -= 8
    ly = _draw_para(
        c,
        "특히 한국어 학술 문서는 명조·고딕 계열 폰트 미임베딩이나 CMap 손상으로 인해 글자가 깨지는 경우가 빈번하다. "
        "이를 해결하기 위해 사전 진단 단계에서 깨진 페이지를 자동 탐지하고 선택적 로컬 OCR을 수행한다.",
        body_style,
        left_x,
        ly,
        col_w,
    )

    ry = _draw_para(c, "2. 제안 아키텍처", h1_style, right_x, col_top, col_w)
    ry -= 5
    ry = _draw_para(
        c,
        "제안하는 변환 엔진은 완전 로컬 오픈소스 파이프라인으로 동작하며 외부 유료 서버로 문서를 전송하지 않는다. "
        "1단 제목과 2단 본문, 그리고 2단을 가로지르는 표는 연속 구역 나누기(Continuous Section Break)로 자동 분할된다.",
        body_style,
        right_x,
        ry,
        col_w,
    )
    ry -= 8
    ry = _draw_para(
        c,
        "또한 복잡한 수식은 420 DPI 고해상도 이미지로 크롭해 2열 테두리 없는 표에 수식 번호와 함께 정렬하고, "
        "대체 텍스트(Alt Text)에 LaTeX 원문을 보존하여 재편집 가능성을 확보한다.",
        body_style,
        right_x,
        ry,
        col_w,
    )

    c.showPage()

    # ---------------- Page 2: Wide Korean Merged Table + Conclusion ----------------
    y = ph - margin
    y = _draw_para(c, "표 1. 한국어 학술 문서 변환 방식별 레이아웃 보존 비교", cap_style, left_x, y, content_w)
    y -= 8

    tbl_data = [
        ["변환 방식", "구조 보존 지표", "", "비고"],
        ["", "2단 정렬 정확도", "한글 폰트 안정성", "수식 LaTeX 보존"],
        ["단순 텍스트 추출", "32.0%", "낮음", "미지원"],
        ["Google Drive 직접 변환", "54.5%", "보통", "소실 빈번"],
        ["제안 방식 (Docs-Safe)", "96.8%", "높음 (Noto KR)", "Alt Text 보존"],
    ]
    tbl = Table(tbl_data, colWidths=[145, 110, 115, 117])
    tbl.setStyle(
        TableStyle(
            [
                ("SPAN", (1, 0), (2, 0)),
                ("SPAN", (0, 0), (0, 1)),
                ("SPAN", (3, 0), (3, 1)),
                ("FONTNAME", (0, 0), (-1, 1), gothic),
                ("FONTNAME", (0, 2), (-1, -1), myungjo),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEABOVE", (0, 0), (-1, 0), 1.2, colors.black),
                ("LINEBELOW", (1, 0), (2, 0), 0.6, colors.grey),
                ("LINEBELOW", (0, 1), (-1, 1), 0.8, colors.black),
                ("LINEBELOW", (0, -1), (-1, -1), 1.2, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    _tw, th = tbl.wrapOn(c, content_w, 400)
    tbl.drawOn(c, left_x, y - th)

    y = y - th - 20
    y = _draw_para(c, "3. 결론 및 향후 과제", h1_style, left_x, y, content_w)
    y -= 6
    _draw_para(
        c,
        "본 연구에서 구현한 Docs-Safe OOXML 컴파일러는 Google Docs 임포트 시 발생하는 부동 텍스트 상자 붕괴와 "
        "폰트 대체 밀림 현상을 효과적으로 억제한다. 향후 연구에서는 Drive API 실제 렌더링 비교를 통한 자동 미세 보정 루프를 "
        "통합할 예정이다.",
        body_style,
        left_x,
        y,
        content_w,
    )

    c.save()
    return path


def generate_all_samples(output_dir: str | Path) -> dict[str, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    return {
        "academic_2col_en": generate_academic_2col_en(out / "academic_2col_en.pdf"),
        "textbook_math_callout": generate_textbook_math_callout(out / "textbook_math_callout.pdf"),
        "korean_academic": generate_korean_academic(out / "korean_academic.pdf"),
    }
