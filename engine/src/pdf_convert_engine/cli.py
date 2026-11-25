"""CLI entrypoint for pdf-convert-engine (Academic PDF -> Markdown)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pdf_convert_engine.compiler import MarkdownCompiler, MarkdownOptions
from pdf_convert_engine.parsers import ParseOptions, get_parser
from pdf_convert_engine.preflight import analyze_pdf

app = typer.Typer(
    name="pdf-convert",
    help="Academic PDF -> Markdown (.md) local conversion engine.",
    add_completion=False,
)
console = Console()


def _parse_page_range(pages_str: str | None) -> tuple[int, int] | None:
    if not pages_str:
        return None
    s = pages_str.strip()
    if "-" in s:
        a, b = s.split("-", 1)
        return int(a.strip()), int(b.strip())
    n = int(s)
    return n, n


@app.command()
def diagnose(
    pdf_path: Path = typer.Argument(..., exists=True, readable=True, help="Input PDF file path"),
    pages: Optional[str] = typer.Option(None, "--pages", help="Page range e.g. '1-3' or '2'"),
) -> None:
    """Run fast Preflight diagnostics (scanned ratio, Korean CMap health, columns, fonts)."""
    prange = _parse_page_range(pages)
    report = analyze_pdf(pdf_path, page_range=prange)

    tbl = Table(title=f"Preflight Report: {pdf_path.name}", show_header=False)
    tbl.add_column("Metric", style="bold cyan")
    tbl.add_column("Value")
    tbl.add_row("Pages", str(report.page_count))
    tbl.add_row("Page Sizes (pt)", str(report.page_sizes_pt[:3]) + (" ..." if len(report.page_sizes_pt) > 3 else ""))
    tbl.add_row("Digital / Scanned", f"{report.digital_pages} digital / {report.scanned_pages} scanned")
    tbl.add_row("Broken CMap Pages", str(report.broken_cmap_pages or "None"))
    tbl.add_row("Detected Columns", str(report.detected_columns))
    tbl.add_row("Language", report.detected_language)
    tbl.add_row("OCR Recommended", str(report.recommended_ocr))
    tbl.add_row("Fonts Found", ", ".join(report.fonts_found[:8]) or "None")
    if report.warnings:
        tbl.add_row("Warnings", "\n".join(report.warnings))

    console.print(tbl)


@app.command()
def convert(
    pdf_path: Path = typer.Argument(..., exists=True, readable=True, help="Input PDF file path"),
    output: Path = typer.Option(..., "-o", "--output", help="Output .md file path"),
    parser_name: str = typer.Option("docling", "--parser", help="Parser backend: docling | fallback"),
    image_mode: Literal["folder", "base64", "none"] = typer.Option(
        "folder", "--image-mode", help="Image handling: folder | base64 | none"
    ),
    no_html_tables: bool = typer.Option(
        False, "--no-html-tables", help="Render merged tables as plain GFM pipes instead of HTML"
    ),
    no_frontmatter: bool = typer.Option(
        False, "--no-frontmatter", help="Omit YAML frontmatter at top of Markdown"
    ),
    force_ocr: bool = typer.Option(False, "--force-ocr", help="Force RapidOCR on all pages"),
    no_formula_enrichment: bool = typer.Option(
        False, "--no-formula-enrichment", help="Disable Docling formula LaTeX enrichment"
    ),
    pages: Optional[str] = typer.Option(None, "--pages", help="Page range e.g. '1-3'"),
    save_ir: Optional[Path] = typer.Option(None, "--save-ir", help="Optional path to dump AcademicDocumentIR JSON"),
) -> None:
    """Convert an Academic PDF directly to clean Academic Markdown (.md)."""
    prange = _parse_page_range(pages)
    preflight = analyze_pdf(pdf_path, page_range=prange)

    md_out = output if output.suffix.lower() in (".md", ".markdown") else output.with_suffix(".md")
    assets_dir = md_out.parent / f".{md_out.stem}_work_assets"

    parser = get_parser(parser_name)
    parse_opts = ParseOptions(
        page_range=prange,
        force_ocr=force_ocr,
        enable_formula_enrichment=not no_formula_enrichment,
        assets_dir=assets_dir,
    )
    ir = parser.parse(pdf_path, preflight, parse_opts)

    if save_ir is not None:
        save_ir.parent.mkdir(parents=True, exist_ok=True)
        save_ir.write_text(ir.model_dump_json(indent=2), encoding="utf-8")

    md_res = MarkdownCompiler().compile(
        ir,
        md_out,
        MarkdownOptions(
            image_mode=image_mode,
            complex_table_html=not no_html_tables,
            include_frontmatter=not no_frontmatter,
        ),
    )

    console.print(
        Panel(
            f"[bold green]Converted Markdown:[/bold green] {md_res.output_path}\n"
            f"Parser: {ir.parser_name} | Chars: {md_res.char_count} | Headings: {md_res.headings}\n"
            f"Tables: {md_res.tables} | Figures: {md_res.figures} | "
            f"Formulas: {md_res.formulas} | Callouts: {md_res.callouts}\n"
            f"Assets Copied: {md_res.assets_copied}"
            + (f" ({md_res.assets_dir})" if md_res.assets_dir else ""),
            title="Markdown Conversion Complete",
        )
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
