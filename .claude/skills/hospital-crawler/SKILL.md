---
name: hospital-crawler
description: |
  MR 스케줄러 프로젝트에서 병원 크롤러를 작성하거나 수정할 때 반드시 사용하는 스킬.
  새로운 병원 크롤러 추가, 기존 크롤러 디버깅, 크롤러 구조 리팩토링, 스케줄 파싱 로직 작성 등
  모든 병원 데이터 수집 관련 작업에 이 스킬을 먼저 읽고 시작할 것.
  "병원 추가", "크롤러 만들어줘", "스케줄 파싱", "진료과 데이터 수집" 등의 표현이 나오면 즉시 이 스킬을 참조할 것.
---

# Hospital Crawler Skill

MR 스케줄러의 병원 크롤러를 일관성 있게 작성하기 위한 표준 가이드.

---

## 핵심 원칙

1. **기술 스택은 병원 유형에 따라 선택** — 아래 판단 기준 참고, 무조건 한 가지만 쓰지 않는다
2. **고유 키 통일** — 의사 식별은 `external_id` (포맷: `{HOSPITAL_CODE}-{원내코드}`). **단독 조회에 필요한 파라미터(진료과 코드·mediof 코드 등)가 원내코드 외에 더 있으면 모두 포함할 것** — 예: `HYUMC-{doct_cd}-{mediof_cd}`
3. **구조 통일** — 모든 크롤러는 아래 표준 클래스 구조를 따른다
4. **비동기 기반** — 모든 크롤러는 `httpx.AsyncClient` + `async def` 사용
5. **에러 무시 금지** — 모든 예외는 로깅 후 빈 리스트 반환, 절대 앱을 죽이지 않는다
6. **병원별 파일 분리** — 크롤러 1개 = 파일 1개 (`crawlers/{hospital_code}_crawler.py`)
7. **`crawl_doctor_schedule()`은 절대로 `_fetch_all()`을 호출하지 않는다** — 개별 교수 조회는 반드시 해당 교수 1명만 네트워크 요청한다. 자세한 내용은 아래 "개별 교수 조회 규칙" 참조
8. **스케줄 판정 규칙 준수** — MR 방문 가능한 "외래 진료" 만 `schedules` / `date_schedules` 에 포함. 수술/내시경/검사 등은 제외하고, `○` 같은 대체 마크도 빠뜨리지 않는다. 자세한 내용은 아래 "스케줄 셀 판정 규칙" 참조
9. **`external_id` 에 `/` 금지** — FastAPI path param(`{staff_id}`) 이 슬래시를 기본적으로 허용하지 않아 404 가 발생한다. 슬래시가 필요하면 `_` 등으로 치환하거나 다른 구분자 사용

---

## 크롤링 기술 선택 기준

병원 사이트에 접근하기 전에 반드시 유형을 판단한다.

| 유형 | 비율 | 판단 방법 | 사용 기술 |
|------|------|-----------|-----------|
| 정적 HTML | ~40% | Network 탭에 XHR/Fetch 요청 없음 | `httpx + BeautifulSoup` |
| XHR API 방식 | ~10% | Network 탭에 JSON API 호출 보임 | `httpx` (API 직접 호출) |
| JS 동적 렌더링 | ~50% | Network 탭에 XHR 있거나 빈 HTML | `Playwright` |

**판단 방법 (브라우저 개발자도구 F12)**
1. Network 탭 → XHR/Fetch 필터 → 페이지 새로고침
2. 요청이 없으면 → 정적 HTML → `httpx`
3. JSON 응답 요청이 보이면 → 그 URL 직접 호출 → `httpx`
4. 요청은 있는데 HTML/JS 파일들만 있거나, `httpx`로 가져온 HTML이 데이터 없이 비어있으면 → `Playwright`

**`httpx`를 먼저 시도하고, 실패하면 `Playwright`로 전환한다.**

---

## 표준 크롤러 클래스 구조

