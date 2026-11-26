import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ExternalLink, Loader2, Printer, X } from "lucide-react";
import type { SessionResponse } from "../types/engine";
import { openFileInSystem, sourcePageUrl, sourcePdfUrl } from "../api/client";

interface PdfPrintModalProps {
  open: boolean;
  session: SessionResponse | null;
  baseUrl: string;
  currentPage: number;
  onClose: () => void;
}

type PrintRangeMode = "all" | "current" | "custom";

function parsePrintPages(raw: string, totalPages: number): { pages: number[]; error: string | null } {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { pages: [], error: "인쇄할 페이지 번호나 범위를 입력해 주세요. (예: 1-3, 5)" };
  }
  const set = new Set<number>();
  const parts = trimmed.split(",").map((p) => p.trim()).filter(Boolean);
  for (const part of parts) {
    if (part.includes("-")) {
      const segs = part.split("-").map((s) => s.trim());
      if (segs.length !== 2 || !/^\d+$/.test(segs[0]) || !/^\d+$/.test(segs[1])) {
        return { pages: [], error: `잘못된 범위 형식입니다: "${part}"` };
      }
      const start = Number.parseInt(segs[0], 10);
      const end = Number.parseInt(segs[1], 10);
      if (start < 1 || end < 1 || start > totalPages || end > totalPages || start > end) {
        return { pages: [], error: `페이지 범위(1~${totalPages})를 벗어났습니다: "${part}"` };
      }
      for (let p = start; p <= end; p += 1) set.add(p);
    } else {
      if (!/^\d+$/.test(part)) {
        return { pages: [], error: `잘못된 페이지 번호입니다: "${part}"` };
      }
      const p = Number.parseInt(part, 10);
      if (p < 1 || p > totalPages) {
        return { pages: [], error: `페이지 번호(1~${totalPages})를 벗어났습니다: "${part}"` };
      }
      set.add(p);
    }
  }
  const sorted = Array.from(set).sort((a, b) => a - b);
  return { pages: sorted, error: sorted.length === 0 ? "선택된 페이지가 없습니다." : null };
}

function preloadImage(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      if (typeof img.decode === "function") {
        img.decode().then(() => resolve()).catch(() => resolve());
      } else {
        resolve();
      }
    };
    img.onerror = () => reject(new Error("페이지 이미지를 불러오지 못했습니다."));
    img.src = url;
  });
}

