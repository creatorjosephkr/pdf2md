"""Academic Markdown (.md) Compiler: compiles AcademicDocumentIR -> Obsidian/Notion/GitHub-ready Markdown."""

from __future__ import annotations

import base64
import html
import re
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from pdf_convert_engine.ir.schema import (
    BlockType,
    CalloutBoxBlock,
    DocumentBlock,
    DocumentIR,
    FigureBlock,
    FormulaBlock,
    TableBlock,
    TableCellIR,
    TextBlock,
    TextRun,
)

_TRAILING_EQ_NUM_RE = re.compile(
    r"(?:\\quad|\\qquad|\s)*(?:\(\s*\d+(?:\.\d+)*\s*\)|\[\s*\d+(?:\.\d+)*\s*\])\s*$"
)


class MarkdownOptions(BaseModel):
    image_mode: Literal["folder", "base64", "none"] = "folder"
    complex_table_html: bool = True
    include_frontmatter: bool = True
    include_page_comments: bool = False
    callout_style: Literal["github_obsidian", "blockquote"] = "github_obsidian"


class MarkdownCompileResult(BaseModel):
    output_path: str | None = None
    assets_dir: str | None = None
    assets_copied: int = 0
    markdown_text: str
    char_count: int = 0
    headings: int = 0
    tables: int = 0
    figures: int = 0
    formulas: int = 0
    callouts: int = 0


def _format_run(run: TextRun) -> str:
    txt = run.text
    if not txt:
        return ""
    if not txt.strip():
        return txt

    lead_len = len(txt) - len(txt.lstrip())
    trail_len = len(txt) - len(txt.rstrip())
    lead = txt[:lead_len]
    trail = txt[len(txt) - trail_len :] if trail_len else ""
    core = txt.strip()

    if run.is_code:
        tick = "``" if "`" in core else "`"
        return f"{lead}{tick}{core}{tick}{trail}"

    if run.superscript:
        return f"{lead}<sup>{html.escape(core)}</sup>{trail}"
    if run.subscript:
        return f"{lead}<sub>{html.escape(core)}</sub>{trail}"

    if run.bold and run.italic:
        core = f"***{core}***"
    elif run.bold:
        core = f"**{core}**"
    elif run.italic:
        core = f"*{core}*"

    if run.underline and not run.bold and not run.italic:
        core = f"<u>{core}</u>"

    return f"{lead}{core}{trail}"


def _format_runs_text(runs: list[TextRun], fallback: str = "") -> str:
    if not runs:
        return fallback.strip()
    out = "".join(_format_run(r) for r in runs).strip()
    return out or fallback.strip()


def _clean_latex_and_tag(latex: str, eq_num: str | None) -> str:
    cleaned = latex.strip()
    if cleaned.startswith("$$") and cleaned.endswith("$$"):
        cleaned = cleaned[2:-2].strip()
    elif cleaned.startswith("$") and cleaned.endswith("$"):
        cleaned = cleaned[1:-1].strip()

    if eq_num:
        cleaned = _TRAILING_EQ_NUM_RE.sub("", cleaned).strip()
        num_bare = eq_num.strip("()[] ")
        if num_bare:
            return f"{cleaned} \\tag{{{num_bare}}}"
    return cleaned


def _classify_callout_admonition(title: str | None, first_line: str) -> str:
    sample = f"{title or ''} {first_line}".lower()
    if any(k in sample for k in ("theorem", "lemma", "corollary", "proposition", "정리", "보조정리")):
        return "IMPORTANT"
    if any(k in sample for k in ("example", "tip", "hint", "예제", "참고")):
        return "TIP"
    if any(k in sample for k in ("warning", "caution", "주의", "경고")):
        return "WARNING"
    return "NOTE"


