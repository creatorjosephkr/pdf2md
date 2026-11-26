import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  LayoutGrid,
  Loader2,
  Maximize2,
  Minimize2,
  Printer,
  RotateCcw,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import type { SessionResponse } from "../types/engine";
import { setWindowFullscreen, sourcePageUrl } from "../api/client";

interface PdfPresentationModalProps {
  open: boolean;
  session: SessionResponse | null;
  baseUrl: string;
  initialPage: number;
  onClose: () => void;
  onOpenPrint: (pageNo: number) => void;
}

export const PdfPresentationModal: React.FC<PdfPresentationModalProps> = ({
  open,
  session,
  baseUrl,
  initialPage,
  onClose,
  onOpenPrint,
}) => {
  const totalPages = session?.preflight.page_count ?? 1;
  const [pageNo, setPageNo] = useState<number>(initialPage);
  const [zoom, setZoom] = useState<number>(1);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [showThumbs, setShowThumbs] = useState<boolean>(false);
  const [imgLoading, setImgLoading] = useState<boolean>(false);
  const [pageInput, setPageInput] = useState<string>(String(initialPage));

  const thumbStripRef = useRef<HTMLDivElement | null>(null);
  const isFullscreenRef = useRef<boolean>(false);
  isFullscreenRef.current = isFullscreen;

  useEffect(() => {
    if (open) {
      const clamped = Math.max(1, Math.min(totalPages, initialPage || 1));
      setPageNo(clamped);
      setPageInput(String(clamped));
      setZoom(1);
      setImgLoading(true);
    } else if (isFullscreenRef.current) {
      void setWindowFullscreen(false);
      setIsFullscreen(false);
    }
  }, [open, initialPage, totalPages]);

  useEffect(() => {
    return () => {
      if (isFullscreenRef.current) {
        void setWindowFullscreen(false);
      }
    };
  }, []);

  const goToPage = useCallback(
    (next: number) => {
      const clamped = Math.max(1, Math.min(totalPages, next));
      setPageNo((prev) => {
        if (prev !== clamped) {
          setImgLoading(true);
        }
        return clamped;
      });
      setPageInput(String(clamped));
    },
    [totalPages]
  );

  const handleToggleFullscreen = useCallback(async () => {
    const next = !isFullscreenRef.current;
    const ok = await setWindowFullscreen(next);
    if (ok) {
      setIsFullscreen(next);
    }
  }, []);

  const handleClose = useCallback(() => {
    if (isFullscreenRef.current) {
      void setWindowFullscreen(false);
      setIsFullscreen(false);
    }
    onClose();
  }, [onClose]);

  // Preload adjacent pages for instant slide transitions
  useEffect(() => {
    if (!open || !session) return;
    const neighbors = [pageNo + 1, pageNo - 1].filter((n) => n >= 1 && n <= totalPages);
    neighbors.forEach((n) => {
      const img = new Image();
      img.src = sourcePageUrl(baseUrl, session.session_id, n, 220);
    });
  }, [open, session, baseUrl, pageNo, totalPages]);

  // Keep active thumbnail visible when thumbnail strip is open
  useEffect(() => {
    if (!showThumbs || !thumbStripRef.current) return;
    const activeEl = thumbStripRef.current.querySelector<HTMLElement>(
      `[data-slide-thumb="${pageNo}"]`
    );
    activeEl?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }, [showThumbs, pageNo]);

  // Keyboard shortcuts for presentation mode
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) {
        if (e.key === "Escape") {
          target.blur();
        }
        return;
      }

      if (e.key === "Escape") {
        e.preventDefault();
        handleClose();
      } else if (
        e.key === "ArrowRight" ||
        e.key === "ArrowDown" ||
        e.key === "PageDown" ||
        e.key === " "
      ) {
        e.preventDefault();
        goToPage(pageNo + 1);
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp" || e.key === "PageUp") {
        e.preventDefault();
        goToPage(pageNo - 1);
      } else if (e.key === "Home") {
        e.preventDefault();
        goToPage(1);
      } else if (e.key === "End") {
        e.preventDefault();
        goToPage(totalPages);
      } else if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        setZoom((z) => Math.min(2.5, Number((z + 0.25).toFixed(2))));
      } else if (e.key === "-") {
        e.preventDefault();
        setZoom((z) => Math.max(0.5, Number((z - 0.25).toFixed(2))));
      } else if (e.key === "0") {
        e.preventDefault();
        setZoom(1);
      } else if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        void handleToggleFullscreen();
      } else if (e.key === "g" || e.key === "G") {
        e.preventDefault();
        setShowThumbs((v) => !v);
      } else if ((e.metaKey || e.ctrlKey) && (e.key === "p" || e.key === "P")) {
        e.preventDefault();
        onOpenPrint(pageNo);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, pageNo, totalPages, goToPage, handleClose, handleToggleFullscreen, onOpenPrint]);

  if (!open || !session) return null;

  const progressPct = totalPages > 1 ? ((pageNo - 1) / (totalPages - 1)) * 100 : 100;
  const pageSrc = sourcePageUrl(baseUrl, session.session_id, pageNo, 220);

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-slate-950/96 text-white select-none backdrop-blur-xs"
      role="dialog"
      aria-modal="true"
      aria-label={`${session.file_name} 프레젠테이션 크게보기`}
    >
      {/* Top Bar */}
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 bg-slate-950/85 px-5 py-2.5">
        <div className="flex min-w-0 items-center gap-3">
          <span className="rounded-md bg-blue-500/20 border border-blue-400/30 px-2 py-0.5 text-[11px] font-semibold text-blue-300">
            프레젠테이션
          </span>
          <span className="truncate text-sm font-semibold text-slate-100" title={session.file_name}>
            {session.file_name}
          </span>
          <span className="shrink-0 rounded-full bg-white/10 px-2.5 py-0.5 text-xs font-semibold text-slate-200">
            {pageNo} / {totalPages}
          </span>
          <span className="hidden text-[11px] text-slate-400 xl:inline">
            ← / → 이동 · Space 다음 · F 전체화면 · G 슬라이드 목록 · ESC 닫기
          </span>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            onClick={() => setShowThumbs((v) => !v)}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors cursor-pointer ${
              showThumbs
                ? "border-blue-400/50 bg-blue-500/20 text-blue-200"
                : "border-white/15 bg-white/5 text-slate-200 hover:bg-white/10"
            }`}
            title="슬라이드 목록 (G)"
          >
            <LayoutGrid className="h-3.5 w-3.5" />
            목록
          </button>

          <button
            type="button"
            onClick={() => onOpenPrint(pageNo)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/5 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-white/10 transition-colors cursor-pointer"
            title="PDF 인쇄 (⌘P / Ctrl+P)"
          >
            <Printer className="h-3.5 w-3.5" />
            인쇄
          </button>

          <button
            type="button"
            onClick={() => void handleToggleFullscreen()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/5 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-white/10 transition-colors cursor-pointer"
            title="전체화면 전환 (F)"
          >
            {isFullscreen ? (
              <>
                <Minimize2 className="h-3.5 w-3.5" />
                창 모드
              </>
            ) : (
              <>
                <Maximize2 className="h-3.5 w-3.5" />
                전체화면
              </>
            )}
          </button>

          <button
            type="button"
            onClick={handleClose}
            className="inline-flex items-center gap-1 rounded-lg border border-white/15 bg-white/10 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-rose-500/80 hover:border-rose-400/60 transition-colors cursor-pointer"
            title="닫기 (ESC)"
          >
            <X className="h-3.5 w-3.5" />
            닫기
          </button>
        </div>
      </div>

      {/* Main Presentation Stage */}
      <div className="relative flex-1 min-h-0 overflow-auto">
        {/* Left Navigation Hit Zone */}
        {totalPages > 1 && pageNo > 1 && (
          <button
            type="button"
            onClick={() => goToPage(pageNo - 1)}
            aria-label="이전 페이지"
            className="fixed left-4 top-1/2 z-20 -translate-y-1/2 flex h-12 w-12 items-center justify-center rounded-full border border-white/15 bg-slate-900/70 text-white/85 shadow-lg backdrop-blur-sm transition-all hover:scale-105 hover:bg-slate-800/90 hover:text-white cursor-pointer"
          >
            <ChevronLeft className="h-6 w-6" />
          </button>
        )}

        {/* Right Navigation Hit Zone */}
        {totalPages > 1 && pageNo < totalPages && (
          <button
            type="button"
            onClick={() => goToPage(pageNo + 1)}
            aria-label="다음 페이지"
            className="fixed right-4 top-1/2 z-20 -translate-y-1/2 flex h-12 w-12 items-center justify-center rounded-full border border-white/15 bg-slate-900/70 text-white/85 shadow-lg backdrop-blur-sm transition-all hover:scale-105 hover:bg-slate-800/90 hover:text-white cursor-pointer"
          >
            <ChevronRight className="h-6 w-6" />
          </button>
        )}

        <div
          className={`flex min-h-full min-w-full items-center justify-center p-5 ${
            zoom > 1 ? "items-start" : ""
          }`}
        >
          <div className="relative flex items-center justify-center">
            {imgLoading && (
              <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
                <div className="flex items-center gap-2 rounded-full bg-slate-900/85 px-3.5 py-2 text-xs text-slate-200 shadow-lg">
                  <Loader2 className="h-4 w-4 animate-spin text-blue-400" />
                  {pageNo}페이지 불러오는 중...
                </div>
              </div>
            )}

            <img
              key={`${session.session_id}-${pageNo}`}
              src={pageSrc}
              alt={`${session.file_name} ${pageNo}페이지`}
              onLoad={() => setImgLoading(false)}
              onError={() => setImgLoading(false)}
              draggable={false}
              style={
                zoom === 1
                  ? {
                      maxHeight: showThumbs ? "calc(100vh - 240px)" : "calc(100vh - 138px)",
                      maxWidth: "calc(100vw - 120px)",
                    }
                  : {
                      height: `calc((${showThumbs ? "100vh - 240px" : "100vh - 138px"}) * ${zoom})`,
                      maxWidth: "none",
                    }
              }
              className="rounded-lg bg-white object-contain shadow-[0_20px_60px_rgba(0,0,0,0.65)] ring-1 ring-white/15 transition-opacity duration-150"
            />
          </div>
        </div>
      </div>

      {/* Optional Slide Thumbnail Strip */}
      {showThumbs && (
        <div className="shrink-0 border-t border-white/10 bg-slate-900/95 px-4 py-2.5">
          <div
            ref={thumbStripRef}
            className="flex items-center gap-2.5 overflow-x-auto pb-1"
          >
            {Array.from({ length: totalPages }, (_, idx) => idx + 1).map((n) => (
              <button
                key={n}
                type="button"
                data-slide-thumb={n}
                onClick={() => goToPage(n)}
                className={`group flex shrink-0 flex-col items-center gap-1 rounded-lg p-1.5 transition-all cursor-pointer ${
                  n === pageNo
                    ? "bg-blue-500/25 ring-2 ring-blue-400"
                    : "bg-white/5 hover:bg-white/10"
                }`}
              >
                <img
                  src={sourcePageUrl(baseUrl, session.session_id, n, 72)}
                  alt={`${n}페이지 썸네일`}
                  loading="lazy"
                  className="h-16 w-auto rounded bg-white object-contain shadow-xs"
                />
                <span
                  className={`text-[10px] font-semibold ${
                    n === pageNo ? "text-blue-200" : "text-slate-400 group-hover:text-slate-200"
                  }`}
                >
                  {n}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Bottom Progress & Controls */}
      <div className="shrink-0 border-t border-white/10 bg-slate-950/90">
        <div className="h-0.5 w-full bg-white/10">
          <div
            className="h-full bg-blue-500 transition-all duration-200"
            style={{ width: `${progressPct}%` }}
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-2.5 text-xs">
          {/* Page Stepper */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => goToPage(pageNo - 1)}
              disabled={pageNo <= 1}
              className="inline-flex items-center gap-1 rounded-lg border border-white/15 bg-white/5 px-2.5 py-1.5 font-medium text-slate-200 hover:bg-white/10 disabled:opacity-35 cursor-pointer"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              이전
            </button>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                const parsed = Number.parseInt(pageInput, 10);
                if (!Number.isNaN(parsed)) {
                  goToPage(parsed);
                } else {
                  setPageInput(String(pageNo));
                }
              }}
              className="inline-flex items-center gap-1.5"
            >
              <input
                type="text"
                inputMode="numeric"
                value={pageInput}
                onChange={(e) => setPageInput(e.target.value)}
                onBlur={() => {
                  const parsed = Number.parseInt(pageInput, 10);
                  if (!Number.isNaN(parsed)) {
                    goToPage(parsed);
                  } else {
                    setPageInput(String(pageNo));
                  }
                }}
                aria-label="페이지 번호 이동"
                className="w-12 rounded-lg border border-white/20 bg-white/10 px-2 py-1 text-center font-semibold text-white focus:border-blue-400 focus:outline-none"
              />
              <span className="text-slate-400">/ {totalPages}</span>
            </form>

            <button
              type="button"
              onClick={() => goToPage(pageNo + 1)}
              disabled={pageNo >= totalPages}
              className="inline-flex items-center gap-1 rounded-lg border border-white/15 bg-white/5 px-2.5 py-1.5 font-medium text-slate-200 hover:bg-white/10 disabled:opacity-35 cursor-pointer"
            >
              다음
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Zoom Controls */}
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setZoom((z) => Math.max(0.5, Number((z - 0.25).toFixed(2))))}
              className="rounded-lg border border-white/15 bg-white/5 p-1.5 text-slate-200 hover:bg-white/10 cursor-pointer"
              title="축소 (-)"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </button>
            <span className="w-14 text-center font-semibold text-slate-200">
              {zoom === 1 ? "화면 맞춤" : `${Math.round(zoom * 100)}%`}
            </span>
            <button
              type="button"
              onClick={() => setZoom((z) => Math.min(2.5, Number((z + 0.25).toFixed(2))))}
              className="rounded-lg border border-white/15 bg-white/5 p-1.5 text-slate-200 hover:bg-white/10 cursor-pointer"
              title="확대 (+)"
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </button>
            {zoom !== 1 && (
              <button
                type="button"
                onClick={() => setZoom(1)}
                className="inline-flex items-center gap-1 rounded-lg border border-white/15 bg-white/5 px-2 py-1.5 text-slate-200 hover:bg-white/10 cursor-pointer"
                title="화면 맞춤 (0)"
              >
                <RotateCcw className="h-3 w-3" />
                맞춤
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
