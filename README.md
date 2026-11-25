<img width="200" height="200" alt="app-icon" src="https://github.com/user-attachments/assets/c4c746fa-3bc1-4546-8c39-72907b264335" />


# PDF 얼개 (PDF Eolgae) — 학술 PDF → 마크다운 · RTF 변환기

학술 논문 및 교재 PDF의 **2단 읽기 순서 · LaTeX 수식 · 병합 표 · 그림 크롭 · Callout 박스** 구조를 온전히 분석하여 깔끔한 **학술 마크다운(`.md`)**과 서식이 포함된 **RTF(`.rtf`)** 문서로 변환하는 100% 로컬 오픈소스 데스크톱 앱 & Python 변환 엔진입니다.

저장소: https://github.com/creatorjosephkr/pdf2md

## 주요 기능

* **레이아웃 정밀 분석 (`Docling` + `RapidOCR` + `Apple MPS` 가속)**: 2단 논문 읽기 순서, 수식(`$$... \tag{N}$$`), 병합 표(`rowspan`/`colspan`), 그림 크롭 및 한글 OCR을 로컬에서 처리합니다.
* **마크다운 원문 편집 & 서식 적용 미리보기**: `원문 편집`과 `미리보기` 탭 전환으로 KaTeX 수식·표·Callout·이미지를 즉시 확인하고 편집할 수 있습니다.
* **`.md` & 서식 있는 `.rtf` 저장**: 추출 그림을 포함한 `.md` 저장과 함께, 글꼴·표·콜아웃·PNG 바이너리가 내장된 단일 `.rtf` 파일 저장을 지원합니다.
* **GitHub 릴리즈 업데이트 체크**: 앱 상단 버전 버튼으로 [GitHub Releases](https://github.com/creatorjosephkr/pdf2md/releases) 최신 버전을 확인하고 설치 파일을 다운로드할 수 있습니다.

자세한 아키텍처는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)를 참고하세요.

<img width="2984" height="2144" alt="image" src="https://github.com/user-attachments/assets/e7186101-abbe-4025-8138-cf43a03bb7be" />

<img width="2984" height="2144" alt="image" src="https://github.com/user-attachments/assets/37d560f6-83d6-4879-a198-d2c3d7a5cab2" />

<img width="2984" height="2144" alt="image" src="https://github.com/user-attachments/assets/a3e5c7a1-b72e-4d58-aadd-a39e908c3e8e" />

<img width="2984" height="2144" alt="image" src="https://github.com/user-attachments/assets/bcb76aba-6ffe-4e2a-ba3d-0c3d4896358c" />



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
* macOS (Intel): `PDF_Eolgae_<version>_macOS_x64.dmg`
* Windows (64-bit): `PDF_Eolgae_<version>_Windows_x64.exe`

---

## 3. 설치 및 처음 실행 안내 (미서명 오픈소스 앱)

본 앱은 별도의 상용 개발자 인증서 없이 배포되는 오픈소스 프로젝트이므로, 첫 실행 시 OS 기본 보안 확인 화면이 나타날 수 있습니다.

### macOS
1. 다운로드한 `.dmg` 파일을 열어 **`PDF Eolgae.app`** 을 **`Applications`** 폴더로 드래그해 복사합니다.
2. 처음 실행 시 **"확인되지 않은 개발자"** 또는 차단 팝업이 뜨면 **`완료` / `확인`** 을 누른 뒤, **시스템 설정 → 개인정보 보호 및 보안** 하단에서 **`'그래도 열기'`** 를 선택합니다. (또는 `응용 프로그램` 폴더에서 앱을 `Control + 클릭` → **`열기`**)
3. 이후 실행부터는 보안 확인 없이 바로 열립니다.

### Windows
1. **`PDF_Eolgae_1.0.0_Windows_x64.exe`** 를 실행합니다. (현재 사용자 계정 설치 방식이므로 관리자 권한 없이 설치됩니다.)
2. **Windows의 PC 보호(SmartScreen)** 화면이 나타나면 왼쪽의 **`추가 정보`** 를 클릭한 뒤 아래쪽 **`실행`** 버튼을 누릅니다.
