"""Markdown (.md) -> Formatted Rich Text Format (.rtf) compiler (zero external binaries)."""

from __future__ import annotations

import base64
import io
import re
import struct
import sys
from pathlib import Path
from typing import Callable

from bs4 import BeautifulSoup, Tag
from markdown_it import MarkdownIt
from markdown_it.token import Token
from PIL import Image
from pydantic import BaseModel

_FRONTMATTER_RE = re.compile(r"^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)")
_DISPLAY_MATH_RE = re.compile(r"(?:^|\n)[ \t]*\$\$([\s\S]*?)\$\$[ \t]*(?=\n|$)")
_INLINE_MATH_RE = re.compile(r"(?<!\\)\$([^\$\n]+?)(?<!\\)\$")
_CALLOUT_RE = re.compile(
    r"^\[!(NOTE|IMPORTANT|TIP|WARNING|CAUTION)\][ \t]*([^\n]*)(?:\n|$)",
    re.IGNORECASE,
)

_LATEX_SYMBOL_MAP: list[tuple[str, str]] = [
    (r"\\alpha\b", "α"),
    (r"\\beta\b", "β"),
    (r"\\gamma\b", "γ"),
    (r"\\delta\b", "δ"),
    (r"\\epsilon\b", "ε"),
    (r"\\varepsilon\b", "ε"),
    (r"\\zeta\b", "ζ"),
    (r"\\eta\b", "η"),
    (r"\\theta\b", "θ"),
    (r"\\vartheta\b", "ϑ"),
    (r"\\iota\b", "ι"),
    (r"\\kappa\b", "κ"),
    (r"\\lambda\b", "λ"),
    (r"\\mu\b", "μ"),
    (r"\\nu\b", "ν"),
    (r"\\xi\b", "ξ"),
    (r"\\pi\b", "π"),
    (r"\\rho\b", "ρ"),
    (r"\\sigma\b", "σ"),
    (r"\\tau\b", "τ"),
    (r"\\upsilon\b", "υ"),
    (r"\\phi\b", "φ"),
    (r"\\varphi\b", "φ"),
    (r"\\chi\b", "χ"),
    (r"\\psi\b", "ψ"),
    (r"\\omega\b", "ω"),
    (r"\\Gamma\b", "Γ"),
    (r"\\Delta\b", "Δ"),
    (r"\\Theta\b", "Θ"),
    (r"\\Lambda\b", "Λ"),
    (r"\\Xi\b", "Ξ"),
    (r"\\Pi\b", "Π"),
    (r"\\Sigma\b", "Σ"),
    (r"\\Phi\b", "Φ"),
    (r"\\Psi\b", "Ψ"),
    (r"\\Omega\b", "Ω"),
    (r"\\sum\b", "∑"),
    (r"\\prod\b", "∏"),
    (r"\\int\b", "∫"),
    (r"\\partial\b", "∂"),
    (r"\\nabla\b", "∇"),
    (r"\\infty\b", "∞"),
    (r"\\pm\b", "±"),
    (r"\\mp\b", "∓"),
    (r"\\times\b", "×"),
    (r"\\cdot\b", "·"),
    (r"\\div\b", "÷"),
    (r"\\leq\b", "≤"),
    (r"\\le\b", "≤"),
    (r"\\geq\b", "≥"),
    (r"\\ge\b", "≥"),
    (r"\\neq\b", "≠"),
    (r"\\ne\b", "≠"),
    (r"\\approx\b", "≈"),
    (r"\\equiv\b", "≡"),
    (r"\\sim\b", "∼"),
    (r"\\propto\b", "∝"),
    (r"\\notin\b", "∉"),
    (r"\\in\b", "∈"),
    (r"\\subseteq\b", "⊆"),
    (r"\\subset\b", "⊂"),
    (r"\\supseteq\b", "⊇"),
    (r"\\supset\b", "⊃"),
    (r"\\cup\b", "∪"),
    (r"\\cap\b", "∩"),
    (r"\\forall\b", "∀"),
    (r"\\exists\b", "∃"),
    (r"\\Rightarrow\b", "⇒"),
    (r"\\Leftarrow\b", "⇐"),
    (r"\\Leftrightarrow\b", "⇔"),
    (r"\\rightarrow\b", "→"),
    (r"\\to\b", "→"),
    (r"\\leftarrow\b", "←"),
    (r"\\cdots\b", "⋯"),
    (r"\\ldots\b", "…"),
    (r"\\dots\b", "…"),
    (r"\\qquad\b", "  "),
    (r"\\quad\b", " "),
]