```python
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "{병원 기본 URL}"
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}


class {HospitalCode}Crawler:
    """
    {병원 전체명} 크롤러
    출처: {크롤링 대상 URL}
    """

    def __init__(self):
        self.hospital_code = "{HOSPITAL_CODE}"
        self.hospital_name = "{병원 전체명}"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self._cached_data = None  # 전체 크롤링 결과 캐시

    async def get_departments(self) -> list[dict]:
        """진료과 목록 반환. 반드시 code, name 포함."""
        raise NotImplementedError

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        """교수 목록 반환 (스케줄 미포함 경량 버전)."""
        raise NotImplementedError

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수의 상세 정보 + 진료시간표 반환."""
        raise NotImplementedError

    async def crawl_doctors(self, department: str = None):
        """전체 크롤링 실행. CrawlResult 스키마로 반환."""
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]

        doctors = [
            CrawledDoctor(
                name=d["name"],
                department=d["department"],
                position=d.get("position", ""),
                specialty=d.get("specialty", ""),
                profile_url=d.get("profile_url", ""),
                external_id=d["external_id"],
                notes=d.get("notes", ""),
                schedules=d["schedules"],
                date_schedules=d.get("date_schedules", []),
            )
            for d in data
        ]

        return CrawlResult(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            status="success" if doctors else "partial",
            doctors=doctors,
            crawled_at=datetime.utcnow(),
        )
```

---

## 표준 반환 포맷

### 진료과 (get_departments)
```python
[
    {"code": "D001", "name": "내과"},
    {"code": "D002", "name": "외과"},
]
```

### 교수 목록 (crawl_doctor_list)
```python
[
    {
        "staff_id": "AMC-abc123",      # external_id와 동일
        "external_id": "AMC-abc123",   # {HOSPITAL_CODE}-{원내코드}
        "name": "홍길동",
        "department": "내과",
        "position": "교수",
        "specialty": "소화기질환",
        "profile_url": "https://...",
        "notes": "",
    },
]
```

### 개별 교수 스케줄 (crawl_doctor_schedule)
```python
{
    "staff_id": "AMC-abc123",
    "name": "홍길동",
    "department": "내과",
    "position": "교수",
    "specialty": "소화기질환",
    "profile_url": "https://...",
    "notes": "",
    "schedules": [
        {
            "day_of_week": 0,          # 0=월 ~ 5=토, 6=일 (int)
            "time_slot": "morning",     # "morning" | "afternoon"
            "start_time": "09:00",
            "end_time": "12:00",
            "location": "",            # 진료 장소 (선택)
        },
    ],
    "date_schedules": [                # 날짜별 스케줄 (지원하는 병원만)
        {
            "schedule_date": "2026-04-10",
            "time_slot": "morning",
            "start_time": "09:00",
            "end_time": "12:00",
            "location": "외래",
            "status": "진료",          # "진료" | "마감"
        },
    ],
}
```

### 전체 크롤링 (crawl_doctors) — Pydantic 스키마 사용
```python
# app/schemas/schemas.py 에 정의됨
CrawlResult(
    hospital_code="AMC",
    hospital_name="서울아산병원",
    status="success",              # "success" | "partial" | "failed"
    doctors=[CrawledDoctor(...)],
    crawled_at=datetime.utcnow(),
)
```

---

## 진료시간표 형식 선택 가이드

크롤러가 반환하는 스케줄 형식은 병원이 제공하는 데이터 유형에 따라 결정한다.

| 병원 제공 데이터 | 사용 필드 | 예시 병원 |
|------------------|-----------|-----------|
| 월별 달력 (날짜별 진료 여부) | `schedules` + `date_schedules` 모두 | HYUMC, KUH, KCCH, KBSMC |
| 주간 패턴만 (요일별 오전/오후) | `schedules`만 | AMC, SNUH, SEVERANCE |

