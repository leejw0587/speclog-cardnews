"""
research_gemini.py
파이프라인 1단계: Gemini API(Google Search 그라운딩)로 카테고리별 소재를 수집하고
표준 JSON(ResearchResult 유사 dict)으로 정제한다. (PRD 3.2 다이어그램의 "A. Gemini API")

실행 예:
    python -m pipeline.research_gemini --category job

주의:
- Gemini에게 "결과를 스스로 판단해서 지어내지 말고, 검색으로 찾은 사실만 채우라"고 명시한다.
- 마감일은 반드시 절대 날짜 문자열로만 받는다 (D-day 계산 금지, design.md F-05).
- 여기서 나온 결과는 아직 카드뉴스 문구가 아니라 '원재료'다. 최종 문구/톤은
  generate_content_claude.py(2단계)에서 만든다.
"""

from __future__ import annotations
import argparse
import json

from google import genai
from google.genai import types

from pipeline.config import config
from pipeline.schema import CategoryCode, SlotCode, CATEGORY_LABELS

RESEARCH_JSON_SCHEMA_HINT = {
    "job/activity/license": {
        "items": [
            {
                "org_name": "기관/기업명",
                "title": "공고/활동명",
                "deadline": "YYYY.MM.DD(요일) 형식의 절대 날짜. 상시모집이면 '상시모집'",
                "location": "장소 또는 '온라인'",
                "target": "지원 대상 원문",
                "benefit": "혜택/수당/상금 등",
                "source_url": "원문 링크",
                "raw_notes": "지원 방법, 전형 단계, 유의사항 등 자유 메모 (2~3문장 이내)",
            }
        ]
    },
    "news": {
        "items": [
            {
                "headline": "헤드라인",
                "summary": "3~4문장 사실 요약",
                "published_date": "YYYY.MM.DD",
                "source_url": "기사 원문 링크",
                "source_name": "매체명",
                "raw_notes": "취업/커리어 관점에서의 시사점 메모 (2~3문장 이내)",
            }
        ]
    },
}


def _prompt_for(category: CategoryCode) -> str:
    label = CATEGORY_LABELS[category]
    today_hint = "요청 시점 기준 최신"

    if category == "news":
        schema = RESEARCH_JSON_SCHEMA_HINT["news"]
        topic = (
            "대학생 취업/커리어에 영향을 주는 IT·산업 트렌드, 채용시장 동향 뉴스 4건 "
            "(정보 전달이 목적이므로 서로 다른 기업/기관/주제를 다루는 뉴스로 다양하게 모을 것 - "
            "같은 이슈를 다른 매체가 다룬 중복 기사는 피할 것)"
        )
    else:
        schema = RESEARCH_JSON_SCHEMA_HINT["job/activity/license"]
        topic_map = {
            "activity": "대학생 대상 대외활동/공모전 (아직 모집 마감 전) 2~3건",
            "license": "대학생이 취업 스펙으로 취득 가능한 자격증 시험/접수 일정 2~3건",
            "job": "대학생 대상 인턴/신입 채용 공고 (대기업/스타트업/공공기관 포함, 아직 지원 가능한 것) 2~3건",
        }
        topic = topic_map[category]

    return f"""
당신은 '스펙로그(SPECLOG)' 서비스의 자료조사 담당입니다.
목표 카테고리: [{label}]
수집 대상: {topic} ({today_hint})

규칙:
1. Google 검색으로 실제 확인 가능한 사실만 사용하세요. 확실하지 않은 정보는 만들어내지 마세요.
2. 마감일/일정은 반드시 "2026.09.15(화)" 같은 절대 날짜 문자열로 적으세요. "D-7" 같은 상대 표기는 절대 쓰지 마세요.
3. 출처 URL을 반드시 포함하세요.
4. 아래 JSON 스키마와 동일한 키를 가진 JSON만 출력하세요. 다른 설명 텍스트는 출력하지 마세요.
5. 각 필드는 스키마에 적힌 분량(문장 수)을 넘기지 마세요 — 이 결과는 다음 단계(Claude)로
   그대로 전달되는 원재료이므로, 장황한 문단 대신 사실 위주로 간결하게 씁니다.

JSON 스키마 예시:
{json.dumps(schema, ensure_ascii=False, indent=2)}
""".strip()


def run(slot: SlotCode, category: CategoryCode) -> dict:
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다 (.env 확인).")

    client = genai.Client(api_key=config.GEMINI_API_KEY)

    prompt = _prompt_for(category)

    # Google 검색 그라운딩 도구를 사용해 최신 사실 기반으로 응답하게 한다.
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[grounding_tool],
            temperature=0.2,
        ),
    )

    raw_text = response.text.strip()
    # 모델이 코드블록(```json ... ```)으로 감싸는 경우 제거
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Gemini 응답을 JSON으로 파싱하지 못했습니다: {e}\n원문:\n{raw_text[:2000]}"
        )

    return {
        "slot": slot,
        "category_code": category,
        "raw": data,  # items 또는 news_items 구조를 그대로 보존 (2단계에서 매핑)
    }


if __name__ == "__main__":
    import datetime

    parser = argparse.ArgumentParser()
    parser.add_argument("--category", required=True, choices=["news", "activity", "license", "job"])
    args = parser.parse_args()

    result = run(datetime.datetime.now().strftime("%H%M"), args.category)
    print(json.dumps(result, ensure_ascii=False, indent=2))
