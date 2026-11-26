"""FastAPI HTTP server exposing the local Academic PDF -> Markdown conversion engine."""

from __future__ import annotations

import argparse
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from pdf_convert_engine import __version__
from pdf_convert_engine.server.hardware import detect_hardware, inspect_local_models
from pdf_convert_engine.server.models import (
    ConvertRequest,
    DownloadRtfRequest,
    ExportMarkdownRequest,
    ExportRtfRequest,
    JobStatusResponse,
    MarkdownPreviewResponse,
    MarkdownStats,
    ModelsOverviewResponse,
    OpenPathRequest,
    ReconvertPageRequest,
    SessionResponse,
    UpdateCheckResponse,
)
from pdf_convert_engine.server.state import EngineWorkspaceStore
from pdf_convert_engine.server.updater import check_github_release


def create_app(data_dir: Path | None = None) -> FastAPI:
    store = EngineWorkspaceStore(data_dir=data_dir)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        store.shutdown()

    app = FastAPI(
        title="PDF 얼개 (PDF Eolgae) Local Conversion Engine",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.store = store

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:1420",
            "http://127.0.0.1:1420",
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ],
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "hardware": detect_hardware().model_dump(),
        }

    @app.get("/api/updates/check", response_model=UpdateCheckResponse)
    def check_updates(current_version: str | None = None) -> UpdateCheckResponse:
        return check_github_release(current_version=current_version)

    @app.post("/api/sessions/open-path", response_model=SessionResponse)
    def open_path(req: OpenPathRequest) -> SessionResponse:
        try:
            return store.create_session_from_path(
                Path(req.pdf_path),
                pages=req.pages,
                display_name=req.display_name,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/sessions/upload", response_model=SessionResponse)
    async def upload_pdf(
        file: UploadFile = File(...),
        pages: str | None = Form(None),
    ) -> SessionResponse:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty PDF upload")
        try:
            return store.create_session_from_bytes(file.filename or "document.pdf", data, pages=pages)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/sessions/{session_id}/pages/{page_no}/source.png")
    def get_source_page_png(session_id: str, page_no: int, dpi: int = 180) -> FileResponse:
        try:
            png_path = store.render_source_page_png(session_id, page_no, dpi=dpi)
            return FileResponse(png_path, media_type="image/png")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except IndexError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/sessions/{session_id}/source.pdf")
    def get_source_pdf(session_id: str) -> FileResponse:
        try:
            rec = store.get_session(session_id)
            if not rec.pdf_path.exists():
                raise FileNotFoundError(f"PDF file not found: {rec.pdf_path}")
            return FileResponse(
                rec.pdf_path,
                media_type="application/pdf",
                content_disposition_type="inline",
                filename=rec.file_name,
            )
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/jobs/convert", response_model=JobStatusResponse)
    def start_convert(req: ConvertRequest) -> JobStatusResponse:
        try:
            return store.start_conversion_job(req)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
    def get_job(job_id: str) -> JobStatusResponse:
        try:
            return store.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/jobs/{job_id}/reconvert-page", response_model=JobStatusResponse)
    def reconvert_page(job_id: str, req: ReconvertPageRequest) -> JobStatusResponse:
        try:
            return store.reconvert_single_page(job_id, req)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/jobs/{job_id}/markdown", response_model=MarkdownPreviewResponse)
    def get_markdown_preview(
        job_id: str,
        image_mode: Literal["folder", "base64", "none"] = "folder",
    ) -> MarkdownPreviewResponse:
        try:
            res = store.get_job_markdown(job_id, image_mode=image_mode)
            return MarkdownPreviewResponse(
                markdown=res.markdown_text,
                stats=MarkdownStats(
                    char_count=res.char_count,
                    headings=res.headings,
                    tables=res.tables,
                    figures=res.figures,
                    formulas=res.formulas,
                    callouts=res.callouts,
                    assets_copied=res.assets_copied,
                ),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/jobs/{job_id}/download-markdown")
    def download_markdown(
        job_id: str,
        image_mode: Literal["folder", "base64", "none"] = "base64",
    ) -> Response:
        try:
            job = store.get_job_record(job_id)
            res = store.get_job_markdown(job_id, image_mode=image_mode)
            md_name = f"{job.md_path.stem}.md"
            return Response(
                content=res.markdown_text,
                media_type="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{md_name}"'},
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/jobs/{job_id}/assets/{filename}")
    def get_job_asset(job_id: str, filename: str) -> FileResponse:
        try:
            asset_path = store.resolve_job_asset_path(job_id, filename)
            media_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
            return FileResponse(asset_path, media_type=media_type)
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/jobs/{job_id}/export-markdown-to")
    def export_markdown(job_id: str, req: ExportMarkdownRequest) -> dict:
        try:
            return store.export_markdown_to(
                job_id,
                req.destination_path,
                image_mode=req.image_mode,
                override_markdown=req.override_markdown,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/jobs/{job_id}/export-rtf-to")
    def export_rtf(job_id: str, req: ExportRtfRequest) -> dict:
        try:
            return store.export_rtf_to(
                job_id,
                req.destination_path,
                override_markdown=req.override_markdown,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/jobs/{job_id}/download-rtf")
    def download_rtf(job_id: str, req: DownloadRtfRequest | None = None) -> Response:
        try:
            job = store.get_job_record(job_id)
            res = store.compile_job_rtf(
                job_id,
                override_markdown=req.override_markdown if req else None,
            )
            rtf_name = f"{job.md_path.stem}.rtf"
            return Response(
                content=res.rtf_text.encode("ascii", errors="strict"),
                media_type="application/rtf",
                headers={"Content-Disposition": f'attachment; filename="{rtf_name}"'},
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/models", response_model=ModelsOverviewResponse)
    def get_models() -> ModelsOverviewResponse:
        return ModelsOverviewResponse(
            hardware=detect_hardware(),
            models=inspect_local_models(),
            warmup_status=store.warmup_status,  # type: ignore[arg-type]
            warmup_message=store.warmup_message,
        )

    @app.post("/api/models/warmup")
    def warmup_models() -> dict[str, str]:
        return store.trigger_model_warmup()

    return app


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="PDF 얼개 (PDF Eolgae) Local FastAPI Sidecar")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args()
    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    run_cli()
