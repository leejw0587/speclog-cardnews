@echo off
chcp 949 >nul
REM SPECLOG 카드뉴스 - 원클릭 생성 (Windows)
REM 더블클릭으로 실행하세요. 조사 -> 콘텐츠 생성 -> 렌더링까지만 자동으로 진행합니다.
REM 검토와 업로드는 항상 사람이 직접 합니다.
REM 진행 상황은 이 창에 실시간으로 표시됩니다.
REM (이 파일은 한글이 깨지지 않도록 CP949(EUC-KR)로 저장되어 있습니다. 메모장 등으로 다시
REM  저장할 경우 인코딩을 "ANSI"로 유지해주세요 - UTF-8로 저장하면 다시 깨집니다.)

setlocal
cd /d "%~dp0"

if not exist ".venv" (
    echo [SETUP] 처음 실행이라 가상환경을 만들고 필요한 패키지를 설치합니다. 몇 분 걸릴 수 있어요...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
    playwright install chromium
) else (
    call .venv\Scripts\activate.bat
)

if not exist ".env" (
    echo.
    echo [경고] .env 파일이 없습니다.
    echo   1^) .env.example을 복사해서 .env로 저장하고
    echo   2^) docs\SETUP.md를 참고해 API 키를 채워주세요.
    echo.
    pause
    exit /b 1
)

echo.
echo ===== SPECLOG 카드뉴스 생성 =====
echo   1^) 뉴스/트렌드   (news)
echo   2^) 대외활동      (activity)
echo   3^) 자격증        (license)
echo   4^) 인턴/채용     (job)
echo.
set /p choice="번호를 입력하세요 (1-4): "

set CATEGORY=
if "%choice%"=="1" set CATEGORY=news
if "%choice%"=="2" set CATEGORY=activity
if "%choice%"=="3" set CATEGORY=license
if "%choice%"=="4" set CATEGORY=job

if "%CATEGORY%"=="" (
    echo 잘못된 입력입니다. 1~4 중에서 골라주세요.
    pause
    exit /b 1
)

echo.
python -m pipeline.generate_only --category %CATEGORY%

echo.
echo 창을 닫으려면 아무 키나 누르세요.
pause > nul
