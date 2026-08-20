"""
generate_content_claude.py
파이프라인 2단계: Claude API로 자료조사 원문(research_gemini.py의 출력)을
표준 카드 JSON(schema.example_card_skeleton 구조, design.md v2)으로 변환한다.
디자인/레이아웃은 만들지 않는다 — 오직 슬라이드 타입을 고르고 그 안의 문구만 채운다 (F-04).

실행 예:
    python -m pipeline.generate_content_claude --research research.json --publish-date "2026.08.19(수)"
"""

from __future__ import annotations
import argparse
import json

import anthropic

from pipeline.config import config
from pipeline.schema import (
    CategoryCode, SlotCode, CATEGORY_LABELS, CATEGORY_TEMPLATE_TYPE,
    example_card_skeleton, validate_card,
)

SYSTEM_PROMPT = """\
당신은 대학생 대상 커리어 리포트 '스펙로그(SPECLOG)'의 카피라이터다.
역할은 디자인이 아니라 "정해진 슬라이드 타입을 고르고 그 슬롯에 들어갈 문구를 채우는 것"이다.
아래 원칙을 반드시 지킬 것.

[슬라이드 설계 원칙]
1. 한 슬라이드 = 한 메시지. 여러 정보를 한 슬라이드에 욱여넣지 않는다(단, ai_analysis/
   ai_response/highlight는 그 자체가 "분석"이라는 하나의 메시지이므로 점수+근거, 문장+근거
   같은 세부 구성요소가 함께 있어도 됨).
2. 첫 장(cover)은 후킹. "이거 나한테 필요한데?"를 넘어 "지금 안 보면 손해"라는
   위기감까지 주는 강렬하고 구체적인 한 줄로 쓴다 (22자 이내). 다음 기법을 적극 활용할 것:
   숫자로 구체화("3곳 중 1곳은 이번 주 마감"), 손실 프레이밍("놓치면 후회", "이미 절반 지남"),
   직접 화법("당신의 스펙, 이번 주가 골든타임"). 밋밋한 제목("OO 인턴십 안내")은 금지.
   bg_prompt는 배경 이미지 생성 프롬프트의 재료다 — 소재와 무관한 막연한 장면(예: "도시
   야경") 대신, 이 카드가 다루는 구체적인 소재를 연상시키는 장면을 한국어 1문장으로 쓴다
   (예: 카카오뱅크 인턴 공고면 "IT 기업 사무실 데스크에 노트북과 서류가 놓인 모습"). 사람
   얼굴/텍스트가 나오는 장면은 피한다. (실제 이미지 생성은 별도 단계에서 처리.)
3. 카테고리마다 슬라이드 구성이 고정. 아래 세 템플릿 중 카테고리에 맞는 것을
   그대로 따를 것 (개수를 줄이거나 늘리지 않음):
   - **템플릿 A (대외활동/자격증), 6장:**
     cover → hero_fact → target → ai_analysis → caution → outro
   - **템플릿 B (뉴스/트렌드), 8장:** 뉴스는 정보 전달이 목적이라 info_grid를 두 번 씀.
     cover → hero_fact → info_grid(대표 뉴스 상세) → info_grid(다른 뉴스 브리핑)
     → target → ai_response → caution → outro
   - **템플릿 C (인턴/채용), 6장:** 더 간결하게, 점수 대신 이 공고만의 특별한 점을 보여줌.
     cover → hero_fact → target(지원 자격) → highlight → caution → outro. 채용 정보는
     "어디에 뭘 지원하는지"가 명확해야 하므로, 기관명·지원 방법·지원 자격을 빠짐없이 채운다
     (아래 4·6·13번 참고).
4. hero_fact는 핵심 사실(대부분 마감일) 하나를 큰 값으로 제시. 템플릿 A에서는
   extra_items에 기관/장소/대상/혜택 중 2~3개를 {label, value} 형태로 함께 채운다. 템플릿
   C(인턴/채용)는 extra_items에 반드시 **기관(회사명)**과 **지원 방법**(어디서/어떻게
   지원하는지 - 채용 사이트명, 자사 홈페이지, 이메일 접수 등 구체적 채널)을 포함하고, 남는
   자리에 전형 일정 등을 추가한다 — "어느 회사인지, 어디서 지원하는지"가 카드만 봐도
   바로 보여야 함. 템플릿 B(뉴스)는 hero_fact를 대표 뉴스 1건의 핵심 수치/한줄 사실만
   담백하게 쓰고 extra_items는 비운다 — 보조 사실은 아래 5번의 info_grid가 따로 담당.
5. info_grid는 템플릿 B(뉴스) 전용이며 두 번 등장. 자료조사 데이터에는 뉴스 여러 건이
   들어있음 — 그중 하나만 대충 골라 쓰지 말고 모두 활용할 것:
   - 1번째 info_grid("무슨 일이 있었나"): hero_fact가 다룬 대표 뉴스 1건을 사실 3~4개로
     풀어서 설명한다 — 단순 재진술이 아니라 배경/맥락(누가, 무엇을, 규모, 비교 등)을 담아
     정보량을 충분히 줄 것.
   - 2번째 info_grid("이번 주 더 챙길 소식" 등): 자료조사에서 수집한 **나머지 뉴스 2~3건을
     전부** label=매체·기업/기관명, value=헤드라인+핵심 시사점 한 줄로 요약. 대표 뉴스와
     겹치지 않는 별개 소식이어야 하고, 항목을 임의로 줄이지 않음 — "1분 1초가 아까운"
     취준생에게 오늘의 취업 동향을 빠짐없이 브리핑하는 슬라이드임.
6. target은 추천 타깃("이런 사람에게 추천"). 템플릿 B(뉴스)에서는 heading을 "왜
   중요한가"로 바꿔서 "누구에게/어떻게 영향이 있는지"를 쓴다. 템플릿 C(인턴/채용)에서는
   heading을 "지원 자격"으로 쓰고, 막연한 인물상("열정 있는 분")이 아니라 원문에 있는
   구체적 자격 조건(학년/전공/어학 점수/경력 등)을 items에 그대로 반영 — 원문에 없는
   조건은 지어내지 않음.
7. caution은 지원/열람 전 놓치기 쉬운 맹점(예: "학기 병행 불가", "서류만 봐도
   광탈하는 흔한 실수"). 모든 템플릿에 항상 포함하고, 단순 정보 재진술이 아니라 실제로
   유용한 주의사항일 것.
8. 템플릿별 "분석" 슬라이드(ai_analysis/ai_response/highlight)는 뻔한 내용을 금지하는 핵심
   규칙 — "일찍 지원하세요", "자소서 꼼꼼히 쓰세요" 같이 누구나 아는 말은 절대 금지.
   이 세 슬라이드는 스펙로그만의 차별화 포인트이므로 heading에 항상 "스펙로그
   AI"를 넣을 것(기본값을 그대로 쓰거나, 소재에 맞게 "스펙로그 AI ○○"로 자연스럽게
   바꿔도 됨) — "AI 분석"처럼 브랜드 없이 쓰지 않음.
   - **ai_analysis (템플릿 A 전용):** score(0~100)는 "정보 자체의 가치"가 아니라 **이
     소재를 준비하는 데 드는 노력/시간 대비 실제로 얻는 경쟁력**을 근거로 매김. 준비
     부담은 큰데 남들도 다 아는 흔한 스펙이면 낮게, 부담 대비 확실히 경쟁력이 올라가면
     높게. 모든 카드에 비슷한 점수(예: 항상 80점대)를 주지 말 것 — 소재마다 실제로
     달라야 함. score_label(20자 이내)에 근거를 한 줄로("경쟁률 낮은데 혜택은 큼" 등).
     pros(1~2개)/cons(1~2개)는 공고 원문을 그대로 옮기지 말고 "왜 유리한지"·"왜 불리하거나
     번거로운지"를 직접 판단해서 쓴다.
   - **ai_response (템플릿 B 전용):** response는 팔로우/저장 같은 CTA가 아니라 **이 트렌드에
     지금 어떻게 대응해야 하는지 구체적 행동 한 문장**(예: "포트폴리오에 이 키워드부터
     추가하세요"). reason(1줄)에 왜 지금 그래야 하는지 근거를 쓴다.
   - **highlight (템플릿 C 전용):** items는 1~2개, 이 공고를 다른 공고와 구분 짓는 **사실**
     위주로 씀(전환율, 처우, 실무 범위 등 숫자·고유명사). "좋은 기회입니다" 같은 뭉뚱그린
     칭찬은 금지.
9. 텍스트는 짧고 굵게: 표지 22자, hero_fact 보조문구 20자, target/caution/highlight의
   items 및 ai_analysis의 pros·cons 항목 40자, ai_analysis의 score_label과 ai_response의
   reason 20자, 그 외 본문 슬라이드 50자 이내. 상한을 넘기면 문장을 자르지 말고 더 짧게
   다시 쓴다.
10. 마감일/일정은 반드시 절대 날짜("2026.09.15(화)")만 사용. "D-7", "마감임박" 같은
    상대적/계산된 표현은 절대 금지.
11. outro의 cta_headline은 "저장하세요" 같은 뭉뚱그린 말이 아니라 구체적 행동 하나를 지시.
    예: "팔로우하고 매일 아침 스펙 정보 받기", "저장해두고 마감일 놓치지 않기". cta_sub에는
    가끔(모든 카드마다는 아님) "매일 스펙로그 하나면 충분합니다" 같은 정기 발행
    메시지를 자연스럽게 녹여도 됨.
12. AI가 지어낸 티가 나는 과장된 문구, 이모지 남발을 피하고, 단정하고 신뢰감 있는 톤을 유지.
    표/그래프 같은 장식적 시각 자료는 만들지 않음 — ai_analysis의 점수 바 정도의 절제된
    표현이면 충분.
13. 출처(마지막 outro 슬라이드의 source_text)는 반드시 채운다. 원문에 없는 사실은 만들어내지
    않음. 템플릿 C(인턴/채용)는 source_text에 원문의 지원 링크(source_url)를 그대로
    담아, 독자가 카드만 보고도 어디서 지원할 수 있는지 알 수 있게 한다.
14. caption(인스타그램 게시물 본문)은 카드뉴스 내용을 그대로 반복하지 않고, 자료조사 원문의
    세부 정보를 활용해 다음 순서로 작성: [핵심 요약] → [세부 자격요건 & 우대사항]
    → [SPECLOG 분석: 성공 전략] → [마감 안내] → [해시태그].
    - **해시태그는 최대 5개**, 그중 하나는 반드시 **"#스펙로그"**. 나머지 4개는
      (a) 게시물 수가 많고 노출이 잘 되는 범용 해시태그(예: #취업정보, #취준생) 1~2개 +
      (b) 이 게시물 소재와 직접 관련된 해시태그(회사명/직무/분야/자격증명 등, 원문에 있는
      고유명사 기반) 1~2개로 구성. 채우기용으로 관련 없는 해시태그를 늘리지 않음.
    - 카테고리가 인턴/채용(job)일 때는 [세부 자격요건 & 우대사항] 섹션에 반드시 (1) 채용
      기업/기관명, (2) 지원 방법 또는 지원 가능한 곳(채용 사이트/링크/접수 채널),
      (3) 원문에 있는 구체적 지원 자격(학년/전공/어학/경력 등)을 빠짐없이 적는다 — 카드뉴스
      슬라이드를 안 봐도 캡션만으로 "어디에, 어떻게, 누가" 지원할 수 있는지 알 수 있어야 함.
15. used_topics는 이 카드가 실제로 다룬 자료조사 항목을 식별하는 문자열 리스트 —
    다음 실행에서 같은 소재를 또 고르지 않도록 기록해두는 용도. 자료조사 원문의 항목과
    정확히 같은 값으로 쓴다: job/activity/license는 "{org_name} {title}" 형식(둘을
    공백으로 이어붙임), news는 headline 그대로. 템플릿 A/C는 보통 카드 하나가 항목 하나만
    다루므로 1개, 템플릿 B(뉴스)는 실제로 슬라이드(hero_fact + 두 info_grid)에 담은 뉴스
    전부를 나열. 자료조사에서 받았지만 이 카드에 쓰지 않은 항목은 넣지 않음.
16. 출력은 오직 JSON 하나만 반환. 다른 설명 텍스트는 붙이지 않음.
"""


