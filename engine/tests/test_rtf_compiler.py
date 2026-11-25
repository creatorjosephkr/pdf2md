"""Tests for Markdown -> Formatted RTF compiler."""

from __future__ import annotations

import base64
import io
import subprocess
import sys
from pathlib import Path

from PIL import Image

from pdf_convert_engine.compiler import MarkdownToRtfCompiler


def _make_png_bytes(color: tuple[int, int, int] = (37, 99, 235)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (120, 60), color=color).save(buf, format="PNG")
    return buf.getvalue()


def test_markdown_to_rtf_compiler_rich_features(tmp_path: Path) -> None:
    png_bytes = _make_png_bytes()
    fig_path = tmp_path / "assets" / "fig_1.png"
    fig_path.parent.mkdir(parents=True, exist_ok=True)
    fig_path.write_bytes(png_bytes)

    b64_png = base64.b64encode(_make_png_bytes((5, 150, 105))).decode("ascii")

    sample_md = f"""---
title: "학술 논문 RTF 내보내기 테스트"
source: "paper.pdf"
pages: 2
language: "ko"
columns: 2
---

# 한국어 논문 제목: Attention Is All You Need

## 1. 서론 (Introduction)

본 문서에는 **굵은 글씨**, *기울임*, ~~취소선~~, `inline_code`, 위첨자 x<sup>2</sup> 및 아래첨자 H<sub>2</sub>O 서식이 포함됩니다.
인라인 수식은 $\\alpha + \\beta \\leq \\gamma$ 와 같이 표현됩니다.

### 1.1 수식 및 코드

$$
\\mathcal{{L}}(\\theta) = \\sum_{{i=1}}^{{N}} \\frac{{x_i}}{{2}} \\quad \\tag{{1}}
$$

```python
def compute_attention(q, k, v):
    return q @ k.T
```

> [!NOTE] 핵심 요약
> 이 문단은 **Obsidian 노트 콜아웃** 테스트입니다.

> [!IMPORTANT] 정리 1.1
> 모든 **연속 함수**는 유계 닫힌 구간에서 최댓값과 최솟값을 가집니다.

- 첫 번째 항목
  - 중첩된 하위 항목
- 두 번째 항목

1. 순서 있는 목록 A
2. 순서 있는 목록 B

| 모델 | 정확도 | 비고 |
| --- | --- | --- |
| Baseline | 89.4% | 기준치 |
| ScholarMD | **96.2%** | 최고 성능 |

<table>
  <thead>
    <tr>
      <th rowspan="2">구분</th>
      <th colspan="2">성능 비교</th>
    </tr>
    <tr>
      <th>정밀도</th>
      <th>재현율</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>제안 기법</td>
      <td>95.1%</td>
      <td>94.8%</td>
    </tr>
  </tbody>
</table>

![그림 1: 로컬 에셋](./assets/fig_1.png)

![그림 2: Base64 인라인](data:image/png;base64,{b64_png})
"""

    out_rtf = tmp_path / "out" / "paper.rtf"
    res = MarkdownToRtfCompiler().compile(
        sample_md,
        output_path=out_rtf,
        asset_resolver=lambda name: fig_path if name == "fig_1.png" else None,
    )

    assert out_rtf.exists()
    assert res.output_path == str(out_rtf.resolve())
    assert res.byte_size > 500
    assert res.embedded_images == 2
    assert res.tables == 2
    assert res.formulas >= 2

    rtf = res.rtf_text
    assert rtf.startswith("{\\rtf1\\ansi\\ansicpg65001")
    assert rtf.endswith("}")
    assert rtf.count("{") == rtf.count("}")
    # ASCII clean encoding
    rtf.encode("ascii", errors="strict")
    # Frontmatter stripped
    assert "columns: 2" not in rtf
    # Korean Unicode escapes emitted (\u- or positive signed codepoint)
    assert "\\u" in rtf
    # Merged HTML table controls
    assert "\\clvmgf" in rtf
    assert "\\clvmrg" in rtf
    # Embedded PNG images
    assert rtf.count("\\pict\\pngblip") == 2

    if sys.platform == "darwin" and Path("/usr/bin/textutil").exists():
        proc = subprocess.run(
            ["/usr/bin/textutil", "-convert", "txt", "-stdout", str(out_rtf)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"textutil failed: {proc.stderr}"
        txt = proc.stdout
        assert "한국어 논문 제목" in txt
        assert "핵심 요약" in txt
        assert "정리 1.1" in txt
        assert "ScholarMD" in txt
        assert "성능 비교" in txt
        assert "제안 기법" in txt
