"""
schema.py
SPECLOG 카드뉴스 파이프라인에서 단계 간에 주고받는 표준 JSON 구조를 정의한다.
design.md v2.7(카테고리 3그룹이 서로 다른 템플릿 타입 A/B/C를 쓰는 구조)와 짝을 이루는 코드 문서.

v2 변경점: 고정 6슬롯 대신 "slides": [{type, ...}, ...] 순서 리스트로 바꿨다.
- 한 슬라이드 = 한 메시지 원칙을 지키되, 여러 개가 될 수 있는 항목(예: 뉴스의 두 번째
  info_grid)은 슬라이드를 여러 장으로 나눈다 (리스트를 한 슬라이드에 욱여넣지 않는다).
- 렌더러(render_cardnews.py)는 slide["type"]으로 템플릿 파일명을 그대로 찾는다.

여기 정의된 타입/필드 이외의 것을 렌더러에 넘기지 않는다. 새 슬라이드 타입이 필요하면
반드시 design.md를 먼저 업데이트한 뒤 이 파일과 templates/*.html을 함께 수정한다 (F-04).
"""

from __future__ import annotations
from typing import Literal, TypedDict, NotRequired

CategoryCode = Literal["news", "activity", "license", "job"]
SlotCode = str  # 정해진 발행 슬롯이 아니라, 실제 생성 시각을 "HHMM" 형식으로 담는다 (예: "1512").
SlideType = Literal[
    "cover", "hero_fact", "info_grid", "target",
    "ai_analysis", "ai_response", "highlight", "caution", "outro",
]

CATEGORY_LABELS: dict[CategoryCode, str] = {
    "news": "뉴스/트렌드",
    "activity": "대외활동",
    "license": "자격증",
    "job": "인턴/채용",
}

# 카테고리 -> 템플릿 타입 (design.md 5.2)
# A=리포트형(대외활동/자격증), B=브리핑형(뉴스), C=간결형(인턴/채용) - v2.6부터 서로 다른 시퀀스를 쓴다.
CATEGORY_TEMPLATE_TYPE: dict[CategoryCode, str] = {
    "news": "B",
    "activity": "A",
    "license": "A",
    "job": "C",
}

# 템플릿 타입별로 항상 포함해야 하는 슬라이드 타입과 정확한 슬라이드 수 (design.md 5.2).
# 타입을 구분 짓는 "분석" 슬라이드(ai_analysis/ai_response/highlight)가 서로 다르다.
REQUIRED_TYPES_BY_TEMPLATE: dict[str, set[str]] = {
    "A": {"cover", "outro", "hero_fact", "target", "ai_analysis", "caution"},
    "B": {"cover", "outro", "hero_fact", "info_grid", "target", "ai_response", "caution"},
    "C": {"cover", "outro", "hero_fact", "target", "highlight", "caution"},
}
# B(뉴스)는 8장 - info_grid를 두 번 써서(대표 뉴스 상세 + 다른 소식 브리핑) 정보량을 늘린다.
SLIDE_COUNT_BY_TEMPLATE: dict[str, int] = {"A": 6, "B": 8, "C": 6}

# 타입별 요구 필드 (필드가 비어 있으면 렌더링 시 빈 값으로 나가므로, 생성 단계에서 반드시 채울 것)
SLIDE_TYPE_FIELDS: dict[SlideType, list[str]] = {
    "cover": ["headline", "bg_prompt"],
    "hero_fact": ["label", "value", "support"],  # extra_items(선택)는 필수 필드 아님
    "info_grid": ["heading", "items"],           # items: [{label, value}] 3~4개
    "target": ["heading", "items"],                # items: 문자열 리스트 3개 이내
    "ai_analysis": ["heading", "score", "score_label", "pros", "cons"],  # score: 0~100, pros/cons: 문자열 리스트 1~2개
    "ai_response": ["heading", "response", "reason"],  # response: 추천 행동 1문장, reason: 근거 1줄
    "highlight": ["heading", "items"],             # items: [{label, value}] 1~2개
    "caution": ["heading", "items"],               # items: 문자열 리스트 2개 이내
    "outro": ["cta_headline", "cta_sub", "source_text"],
}


