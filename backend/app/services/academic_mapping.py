"""학회명/행사명 → 진료과 키워드 매핑 엔진.

병원마다 진료과명을 조금씩 다르게 쓰지만(`비뇨의학과` / `비뇨기과`) 핵심 키워드는
대부분 공통. 이 키워드를 기준으로 학회명에서 진료과를 역추출한다.
"""
from __future__ import annotations

import json
from typing import Optional


# (keyword, [DB 진료과명들]) — 순서 중요: 구체적인 키워드를 먼저 (신경외 > 신경)
DEPT_KEYWORDS: list[tuple[str, list[str]]] = [
    # 외과 계열 (구체 먼저)
    ("정형외", ["정형외과"]),
    ("신경외", ["신경외과"]),
    ("성형외", ["성형외과"]),
    ("흉부외", ["흉부외과", "심장혈관흉부외과"]),
    ("심장혈관흉부", ["심장혈관흉부외과"]),
    ("간담췌", ["간담췌외과"]),
    ("대장항문", ["대장항문외과"]),
    ("소아외", ["소아외과"]),
    ("이식", ["이식혈관외과"]),

    # 소아 세부 (소아 앞에 붙는 복합 키워드를 먼저)
    ("소아심장", ["소아청소년과"]),
    ("소아신경", ["소아청소년과"]),
    ("소아혈액", ["소아청소년과"]),
    ("소아감염", ["소아청소년과"]),
    ("소아내분비", ["소아청소년과"]),
    ("소아알레르기", ["소아청소년과"]),
    ("소아청소년", ["소아청소년과"]),

    # 내과 세부
    ("소화기", ["소화기내과"]),
    ("간학회", ["소화기내과"]),
    ("순환기", ["순환기내과"]),
    ("심장", ["순환기내과"]),
    ("호흡기", ["호흡기내과"]),
    ("결핵", ["호흡기내과"]),
    ("내분비", ["내분비내과"]),
    ("당뇨", ["내분비내과"]),
    ("갑상선", ["내분비내과"]),
    ("신장", ["신장내과"]),
    ("투석", ["신장내과"]),
    ("감염", ["감염내과"]),
    ("방사선종양", ["방사선종양학과"]),
    ("혈액종양", ["혈액종양내과"]),
    ("혈액", ["혈액내과", "혈액종양내과"]),
    ("종양", ["종양내과", "혈액종양내과"]),
    ("암", ["종양내과", "혈액종양내과"]),
    ("류마티스", ["류마티스내과"]),
    ("알레르기", ["알레르기내과"]),

    # 독립 과
    ("비뇨", ["비뇨의학과"]),
    ("산부인", ["산부인과"]),
    ("산과", ["산부인과"]),
    ("부인", ["산부인과"]),
    ("모체태아", ["산부인과"]),
    ("폐경", ["산부인과"]),
    ("소아", ["소아청소년과"]),
    ("안과", ["안과"]),
    ("녹내장", ["안과"]),
    ("망막", ["안과"]),
    ("이비인후", ["이비인후과"]),
    ("두경부", ["이비인후과"]),
    ("피부", ["피부과"]),
    ("치과", ["치과"]),
    ("구강", ["치과"]),
    ("정신건강", ["정신건강의학과"]),
    ("신경정신", ["정신건강의학과"]),
    ("정신의학", ["정신건강의학과"]),
    ("마취통증", ["마취통증의학과"]),
    ("마취", ["마취통증의학과"]),
    ("통증", ["마취통증의학과"]),
    ("응급", ["응급의학과"]),
    ("외상", ["응급의학과"]),
    ("재활", ["재활의학과"]),
    ("가정의학", ["가정의학과"]),
    ("영상의학", ["영상의학과"]),
    ("초음파", ["영상의학과"]),
    ("방사선종양", ["방사선종양학과"]),
    ("방사선", ["영상의학과"]),
    ("핵의학", ["핵의학과"]),
    ("병리", ["병리과"]),
    ("진단검사", ["진단검사의학과"]),
    ("임상병리", ["진단검사의학과"]),
    # 신경 (신경외 매칭이 앞에서 소비한 뒤에 실행)
    ("신경", ["신경과"]),
    ("뇌졸중", ["신경과"]),
    ("간질", ["신경과"]),
    ("치매", ["신경과"]),
    ("수면", ["신경과"]),
    ("노인", ["가정의학과"]),
    ("직업환경", ["직업환경의학과"]),
    ("예방", ["예방의학과"]),
    ("결핵호흡기", ["호흡기내과"]),

    # 포괄 카테고리 (세부 매칭 전부 실패 시 fallback)
    ("내과", ["내과"]),
    ("외과", ["외과"]),
]

