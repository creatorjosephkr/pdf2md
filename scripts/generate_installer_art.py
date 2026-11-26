"""Generate Retina macOS DMG background PNGs and Windows NSIS BMP branding images."""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
APP_ICON = ROOT / "apps" / "desktop" / "public" / "app-icon.png"
DMG_DIR = ROOT / "apps" / "desktop" / "src-tauri" / "dmg"
NSIS_DIR = ROOT / "apps" / "desktop" / "src-tauri" / "nsis"


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 6 if bold else 0),
        ("/System/Library/Fonts/Supplemental/AppleGothic.ttf", 0),
        ("/Library/Fonts/NanumGothic.ttf", 0),
    ]
    for path, index in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size, index=index)
            except Exception:
                try:
                    return ImageFont.truetype(path, size=size)
                except Exception:
                    pass
    return ImageFont.load_default()


def _vertical_gradient(
    w: int, h: int, top_rgb: tuple[int, int, int], bot_rgb: tuple[int, int, int]
) -> Image.Image:
    base = Image.new("RGB", (w, h), top_rgb)
    draw = ImageDraw.Draw(base)
    for y in range(h):
        t = y / max(1, h - 1)
        r = round(top_rgb[0] + (bot_rgb[0] - top_rgb[0]) * t)
        g = round(top_rgb[1] + (bot_rgb[1] - top_rgb[1]) * t)
        b = round(top_rgb[2] + (bot_rgb[2] - top_rgb[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return base


def _paste_icon_with_shadow(
    canvas: Image.Image,
    icon_rgba: Image.Image,
    pos: tuple[int, int],
    size: int,
    shadow_alpha: int = 75,
    shadow_blur: int = 8,
    shadow_offset: tuple[int, int] = (0, 4),
    border_rgba: tuple[int, int, int, int] | None = None,
) -> None:
    resized = icon_rgba.resize((size, size), Image.Resampling.LANCZOS)
    alpha = resized.getchannel("A")

    pad = shadow_blur * 3
    sh_layer = Image.new("RGBA", (size + pad * 2, size + pad * 2), (0, 0, 0, 0))
    sh_solid = Image.new("RGBA", (size, size), (15, 23, 42, shadow_alpha))
    sh_layer.paste(sh_solid, (pad, pad), mask=alpha)
    sh_layer = sh_layer.filter(ImageFilter.GaussianBlur(radius=shadow_blur))

    sx = pos[0] - pad + shadow_offset[0]
    sy = pos[1] - pad + shadow_offset[1]
    canvas.alpha_composite(sh_layer, (sx, sy))
    canvas.alpha_composite(resized, pos)

    if border_rgba is not None:
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        r = max(4, round(size * (110.51 / 510.24)))
        d.rounded_rectangle(
            (pos[0], pos[1], pos[0] + size - 1, pos[1] + size - 1),
            radius=r,
            outline=border_rgba,
            width=1,
        )
        canvas.alpha_composite(overlay)


def build_dmg_backgrounds(icon_rgba: Image.Image) -> None:
    DMG_DIR.mkdir(parents=True, exist_ok=True)
    # 2x Retina canvas (1320 x 800 -> logical 660 x 400)
    w, h = 1320, 800
    canvas = _vertical_gradient(w, h, (248, 250, 252), (233, 238, 245)).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    # Subtle dot grid matching Studio background aesthetic
    for gx in range(40, w, 40):
        for gy in range(40, h, 40):
            draw.ellipse((gx - 1, gy - 1, gx + 1, gy + 1), fill=(148, 163, 184, 52))

    # Top brand header centered
    f_title = _load_font(40, bold=True)
    f_sub = _load_font(24, bold=False)
    f_hint = _load_font(19, bold=True)
    f_note = _load_font(21, bold=False)

    title_txt = "PDF 얼개"
    sub_txt = "PDF Eolgae"
    tb = draw.textbbox((0, 0), title_txt, font=f_title)
    sb = draw.textbbox((0, 0), sub_txt, font=f_sub)
    icon_sz = 68
    total_header_w = icon_sz + 18 + (tb[2] - tb[0]) + 14 + (sb[2] - sb[0])
    hx = (w - total_header_w) // 2
    hy = 44

    _paste_icon_with_shadow(
        canvas,
        icon_rgba,
        (hx, hy),
        size=icon_sz,
        shadow_alpha=55,
        shadow_blur=6,
        shadow_offset=(0, 3),
        border_rgba=(148, 163, 184, 140),
    )

    draw = ImageDraw.Draw(canvas)
    draw.text((hx + icon_sz + 18, hy + 12), title_txt, font=f_title, fill=(15, 23, 42, 255))
    draw.text(
        (hx + icon_sz + 18 + (tb[2] - tb[0]) + 14, hy + 23),
        sub_txt,
        font=f_sub,
        fill=(100, 116, 139, 255),
    )

    # Subtle rounded cards behind App icon (x=360, y=385 @2x) and Applications (x=960, y=385 @2x)
    for cx, cy in ((360, 385), (960, 385)):
        cw, ch = 296, 324
        x0, y0 = cx - cw // 2, cy - ch // 2
        x1, y1 = cx + cw // 2, cy + ch // 2
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=36,
            fill=(255, 255, 255, 220),
            outline=(203, 213, 225, 210),
            width=2,
        )

    # Center directional arrow at x=660, y=370 @2x
    ax, ay = 660, 370
    draw.rounded_rectangle((ax - 66, ay - 7, ax + 46, ay + 7), radius=7, fill=(37, 99, 235, 235))
    draw.polygon(
        [(ax + 30, ay - 24), (ax + 72, ay), (ax + 30, ay + 24)],
        fill=(37, 99, 235, 235),
    )
    drag_txt = "응용 프로그램 폴더로 드래그"
    db = draw.textbbox((0, 0), drag_txt, font=f_hint)
    draw.text((ax - (db[2] - db[0]) // 2, ay + 44), drag_txt, font=f_hint, fill=(30, 64, 175, 255))

    # Bottom macOS first-run security tip pill
    note_txt = "처음 실행 시 보안 경고가 뜨면:  시스템 설정 → 개인정보 보호 및 보안 → '확인 없이 열기'"
    nb = draw.textbbox((0, 0), note_txt, font=f_note)
    pill_w = (nb[2] - nb[0]) + 56
    pill_h = 54
    px0 = (w - pill_w) // 2
    py0 = 678
    draw.rounded_rectangle(
        (px0, py0, px0 + pill_w, py0 + pill_h),
        radius=27,
        fill=(255, 255, 255, 238),
        outline=(191, 219, 254, 255),
        width=2,
    )
    draw.text((px0 + 28, py0 + 14), note_txt, font=f_note, fill=(51, 65, 85, 255))

    rgb_2x = canvas.convert("RGB")
    bg_2x = DMG_DIR / "dmg-background@2x.png"
    bg_1x = DMG_DIR / "dmg-background.png"
    rgb_2x.save(bg_2x, format="PNG")
    rgb_2x.resize((660, 400), Image.Resampling.LANCZOS).save(bg_1x, format="PNG")
    print("Saved DMG backgrounds:", bg_1x, bg_2x)


def build_nsis_bmps(icon_rgba: Image.Image) -> None:
    """Build clean graphic-only Windows NSIS BMPs (no raster text so HiDPI never squishes fonts)."""
    NSIS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Header BMP (150 x 57 RGB) — pure white seamless header with crisp right-aligned app icon only
    hw, hh = 150, 57
    hdr = Image.new("RGBA", (hw, hh), (255, 255, 255, 255))
    icon_h_sz = 40
    _paste_icon_with_shadow(
        hdr,
        icon_rgba,
        (hw - icon_h_sz - 14, (hh - icon_h_sz) // 2),
        size=icon_h_sz,
        shadow_alpha=45,
        shadow_blur=3,
        shadow_offset=(0, 1),
        border_rgba=(148, 163, 184, 150),
    )
    hdr_path = NSIS_DIR / "header.bmp"
    hdr.convert("RGB").save(hdr_path, format="BMP")

    # 2. Sidebar BMP (164 x 314 RGB) — sleek dark slate gradient + crisp centered new app icon only
    sw, sh = 164, 314
    side = _vertical_gradient(sw, sh, (15, 23, 42), (51, 65, 85)).convert("RGBA")
    s_draw = ImageDraw.Draw(side)

    # Subtle dot matrix accent in background (alpha-composited so dots stay faint & refined)
    dot_layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    d_draw = ImageDraw.Draw(dot_layer)
    for gx in range(16, sw, 20):
        for gy in range(16, sh, 20):
            d_draw.ellipse((gx, gy, gx + 1, gy + 1), fill=(255, 255, 255, 26))
    side.alpha_composite(dot_layer)

    # Centered new app icon with clean drop shadow (no text inside BMP to prevent DPI distortion)
    icon_s_sz = 96
    ix = (sw - icon_s_sz) // 2
    iy = 86
    _paste_icon_with_shadow(
        side,
        icon_rgba,
        (ix, iy),
        size=icon_s_sz,
        shadow_alpha=120,
        shadow_blur=9,
        shadow_offset=(0, 5),
        border_rgba=(255, 255, 255, 90),
    )

    # Minimal accent bar below icon
    s_draw = ImageDraw.Draw(side)
    s_draw.rounded_rectangle((sw // 2 - 22, iy + icon_s_sz + 24, sw // 2 + 22, iy + icon_s_sz + 27), radius=2, fill=(148, 163, 184, 160))

    side_path = NSIS_DIR / "sidebar.bmp"
    side.convert("RGB").save(side_path, format="BMP")
    print("Saved NSIS BMPs:", hdr_path, side_path)


def main() -> None:
    icon_rgba = Image.open(APP_ICON).convert("RGBA")
    build_dmg_backgrounds(icon_rgba)
    build_nsis_bmps(icon_rgba)


if __name__ == "__main__":
    main()
