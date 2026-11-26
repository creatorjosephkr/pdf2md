import React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Terminal,
  X,
} from "lucide-react";
import type { SidecarStatus } from "../types/engine";

interface EngineBootstrapModalProps {
  open: boolean;
  connecting: boolean;
  sidecarStatus: SidecarStatus | null;
  onRetry: () => void;
  onDismiss: () => void;
}

type StepState = "done" | "active" | "pending" | "error";

function getStepStates(
  connecting: boolean,
  phase: string | undefined
): [StepState, StepState, StepState] {
  if (phase === "error" || !connecting) {
    if (phase === "bootstrapping") return ["error", "pending", "pending"];
    if (phase === "starting") return ["done", "error", "pending"];
    return ["done", "done", "error"];
  }
  if (phase === "bootstrapping") {
    return ["active", "pending", "pending"];
  }
  if (phase === "running") {
    return ["done", "done", "active"];
  }
  // Default "starting" or initial connecting
  return ["done", "active", "pending"];
}

export const EngineBootstrapModal: React.FC<EngineBootstrapModalProps> = ({
  open,
  connecting,
  sidecarStatus,
  onRetry,
  onDismiss,
}) => {
  if (!open) return null;

  const phase = sidecarStatus?.phase;
  const isError = phase === "error" || !connecting;
  const isBootstrapping = phase === "bootstrapping" && connecting;
  const [step1, step2, step3] = getStepStates(connecting, phase);

  const steps: { title: string; desc: string; state: StepState }[] = [
    {
      title: "로컬 실행 환경 구성",
      desc: "Python 3.12 및 로컬 AI 분석 패키지 확인·설치",
      state: step1,
    },
    {
      title: "로컬 엔진 서버 기동",
      desc: "내 PC 전용 변환 엔진(127.0.0.1) 시작",
      state: step2,
    },
    {
      title: "엔진 상태 및 가속기 연결",
      desc: "하드웨어 가속(MPS / CUDA / CPU) 점검 완료",
      state: step3,
    },
  ];

  const progressPct = isError
    ? 100
    : phase === "bootstrapping"
      ? 36
      : phase === "running"
        ? 88
        : 65;

  const renderStepIcon = (state: StepState) => {
    if (state === "done") {
      return <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />;
    }
    if (state === "active") {
      return <Loader2 className="h-4 w-4 shrink-0 animate-spin text-blue-600" />;
    }
    if (state === "error") {
      return <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />;
    }
    return <span className="h-4 w-4 shrink-0 rounded-full border-2 border-slate-300 bg-white" />;
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/45 p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-label="로컬 변환 엔진 준비 상태"
    >
      <div className="w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-3">
            <img
              src="/app-icon.png"
              alt="PDF 얼개"
              className="h-10 w-10 shrink-0 rounded-xl shadow-xs select-none"
              draggable={false}
            />
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-bold text-slate-900">
                  {isError
                    ? "로컬 엔진 연결 확인 필요"
                    : isBootstrapping
                      ? "로컬 AI 엔진 최초 설치 중"
                      : "로컬 변환 엔진 준비 중"}
                </h2>
                {isBootstrapping ? (
                  <span className="rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-blue-700">
                    최초 1회 · 약 1~2분
                  </span>
                ) : isError ? (
                  <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800">
                    오프라인
                  </span>
                ) : (
                  <span className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
                    잠시만 기다려 주세요
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-xs text-slate-500">
                PDF 얼개 (PDF Eolgae) 로컬 변환 엔진
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onDismiss}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 cursor-pointer"
            title="백그라운드에서 계속 준비"
            aria-label="창 닫기"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-4 px-5 py-4">
          {/* Primary Status Callout */}
          <div
            className={`rounded-xl border px-4 py-3 ${
              isError
                ? "border-amber-200 bg-amber-50 text-amber-950"
                : "border-blue-200 bg-blue-50/80 text-blue-950"
            }`}
          >
            <div className="flex items-start gap-2.5">
              {isError ? (
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              ) : (
                <Cpu className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
              )}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold leading-snug">
                  {sidecarStatus?.message ||
                    (isError
                      ? "로컬 변환 엔진에 연결하지 못했습니다. 엔진을 다시 시작해 주세요."
                      : "로컬 변환 엔진을 시작하고 있습니다...")}
                </p>
                {!isError && (
                  <div className="mt-2.5 h-2 w-full overflow-hidden rounded-full bg-blue-100">
                    <div
                      className="h-full rounded-full bg-blue-600 transition-all duration-500 animate-pulse"
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* 3-Step Checklist */}
          <div className="space-y-2.5 rounded-xl border border-slate-200 bg-slate-50/70 p-3.5">
            {steps.map((s) => (
              <div key={s.title} className="flex items-start gap-2.5">
                <div className="mt-0.5">{renderStepIcon(s.state)}</div>
                <div className="min-w-0">
                  <div
                    className={`text-xs font-semibold ${
                      s.state === "active"
                        ? "text-blue-700"
                        : s.state === "done"
                          ? "text-slate-900"
                          : s.state === "error"
                            ? "text-amber-800"
                            : "text-slate-400"
                    }`}
                  >
                    {s.title}
                  </div>
                  <div className="text-[11px] text-slate-500">{s.desc}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Live Log Tail */}
          {sidecarStatus?.last_log && (
            <div className="rounded-xl border border-slate-200 bg-slate-900 px-3.5 py-2.5 text-[11px] text-slate-200">
              <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                <Terminal className="h-3 w-3" />
                최근 진행 로그
              </div>
              <p className="break-all font-mono leading-relaxed text-slate-100">
                {sidecarStatus.last_log}
              </p>
            </div>
          )}

          {/* Privacy / First-Run Reassurance */}
          <div className="flex items-start gap-2 text-xs leading-relaxed text-slate-500">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
            <p>
              {isError && sidecarStatus?.log_path ? (
                <>
                  문제가 계속되면 로그 파일(
                  <span className="font-mono text-[11px] text-slate-700">
                    {sidecarStatus.log_path}
                  </span>
                  )을 확인하거나 아래 <strong>엔진 재시작</strong>을 눌러 주세요.
                </>
              ) : (
                "최초 1회 설치 후에는 다음 실행부터 빠르게 시작됩니다. 모든 PDF 분석과 변환은 외부 전송 없이 내 PC에서만 처리됩니다."
              )}
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3">
          {isError ? (
            <>
              <button
                type="button"
                onClick={onDismiss}
                className="rounded-lg border border-slate-300 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 cursor-pointer"
              >
                닫기
              </button>
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 cursor-pointer"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                엔진 재시작
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={onDismiss}
              className="rounded-lg border border-slate-300 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 cursor-pointer"
            >
              백그라운드에서 계속 준비
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