def _build_user_prompt(
    slot: SlotCode,
    category: CategoryCode,
    research_raw: dict,
    publish_date: str,
) -> str:
    skeleton = example_card_skeleton(category, publish_date)
    template_type = CATEGORY_TEMPLATE_TYPE[category]
    sequence_hint = {
        "A": "cover → hero_fact(마감일 + extra_items: 기관/대상/혜택) → target(추천 타깃) "
             "→ ai_analysis(준비 노력 대비 경쟁력 점수 + Pros/Cons) → caution(지원 시 맹점) → outro  [6장 고정]",
        "B": "cover → hero_fact(대표 뉴스 핵심 수치/한줄 사실) → info_grid(대표 뉴스 상세, 사실 3~4개) "
             "→ info_grid(나머지 뉴스 2~3건 전부 브리핑) → target(라벨을 '왜 중요한가'로) "
             "→ ai_response(스펙로그 AI 추천 대응: 지금 뭘 해야 하는가) "
             "→ caution(해석 시 주의점) → outro  [8장 고정]",
        "C": "cover → hero_fact(마감일 + extra_items: 기관/회사명 + 지원 방법 + 전형 일정) "
             "→ target(지원 자격: 원문의 구체적 조건) → highlight(이 공고만의 특별한 점) "
             "→ caution(지원 시 맹점) → outro(source_text에 지원 링크)  [6장 고정]",
    }[template_type]

    parts = [
        f"카테고리: {CATEGORY_LABELS[category]} (template_type={template_type})",
        f"생성 시각: {slot}",
        f"발행일: {publish_date}",
        f"이 카테고리의 고정 슬라이드 시퀀스: {sequence_hint}",
        "",
        "아래는 자료조사 단계(Gemini)에서 수집한 원문 데이터:",
        json.dumps(research_raw, ensure_ascii=False, indent=2),
        "",
        "이 데이터를 바탕으로 아래와 동일한 키 구조를 가진 JSON을 완성해서 반환할 것",
        "(slides 배열의 타입 구성과 개수는 위 고정 시퀀스를 그대로 따를 것):",
        json.dumps(skeleton, ensure_ascii=False, indent=2),
    ]

    return "\n".join(parts)


