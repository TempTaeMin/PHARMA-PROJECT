"""스케줄 셀 판정 공용 유틸.

판정 순서 (중요):
  INACTIVE  → EXCLUDE  → CLINIC(키워드) → MARK → (시간 패턴) → False
순서를 지키지 않으면 "수술 진료" 같은 셀이 CLINIC 에 먼저 걸려 오분류됨.
"""
import re

CLINIC_MARKS = {"●", "○", "◎", "◯", "★", "ㅇ", "O", "V", "v", "◆", "■", "✓"}

CLINIC_KEYWORDS = (
    "진료", "외래", "예약", "격주", "순환",
    "클리닉", "상담", "투석", "검진",
)

EXCLUDE_KEYWORDS = (
    "수술", "내시경", "시술", "초음파", "조영",
    "CT", "MRI", "PET", "회진", "실험", "연구", "검사",
    "왕진",
)

INACTIVE_KEYWORDS = (
    "휴진", "휴무", "공휴일", "부재", "출장", "학회",
)

BIWEEKLY_MARKERS = (
    "격주", "1·3주", "2·4주", "홀수주", "짝수주",
    "1,3주", "2,4주", "1/3주", "2/4주",
)


def is_clinic_cell(text: str) -> bool:
    """셀 텍스트가 외래 진료인지 판정."""
    if not text:
        return False
    t = text.strip()
    if not t:
        return False

    for kw in INACTIVE_KEYWORDS:
        if kw in t:
            return False
    for kw in EXCLUDE_KEYWORDS:
        if kw in t:
            return False
    for kw in CLINIC_KEYWORDS:
        if kw in t:
            return True
    for mark in CLINIC_MARKS:
        if mark in t:
            return True
    if re.search(r"\d{1,2}[:시]\d{0,2}", t):
        return True
    return False


def has_biweekly_mark(text: str) -> bool:
    """텍스트에 격주 근무 표시가 포함돼 있는지."""
    if not text:
        return False
    for m in BIWEEKLY_MARKERS:
        if m in text:
            return True
    return False


def find_exclude_keyword(text: str) -> str | None:
    """텍스트에 들어있는 EXCLUDE 키워드를 반환 (없으면 None). 검증용."""
    if not text:
        return None
    for kw in EXCLUDE_KEYWORDS:
        if kw in text:
            return kw
    return None