# ---------------------------------------------------------------------------
# 1단계 산출물: 자료조사 결과 (Gemini API) - research_gemini.py의 출력
# 이 구조는 v1과 동일하게 유지 (자료조사는 슬라이드 디자인과 무관한 원재료 단계)
# ---------------------------------------------------------------------------

class ResearchItem(TypedDict):
    """리포트형(대외활동/자격증/인턴) 자료조사 1건."""
    org_name: str
    title: str
    deadline: str          # "2026.09.15(화)" 형식의 절대 날짜 문자열. D-day 계산 금지 (F-05)
    location: NotRequired[str]
    target: NotRequired[str]
    benefit: NotRequired[str]
    source_url: NotRequired[str]
    raw_notes: NotRequired[str]


class ResearchNewsItem(TypedDict):
    """브리핑형(뉴스/트렌드) 자료조사 1건."""
    headline: str
    summary: str
    published_date: str
    source_url: NotRequired[str]
    source_name: NotRequired[str]
    raw_notes: NotRequired[str]


# ---------------------------------------------------------------------------
# 2단계 산출물: 카드 콘텐츠 (Claude API) - generate_content_claude.py의 출력
# slides 리스트의 각 원소가 그대로 해당 type 템플릿의 Jinja2 변수로 주입된다.
# ---------------------------------------------------------------------------

REQUIRED_CARD_KEYS = {"category_code", "category_label", "publish_date", "slides", "caption", "used_topics"}


def example_card_skeleton(category_code: CategoryCode, publish_date: str) -> dict:
    """Claude 프롬프트에 예시로 보여줄 표준 카드 JSON 골격. 실제 값은 비워두고 구조와 타입
    시퀀스만 예시로 제공한다. 템플릿 타입(A/B/C)에 따라 슬라이드 구성이 다르다(design.md 5.2)."""
    template_type = CATEGORY_TEMPLATE_TYPE[category_code]
    base = {
        "category_code": category_code,
        "category_label": CATEGORY_LABELS[category_code],
        "publish_date": publish_date,   # "2026.08.19(수)"
        "caption": "",  # 인스타그램 게시물 캡션 (해시태그 포함)
        "used_topics": [],  # 실제로 이 카드에 담은 자료조사 항목 식별 문자열 (topic_history 기록용)
    }

    if template_type == "B":  # 브리핑형 (뉴스) - info_grid 2장으로 정보량 확보
        base["slides"] = [
            {"type": "cover", "headline": "", "bg_prompt": ""},
            {"type": "hero_fact", "label": "", "value": "", "support": ""},
            {"type": "info_grid", "heading": "무슨 일이 있었나", "items": [
                {"label": "", "value": ""}, {"label": "", "value": ""}, {"label": "", "value": ""},
            ]},
            {"type": "info_grid", "heading": "이번 주 더 챙길 소식", "items": [
                {"label": "", "value": ""}, {"label": "", "value": ""},
            ]},
            {"type": "target", "heading": "왜 중요한가", "items": []},
            {"type": "ai_response", "heading": "스펙로그 AI 추천 대응", "response": "", "reason": ""},
            {"type": "caution", "heading": "해석 시 주의점", "items": []},
            {"type": "outro", "cta_headline": "", "cta_sub": "", "source_text": ""},
        ]
    elif template_type == "C":  # 간결형 (인턴/채용)
        base["slides"] = [
            {"type": "cover", "headline": "", "bg_prompt": ""},
            {"type": "hero_fact", "label": "마감일", "value": "", "support": "", "extra_items": [
                {"label": "기관", "value": ""},
                {"label": "지원 방법", "value": ""},
                {"label": "전형 일정", "value": ""},
            ]},
            {"type": "target", "heading": "지원 자격", "items": []},
            {"type": "highlight", "heading": "스펙로그 AI가 찾은 특별한 점", "items": [
                {"label": "", "value": ""},
            ]},
            {"type": "caution", "heading": "지원 전 주의사항", "items": []},
            {"type": "outro", "cta_headline": "", "cta_sub": "", "source_text": ""},
        ]
    else:  # "A" 리포트형 (대외활동/자격증)
        base["slides"] = [
            {"type": "cover", "headline": "", "bg_prompt": ""},
            {"type": "hero_fact", "label": "마감일", "value": "", "support": "", "extra_items": [
                {"label": "기관/장소", "value": ""},
                {"label": "대상", "value": ""},
                {"label": "혜택", "value": ""},
            ]},
            {"type": "target", "heading": "추천 타깃", "items": []},
            {"type": "ai_analysis", "heading": "스펙로그 AI 시성비 분석", "score": 0, "score_label": "",
             "pros": [], "cons": []},
            {"type": "caution", "heading": "지원 전 주의사항", "items": []},
            {"type": "outro", "cta_headline": "", "cta_sub": "", "source_text": ""},
        ]

    return base