**원칙:**
- `date_schedules`를 지원하는 병원은 반드시 `schedules`(요일 요약)도 함께 반환한다
- `date_schedules`는 현재 월부터 3개월치를 수집한다 (`months=3` 파라미터)
- `schedules`만 있는 크롤러에 `date_schedules`를 추가할 수 없다면 빈 리스트 `[]`를 반환한다 (Pydantic 기본값)

**구현 패턴 (달력형 병원):**
```python
# 주간 패턴: _fetch_schedule() 또는 _fetch_doctor_schedule()
schedules = await self._fetch_schedule(client, doctor_id)

# 날짜별 3개월: _fetch_monthly_schedule()
date_schedules = await self._fetch_monthly_schedule(client, doctor_id)

# _fetch_all()에서 둘 다 dict에 저장
doc["schedules"] = schedules
doc["date_schedules"] = date_schedules
```

---

## 진료장소(location) 표기 가이드

`schedules`와 `date_schedules`의 `location` 필드 사용 기준:

| 상황 | location 처리 | notes 처리 |
|------|---------------|------------|
| 단일 캠퍼스, 장소 구분 없음 | `""` (빈 문자열) | 불필요 |
| 단일 캠퍼스, 외래/클리닉 구분 | `"외래"` / `"클리닉"` | 불필요 |
| 여러 캠퍼스/분원 | 각 스케줄에 장소명 기록 | 여러 장소 진료 시 notes에 요약 |

**여러 장소에서 진료하는 의사 — SNUH 패턴** (`crawlers/snuh_crawler.py`):

의사가 2개 이상의 장소에서 진료하면, `notes` 필드에 장소별 일정을 요약 기록한다:
```python
if len(doc["locations"]) > 1:
    lines = []
    for loc in doc["locations"]:
        loc_schedules = [s for s in doc["schedules"] if s["location"] == loc]
        if loc_schedules:
            day_slots = []
            for s in loc_schedules:
                day = ["월","화","수","목","금","토"][s["day_of_week"]]
                slot = "오전" if s["time_slot"] == "morning" else "오후"
                day_slots.append(f"{day} {slot}")
            lines.append(f"{loc}: {', '.join(day_slots)}")
    notes = "\n".join(lines)
# 결과 예시: "본원: 월 오전, 화 오후\n어린이병원: 수 오전, 목 오전"
```

**주의:** KBSMC처럼 단일 캠퍼스이고 API 응답에 장소 정보가 없는 경우, `location`은 빈 문자열로 두며 강제로 채우지 않는다.

---

## 스케줄 셀 판정 규칙

MR 방문 스케줄 수집이 목적이므로 **환자를 직접 만나는 외래/진료 활동만** `schedules` / `date_schedules` 에 포함한다. 병원 시간표는 같은 셀(`td`)에 여러 표기 방식을 섞어 쓰므로, 아래 3가지 차원을 각각 점검한다.

### 1) 셀 마크 인식 — 진료 있음으로 판정

병원별로 쓰는 "진료 있음" 마크가 제각각이라 한 가지만 잡으면 누락된다. 아래 마크를 모두 활성 셀로 인정한다:

```python
CLINIC_MARKS = {"●", "○", "◎", "◯", "★", "ㅇ", "O", "V", "v", "◆", "■", "✓"}
```

- `●` : 가장 일반적. 모든 크롤러가 이것은 잡음
- `○` : 격주/월별 교차 진료에서 쓰는 병원이 많음 (DUIH, PARK, WOORIDUL 등) — **누락하기 쉬움**
- `◎` : 특진/프리미엄 진료 표시로 쓰는 병원 있음
- `ㅇ` / `O` : 한글/영문 O 로 대체하는 저수준 HTML 병원 (NCC 등)
- 텍스트로 시간(`09:00~12:00`, `오전/오후`) 이 직접 적혀 있으면 마크 없이도 활성

### 2) 셀 텍스트 키워드 판정 — 포함할 것 vs 제외할 것

셀이 비어 있지 않더라도 다음 키워드 중 하나라도 있으면 **외래 진료가 아니므로 제외**한다. 반대로 "진료로 간주할 키워드" 에 해당하면 마크가 없어도 포함한다.

