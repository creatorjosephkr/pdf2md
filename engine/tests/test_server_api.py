"""Tests for simplified Markdown-only FastAPI Sidecar server endpoints."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from fixtures_generator import generate_all_samples
from pdf_convert_engine.server.app import create_app


def _poll_job_completed(client: TestClient, job_id: str, timeout_s: float = 15.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        res = client.get(f"/api/jobs/{job_id}")
        assert res.status_code == 200
        body = res.json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.05)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout_s}s")


def test_server_health_and_models(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app) as client:
        h = client.get("/api/health")
        assert h.status_code == 200
        h_json = h.json()
        assert h_json["status"] == "ok"
        assert h_json["hardware"]["accelerator"] in ("mps", "cuda", "cpu")

        m = client.get("/api/models")
        assert m.status_code == 200
        assert len(m.json()["models"]) == 4


def test_server_session_convert_reconvert_and_export_markdown(tmp_path: Path) -> None:
    samples_dir = tmp_path / "samples"
    created = generate_all_samples(samples_dir)
    pdf_path = created["academic_2col_en"]
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app) as client:
        # 1. Open via path
        sess_res = client.post("/api/sessions/open-path", json={"pdf_path": str(pdf_path)})
        assert sess_res.status_code == 200
        sess = sess_res.json()
        sid = sess["session_id"]
        assert sess["preflight"]["page_count"] == 2
        assert sess["preflight"]["detected_columns"] == 2

        # 2. Upload bytes flow
        up_res = client.post(
            "/api/sessions/upload",
            files={"file": ("uploaded_paper.pdf", pdf_path.read_bytes(), "application/pdf")},
        )
        assert up_res.status_code == 200
        assert up_res.json()["file_name"] == "uploaded_paper.pdf"

        # 3. Render source PNG page 1
        png_res = client.get(f"/api/sessions/{sid}/pages/1/source.png?dpi=120")
        assert png_res.status_code == 200
        assert png_res.content[:4] == b"\x89PNG"

        # 4. Start Markdown conversion job & poll until completed
        job_res = client.post(
            "/api/jobs/convert",
            json={
                "session_id": sid,
                "parser": "fallback",
                "image_mode": "folder",
                "complex_table_html": True,
                "include_frontmatter": True,
            },
        )
        assert job_res.status_code == 200
        job_id = job_res.json()["job_id"]

        done = _poll_job_completed(client, job_id)
        assert done["status"] == "completed", f"Failed: {done.get('error')}"
        assert done["markdown"] is not None
        assert "High-Fidelity Layout Reconstruction" in done["markdown"]
        assert done["stats"]["headings"] >= 1
        assert done["ir"] is not None

        # 5. Per-page reconvert on page 1
        reconv_res = client.post(
            f"/api/jobs/{job_id}/reconvert-page",
            json={"page_no": 1, "force_ocr": False, "parser": "fallback"},
        )
        assert reconv_res.status_code == 200
        reconv = reconv_res.json()
        assert reconv["status"] == "completed"
        assert reconv["markdown"] is not None

        # 6. Markdown preview, download, and export (with custom edited markdown override)
        md_res = client.get(f"/api/jobs/{job_id}/markdown?image_mode=base64")
        assert md_res.status_code == 200
        assert "High-Fidelity Layout Reconstruction" in md_res.json()["markdown"]

        md_dl = client.get(f"/api/jobs/{job_id}/download-markdown?image_mode=none")
        assert md_dl.status_code == 200
        assert "High-Fidelity Layout Reconstruction" in md_dl.text

        export_target = tmp_path / "exported_md" / "paper.md"
        exp = client.post(
            f"/api/jobs/{job_id}/export-markdown-to",
            json={
                "destination_path": str(export_target),
                "image_mode": "folder",
                "override_markdown": "# Custom Edited Title\n\nBody text.\n",
            },
        )
        assert exp.status_code == 200
        assert export_target.exists()
        assert export_target.read_text(encoding="utf-8").startswith("# Custom Edited Title")


def test_concurrent_source_page_rendering_no_crash(tmp_path: Path) -> None:
    """Stress-test parallel /source.png requests for libpdfium thread safety."""
    samples_dir = tmp_path / "samples"
    created = generate_all_samples(samples_dir)
    pdf_path = created["academic_2col_en"]
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app) as client:
        sess = client.post("/api/sessions/open-path", json={"pdf_path": str(pdf_path)}).json()
        sid = sess["session_id"]

        targets = [
            (page_no, dpi)
            for _ in range(4)
            for page_no in (1, 2)
            for dpi in (96, 180)
        ]

        def fetch(item: tuple[int, int]) -> bytes:
            page_no, dpi = item
            res = client.get(f"/api/sessions/{sid}/pages/{page_no}/source.png?dpi={dpi}")
            assert res.status_code == 200
            return res.content

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(fetch, targets))

        assert len(results) == 16
        assert all(data[:4] == b"\x89PNG" for data in results)


def test_job_asset_serving_and_path_traversal_guard(tmp_path: Path) -> None:
    samples_dir = tmp_path / "samples"
    created = generate_all_samples(samples_dir)
    pdf_path = created["academic_2col_en"]
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app) as client:
        sess = client.post("/api/sessions/open-path", json={"pdf_path": str(pdf_path)}).json()
        sid = sess["session_id"]
        job_res = client.post(
            "/api/jobs/convert",
            json={"session_id": sid, "parser": "fallback", "image_mode": "folder"},
        )
        assert job_res.status_code == 200
        job_id = job_res.json()["job_id"]
        done = _poll_job_completed(client, job_id)
        assert done["status"] == "completed"

        job_rec = app.state.store.get_job_record(job_id)
        job_rec.assets_dir.mkdir(parents=True, exist_ok=True)
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        (job_rec.assets_dir / "sample_fig.png").write_bytes(png_bytes)

        ok_res = client.get(f"/api/jobs/{job_id}/assets/sample_fig.png")
        assert ok_res.status_code == 200
        assert ok_res.content == png_bytes

        missing_res = client.get(f"/api/jobs/{job_id}/assets/does_not_exist.png")
        assert missing_res.status_code == 404

        for bad_name in ("%2e%2e", "..%2F..%2Fetc%2Fpasswd", "..%5Csecret.png", "sub%2Ffile.png"):
            bad_res = client.get(f"/api/jobs/{job_id}/assets/{bad_name}")
            assert bad_res.status_code in (400, 404)

        try:
            app.state.store.resolve_job_asset_path(job_id, "..")
            raise AssertionError("Expected ValueError for '..'")
        except ValueError:
            pass


def test_export_and_download_rtf_endpoints(tmp_path: Path) -> None:
    import io
    from PIL import Image

    samples_dir = tmp_path / "samples"
    created = generate_all_samples(samples_dir)
    pdf_path = created["academic_2col_en"]
    app = create_app(data_dir=tmp_path / "data")

    with TestClient(app) as client:
        sess = client.post("/api/sessions/open-path", json={"pdf_path": str(pdf_path)}).json()
        sid = sess["session_id"]
        job_res = client.post(
            "/api/jobs/convert",
            json={"session_id": sid, "parser": "fallback", "image_mode": "folder"},
        )
        assert job_res.status_code == 200
        job_id = job_res.json()["job_id"]
        done = _poll_job_completed(client, job_id)
        assert done["status"] == "completed"

        # Seed a real PNG inside job.assets_dir
        buf = io.BytesIO()
        Image.new("RGB", (64, 32), color=(15, 23, 42)).save(buf, format="PNG")
        job_rec = app.state.store.get_job_record(job_id)
        job_rec.assets_dir.mkdir(parents=True, exist_ok=True)
        (job_rec.assets_dir / "chart_test.png").write_bytes(buf.getvalue())

        custom_md = (
            "# 한국어 테스트 보고서\n\n"
            "**강조 텍스트** 및 `코드`\n\n"
            "![차트](./assets/chart_test.png)\n"
        )
        export_target = tmp_path / "exported_rtf" / "report"
        exp = client.post(
            f"/api/jobs/{job_id}/export-rtf-to",
            json={"destination_path": str(export_target), "override_markdown": custom_md},
        )
        assert exp.status_code == 200
        exp_json = exp.json()
        exported_path = Path(exp_json["exported_path"])
        assert exported_path.suffix == ".rtf"
        assert exported_path.exists()
        assert exp_json["embedded_images"] == 1
        assert exported_path.read_text(encoding="ascii").startswith("{\\rtf1")

        dl = client.post(
            f"/api/jobs/{job_id}/download-rtf",
            json={"override_markdown": custom_md},
        )
        assert dl.status_code == 200
        assert dl.headers["content-type"].startswith("application/rtf")
        assert dl.content.startswith(b"{\\rtf1")
        assert b"\\pict\\pngblip" in dl.content


def test_updates_check_endpoint(tmp_path: Path, monkeypatch) -> None:
    import pdf_convert_engine.server.app as app_mod
    from pdf_convert_engine.server.models import UpdateCheckResponse

    def fake_check(current_version: str | None = None) -> UpdateCheckResponse:
        return UpdateCheckResponse(
            status="update_available",
            current_version=current_version or "0.1.0",
            latest_version="0.2.0",
            has_update=True,
            release_name="PDF 얼개 v0.2.0",
            release_notes="업데이트 노트",
            published_at="2026-11-25T00:00:00Z",
            release_url="https://github.com/creatorjosephkr/pdf2md/releases/tag/v0.2.0",
            download_url="https://github.com/creatorjosephkr/pdf2md/releases/download/v0.2.0/app.dmg",
            repo_url="https://github.com/creatorjosephkr/pdf2md",
            checked_at="2026-11-25T00:00:00Z",
            message="새 버전 v0.2.0이(가) 출시되었습니다.",
        )

    monkeypatch.setattr(app_mod, "check_github_release", fake_check)
    app = create_app(data_dir=tmp_path / "data")
    with TestClient(app) as client:
        res = client.get("/api/updates/check?current_version=0.1.0")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "update_available"
        assert body["has_update"] is True
        assert body["latest_version"] == "0.2.0"
        assert body["repo_url"] == "https://github.com/creatorjosephkr/pdf2md"
