"""
render_cardnews.py
파이프라인 3단계: 표준 카드 JSON(generate_content_claude.py의 출력)을 templates/_deck.html에
매핑해서 카드 1세트 = HTML 파일 1개로 만들고(사용자 피드백: "하나의 html파일로 묶어서 제공"),
이어서 슬라이드별 PNG로 변환한다. (PRD 3.2 "이미지 변환" / design.md v2 8장)

HTML은 output/에 그대로 보존한다. 문구를 다듬고 싶으면 PNG를 다시 만들 필요 없이 이 HTML
파일을 브라우저로 열어 확인하고, 텍스트를 직접 수정한 뒤 render_html_to_png()만 다시 돌리면
이미지가 갱신된다. 두 단계를 분리해서 제공한다:

    render_card_html(card)      -> 통합 HTML 1개 생성 (빠름, 검토/수정용)
    render_html_to_png(...)     -> 이미 만들어진 HTML을 슬라이드별 PNG로 변환
    render_card(card)           -> 위 둘을 순서대로 실행하는 편의 함수

디자인은 여기서 만들지 않는다. templates/에 이미 정의된 고정 레이아웃(_slide_macros.html)에
데이터만 주입하고 스크린샷을 찍는다 (F-04).

PNG 변환은 Playwright의 element screenshot을 사용한다 - 페이지를 한 번만 로드하고,
슬라이드마다 `.canvas` 요소 하나씩을 캡처하기 때문에 파일은 하나여도 이미지는 장별로 나온다.

실행 예:
    python -m pipeline.render_cardnews --card card.json
"""

from __future__ import annotations
import argparse
import glob
import json
import os

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

from pipeline.config import config

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1350
DEVICE_SCALE_FACTOR = 2  # design.md 2장: 2x 렌더링 후 다운스케일 권장(텍스트 선명도)


def _folder_name(card: dict) -> str:
    """생성 1회 = 폴더 1개. 나중에 찾기 쉽도록 "날짜_생성시각_카테고리"로 묶는다."""
    date_compact = card["publish_date"].split("(")[0].replace(".", "")  # "20260819"
    slot = card.get("slot", "0000")  # 실제 생성 시각(HHMM)
    category = card["category_code"]
    return f"{date_compact}_{slot}_{category}"


def render_card_html(card: dict, out_dir: str | None = None) -> str:
    """카드 1세트를 하나의 HTML 파일로 렌더링해서 저장하고 경로를 반환한다."""
    out_dir = out_dir or os.path.join(config.OUTPUT_DIR, _folder_name(card))
    os.makedirs(out_dir, exist_ok=True)

    env = Environment(loader=FileSystemLoader(config.TEMPLATES_DIR), autoescape=True)
    template = env.get_template("_deck.html")

    ctx = dict(card)
    ctx.setdefault("brand_handle", "@speclog.official")

    html_out = template.render(card=ctx)
    html_path = os.path.join(out_dir, "deck.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_out)
    return html_path


def render_html_to_png(deck_html_path: str, slide_count: int, out_dir: str | None = None) -> list[str]:
    """통합 HTML 파일을 한 번 로드하고, 슬라이드(.canvas)마다 개별 PNG로 캡처한다."""
    out_dir = out_dir or os.path.dirname(deck_html_path)
    os.makedirs(out_dir, exist_ok=True)

    # 이전 실행에서 슬라이드 수가 더 많았다면 남는 PNG가 안 지워지고 섞여 남으므로 먼저 정리한다.
    for stale in glob.glob(os.path.join(out_dir, "*.png")):
        os.remove(stale)

    png_paths: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=DEVICE_SCALE_FACTOR)
        page.goto(f"file://{os.path.abspath(deck_html_path)}")
        page.wait_for_timeout(200)  # 웹폰트/이미지 로드 여유

        canvases = page.locator(".canvas")
        actual_count = canvases.count()
        if actual_count != slide_count:
            print(f"[render_html_to_png] 경고: 예상 슬라이드 수({slide_count})와 실제 .canvas 개수({actual_count})가 다릅니다.")

        for i in range(actual_count):
            png_path = os.path.join(out_dir, f"{i + 1:02d}.png")
            canvases.nth(i).screenshot(path=png_path)
            png_paths.append(png_path)

        browser.close()
    return png_paths


def render_card(card: dict, out_dir: str | None = None) -> tuple[str, list[str]]:
    """HTML 생성 + PNG 변환을 순서대로 실행하는 편의 함수. (html_path, png_paths)를 반환."""
    html_path = render_card_html(card, out_dir=out_dir)
    png_paths = render_html_to_png(html_path, slide_count=len(card["slides"]), out_dir=out_dir)
    return html_path, png_paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", required=True, help="generate_content_claude.py 출력 JSON 파일 경로")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--html-only", action="store_true", help="HTML만 생성하고 PNG 변환은 건너뜀")
    args = parser.parse_args()

    with open(args.card, encoding="utf-8") as f:
        card = json.load(f)

    if args.html_only:
        html_path = render_card_html(card, out_dir=args.out_dir)
        print(f"생성된 HTML: {html_path}")
    else:
        html_path, png_paths = render_card(card, out_dir=args.out_dir)
        print(f"생성된 HTML: {html_path}")
        print("생성된 이미지:")
        for p in png_paths:
            print(f"  {p}")