```python
# 외래/진료로 포함 (MR 방문 대상)
CLINIC_KEYWORDS = (
    "진료", "외래", "예약", "격주", "순환", "왕진",
    "클리닉", "상담", "투석", "검진",
)

# 외래 아님 — 제외
EXCLUDE_KEYWORDS = (
    "수술", "내시경", "시술", "초음파", "조영",
    "CT", "MRI", "PET", "회진", "실험", "연구",
)

# 비활성 — 아예 셀이 없는 것과 동일 처리
INACTIVE_KEYWORDS = (
    "휴진", "휴무", "공휴일", "부재", "출장", "학회",
)
```

**주의 — `검진` 은 포함, `검사` 는 제외**
- `검진` (건강검진·종합검진·건진): 교수가 외래처럼 환자를 만나는 활동 → 포함
- `검사` (내시경검사·영상검사 등): 검사실에서 이뤄져 MR 방문 대상 아님 → 제외

**판정 순서 (매우 중요):**
1. `INACTIVE_KEYWORDS` 매칭 → 비활성 처리 후 즉시 종료
2. `EXCLUDE_KEYWORDS` 매칭 → 제외 처리 후 즉시 종료 (EXCLUDE 가 CLINIC 보다 먼저!)
3. `CLINIC_KEYWORDS` 또는 `CLINIC_MARKS` 매칭 → 진료로 포함
4. 그 외 → 비활성 (의심될 땐 제외하는 쪽으로)

순서를 지키지 않으면 `"수술 진료"` 같은 셀이 CLINIC 매칭에 걸려 잘못 포함된다.

### 3) 공통 유틸 사용 권장

위 판정을 각 크롤러에 중복 구현하지 말고, 공통 유틸로 뽑아서 import 해서 쓴다:

```python
# backend/app/crawlers/_schedule_rules.py
CLINIC_MARKS = {"●", "○", "◎", "◯", "★", "ㅇ", "O", "V", "v", "◆", "■", "✓"}
CLINIC_KEYWORDS = ("진료", "외래", "예약", "격주", "순환", "왕진", "클리닉", "상담", "투석", "검진")
EXCLUDE_KEYWORDS = ("수술", "내시경", "시술", "초음파", "조영", "CT", "MRI", "PET", "회진", "실험", "연구")
INACTIVE_KEYWORDS = ("휴진", "휴무", "공휴일", "부재", "출장", "학회")


def is_clinic_cell(text: str) -> bool:
    """
    셀 텍스트를 보고 외래 진료인지 판정.
    True → schedules/date_schedules 에 추가해야 함
    False → 건너뛸 것 (수술/내시경/휴진/빈칸)
    """
    if not text:
        return False
    t = text.strip()
    if not t:
        return False

    # 1) 비활성 우선
    for kw in INACTIVE_KEYWORDS:
        if kw in t:
            return False

    # 2) 제외 (진료 키워드보다 먼저!)
    for kw in EXCLUDE_KEYWORDS:
        if kw in t:
            return False

    # 3) 진료 키워드 또는 마크
    for kw in CLINIC_KEYWORDS:
        if kw in t:
            return True
    for mark in CLINIC_MARKS:
        if mark in t:
            return True

    # 4) 시간 패턴 (09:00~12:00 등)
    import re
    if re.search(r"\d{1,2}[:시]\d{0,2}", t):
        return True

    return False
```

크롤러에서는 이렇게만 쓰면 된다:
```python
from app.crawlers._schedule_rules import is_clinic_cell

for cell in row_cells:
    if not is_clinic_cell(cell.get_text(" ", strip=True)):
        continue
    # ... schedule dict 생성 ...
```

### 레퍼런스 크롤러

**올바르게 제외하는 크롤러 (수술/내시경 미포함):**
- `crawlers/shh_crawler.py` — 텍스트에 "수술" 포함 시 건너뜀
- `crawlers/dbje_crawler.py` — 셀 텍스트 필터링 후 포함 여부 결정
- `crawlers/hanil_crawler.py` — 검사 셀 제외

