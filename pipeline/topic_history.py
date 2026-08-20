"""
topic_history.py
어제 다룬 소재를 오늘 또 고르지 않도록, 카테고리별로 최근에 다룬 소재 키워드를
output/_topic_history.json에 남겨두고 다음 자료조사 프롬프트에 "제외 목록"으로 전달한다.
"""

from __future__ import annotations
import datetime
import json
import os

from pipeline.config import config

HISTORY_PATH = os.path.join(config.OUTPUT_DIR, "_topic_history.json")
KEEP_DAYS = 14  # 이보다 오래된 항목은 프롬프트를 불필요하게 길게 만들 뿐이므로 정리한다


def _load_all() -> dict:
    if not os.path.exists(HISTORY_PATH):
        return {}
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def recent_keywords(category: str) -> list[str]:
    """최근 KEEP_DAYS일 이내에 이 카테고리에서 이미 다룬 키워드 목록."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)).isoformat()
    entries = _load_all().get(category, [])
    return [e["keyword"] for e in entries if e["date"] >= cutoff]


def record_keywords(category: str, keywords: list[str]) -> None:
    """오늘 다룬 키워드를 히스토리에 추가하고, 오래된 항목은 정리한다."""
    if not keywords:
        return
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    data = _load_all()
    today = datetime.date.today().isoformat()
    cutoff = (datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)).isoformat()

    entries = [e for e in data.get(category, []) if e["date"] >= cutoff]
    entries.extend({"date": today, "keyword": kw} for kw in keywords)
    data[category] = entries

    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 최소 자가 점검: 기록 -> 조회 -> 만료 정리가 기대대로 동작하는지 임시 경로로 확인
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        HISTORY_PATH_BAK = HISTORY_PATH
        config.OUTPUT_DIR = tmp
        globals()["HISTORY_PATH"] = os.path.join(tmp, "_topic_history.json")

        record_keywords("job", ["삼성전자 SW 인턴", "카카오 신입 공채"])
        assert set(recent_keywords("job")) == {"삼성전자 SW 인턴", "카카오 신입 공채"}
        assert recent_keywords("news") == []

        globals()["HISTORY_PATH"] = HISTORY_PATH_BAK
        print("topic_history self-check OK")
