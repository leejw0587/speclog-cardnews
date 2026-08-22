"""
config.py
환경 변수를 한 곳에서 로드한다. 실제 값은 .env 파일에 채운다 (.env.example 참조).
.env 파일은 절대 git에 커밋하지 않는다.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


class Config:
    # --- Gemini (자료조사 + 표지 배경 이미지 생성) ---
    GEMINI_API_KEY = _get("GEMINI_API_KEY")
    GEMINI_MODEL = _get("GEMINI_MODEL", default="gemini-3.6-flash")
    GEMINI_IMAGE_MODEL = _get("GEMINI_IMAGE_MODEL", default="gemini-2.5-flash-image")

    # --- Claude / Anthropic (콘텐츠 생성) ---
    ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
    CLAUDE_MODEL = _get("CLAUDE_MODEL", default="claude-sonnet-5")
    # "api_key"(기본, 종량 과금) 또는 "oauth"(Claude Pro/Max 구독 사용량, `claude setup-token`으로
    # 미리 로그인해둬야 함). docs/SETUP.md 참고.
    CLAUDE_AUTH_MODE = _get("CLAUDE_AUTH_MODE", default="api_key")

    # --- 경로 ---
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
    OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")


config = Config()
