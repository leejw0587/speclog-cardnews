# SETUP - 자격증명 발급 & 실행 환경 설정 가이드

이 문서는 파이프라인을 실제로 돌리기 위해 필요한 자격증명 발급 방법을 안내합니다.
외부 서비스 화면/정책은 수시로 바뀌므로, 막히는 단계가 있으면 해당 서비스의
공식 문서를 함께 확인하세요.

**필요한 건 1~2번(Gemini, Claude)뿐입니다.** 이 프로젝트는 "조사 → 생성 → 렌더링"까지만
자동화하고, 검토·업로드는 항상 사람이 직접 합니다.

---

## 지금 하는 것: 로컬에서 원클릭 생성 준비

1. **Python 설치 확인** (3.10 이상). Windows는 [python.org](https://www.python.org/downloads/)에서
   설치 시 "Add python.exe to PATH" 체크.
2. **`.env` 파일 만들기**: `CardNews` 폴더의 `.env.example`을 복사해서 같은 폴더에 `.env`로
   저장합니다. 아래 1~2번에서 발급받은 키를 이 파일에 채워 넣습니다. (`.env`는 절대 남에게
   공유하거나 커밋하지 마세요.)
3. **`generate.bat`(Windows) 더블클릭**: 처음 실행 시 자동으로 가상환경을 만들고 필요한
   패키지(`requirements.txt`)와 Playwright 브라우저를 설치합니다 (몇 분 소요). 이후 카테고리
   번호(1~4)를 고르면 조사 → 생성 → 렌더링이 진행되며 콘솔에 실시간 로그가 뜹니다.
   완료되면 `output/{날짜}_{생성시각}_{카테고리}/` 폴더가 새로 만들어지고, 그 안의
   `deck.html`을 브라우저로 열면 표지부터 아웃트로까지 전체 카드뉴스를 한 번에 볼 수 있습니다.

---

## 1. Gemini API 키 (자료조사 + 표지 배경 이미지)

1. [Google AI Studio](https://ai.google.dev/gemini-api/docs/api-key)에 구글 계정으로 로그인합니다.
2. "Get API key" > "Create API key"로 새 키를 발급합니다 (개인 사용량 기준 무료 티어 제공).
3. 발급된 키를 `.env`의 `GEMINI_API_KEY`에 붙여넣습니다.
4. 이 프로젝트는 `google-genai` 파이썬 패키지와 Google 검색 그라운딩 기능을 사용합니다
   (`pipeline/research_gemini.py`). 별도 결제 계정 없이도 무료 한도 내에서 테스트 가능합니다.
5. 같은 키로 표지 배경 이미지도 생성합니다 (`pipeline/generate_cover_image.py`,
   모델: `gemini-2.5-flash-image`). 모델 ID가 바뀌면 `.env`의 `GEMINI_IMAGE_MODEL`만
   수정하면 됩니다 — 이미지 생성이 실패해도 파이프라인은 멈추지 않고 그라디언트 배경으로
   자동 대체됩니다.

## 2. Claude(Anthropic) API 키 (콘텐츠 생성)

1. [console.anthropic.com](https://console.anthropic.com)에서 계정을 만들고 결제 정보를 등록합니다.
2. **API Keys** 메뉴에서 새 키를 발급합니다.
3. `.env`의 `ANTHROPIC_API_KEY`에 붙여넣습니다.
4. `.env.example`의 `CLAUDE_MODEL` 기본값(`claude-sonnet-5`)은 실행 시점 기준 사용 가능한
   최신 모델 ID로 바꿔도 됩니다. Anthropic 문서(docs.claude.com)의 모델 목록을 확인하세요.

### 2-b. (선택) API 키 대신 Claude Pro/Max 구독으로 실행하기

Claude Pro/Max 구독자라면 종량 과금 API 키 없이, 본인 구독 사용량으로 콘텐츠 생성 단계를 돌릴
수 있습니다. **로컬 PC 실행 전용**입니다 — GitHub Actions 같은 원격 실행은 브라우저 로그인이
불가능해 계속 `ANTHROPIC_API_KEY`가 필요합니다.

1. `pip install claude-agent-sdk` (가상환경 활성화 상태에서).
2. 터미널에서 `claude setup-token` 실행 → 브라우저가 열리면 Claude 계정으로 로그인하고,
   완료되면 터미널에 토큰 문자열이 출력됩니다.
3. `.env`에 두 줄을 추가합니다 (`ANTHROPIC_API_KEY`는 비워둬도 됩니다):
   ```
   CLAUDE_AUTH_MODE=oauth
   CLAUDE_CODE_OAUTH_TOKEN=<2번에서 출력된 토큰 값>
   ```
   `claude` CLI의 로그인 세션에 자동으로 저장되는 게 아니라, 이 환경변수로 직접 넘겨줘야
   스크립트가 인식합니다 — `claude setup-token`만 하고 이 줄을 빼먹으면 "OAuth session
   expired" 에러가 납니다. 한 번만 설정해두면 이후 실행마다 다시 물어보지 않습니다.

`CLAUDE_AUTH_MODE`를 다시 지우거나 `api_key`로 바꾸면 기존 API 키 방식으로 돌아갑니다.

---

## 원격(클라우드)에서 생성하고 싶을 때

로컬 PC 대신 클라우드에서 돌리고 싶다면 `.github/workflows/speclog-publish.yml`을 씁니다.
**수동 실행(workflow_dispatch)만** 지원하며(자동 스케줄은 꺼둠), 결과 HTML/PNG를 Actions
아티팩트로 다운받아 검토하는 용도입니다.

1. GitHub에 **Private** 저장소를 만들고 `CardNews` 폴더를 푸시합니다 (`.env`는 `.gitignore`에
   포함되어 있으니 실수로 커밋되지 않습니다).
2. 저장소 > **Settings > Secrets and variables > Actions**에서 `GEMINI_API_KEY`,
   `ANTHROPIC_API_KEY`를 Secret으로, `GEMINI_IMAGE_MODEL`/`CLAUDE_MODEL`은 Variable로 등록합니다.
3. 저장소의 **Actions** 탭 > `SPECLOG 카드뉴스 생성 (수동 실행)` > **Run workflow**로 카테고리를
   골라 실행하면, 완료 후 Artifacts에서 결과물을 내려받을 수 있습니다.

---

## 체크리스트

- [ ] Python 설치 확인
- [ ] `.env` 파일 생성 (`.env.example` 복사)
- [ ] Gemini API 키 발급 → `.env`
- [ ] Anthropic API 키 발급 → `.env`
- [ ] `generate.bat`(또는 `generate.sh`) 실행해서 카드뉴스 1세트 생성 테스트
- [ ] 생성된 `output/{날짜}_{생성시각}_{카테고리}/deck.html`을 브라우저로 열어 디자인/문구 확인
- [ ] 마음에 들면 같은 폴더의 `.png`를 원하는 시점에 인스타그램 앱에서 직접 캐러셀로 업로드
