"""Claude Haiku 기반 MR 메모 AI 정리 서비스.

원본 자유 텍스트 메모 + 템플릿(필드/프롬프트 애드온)을 받아
구조화된 JSON({ title, summary: { field: value, ... } })을 반환한다.
"""
import json
import logging
import os
from typing import Any, Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1500
DEFAULT_FIELDS = [
    "방문일시", "교수명", "병원명", "논의내용",
    "결과", "다음 액션", "논의 제품", "면담시간",
]


def _get_client():
    """anthropic 클라이언트를 런타임에 임포트 (미설치 환경에서 import 에러 방지)."""
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail="anthropic SDK 미설치. backend에서 `pip install anthropic` 후 재시작하세요.",
        ) from e

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY 환경변수 누락. backend/.env 에 설정 후 재시작하세요.",
        )
    return Anthropic(api_key=api_key)


def _build_user_prompt(raw_memo: str, fields: list[str], context: dict) -> str:
    field_list = "\n".join(f"- {f}" for f in fields)
    ctx_lines = []
    if context.get("doctor_name"):
        ctx_lines.append(f"교수명: {context['doctor_name']}")
    if context.get("hospital_name"):
        ctx_lines.append(f"병원명: {context['hospital_name']}")
    if context.get("department"):
        ctx_lines.append(f"진료과: {context['department']}")
    if context.get("visit_date"):
        ctx_lines.append(f"방문일시: {context['visit_date']}")
    ctx_block = "\n".join(ctx_lines) if ctx_lines else "(없음)"

    return f"""다음은 MR(영업사원)이 방문 직후 작성한 원본 메모입니다.
아래 메타정보와 원본 메모를 참고하여 요청된 필드를 JSON으로 정리해주세요.

[메타정보]
{ctx_block}

[원본 메모]
{raw_memo}

[요청 필드]
{field_list}

[응답 형식]
다음 구조의 JSON만 출력하세요 (코드블록/설명 금지):
{{
  "title": "간결한 한 줄 제목 (예: '김정형 교수 – 관절주사A 전환 논의')",
  "summary": {{
    "필드명1": "정리된 값",
    "필드명2": "정리된 값"
  }}
}}

원본에서 명확히 추출할 수 없는 필드는 빈 문자열 ""로 두세요. 없는 내용을 추측해서 채우지 마세요."""


def _build_system_prompt(prompt_addon: Optional[str]) -> str:
    base = (
        "당신은 제약회사 MR(영업사원)의 방문 메모를 구조화된 방문일지로 정리하는 전문 어시스턴트입니다. "
        "MR의 자유 서술 메모를 객관적 사실만 남겨 간결하게 정리하되, 원본에 없는 내용을 추측하거나 만들어내지 않습니다. "
        "응답은 오직 유효한 JSON 객체만 출력하며, 앞뒤 설명이나 코드블록을 절대 포함하지 않습니다."
    )
    if prompt_addon:
        base += f"\n\n추가 지시사항:\n{prompt_addon}"
    return base


async def organize_memo(
    raw_memo: str,
    fields: list[str],
    prompt_addon: Optional[str] = None,
    context: Optional[dict] = None,
) -> dict[str, Any]:
    """Claude Haiku를 호출해 원본 메모를 구조화된 JSON으로 정리.

    Returns: { "title": str, "summary": { field: value, ... } }
    Raises: HTTPException 502 on API/파싱 실패
    """
    if not raw_memo or not raw_memo.strip():
        raise HTTPException(status_code=400, detail="raw_memo가 비어 있습니다.")

    use_fields = fields or DEFAULT_FIELDS
    user_prompt = _build_user_prompt(raw_memo, use_fields, context or {})
    system_prompt = _build_system_prompt(prompt_addon)

    client = _get_client()
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:
        logger.exception("Claude API 호출 실패")
        raise HTTPException(status_code=502, detail=f"Claude API 호출 실패: {e}") from e

    text_parts = [
        block.text for block in msg.content if getattr(block, "type", None) == "text"
    ]
    raw_text = "".join(text_parts).strip()
    if not raw_text:
        raise HTTPException(status_code=502, detail="Claude 응답이 비어 있습니다.")

    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        raw_text = "\n".join(lines).strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error("Claude JSON 파싱 실패. 원문=%s", raw_text[:500])
        raise HTTPException(
            status_code=502, detail=f"Claude 응답 JSON 파싱 실패: {e}"
        ) from e

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Claude 응답이 객체가 아닙니다.")
    data.setdefault("title", "")
    data.setdefault("summary", {})
    return data


def _build_freeform_prompt(raw_memo: str, kind: str) -> str:
    """업무 일정 / 공지용 자유 문장 정리 프롬프트.

    방문 메모 템플릿을 끼워 맞추지 않고 원문을 자연스럽게 정돈한다.
    kind: 'announcement' | 'personal'
    """
    kind_label = "업무 공지" if kind == "announcement" else "업무 일정/메모"
    return f"""다음은 MR(영업사원)이 작성한 {kind_label} 원문입니다.
구조화된 방문일지 템플릿에 끼워 맞추지 말고, 원문의 요지를 유지한 채 **간결하게 정리**해 주세요.

[원문]
{raw_memo}

[응답 형식]
다음 구조의 JSON만 출력하세요 (코드블록/설명 금지):
{{
  "title": "한 줄 제목 (원문 주제 요약, 12자 내외 권장)",
  "summary": {{
    "핵심": "정리된 핵심 내용 (2~4문장 권장, 원문 근거)",
    "일시/장소": "원문에 있으면 채우고 없으면 빈 문자열",
    "준비/참고": "준비물·참고사항·담당자 등 있으면 정리, 없으면 빈 문자열"
  }}
}}

원문에 없는 내용을 추측하지 마세요. 필드가 해당 없으면 빈 문자열로 두세요."""


async def summarize_freeform(
    raw_memo: str,
    kind: str = "personal",
) -> dict[str, Any]:
    """업무 일정 / 공지처럼 구조 없는 자유 텍스트를 정리.

    방문 메모와 달리 템플릿 필드를 강제하지 않고, 원문을 자연스럽게 정돈한다.
    """
    if not raw_memo or not raw_memo.strip():
        raise HTTPException(status_code=400, detail="raw_memo가 비어 있습니다.")

    user_prompt = _build_freeform_prompt(raw_memo, kind)
    system_prompt = (
        "당신은 업무 메모/공지를 읽기 쉽게 정리하는 어시스턴트입니다. "
        "원문에 없는 내용을 추측하거나 만들지 않고, 핵심만 간결하게 정돈합니다. "
        "응답은 오직 유효한 JSON 객체만 출력하며, 앞뒤 설명이나 코드블록을 포함하지 않습니다."
    )

    client = _get_client()
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:
        logger.exception("Claude API 호출 실패")
        raise HTTPException(status_code=502, detail=f"Claude API 호출 실패: {e}") from e

    text_parts = [
        block.text for block in msg.content if getattr(block, "type", None) == "text"
    ]
    raw_text = "".join(text_parts).strip()
    if not raw_text:
        raise HTTPException(status_code=502, detail="Claude 응답이 비어 있습니다.")
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        raw_text = "\n".join(lines).strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error("Claude JSON 파싱 실패. 원문=%s", raw_text[:500])
        raise HTTPException(status_code=502, detail=f"Claude 응답 JSON 파싱 실패: {e}") from e

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Claude 응답이 객체가 아닙니다.")
    data.setdefault("title", "")
    data.setdefault("summary", {})
    return data
