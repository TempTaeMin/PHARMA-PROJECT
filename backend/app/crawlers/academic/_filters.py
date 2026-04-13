"""학회 이벤트 수집 단계 필터.

MR 의 현장 방문 일정과 무관한 완전 온라인(웨비나/줌) 이벤트는 저장하지 않는다.
하이브리드(현장+온라인 동시 개최)는 현장 방문 가치가 있으므로 유지.
"""
from __future__ import annotations

import re

_ONLINE_NAME_RE = re.compile(
    r"(\(|\[)\s*(온라인|online|웨비나|webinar)\s*(\)|\])",
    re.IGNORECASE,
)
_ONLINE_LOC_RE = re.compile(
    r"(온라인|online|zoom|webinar|웨비나|웹세미나|가상|virtual|e-learning|원격)",
    re.IGNORECASE,
)
_PHYSICAL_RE = re.compile(
    r"(시\s|구\s|동\s|로\s|병원|센터|호텔|빌딩|컨벤션|타워|대학교|회관|강당|아트홀)"
)


def is_online_only(name: str | None, location: str | None) -> bool:
    name = name or ""
    location = location or ""
    if _ONLINE_NAME_RE.search(name):
        return True
    if _ONLINE_LOC_RE.search(location):
        if _PHYSICAL_RE.search(location):
            return False  # 하이브리드 — 유지
        return True
    return False
