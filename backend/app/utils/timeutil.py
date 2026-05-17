"""Datetime 직렬화 헬퍼.

대부분의 DB DateTime 컬럼이 `datetime.utcnow` 로 저장되는 naive UTC 다.
이걸 그대로 `.isoformat()` 하면 timezone 정보 없는 문자열이 나가서, JS 측의
`new Date(s)` 가 로컬 timezone 으로 해석한다. KST 사용자 화면에 9시간
어긋남이 발생한다 (활동 로그에서 처음 발견 — 2026-05-17).

UTC 컬럼은 `iso_utc()` 로 직렬화해 'Z' 접미사를 붙인다. JS 가 명시적 UTC
로 인식하고 로컬 timezone 으로 변환해 표시한다.

주의 — visit_logs.visit_date / memos.visit_date 는 `fix_visit_tz.py` 마이그
이후 naive LOCAL (KST) 로 저장돼 있다. 여기엔 절대 `iso_utc()` 적용하면
안 된다 — 그냥 `.isoformat()` 으로 두면 JS 가 로컬로 해석해 맞게 표시된다.
"""
from datetime import datetime, timezone
from typing import Optional


def iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """naive UTC datetime 을 'Z' suffix ISO 문자열로 직렬화. None 은 None 반환."""
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