class MarkdownCompiler:
    """Compiles canonical AcademicDocumentIR into structured Academic Markdown."""

    def compile(
        self,
        ir: DocumentIR,
        output_path: str | Path | None = None,
        options: MarkdownOptions | None = None,
    ) -> MarkdownCompileResult:
        opts = options or MarkdownOptions()
        out_file = Path(output_path).resolve() if output_path is not None else None
        assets_dir: Path | None = None
        if out_file is not None and opts.image_mode == "folder":
            assets_dir = out_file.parent / f"{out_file.stem}_assets"

        stats = {
            "headings": 0,
            "tables": 0,
            "figures": 0,
            "formulas": 0,
            "callouts": 0,
            "assets_copied": 0,
        }
        copied_map: dict[str, str] = {}

        def resolve_image_url(src_path_str: str | None) -> str | None:
            if not src_path_str or opts.image_mode == "none":
                return None
            src_path = Path(src_path_str)
            if not src_path.exists():
                return None

            if opts.image_mode == "base64":
                b64 = base64.b64encode(src_path.read_bytes()).decode("ascii")
                return f"data:image/png;base64,{b64}"

            # folder mode
            if out_file is not None and assets_dir is not None:
                if str(src_path) not in copied_map:
                    assets_dir.mkdir(parents=True, exist_ok=True)
                    dest = assets_dir / src_path.name
                    if src_path.resolve() != dest.resolve():
                        shutil.copy2(src_path, dest)
                    copied_map[str(src_path)] = f"./{assets_dir.name}/{src_path.name}"
                    stats["assets_copied"] += 1
                return copied_map[str(src_path)]

            # In-memory preview without output file path
            return f"./assets/{src_path.name}"

        sections: list[str] = []

        # Optional YAML frontmatter
        if opts.include_frontmatter:
            first_title = self._find_title(ir)
            safe_title = (first_title or Path(ir.source_path).stem).replace('"', "'")
            fm_lines = [
                "---",
                f'title: "{safe_title}"',
                f'source: "{Path(ir.source_path).name}"',
                f"pages: {len(ir.pages)}",
                f'language: "{ir.preflight.detected_language}"',
                f"columns: {ir.preflight.detected_columns}",
                "---",
            ]
            sections.append("\n".join(fm_lines))

        for page in ir.pages:
            if opts.include_page_comments:
                sections.append(f"<!-- Page {page.page_no} -->")

            for band in page.bands:
                if band.columns == 2:
                    ordered = list(band.left_column_blocks) + list(band.right_column_blocks)
                else:
                    ordered = list(band.blocks)

                for blk in ordered:
                    rendered = self._render_block(blk, opts, stats, resolve_image_url)
                    if rendered:
                        sections.append(rendered)

            if page.footnotes:
                fn_lines = ["---"]
                for fn in page.footnotes:
                    fn_txt = _format_runs_text(fn.runs, fn.plain_text)
                    if fn_txt:
                        fn_lines.append(f"> {fn_txt}")
                if len(fn_lines) > 1:
                    sections.append("\n".join(fn_lines))

        markdown_text = "\n\n".join(sections).strip() + "\n"

        if out_file is not None:
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(markdown_text, encoding="utf-8")

        return MarkdownCompileResult(
            output_path=str(out_file) if out_file else None,
            assets_dir=str(assets_dir) if (assets_dir and assets_dir.exists()) else None,
            assets_copied=stats["assets_copied"],
            markdown_text=markdown_text,
            char_count=len(markdown_text),
            headings=stats["headings"],
            tables=stats["tables"],
            figures=stats["figures"],
            formulas=stats["formulas"],
            callouts=stats["callouts"],
        )

    def _find_title(self, ir: DocumentIR) -> str | None:
        for page in ir.pages:
            for band in page.bands:
                for blk in band.blocks:
                    if isinstance(blk, TextBlock) and blk.block_type == BlockType.TITLE:
                        return blk.plain_text.strip()
        return None

    def _render_block(
        self,
        blk: DocumentBlock,
        opts: MarkdownOptions,
        stats: dict[str, int],
        resolve_image_url,
    ) -> str | None:
        if isinstance(blk, TextBlock):
            return self._render_text_block(blk, stats)
        if isinstance(blk, TableBlock):
            stats["tables"] += 1
            return self._render_table_block(blk, opts)
        if isinstance(blk, FormulaBlock):
            stats["formulas"] += 1
            return self._render_formula_block(blk, resolve_image_url)
        if isinstance(blk, FigureBlock):
            stats["figures"] += 1
            return self._render_figure_block(blk, resolve_image_url)
        if isinstance(blk, CalloutBoxBlock):
            stats["callouts"] += 1
            return self._render_callout_block(blk, opts)
        return None

    def _render_text_block(self, blk: TextBlock, stats: dict[str, int]) -> str | None:
        if blk.block_type == BlockType.CODE_BLOCK:
            code = blk.plain_text.strip("\n")
            if not code:
                return None
            lang = "python" if any(tok in code for tok in ("def ", "import ", "return ")) else ""
            return f"```{lang}\n{code}\n```"

        text = _format_runs_text(blk.runs, blk.plain_text)
        if not text:
            return None

        if blk.block_type == BlockType.TITLE:
            stats["headings"] += 1
            return f"# {blk.plain_text.strip()}"

        if blk.block_type == BlockType.HEADING:
            stats["headings"] += 1
            lvl = max(2, min(4, (blk.heading_level or 1) + 1))
            return f"{'#' * lvl} {blk.plain_text.strip()}"

        if blk.block_type == BlockType.CAPTION:
            plain = blk.plain_text.strip()
            return f"*{plain}*"

        if blk.block_type == BlockType.LIST_ITEM:
            marker = (blk.list_marker or "").strip()
            if marker and not text.startswith(marker):
                return f"{marker} {text}"
            if re.match(r"^(\d+[.)]|[-*•])\s+", text):
                return re.sub(r"^•\s+", "- ", text)
            return f"- {text}"

        return text

    def _render_formula_block(self, blk: FormulaBlock, resolve_image_url) -> str:
        latex = (blk.latex or "").strip()
        if latex:
            expr = _clean_latex_and_tag(latex, blk.equation_number)
            return f"$$\n{expr}\n$$"

        img_url = resolve_image_url(blk.image_path)
        num_suffix = f" {blk.equation_number}" if blk.equation_number else ""
        if img_url:
            return f"![Equation{num_suffix}]({img_url})"

        raw = (blk.raw_text or "").strip()
        return f"$$\n{raw}\n$$" if raw else ""

    def _render_figure_block(self, blk: FigureBlock, resolve_image_url) -> str:
        alt = (blk.alt_text or blk.caption_text or "Figure").replace("\n", " ").strip()
        img_url = resolve_image_url(blk.image_path)
        if img_url:
            return f"![{alt}]({img_url})"
        return f"*[{alt}]*"

    def _render_table_block(self, blk: TableBlock, opts: MarkdownOptions) -> str:
        num_rows = max(1, blk.num_rows)
        num_cols = max(1, blk.num_cols)
        has_merges = any(c.row_span > 1 or c.col_span > 1 for c in blk.cells)

        cell_map: dict[tuple[int, int], TableCellIR] = {}
        covered: set[tuple[int, int]] = set()
        for c in sorted(blk.cells, key=lambda x: (x.row, x.col)):
            if (c.row, c.col) in covered:
                continue
            cell_map[(c.row, c.col)] = c
            for rr in range(c.row, min(num_rows, c.row + c.row_span)):
                for cc in range(c.col, min(num_cols, c.col + c.col_span)):
                    covered.add((rr, cc))

        if has_merges and opts.complex_table_html:
            return self._render_html_table(num_rows, num_cols, cell_map, covered)

        # Clean GFM pipe table
        rows_txt: list[list[str]] = []
        for r in range(num_rows):
            row_vals: list[str] = []
            for c in range(num_cols):
                cell = cell_map.get((r, c))
                val = _format_runs_text(cell.runs, cell.text) if cell else ""
                val = val.replace("|", "\\|").replace("\n", " ")
                row_vals.append(val)
            rows_txt.append(row_vals)

        lines = [
            "| " + " | ".join(rows_txt[0]) + " |",
            "| " + " | ".join("---" for _ in range(num_cols)) + " |",
        ]
        for row_vals in rows_txt[1:]:
            lines.append("| " + " | ".join(row_vals) + " |")
        return "\n".join(lines)

    def _render_html_table(
        self,
        num_rows: int,
        num_cols: int,
        cell_map: dict[tuple[int, int], TableCellIR],
        covered: set[tuple[int, int]],
    ) -> str:
        header_row_limit = 0
        for r in range(num_rows):
            row_cells = [cell_map[(r, c)] for c in range(num_cols) if (r, c) in cell_map]
            if row_cells and any(c.is_header for c in row_cells):
                header_row_limit = r + 1
            else:
                break

        lines = ["<table>"]
        if header_row_limit > 0:
            lines.append("  <thead>")
            for r in range(header_row_limit):
                lines.append(self._html_table_row(r, num_cols, cell_map, covered, tag="th"))
            lines.append("  </thead>")

        lines.append("  <tbody>")
        for r in range(header_row_limit, num_rows):
            lines.append(self._html_table_row(r, num_cols, cell_map, covered, tag="td"))
        lines.append("  </tbody>")
        lines.append("</table>")
        return "\n".join(lines)

    def _html_table_row(
        self,
        row_idx: int,
        num_cols: int,
        cell_map: dict[tuple[int, int], TableCellIR],
        covered: set[tuple[int, int]],
        tag: str,
    ) -> str:
        cells_html: list[str] = []
        for c in range(num_cols):
            cell = cell_map.get((row_idx, c))
            if cell is None:
                if (row_idx, c) in covered:
                    continue
                cells_html.append(f"<{tag}></{tag}>")
                continue
            attrs = ""
            if cell.col_span > 1:
                attrs += f' colspan="{cell.col_span}"'
            if cell.row_span > 1:
                attrs += f' rowspan="{cell.row_span}"'
            escaped = html.escape(cell.text.strip()).replace("\n", "<br/>")
            cells_html.append(f"<{tag}{attrs}>{escaped}</{tag}>")
        return "    <tr>" + "".join(cells_html) + "</tr>"

    def _render_callout_block(self, blk: CalloutBoxBlock, opts: MarkdownOptions) -> str:
        inner_parts: list[str] = []
        for inner in blk.blocks:
            txt = _format_runs_text(inner.runs, inner.plain_text)
            if not txt:
                continue
            if inner.block_type == BlockType.HEADING and not txt.startswith("**"):
                inner_parts.append(f"**{inner.plain_text.strip()}**")
            else:
                inner_parts.append(txt)

        if not inner_parts:
            return ""

        first_line = inner_parts[0]
        body_lines = "\n\n".join(inner_parts).splitlines()

        if opts.callout_style == "github_obsidian":
            kind = _classify_callout_admonition(blk.title, first_line)
            quoted = [f"> [!{kind}]"]
            for ln in body_lines:
                quoted.append(f"> {ln}" if ln else ">")
            return "\n".join(quoted)

        return "\n".join(f"> {ln}" if ln else ">" for ln in body_lines)
