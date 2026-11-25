"""Pydantic v2 API request and response schemas for the Markdown Sidecar server."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from pdf_convert_engine.ir.schema import DocumentIR, PreflightReport


class HardwareInfo(BaseModel):
    os: str
    arch: str
    accelerator: Literal["mps", "cuda", "cpu"]
    accelerator_label: str
    python_version: str
    docling_version: str


class ModelStatusItem(BaseModel):
    id: str
    name: str
    role: str
    license: str
    installed: bool
    size_mb: float
    cache_path: str | None = None
    description: str


class ModelsOverviewResponse(BaseModel):
    hardware: HardwareInfo
    models: list[ModelStatusItem]
    warmup_status: Literal["idle", "running", "completed", "failed"] = "idle"
    warmup_message: str | None = None


class OpenPathRequest(BaseModel):
    pdf_path: str
    pages: str | None = None
    display_name: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    file_name: str
    pdf_path: str
    preflight: PreflightReport


class ConvertRequest(BaseModel):
    session_id: str
    parser: Literal["docling", "fallback"] = "docling"
    image_mode: Literal["folder", "base64", "none"] = "folder"
    complex_table_html: bool = True
    include_frontmatter: bool = True
    force_ocr: bool = False
    enable_formula_enrichment: bool = True
    pages: str | None = None


class ReconvertPageRequest(BaseModel):
    page_no: int = Field(ge=1)
    force_ocr: bool = True
    parser: Literal["docling", "fallback"] | None = None


class MarkdownStats(BaseModel):
    char_count: int = 0
    headings: int = 0
    tables: int = 0
    figures: int = 0
    formulas: int = 0
    callouts: int = 0
    assets_copied: int = 0


class MarkdownPreviewResponse(BaseModel):
    markdown: str
    stats: MarkdownStats


class ExportMarkdownRequest(BaseModel):
    destination_path: str
    image_mode: Literal["folder", "base64", "none"] = "folder"
    override_markdown: str | None = None


class ExportRtfRequest(BaseModel):
    destination_path: str
    override_markdown: str | None = None


class DownloadRtfRequest(BaseModel):
    override_markdown: str | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    session_id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress_pct: int = Field(ge=0, le=100)
    stage: str
    error: str | None = None
    options: ConvertRequest
    markdown: str | None = None
    stats: MarkdownStats | None = None
    ir: DocumentIR | None = None
    md_path: str | None = None


class UpdateCheckResponse(BaseModel):
    status: Literal["update_available", "up_to_date", "no_release", "error"]
    current_version: str
    latest_version: str | None = None
    has_update: bool = False
    release_name: str | None = None
    release_notes: str | None = None
    published_at: str | None = None
    release_url: str
    download_url: str | None = None
    repo_url: str
    checked_at: str
    message: str
