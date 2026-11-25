"""Base classes and options for PDF parser adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel

from pdf_convert_engine.ir.schema import DocumentIR, PreflightReport


class ParseOptions(BaseModel):
    page_range: tuple[int, int] | None = None
    force_ocr: bool = False
    enable_formula_enrichment: bool = True
    crop_dpi: int = 350
    formula_crop_dpi: int = 420
    assets_dir: Path | None = None


class ParserAdapter(ABC):
    """Abstract interface for PDF -> AcademicDocumentIR adapters."""

    name: str = "base"

    @abstractmethod
    def parse(
        self,
        pdf_path: Path,
        preflight: PreflightReport,
        options: ParseOptions,
    ) -> DocumentIR:
        """Parse a PDF document into canonical AcademicDocumentIR."""
