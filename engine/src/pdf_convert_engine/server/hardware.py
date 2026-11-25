"""Local hardware acceleration detection and on-disk AI model cache inspection."""

from __future__ import annotations

import importlib.metadata
import os
import platform
import subprocess
import sys
from pathlib import Path

from pdf_convert_engine.parsers.docling_adapter import DoclingAdapter
from pdf_convert_engine.server.models import HardwareInfo, ModelStatusItem


def _dir_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = 0
    for root, _dirs, files in os.walk(path):
        for fn in files:
            fp = Path(root) / fn
            try:
                if not fp.is_symlink():
                    total += fp.stat().st_size
                else:
                    # HF snapshot files symlink to blobs; count logical size safely
                    total += fp.stat().st_size
            except OSError:
                continue
    return round(total / (1024.0 * 1024.0), 1)


def _macos_chip_name() -> str:
    try:
        out = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True, timeout=2)
        return out.strip() or "Apple Silicon"
    except Exception:
        return "Apple Silicon"


def detect_hardware() -> HardwareInfo:
    sys_os = platform.system()
    arch = platform.machine()
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    try:
        docling_ver = importlib.metadata.version("docling")
    except importlib.metadata.PackageNotFoundError:
        docling_ver = "unknown"

    accelerator = "cpu"
    label = f"CPU ({platform.processor() or arch})"

    try:
        import torch

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            accelerator = "mps"
            chip = _macos_chip_name() if sys_os == "Darwin" else "Apple Silicon"
            label = f"{chip} (MPS)"
        elif torch.cuda.is_available():
            accelerator = "cuda"
            dev_name = torch.cuda.get_device_name(0)
            label = f"NVIDIA {dev_name} (CUDA)"
    except Exception:
        pass

    return HardwareInfo(
        os=sys_os,
        arch=arch,
        accelerator=accelerator,  # type: ignore[arg-type]
        accelerator_label=label,
        python_version=py_ver,
        docling_version=docling_ver,
    )


def _find_hf_cache_dir(repo_patterns: list[str]) -> Path | None:
    hf_hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    if not hf_hub.exists():
        return None
    for entry in hf_hub.iterdir():
        if entry.is_dir() and any(pat in entry.name.lower() for pat in repo_patterns):
            snapshots = entry / "snapshots"
            if snapshots.exists() and any(snapshots.iterdir()):
                return entry
    return None


def _find_rapidocr_models() -> tuple[bool, float, str | None]:
    # Check docling cache or rapidocr package models directory
    docling_cache = Path.home() / ".cache" / "docling"
    if docling_cache.exists():
        onnx_files = list(docling_cache.rglob("*.onnx"))
        if onnx_files:
            sz = round(sum(f.stat().st_size for f in onnx_files) / (1024.0 * 1024.0), 1)
            return True, sz, str(docling_cache)

    try:
        import rapidocr

        pkg_dir = Path(rapidocr.__file__).resolve().parent
        models_dir = pkg_dir / "models"
        onnx_files = list(models_dir.rglob("*.onnx")) if models_dir.exists() else []
        if onnx_files:
            sz = round(sum(f.stat().st_size for f in onnx_files) / (1024.0 * 1024.0), 1)
            return True, sz, str(models_dir)
    except Exception:
        pass

    return False, 0.0, None


def inspect_local_models() -> list[ModelStatusItem]:
    layout_dir = _find_hf_cache_dir(["docling-layout-heron", "docling-layout"])
    table_dir = _find_hf_cache_dir(["docling-models"])
    formula_dir = _find_hf_cache_dir(["codeformula"])
    ocr_installed, ocr_size_mb, ocr_path = _find_rapidocr_models()

    return [
        ModelStatusItem(
            id="docling-layout",
            name="Docling Layout (Heron)",
            role="2단·그림·표·캡션 레이아웃 영역 분할",
            license="MIT",
            installed=layout_dir is not None,
            size_mb=_dir_size_mb(layout_dir) if layout_dir else 0.0,
            cache_path=str(layout_dir) if layout_dir else None,
            description="학술 논문 2단 본문, 2단 가로지르기 그림, 각주 영역을 정밀 분할합니다.",
        ),
        ModelStatusItem(
            id="docling-tableformer",
            name="Docling TableFormer",
            role="학술 Booktabs · 병합 셀 표 구조 복원",
            license="MIT",
            installed=table_dir is not None,
            size_mb=_dir_size_mb(table_dir) if table_dir else 0.0,
            cache_path=str(table_dir) if table_dir else None,
            description="colSpan / rowSpan 병합 헤더와 세로선 없는 Booktabs 표를 복원합니다.",
        ),
        ModelStatusItem(
            id="docling-codeformula",
            name="Docling CodeFormulaV2",
            role="수식 LaTeX 추출 (Alt Text 보존용)",
            license="MIT",
            installed=formula_dir is not None,
            size_mb=_dir_size_mb(formula_dir) if formula_dir else 0.0,
            cache_path=str(formula_dir) if formula_dir else None,
            description="디스플레이 수식을 인식해 Google Docs 이미지 Alt Text용 LaTeX 코드를 생성합니다.",
        ),
        ModelStatusItem(
            id="rapidocr-onnx",
            name="RapidOCR (ONNX Runtime)",
            role="스캔본 · 깨진 한글 CMap 선택적 로컬 OCR",
            license="Apache-2.0",
            installed=ocr_installed,
            size_mb=ocr_size_mb,
            cache_path=ocr_path,
            description="PyTorch 없이 ONNX Runtime으로 동작하는 경량 로컬 OCR 엔진입니다.",
        ),
    ]


def warmup_docling_models() -> dict[str, str]:
    adapter = DoclingAdapter()
    adapter._build_converter(use_ocr=True, enable_formula_enrichment=True)
    return {"status": "completed", "message": "Docling Layout, TableFormer, CodeFormula, RapidOCR 파이프라인 초기화 완료"}