_CALLOUT_STYLES: dict[str, tuple[int, int, str]] = {
    # kind -> (border_cf, bg_cbpat, default_title)
    "NOTE": (4, 9, "NOTE"),
    "IMPORTANT": (5, 10, "IMPORTANT"),
    "TIP": (6, 11, "TIP"),
    "WARNING": (7, 12, "WARNING"),
    "CAUTION": (7, 12, "CAUTION"),
}


class RtfCompileResult(BaseModel):
    output_path: str | None = None
    rtf_text: str
    byte_size: int = 0
    embedded_images: int = 0
    tables: int = 0
    formulas: int = 0


def rtf_escape(text: str) -> str:
    """Escape text for RTF 1.9 (\\uc1) with signed 16-bit Unicode escapes."""
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == "{":
            out.append("\\{")
        elif ch == "}":
            out.append("\\}")
        elif ch == "\r":
            continue
        elif ch == "\n":
            out.append("\\line ")
        elif ch == "\t":
            out.append("\\tab ")
        elif code < 128:
            out.append(ch)
        elif code <= 0xFFFF:
            signed = code if code < 32768 else code - 65536
            out.append(f"\\u{signed}?")
        else:
            # Supplementary plane -> UTF-16BE surrogate pair
            b = ch.encode("utf-16-be")
            hi, lo = struct.unpack(">HH", b)
            hi_s = hi if hi < 32768 else hi - 65536
            lo_s = lo if lo < 32768 else lo - 65536
            out.append(f"\\u{hi_s}?\\u{lo_s}?")
    return "".join(out)


