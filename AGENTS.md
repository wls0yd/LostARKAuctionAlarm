# AGENTS.md

이 문서는 `LostArkWatcher` 저장소에서 작업하는 에이전트용 작업 기준서입니다.
최우선 목표는 **비개발자도 쉽게 쓸 수 있는 악세서리 알람 앱**을 유지/개선하는 것입니다.

## 1) 저장소 개요

- 메인 애플리케이션: `watcher.py` (Tkinter 팝업 + CLI 감시 루프)
- 빌드 관련: `build_exe.bat`, `LostArkWatcher.spec` (PyInstaller onefile windowed)
- 실행 보조 스크립트: `run_watcher.bat`
- 런타임 산출물: `state.json`, `watch.log`, `dist/`, `build/`
- 언어/플랫폼: Python, Windows 중심

## 2) 명령어 기준 원칙

- 기본적으로 저장소에 이미 있는 스크립트(`build_exe.bat`, `run_watcher.bat`)를 우선 사용합니다.
- 저장소에 없는 도구 체인을 임의로 "있는 것처럼" 가정하지 않습니다.
- 새 도구(pytest/ruff/mypy 등)를 도입하면 README와 이 문서를 동시에 갱신합니다.

## 3) 환경 준비 명령

- Python 런처 우선순위
  - 1순위: `py`
  - 2순위: `python`
- pip 업데이트(필요 시)
  - `py -m pip install --upgrade pip`
  - 또는 `python -m pip install --upgrade pip`

## 4) 실행 명령

- GUI 모드(기본)
  - `py watcher.py`
  - 또는 `python watcher.py`
- CLI 모드(팝업 없이)
  - `py watcher.py --cli`
  - 또는 `python watcher.py --cli`
- 배치 스크립트 실행
  - `run_watcher.bat`

## 5) 빌드 명령

- 표준 빌드(권장)
  - `build_exe.bat`
- 수동 빌드(동등 명령)
  - `py -m pip install pyinstaller`
  - `py -m PyInstaller --noconfirm --clean --windowed --onefile --name LostArkWatcher watcher.py`
- 기대 결과물
  - `dist/LostArkWatcher.exe`

## 6) 린트 / 포맷 / 타입체크 현황

현재 저장소에는 전용 린트/포맷/타입체크 설정 파일이 없습니다.

- 미구성 도구
  - `ruff`
  - `flake8`
  - `black`
  - `isort`
  - `mypy`
  - `pyright`
- 최소 검증(구문 확인)
  - `py -m py_compile watcher.py`

도구를 새로 도입했다면 설정 파일과 명령어를 이 문서에 반드시 추가합니다.

## 7) 테스트 명령

현재는 `tests/` 디렉터리 및 pytest/unittest 자동 테스트가 없습니다.

- 자동 테스트 없음(현 상태)
- 기능 변경 시 수동 확인 필수
  - GUI 실행 후 탐색 시작/종료 동작 확인
  - API 토큰 유효성 검사 경로 확인
  - 로그 창 자동 갱신 확인
  - `state.json` 읽기/쓰기 확인

### 단일 테스트 실행 명령(향후 pytest 도입 시)

- 단일 테스트 파일
  - `py -m pytest tests/test_watcher.py -q`
- 단일 테스트 케이스
  - `py -m pytest tests/test_watcher.py::test_name -q`

## 8) 환경 변수 규칙

- `LOSTARK_API_TOKEN`
  - 원본 토큰 또는 `bearer <token>` 형태 허용
  - 코드에서 `bearer ` 접두어를 자동 보정
- `LOSTARK_WATCH_INTERVAL`
  - 감시 주기(초)
  - 기본값: `60`

## 9) 코드 스타일 가이드 (현 코드베이스 관찰 기반)

### Import

- import는 파일 상단에 배치합니다.
- 현재 코드는 표준 라이브러리 중심입니다.
- `tkinter` 하위 모듈은 명시 import(`messagebox`, `scrolledtext`)를 사용합니다.
- 와일드카드 import는 금지합니다.

### 네이밍

- 상수: `UPPER_SNAKE_CASE` (`API_URL`, `POLL_SECONDS`, `STATE_PATH`)
- 함수/변수: `snake_case`
- 클래스: `PascalCase` (`WatcherPopup`)
- 모니터 key 문자열도 snake_case(`necklace_damage`)를 유지합니다.

### 타입

- 최신 타입 힌트 문법 사용 (`list[dict]`, `dict[str, set[str]]`, `str | None`)
- 함수 시그니처 타입 주석을 일관되게 유지합니다.
- 가능하면 구체 타입을 사용하고, 불필요한 광범위 타입은 피합니다.
- 타입 억제 패턴(`as any`, `# type: ignore`)은 사용하지 않습니다.

