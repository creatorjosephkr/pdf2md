import { invoke } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";
import { openUrl } from "@tauri-apps/plugin-opener";
import type {
  AppMeta,
  ConvertRequest,
  HealthResponse,
  JobStatusResponse,
  MarkdownImageMode,
  MarkdownPreviewResponse,
  ModelsOverviewResponse,
  ReconvertPageRequest,
  SessionResponse,
  SidecarStatus,
  UpdateCheckResponse,
} from "../types/engine";

const FALLBACK_URL =
  (import.meta.env.VITE_ENGINE_URL as string | undefined) || "http://127.0.0.1:18765";

let cachedBaseUrl: string | null = null;

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function getEngineBaseUrl(): Promise<string> {
  if (cachedBaseUrl) return cachedBaseUrl;
  if (isTauriRuntime()) {
    try {
      const url = await invoke<string>("get_engine_url");
      if (url) {
        cachedBaseUrl = url;
        return url;
      }
    } catch {
      // Fallback to default port if invoke unavailable
    }
  }
  cachedBaseUrl = FALLBACK_URL;
  return cachedBaseUrl;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const base = await getEngineBaseUrl();
  const res = await fetch(`${base}${path}`, init);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const errBody = (await res.json()) as { detail?: string };
      if (errBody.detail) msg = errBody.detail;
    } catch {
      // ignore json parse error
    }
    throw new Error(msg);
  }
  return (await res.json()) as T;
}

export const engineApi = {
  getHealth: () => apiFetch<HealthResponse>("/api/health"),
  openPdfPath: (pdfPath: string, pages?: string | null) =>
    apiFetch<SessionResponse>("/api/sessions/open-path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pdf_path: pdfPath, pages: pages || null }),
    }),
  uploadPdf: async (file: File, pages?: string | null): Promise<SessionResponse> => {
    const form = new FormData();
    form.append("file", file);
    if (pages) form.append("pages", pages);
    return apiFetch<SessionResponse>("/api/sessions/upload", {
      method: "POST",
      body: form,
    });
  },
  startConvert: (req: ConvertRequest) =>
    apiFetch<JobStatusResponse>("/api/jobs/convert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  getJob: (jobId: string) => apiFetch<JobStatusResponse>(`/api/jobs/${jobId}`),
  reconvertPage: (jobId: string, req: ReconvertPageRequest) =>
    apiFetch<JobStatusResponse>(`/api/jobs/${jobId}/reconvert-page`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  getJobMarkdown: (jobId: string, imageMode: MarkdownImageMode = "folder") =>
    apiFetch<MarkdownPreviewResponse>(
      `/api/jobs/${jobId}/markdown?image_mode=${encodeURIComponent(imageMode)}`
    ),
  exportMarkdownToPath: (
    jobId: string,
    destinationPath: string,
    imageMode: MarkdownImageMode = "folder",
    overrideMarkdown?: string | null
  ) =>
    apiFetch<{ exported_path: string; assets_dir: string | null; assets_copied: number }>(
      `/api/jobs/${jobId}/export-markdown-to`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          destination_path: destinationPath,
          image_mode: imageMode,
          override_markdown: overrideMarkdown ?? null,
        }),
      }
    ),
  exportRtfToPath: (
    jobId: string,
    destinationPath: string,
    overrideMarkdown?: string | null
  ) =>
    apiFetch<{ exported_path: string; byte_size: number; embedded_images: number }>(
      `/api/jobs/${jobId}/export-rtf-to`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          destination_path: destinationPath,
          override_markdown: overrideMarkdown ?? null,
        }),
      }
    ),
  downloadRtfBlob: async (
    jobId: string,
    overrideMarkdown?: string | null
  ): Promise<Blob> => {
    const base = await getEngineBaseUrl();
    const res = await fetch(`${base}/api/jobs/${jobId}/download-rtf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ override_markdown: overrideMarkdown ?? null }),
    });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const errBody = (await res.json()) as { detail?: string };
        if (errBody.detail) msg = errBody.detail;
      } catch {
        // ignore json parse error
      }
      throw new Error(msg);
    }
    return await res.blob();
  },
  getModels: () => apiFetch<ModelsOverviewResponse>("/api/models"),
  warmupModels: () =>
    apiFetch<{ status: string; message: string }>("/api/models/warmup", {
      method: "POST",
    }),
  checkUpdate: (currentVersion?: string) => {
    const query = currentVersion ? `?current_version=${encodeURIComponent(currentVersion)}` : "";
    return apiFetch<UpdateCheckResponse>(`/api/updates/check${query}`);
  },
};

export function sourcePageUrl(baseUrl: string, sessionId: string, pageNo: number, dpi = 180): string {
  return `${baseUrl}/api/sessions/${sessionId}/pages/${pageNo}/source.png?dpi=${dpi}`;
}

export function downloadMarkdownUrl(
  baseUrl: string,
  jobId: string,
  imageMode: MarkdownImageMode = "base64"
): string {
  return `${baseUrl}/api/jobs/${jobId}/download-markdown?image_mode=${encodeURIComponent(imageMode)}`;
}

export function jobAssetUrl(baseUrl: string, jobId: string, rawSrc: string): string {
  const trimmed = rawSrc.trim();
  if (
    !trimmed ||
    trimmed.startsWith("data:") ||
    trimmed.startsWith("http://") ||
    trimmed.startsWith("https://") ||
    trimmed.startsWith("blob:")
  ) {
    return trimmed;
  }
  const clean = trimmed.split(/[?#]/)[0];
  const segments = clean.split(/[/\\]/).filter(Boolean);
  const filename = segments[segments.length - 1] || clean;
  return `${baseUrl}/api/jobs/${jobId}/assets/${encodeURIComponent(filename)}`;
}

export async function pickNativePdfPath(): Promise<string | null> {
  if (!isTauriRuntime()) return null;
  const selected = await open({
    multiple: false,
    directory: false,
    filters: [{ name: "PDF Documents", extensions: ["pdf"] }],
  });
  return typeof selected === "string" ? selected : null;
}

export async function pickSaveMarkdownPath(defaultName: string): Promise<string | null> {
  if (!isTauriRuntime()) return null;
  const selected = await save({
    defaultPath: defaultName,
    filters: [{ name: "Markdown Document (.md)", extensions: ["md", "markdown"] }],
  });
  return selected || null;
}

export async function pickSaveRtfPath(defaultName: string): Promise<string | null> {
  if (!isTauriRuntime()) return null;
  const selected = await save({
    defaultPath: defaultName,
    filters: [{ name: "Rich Text Format (.rtf)", extensions: ["rtf"] }],
  });
  return selected || null;
}

export async function getAppMeta(): Promise<AppMeta> {
  if (isTauriRuntime()) {
    try {
      return await invoke<AppMeta>("get_app_meta");
    } catch {
      // Fallback below
    }
  }
  return { os: "web", arch: "web", version: "1.0.0", is_tauri: false };
}

export async function getSidecarStatus(): Promise<SidecarStatus | null> {
  if (!isTauriRuntime()) return null;
  try {
    return await invoke<SidecarStatus>("get_sidecar_status");
  } catch {
    return null;
  }
}

export async function restartSidecar(): Promise<void> {
  if (!isTauriRuntime()) return;
  try {
    await invoke("restart_sidecar");
  } catch {
    // Ignore invoke failure
  }
}

export async function openExternalUrl(url: string): Promise<void> {
  if (isTauriRuntime()) {
    try {
      await openUrl(url);
      return;
    } catch {
      // Fall back to browser window.open
    }
  }
  window.open(url, "_blank", "noopener,noreferrer");
}