def _prettify_latex(expr: str) -> str:
    s = expr.strip()
    if s.startswith("$$") and s.endswith("$$"):
        s = s[2:-2].strip()
    elif s.startswith("$") and s.endswith("$"):
        s = s[1:-1].strip()

    tag_text = ""
    tag_match = re.search(r"\\tag\{([^{}]+)\}", s)
    if tag_match:
        tag_text = f"   ({tag_match.group(1).strip()})"
        s = (s[: tag_match.start()] + s[tag_match.end() :]).strip()

    s = re.sub(r"\\(?:text|mathrm|mathbf|mathit|operatorname)\s*\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"(\1)/(\2)", s)
    s = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√(\1)", s)
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\{", "{").replace("\\}", "}")

    for pattern, repl in _LATEX_SYMBOL_MAP:
        s = re.sub(pattern, repl, s)

    s = re.sub(r"\s+", " ", s).strip()
    return f"{s}{tag_text}".strip()


class MarkdownToRtfCompiler:
    """Converts Academic Markdown (.md) into a self-contained formatted RTF 1.9 document."""

    CONTENT_WIDTH_TWIPS = 9026  # A4 11906 - 2 * 1440pt margins
    MAX_IMAGE_TWIPS = 8200

    def compile(
        self,
        markdown_text: str,
        output_path: str | Path | None = None,
        asset_resolver: Callable[[str], Path | None] | None = None,
    ) -> RtfCompileResult:
        body = _FRONTMATTER_RE.sub("", markdown_text).strip()

        # Protect display math blocks from markdown-it emphasis parsing
        display_math_map: dict[str, str] = {}

        def _replace_display_math(match: re.Match[str]) -> str:
            key = f"SCHOLARMD_DISPLAY_MATH_{len(display_math_map)}"
            display_math_map[key] = match.group(1).strip()
            return f"\n\n{key}\n\n"

        preprocessed = _DISPLAY_MATH_RE.sub(_replace_display_math, body)

        md = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
        tokens = md.parse(preprocessed)

        stats = {"embedded_images": 0, "tables": 0, "formulas": len(display_math_map)}
        body_parts: list[str] = [self._build_header()]
        self._render_blocks(
            tokens,
            0,
            len(tokens),
            body_parts,
            display_math_map=display_math_map,
            asset_resolver=asset_resolver,
            stats=stats,
            list_depth=0,
            blockquote_style=None,
        )
        body_parts.append("}")

        rtf_text = "\n".join(body_parts)
        byte_data = rtf_text.encode("ascii", errors="strict")

        out_path_str: str | None = None
        if output_path is not None:
            out_file = Path(output_path).resolve()
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(byte_data)
            out_path_str = str(out_file)

        return RtfCompileResult(
            output_path=out_path_str,
            rtf_text=rtf_text,
            byte_size=len(byte_data),
            embedded_images=stats["embedded_images"],
            tables=stats["tables"],
            formulas=stats["formulas"],
        )

    def _build_header(self) -> str:
        if sys.platform == "darwin":
            sans_font = "Apple SD Gothic Neo"
            mono_font = "Menlo"
            serif_font = "Georgia"
        else:
            sans_font = "Malgun Gothic"
            mono_font = "Consolas"
            serif_font = "Cambria"

        return (
            "{\\rtf1\\ansi\\ansicpg65001\\deff0\\uc1\n"
            "{\\fonttbl"
            f"{{\\f0\\fnil\\fcharset129 {sans_font};}}"
            f"{{\\f1\\fmodern\\fcharset0 {mono_font};}}"
            f"{{\\f2\\froman\\fcharset0 {serif_font};}}"
            "}\n"
            "{\\colortbl;"
            "\\red15\\green23\\blue42;"     # 1: #0F172A dark slate
            "\\red30\\green41\\blue59;"     # 2: #1E293B body
            "\\red71\\green85\\blue105;"    # 3: #475569 muted
            "\\red37\\green99\\blue235;"    # 4: #2563EB blue
            "\\red124\\green58\\blue237;"   # 5: #7C3AED violet
            "\\red5\\green150\\blue105;"    # 6: #059669 emerald
            "\\red217\\green119\\blue6;"    # 7: #D97706 amber
            "\\red241\\green245\\blue249;"  # 8: #F1F5F9 light slate bg
            "\\red239\\green246\\blue255;"  # 9: #EFF6FF NOTE bg
            "\\red245\\green243\\blue255;"  # 10: #F5F3FF IMPORTANT bg
            "\\red236\\green253\\blue245;"  # 11: #ECFDF5 TIP bg
            "\\red255\\green251\\blue235;"  # 12: #FFFBEB WARNING bg
            "\\red203\\green213\\blue225;"  # 13: #CBD5E1 border gray
            "\\red248\\green250\\blue252;"  # 14: #F8FAFC subtle surface
            "}\n"
            "\\paperw11906\\paperh16838\\margl1440\\margr1440\\margt1440\\margb1440"
            "\\viewkind4\\f0\\fs21\\cf2"
        )

    def _find_matching_close(self, tokens: list[Token], open_idx: int) -> int:
        open_type = tokens[open_idx].type
        close_type = open_type[:-5] + "_close" if open_type.endswith("_open") else ""
        depth = 0
        for idx in range(open_idx, len(tokens)):
            t = tokens[idx]
            if t.type == open_type:
                depth += 1
            elif t.type == close_type:
                depth -= 1
                if depth == 0:
                    return idx
        return len(tokens) - 1

    def _render_blocks(
        self,
        tokens: list[Token],
        start: int,
        end: int,
        out: list[str],
        *,
        display_math_map: dict[str, str],
        asset_resolver: Callable[[str], Path | None] | None,
        stats: dict[str, int],
        list_depth: int,
        blockquote_style: tuple[int, int] | None,
    ) -> None:
        idx = start
        while idx < end:
            tok = tokens[idx]

            if tok.type == "heading_open":
                close_idx = self._find_matching_close(tokens, idx)
                level = int(tok.tag[1]) if tok.tag.startswith("h") and tok.tag[1:].isdigit() else 2
                inline_tok = tokens[idx + 1] if idx + 1 < close_idx else None
                content = self._render_inline(inline_tok, asset_resolver, stats)
                if level == 1:
                    prefix = "\\pard\\f0\\fs40\\b\\cf1\\sb180\\sa160\\brdrb\\brdrs\\brdrw10\\brdrcf13 "
                elif level == 2:
                    prefix = "\\pard\\f0\\fs30\\b\\cf1\\sb220\\sa120\\brdrb\\brdrs\\brdrw8\\brdrcf8 "
                elif level == 3:
                    prefix = "\\pard\\f0\\fs25\\b\\cf2\\sb160\\sa80 "
                else:
                    prefix = "\\pard\\f0\\fs22\\b\\cf3\\sb120\\sa60 "
                out.append(f"{{{prefix}{content}\\par}}")
                idx = close_idx + 1
                continue

            if tok.type == "paragraph_open":
                close_idx = self._find_matching_close(tokens, idx)
                inline_tok = tokens[idx + 1] if idx + 1 < close_idx else None
                raw_content = inline_tok.content.strip() if inline_tok else ""

                if raw_content in display_math_map:
                    pretty = _prettify_latex(display_math_map[raw_content])
                    out.append(
                        "{\\pard\\qc\\f1\\fs21\\cf1\\cbpat14"
                        "\\brdrt\\brdrs\\brdrw10\\brdrcf13"
                        "\\brdrb\\brdrs\\brdrw10\\brdrcf13"
                        "\\sb120\\sa160 "
                        + rtf_escape(pretty)
                        + "\\par}"
                    )
                    idx = close_idx + 1
                    continue

                is_image_only = bool(
                    inline_tok
                    and inline_tok.children
                    and len(inline_tok.children) == 1
                    and inline_tok.children[0].type == "image"
                )
                content = self._render_inline(inline_tok, asset_resolver, stats)
                if blockquote_style is not None:
                    b_cf, bg_cb = blockquote_style
                    out.append(
                        f"{{\\pard\\f0\\fs20\\cf2\\li240\\ri180\\sb60\\sa100\\sl300\\slmult1"
                        f"\\cbpat{bg_cb}\\brdrl\\brdrs\\brdrw45\\brdrcf{b_cf} {content}\\par}}"
                    )
                elif is_image_only:
                    out.append(f"{{\\pard\\qc\\sb100\\sa120 {content}\\par}}")
                else:
                    out.append(f"{{\\pard\\f0\\fs21\\cf2\\sl324\\slmult1\\sa120 {content}\\par}}")
                idx = close_idx + 1
                continue

            if tok.type in ("bullet_list_open", "ordered_list_open"):
                close_idx = self._find_matching_close(tokens, idx)
                ordered = tok.type == "ordered_list_open"
                start_num = 1
                if ordered and tok.attrs:
                    try:
                        start_num = int(tok.attrGet("start") or 1)
                    except (TypeError, ValueError):
                        start_num = 1
                self._render_list(
                    tokens,
                    idx + 1,
                    close_idx,
                    out,
                    ordered=ordered,
                    start_num=start_num,
                    depth=list_depth + 1,
                    display_math_map=display_math_map,
                    asset_resolver=asset_resolver,
                    stats=stats,
                )
                idx = close_idx + 1
                continue

            if tok.type in ("fence", "code_block"):
                code_str = tok.content.rstrip("\n")
                out.append(
                    "{\\pard\\f1\\fs18\\cf1\\li240\\ri240\\sb100\\sa140\\sl260\\slmult1"
                    "\\cbpat8\\box\\brdrs\\brdrw10\\brdrcf13 "
                    + rtf_escape(code_str)
                    + "\\par}"
                )
                idx += 1
                continue

            if tok.type == "blockquote_open":
                close_idx = self._find_matching_close(tokens, idx)
                self._render_blockquote(
                    tokens,
                    idx + 1,
                    close_idx,
                    out,
                    display_math_map=display_math_map,
                    asset_resolver=asset_resolver,
                    stats=stats,
                )
                idx = close_idx + 1
                continue

            if tok.type == "table_open":
                close_idx = self._find_matching_close(tokens, idx)
                self._render_gfm_table(tokens, idx + 1, close_idx, out, asset_resolver, stats)
                stats["tables"] += 1
                idx = close_idx + 1
                continue

            if tok.type == "html_block":
                raw_html = tok.content.strip()
                if raw_html.startswith("<!--") and raw_html.endswith("-->"):
                    idx += 1
                    continue
                if "<table" in raw_html.lower():
                    self._render_html_table(raw_html, out, stats)
                else:
                    soup = BeautifulSoup(raw_html, "html.parser")
                    txt = soup.get_text(" ", strip=True)
                    if txt:
                        out.append(f"{{\\pard\\f0\\fs21\\cf2\\sa100 {rtf_escape(txt)}\\par}}")
                idx += 1
                continue

            if tok.type == "hr":
                out.append("{\\pard\\sb80\\sa140\\brdrb\\brdrs\\brdrw10\\brdrcf13 \\par}")
                idx += 1
                continue

            idx += 1

    def _render_list(
        self,
        tokens: list[Token],
        start: int,
        end: int,
        out: list[str],
        *,
        ordered: bool,
        start_num: int,
        depth: int,
        display_math_map: dict[str, str],
        asset_resolver: Callable[[str], Path | None] | None,
        stats: dict[str, int],
    ) -> None:
        item_num = start_num
        idx = start
        indent = 360 * depth
        while idx < end:
            tok = tokens[idx]
            if tok.type == "list_item_open":
                close_idx = self._find_matching_close(tokens, idx)
                marker = f"{item_num}." if ordered else "\\u8226?"
                item_num += 1

                # Collect direct paragraph inline content and nested sub-lists
                sub_idx = idx + 1
                emitted_first_para = False
                while sub_idx < close_idx:
                    sub = tokens[sub_idx]
                    if sub.type == "paragraph_open":
                        p_close = self._find_matching_close(tokens, sub_idx)
                        inline_tok = tokens[sub_idx + 1] if sub_idx + 1 < p_close else None
                        content = self._render_inline(inline_tok, asset_resolver, stats)
                        if not emitted_first_para:
                            out.append(
                                f"{{\\pard\\f0\\fs21\\cf2\\li{indent}\\fi-240\\sl312\\slmult1\\sa70 "
                                f"{marker}\\tab {content}\\par}}"
                            )
                            emitted_first_para = True
                        else:
                            out.append(
                                f"{{\\pard\\f0\\fs21\\cf2\\li{indent}\\sl312\\slmult1\\sa70 "
                                f"{content}\\par}}"
                            )
                        sub_idx = p_close + 1
                    else:
                        self._render_blocks(
                            tokens,
                            sub_idx,
                            close_idx,
                            out,
                            display_math_map=display_math_map,
                            asset_resolver=asset_resolver,
                            stats=stats,
                            list_depth=depth,
                            blockquote_style=None,
                        )
                        break
                idx = close_idx + 1
                continue
            idx += 1

    def _render_blockquote(
        self,
        tokens: list[Token],
        start: int,
        end: int,
        out: list[str],
        *,
        display_math_map: dict[str, str],
        asset_resolver: Callable[[str], Path | None] | None,
        stats: dict[str, int],
    ) -> None:
        # Check whether the first paragraph opens with an Obsidian/GitHub [!NOTE|...] marker
        callout_match: tuple[int, int, str] | None = None
        first_para_inline_idx: int | None = None
        remaining_first_line = ""

        for idx in range(start, end):
            if tokens[idx].type == "paragraph_open" and idx + 1 < end and tokens[idx + 1].type == "inline":
                inline_tok = tokens[idx + 1]
                m = _CALLOUT_RE.match(inline_tok.content)
                if m:
                    kind = m.group(1).upper()
                    b_cf, bg_cb, default_title = _CALLOUT_STYLES[kind]
                    title = m.group(2).strip() or default_title
                    callout_match = (b_cf, bg_cb, title)
                    first_para_inline_idx = idx + 1
                    remaining_first_line = inline_tok.content[m.end() :]
                break

        if callout_match is not None and first_para_inline_idx is not None:
            b_cf, bg_cb, title = callout_match
            # Emit title line of callout
            out.append(
                f"{{\\pard\\f0\\fs20\\b\\cf{b_cf}\\li240\\ri180\\sb120\\sa40"
                f"\\cbpat{bg_cb}\\brdrl\\brdrs\\brdrw45\\brdrcf{b_cf} "
                f"{rtf_escape(title)}\\par}}"
            )
            # Re-parse remaining body of first paragraph if any, and render remaining tokens
            orig_inline = tokens[first_para_inline_idx]
            if remaining_first_line.strip():
                md_sub = MarkdownIt("commonmark", {"html": True}).enable(["strikethrough"])
                sub_tokens = md_sub.parse(remaining_first_line)
                self._render_blocks(
                    sub_tokens,
                    0,
                    len(sub_tokens),
                    out,
                    display_math_map=display_math_map,
                    asset_resolver=asset_resolver,
                    stats=stats,
                    list_depth=0,
                    blockquote_style=(b_cf, bg_cb),
                )
            # Skip the consumed first paragraph
            first_para_close = self._find_matching_close(tokens, first_para_inline_idx - 1)
            _ = orig_inline
            if first_para_close + 1 < end:
                self._render_blocks(
                    tokens,
                    first_para_close + 1,
                    end,
                    out,
                    display_math_map=display_math_map,
                    asset_resolver=asset_resolver,
                    stats=stats,
                    list_depth=0,
                    blockquote_style=(b_cf, bg_cb),
                )
            return

        # Standard blockquote
        self._render_blocks(
            tokens,
            start,
            end,
            out,
            display_math_map=display_math_map,
            asset_resolver=asset_resolver,
            stats=stats,
            list_depth=0,
            blockquote_style=(13, 14),
        )

    def _render_gfm_table(
        self,
        tokens: list[Token],
        start: int,
        end: int,
        out: list[str],
        asset_resolver: Callable[[str], Path | None] | None,
        stats: dict[str, int],
    ) -> None:
        rows: list[tuple[bool, list[str]]] = []
        in_header = False
        idx = start
        while idx < end:
            tok = tokens[idx]
            if tok.type == "thead_open":
                in_header = True
            elif tok.type == "thead_close":
                in_header = False
            elif tok.type == "tr_open":
                row_close = self._find_matching_close(tokens, idx)
                cells: list[str] = []
                c_idx = idx + 1
                while c_idx < row_close:
                    ctok = tokens[c_idx]
                    if ctok.type in ("th_open", "td_open"):
                        c_close = self._find_matching_close(tokens, c_idx)
                        inline_tok = tokens[c_idx + 1] if c_idx + 1 < c_close else None
                        cells.append(self._render_inline(inline_tok, asset_resolver, stats))
                        c_idx = c_close + 1
                        continue
                    c_idx += 1
                if cells:
                    rows.append((in_header, cells))
                idx = row_close + 1
                continue
            idx += 1

        if not rows:
            return
        num_cols = max(len(c) for _, c in rows)
        if num_cols <= 0:
            return

        for is_hdr, cells in rows:
            padded = cells + [""] * (num_cols - len(cells))
            row_def = ["\\trowd\\trgaph108\\trleft0"]
            for c_i in range(num_cols):
                right_x = round((c_i + 1) * self.CONTENT_WIDTH_TWIPS / num_cols)
                bg = "\\clcbpat8" if is_hdr else ""
                row_def.append(
                    f"{bg}\\clbrdrt\\brdrs\\brdrw10\\brdrcf13"
                    "\\clbrdrl\\brdrs\\brdrw10\\brdrcf13"
                    "\\clbrdrb\\brdrs\\brdrw10\\brdrcf13"
                    "\\clbrdrr\\brdrs\\brdrw10\\brdrcf13"
                    f"\\cellx{right_x}"
                )
            cell_strs = []
            for txt in padded:
                style = "\\b\\cf1" if is_hdr else "\\cf2"
                cell_strs.append(f"\\pard\\intbl\\f0\\fs19{style} {txt}\\cell")
            out.append("{" + "".join(row_def) + "".join(cell_strs) + "\\row}")
        out.append("{\\pard\\sa100 \\par}")

    def _render_html_table(
        self,
        raw_html: str,
        out: list[str],
        stats: dict[str, int],
    ) -> None:
        soup = BeautifulSoup(raw_html, "html.parser")
        table = soup.find("table")
        if not isinstance(table, Tag):
            return

        tr_tags = table.find_all("tr")
        if not tr_tags:
            return

        # Build grid accounting for rowspan/colspan
        occupied: dict[tuple[int, int], tuple[int, int, int, bool]] = {}
        # maps (r, c) -> (owner_r, owner_c, owner_colspan, is_header)
        grid_cells: dict[tuple[int, int], tuple[str, int, int, bool]] = {}
        # maps (r, c) -> (text_rtf, colspan, rowspan, is_header)
        num_cols = 0

        for r_idx, tr in enumerate(tr_tags):
            c_idx = 0
            in_thead = isinstance(tr.parent, Tag) and tr.parent.name == "thead"
            for cell in tr.find_all(["th", "td"], recursive=False):
                while (r_idx, c_idx) in occupied:
                    c_idx += 1
                try:
                    colspan = max(1, int(cell.get("colspan") or 1))
                except (TypeError, ValueError):
                    colspan = 1
                try:
                    rowspan = max(1, int(cell.get("rowspan") or 1))
                except (TypeError, ValueError):
                    rowspan = 1

                is_hdr = in_thead or cell.name == "th"
                txt = re.sub(r"\s+", " ", cell.get_text(" ", strip=True))
                grid_cells[(r_idx, c_idx)] = (rtf_escape(txt), colspan, rowspan, is_hdr)

                for rr in range(r_idx, r_idx + rowspan):
                    for cc in range(c_idx, c_idx + colspan):
                        occupied[(rr, cc)] = (r_idx, c_idx, colspan, is_hdr)
                c_idx += colspan
                num_cols = max(num_cols, c_idx)

        if num_cols <= 0:
            return

        stats["tables"] += 1
        num_rows = len(tr_tags)
        for r_idx in range(num_rows):
            row_def = ["\\trowd\\trgaph108\\trleft0"]
            cell_strs: list[str] = []
            c_idx = 0
            while c_idx < num_cols:
                if (r_idx, c_idx) in grid_cells:
                    txt_rtf, colspan, rowspan, is_hdr = grid_cells[(r_idx, c_idx)]
                    right_x = round(min(num_cols, c_idx + colspan) * self.CONTENT_WIDTH_TWIPS / num_cols)
                    vmerge = "\\clvmgf" if rowspan > 1 else ""
                    bg = "\\clcbpat8" if is_hdr else ""
                    row_def.append(
                        f"{vmerge}{bg}\\clbrdrt\\brdrs\\brdrw10\\brdrcf13"
                        "\\clbrdrl\\brdrs\\brdrw10\\brdrcf13"
                        "\\clbrdrb\\brdrs\\brdrw10\\brdrcf13"
                        "\\clbrdrr\\brdrs\\brdrw10\\brdrcf13"
                        f"\\cellx{right_x}"
                    )
                    style = "\\b\\cf1" if is_hdr else "\\cf2"
                    cell_strs.append(f"\\pard\\intbl\\f0\\fs19{style} {txt_rtf}\\cell")
                    c_idx += colspan
                elif (r_idx, c_idx) in occupied:
                    owner_r, owner_c, colspan, is_hdr = occupied[(r_idx, c_idx)]
                    if c_idx == owner_c and owner_r < r_idx:
                        right_x = round(
                            min(num_cols, c_idx + colspan) * self.CONTENT_WIDTH_TWIPS / num_cols
                        )
                        bg = "\\clcbpat8" if is_hdr else ""
                        row_def.append(
                            f"\\clvmrg{bg}\\clbrdrt\\brdrs\\brdrw10\\brdrcf13"
                            "\\clbrdrl\\brdrs\\brdrw10\\brdrcf13"
                            "\\clbrdrb\\brdrs\\brdrw10\\brdrcf13"
                            "\\clbrdrr\\brdrs\\brdrw10\\brdrcf13"
                            f"\\cellx{right_x}"
                        )
                        cell_strs.append("\\pard\\intbl\\cell")
                        c_idx += colspan
                    else:
                        c_idx += 1
                else:
                    right_x = round((c_idx + 1) * self.CONTENT_WIDTH_TWIPS / num_cols)
                    row_def.append(
                        "\\clbrdrt\\brdrs\\brdrw10\\brdrcf13"
                        "\\clbrdrl\\brdrs\\brdrw10\\brdrcf13"
                        "\\clbrdrb\\brdrs\\brdrw10\\brdrcf13"
                        "\\clbrdrr\\brdrs\\brdrw10\\brdrcf13"
                        f"\\cellx{right_x}"
                    )
                    cell_strs.append("\\pard\\intbl\\cell")
                    c_idx += 1

            out.append("{" + "".join(row_def) + "".join(cell_strs) + "\\row}")
        out.append("{\\pard\\sa100 \\par}")

    def _render_inline(
        self,
        inline_tok: Token | None,
        asset_resolver: Callable[[str], Path | None] | None,
        stats: dict[str, int],
    ) -> str:
        if inline_tok is None:
            return ""
        children = inline_tok.children or []
        if not children:
            return self._render_text_with_inline_math(inline_tok.content, stats)

        out: list[str] = []
        i = 0
        while i < len(children):
            ch = children[i]
            if ch.type == "text":
                out.append(self._render_text_with_inline_math(ch.content, stats))
            elif ch.type == "softbreak":
                out.append(" ")
            elif ch.type == "hardbreak":
                out.append("\\line ")
            elif ch.type == "code_inline":
                out.append(f"{{\\f1\\fs19\\chcbpat8 {rtf_escape(ch.content)}}}")
            elif ch.type == "strong_open":
                out.append("{\\b ")
            elif ch.type == "strong_close":
                out.append("}")
            elif ch.type == "em_open":
                out.append("{\\i ")
            elif ch.type == "em_close":
                out.append("}")
            elif ch.type == "s_open":
                out.append("{\\strike ")
            elif ch.type == "s_close":
                out.append("}")
            elif ch.type == "link_open":
                href = ch.attrGet("href") or ""
                safe_href = str(href).replace('"', '\\"')
                out.append(f'{{\\field{{\\*\\fldinst{{HYPERLINK "{rtf_escape(safe_href)}"}}}}{{\\fldrslt{{\\ul\\cf4 ')
            elif ch.type == "link_close":
                out.append("}}}")
            elif ch.type == "image":
                src = str(ch.attrGet("src") or "")
                alt = ch.content or str(ch.attrGet("alt") or "Figure")
                out.append(self._render_image_rtf(src, alt, asset_resolver, stats))
            elif ch.type == "html_inline":
                tag = ch.content.strip().lower()
                if tag == "<sup>":
                    out.append("{\\super\\fs15 ")
                elif tag == "<sub>":
                    out.append("{\\sub\\fs15 ")
                elif tag in ("</sup>", "</sub>"):
                    out.append("}")
                elif tag == "<u>":
                    out.append("{\\ul ")
                elif tag == "</u>":
                    out.append("}")
                elif tag in ("<br>", "<br/>", "<br />"):
                    out.append("\\line ")
            i += 1
        return "".join(out)

    def _render_text_with_inline_math(self, text: str, stats: dict[str, int]) -> str:
        if "$" not in text:
            return rtf_escape(text)
        parts: list[str] = []
        last = 0
        for m in _INLINE_MATH_RE.finditer(text):
            if m.start() > last:
                parts.append(rtf_escape(text[last : m.start()]))
            pretty = _prettify_latex(m.group(1))
            stats["formulas"] += 1
            parts.append(f"{{\\i\\f2 {rtf_escape(pretty)}}}")
            last = m.end()
        if last < len(text):
            parts.append(rtf_escape(text[last:]))
        return "".join(parts)

    def _render_image_rtf(
        self,
        src: str,
        alt: str,
        asset_resolver: Callable[[str], Path | None] | None,
        stats: dict[str, int],
    ) -> str:
        png_bytes: bytes | None = None
        trimmed = src.strip()

        if trimmed.startswith("data:image/") and ";base64," in trimmed:
            try:
                b64_part = trimmed.split(";base64,", 1)[1]
                raw = base64.b64decode(b64_part)
                png_bytes = self._ensure_png_bytes(raw)
            except Exception:
                png_bytes = None
        elif trimmed and asset_resolver is not None:
            clean = trimmed.split("?")[0].split("#")[0]
            filename = Path(clean).name
            resolved = asset_resolver(filename)
            if resolved is not None and resolved.exists():
                try:
                    png_bytes = self._ensure_png_bytes(resolved.read_bytes())
                except Exception:
                    png_bytes = None

        if not png_bytes:
            return f"{{\\i\\cf3 [Figure: {rtf_escape(alt)}]}}"

        try:
            with Image.open(io.BytesIO(png_bytes)) as img:
                px_w, px_h = img.size
        except Exception:
            return f"{{\\i\\cf3 [Figure: {rtf_escape(alt)}]}}"

        px_w = max(1, px_w)
        px_h = max(1, px_h)
        goal_w = px_w * 15
        goal_h = px_h * 15
        if goal_w > self.MAX_IMAGE_TWIPS:
            scale = self.MAX_IMAGE_TWIPS / goal_w
            goal_w = self.MAX_IMAGE_TWIPS
            goal_h = max(120, round(goal_h * scale))

        stats["embedded_images"] += 1
        hex_str = png_bytes.hex()
        return (
            f"{{\\pict\\pngblip\\picw{px_w}\\pich{px_h}"
            f"\\picwgoal{goal_w}\\pichgoal{goal_h} {hex_str}}}"
        )

    def _ensure_png_bytes(self, raw_bytes: bytes) -> bytes:
        if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return raw_bytes
        with Image.open(io.BytesIO(raw_bytes)) as img:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