### 포맷

- 4칸 들여쓰기 유지
- 가독성을 해치지 않도록 줄바꿈(특히 긴 f-string, 멀티라인 호출)을 적용
- 기존 파일 스타일(공백/괄호 배치)을 우선 따릅니다.

### 문자열/인코딩

- 파일 I/O는 UTF-8을 사용합니다.
- 한국어 UI 문구는 사용자 경험의 일부이므로 의도적 UX 개편이 아니면 유지합니다.
- JSON 저장 시 `ensure_ascii=False`를 유지합니다.

### 에러 처리

- GUI 입력 오류는 `messagebox.showerror`로 사용자에게 명확히 안내합니다.
- 감시 루프 예외는 `log(...)`에 기록하고 루프 전체는 가능한 한 유지합니다.
- HTTP 오류는 코드/응답 본문 등 진단 가능한 정보를 남깁니다.
- 광범위 예외 처리는 루프 경계(최상위 작업 경계)에서만 제한적으로 사용합니다.

### 로깅/상태 저장

- 임의 `print` 남발 대신 중앙 `log(...)` 경로를 사용합니다.
- `watch.log`는 현재 구현상 시간 단위 초기화 동작이 있으므로, 변경 시 의도를 명확히 남깁니다.
- 상태는 `state.json`의 `seen_by_monitor` 스키마를 기준으로 유지합니다.
- `load_state()`의 레거시 호환 로직은 스키마 변경 시에도 보존합니다.

### UI/스레딩

- Tkinter UI 업데이트는 메인 스레드 기준으로 유지합니다.
- 감시 로직은 백그라운드 daemon thread + `threading.Event`로 제어합니다.
- 실행/중지 버튼 상태는 실제 worker 상태와 동기화합니다.
- 장시간 작업이 Tkinter 메인루프를 블로킹하지 않게 설계합니다.

## 10) 변경 작업 원칙

- 요청 범위 내에서 최소 수정을 우선합니다.
- 현재 단일 파일 중심 구조를 불필요하게 분해하지 않습니다(리팩터링 요청 시 예외).
- 의존성 추가 시 빌드 경로와 사용자 실행 경로 영향도를 먼저 검토합니다.
- 테스트를 도입하면 `tests/` 구조와 단일 테스트 실행법을 문서에 즉시 반영합니다.
- 저장 상태(`state.json`)와 토큰 처리 로직은 하위 호환성을 최대한 유지합니다.
- Windows 사용성을 우선 고려합니다(`.bat`, `winsound`, exe 배포 흐름).
- Git 커밋 워크플로우는 기본적으로 `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:` 같은 접두어를 사용하는 형식을 따릅니다.
- 커밋 메시지는 가능하면 변경 이유가 드러나도록 짧고 명확하게 작성합니다.

## 11) 작업 완료 전 검증 체크리스트

- 최소: `py -m py_compile watcher.py` 실행
- 실행 검증: GUI 1회 실행 및 시작/중지 동작 확인
- 감시 로직 변경 시: `--cli` 모드도 짧게 점검
- 빌드 관련 변경 시: `build_exe.bat` 실행 후 `dist/LostArkWatcher.exe` 확인
- 생성 산출물(`build/`, `dist/`, 로그/상태 파일) 의도치 않은 변경 여부 확인

## 12) Cursor / Copilot 규칙 파일 확인 결과

- `.cursorrules`: 없음
- `.cursor/rules/`: 없음
- `.github/copilot-instructions.md`: 없음

즉, 이 저장소에서 에이전트 동작 기준 문서는 현재 `AGENTS.md`가 유일합니다.

## 13) 제품 목표 기준 의사결정

- 항상 "사용자가 편하게 쓸 수 있는가"를 최우선으로 판단합니다.
- 설정/실행 단계를 늘리는 변경은 신중히 검토합니다.
- 오류 메시지는 기술자 중심이 아니라 사용자 행동 유도 중심으로 작성합니다.
- 배포 산출물 경로(`dist/LostArkWatcher.exe`)는 항상 명확하게 유지합니다.

## 14) 권장 커뮤니케이션 규칙(에이전트용)

- 변경 시 "무엇을/왜"를 짧고 명확하게 보고합니다.
- 확인한 근거 파일 경로를 함께 남깁니다.
- 추정 대신 실제 파일/명령 결과 기반으로 판단합니다.
- 자동 테스트가 없으므로 수동 검증 결과를 반드시 명시합니다.
