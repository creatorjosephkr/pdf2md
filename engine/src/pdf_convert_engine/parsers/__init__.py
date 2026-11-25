"""Parser adapters for Academic PDF -> AcademicDocumentIR."""

from pdf_convert_engine.parsers.base import ParseOptions, ParserAdapter
from pdf_convert_engine.parsers.column_planner import plan_page_bands
from pdf_convert_engine.parsers.docling_adapter import DoclingAdapter
from pdf_convert_engine.parsers.fallback_adapter import FallbackHeuristicAdapter


def get_parser(name: str = "docling") -> ParserAdapter:
    normalized = name.strip().lower()
    if normalized == "docling":
        return DoclingAdapter()
    if normalized == "fallback":
        return FallbackHeuristicAdapter()
    raise ValueError(f"Unknown parser adapter: {name!r}. Choose 'docling' or 'fallback'.")


__all__ = [
    "DoclingAdapter",
    "FallbackHeuristicAdapter",
    "ParseOptions",
    "ParserAdapter",
    "get_parser",
    "plan_page_bands",
]
