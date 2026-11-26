import React, { useCallback, useEffect, useState } from "react";
import {
  ArrowUpCircle,
  Cpu,
  LayoutDashboard,
  Loader2,
  SplitSquareHorizontal,
} from "lucide-react";
import type {
  ConvertRequest,
  HealthResponse,
  JobStatusResponse,
  SessionResponse,
  SidecarStatus,
  UpdateCheckResponse,
} from "./types/engine";
import {
  engineApi,
  getAppMeta,
  getEngineBaseUrl,
  getSidecarStatus,
  restartSidecar,
} from "./api/client";
import { DashboardView } from "./components/DashboardView";
import { StudioView } from "./components/StudioView";
import { ModelsView } from "./components/ModelsView";
import { UpdateModal } from "./components/UpdateModal";
import { SponsorIcon, SponsorModal } from "./components/SponsorModal";
import { PdfPresentationModal } from "./components/PdfPresentationModal";
import { PdfPrintModal } from "./components/PdfPrintModal";
import { EngineBootstrapModal } from "./components/EngineBootstrapModal";

type TabId = "dashboard" | "studio" | "models";

export const App: React.FC = () => {
  const [tab, setTab] = useState<TabId>("dashboard");
  const [baseUrl, setBaseUrl] = useState<string>("http://127.0.0.1:18765");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [connecting, setConnecting] = useState<boolean>(true);
  const [sidecarStatus, setSidecarStatus] = useState<SidecarStatus | null>(null);
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [activeJob, setActiveJob] = useState<JobStatusResponse | null>(null);
  const [appVersion, setAppVersion] = useState<string>("1.0.1");
  const [updateInfo, setUpdateInfo] = useState<UpdateCheckResponse | null>(null);
  const [checkingUpdate, setCheckingUpdate] = useState<boolean>(false);
  const [showUpdateModal, setShowUpdateModal] = useState<boolean>(false);
  const [showSponsorModal, setShowSponsorModal] = useState<boolean>(false);
  const [presentationPage, setPresentationPage] = useState<number | null>(null);
  const [printPage, setPrintPage] = useState<number | null>(null);
  const [engineModalDismissed, setEngineModalDismissed] = useState<boolean>(false);

  const runUpdateCheck = useCallback(
    async (verOverride?: string) => {
      setCheckingUpdate(true);
      try {
        const res = await engineApi.checkUpdate(verOverride || appVersion);
        setUpdateInfo(res);
      } catch (err) {
        setUpdateInfo({
          status: "error",
          current_version: verOverride || appVersion,
          latest_version: null,
          has_update: false,
          release_name: null,
          release_notes: null,
          published_at: null,
          release_url: "https://github.com/creatorjosephkr/pdf2md/releases",
          download_url: null,
          repo_url: "https://github.com/creatorjosephkr/pdf2md",
          checked_at: new Date().toISOString(),
          message: err instanceof Error ? err.message : "업데이트 확인 중 오류가 발생했습니다.",
        });
      } finally {
        setCheckingUpdate(false);
      }
    },
    [appVersion]
  );

  const connectToEngine = useCallback(async (restartFirst = false) => {
    setConnecting(true);
    setHealth(null);
    if (restartFirst) {
      await restartSidecar();
    }

    let idleAttempts = 0;
    for (let tick = 0; tick < 600; tick += 1) {
      const st = await getSidecarStatus();
      if (st) setSidecarStatus(st);

      try {
        const url = await getEngineBaseUrl();
        setBaseUrl(url);
        const h = await engineApi.getHealth();
        setHealth(h);
        setConnecting(false);
        return h;
      } catch {
        if (st?.phase === "error") {
          setConnecting(false);
          return null;
        }
        if (!st || (st.phase !== "bootstrapping" && st.phase !== "starting")) {
          idleAttempts += 1;
          if (idleAttempts >= 30) {
            setConnecting(false);
            return null;
          }
        } else {
          idleAttempts = 0;
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
    }
    setConnecting(false);
    return null;
  }, []);

  const checkHealth = async () => {
    setEngineModalDismissed(false);
    const h = await connectToEngine(true);
    if (h) {
      void runUpdateCheck(appVersion);
    }
  };

  useEffect(() => {
    let cancelled = false;

    const boot = async () => {
      const meta = await getAppMeta();
      if (!cancelled && meta.version) {
        setAppVersion(meta.version);
      }

      let idleAttempts = 0;
      for (let tick = 0; tick < 600 && !cancelled; tick += 1) {
        const st = await getSidecarStatus();
        if (!cancelled && st) setSidecarStatus(st);

        try {
          const url = await getEngineBaseUrl();
          if (!cancelled) setBaseUrl(url);
          const h = await engineApi.getHealth();
          if (!cancelled) {
            setHealth(h);
            setConnecting(false);
            void runUpdateCheck(meta.version || "1.0.1");
          }
          return;
        } catch {
          if (st?.phase === "error") {
            if (!cancelled) setConnecting(false);
            return;
          }
          if (!st || (st.phase !== "bootstrapping" && st.phase !== "starting")) {
            idleAttempts += 1;
            if (idleAttempts >= 30) {
              if (!cancelled) setConnecting(false);
              return;
            }
          } else {
            idleAttempts = 0;
          }
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
      if (!cancelled) setConnecting(false);
    };

    void boot();
    return () => {
      cancelled = true;
    };
  }, []);

  // Poll running conversion job
  useEffect(() => {
    if (!activeJob || (activeJob.status !== "queued" && activeJob.status !== "running")) {
      return;
    }
    const timer = setInterval(async () => {
      try {
        const updated = await engineApi.getJob(activeJob.job_id);
        setActiveJob(updated);
        if (updated.status === "completed") {
          setTab("studio");
        }
      } catch {
        // ignore transient poll error
      }
    }, 450);

    return () => clearInterval(timer);
  }, [activeJob?.job_id, activeJob?.status]);

  const handleStartConvert = async (req: ConvertRequest) => {
    const job = await engineApi.startConvert(req);
    setActiveJob(job);
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#F3F4F6] text-slate-900">
      {/* Top Navigation Bar */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200/90 bg-white/95 px-5 backdrop-blur-sm">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2.5">
            <img
              src="/app-icon.png"
              alt="PDF 얼개"
              className="h-9 w-9 rounded-xl shadow-xs select-none"
              draggable={false}
            />
            <div className="flex items-center gap-2">
              <span className="text-base font-bold tracking-tight text-slate-900">PDF 얼개</span>
              <span className="text-xs font-medium text-slate-400">PDF Eolgae</span>
              <span className="rounded-md border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-blue-700">
                PDF → Markdown · RTF
              </span>
            </div>
          </div>

          <nav className="flex items-center gap-1 rounded-xl bg-slate-100 p-1">
            <button
              type="button"
              onClick={() => setTab("dashboard")}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all cursor-pointer ${
                tab === "dashboard"
                  ? "bg-white text-slate-900 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <LayoutDashboard className="h-4 w-4" />
              PDF 변환
            </button>

            <button
              type="button"
              onClick={() => activeJob?.status === "completed" && setTab("studio")}
              disabled={!activeJob || activeJob.status !== "completed"}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all ${
                tab === "studio"
                  ? "bg-white text-slate-900 shadow-xs"
                  : activeJob?.status === "completed"
                    ? "text-slate-600 hover:text-slate-900 cursor-pointer"
                    : "text-slate-400 cursor-not-allowed"
              }`}
            >
              <SplitSquareHorizontal className="h-4 w-4" />
              마크다운 결과
            </button>

            <button
              type="button"
              onClick={() => setTab("models")}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all cursor-pointer ${
                tab === "models"
                  ? "bg-white text-slate-900 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Cpu className="h-4 w-4" />
              로컬 모델
            </button>
          </nav>
        </div>

        {/* Sidecar Engine Status Pill, Update Check & Sponsor */}
        <div className="flex items-center gap-2.5 text-xs">
          {connecting ? (
            <button
              type="button"
              onClick={() => setEngineModalDismissed(false)}
              className="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100 cursor-pointer"
              title="로컬 엔진 준비 상태 자세히 보기"
            >
              <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
              {sidecarStatus?.phase === "bootstrapping"
                ? "엔진 최초 설치 중..."
                : "로컬 엔진 연결 중..."}
            </button>
          ) : health ? (
            <span className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              엔진 온라인 · {health.hardware.accelerator_label}
            </span>
          ) : (
            <button
              type="button"
              onClick={() => void checkHealth()}
              className="inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800 hover:bg-amber-100 cursor-pointer"
            >
              엔진 오프라인 — 재연결 시도
            </button>
          )}

          <button
            type="button"
            onClick={() => {
              setShowUpdateModal(true);
              if (!updateInfo || updateInfo.status === "error") {
                void runUpdateCheck();
              }
            }}
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors cursor-pointer ${
              updateInfo?.has_update
                ? "border-blue-300 bg-blue-50 text-blue-700 hover:bg-blue-100"
                : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            }`}
            title="GitHub 릴리즈 업데이트 확인"
          >
            {checkingUpdate ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
            ) : updateInfo?.has_update ? (
              <ArrowUpCircle className="h-3.5 w-3.5 text-blue-600" />
            ) : null}
            {updateInfo?.has_update && updateInfo.latest_version
              ? `v${updateInfo.latest_version} 업데이트`
              : `v${appVersion}`}
          </button>

          <button
            type="button"
            onClick={() => setShowSponsorModal(true)}
            className="inline-flex items-center justify-center bg-transparent p-1 text-slate-600 hover:text-slate-900 transition-colors cursor-pointer"
            title="후원하기"
            aria-label="후원하기"
          >
            <SponsorIcon className="h-6 w-6" />
          </button>
        </div>
      </header>

      {/* First-Run Bootstrap or Sidecar Error Banner (shown when modal is dismissed) */}
      {!health &&
        engineModalDismissed &&
        sidecarStatus &&
        (sidecarStatus.phase === "bootstrapping" || sidecarStatus.phase === "error") && (
        <div
          className={`flex flex-wrap items-center justify-between gap-2 border-b px-5 py-2 text-xs ${
            sidecarStatus.phase === "error"
              ? "border-amber-200 bg-amber-50 text-amber-900"
              : "border-blue-200 bg-blue-50 text-blue-900"
          }`}
        >
          <div className="flex min-w-0 items-center gap-2">
            {sidecarStatus.phase === "bootstrapping" && (
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-blue-600" />
            )}
            <span className="font-semibold">{sidecarStatus.message}</span>
            {sidecarStatus.last_log && (
              <span className="hidden truncate font-mono text-[11px] opacity-75 md:inline max-w-[460px]">
                {sidecarStatus.last_log}
              </span>
            )}
          </div>
          {sidecarStatus.phase === "error" && (
            <button
              type="button"
              onClick={() => void checkHealth()}
              className="rounded-lg border border-amber-300 bg-white px-2.5 py-1 text-xs font-semibold text-amber-900 hover:bg-amber-100 cursor-pointer"
            >
              엔진 재시작
            </button>
          )}
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1 min-h-0 overflow-y-auto">
        {tab === "dashboard" && (
          <DashboardView
            session={session}
            baseUrl={baseUrl}
            activeJob={activeJob}
            engineReady={Boolean(health)}
            engineStatusMessage={sidecarStatus?.message || null}
            onSessionLoaded={(sess) => {
              setSession(sess);
              setActiveJob(null);
            }}
            onClearSession={() => {
              setSession(null);
              setActiveJob(null);
            }}
            onStartConvert={(req) => void handleStartConvert(req)}
            onOpenStudio={() => setTab("studio")}
            onOpenPresentation={(pageNo) => setPresentationPage(pageNo)}
            onOpenPrint={(pageNo) => setPrintPage(pageNo)}
          />
        )}

        {tab === "studio" && activeJob && activeJob.status === "completed" && (
          <StudioView
            job={activeJob}
            fileName={session?.file_name || "document.pdf"}
            baseUrl={baseUrl}
            onJobUpdated={(updated) => setActiveJob(updated)}
            onBackToDashboard={() => setTab("dashboard")}
            onOpenPresentation={(pageNo) => setPresentationPage(pageNo)}
            onOpenPrint={(pageNo) => setPrintPage(pageNo)}
          />
        )}

        {tab === "models" && <ModelsView />}
      </main>

      <UpdateModal
        open={showUpdateModal}
        appVersion={appVersion}
        checking={checkingUpdate}
        updateInfo={updateInfo}
        onCheckAgain={() => void runUpdateCheck()}
        onClose={() => setShowUpdateModal(false)}
      />

      <SponsorModal
        open={showSponsorModal}
        onClose={() => setShowSponsorModal(false)}
      />

      <PdfPresentationModal
        open={presentationPage !== null}
        session={session}
        baseUrl={baseUrl}
        initialPage={presentationPage ?? 1}
        onClose={() => setPresentationPage(null)}
        onOpenPrint={(pageNo) => {
          setPresentationPage(null);
          setPrintPage(pageNo);
        }}
      />

      <PdfPrintModal
        open={printPage !== null}
        session={session}
        baseUrl={baseUrl}
        currentPage={printPage ?? 1}
        onClose={() => setPrintPage(null)}
      />

      <EngineBootstrapModal
        open={!health && !engineModalDismissed}
        connecting={connecting}
        sidecarStatus={sidecarStatus}
        onRetry={() => void checkHealth()}
        onDismiss={() => setEngineModalDismissed(true)}
      />
    </div>
  );
};
export default App;
