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
2. **고유 키 통일** — 의사 식별은 `external_id` (포맷: `{HOSPITAL_CODE}-{원내코드}`)
3. **구조 통일** — 모든 크롤러는 아래 표준 클래스 구조를 따른다
4. **비동기 기반** — 모든 크롤러는 `httpx.AsyncClient` + `async def` 사용
5. **에러 무시 금지** — 모든 예외는 로깅 후 빈 리스트 반환, 절대 앱을 죽이지 않는다
6. **병원별 파일 분리** — 크롤러 1개 = 파일 1개 (`crawlers/{hospital_code}_crawler.py`)

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

## 캐싱 패턴

전체 크롤링 결과를 `_cached_data`에 캐시하여, `crawl_doctor_list`와 `crawl_doctor_schedule` 호출 시 재사용한다.

```python
async def _fetch_all(self) -> list[dict]:
    """전체 데이터 크롤링 + 캐싱"""
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
5. [ ] `crawlers/{hospital_code}_crawler.py` 파일 생성
6. [ ] `crawlers/factory.py`의 `_DEDICATED_CRAWLERS` dict에 등록
7. [ ] `crawlers/factory.py`의 `_HOSPITAL_REGION` dict에 지역 추가
8. [ ] DB의 `hospitals` 테이블에 병원 레코드 추가
9. [ ] 크롤러 단독 실행 테스트

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