export const PdfPrintModal: React.FC<PdfPrintModalProps> = ({
  open,
  session,
  baseUrl,
  currentPage,
  onClose,
}) => {
  const totalPages = session?.preflight.page_count ?? 1;
  const clampedCurrent = Math.max(1, Math.min(totalPages, currentPage || 1));

  const [rangeMode, setRangeMode] = useState<PrintRangeMode>("all");
  const [customRange, setCustomRange] = useState<string>(`1-${Math.min(totalPages, 5)}`);
  const [dpi, setDpi] = useState<150 | 240>(240);
  const [preparing, setPreparing] = useState<boolean>(false);
  const [loadedCount, setLoadedCount] = useState<number>(0);
  const [printPages, setPrintPages] = useState<number[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const cancelRef = useRef<boolean>(false);

  useEffect(() => {
    if (open) {
      setRangeMode("all");
      setCustomRange(`1-${Math.min(totalPages, 5)}`);
      setDpi(240);
      setPreparing(false);
      setLoadedCount(0);
      setErrorMsg(null);
      cancelRef.current = false;
    } else {
      cancelRef.current = true;
      setPrintPages([]);
    }
  }, [open, totalPages]);

  useEffect(() => {
    const onAfterPrint = () => {
      setPreparing(false);
    };
    window.addEventListener("afterprint", onAfterPrint);
    return () => window.removeEventListener("afterprint", onAfterPrint);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !preparing) {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, preparing, onClose]);

  const targetSelection = useMemo(() => {
    if (rangeMode === "all") {
      return {
        pages: Array.from({ length: totalPages }, (_, i) => i + 1),
        error: null,
      };
    }
    if (rangeMode === "current") {
      return { pages: [clampedCurrent], error: null };
    }
    return parsePrintPages(customRange, totalPages);
  }, [rangeMode, customRange, totalPages, clampedCurrent]);

  if (!open || !session) return null;

  const handleStartPrint = async () => {
    if (targetSelection.error || targetSelection.pages.length === 0) {
      setErrorMsg(targetSelection.error || "인쇄할 페이지를 선택해 주세요.");
      return;
    }

    cancelRef.current = false;
    setErrorMsg(null);
    setPreparing(true);
    setLoadedCount(0);
    setPrintPages(targetSelection.pages);

    try {
      const pages = targetSelection.pages;
      const concurrency = 4;
      let completed = 0;

      for (let i = 0; i < pages.length; i += concurrency) {
        if (cancelRef.current) return;
        const batch = pages.slice(i, i + concurrency);
        await Promise.all(
          batch.map(async (p) => {
            await preloadImage(sourcePageUrl(baseUrl, session.session_id, p, dpi));
            completed += 1;
            if (!cancelRef.current) {
              setLoadedCount(completed);
            }
          })
        );
      }

      if (cancelRef.current) return;

      // Allow the portal DOM to paint the cached images before opening native print dialog
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
      );

      if (cancelRef.current) return;
      window.print();
    } catch (err) {
      if (!cancelRef.current) {
        setErrorMsg(err instanceof Error ? err.message : "인쇄 준비 중 오류가 발생했습니다.");
      }
    } finally {
      if (!cancelRef.current) {
        setPreparing(false);
      }
    }
  };

  const handleOpenInSystemApp = async () => {
    setErrorMsg(null);
    try {
      await openFileInSystem(session.pdf_path, sourcePdfUrl(baseUrl, session.session_id));
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "기본 PDF 앱으로 열지 못했습니다.");
    }
  };

  return (
    <>
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-[2px]"
        onClick={() => {
          if (!preparing) onClose();
        }}
      >
        <div
          className="w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600 border border-blue-200/80">
                <Printer className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <h2 className="text-base font-bold text-slate-900">PDF 인쇄</h2>
                <p className="truncate text-xs text-slate-500" title={session.file_name}>
                  {session.file_name} ({totalPages}페이지)
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              disabled={preparing}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-40 cursor-pointer"
              aria-label="닫기"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Body */}
          <div className="space-y-4 px-5 py-4 text-sm">
            {/* Page Range */}
            <div>
              <label className="mb-2 block text-xs font-semibold text-slate-600">인쇄 페이지 범위</label>
              <div className="space-y-2">
                <label className="flex items-center justify-between rounded-xl border border-slate-200 px-3.5 py-2.5 hover:bg-slate-50 cursor-pointer">
                  <span className="inline-flex items-center gap-2 text-slate-800 font-medium">
                    <input
                      type="radio"
                      name="print-range"
                      checked={rangeMode === "all"}
                      onChange={() => setRangeMode("all")}
                      disabled={preparing}
                      className="text-blue-600"
                    />
                    전체 페이지
                  </span>
                  <span className="text-xs text-slate-500">1–{totalPages} ({totalPages}장)</span>
                </label>

                <label className="flex items-center justify-between rounded-xl border border-slate-200 px-3.5 py-2.5 hover:bg-slate-50 cursor-pointer">
                  <span className="inline-flex items-center gap-2 text-slate-800 font-medium">
                    <input
                      type="radio"
                      name="print-range"
                      checked={rangeMode === "current"}
                      onChange={() => setRangeMode("current")}
                      disabled={preparing}
                      className="text-blue-600"
                    />
                    현재 보고 있는 페이지
                  </span>
                  <span className="text-xs text-slate-500">{clampedCurrent}페이지 (1장)</span>
                </label>

                <div className="rounded-xl border border-slate-200 px-3.5 py-2.5">
                  <label className="flex items-center gap-2 text-slate-800 font-medium cursor-pointer">
                    <input
                      type="radio"
                      name="print-range"
                      checked={rangeMode === "custom"}
                      onChange={() => setRangeMode("custom")}
                      disabled={preparing}
                      className="text-blue-600"
                    />
                    페이지 직접 지정
                  </label>
                  {rangeMode === "custom" && (
                    <div className="mt-2.5">
                      <input
                        type="text"
                        value={customRange}
                        onChange={(e) => setCustomRange(e.target.value)}
                        disabled={preparing}
                        placeholder="예: 1-3, 5, 8-10"
                        className="w-full rounded-lg border border-slate-300 bg-slate-50 px-3 py-1.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:bg-white focus:outline-none"
                      />
                      {targetSelection.error ? (
                        <p className="mt-1 text-xs text-rose-600">{targetSelection.error}</p>
                      ) : (
                        <p className="mt-1 text-xs text-slate-500">
                          선택됨: {targetSelection.pages.length}페이지
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Print Quality */}
            <div>
              <label className="mb-2 block text-xs font-semibold text-slate-600">인쇄 품질</label>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { value: 150 as const, title: "표준 (150 DPI)", desc: "빠른 준비 · 일반 문서" },
                  { value: 240 as const, title: "고화질 (240 DPI)", desc: "선명한 글자 · 도표 권장" },
                ].map((q) => (
                  <button
                    key={q.value}
                    type="button"
                    disabled={preparing}
                    onClick={() => setDpi(q.value)}
                    className={`rounded-xl border p-2.5 text-left transition-all cursor-pointer ${
                      dpi === q.value
                        ? "border-blue-500 bg-blue-50/80 ring-1 ring-blue-500/20"
                        : "border-slate-200 bg-slate-50/70 hover:border-slate-300"
                    }`}
                  >
                    <div className="text-xs font-semibold text-slate-900">{q.title}</div>
                    <div className="mt-0.5 text-[11px] text-slate-500">{q.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {preparing && (
              <div className="rounded-xl border border-blue-200 bg-blue-50 px-3.5 py-2.5 text-xs text-blue-900">
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-2 font-medium">
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
                    인쇄용 페이지 준비 중...
                  </span>
                  <span className="font-semibold text-blue-700">
                    {loadedCount} / {targetSelection.pages.length}
                  </span>
                </div>
              </div>
            )}

            {errorMsg && (
              <div className="rounded-xl border border-rose-200 bg-rose-50 px-3.5 py-2 text-xs text-rose-700">
                {errorMsg}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3.5">
            <button
              type="button"
              onClick={() => void handleOpenInSystemApp()}
              disabled={preparing}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50 cursor-pointer"
              title="원본 PDF를 OS 기본 PDF 뷰어(미리보기 등)로 엽니다"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              기본 PDF 앱으로 열기
            </button>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onClose}
                disabled={preparing}
                className="rounded-lg border border-slate-300 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50 cursor-pointer"
              >
                취소
              </button>
              <button
                type="button"
                onClick={() => void handleStartPrint()}
                disabled={preparing || Boolean(targetSelection.error)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:bg-slate-300 disabled:text-slate-500 cursor-pointer"
              >
                {preparing ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Printer className="h-3.5 w-3.5" />
                )}
                인쇄하기
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Dedicated Print-Only Portal */}
      {printPages.length > 0 &&
        createPortal(
          <div id="pdf-print-root" aria-hidden="true">
            {printPages.map((p) => (
              <div key={p} className="pdf-print-page">
                <img
                  src={sourcePageUrl(baseUrl, session.session_id, p, dpi)}
                  alt={`${session.file_name} ${p}페이지`}
                />
              </div>
            ))}
          </div>,
          document.body
        )}
    </>
  );
};
