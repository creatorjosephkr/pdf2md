import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  Check,
  Columns2,
  Copy,
  Download,
  Eye,
  FileCode2,
  FileText,
  Loader2,
  Maximize2,
  PanelLeft,
  RefreshCw,
  RotateCcw,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { MarkdownPreview } from "./MarkdownPreview";
import type {
  DocumentBlock,
  JobStatusResponse,
  MarkdownImageMode,
  MarkdownStats,
  PageIR,
} from "../types/engine";
import {
  downloadMarkdownUrl,
  engineApi,
  isTauriRuntime,
  pickSaveMarkdownPath,
  pickSaveRtfPath,
  sourcePageUrl,
} from "../api/client";

interface StudioViewProps {
  job: JobStatusResponse;
  fileName: string;
  baseUrl: string;
  onJobUpdated: (job: JobStatusResponse) => void;
  onBackToDashboard: () => void;
}

type ViewMode = "split" | "markdown" | "source";
type ZoomMode = "fit" | "manual";

const BLOCK_COLORS: Record<string, { stroke: string; fill: string; label: string }> = {
  figure: { stroke: "#2563eb", fill: "rgba(37, 99, 235, 0.14)", label: "Figure" },
  table: { stroke: "#059669", fill: "rgba(5, 150, 105, 0.14)", label: "Table" },
  formula: { stroke: "#7c3aed", fill: "rgba(124, 58, 237, 0.16)", label: "Formula" },
  callout_box: { stroke: "#d97706", fill: "rgba(217, 119, 6, 0.14)", label: "Callout" },
  title: { stroke: "#0ea5e9", fill: "rgba(14, 165, 233, 0.10)", label: "Title" },
  heading: { stroke: "#64748b", fill: "rgba(100, 116, 139, 0.10)", label: "Heading" },
};

