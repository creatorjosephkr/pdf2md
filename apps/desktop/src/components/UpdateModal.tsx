import React from "react";
import {
  AlertCircle,
  ArrowUpCircle,
  CheckCircle2,
  Download,
  ExternalLink,
  Info,
  Loader2,
  RefreshCw,
  X,
} from "lucide-react";
import type { UpdateCheckResponse } from "../types/engine";
import { openExternalUrl } from "../api/client";

interface UpdateModalProps {
  open: boolean;
  appVersion: string;
  checking: boolean;
  updateInfo: UpdateCheckResponse | null;
  onCheckAgain: () => void;
  onClose: () => void;
}

const GITHUB_RELEASES_FALLBACK = "https://github.com/creatorjosephkr/pdf2md/releases";

export const UpdateModal: React.FC<UpdateModalProps> = ({
  open,
  appVersion,
  checking,
  updateInfo,
  onCheckAgain,
  onClose,
}) => {
  if (!open) return null;

  const status = updateInfo?.status;
  const currentVer = updateInfo?.current_version || appVersion;
  const latestVer = updateInfo?.latest_version;
  const releaseUrl = updateInfo?.release_url || GITHUB_RELEASES_FALLBACK;
  const downloadUrl = updateInfo?.download_url || null;

  const publishedDate = updateInfo?.published_at
    ? new Date(updateInfo.published_at).toLocaleDateString("ko-KR", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 p-4 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-3">
            <img
              src="/app-icon.png"
              alt="PDF 얼개"
              className="h-9 w-9 rounded-xl shadow-xs select-none"
              draggable={false}
            />
            <div>
              <h2 className="text-base font-bold text-slate-900">소프트웨어 업데이트 확인</h2>
              <p className="text-xs text-slate-500">GitHub · creatorjosephkr/pdf2md</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 cursor-pointer"
            aria-label="닫기"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-4 px-5 py-5">
          {/* Version summary cards */}
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
              <div className="text-xs font-medium text-slate-500">현재 설치 버전</div>
              <div className="mt-1 text-base font-bold text-slate-900">v{currentVer}</div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
              <div className="text-xs font-medium text-slate-500">최신 GitHub 릴리즈</div>
              <div className="mt-1 text-base font-bold text-slate-900">
                {checking ? (
                  <span className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500">
                    <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                    확인 중...
                  </span>
                ) : latestVer ? (
                  <span className={updateInfo?.has_update ? "text-blue-700" : "text-slate-900"}>
                    v{latestVer}
                  </span>
                ) : (
                  <span className="text-sm font-medium text-slate-500">릴리즈 없음</span>
                )}
              </div>
            </div>
          </div>

          {/* Status Banner */}
          {!checking && updateInfo && (
            <div
              className={`flex items-start gap-2.5 rounded-xl border px-4 py-3 text-sm ${
                status === "update_available"
                  ? "border-blue-200 bg-blue-50 text-blue-900"
                  : status === "up_to_date"
                    ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                    : status === "no_release"
                      ? "border-slate-200 bg-slate-50 text-slate-700"
                      : "border-amber-200 bg-amber-50 text-amber-900"
              }`}
            >
              {status === "update_available" ? (
                <ArrowUpCircle className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
              ) : status === "up_to_date" ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
              ) : status === "no_release" ? (
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
              ) : (
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              )}
              <div className="space-y-0.5">
                <div className="font-semibold">{updateInfo.message}</div>
                {publishedDate && (
                  <div className="text-xs opacity-80">게시일: {publishedDate}</div>
                )}
              </div>
            </div>
          )}

          {/* Release Notes */}
          {updateInfo?.release_notes && (
            <div className="space-y-1.5">
              <div className="text-xs font-semibold text-slate-600">
                릴리즈 노트 {updateInfo.release_name ? `· ${updateInfo.release_name}` : ""}
              </div>
              <div className="max-h-48 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-3.5 text-xs leading-relaxed text-slate-700 whitespace-pre-wrap">
                {updateInfo.release_notes}
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-slate-50/70 px-5 py-3.5 rounded-b-2xl">
          <button
            type="button"
            onClick={onCheckAgain}
            disabled={checking}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50 cursor-pointer"
          >
            {checking ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            다시 확인
          </button>

          <div className="flex items-center gap-2">
            {updateInfo?.has_update && downloadUrl && (
              <button
                type="button"
                onClick={() => void openExternalUrl(downloadUrl)}
                className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-blue-700 cursor-pointer"
              >
                <Download className="h-3.5 w-3.5" />
                설치 파일 다운로드
              </button>
            )}
            <button
              type="button"
              onClick={() => void openExternalUrl(releaseUrl)}
              className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 px-3.5 py-2 text-xs font-semibold text-white hover:bg-slate-800 cursor-pointer"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              GitHub 릴리즈 열기
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
