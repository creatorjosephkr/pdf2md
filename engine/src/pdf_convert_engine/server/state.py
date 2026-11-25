"""Workspace session, async Markdown conversion queue, and page image cache."""

from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from pdf_convert_engine.compiler import (
    MarkdownCompileResult,
    MarkdownCompiler,
    MarkdownOptions,
    MarkdownToRtfCompiler,
    RtfCompileResult,
)
from pdf_convert_engine.ir.schema import DocumentIR, PageIR, PreflightReport
from pdf_convert_engine.parsers import ParseOptions, get_parser
from pdf_convert_engine.parsers.cropper import PDFIUM_LOCK, PageCropper
from pdf_convert_engine.preflight import analyze_pdf
from pdf_convert_engine.server.hardware import warmup_docling_models
from pdf_convert_engine.server.models import (
    ConvertRequest,
    JobStatusResponse,
    MarkdownStats,
    ReconvertPageRequest,
    SessionResponse,
)


def parse_page_range_str(pages_str: str | None) -> tuple[int, int] | None:
    if not pages_str or not pages_str.strip():
        return None
    s = pages_str.strip()
    if "-" in s:
        a, b = s.split("-", 1)
        return int(a.strip()), int(b.strip())
    n = int(s)
    return n, n


def _to_stats(res: MarkdownCompileResult) -> MarkdownStats:
    return MarkdownStats(
        char_count=res.char_count,
        headings=res.headings,
        tables=res.tables,
        figures=res.figures,
        formulas=res.formulas,
        callouts=res.callouts,
        assets_copied=res.assets_copied,
    )


@dataclass
class _SessionRecord:
    session_id: str
    file_name: str
    pdf_path: Path
    work_dir: Path
    preflight: PreflightReport


@dataclass
class _JobRecord:
    job_id: str
    session_id: str
    work_dir: Path
    assets_dir: Path
    md_path: Path
    ir_path: Path
    options: ConvertRequest
    status: str = "queued"
    progress_pct: int = 0
    stage: str = "대기 중"
    error: str | None = None
    markdown: str | None = None
    stats: MarkdownStats | None = None
    ir: DocumentIR | None = None


