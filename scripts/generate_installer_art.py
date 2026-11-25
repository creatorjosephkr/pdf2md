"""Generate Retina macOS DMG background PNGs and Windows NSIS BMP branding images."""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

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


def _vertical_gradient(w: int, h: int, top_rgb: tuple[int, int, int], bot_rgb: tuple[int, int, int]) -> Image.Image:
    base = Image.new("RGB", (w, h), top_rgb)
    draw = ImageDraw.Draw(base)
    for y in range(h):
        t = y / max(1, h - 1)
        r = round(top_rgb[0] + (bot_rgb[0] - top_rgb[0]) * t)
        g = round(top_rgb[1] + (bot_rgb[1] - top_rgb[1]) * t)
        b = round(top_rgb[2] + (bot_rgb[2] - top_rgb[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return base


def build_dmg_backgrounds(icon_rgba: Image.Image) -> None:
    DMG_DIR.mkdir(parents=True, exist_ok=True)
    # 2x Retina canvas (1320 x 800 -> logical 660 x 400)
    w, h = 1320, 800
    canvas = _vertical_gradient(w, h, (248, 250, 252), (235, 240, 247)).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    # Subtle dot grid matching Studio background aesthetic
    for gx in range(40, w, 40):
        for gy in range(40, h, 40):
            draw.ellipse((gx - 1, gy - 1, gx + 1, gy + 1), fill=(148, 163, 184, 55))

    # Top brand header centered
    f_title = _load_font(40, bold=True)
    f_sub = _load_font(24, bold=False)
    f_hint = _load_font(19, bold=True)
    f_note = _load_font(21, bold=False)

    mini_icon = icon_rgba.resize((68, 68), Image.Resampling.LANCZOS)
    title_txt = "PDF 얼개"
    sub_txt = "PDF Eolgae"
    tb = draw.textbbox((0, 0), title_txt, font=f_title)
    sb = draw.textbbox((0, 0), sub_txt, font=f_sub)
    total_header_w = 68 + 18 + (tb[2] - tb[0]) + 14 + (sb[2] - sb[0])
    hx = (w - total_header_w) // 2
    hy = 44
    canvas.alpha_composite(mini_icon, (hx, hy))
    draw.text((hx + 68 + 18, hy + 12), title_txt, font=f_title, fill=(15, 23, 42, 255))
    draw.text(
        (hx + 68 + 18 + (tb[2] - tb[0]) + 14, hy + 23),
        sub_txt,
        font=f_sub,
        fill=(100, 116, 139, 255),
    )

    # Subtle rounded cards behind App icon (x=360, y=370 @2x) and Applications (x=960, y=370 @2x)
    for cx, cy in ((360, 385), (960, 385)):
        cw, ch = 296, 324
        x0, y0 = cx - cw // 2, cy - ch // 2
        x1, y1 = cx + cw // 2, cy + ch // 2
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=36,
            fill=(255, 255, 255, 215),
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
    note_txt = "처음 실행 시 보안 경고가 뜨면:  시스템 설정 → 개인정보 보호 및 보안 → '그래도 열기'"
    nb = draw.textbbox((0, 0), note_txt, font=f_note)
    pill_w = (nb[2] - nb[0]) + 56
    pill_h = 54
    px0 = (w - pill_w) // 2
    py0 = 678
    draw.rounded_rectangle(
        (px0, py0, px0 + pill_w, py0 + pill_h),
        radius=27,
        fill=(255, 255, 255, 235),
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
    NSIS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Header BMP (150 x 57 RGB)
    hw, hh = 150, 57
    hdr = Image.new("RGBA", (hw, hh), (248, 250, 252, 255))
    h_draw = ImageDraw.Draw(hdr)
    h_draw.line([(0, hh - 1), (hw, hh - 1)], fill=(226, 232, 240, 255), width=1)
    h_icon = icon_rgba.resize((36, 36), Image.Resampling.LANCZOS)
    hdr.alpha_composite(h_icon, (14, 10))
    f_hdr = _load_font(13, bold=True)
    f_hdr_sub = _load_font(10, bold=False)
    h_draw.text((58, 12), "PDF 얼개", font=f_hdr, fill=(15, 23, 42, 255))
    h_draw.text((58, 30), "PDF Eolgae", font=f_hdr_sub, fill=(100, 116, 139, 255))
    hdr_path = NSIS_DIR / "header.bmp"
    hdr.convert("RGB").save(hdr_path, format="BMP")

    # 2. Sidebar BMP (164 x 314 RGB)
    sw, sh = 164, 314
    side = _vertical_gradient(sw, sh, (15, 23, 42), (29, 78, 216)).convert("RGBA")
    s_draw = ImageDraw.Draw(side)
    s_icon = icon_rgba.resize((88, 88), Image.Resampling.LANCZOS)
    side.alpha_composite(s_icon, ((sw - 88) // 2, 68))

    f_side = _load_font(18, bold=True)
    f_side_sub = _load_font(12, bold=False)
    f_side_tag = _load_font(11, bold=False)
    t1 = "PDF 얼개"
    t2 = "PDF Eolgae"
    t3 = "PDF → MD · RTF"
    b1 = s_draw.textbbox((0, 0), t1, font=f_side)
    b2 = s_draw.textbbox((0, 0), t2, font=f_side_sub)
    b3 = s_draw.textbbox((0, 0), t3, font=f_side_tag)
    s_draw.text(((sw - (b1[2] - b1[0])) // 2, 174), t1, font=f_side, fill=(255, 255, 255, 255))
    s_draw.text(((sw - (b2[2] - b2[0])) // 2, 200), t2, font=f_side_sub, fill=(191, 219, 254, 255))
    s_draw.text(((sw - (b3[2] - b3[0])) // 2, 236), t3, font=f_side_tag, fill=(147, 197, 253, 255))

    side_path = NSIS_DIR / "sidebar.bmp"
    side.convert("RGB").save(side_path, format="BMP")
    print("Saved NSIS BMPs:", hdr_path, side_path)


def main() -> None:
    icon_rgba = Image.open(APP_ICON).convert("RGBA")
    build_dmg_backgrounds(icon_rgba)
    build_nsis_bmps(icon_rgba)


if __name__ == "__main__":
    main()