# 포괄 카테고리는 구체 매칭이 있으면 드롭
_UMBRELLA_KEYWORDS = {"내과", "외과"}


# KMA 임상의학 서브카테고리 (s_scode=1~25) → DB 진료과명
# 대부분 1:1, 몇 개만 alias/재해석
KMA_CATEGORY_MAP: dict[str, list[str]] = {
    "내과": ["내과"],
    "외과": ["외과"],
    "소아청소년과": ["소아청소년과"],
    "산부인과": ["산부인과"],
    "정신건강의학과": ["정신건강의학과"],
    "정형외과": ["정형외과"],
    "신경외과": ["신경외과"],
    "흉부외과": ["흉부외과", "심장혈관흉부외과"],
    "성형외과": ["성형외과"],
    "안과": ["안과"],
    "이비인후과": ["이비인후과"],
    "피부과": ["피부과"],
    "비뇨의학과": ["비뇨의학과"],
    "영상의학과": ["영상의학과"],
    "방사선종양학과": ["방사선종양학과"],
    "마취통증의학과": ["마취통증의학과"],
    "신경과": ["신경과"],
    "재활의학과": ["재활의학과"],
    "결핵과": ["호흡기내과"],  # 결핵 → 호흡기로 흡수
    "진단검사의학과": ["진단검사의학과"],
    "병리과": ["병리과"],
    "가정의학과": ["가정의학과"],
    "산업의학과": ["직업환경의학과"],  # 구 명칭
    "핵의학과": ["핵의학과"],
    "응급의학과": ["응급의학과"],
}


def extract_departments(text: str) -> tuple[list[str], str]:
    """학회명/행사명에서 진료과를 추출.

    반환: (department_list, status) — status = "keyword" | "unclassified"

    매칭된 키워드 span 은 텍스트에서 소비(consume)해서 하위 키워드의 중복
    매칭을 방지한다. 예: "소아심장학회" 는 "소아심장" 만 매칭, "심장" 따로 매칭 X.
    """
    if not text:
        return [], "unclassified"

    working = text
    matched: set[str] = set()
    matched_specific = False
    umbrella_matches: list[list[str]] = []

    for keyword, depts in DEPT_KEYWORDS:
        if keyword in working:
            if keyword in _UMBRELLA_KEYWORDS:
                umbrella_matches.append(depts)
            else:
                matched.update(depts)
                matched_specific = True
            working = working.replace(keyword, " " * len(keyword))

    if not matched_specific:
        for depts in umbrella_matches:
            matched.update(depts)

    if matched:
        return sorted(matched), "keyword"
    return [], "unclassified"


def resolve_kma_category(raw: str) -> list[str]:
    """KMA `교육종류(임상의학)` 원본 문자열을 DB 진료과명 리스트로 확장.

    예: "정형외과, 마취통증의학과" → ["정형외과", "마취통증의학과"]
        "내과, 외과" → ["내과", "외과"]
        "선택항목 없음" → []
    """
    if not raw or "선택항목" in raw:
        return []
    result: set[str] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        depts = KMA_CATEGORY_MAP.get(token)
        if depts:
            result.update(depts)
    return sorted(result)


def resolve_event(
    organizer_name: Optional[str],
    event_name: Optional[str],
    organizers_lookup: dict[str, list[str]],
    kma_category: Optional[str] = None,
) -> tuple[list[str], str]:
    """이벤트 진료과 해석 3단계.

    1) kma_category 가 있고 KMA_CATEGORY_MAP 에서 뭐라도 뽑히면 → status="kma"
    2) organizer_name 이 seed 테이블에 있으면 → status="mapped"
    3) organizer_name + event_name 키워드 추출 → status="keyword" | "unclassified"
    """
    if kma_category:
        kma_depts = resolve_kma_category(kma_category)
        if kma_depts:
            return kma_depts, "kma"

    if organizer_name and organizer_name in organizers_lookup:
        depts = organizers_lookup[organizer_name]
        if depts:
            return depts, "mapped"

    text = f"{organizer_name or ''} {event_name or ''}".strip()
    return extract_departments(text)


def departments_to_json(departments: list[str]) -> str:
    return json.dumps(departments, ensure_ascii=False)


def departments_from_json(payload: Optional[str]) -> list[str]:
    if not payload:
        return []
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        return []
    if isinstance(data, list):
        return [str(d) for d in data]
    return []