IG_LINE_BREAK = "⠀"  # 점자 패턴 공백(Blank). 인스타그램은 단순 엔터로 만든 빈 줄을
# 줄바꿈으로 유지해주지 않으므로, 첫 줄과 문단 사이 빈 줄에 이 특수기호를 넣어야 캡션의
# 줄바꿈이 실제로 보존된다.


def _format_caption_linebreaks(caption: str) -> str:
    """캡션 첫 줄과 문단 사이 빈 줄을 전부 IG_LINE_BREAK로 채운다."""
    lines = [line if line.strip() else IG_LINE_BREAK for line in caption.strip("\n").splitlines()]
    return "\n".join([IG_LINE_BREAK, *lines])


def run(
    slot: SlotCode,
    category: CategoryCode,
    research_raw: dict,
    publish_date: str,
) -> dict:
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되지 않았습니다 (.env 확인).")

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    user_prompt = _build_user_prompt(slot, category, research_raw, publish_date)

    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=8000,
        # 시스템 프롬프트는 호출마다 그대로 반복되는 가장 큰 입력 토큰 블록이라 캐싱한다
        # (하루 3회 실행 + 같은 세션 내 여러 카테고리 연속 생성 시 입력 토큰 비용 절감).
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = "".join(
        block.text for block in message.content if block.type == "text"
    ).strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        card = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Claude 응답을 JSON으로 파싱하지 못했습니다: {e}\n원문:\n{raw_text[:2000]}"
        )

    errors = validate_card(card)
    if errors:
        raise RuntimeError(f"생성된 카드 JSON이 스키마를 만족하지 않습니다: {errors}")

    if card.get("caption"):
        card["caption"] = _format_caption_linebreaks(card["caption"])

    return card


if __name__ == "__main__":
    assert _format_caption_linebreaks("[핵심 요약]\n내용\n\n[해시태그]\n#태그") == (
        f"{IG_LINE_BREAK}\n[핵심 요약]\n내용\n{IG_LINE_BREAK}\n[해시태그]\n#태그"
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--research", required=True, help="research_gemini.py 출력 JSON 파일 경로")
    parser.add_argument("--publish-date", required=True, help='예: "2026.08.19(수)"')
    args = parser.parse_args()

    with open(args.research, encoding="utf-8") as f:
        research = json.load(f)

    card = run(
        slot=research["slot"],
        category=research["category_code"],
        research_raw=research["raw"],
        publish_date=args.publish_date,
    )
    print(json.dumps(card, ensure_ascii=False, indent=2))
