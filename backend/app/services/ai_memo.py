"""MR 메모/보고서 AI 서비스 — Gemini Flash 단일 모델 (저비용).

- organize_memo: 단건 메모 → 구조화 JSON
- summarize_freeform: 자유 텍스트 (공지/개인일정) 정리
- summarize_report: 다건 메모 → 일일/주간 종합 보고서

추론형 고급 모델은 비용 대비 효용이 낮다고 판단. 부족한 부분은
사용자가 docx 다운로드 후 직접 편집하는 워크플로우로 보완.
"""
import json
import logging
import os
from typing import Any, Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_MAX_TOKENS = 1500

DEFAULT_FIELDS = [
    "방문일시", "교수명", "병원명", "논의내용",
    "결과", "다음 액션", "논의 제품", "면담시간",
]


def _get_gemini_client():
    """Gemini (google-genai) 클라이언트 — 단건 메모 정리용 저비용 모델."""
    try:
        from google import genai
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail="google-genai SDK 미설치. backend에서 `pip install google-genai` 후 재시작하세요.",
        ) from e

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY 환경변수 누락. backend/.env 에 GEMINI_API_KEY 추가 후 재시작하세요.",
        )
    return genai.Client(api_key=api_key)


def _gemini_json_call(system_prompt: str, user_prompt: str, *, max_tokens: int = 1500) -> dict[str, Any]:
    """Gemini 호출 + JSON 파싱 공용 헬퍼."""
    from google.genai import types as gemini_types
    client = _get_gemini_client()
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_prompt,
            config=gemini_types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                max_output_tokens=max_tokens,
            ),
        )
    except Exception as e:
        logger.exception("Gemini API 호출 실패")
        raise HTTPException(status_code=502, detail=f"Gemini API 호출 실패: {e}") from e

    raw_text = (response.text or "").strip()
    if not raw_text:
        raise HTTPException(status_code=502, detail="Gemini 응답이 비어 있습니다.")
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        raw_text = "\n".join(lines).strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error("Gemini JSON 파싱 실패. 원문=%s", raw_text[:500])
        raise HTTPException(status_code=502, detail=f"Gemini 응답 JSON 파싱 실패: {e}") from e

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Gemini 응답이 객체가 아닙니다.")
    data.setdefault("title", "")
    data.setdefault("summary", {})
    return data


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
    """Gemini Flash 로 원본 메모를 구조화된 JSON으로 정리 (저비용).

    Returns: { "title": str, "summary": { field: value, ... } }
    Raises: HTTPException 502 on API/파싱 실패
    """
    if not raw_memo or not raw_memo.strip():
        raise HTTPException(status_code=400, detail="raw_memo가 비어 있습니다.")

    use_fields = fields or DEFAULT_FIELDS
    user_prompt = _build_user_prompt(raw_memo, use_fields, context or {})
    system_prompt = _build_system_prompt(prompt_addon)
    return _gemini_json_call(system_prompt, user_prompt, max_tokens=GEMINI_MAX_TOKENS)


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
    """업무 일정 / 공지처럼 구조 없는 자유 텍스트를 Gemini Flash 로 정리 (저비용).

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
    return _gemini_json_call(system_prompt, user_prompt, max_tokens=GEMINI_MAX_TOKENS)


# ─────────── 보고서 (일일/주간) 종합 ───────────

REPORT_FIELDS_DAILY = ["핵심 활동", "병원별 활동", "주요 논의/이슈", "다음 액션"]
REPORT_FIELDS_WEEKLY = [
    "핵심 활동", "병원별 활동", "주요 논의/이슈",
    "이번 주 지표", "다음 주 계획",
]


def _build_report_prompt(
    items: list[dict],
    report_type: str,
    period_label: str,
    custom_fields: Optional[list[str]] = None,
) -> str:
    """여러 메모/일일 보고서 묶음을 종합 정리용 프롬프트로 변환.

    custom_fields 가 제공되면 일일/주간 기본 필드 대신 사용. 일일/주간 강조 노트
    (extra_note) 는 그대로 유지.
    """
    blocks = []
    for i, m in enumerate(items, 1):
        meta = []
        if m.get("visit_date"):
            meta.append(f"방문일: {m['visit_date']}")
        if m.get("doctor_name"):
            meta.append(f"교수: {m['doctor_name']}")
        if m.get("hospital_name"):
            meta.append(f"병원: {m['hospital_name']}")
        if m.get("department"):
            meta.append(f"진료과: {m['department']}")
        if m.get("title"):
            meta.append(f"제목: {m['title']}")
        meta_line = " · ".join(meta) if meta else "(메타 없음)"
        body = m.get("ai_summary_text") or m.get("raw_memo") or ""
        blocks.append(f"[{i}] {meta_line}\n{body}")

    if custom_fields:
        fields = custom_fields
    else:
        fields = REPORT_FIELDS_WEEKLY if report_type == "weekly" else REPORT_FIELDS_DAILY
    field_list = "\n".join(f"- {f}" for f in fields)
    type_label = "주간" if report_type == "weekly" else "일일"
    if report_type == "weekly":
        extra_note = (
            "\n주간 보고서이므로 추세, 누적 성과, 다음 주 계획을 강조해서 정리해주세요. "
            "병원별 활동은 방문 횟수와 핵심 결과 위주로 요약하세요."
        )
    else:
        extra_note = (
            "\n일일 보고서이므로 오늘 방문/면담의 핵심 인사이트를 추출하고, "
            "병원/교수별로 묶어서 정리하세요."
        )
    blocks_text = "\n".join(blocks)

    return f"""다음은 MR(영업사원)이 {period_label} 기간에 작성한 방문 메모/면담 기록 {len(items)}건입니다.
