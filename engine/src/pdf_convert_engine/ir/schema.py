"""Canonical Pydantic v2 schema for AcademicDocumentIR.

All coordinates use TOPLEFT origin in PDF points (1 pt = 1/72 inch).
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator


class BBox(BaseModel):
    """Axis-aligned bounding box in TOPLEFT origin PDF points."""

    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def _normalize_bounds(self) -> "BBox":
        if self.x1 < self.x0:
            self.x0, self.x1 = self.x1, self.x0
        if self.y1 < self.y0:
            self.y0, self.y1 = self.y1, self.y0
        return self

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def area(self) -> float:
        return self.width * self.height

    def intersects(self, other: "BBox", tol: float = 0.0) -> bool:
        return not (
            self.x1 + tol < other.x0
            or other.x1 + tol < self.x0
            or self.y1 + tol < other.y0
            or other.y1 + tol < self.y0
        )

    def contains(self, other: "BBox", tol: float = 2.0) -> bool:
        return (
            self.x0 - tol <= other.x0
            and self.y0 - tol <= other.y0
            and self.x1 + tol >= other.x1
            and self.y1 + tol >= other.y1
        )

    def intersection_area(self, other: "BBox") -> float:
        ix0 = max(self.x0, other.x0)
        iy0 = max(self.y0, other.y0)
        ix1 = min(self.x1, other.x1)
        iy1 = min(self.y1, other.y1)
        if ix1 <= ix0 or iy1 <= iy0:
            return 0.0
        return (ix1 - ix0) * (iy1 - iy0)

    def intersection_ratio(self, other: "BBox") -> float:
        """Fraction of `self`'s area overlapped by `other`."""
        if self.area <= 0.0:
            return 0.0
        return self.intersection_area(other) / self.area


class MarginBox(BaseModel):
    """Page margins in PDF points."""

    top: float = 72.0
    bottom: float = 72.0
    left: float = 72.0
    right: float = 72.0


class Alignment(str, Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"


class BlockType(str, Enum):
    TITLE = "title"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    FORMULA = "formula"
    FIGURE = "figure"
    CAPTION = "caption"
    CALLOUT_BOX = "callout_box"
    CODE_BLOCK = "code_block"
    FOOTNOTE = "footnote"
    PAGE_HEADER = "page_header"
    PAGE_FOOTER = "page_footer"


class TextRun(BaseModel):
    """Styled inline text span."""

    text: str
    font_name: str | None = None
    font_size_pt: float = 10.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    superscript: bool = False
    subscript: bool = False
    color_hex: str | None = None
    is_code: bool = False
    is_math: bool = False


class _BaseBlock(BaseModel):
    id: str
    page_no: int = Field(ge=1)
    bbox: BBox
    column_span: Literal["auto", "single", "full"] = "auto"
    source: Literal["native", "ocr", "hybrid"] = "native"


class TextBlock(_BaseBlock):
    block_type: Literal[
        BlockType.TITLE,
        BlockType.HEADING,
        BlockType.PARAGRAPH,
        BlockType.CAPTION,
        BlockType.LIST_ITEM,
        BlockType.FOOTNOTE,
        BlockType.PAGE_HEADER,
        BlockType.PAGE_FOOTER,
        BlockType.CODE_BLOCK,
    ] = BlockType.PARAGRAPH
    runs: list[TextRun] = Field(default_factory=list)
    plain_text: str = ""
    alignment: Alignment = Alignment.LEFT
    heading_level: int | None = None
    list_marker: str | None = None
    line_spacing: float | None = None
    space_before_pt: float | None = None
    space_after_pt: float | None = None
    keep_with_next: bool = False


class TableCellIR(BaseModel):
    row: int = Field(ge=0)
    col: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    col_span: int = Field(default=1, ge=1)
    text: str = ""
    runs: list[TextRun] = Field(default_factory=list)
    is_header: bool = False
    alignment: Alignment = Alignment.LEFT
    fill_hex: str | None = None


class TableBlock(_BaseBlock):
    block_type: Literal[BlockType.TABLE] = BlockType.TABLE
    num_rows: int = Field(ge=1)
    num_cols: int = Field(ge=1)
    col_widths_pt: list[float] = Field(default_factory=list)
    cells: list[TableCellIR] = Field(default_factory=list)
    style_hint: Literal["booktabs", "grid", "borderless"] = "booktabs"
    caption_block_id: str | None = None


class FormulaBlock(_BaseBlock):
    block_type: Literal[BlockType.FORMULA] = BlockType.FORMULA
    latex: str | None = None
    raw_text: str = ""
    equation_number: str | None = None
    is_display: bool = True
    image_path: str | None = None
    image_width_pt: float | None = None
    image_height_pt: float | None = None


class FigureBlock(_BaseBlock):
    block_type: Literal[BlockType.FIGURE] = BlockType.FIGURE
    image_path: str
    image_width_pt: float = Field(gt=0)
    image_height_pt: float = Field(gt=0)
    caption_text: str | None = None
    alt_text: str | None = None
    keep_with_next: bool = False


class CalloutBoxBlock(_BaseBlock):
    block_type: Literal[BlockType.CALLOUT_BOX] = BlockType.CALLOUT_BOX
    title: str | None = None
    blocks: list[TextBlock] = Field(default_factory=list)
    fill_hex: str = "F3F6FA"
    border_hex: str = "3B6EA5"
    border_width_pt: float = 1.0
    accent_left_only: bool = False


DocumentBlock = Annotated[
    Union[TextBlock, TableBlock, FormulaBlock, FigureBlock, CalloutBoxBlock],
    Field(discriminator="block_type"),
]


class LayoutBand(BaseModel):
    """Contiguous vertical region on a page with uniform column count (1 or 2)."""

    columns: int = Field(default=1, ge=1, le=2)
    gutter_pt: float = 18.0
    blocks: list[DocumentBlock] = Field(default_factory=list)
    left_column_blocks: list[DocumentBlock] = Field(default_factory=list)
    right_column_blocks: list[DocumentBlock] = Field(default_factory=list)


class PageIR(BaseModel):
    page_no: int = Field(ge=1)
    width_pt: float = Field(gt=0)
    height_pt: float = Field(gt=0)
    margins: MarginBox = Field(default_factory=MarginBox)
    is_scanned: bool = False
    has_broken_unicode: bool = False
    bands: list[LayoutBand] = Field(default_factory=list)
    headers: list[TextBlock] = Field(default_factory=list)
    footers: list[TextBlock] = Field(default_factory=list)
    footnotes: list[TextBlock] = Field(default_factory=list)


class PreflightReport(BaseModel):
    file_path: str
    page_count: int = Field(ge=0)
    page_sizes_pt: list[tuple[float, float]] = Field(default_factory=list)
    digital_pages: int = 0
    scanned_pages: int = 0
    broken_cmap_pages: list[int] = Field(default_factory=list)
    detected_columns: int = 1
    detected_language: Literal["ko", "en", "mixed", "other"] = "en"
    fonts_found: list[str] = Field(default_factory=list)
    estimated_margins_pt: MarginBox = Field(default_factory=MarginBox)
    recommended_ocr: bool = False
    warnings: list[str] = Field(default_factory=list)


class DocumentIR(BaseModel):
    source_path: str
    parser_name: str
    preflight: PreflightReport
    pages: list[PageIR] = Field(default_factory=list)
    assets_dir: str | None = None
