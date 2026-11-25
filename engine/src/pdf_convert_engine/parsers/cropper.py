"""High-DPI PDF region cropper backed by pypdfium2 (Apache-2.0/BSD-3)."""

from __future__ import annotations

import threading
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageChops

from pdf_convert_engine.ir.schema import BBox

# libpdfium is NOT thread-safe; serialize all pypdfium2 calls across FastAPI / Docling threads.
PDFIUM_LOCK = threading.RLock()


class PageCropper:
    """Thread-safe PDF page renderer & region cropper with strict resource cleanup."""

    def __init__(self, pdf_path: str | Path) -> None:
        self.pdf_path = Path(pdf_path)
        self._page_cache: dict[tuple[int, int], Image.Image] = {}

    def close(self) -> None:
        self._page_cache.clear()

    def __enter__(self) -> "PageCropper":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def render_page(self, page_no: int, dpi: int = 350) -> Image.Image:
        key = (page_no, dpi)
        cached = self._page_cache.get(key)
        if cached is not None:
            return cached

        scale = dpi / 72.0
        with PDFIUM_LOCK:
            doc = pdfium.PdfDocument(str(self.pdf_path))
            try:
                page = doc[page_no - 1]
                try:
                    bitmap = page.render(scale=scale)
                    try:
                        pil_img = bitmap.to_pil().convert("RGB").copy()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
            finally:
                doc.close()

        self._page_cache[key] = pil_img
        return pil_img

    @staticmethod
    def _trim_white_border(img: Image.Image, pad_px: int = 4) -> Image.Image:
        bg = Image.new("RGB", img.size, (255, 255, 255))
        diff = ImageChops.difference(img, bg)
        bbox = diff.getbbox()
        if bbox is None:
            return img
        x0 = max(0, bbox[0] - pad_px)
        y0 = max(0, bbox[1] - pad_px)
        x1 = min(img.width, bbox[2] + pad_px)
        y1 = min(img.height, bbox[3] + pad_px)
        return img.crop((x0, y0, x1, y1))

    def crop_bbox(
        self,
        page_no: int,
        bbox: BBox,
        out_path: str | Path,
        dpi: int = 350,
        pad_pt: float = 1.5,
        trim_whitespace: bool = False,
    ) -> tuple[float, float]:
        """Crop a TOPLEFT PDF-point bbox and save as PNG. Returns (width_pt, height_pt)."""
        page_img = self.render_page(page_no, dpi=dpi)
        scale = dpi / 72.0

        px0 = max(0, int((bbox.x0 - pad_pt) * scale))
        py0 = max(0, int((bbox.y0 - pad_pt) * scale))
        px1 = min(page_img.width, int((bbox.x1 + pad_pt) * scale))
        py1 = min(page_img.height, int((bbox.y1 + pad_pt) * scale))

        if px1 <= px0:
            px1 = min(page_img.width, px0 + 10)
        if py1 <= py0:
            py1 = min(page_img.height, py0 + 10)

        cropped = page_img.crop((px0, py0, px1, py1))
        if trim_whitespace:
            cropped = self._trim_white_border(cropped)

        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(out, format="PNG")

        w_pt = max(1.0, cropped.width / scale)
        h_pt = max(1.0, cropped.height / scale)
        return round(w_pt, 2), round(h_pt, 2)
