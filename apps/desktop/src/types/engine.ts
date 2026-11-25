export type ParserName = "docling" | "fallback";
export type MarkdownImageMode = "folder" | "base64" | "none";

export interface BBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface MarginBox {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

export type BlockType =
  | "title"
  | "heading"
  | "paragraph"
  | "list_item"
  | "table"
  | "formula"
  | "figure"
  | "caption"
  | "callout_box"
  | "code_block"
  | "footnote"
  | "page_header"
  | "page_footer";

export interface DocumentBlock {
  id: string;
  page_no: number;
  bbox: BBox;
  block_type: BlockType;
}

export interface LayoutBand {
  columns: 1 | 2;
  gutter_pt: number;
  blocks: DocumentBlock[];
}

export interface PageIR {
  page_no: number;
  width_pt: number;
  height_pt: number;
  margins: MarginBox;
  is_scanned: boolean;
  has_broken_unicode: boolean;
  bands: LayoutBand[];
}

export interface PreflightReport {
  file_path: string;
  page_count: number;
  page_sizes_pt: [number, number][];
  digital_pages: number;
  scanned_pages: number;
  broken_cmap_pages: number[];
  detected_columns: number;
  detected_language: "ko" | "en" | "mixed" | "other";
  fonts_found: string[];
  estimated_margins_pt: MarginBox;
  recommended_ocr: boolean;
  warnings: string[];
}

export interface DocumentIR {
  source_path: string;
  parser_name: string;
  preflight: PreflightReport;
  pages: PageIR[];
  assets_dir: string | null;
}

export interface ConvertRequest {
  session_id: string;
  parser: ParserName;
  image_mode: MarkdownImageMode;
  complex_table_html: boolean;
  include_frontmatter: boolean;
  force_ocr: boolean;
  enable_formula_enrichment: boolean;
  pages: string | null;
}

export interface ReconvertPageRequest {
  page_no: number;
  force_ocr: boolean;
  parser?: ParserName | null;
}

export interface MarkdownStats {
  char_count: number;
  headings: number;
  tables: number;
  figures: number;
  formulas: number;
  callouts: number;
  assets_copied: number;
}

export interface MarkdownPreviewResponse {
  markdown: string;
  stats: MarkdownStats;
}

export interface JobStatusResponse {
  job_id: string;
  session_id: string;
  status: "queued" | "running" | "completed" | "failed";
  progress_pct: number;
  stage: string;
  error: string | null;
  options: ConvertRequest;
  markdown: string | null;
  stats: MarkdownStats | null;
  ir: DocumentIR | null;
  md_path: string | null;
}

export interface HardwareInfo {
  os: string;
  arch: string;
  accelerator: "mps" | "cuda" | "cpu";
  accelerator_label: string;
  python_version: string;
  docling_version: string;
}

export interface ModelStatusItem {
  id: string;
  name: string;
  role: string;
  license: string;
  installed: boolean;
  size_mb: number;
  cache_path: string | null;
  description: string;
}

export interface ModelsOverviewResponse {
  hardware: HardwareInfo;
  models: ModelStatusItem[];
  warmup_status: "idle" | "running" | "completed" | "failed";
  warmup_message: string | null;
}

export interface SessionResponse {
  session_id: string;
  file_name: string;
  pdf_path: string;
  preflight: PreflightReport;
}

export interface HealthResponse {
  status: string;
  version: string;
  hardware: HardwareInfo;
}

export interface AppMeta {
  os: string;
  arch: string;
  version: string;
  is_tauri: boolean;
}

export interface SidecarStatus {
  phase: "idle" | "bootstrapping" | "starting" | "running" | "error";
  message: string;
  log_path: string | null;
  last_log: string | null;
}

export interface UpdateCheckResponse {
  status: "update_available" | "up_to_date" | "no_release" | "error";
  current_version: string;
  latest_version: string | null;
  has_update: boolean;
  release_name: string | null;
  release_notes: string | null;
  published_at: string | null;
  release_url: string;
  download_url: string | null;
  repo_url: string;
  checked_at: string;
  message: string;
}
