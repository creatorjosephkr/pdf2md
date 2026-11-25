# PDF 얼개 (PDF Eolgae) — 학술 PDF → 마크다운 · RTF 변환기

학술 논문 및 교재 PDF의 **2단 읽기 순서 · LaTeX 수식 · 병합 표 · 그림 크롭 · Callout 박스** 구조를 온전히 분석하여 깔끔한 **학술 마크다운(`.md`)**과 서식이 포함된 **RTF(`.rtf`)** 문서로 변환하는 100% 로컬 오픈소스 데스크톱 앱 & Python 변환 엔진입니다.

저장소: https://github.com/creatorjosephkr/pdf2md

## 주요 기능

* **레이아웃 정밀 분석 (`Docling` + `RapidOCR` + `Apple MPS` 가속)**: 2단 논문 읽기 순서, 수식(`$$... \tag{N}$$`), 병합 표(`rowspan`/`colspan`), 그림 크롭 및 한글 OCR을 로컬에서 처리합니다.
* **마크다운 원문 편집 & 서식 적용 미리보기**: `원문 편집`과 `미리보기` 탭 전환으로 KaTeX 수식·표·Callout·이미지를 즉시 확인하고 편집할 수 있습니다.
* **`.md` & 서식 있는 `.rtf` 저장**: 추출 그림을 포함한 `.md` 저장과 함께, 글꼴·표·콜아웃·PNG 바이너리가 내장된 단일 `.rtf` 파일 저장을 지원합니다.
* **GitHub 릴리즈 업데이트 체크**: 앱 상단 버전 버튼으로 [GitHub Releases](https://github.com/creatorjosephkr/pdf2md/releases) 최신 버전을 확인하고 설치 파일을 다운로드할 수 있습니다.

자세한 아키텍처는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)를 참고하세요.

---

## 1. Python 로컬 변환 엔진 (CLI & Sidecar)

* Python **3.12 ~ 3.13** + `uv`

```bash
cd engine
uv sync --python 3.12 --extra dev
```

### PDF 사전 진단 & 마크다운 변환
```bash
uv run pdf-convert diagnose ../samples/input/academic_2col_en.pdf
uv run pdf-convert convert ../samples/input/academic_2col_en.pdf -o ../samples/output/academic_2col_en.md
```

### 테스트 실행
```bash
uv run pytest -v
```

---

## 2. Tauri v2 데스크톱 앱 (`PDF 얼개 / PDF Eolgae`)

* **Node.js 20+** 및 **Rust (`rustc` / `cargo`)** 필요

```bash
cd apps/desktop
npm install
npm run tauri dev
```

### 릴리즈 빌드 산출물 명명 규칙
* macOS (Apple Silicon): `PDF_Eolgae_<version>_macOS_arm64.dmg`
* Windows (64-bit): `PDF_Eolgae_<version>_Windows_x64.exe`