**`○` 마크를 정상 인식하는 크롤러:**
- `crawlers/duih_crawler.py` — `● ○ ◎` 셋 다 매칭
- `crawlers/park_crawler.py` — 상단 `CLINIC_MARKS` 상수 정의
- `crawlers/wooridul_crawler.py` — 마크 리스트에 `○` 포함

---

## 캐싱 패턴

`_cached_data`는 **동일 크롤러 인스턴스 내에서 `_fetch_all()` 중복 호출을 막기 위한 것**이다. `crawl_doctors` → 내부적으로 `_fetch_all()`을 여러 번 호출하는 구조일 때만 의미가 있다.

**중요 — 인스턴스 수명 이해:**
- `factory.py:get_crawler()`는 **매 HTTP 요청마다 새 인스턴스를 생성한다** (`entry[0]()`)
- 따라서 `self._cached_data`는 **HTTP 요청 간에 공유되지 않는다**
- 즉, 한 요청에서 다른 요청으로 캐시를 넘길 수 없음 → **요청 간 캐시는 DB가 담당**

```python
async def _fetch_all(self) -> list[dict]:
    """전체 데이터 크롤링 + 인스턴스 로컬 캐싱"""
    if self._cached_data is not None:
        return self._cached_data

    all_doctors = {}  # external_id → doctor dict (중복 방지)

    async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
        # ... 크롤링 로직 ...
        pass

    result = list(all_doctors.values())
    self._cached_data = result
    return result
```

---

## 개별 교수 조회 규칙 (crawl_doctor_schedule)

사용자가 "교수 탐색"에서 교수 1명을 클릭할 때의 호출 경로:
```
BrowseDoctors.jsx → GET /api/crawl/doctor/{code}/{staff_id}
  → crawl.py:crawl_single_doctor()
    → [1단계] DB 조회 (DoctorSchedule / DoctorDateSchedule) — 있으면 즉시 반환
    → [2단계] DB 미존재 또는 refresh=true → crawler.crawl_doctor_schedule(staff_id)
```

2단계에 진입했다는 것은 **DB에 해당 교수 데이터가 없다는 뜻**이므로, 크롤러는 "그 한 명"만 개별 조회해야 한다. 여기서 `_fetch_all()`을 호출하면 1명을 위해 수십~수백 페이지를 재크롤링하는 심각한 성능/부하 문제가 발생한다.

### ❌ 금지 패턴 (절대 하지 말 것)

```python
async def crawl_doctor_schedule(self, staff_id: str) -> dict:
    if self._cached_data is not None:
        for d in self._cached_data:
            if d["external_id"] == staff_id:
                return d

    # 🚫 금지: 1명 조회를 위해 전체 크롤링 실행
    await self._fetch_all()
    for d in self._cached_data:
        if d["external_id"] == staff_id:
            return d
    return empty
```

이유:
- `get_crawler()`가 새 인스턴스를 만들기 때문에 `_cached_data`는 항상 `None` → 매 요청마다 전체 크롤링 실행
- 1명 스케줄에 응답 시간 수 초~수십 초, 대상 병원 서버에 불필요한 부하
- 프로젝트 전역 규칙 위반 (`핵심 원칙 #7`)

### ✅ 올바른 패턴 — 개별 URL 조회

`external_id`에서 교수 고유 ID를 파싱해 **해당 교수의 상세/스케줄 엔드포인트만 직접 호출**한다. KBSMC 크롤러(`kbsmc_crawler.py:560-625`)가 레퍼런스.

