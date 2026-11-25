# ScholarMD (`pdf-convert`) 아키텍처

## 1. 프로젝트 개요

학술 논문 및 전공 교재 PDF를 **보이는 구조 그대로** 편집 가능한 **학술 마크다운(`.md`)**으로 변환하는 **100% 로컬 · 오픈소스 Win/Mac 데스크톱 앱**입니다.

### 핵심 원칙
* **상용 친화적 오픈소스 스택**: MIT / Apache-2.0 / BSD 계열 컴포넌트로만 구성합니다(AGPL `PyMuPDF` 미사용, `python-docx` 등 불필요한 오피스 의존성 제거).
* **단순 텍스트 추출 금지**: AI 레이아웃 분석(`Docling`) + 정밀 타이포그래피(`pdfplumber`) + 고해상도 영역 크롭(`pypdfium2`)을 결합해 2단 읽기 순서·LaTeX 수식·병합 표·그림·Callout 박스를 구조화합니다.

---

## 2. 기술 스택 (Commercial-Safe Open Source)

| 계층 | 채택 기술 | 라이선스 | 역할 |
| :--- | :--- | :---: | :--- |
| 데스크톱 셸 | **Tauri v2** (Rust) + React + Tailwind CSS v4 | MIT / Apache-2.0 | Win/Mac 네이티브 창, 파일 다이얼로그, Python Sidecar 생명주기 관리 |
| 로컬 API 서버 | **FastAPI** + Uvicorn | MIT | 비동기 변환 큐, 페이지 이미지 렌더링 캐시, 단일 페이지 OCR 재분석 |
| AI 레이아웃·표·수식 | **Docling** (Layout Heron, TableFormer, CodeFormulaV2) | MIT | 2단 영역, 병합 셀 표, 수식 LaTeX 추출 |
| 로컬 OCR | **RapidOCR** (ONNX Runtime) | Apache-2.0 | 스캔 교재·깨진 한글 CMap 선택적 복구 |
| PDF 렌더링·폰트 | **pypdfium2** + **pdfplumber** | Apache-2.0 / MIT | 고해상도 그림 크롭, bold/italic/위·아래첨자, Callout 박스 탐지 |

---

## 3. 변환 파이프라인

1. **Preflight 진단 (`preflight/analyzer.py`)**: 디지털/스캔 비율, 깨진 한글 CMap, 1단/2단 열 구조, 언어(`ko`/`en`/`mixed`) 자동 판별
2. **하이브리드 파싱 (`parsers/`)**:
   * **Mask-First 그림 보호**: 벡터 차트/도표 내부 텍스트가 본문으로 새지 않도록 마스킹 후 350 DPI PNG 크롭
   * **2단 읽기 순서 계획 (`column_planner.py`)**: 1단 제목/초록 → 2단 본문(왼쪽 단 → 오른쪽 단) → 2단 가로지르기 그림/표 순서 보존
3. **마크다운 컴파일 (`compiler/markdown_compiler.py`)**:
   * **수식**: `$$ ... \tag{N} $$` LaTeX 블록 생성
   * **표**: 일반 표는 GFM 파이프 표, 병합 셀(`row_span`/`col_span`) 표는 열 어긋남 없는 HTML `<table>` 생성
   * **그림**: `folder` (`<stem>_assets/` 분리) / `base64` / `none` 3모드 지원
   * **Callout 박스**: `> [!NOTE]`, `> [!IMPORTANT]` 등 GitHub/Obsidian Admonition 문법 변환
