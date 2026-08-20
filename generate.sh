#!/usr/bin/env bash
# SPECLOG 카드뉴스 - 원클릭 생성 (macOS/Linux)
# 조사 -> 콘텐츠 생성 -> 렌더링까지만 자동으로 진행합니다. 검토와 업로드는 항상 사람이
# 직접 합니다. 진행 상황은 이 터미널에 실시간으로 표시됩니다.
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "[SETUP] 처음 실행이라 가상환경을 만들고 필요한 패키지를 설치합니다. 몇 분 걸릴 수 있어요..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  playwright install chromium
else
  source .venv/bin/activate
fi

if [ ! -f ".env" ]; then
  echo
  echo "[경고] .env 파일이 없습니다."
  echo "  1) .env.example을 복사해서 .env로 저장하고"
  echo "  2) docs/SETUP.md를 참고해 API 키를 채워주세요."
  echo
  exit 1
fi

echo
echo "===== SPECLOG 카드뉴스 생성 ====="
echo "  1) 뉴스/트렌드   (news)"
echo "  2) 대외활동      (activity)"
echo "  3) 자격증        (license)"
echo "  4) 인턴/채용     (job)"
echo
read -p "번호를 입력하세요 (1-4): " choice

case "$choice" in
  1) CATEGORY=news ;;
  2) CATEGORY=activity ;;
  3) CATEGORY=license ;;
  4) CATEGORY=job ;;
  *) echo "잘못된 입력입니다. 1~4 중에서 골라주세요."; exit 1 ;;
esac

echo
read -p "특정 주제를 지정하시겠어요? (예: 카카오 2026 신입 공채 / 그냥 Enter시 자동 선정): " TOPIC

echo
if [ -z "$TOPIC" ]; then
  python -m pipeline.generate_only --category "$CATEGORY"
else
  python -m pipeline.generate_only --category "$CATEGORY" --topic "$TOPIC"
fi
