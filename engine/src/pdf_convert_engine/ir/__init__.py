"""Canonical Academic Document Intermediate Representation (IR)."""

from pdf_convert_engine.ir.schema import (
    Alignment,
    BBox,
    BlockType,
    CalloutBoxBlock,
    DocumentBlock,
    DocumentIR,
    FigureBlock,
    FormulaBlock,
    LayoutBand,
    MarginBox,
    PageIR,
    PreflightReport,
    TableBlock,
    TableCellIR,
    TextBlock,
    TextRun,
)

__all__ = [
    "Alignment",
    "BBox",
    "BlockType",
    "CalloutBoxBlock",
    "DocumentBlock",
    "DocumentIR",
    "FigureBlock",
    "FormulaBlock",
    "LayoutBand",
    "MarginBox",
    "PageIR",
    "PreflightReport",
    "TableBlock",
    "TableCellIR",
    "TextBlock",
    "TextRun",
]