export const StudioView: React.FC<StudioViewProps> = ({
  job,
  fileName,
  baseUrl,
  onJobUpdated,
  onBackToDashboard,
}) => {
  const pages = job.ir?.pages || [];
  const [activePageNo, setActivePageNo] = useState<number>(pages[0]?.page_no || 1);
  const [viewMode, setViewMode] = useState<ViewMode>("split");
  const [zoomMode, setZoomMode] = useState<ZoomMode>("fit");
  const [manualZoom, setManualZoom] = useState<number>(1.0);
  const [containerWidth, setContainerWidth] = useState<number>(1120);

  const [showPageStrip, setShowPageStrip] = useState<boolean>(pages.length > 1);
  const [showOverlay, setShowOverlay] = useState<boolean>(true);
  const [reconverting, setReconverting] = useState<boolean>(false);

  const [mdImageMode, setMdImageMode] = useState<MarkdownImageMode>(job.options.image_mode);
  const [mdPaneTab, setMdPaneTab] = useState<"edit" | "preview">("edit");
  const [mdText, setMdText] = useState<string>(job.markdown || "");
  const [mdOriginal, setMdOriginal] = useState<string>(job.markdown || "");
  const [mdStats, setMdStats] = useState<MarkdownStats | null>(job.stats);
  const [mdLoading, setMdLoading] = useState<boolean>(false);
  const [rtfSaving, setRtfSaving] = useState<boolean>(false);
  const [mdCopied, setMdCopied] = useState<boolean>(false);
  const [statusBanner, setStatusBanner] = useState<string | null>(null);

  const stageWrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = stageWrapRef.current;
    if (!el) return;
    const updateWidth = () => {
      if (el.clientWidth > 0) {
        setContainerWidth(el.clientWidth);
      }
    };
    updateWidth();
    const ro = new ResizeObserver(updateWidth);
    ro.observe(el);
    return () => ro.disconnect();
  }, [showPageStrip, viewMode]);

  useEffect(() => {
    if (pages.length > 0 && !pages.some((p) => p.page_no === activePageNo)) {
      setActivePageNo(pages[0].page_no);
    }
  }, [pages, activePageNo]);

  useEffect(() => {
    const nextMd = job.markdown || "";
    setMdText(nextMd);
    setMdOriginal(nextMd);
    setMdStats(job.stats);
    setMdImageMode(job.options.image_mode);
  }, [job.job_id, job.markdown, job.stats, job.options.image_mode]);

  const activePage: PageIR | undefined = useMemo(
    () => pages.find((p) => p.page_no === activePageNo) || pages[0],
    [pages, activePageNo]
  );

  const pageBlocks: DocumentBlock[] = useMemo(() => {
    if (!activePage) return [];
    return activePage.bands.flatMap((b) => b.blocks);
  }, [activePage]);

  const effectiveZoom = useMemo(() => {
    if (zoomMode === "manual") return manualZoom;
    if (!activePage || activePage.width_pt <= 0) return 1.0;
    const paneWidth = viewMode === "split" ? containerWidth / 2 : containerWidth;
    const fitScale = (paneWidth - 32) / activePage.width_pt;
    return Math.max(0.55, Math.min(1.5, Number(fitScale.toFixed(3))));
  }, [zoomMode, manualZoom, containerWidth, viewMode, activePage]);

  const handleZoomStep = (delta: number) => {
    const next = Math.max(0.55, Math.min(1.8, Number((effectiveZoom + delta).toFixed(2))));
    setManualZoom(next);
    setZoomMode("manual");
  };

  const handleImageModeChange = async (nextMode: MarkdownImageMode) => {
    setMdImageMode(nextMode);
    setMdLoading(true);
    try {
      const res = await engineApi.getJobMarkdown(job.job_id, nextMode);
      setMdText(res.markdown);
      setMdOriginal(res.markdown);
      setMdStats(res.stats);
    } catch (err) {
      setStatusBanner(err instanceof Error ? err.message : String(err));
    } finally {
      setMdLoading(false);
    }
  };

  const handleReconvertPageOcr = async () => {
    if (!activePage) return;
    setReconverting(true);
    setStatusBanner(null);
    try {
      const updated = await engineApi.reconvertPage(job.job_id, {
        page_no: activePage.page_no,
        force_ocr: true,
        parser: job.options.parser,
      });
      onJobUpdated(updated);
      setStatusBanner(`${activePage.page_no}페이지 OCR 재분석을 마크다운에 반영했습니다.`);
    } catch (err) {
      setStatusBanner(err instanceof Error ? err.message : String(err));
    } finally {
      setReconverting(false);
    }
  };

  const handleCopyMarkdown = async () => {
    if (!mdText) return;
    try {
      await navigator.clipboard.writeText(mdText);
      setMdCopied(true);
      setTimeout(() => setMdCopied(false), 1800);
    } catch (err) {
      setStatusBanner(err instanceof Error ? err.message : String(err));
    }
  };

  const handleSaveMarkdown = async () => {
    const defaultName = fileName.replace(/\.pdf$/i, "") + ".md";
    const edited = mdText !== mdOriginal ? mdText : null;
    if (isTauriRuntime()) {
      const dest = await pickSaveMarkdownPath(defaultName);
      if (!dest) return;
      try {
        const res = await engineApi.exportMarkdownToPath(job.job_id, dest, mdImageMode, edited);
        const assetInfo =
          res.assets_copied > 0 && res.assets_dir
            ? ` (이미지 ${res.assets_copied}개 → ${res.assets_dir})`
            : "";
        setStatusBanner(`저장 완료: ${res.exported_path}${assetInfo}`);
      } catch (err) {
        setStatusBanner(err instanceof Error ? err.message : String(err));
      }
      return;
    }
    const url = downloadMarkdownUrl(
      baseUrl,
      job.job_id,
      mdImageMode === "folder" ? "base64" : mdImageMode
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = defaultName;
    a.click();
  };

  const handleSaveRtf = async () => {
    if (!mdText) return;
    const defaultName = fileName.replace(/\.pdf$/i, "") + ".rtf";
    if (isTauriRuntime()) {
      const dest = await pickSaveRtfPath(defaultName);
      if (!dest) return;
      setRtfSaving(true);
      try {
        const res = await engineApi.exportRtfToPath(job.job_id, dest, mdText);
        const imgInfo =
          res.embedded_images > 0 ? ` (이미지 ${res.embedded_images}개 포함)` : "";
        setStatusBanner(`RTF 저장 완료: ${res.exported_path}${imgInfo}`);
      } catch (err) {
        setStatusBanner(err instanceof Error ? err.message : String(err));
      } finally {
        setRtfSaving(false);
      }
      return;
    }

    setRtfSaving(true);
    try {
      const blob = await engineApi.downloadRtfBlob(job.job_id, mdText);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = defaultName;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setStatusBanner(err instanceof Error ? err.message : String(err));
    } finally {
      setRtfSaving(false);
    }
  };

  if (!activePage) {
    return (
      <div className="p-8 text-center text-sm text-slate-600">
        변환된 페이지가 없습니다.{" "}
        <button
          type="button"
          onClick={onBackToDashboard}
          className="text-blue-600 underline cursor-pointer"
        >
          돌아가기
        </button>
      </div>
    );
  }

  const isEdited = mdText !== mdOriginal;

  return (
    <div className="flex h-[calc(100vh-56px)] flex-col overflow-hidden bg-[#F3F4F6]">
      {/* Studio Top Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-4 py-2">
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={onBackToDashboard}
            className="rounded-lg border border-slate-300 bg-slate-50 px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 cursor-pointer"
          >
            ← 새 PDF
          </button>
          <button
            type="button"
            onClick={() => setShowPageStrip((v) => !v)}
            className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-medium cursor-pointer ${
              showPageStrip
                ? "border-slate-300 bg-slate-100 text-slate-800"
                : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50"
            }`}
          >
            <PanelLeft className="h-3.5 w-3.5" />
            페이지
          </button>
          <span className="text-sm font-semibold text-slate-900 truncate max-w-[200px]" title={fileName}>
            {fileName}
          </span>
        </div>

        {/* Center View Switcher & PDF Zoom */}
        <div className="flex flex-wrap items-center gap-1.5">
          <div className="inline-flex items-center rounded-lg bg-slate-100 p-0.5 border border-slate-200">
            {[
              { id: "split" as const, label: "원본 | 마크다운", icon: Columns2 },
              { id: "markdown" as const, label: "마크다운만", icon: FileCode2 },
              { id: "source" as const, label: "원본만", icon: Eye },
            ].map((m) => {
              const Icon = m.icon;
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setViewMode(m.id)}
                  className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-all cursor-pointer ${
                    viewMode === m.id
                      ? "bg-white text-slate-900 shadow-xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {m.label}
                </button>
              );
            })}
          </div>

          {viewMode !== "markdown" && (
            <>
              <div className="mx-1 h-4 w-px bg-slate-200" />
              <button
                type="button"
                onClick={() => handleZoomStep(-0.15)}
                className="rounded-lg border border-slate-300 bg-white p-1.5 text-slate-700 hover:bg-slate-50 cursor-pointer"
                title="축소"
              >
                <ZoomOut className="h-4 w-4" />
              </button>
              <span className="w-12 text-center text-xs font-semibold text-slate-700">
                {Math.round(effectiveZoom * 100)}%
              </span>
              <button
                type="button"
                onClick={() => handleZoomStep(0.15)}
                className="rounded-lg border border-slate-300 bg-white p-1.5 text-slate-700 hover:bg-slate-50 cursor-pointer"
                title="확대"
              >
                <ZoomIn className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setZoomMode("fit")}
                className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-medium cursor-pointer ${
                  zoomMode === "fit"
                    ? "border-blue-300 bg-blue-50 text-blue-700"
                    : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                <Maximize2 className="h-3.5 w-3.5" />
                폭 맞춤
              </button>
              <button
                type="button"
                onClick={() => setShowOverlay((v) => !v)}
                className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-medium cursor-pointer ${
                  showOverlay
                    ? "border-violet-200 bg-violet-50 text-violet-700"
                    : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                <Eye className="h-3.5 w-3.5" />
                AI 영역
              </button>
            </>
          )}
        </div>

        {/* Right Markdown Actions */}
        <div className="flex items-center gap-2">
          <select
            value={mdImageMode}
            onChange={(e) => void handleImageModeChange(e.target.value as MarkdownImageMode)}
            className="rounded-lg border border-slate-300 bg-slate-50 px-2.5 py-1.5 text-xs font-medium text-slate-800"
          >
            <option value="folder">이미지 폴더 (_assets/)</option>
            <option value="base64">단일 파일 (Base64)</option>
            <option value="none">텍스트만</option>
          </select>

          <button
            type="button"
            onClick={() => void handleCopyMarkdown()}
            disabled={!mdText}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 cursor-pointer"
          >
            {mdCopied ? (
              <>
                <Check className="h-3.5 w-3.5 text-emerald-600" />
                복사됨
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                복사
              </>
            )}
          </button>

          <button
            type="button"
            onClick={() => void handleSaveRtf()}
            disabled={!mdText || rtfSaving}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-50 disabled:opacity-50 cursor-pointer"
            title="서식이 적용된 Rich Text Format (.rtf) 문서로 저장"
          >
            {rtfSaving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
            ) : (
              <FileText className="h-3.5 w-3.5 text-blue-700" />
            )}
            .rtf 저장
          </button>

          <button
            type="button"
            onClick={() => void handleSaveMarkdown()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 cursor-pointer"
          >
            <Download className="h-3.5 w-3.5" />
            .md 저장
          </button>
        </div>
      </div>

      {statusBanner && (
        <div className="flex items-center justify-between bg-blue-50 border-b border-blue-200 px-4 py-2 text-xs font-medium text-blue-800">
          <span>{statusBanner}</span>
          <button
            type="button"
            onClick={() => setStatusBanner(null)}
            className="text-blue-600 hover:text-blue-900 cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Main Studio Body */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left Slim Page Thumbnail Strip */}
        {showPageStrip && viewMode !== "markdown" && (
          <aside className="w-28 shrink-0 overflow-y-auto border-r border-slate-200 bg-slate-50 p-2 space-y-2">
            <div className="px-1 text-xs font-semibold text-slate-500">
              페이지 ({pages.length})
            </div>
            {pages.map((pg) => {
              const active = pg.page_no === activePage.page_no;
              return (
                <button
                  key={pg.page_no}
                  type="button"
                  onClick={() => setActivePageNo(pg.page_no)}
                  className={`w-full rounded-xl border p-1.5 text-left transition-all cursor-pointer ${
                    active
                      ? "border-blue-500 bg-white ring-2 ring-blue-500/15 shadow-xs"
                      : "border-slate-200 bg-white/80 hover:border-slate-300 hover:bg-white"
                  }`}
                >
                  <div className="mb-1 text-xs font-bold text-slate-900">P.{pg.page_no}</div>
                  <div className="overflow-hidden rounded border border-slate-200 bg-white">
                    <img
                      src={sourcePageUrl(baseUrl, job.session_id, pg.page_no, 96)}
                      alt={`Page ${pg.page_no}`}
                      className="w-full object-contain"
                    />
                  </div>
                </button>
              );
            })}
          </aside>
        )}

        {/* Center Comparison Viewport */}
        <div ref={stageWrapRef} className="flex flex-1 min-w-0 overflow-hidden">
          {/* Left: Original PDF */}
          {viewMode !== "markdown" && (
            <div
              className={`flex flex-1 min-w-0 flex-col overflow-hidden ${
                viewMode === "split" ? "border-r border-slate-200" : ""
              }`}
            >
              <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-3.5 py-2 text-xs">
                <span className="font-semibold text-slate-800">
                  원본 PDF — {activePage.page_no}페이지
                </span>
                <div className="flex items-center gap-2">
                  {showOverlay && (
                    <div className="hidden xl:flex items-center gap-2 text-[11px] font-medium">
                      <span className="text-blue-600">■ Figure</span>
                      <span className="text-emerald-600">■ Table</span>
                      <span className="text-violet-600">■ Formula</span>
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={() => void handleReconvertPageOcr()}
                    disabled={reconverting}
                    className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50 cursor-pointer"
                    title="이 페이지만 로컬 OCR로 다시 인식합니다"
                  >
                    {reconverting ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3 w-3" />
                    )}
                    이 페이지 OCR 재분석
                  </button>
                </div>
              </div>
              <div className="studio-grid-bg flex-1 overflow-auto p-3.5">
                <div
                  className="paper-sheet relative mx-auto rounded-sm overflow-hidden"
                  style={{
                    width: `${activePage.width_pt * effectiveZoom}px`,
                    height: `${activePage.height_pt * effectiveZoom}px`,
                  }}
                >
                  <img
                    src={sourcePageUrl(baseUrl, job.session_id, activePage.page_no, 180)}
                    alt={`Source Page ${activePage.page_no}`}
                    className="h-full w-full object-contain select-none"
                    draggable={false}
                  />
                  {showOverlay && (
                    <svg
                      viewBox={`0 0 ${activePage.width_pt} ${activePage.height_pt}`}
                      className="pointer-events-none absolute inset-0 h-full w-full"
                    >
                      {pageBlocks.map((blk) => {
                        const style = BLOCK_COLORS[blk.block_type];
                        if (!style) return null;
                        return (
                          <g key={blk.id}>
                            <rect
                              x={blk.bbox.x0}
                              y={blk.bbox.y0}
                              width={Math.max(2, blk.bbox.x1 - blk.bbox.x0)}
                              height={Math.max(2, blk.bbox.y1 - blk.bbox.y0)}
                              fill={style.fill}
                              stroke={style.stroke}
                              strokeWidth={1.2}
                            />
                            <text
                              x={blk.bbox.x0 + 3}
                              y={Math.max(10, blk.bbox.y0 + 10)}
                              fill={style.stroke}
                              fontSize={8.5}
                              fontWeight="bold"
                            >
                              {style.label}
                            </text>
                          </g>
                        );
                      })}
                    </svg>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Right: Editable / Formatted Preview Markdown Output */}
          {viewMode !== "source" && (
            <div className="flex flex-1 min-w-0 flex-col overflow-hidden bg-[#F3F4F6]">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-4 py-1.5 text-xs">
                <div className="flex items-center gap-2">
                  <div className="inline-flex items-center rounded-lg border border-slate-200 bg-slate-200/70 p-0.5">
                    <button
                      type="button"
                      onClick={() => setMdPaneTab("edit")}
                      className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-all cursor-pointer ${
                        mdPaneTab === "edit"
                          ? "bg-white text-slate-900 shadow-xs"
                          : "text-slate-600 hover:text-slate-900"
                      }`}
                    >
                      <FileCode2 className="h-3.5 w-3.5" />
                      원문 편집
                    </button>
                    <button
                      type="button"
                      onClick={() => setMdPaneTab("preview")}
                      className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-all cursor-pointer ${
                        mdPaneTab === "preview"
                          ? "bg-white text-blue-700 shadow-xs"
                          : "text-slate-600 hover:text-slate-900"
                      }`}
                    >
                      <BookOpen className="h-3.5 w-3.5" />
                      미리보기
                    </button>
                  </div>
                  {isEdited && (
                    <span className="rounded-md border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700">
                      수정됨
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  {mdStats && (
                    <span className="text-slate-600">
                      {mdText.length.toLocaleString()}자 · 제목 {mdStats.headings} · 표{" "}
                      {mdStats.tables} · 그림 {mdStats.figures} · 수식 {mdStats.formulas}
                    </span>
                  )}
                  {isEdited && (
                    <button
                      type="button"
                      onClick={() => setMdText(mdOriginal)}
                      className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-700 hover:bg-slate-100 cursor-pointer"
                    >
                      <RotateCcw className="h-3 w-3" />
                      원본 복원
                    </button>
                  )}
                </div>
              </div>

              <div className="flex-1 min-h-0 p-4">
                {mdLoading ? (
                  <div className="flex h-full items-center justify-center gap-2 text-sm text-slate-600">
                    <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
                    마크다운을 업데이트하는 중...
                  </div>
                ) : mdPaneTab === "preview" ? (
                  <MarkdownPreview markdown={mdText} jobId={job.job_id} baseUrl={baseUrl} />
                ) : (
                  <textarea
                    value={mdText}
                    onChange={(e) => setMdText(e.target.value)}
                    spellCheck={false}
                    className="h-full w-full resize-none rounded-2xl border border-slate-200 bg-white p-5 text-[13.5px] leading-relaxed text-slate-900 shadow-xs focus:border-blue-400 focus:outline-none"
                    style={{ fontFamily: '"JetBrains Mono", "Noto Sans KR", monospace' }}
                  />
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
