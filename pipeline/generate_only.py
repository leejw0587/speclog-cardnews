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
import ctypes
import datetime
import os
import subprocess
import sys
import time
import webbrowser

from pipeline import research_gemini, generate_content_claude, generate_cover_image, render_cardnews, topic_history
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


def _open_folder(path: str) -> None:
    if sys.platform == "win32":
        subprocess.Popen(["explorer", path])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _open_in_browser(html_path: str) -> None:
    webbrowser.open(f"file:///{os.path.abspath(html_path)}", new=1)


def _copy_to_clipboard(text: str) -> None:
    if sys.platform == "win32":
        # 표준 라이브러리(ctypes)만으로 유니코드 클립보드 복사 (Win32 API 직접 호출).
        # GlobalAlloc/GlobalLock의 반환형을 명시하지 않으면 ctypes 기본값(32비트 int)으로
        # 포인터가 잘려서 64비트 프로세스에서 access violation이 난다 - wintypes로 명시할 것.
        from ctypes import wintypes

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32

        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
        kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
        user32.SetClipboardData.restype = wintypes.HANDLE
        user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)

        data = text.encode("utf-16-le") + b"\x00\x00"
        if not user32.OpenClipboard(0):
            raise OSError("클립보드를 열 수 없습니다.")
        try:
            user32.EmptyClipboard()
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            ptr = kernel32.GlobalLock(h_mem)
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(h_mem)
            user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        finally:
            user32.CloseClipboard()
    elif sys.platform == "darwin":
        subprocess.run("pbcopy", input=text.encode("utf-8"), check=True)
    else:
        subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), check=True)


def _reveal_result(out_dir: str, html_path: str, caption: str, log: LiveLog) -> None:
    """결과 폴더/HTML을 새 창으로 띄우고 캡션을 클립보드에 복사한다. GUI/클립보드가 없는 환경
    (예: GitHub Actions)에서도 파이프라인 자체는 실패하지 않도록 단계별로 실패를 흡수한다."""
    for label, action in [
        ("결과 폴더 열기", lambda: _open_folder(out_dir)),
        ("HTML 새 창으로 열기", lambda: _open_in_browser(html_path)),
        ("캡션 클립보드 복사", lambda: _copy_to_clipboard(caption)),
    ]:
        try:
            action()
            log.step(f"      {label} 완료")
        except Exception as e:  # noqa: BLE001
            log.step(f"      {label} 실패 (건너뜀): {e}")


def run(slot: SlotCode, category: CategoryCode, topic: str | None = None) -> dict:
    publish_date = _today_publish_date()
    label = CATEGORY_LABELS[category]
    date_compact = publish_date.split("(")[0].replace(".", "")
    # 생성 1회 = 폴더 1개. 나중에 찾기 쉽도록 "날짜_생성시각_카테고리"로 묶는다.
    out_dir = os.path.join(config.OUTPUT_DIR, f"{date_compact}_{slot}_{category}")
    log_path = os.path.join(out_dir, "log.txt")
    log = LiveLog(log_path)

    t0 = time.time()
    try:
        topic_note = f" / 지정 주제: {topic}" if topic else ""
        log.step(f"시작 - 카테고리: {label} ({category}) / 생성 시각: {slot} / 발행일: {publish_date}{topic_note}")

        log.step("[1/4] 자료조사 중... (Gemini + Google 검색)")
        research = research_gemini.run(slot, category, topic=topic)
        n_items = len(research["raw"].get("items") or research["raw"].get("news_items") or [])
        log.step(f"      자료조사 완료 - {n_items}건 수집")

        log.step("[2/4] 카드 콘텐츠 생성 중... (Claude)")
        card = generate_content_claude.run(
            slot=slot, category=category, research_raw=research["raw"], publish_date=publish_date
        )
        card["slot"] = slot
        log.step(f"      콘텐츠 생성 완료 - 슬라이드 {len(card['slides'])}장 구성")

        # 실제로 카드에 담긴 소재만 히스토리에 남긴다 (조사만 하고 버려진 후보는 기록하지 않음)
        topic_history.record_keywords(category, card.get("used_topics") or [])

        log.step("[3/4] 표지 배경 이미지 생성 중... (Gemini 이미지 모델)")
        cover_slide = next((s for s in card["slides"] if s.get("type") == "cover"), None)
        if cover_slide:
            data_uri, error = generate_cover_image.generate_cover_background(category, cover_slide.get("bg_prompt", ""))
            if data_uri:
                cover_slide["bg_image_data_uri"] = data_uri
                log.step("      배경 이미지 생성 완료")
            else:
                log.step(f"      배경 이미지 생성 실패 - 그라디언트로 대체 (문제 없음). 사유: {error}")

        log.step("[4/4] 카드뉴스 렌더링 중... (HTML 저장 -> PNG 변환)")
        html_path, png_paths = render_cardnews.render_card(card, out_dir=out_dir)
        log.step(f"      렌더링 완료 - HTML 1개 + PNG {len(png_paths)}장")

        elapsed = time.time() - t0
        log.step(f"전체 완료 ({elapsed:.1f}초 소요)")
        log.step(f"검토용 HTML: {html_path}")

        log.step("결과 폴더/HTML을 열고 캡션을 클립보드에 복사합니다...")
        _reveal_result(out_dir, html_path, card.get("caption") or "", log)
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
    parser.add_argument("--topic", default=None, help="지정하면 이 소재만 조사해서 카드뉴스로 만든다")
    args = parser.parse_args()

    slot = _current_slot()

    try:
        result = run(slot, args.category, topic=args.topic)
    except Exception as e:  # noqa: BLE001
        print(f"\n생성 중 오류가 발생했습니다: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n완료! 아래 파일을 브라우저로 열어 확인하세요:\n  {result['html_path']}")
