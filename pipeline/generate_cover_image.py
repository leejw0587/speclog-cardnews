"""
generate_cover_image.py
표지(cover) 슬라이드의 배경 사진을 Gemini 이미지 생성 모델로 만든다. (사용자 피드백 #2)

모델: gemini-2.5-flash-image ("Nano Banana" 계열). Google이 새 버전을 낼 때마다
모델 ID가 바뀌므로 .env의 GEMINI_IMAGE_MODEL로 오버라이드 가능하게 했다.
(참고: Imagen 3/4 계열은 2026-08-17부로 단계적 종료되어 이 프로젝트에서는 사용하지 않는다.)

실패하거나 키가 없으면 None을 반환하고, 렌더러/템플릿(cover.html)이 자체적으로
accent 컬러 그라디언트 배경으로 폴백한다 (design.md 6장) — 이미지 생성이 안 되더라도
파이프라인 전체가 멈추지 않는다.
"""

from __future__ import annotations
import base64

from pipeline.config import config

NEGATIVE_STYLE_HINT = (
    "no text, no logos, no watermark, no illustration, no 3d render, no cartoon, "
    "no AI-art / synthetic look, no visible human faces close-up"
)

CATEGORY_MOOD = {
    "news": "modern city skyline at dusk, office district, wide shot",
    "activity": "university campus, students walking, silhouettes, candid, wide shot",
    "license": "clean desk with notebook and laptop, soft window light, close-up",
    "job": "city night view from office window, desk with laptop, editorial mood",
}


def build_prompt(category_code: str, topic_hint: str = "") -> str:
    """topic_hint는 generate_content_claude.py가 cover 슬라이드의 bg_prompt로 직접 작성한,
    그날 소재에 특화된 한국어 장면 묘사다 (design.md 6장 v2.4: "아무 사진"이 아니라 "이 얘기구나"
    싶은 사진). CATEGORY_MOOD는 topic_hint가 없을 때만 쓰는 카테고리 단위 폴백이다."""
    mood = CATEGORY_MOOD.get(category_code, "modern minimal office desk")
    scene = f"Specific scene: {topic_hint}." if topic_hint else f"Generic scene: {mood}."
    return (
        f"Photo-realistic editorial photography that visually reflects the specific topic below "
        f"— not a generic stock photo. {scene} "
        f"Subtle, muted color grading suitable as a lightly blurred background behind bold white text. "
        f"{NEGATIVE_STYLE_HINT}."
    ).strip()


def generate_cover_background(category_code: str, topic_hint: str = "") -> tuple[str | None, str | None]:
    """성공하면 (data URI, None)을 반환. 실패하면 (None, 실패 사유)를 반환한다.
    실패 사유는 호출부(generate_only.py)가 log.txt에 남겨서, 나중에 원인을 확인할 수 있게 한다."""
    if not config.GEMINI_API_KEY:
        return None, "GEMINI_API_KEY가 설정되지 않음"

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=config.GEMINI_API_KEY)
        prompt = build_prompt(category_code, topic_hint)

        response = client.models.generate_content(
            model=config.GEMINI_IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio="4:5"),
            ),
        )

        for part in (response.parts or []):  # 세이프티 필터 등으로 candidates가 비면 parts가 None일 수 있음
            if getattr(part, "inline_data", None):
                img_bytes = part.inline_data.data
                # SDK 버전에 따라 bytes 또는 base64 str로 올 수 있어 방어적으로 처리
                if isinstance(img_bytes, str):
                    b64 = img_bytes
                else:
                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                mime = getattr(part.inline_data, "mime_type", "image/png") or "image/png"
                return f"data:{mime};base64,{b64}", None

        return None, f"응답에 이미지 파트 없음 (세이프티 필터 등) - finish_reason: {getattr(response, 'candidates', None) and response.candidates[0].finish_reason}"

    except Exception as e:  # noqa: BLE001
        # 표지 배경 생성 실패는 치명적 오류가 아니다 - CSS 그라디언트로 폴백한다.
        return None, str(e)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--category", required=True, choices=["news", "activity", "license", "job"])
    parser.add_argument("--topic", default="")
    parser.add_argument("--out", default="cover_bg_test.png")
    args = parser.parse_args()

    uri, error = generate_cover_background(args.category, args.topic)
    if uri is None:
        print(f"생성 실패 - 폴백 그라디언트가 사용됩니다. 사유: {error}")
    else:
        header, b64data = uri.split(",", 1)
        with open(args.out, "wb") as f:
            f.write(base64.b64decode(b64data))
        print(f"저장됨: {args.out}")