```python
async def crawl_doctor_schedule(self, staff_id: str) -> dict:
    """개별 교수 진료시간표 조회 — 해당 교수 1명만 네트워크 요청"""
    empty = {
        "staff_id": staff_id, "name": "", "department": "", "position": "",
        "specialty": "", "profile_url": "", "notes": "",
        "schedules": [], "date_schedules": [],
    }

    # 동일 인스턴스 내 캐시가 있으면 사용 (crawl_doctors 흐름에서 의미)
    if self._cached_data is not None:
        for d in self._cached_data:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                return self._to_schedule_dict(d)
        return empty

    # external_id 에서 병원 원내코드 파싱 (포맷: {HOSPITAL_CODE}-{원내코드})
    prefix = f"{self.hospital_code}-"
    raw_id = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

    # 해당 교수 1명의 상세/스케줄 페이지만 직접 호출
    async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
        try:
            schedules = await self._fetch_doctor_schedule(client, raw_id)
            date_schedules = await self._fetch_monthly_schedule(client, raw_id)  # 지원 시
            info = await self._fetch_doctor_info(client, raw_id)  # 이름/진료과 등
        except Exception as e:
            logger.error(f"[{self.hospital_code}] 개별 조회 실패 {staff_id}: {e}")
            return empty

    return {
        "staff_id": staff_id,
        "name": info.get("name", ""),
        "department": info.get("department", ""),
        "position": info.get("position", ""),
        "specialty": info.get("specialty", ""),
        "profile_url": info.get("profile_url", ""),
        "notes": info.get("notes", ""),
        "schedules": schedules,
        "date_schedules": date_schedules,
    }
```

### 개별 URL을 못 찾는 예외 상황

병원에 따라 "특정 교수 상세" 전용 URL이 없고 목록 페이지 파싱을 통해야만 스케줄을 얻을 수 있는 경우도 있다. 이때는:
- 원내코드에 포함된 진료과 정보(예: `mp_idx`)를 이용해 **해당 진료과만** 크롤링 후 필터 (전체가 아니라 1개 진료과)
- 그래도 불가능하면 **반드시 구현 시 TODO 주석**을 남기고, `_fetch_all()` 대신 `logger.warning`으로 제한된 fallback임을 기록
- 전체 크롤링 fallback을 넣어야만 한다면 PR/커밋에 이유를 명시

### 테스트 방법

```bash
# DB 미존재 상태를 재현하려면 refresh=true
curl "http://localhost:8000/api/crawl/doctor/{HOSPITAL_CODE}/{HOSPITAL_CODE}-{원내코드}?refresh=true"
```
- 응답이 1초 이내에 오는지 (전체 크롤링이면 수 초~수십 초)
- 백엔드 로그에 다른 교수 페이지 호출이 없는지

---

## 병원 사이트 구조 유형

대부분의 병원은 아래 **3단계 구조**를 따른다. 이것이 표준 패턴이다.

```
1단계: 진료과 목록 페이지
   └── 2단계: 진료과별 의사 목록 페이지  (진료과 코드로 필터)
           └── 3단계: 의사 개인 스케줄 페이지  (의사 코드로 조회)
```

**AMC(서울아산병원) — 표준 다단계 구조의 참조 기준** (`crawlers/asan_crawler.py`)
- 진료과 목록: `deptListTypeA.do` → 진료과 코드 동적 추출 (실패 시 하드코딩 폴백)
- 의사 목록: `staffBaseInfoList.do?searchHpCd={코드}` → HTML 파싱
- 의사 식별자: `drEmpId` 파라미터 (Base64 암호화 문자열)
- 스케줄: 상세 페이지에서 테이블 파싱 + 텍스트 패턴 폴백

**SNUH(서울대학교병원) — 특수 케이스 (참조 기준 아님)** (`crawlers/snuh_crawler.py`)
- 전체 스케줄이 URL 한 번으로 한 HTML에 다 담기는 예외적으로 쉬운 구조
- 새 병원 작성 시 이 패턴으로 접근하면 안 됨

---

## 병원 그룹 베이스 클래스

동일 재단/네트워크 병원은 베이스 클래스를 공유한다. 새 크롤러 작성 전 해당 계열인지 확인할 것.