이를 종합하여 관리자에게 보고할 {type_label} 보고서를 JSON으로 작성해주세요.{extra_note}

[메모/기록 목록]
{blocks_text}

[요청 필드]
{field_list}

[응답 형식]
다음 구조의 JSON만 출력하세요 (코드블록/설명 금지):
{{
  "title": "{type_label} 보고서 제목 (예: '04/29 일일 보고 - 정형외과 3건 외')",
  "summary": {{
    "필드명1": "정리된 값 (여러 줄/항목이면 줄바꿈/하이픈 사용)",
    "필드명2": "정리된 값"
  }}
}}

원문에 없는 수치나 사실을 추측해서 만들지 마세요. 정보가 부족한 필드는 빈 문자열 ""로 두세요."""


async def summarize_report(
    items: list[dict],
    report_type: str,
    period_label: str,
    prompt_addon: Optional[str] = None,
    custom_fields: Optional[list[str]] = None,
) -> dict[str, Any]:
    """여러 메모(또는 일일 보고서)를 Gemini Flash 로 종합 (저비용).

    items 각 항목 키:
      visit_date, doctor_name, hospital_name, department, title,
      raw_memo, ai_summary_text (이미 정리된 메모일 경우 사용)

    custom_fields 로 보고서 템플릿의 필드 목록을 지정하면 기본
    REPORT_FIELDS_DAILY/WEEKLY 대신 그것을 사용한다.

    반환: { "title": str, "summary": { field: value, ... } }
    부족한 부분은 사용자가 docx 다운로드 후 직접 수정하는 워크플로우.
    """
    if not items:
        raise HTTPException(status_code=400, detail="종합할 메모/보고서가 없습니다.")

    user_prompt = _build_report_prompt(items, report_type, period_label, custom_fields)
    system_prompt = (
        "당신은 제약회사 MR 활동 보고서를 작성하는 전문 어시스턴트입니다. "
        "MR이 제공한 여러 방문/면담 기록을 종합하여 관리자가 한눈에 파악할 수 있게 정리합니다. "
        "원문에 없는 수치/사실은 추측하지 않으며, 객관적 사실 위주로 간결하게 작성합니다. "
        "응답은 오직 유효한 JSON 객체만 출력하며, 앞뒤 설명이나 코드블록을 포함하지 않습니다."
    )
    if prompt_addon:
        system_prompt += f"\n\n추가 지시사항:\n{prompt_addon}"

    return _gemini_json_call(system_prompt, user_prompt, max_tokens=GEMINI_MAX_TOKENS * 2)