class EngineWorkspaceStore:
    """Thread-safe workspace managing PDF sessions, rendered pages, and Markdown jobs."""

    def __init__(self, data_dir: Path | None = None) -> None:
        base = data_dir or Path(os.environ.get("PDF_CONVERT_DATA_DIR", Path.home() / ".cache" / "pdf-convert"))
        self.sessions_root = base / "sessions"
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._sessions: dict[str, _SessionRecord] = {}
        self._jobs: dict[str, _JobRecord] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pdf-md")
        self.warmup_status: str = "idle"
        self.warmup_message: str | None = None

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)

    def create_session_from_path(self, pdf_path: Path, pages: str | None = None) -> SessionResponse:
        resolved = pdf_path.expanduser().resolve()
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"PDF file not found: {resolved}")

        sid = uuid.uuid4().hex[:12]
        work_dir = self.sessions_root / sid
        work_dir.mkdir(parents=True, exist_ok=True)

        prange = parse_page_range_str(pages)
        preflight = analyze_pdf(resolved, page_range=prange)

        rec = _SessionRecord(
            session_id=sid,
            file_name=resolved.name,
            pdf_path=resolved,
            work_dir=work_dir,
            preflight=preflight,
        )
        with self._lock:
            self._sessions[sid] = rec

        return SessionResponse(
            session_id=sid,
            file_name=rec.file_name,
            pdf_path=str(rec.pdf_path),
            preflight=preflight,
        )

    def create_session_from_bytes(self, filename: str, data: bytes, pages: str | None = None) -> SessionResponse:
        sid = uuid.uuid4().hex[:12]
        work_dir = self.sessions_root / sid
        work_dir.mkdir(parents=True, exist_ok=True)

        safe_name = Path(filename or "document.pdf").name
        if not safe_name.lower().endswith(".pdf"):
            safe_name = f"{safe_name}.pdf"
        stored_pdf = work_dir / safe_name
        stored_pdf.write_bytes(data)

        prange = parse_page_range_str(pages)
        preflight = analyze_pdf(stored_pdf, page_range=prange)

        rec = _SessionRecord(
            session_id=sid,
            file_name=safe_name,
            pdf_path=stored_pdf,
            work_dir=work_dir,
            preflight=preflight,
        )
        with self._lock:
            self._sessions[sid] = rec

        return SessionResponse(
            session_id=sid,
            file_name=rec.file_name,
            pdf_path=str(rec.pdf_path),
            preflight=preflight,
        )

    def get_session(self, session_id: str) -> _SessionRecord:
        with self._lock:
            rec = self._sessions.get(session_id)
        if rec is None:
            raise KeyError(f"Unknown session_id: {session_id}")
        return rec

    def render_source_page_png(self, session_id: str, page_no: int, dpi: int = 180) -> Path:
        rec = self.get_session(session_id)
        if page_no < 1 or page_no > rec.preflight.page_count:
            raise IndexError(f"Page {page_no} out of range (1..{rec.preflight.page_count})")

        clamped_dpi = max(72, min(300, dpi))
        cache_dir = rec.work_dir / "source_pages"
        cache_dir.mkdir(parents=True, exist_ok=True)
        out_png = cache_dir / f"p{page_no}_{clamped_dpi}dpi.png"
        if not out_png.exists():
            with PDFIUM_LOCK:
                if not out_png.exists():
                    tmp_png = cache_dir / f".tmp_{uuid.uuid4().hex[:8]}_p{page_no}.png"
                    with PageCropper(rec.pdf_path) as cropper:
                        img = cropper.render_page(page_no, dpi=clamped_dpi)
                        img.save(tmp_png, format="PNG")
                    os.replace(tmp_png, out_png)
        return out_png

    def _build_md_options(self, req: ConvertRequest, image_mode_override: str | None = None) -> MarkdownOptions:
        return MarkdownOptions(
            image_mode=(image_mode_override or req.image_mode),  # type: ignore[arg-type]
            complex_table_html=req.complex_table_html,
            include_frontmatter=req.include_frontmatter,
        )

    def _job_to_response(self, job: _JobRecord) -> JobStatusResponse:
        return JobStatusResponse(
            job_id=job.job_id,
            session_id=job.session_id,
            status=job.status,  # type: ignore[arg-type]
            progress_pct=job.progress_pct,
            stage=job.stage,
            error=job.error,
            options=job.options,
            markdown=job.markdown,
            stats=job.stats,
            ir=job.ir,
            md_path=str(job.md_path) if job.md_path.exists() else None,
        )

    def start_conversion_job(self, req: ConvertRequest) -> JobStatusResponse:
        rec = self.get_session(req.session_id)
        jid = uuid.uuid4().hex[:12]
        job_dir = rec.work_dir / f"job_{jid}"
        assets_dir = job_dir / "assets"
        job_dir.mkdir(parents=True, exist_ok=True)
        assets_dir.mkdir(parents=True, exist_ok=True)

        stem = rec.pdf_path.stem
        md_path = job_dir / f"{stem}.md"
        ir_path = job_dir / f"{stem}.ir.json"

        job = _JobRecord(
            job_id=jid,
            session_id=req.session_id,
            work_dir=job_dir,
            assets_dir=assets_dir,
            md_path=md_path,
            ir_path=ir_path,
            options=req,
            status="queued",
            progress_pct=5,
            stage="변환 작업 대기 중",
        )
        with self._lock:
            self._jobs[jid] = job

        self._executor.submit(self._run_conversion_worker, jid)
        return self._job_to_response(job)

    def _run_conversion_worker(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            sess = self._sessions[job.session_id]
            job.status = "running"
            job.progress_pct = 15
            job.stage = "PDF 문서 구조 확인 중"

        try:
            prange = parse_page_range_str(job.options.pages)
            preflight = analyze_pdf(sess.pdf_path, page_range=prange) if prange else sess.preflight

            with self._lock:
                job.progress_pct = 35
                job.stage = f"{job.options.parser.upper()} 레이아웃 · 표 · 수식 분석 중"

            parser = get_parser(job.options.parser)
            parse_opts = ParseOptions(
                page_range=prange,
                force_ocr=job.options.force_ocr,
                enable_formula_enrichment=job.options.enable_formula_enrichment,
                assets_dir=job.assets_dir,
            )
            ir = parser.parse(sess.pdf_path, preflight, parse_opts)

            with self._lock:
                job.progress_pct = 82
                job.stage = "학술 마크다운(.md) 생성 중"

            md_res = MarkdownCompiler().compile(
                ir,
                job.md_path,
                self._build_md_options(job.options),
            )
            job.ir_path.write_text(ir.model_dump_json(indent=2), encoding="utf-8")

            with self._lock:
                job.ir = ir
                job.markdown = md_res.markdown_text
                job.stats = _to_stats(md_res)
                job.status = "completed"
                job.progress_pct = 100
                job.stage = "마크다운 변환 완료"
        except Exception as exc:
            with self._lock:
                job.status = "failed"
                job.progress_pct = 100
                job.stage = "변환 실패"
                job.error = str(exc)

    def get_job(self, job_id: str) -> JobStatusResponse:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(f"Unknown job_id: {job_id}")
            return self._job_to_response(job)

    def get_job_record(self, job_id: str) -> _JobRecord:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(f"Unknown job_id: {job_id}")
            return job

    def resolve_job_asset_path(self, job_id: str, filename: str) -> Path:
        """Resolve an image asset belonging to a conversion job safely."""
        job = self.get_job_record(job_id)
        if (
            not filename
            or "/" in filename
            or "\\" in filename
            or ".." in filename
            or Path(filename).name != filename
        ):
            raise ValueError(f"Invalid asset filename: {filename}")

        work_root = job.work_dir.resolve()
        candidates = [
            job.assets_dir / filename,
            job.md_path.parent / f"{job.md_path.stem}_assets" / filename,
        ]
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.is_relative_to(work_root) and resolved.is_file():
                return resolved
        raise FileNotFoundError(f"Asset not found: {filename}")

    def reconvert_single_page(self, job_id: str, req: ReconvertPageRequest) -> JobStatusResponse:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(f"Unknown job_id: {job_id}")
            if job.ir is None:
                raise ValueError("Job has no compiled IR yet")
            sess = self._sessions[job.session_id]

        target_parser_name = req.parser or job.options.parser
        parser = get_parser(target_parser_name)
        parse_opts = ParseOptions(
            page_range=(req.page_no, req.page_no),
            force_ocr=req.force_ocr,
            enable_formula_enrichment=job.options.enable_formula_enrichment,
            assets_dir=job.assets_dir,
        )
        single_page_preflight = analyze_pdf(sess.pdf_path, page_range=(req.page_no, req.page_no))
        new_ir = parser.parse(sess.pdf_path, single_page_preflight, parse_opts)
        if not new_ir.pages:
            raise RuntimeError(f"Re-parsing page {req.page_no} produced no pages")

        new_page: PageIR = new_ir.pages[0].model_copy(update={"page_no": req.page_no})

        with self._lock:
            assert job.ir is not None
            updated_pages = [p for p in job.ir.pages if p.page_no != req.page_no]
            updated_pages.append(new_page)
            updated_pages.sort(key=lambda p: p.page_no)
            updated_ir = job.ir.model_copy(update={"pages": updated_pages})

            md_res = MarkdownCompiler().compile(
                updated_ir,
                job.md_path,
                self._build_md_options(job.options),
            )
            job.ir_path.write_text(updated_ir.model_dump_json(indent=2), encoding="utf-8")

            job.ir = updated_ir
            job.markdown = md_res.markdown_text
            job.stats = _to_stats(md_res)
            job.stage = f"{req.page_no}페이지 OCR 재분석 완료"
            return self._job_to_response(job)

    def get_job_markdown(
        self,
        job_id: str,
        image_mode: str = "folder",
    ) -> MarkdownCompileResult:
        job = self.get_job_record(job_id)
        if job.ir is None:
            raise ValueError("Job has no compiled IR yet")
        opts = self._build_md_options(job.options, image_mode_override=image_mode)
        return MarkdownCompiler().compile(job.ir, output_path=None, options=opts)

    def export_markdown_to(
        self,
        job_id: str,
        destination_path: str,
        image_mode: str = "folder",
        override_markdown: str | None = None,
    ) -> dict[str, str | int | None]:
        job = self.get_job_record(job_id)
        if job.ir is None:
            raise ValueError("Job has no compiled IR yet")
        dest = Path(destination_path).expanduser().resolve()
        opts = self._build_md_options(job.options, image_mode_override=image_mode)
        res = MarkdownCompiler().compile(job.ir, output_path=dest, options=opts)
        if override_markdown is not None:
            dest.write_text(override_markdown, encoding="utf-8")
        return {
            "exported_path": str(dest),
            "assets_dir": res.assets_dir,
            "assets_copied": res.assets_copied,
        }

    def compile_job_rtf(
        self,
        job_id: str,
        override_markdown: str | None = None,
        destination_path: Path | None = None,
    ) -> RtfCompileResult:
        job = self.get_job_record(job_id)
        md_text = override_markdown
        if md_text is None:
            if job.markdown is not None:
                md_text = job.markdown
            elif job.ir is not None:
                md_text = MarkdownCompiler().compile(
                    job.ir, output_path=None, options=self._build_md_options(job.options, "folder")
                ).markdown_text
            else:
                raise ValueError("Job has no compiled Markdown yet")

        def _resolve_asset(filename: str) -> Path | None:
            try:
                return self.resolve_job_asset_path(job_id, Path(filename).name)
            except (ValueError, FileNotFoundError):
                return None

        return MarkdownToRtfCompiler().compile(
            md_text,
            output_path=destination_path,
            asset_resolver=_resolve_asset,
        )

    def export_rtf_to(
        self,
        job_id: str,
        destination_path: str,
        override_markdown: str | None = None,
    ) -> dict[str, str | int]:
        dest = Path(destination_path).expanduser().resolve()
        if dest.suffix.lower() != ".rtf":
            dest = dest.with_suffix(".rtf")
        res = self.compile_job_rtf(
            job_id,
            override_markdown=override_markdown,
            destination_path=dest,
        )
        return {
            "exported_path": str(dest),
            "byte_size": res.byte_size,
            "embedded_images": res.embedded_images,
        }

    def trigger_model_warmup(self) -> dict[str, str]:
        with self._lock:
            if self.warmup_status == "running":
                return {"status": "running", "message": "이미 모델 초기화가 진행 중입니다."}
            self.warmup_status = "running"
            self.warmup_message = "Docling AI 및 RapidOCR 모델 캐시 확인 중..."

        def _worker() -> None:
            try:
                res = warmup_docling_models()
                with self._lock:
                    self.warmup_status = "completed"
                    self.warmup_message = res["message"]
            except Exception as exc:
                with self._lock:
                    self.warmup_status = "failed"
                    self.warmup_message = str(exc)

        self._executor.submit(_worker)
        return {"status": "running", "message": "모델 워밍업을 시작했습니다."}