def validate_card(card: dict) -> list[str]:
    """필수 키/타입/D-day 표기 여부를 가볍게 검사한다 (외부 의존성 없이 dict 기반).
    반환값이 빈 리스트면 통과. render_cardnews.py 호출 전에 반드시 실행할 것."""
    errors: list[str] = []
    missing = REQUIRED_CARD_KEYS - card.keys()
    if missing:
        errors.append(f"최상위 필드 누락: {sorted(missing)}")
        return errors

    slides = card.get("slides", [])
    if not isinstance(slides, list) or not slides:
        errors.append("slides가 비어 있거나 리스트가 아님")
        return errors

    category_code = card.get("category_code")
    template_type = CATEGORY_TEMPLATE_TYPE.get(category_code)
    if template_type is None:
        errors.append(f"알 수 없는 category_code: '{category_code}'")
        return errors

    required_types = REQUIRED_TYPES_BY_TEMPLATE[template_type]
    expected_count = SLIDE_COUNT_BY_TEMPLATE[template_type]

    types_present = [s.get("type") for s in slides]

    for t in required_types:
        if t not in types_present:
            errors.append(f"필수 슬라이드 타입 누락 (템플릿 {template_type}): '{t}'")
    if types_present and types_present[0] != "cover":
        errors.append("첫 슬라이드는 반드시 'cover'여야 함")
    if types_present and types_present[-1] != "outro":
        errors.append("마지막 슬라이드는 반드시 'outro'여야 함")
    if len(slides) != expected_count:
        errors.append(
            f"템플릿 {template_type}는 {expected_count}장 고정 (현재 {len(slides)}장) - design.md 5.2"
        )

    for i, slide in enumerate(slides):
        stype = slide.get("type")
        if stype not in SLIDE_TYPE_FIELDS:
            errors.append(f"[{i}] 알 수 없는 슬라이드 타입: '{stype}'")
            continue
        for field in SLIDE_TYPE_FIELDS[stype]:
            if field not in slide or slide[field] in ("", None, []):
                errors.append(f"[{i}] type='{stype}' 필수 필드 비어있음: '{field}'")

        # D-day 계산 표기 금지 검사 (F-05) - value/text류 필드 전체를 훑는다
        for key in ("value", "text", "support", "big_text", "sub_text", "score_label"):
            val = slide.get(key)
            if isinstance(val, str) and (val.upper().startswith("D-") or val.upper().startswith("D+")):
                errors.append(f"[{i}] '{key}'에 D-day 표기가 감지됨 (F-05 위반): '{val}'")

    outro_slides = [s for s in slides if s.get("type") == "outro"]
    if outro_slides and not outro_slides[-1].get("source_text"):
        errors.append("outro.source_text(출처)가 비어 있음")

    used_topics = card.get("used_topics")
    if not isinstance(used_topics, list) or not used_topics or not all(isinstance(t, str) and t for t in used_topics):
        errors.append("used_topics가 비어 있거나 문자열 리스트가 아님 (실제로 다룬 자료조사 항목을 적어야 함)")

    return errors
