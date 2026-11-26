import React, { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Columns2,
  FileCode2,
  FileText,
  FolderOpen,
  Languages,
  Loader2,
  Play,
  Presentation,
  Printer,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import type {
  ConvertRequest,
  JobStatusResponse,
  MarkdownImageMode,
  ParserName,
  SessionResponse,
} from "../types/engine";
import {
  engineApi,
  isTauriRuntime,
  pickNativePdfPath,
  sourcePageUrl,
  stagePdfForEngine,
} from "../api/client";

interface DashboardViewProps {
  session: SessionResponse | null;
  baseUrl: string;
  activeJob: JobStatusResponse | null;
  engineReady: boolean;
  engineStatusMessage?: string | null;
  onSessionLoaded: (session: SessionResponse) => void;
  onClearSession: () => void;
  onStartConvert: (req: ConvertRequest) => void;
  onOpenStudio: () => void;
  onOpenPresentation: (pageNo: number) => void;
  onOpenPrint: (pageNo: number) => void;
}

const LANG_LABELS: Record<string, string> = {
  ko: "한국어",
  en: "영문 (English)",
  mixed: "한·영 혼합",
  other: "기타",
};

export const DashboardView: React.FC<DashboardViewProps> = ({
  session,
  baseUrl,
  activeJob,
  engineReady,
  engineStatusMessage,
  onSessionLoaded,
  onClearSession,
  onStartConvert,
  onOpenStudio,
  onOpenPresentation,
  onOpenPrint,
}) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const [loadingPdf, setLoadingPdf] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [pendingPdfPath, setPendingPdfPath] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [previewPageNo, setPreviewPageNo] = useState(1);

  const engineReadyRef = useRef(engineReady);
  engineReadyRef.current = engineReady;

  const [parser, setParser] = useState<ParserName>("docling");
  const [imageMode, setImageMode] = useState<MarkdownImageMode>("folder");
  const [complexTableHtml, setComplexTableHtml] = useState(true);
  const [includeFrontmatter, setIncludeFrontmatter] = useState(true);
  const [forceOcr, setForceOcr] = useState(false);
  const [enableFormula, setEnableFormula] = useState(true);
  const [pagesStr, setPagesStr] = useState("");

  useEffect(() => {
    setPreviewPageNo(1);
    if (session) {
      setForceOcr(session.preflight.recommended_ocr);
    }
  }, [session?.session_id]);

  // Listen for native Tauri drag-drop events (returns real local file path)
  useEffect(() => {
    if (!isTauriRuntime()) return;
    let unlisten: (() => void) | null = null;
    getCurrentWebview()
      .onDragDropEvent((event) => {
        if (event.payload.type === "over") {
          setDragging(true);
        } else if (event.payload.type === "leave") {
          setDragging(false);
        } else if (event.payload.type === "drop") {
          setDragging(false);
          const pdfPath = event.payload.paths.find((p) => p.toLowerCase().endsWith(".pdf"));
          if (pdfPath) {
            void handleOpenPath(pdfPath);
          } else {
            setErrorMsg("PDF 파일(.pdf)만 열 수 있습니다.");
          }
        }
      })
      .then((fn) => {
        unlisten = fn;
      })
      .catch(() => {});

    return () => {
      if (unlisten) unlisten();
    };
  }, []);

  const handleOpenPath = async (pdfPath: string) => {
    setErrorMsg(null);
    if (!engineReadyRef.current) {
      setPendingFile(null);
      setPendingPdfPath(pdfPath);
      return;
    }
    setLoadingPdf(true);
    try {
      const staged = await stagePdfForEngine(pdfPath);
      const res = staged
        ? await engineApi.openPdfPath(staged.staged_path, null, staged.original_name)
        : await engineApi.openPdfPath(pdfPath);
      onSessionLoaded(res);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingPdf(false);
    }
  };

  const handleUploadFile = async (file: File) => {
    setErrorMsg(null);
    if (!engineReadyRef.current) {
      setPendingPdfPath(null);
      setPendingFile(file);
      return;
    }
    setLoadingPdf(true);
    try {
      const res = await engineApi.uploadPdf(file);
      onSessionLoaded(res);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingPdf(false);
    }
  };

  useEffect(() => {
    if (!engineReady) return;
    if (pendingPdfPath) {
      const path = pendingPdfPath;
      setPendingPdfPath(null);
      void handleOpenPath(path);
    } else if (pendingFile) {
      const f = pendingFile;
      setPendingFile(null);
      void handleUploadFile(f);
    }
  }, [engineReady, pendingPdfPath, pendingFile]);

  const handlePickFile = async () => {
    setErrorMsg(null);
    if (isTauriRuntime()) {
      try {
        const picked = await pickNativePdfPath();
        if (picked) {
          await handleOpenPath(picked);
        }
        return;
      } catch {
        // Fallback to standard file input if native dialog fails
      }
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
      fileInputRef.current.click();
    }
  };

  const handleConvertClick = () => {
    if (!session) return;
    onStartConvert({
      session_id: session.session_id,
      parser,
      image_mode: imageMode,
      complex_table_html: complexTableHtml,
      include_frontmatter: includeFrontmatter,
      force_ocr: forceOcr,
      enable_formula_enrichment: enableFormula,
      pages: pagesStr.trim() || null,
    });
  };

  const isConverting = activeJob?.status === "queued" || activeJob?.status === "running";
  const totalPages = session?.preflight.page_count ?? 1;

  return (
    <div className="mx-auto h-full w-full max-w-[1600px] overflow-hidden p-4">
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void handleUploadFile(f);
        }}
      />

      {/* Left (A4 Portrait Fit-to-Screen) / Right (Markdown Conversion Settings) */}
      <div className="grid h-full min-h-0 grid-cols-1 gap-4 lg:grid-cols-[5fr_6fr]">
        {/* LEFT (~45.5%): PDF Attachment & A4 Fit-to-Screen Preview */}
        <section
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const file = e.dataTransfer.files?.[0];
            if (file && file.name.toLowerCase().endsWith(".pdf")) {
              void handleUploadFile(file);
            } else if (file) {
              setErrorMsg("PDF 파일(.pdf)만 업로드할 수 있습니다.");
            }
          }}
          className={`flex h-full min-h-0 flex-col overflow-hidden rounded-2xl transition-all ${
            session
              ? `border bg-white shadow-xs ${
                  dragging ? "border-blue-500 ring-2 ring-blue-500/20" : "border-slate-200"
                }`
              : `items-center justify-center border-2 border-dashed p-8 text-center shadow-xs ${
                  dragging
                    ? "border-blue-500 bg-blue-50/70"
                    : "border-slate-300 bg-white hover:border-slate-400"
                }`
          }`}
        >
          {!session ? (
            <>
              <div className="mb-4 rounded-2xl bg-blue-50 p-4 text-blue-600 ring-1 ring-blue-200/80">
                {loadingPdf ? (
                  <Loader2 className="h-8 w-8 animate-spin" />
                ) : (
                  <Upload className="h-8 w-8" />
                )}
              </div>
              <h2 className="text-xl font-semibold text-slate-900">
                PDF 문서를 여기에 놓으세요
              </h2>
              <p className="mt-2.5 max-w-md text-sm leading-relaxed text-slate-600">
                2단 학술 논문 · 수식(LaTeX) · 병합 표 · 그림 · Callout 박스를 로컬 AI로 분석해{" "}
                <span className="font-semibold text-blue-700">깔끔한 마크다운(.md)</span>으로
                변환합니다.
              </p>
              <div className="mt-6 flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => void handlePickFile()}
                  disabled={loadingPdf}
                  className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white shadow-xs hover:bg-slate-800 disabled:opacity-50 cursor-pointer"
                >
                  <FolderOpen className="h-4 w-4" />
                  PDF 파일 선택
                </button>
              </div>
              {(pendingPdfPath || pendingFile) && !engineReady ? (
                <p className="mt-4 inline-flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-3.5 py-2 text-xs font-medium text-blue-800">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
                  로컬 엔진 준비가 끝나면 선택한 PDF를 자동으로 불러옵니다...
                </p>
              ) : !engineReady ? (
                <p className="mt-4 text-xs text-slate-500">
                  {engineStatusMessage || "로컬 변환 엔진 준비 중입니다... 완료되면 바로 변환할 수 있습니다."}
                </p>
              ) : null}
            </>
          ) : (
            <div className="flex h-full min-h-0 flex-col overflow-hidden">
              {/* Preview Header with Replace & Delete */}
              <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-4 py-2.5">
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600 border border-blue-200/80">
                    <FileText className="h-4 w-4" />
                  </div>
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className="truncate text-sm font-semibold text-slate-900"
                      title={session.file_name}
                    >
                      {session.file_name}
                    </span>
                    <span className="shrink-0 rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
                      {totalPages}p
                    </span>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => onOpenPresentation(previewPageNo)}
                    disabled={loadingPdf}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100 disabled:opacity-50 cursor-pointer"
                    title="프레젠테이션 형식으로 크게보기"
                  >
                    <Presentation className="h-3.5 w-3.5" />
                    크게보기
                  </button>
                  <button
                    type="button"
                    onClick={() => onOpenPrint(previewPageNo)}
                    disabled={loadingPdf}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 cursor-pointer"
                    title="불러온 PDF 인쇄"
                  >
                    <Printer className="h-3.5 w-3.5" />
                    인쇄
                  </button>
                  <button
                    type="button"
                    onClick={() => void handlePickFile()}
                    disabled={loadingPdf}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 cursor-pointer"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${loadingPdf ? "animate-spin" : ""}`} />
                    다시 첨부
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setErrorMsg(null);
                      onClearSession();
                    }}
                    disabled={loadingPdf || isConverting}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-100 disabled:opacity-50 cursor-pointer"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    삭제
                  </button>
                </div>
              </div>

              {/* Fit-to-Screen A4 Portrait Preview Stage */}
              <div className="relative flex-1 min-h-0 bg-[#ECEEF2]">
                <div className="absolute inset-3 flex items-center justify-center">
                  {loadingPdf ? (
                    <div className="flex items-center gap-2 text-sm text-slate-600">
                      <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
                      PDF 문서를 불러오는 중...
                    </div>
                  ) : (
                    <img
                      src={sourcePageUrl(baseUrl, session.session_id, previewPageNo, 180)}
                      alt={`${session.file_name} ${previewPageNo}페이지 미리보기`}
                      onDoubleClick={() => onOpenPresentation(previewPageNo)}
                      title="더블클릭하여 프레젠테이션 크게보기"
                      className="max-h-full max-w-full object-contain rounded-lg border border-slate-300/90 bg-white shadow-sm cursor-zoom-in"
                    />
                  )}
                </div>
              </div>

              {/* Preview Footer Page Stepper */}
              <div className="flex shrink-0 items-center justify-between border-t border-slate-200 bg-slate-50 px-4 py-2">
                <span className="text-xs text-slate-500">
                  {previewPageNo} / {totalPages} 페이지 · 드래그로 교체 가능
                </span>
                {totalPages > 1 && (
                  <div className="inline-flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => setPreviewPageNo((p) => Math.max(1, p - 1))}
                      disabled={previewPageNo <= 1}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40 cursor-pointer"
                    >
                      <ChevronLeft className="h-3.5 w-3.5" />
                      이전
                    </button>
                    <button
                      type="button"
                      onClick={() => setPreviewPageNo((p) => Math.min(totalPages, p + 1))}
                      disabled={previewPageNo >= totalPages}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40 cursor-pointer"
                    >
                      다음
                      <ChevronRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {(pendingPdfPath || pendingFile) && session && !engineReady && (
            <p className="m-3 flex items-center gap-2 text-xs text-blue-800 bg-blue-50 px-3 py-2 rounded-lg border border-blue-200">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
              로컬 엔진이 준비되는 대로 새 PDF를 자동으로 불러옵니다...
            </p>
          )}

          {errorMsg && (
            <p className="m-3 text-xs text-rose-700 bg-rose-50 px-3 py-2 rounded-lg border border-rose-200">
              {errorMsg}
            </p>
          )}
        </section>

        {/* RIGHT (~54.5%): Simple Markdown Conversion Settings & Preflight */}
        <section className="flex min-h-0 flex-col gap-4 overflow-y-auto pr-0.5">
          {/* Markdown Settings Card */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs space-y-5">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-slate-900 flex items-center gap-2">
                <FileCode2 className="h-4 w-4 text-blue-600" />
                마크다운(.md) 변환 설정
              </h3>
              <span className="text-xs text-slate-500">Obsidian · Notion · GitHub 호환</span>
            </div>

            {/* Image Handling Mode */}
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-2">
                그림·도표 처리 방식
              </label>
              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
                {[
                  {
                    id: "folder" as const,
                    title: "이미지 폴더 분리",
                    desc: ".md 옆 _assets/ 폴더에 그림 PNG 저장 (추천)",
                  },
                  {
                    id: "base64" as const,
                    title: "단일 파일 임베딩",
                    desc: "그림을 Base64로 .md 안에 직접 포함",
                  },
                  {
                    id: "none" as const,
                    title: "텍스트만",
                    desc: "그림 파일 없이 캡션 텍스트만 출력",
                  },
                ].map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setImageMode(opt.id)}
                    className={`rounded-xl border p-3 text-left transition-all cursor-pointer ${
                      imageMode === opt.id
                        ? "border-blue-500 bg-blue-50/80 ring-1 ring-blue-500/20"
                        : "border-slate-200 bg-slate-50/70 hover:border-slate-300"
                    }`}
                  >
                    <div className="text-sm font-semibold text-slate-900">{opt.title}</div>
                    <div className="mt-1 text-xs leading-snug text-slate-600">{opt.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Parser + Page Range */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                  AI 분석 엔진
                </label>
                <select
                  value={parser}
                  onChange={(e) => setParser(e.target.value as ParserName)}
                  className="w-full rounded-xl border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-900"
                >
                  <option value="docling">Docling AI 정밀 (2단 · 수식 · 표)</option>
                  <option value="fallback">경량 규칙 파서 (초고속)</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                  변환 페이지 범위
                </label>
                <input
                  type="text"
                  placeholder="전체 (예: 1-3 또는 2)"
                  value={pagesStr}
                  onChange={(e) => setPagesStr(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400"
                />
              </div>
            </div>

            {/* Clean Option Checkboxes */}
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 pt-1">
              <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={enableFormula}
                  onChange={(e) => setEnableFormula(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-blue-600"
                />
                수식 LaTeX ($$...$$) 추출
              </label>
              <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={complexTableHtml}
                  onChange={(e) => setComplexTableHtml(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-blue-600"
                />
                병합 셀 표 HTML 유지
              </label>
              <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeFrontmatter}
                  onChange={(e) => setIncludeFrontmatter(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-blue-600"
                />
                문서 메타데이터(YAML) 포함
              </label>
              <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={forceOcr}
                  onChange={(e) => setForceOcr(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-blue-600"
                />
                로컬 RapidOCR 강제 사용
              </label>
            </div>

            {/* Progress or Primary Convert Button */}
            {isConverting && activeJob ? (
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium text-blue-900 flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                    {activeJob.stage}
                  </span>
                  <span className="font-semibold text-blue-700">{activeJob.progress_pct}%</span>
                </div>
                <div className="h-2.5 w-full overflow-hidden rounded-full bg-blue-100">
                  <div
                    className="h-full bg-blue-600 transition-all duration-300"
                    style={{ width: `${activeJob.progress_pct}%` }}
                  />
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
                {activeJob?.status === "failed" && activeJob.error ? (
                  <span className="text-xs text-rose-600 font-medium">{activeJob.error}</span>
                ) : session && activeJob?.status === "completed" && activeJob.session_id === session.session_id ? (
                  <button
                    type="button"
                    onClick={onOpenStudio}
                    className="text-sm font-semibold text-blue-700 hover:underline cursor-pointer"
                  >
                    변환된 마크다운 보기 →
                  </button>
                ) : (
                  <span className="text-xs text-slate-500">
                    {session
                      ? "변환 완료 후 원본·마크다운 비교 화면으로 이동합니다."
                      : "왼쪽 영역에 PDF를 첨부하면 변환을 시작할 수 있습니다."}
                  </span>
                )}

                <button
                  type="button"
                  onClick={handleConvertClick}
                  disabled={!session || loadingPdf}
                  className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white shadow-xs hover:bg-slate-800 disabled:bg-slate-300 disabled:text-slate-500 disabled:cursor-not-allowed cursor-pointer"
                >
                  <Play className="h-4 w-4 fill-current" />
                  마크다운으로 변환
                </button>
              </div>
            )}
          </div>

          {/* Preflight Diagnostic Card */}
          {session ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-xs space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-wider text-blue-600">
                    PDF 문서 진단
                  </span>
                  <h3 className="mt-0.5 text-sm font-semibold text-slate-900 break-all">
                    {session.file_name}
                  </h3>
                </div>
                <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600" />
              </div>

              <div className="grid grid-cols-3 gap-2.5">
                <div className="rounded-xl bg-slate-50 p-3 border border-slate-200/80">
                  <div className="text-xs text-slate-500 flex items-center gap-1">
                    <FileText className="h-3.5 w-3.5 text-blue-600" />
                    페이지
                  </div>
                  <div className="mt-1 text-sm font-semibold text-slate-900">
                    {session.preflight.page_count}p (디지털 {session.preflight.digital_pages}p)
                  </div>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 border border-slate-200/80">
                  <div className="text-xs text-slate-500 flex items-center gap-1">
                    <Columns2 className="h-3.5 w-3.5 text-violet-600" />
                    단 구성
                  </div>
                  <div className="mt-1 text-sm font-semibold text-slate-900">
                    {session.preflight.detected_columns}단
                  </div>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 border border-slate-200/80">
                  <div className="text-xs text-slate-500 flex items-center gap-1">
                    <Languages className="h-3.5 w-3.5 text-emerald-600" />
                    언어
                  </div>
                  <div className="mt-1 text-sm font-semibold text-slate-900">
                    {LANG_LABELS[session.preflight.detected_language] || session.preflight.detected_language}
                  </div>
                </div>
              </div>

              {session.preflight.warnings.length > 0 && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 flex gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 mt-0.5" />
                  <div>{session.preflight.warnings.join(" ")}</div>
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white/70 p-5 text-center text-sm text-slate-500">
              PDF를 첨부하면 페이지 수·단 구성·언어·한글 깨짐 여부를 자동으로 진단합니다.
            </div>
          )}
        </section>
      </div>
    </div>
  );
};
