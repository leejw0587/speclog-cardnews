"""
generate_only.py
"조사 → 생성 → 렌더링"까지만 자동화하고, 업로드는 사람이 결과물을 직접 열어 검토한 뒤
원하는 시점에 손으로 진행한다.

이 스크립트가 기본 실행 진입점이다.

실행 예:
    python -m pipeline.generate_only --category job

원클릭 실행(Windows)은 프로젝트 루트의 generate.bat을 더블클릭하면 된다 (내부에서 이 스크립트를
호출한다). 진행 상황은 콘솔에 실시간으로 출력되고, 같은 내용이 output/ 아래 로그 파일로도
저장된다.
"""

from __future__ import annotations
import argparse
import datetime
import os
import sys
import time

from pipeline import research_gemini, generate_content_claude, generate_cover_image, render_cardnews
from pipeline.config import config
from pipeline.schema import CategoryCode, SlotCode, CATEGORY_LABELS

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def _today_publish_date() -> str:
    now = datetime.datetime.now()
    return f"{now.year}.{now.month:02d}.{now.day:02d}({WEEKDAY_KR[now.weekday()]})"


def _current_slot() -> SlotCode:
    """정해진 발행 시간이 아니라, 실제로 생성한 시각을 HHMM으로 남긴다."""
    return datetime.datetime.now().strftime("%H%M")


class LiveLog:
    """콘솔에 실시간으로 찍으면서, 같은 내용을 파일에도 남기는 아주 작은 로거.
    별도 라이브러리 없이 print()만 쓰기 때문에 콘솔 창(cmd/터미널)에서 그대로 실시간으로 보인다."""

    def __init__(self, log_path: str):
        self.log_path = log_path
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        self._f = open(log_path, "w", encoding="utf-8")

    def step(self, msg: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        self._f.write(line + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()


def run(slot: SlotCode, category: CategoryCode) -> dict:
    publish_date = _today_publish_date()
    label = CATEGORY_LABELS[category]
    date_compact = publish_date.split("(")[0].replace(".", "")
    # 생성 1회 = 폴더 1개. 나중에 찾기 쉽도록 "날짜_생성시각_카테고리"로 묶는다.
    out_dir = os.path.join(config.OUTPUT_DIR, f"{date_compact}_{slot}_{category}")
    log_path = os.path.join(out_dir, "log.txt")
    log = LiveLog(log_path)

    t0 = time.time()
    try:
        log.step(f"시작 - 카테고리: {label} ({category}) / 생성 시각: {slot} / 발행일: {publish_date}")

        log.step("[1/4] 자료조사 중... (Gemini + Google 검색)")
        research = research_gemini.run(slot, category)
        n_items = len(research["raw"].get("items") or research["raw"].get("news_items") or [])
        log.step(f"      자료조사 완료 - {n_items}건 수집")

        log.step("[2/4] 카드 콘텐츠 생성 중... (Claude)")
        card = generate_content_claude.run(
            slot=slot, category=category, research_raw=research["raw"], publish_date=publish_date
        )
        card["slot"] = slot
        log.step(f"      콘텐츠 생성 완료 - 슬라이드 {len(card['slides'])}장 구성")

        log.step("[3/4] 표지 배경 이미지 생성 중... (Gemini 이미지 모델)")
        cover_slide = next((s for s in card["slides"] if s.get("type") == "cover"), None)
        if cover_slide:
            data_uri = generate_cover_image.generate_cover_background(category, cover_slide.get("bg_prompt", ""))
            if data_uri:
                cover_slide["bg_image_data_uri"] = data_uri
                log.step("      배경 이미지 생성 완료")
            else:
                log.step("      배경 이미지 생성 실패/키 없음 - 그라디언트로 대체 (문제 없음)")

        log.step("[4/4] 카드뉴스 렌더링 중... (HTML 저장 -> PNG 변환)")
        html_path, png_paths = render_cardnews.render_card(card, out_dir=out_dir)
        log.step(f"      렌더링 완료 - HTML 1개 + PNG {len(png_paths)}장")

        elapsed = time.time() - t0
        log.step(f"전체 완료 ({elapsed:.1f}초 소요)")
        log.step(f"검토용 HTML: {html_path}")
        log.step("이미지를 확인한 뒤, 마음에 들면 원하는 시점에 직접 업로드하세요.")

        return {"html_path": html_path, "png_paths": png_paths, "card": card, "log_path": log_path}
    except Exception as e:  # noqa: BLE001
        log.step(f"오류 발생: {e}")
        raise
    finally:
        log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SPECLOG 카드뉴스 - 조사부터 렌더링까지 원클릭 생성")
    parser.add_argument("--category", choices=["news", "activity", "license", "job"], required=True)
    args = parser.parse_args()

    slot = _current_slot()

    try:
        result = run(slot, args.category)
    except Exception as e:  # noqa: BLE001
        print(f"\n생성 중 오류가 발생했습니다: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n완료! 아래 파일을 브라우저로 열어 확인하세요:\n  {result['html_path']}")
