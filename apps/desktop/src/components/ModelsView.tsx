import React, { useEffect, useState } from "react";
import { CheckCircle2, Cpu, Download, HardDrive, Loader2, RefreshCw } from "lucide-react";
import type { ModelsOverviewResponse } from "../types/engine";
import { engineApi } from "../api/client";

export const ModelsView: React.FC = () => {
  const [data, setData] = useState<ModelsOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [warming, setWarming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadModels = async () => {
    try {
      const res = await engineApi.getModels();
      setData(res);
      setWarming(res.warmup_status === "running");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadModels();
  }, []);

  useEffect(() => {
    if (!warming) return;
    const timer = setInterval(() => {
      void loadModels();
    }, 1500);
    return () => clearInterval(timer);
  }, [warming]);

  const handleWarmup = async () => {
    setWarming(true);
    try {
      await engineApi.warmupModels();
      await loadModels();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setWarming(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center text-sm text-slate-600 gap-2">
        <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
        로컬 AI 모델 및 하드웨어 상태를 확인하는 중...
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-3.5 text-sm text-rose-700">
          {error}
        </div>
      )}

      {data && (
        <>
          {/* Hardware Acceleration Card */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="rounded-2xl bg-blue-50 p-3.5 text-blue-600 ring-1 ring-blue-200">
                <Cpu className="h-7 w-7" />
              </div>
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-blue-600">
                  로컬 하드웨어 가속 상태
                </div>
                <h2 className="text-lg font-semibold text-slate-900">
                  {data.hardware.accelerator_label}
                </h2>
                <p className="text-sm text-slate-600">
                  OS: {data.hardware.os} ({data.hardware.arch}) · Python {data.hardware.python_version} ·
                  Docling {data.hardware.docling_version}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={() => void loadModels()}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 cursor-pointer"
              >
                <RefreshCw className="h-4 w-4" />
                새로고침
              </button>
              <button
                type="button"
                onClick={() => void handleWarmup()}
                disabled={warming}
                className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50 cursor-pointer"
              >
                {warming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                {warming ? "모델 워밍업 중..." : "모델 워밍업 / 다운로드"}
              </button>
            </div>
          </div>

          {data.warmup_message && (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-xs">
              상태: <span className="font-semibold text-blue-700">{data.warmup_message}</span>
            </div>
          )}

          {/* Model Cards */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {data.models.map((m) => (
              <div
                key={m.id}
                className="rounded-2xl border border-slate-200 bg-white p-5 shadow-xs flex flex-col justify-between space-y-4"
              >
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-base font-semibold text-slate-900">{m.name}</h3>
                      <p className="text-xs font-medium text-blue-600 mt-0.5">{m.role}</p>
                    </div>
                    <span className="rounded-md border border-slate-200 bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-700">
                      {m.license}
                    </span>
                  </div>
                  <p className="text-sm leading-relaxed text-slate-600">{m.description}</p>
                </div>

                <div className="flex items-center justify-between border-t border-slate-200 pt-3 text-xs">
                  {m.installed ? (
                    <span className="inline-flex items-center gap-1.5 font-semibold text-emerald-700">
                      <CheckCircle2 className="h-4 w-4" />
                      로컬 캐시 준비됨 ({m.size_mb} MB)
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-slate-500">
                      <HardDrive className="h-4 w-4" />
                      첫 변환 또는 워밍업 시 자동 다운로드
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
};