| 베이스 클래스 | 파일 | 해당 병원 |
|---------------|------|-----------|
| `CmcBaseCrawler` | `crawlers/cmc_base.py` | 서울성모, 은평성모, 여의도성모, 성빈센트, 인천성모 |
| `KumcBaseCrawler` | `crawlers/kumc_base.py` | 고대안암, 고대구로, 고대안산 |
| `EumcCrawler` | `crawlers/eumc_crawler.py` | 이대목동, 이대서울 |

**사용 예시 (CMC 계열):**
```python
from app.crawlers.cmc_base import CmcBaseCrawler

class CmcseoulCrawler(CmcBaseCrawler):
    def __init__(self):
        super().__init__(
            base_url="https://www.cmcseoul.or.kr",
            inst_no="01",
            hospital_code="CMCSEOUL",
            hospital_name="서울성모병원",
        )
```

---

## 새 병원 추가 체크리스트

1. [ ] 병원 홈페이지에서 진료과/의사 조회 URL 확인
2. [ ] 같은 재단/네트워크 병원인지 확인 → 베이스 클래스 사용 가능 여부 판단
3. [ ] 정적 HTML인지 동적(JS) 렌더링인지 확인
   - 정적 → `httpx.AsyncClient` 직접 사용
   - JSON API → `httpx`로 API 직접 호출
   - 동적 → `Playwright` 사용
4. [ ] `external_id`에 사용할 의사 고유 코드 확인 (포맷: `{HOSPITAL_CODE}-{원내코드}`)
5. [ ] **개별 교수 상세/스케줄 URL 확인** — `crawl_doctor_schedule`에서 1명만 조회할 수 있는 엔드포인트 패턴을 반드시 설계해 둘 것 (전체 크롤링 fallback은 금지)
6. [ ] `crawlers/{hospital_code}_crawler.py` 파일 생성
7. [ ] `crawl_doctor_schedule()` 구현 시 `_fetch_all()` 호출하지 않는지 재확인
8. [ ] `crawlers/factory.py`의 `_DEDICATED_CRAWLERS` dict에 등록
9. [ ] `crawlers/factory.py`의 `_HOSPITAL_REGION` dict에 지역 추가
10. [ ] DB의 `hospitals` 테이블에 병원 레코드 추가
11. [ ] 크롤러 단독 실행 테스트
12. [ ] 개별 조회 성능 테스트 — `?refresh=true` 로 1명 조회 시 1초 내외, 네트워크 로그에 다른 교수 호출 없음
13. [ ] **병원 로고 추가** — `frontend/public/hospital-logos/{HOSPITAL_CODE}.png` (아래 가이드 참조)

---

## 병원 로고 자동 수집 가이드

새 병원 크롤러 추가 시 로고 파일도 함께 준비한다. 저장 위치와 파일명은 고정:
- 경로: `frontend/public/hospital-logos/{HOSPITAL_CODE}.png` (또는 `.svg`)
- 파일명: 병원 코드 대문자 (factory.py 의 `_DEDICATED_CRAWLERS` 키와 동일)
- 프론트엔드 `HospitalLogo` 컴포넌트가 `.svg → .png → 🏥 이모지` 순으로 자동 폴백하므로, 파일이 없어도 앱은 깨지지 않음

**3단계 수집 절차 (순서대로 시도):**

### 1단계 — Google 파비콘 서비스 (빠른 첫 시도)
```bash
curl -sfL "https://www.google.com/s2/favicons?domain={DOMAIN}&sz=128" \
  -o frontend/public/hospital-logos/{HOSPITAL_CODE}.png
```
다운로드 후 **반드시 해상도 확인**:
```bash
python -c "from PIL import Image; print(Image.open('frontend/public/hospital-logos/{HOSPITAL_CODE}.png').size)"
```
- **48×48 이상이면** → 그대로 사용, 종료
- **48px 미만이면** → 확대 시 깨져 보이므로 2단계로 진행

