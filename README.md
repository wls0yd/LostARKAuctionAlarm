# LostArkWatcher

실행 파일(`.exe`)은 아래 링크에서 바로 확인하고 다운로드할 수 있습니다.

- [exe 폴더로 이동 (exe)](./exe/)

## 다운로드 방법

1. 위 링크를 눌러 `exe` 폴더로 이동합니다.
2. 원하는 `.exe` 파일을 선택합니다.
3. 파일 화면에서 **Download raw file** 버튼으로 다운로드합니다.

## 자동 업데이트

- `LostArkWatcher.exe`를 실행하면 시작 후 자동으로 최신 exe를 확인합니다.
- 최신 파일이 있으면 자동 다운로드 후 실행 중인 exe를 교체하고 앱을 재시작합니다.
- 기본 확인 대상은 `Jeong-Jin-Yong/LostARKAccessoriesAlarm` 저장소의 `exe/LostArkWatcher.exe`입니다.

### 자동 업데이트 환경변수(선택)

- `LOSTARK_UPDATE_REPO`: 업데이트 원본 저장소(`owner/repo`), 기본값 `Jeong-Jin-Yong/LostARKAccessoriesAlarm`
- `LOSTARK_UPDATE_REF`: 조회 브랜치/태그, 미지정 시 저장소 기본 브랜치 자동 사용
- `LOSTARK_UPDATE_EXE_PATH`: 저장소 내 exe 경로, 기본값 `exe/LostArkWatcher.exe`

## 다른 사람들을 위한 빠른 시작 가이드

### 1) 먼저 준비할 것

- 윈도우 환경에서 실행하는 것을 기준으로 합니다.
- 로스트아크 API 토큰을 미리 준비해 주세요.

### 2) 가장 쉬운 실행 방법 (`.exe`)

1. 위의 `exe` 링크에서 `LostArkWatcher.exe`를 다운로드합니다.
2. 실행 후 토큰 입력(또는 환경변수 설정) 후 감시를 시작합니다.
3. 알림이 뜨면 게임 내 거래소에서 같은 옵션을 확인합니다.

### 3) 환경변수로 토큰 설정 (선택)

- 변수명: `LOSTARK_API_TOKEN`
- 값 형식: 원본 토큰 또는 `bearer <token>` 모두 허용
- 앱에서 `bearer ` 접두어를 자동 보정합니다.

### 4) 파이썬으로 직접 실행하고 싶다면

```bash
py src/watcher.py
```

- 콘솔만 사용하려면:

```bash
py src/watcher.py --cli
```

### 5) 자주 막히는 문제

- 실행이 안 될 때: 백신/SmartScreen 차단 여부를 먼저 확인하세요.
- 알림이 안 올 때: 토큰이 만료되었는지 확인하고 다시 입력하세요.
- 업데이트가 안 될 때: 인터넷 연결 상태와 업데이트 환경변수를 확인하세요.