### 2단계 — 홈페이지 HTML 에서 실제 로고 `<img>` 추출
파비콘이 저해상도면 병원 홈페이지 헤더의 실제 로고 이미지를 추출한다:
```bash
# (1) 홈페이지 HTML 다운로드
curl -sL -A "Mozilla/5.0" "https://{DOMAIN}/" -o /tmp/page.html

# (2) 로고 후보 찾기 — class/src/alt 에 "logo" 포함된 <img>
grep -iEo '<img[^>]*logo[^>]*>' /tmp/page.html | head -10
```
보통 `<img class="logo" src="/common/img/logo.png">` 또는 `<h1 class="logo"><img src="...">` 구조. src 가 상대경로면 도메인 붙여서 다운로드 후 `{HOSPITAL_CODE}.png` 로 저장.

**판단 포인트:**
- `<img>` 여러 개 나오면 alt 텍스트나 경로(`/header/`, `/main/`)로 헤더 로고 선별
- SVG 경로(`.svg`)가 나오면 그대로 받아 `.svg` 로 저장 (프론트가 우선 사용)
- CSS `background-image` 로만 깔린 로고는 CSS 파일까지 파싱해야 함 → 이 경우 3단계로 스킵

### 3단계 — 포기하고 폴백 유지
위 두 단계 모두 실패하거나 로고 추출이 과하게 복잡하면, 해당 병원은 🏥 이모지 폴백으로 남겨둔다. 앱 동작에는 지장 없음. 나중에 수동으로 교체 가능.

**주의사항:**
- 다운로드한 파일이 실제 이미지인지 항상 확인 (`file {파일}` → `PNG image` / `SVG` 확인). HTML 에러 페이지가 내려오는 경우가 많음
- 병원 로고는 저작권 이슈가 있을 수 있으나 내부 도구용 식별자 목적이면 일반적으로 허용 범위

---

## 팩토리 등록 방법

`backend/app/crawlers/factory.py`:
```python
from app.crawlers.{hospital_code}_crawler import {ClassName}

_DEDICATED_CRAWLERS = {
    # ... 기존 항목 ...
    "{HOSPITAL_CODE}": ({ClassName}, "{병원 전체명}"),
}

_HOSPITAL_REGION = {
    # ... 기존 항목 ...
    "{HOSPITAL_CODE}": "서울",  # 서울 | 경기 | 인천
}
```

---

## 자주 쓰는 httpx + BeautifulSoup 패턴

```python
async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
    # GET 요청 → HTML 파싱
    resp = await client.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # POST (form 데이터)
    resp = await client.post(url, data={"deptcd": deptcd})

    # JSON API
    resp = await client.get(url, params={"deptcd": deptcd})
    data = resp.json()

    # 테이블 파싱
    rows = soup.select("table.schedule tbody tr")
    for row in rows:
        cols = row.find_all("td")
        # cols[0].text.strip() 등으로 접근
```

---

## 에러 처리 표준

```python
# 개별 의사 실패 시 → 해당 의사만 건너뜀, 전체 중단 금지
try:
    detail = await self.crawl_doctor_schedule(staff_id)
except httpx.TimeoutException:
    logger.warning(f"[{self.hospital_code}] Timeout: {staff_id}")
    continue
except Exception as e:
    logger.error(f"[{self.hospital_code}] 크롤링 실패 {name}: {e}")
    continue
```

재시도는 Celery 태스크 레벨에서 처리됨 (`max_retries=3`, `default_retry_delay=120`).

---

## 크롤러 Celery 태스크 연결

완성된 크롤러는 `factory.py`에 등록하면 자동으로 Celery 태스크에서 사용됨.
→ 상세 패턴은 `references/celery_integration.md` 참조

---

## 참조 파일

- `references/amc_reference.md` — AMC 표준 다단계 크롤러 구현 (참조 기준)
- `references/snuh_reference.md` — SNUH 단일 페이지 크롤러 (특수 케이스, 참고용)
- `references/playwright_pattern.md` — JS 동적 렌더링 병원용 Playwright 패턴
- `references/celery_integration.md` — Celery 태스크 연결 패턴
