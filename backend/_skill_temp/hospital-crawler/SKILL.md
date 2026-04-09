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
2. **고유 키 통일** — 의사 식별은 반드시 `deptcd + drcd` 조합을 사용한다
3. **구조 통일** — 모든 크롤러는 아래 표준 클래스 구조를 따른다
4. **에러 무시 금지** — 모든 예외는 로깅 후 빈 리스트 반환, 절대 앱을 죽이지 않는다
5. **병원별 파일 분리** — 크롤러 1개 = 파일 1개 (`crawlers/snuh.py`, `crawlers/amc.py` 등)

---

## 크롤링 기술 선택 기준

병원 사이트에 접근하기 전에 반드시 유형을 판단한다.

| 유형 | 비율 | 판단 방법 | 사용 기술 |
|------|------|-----------|-----------|
| 정적 HTML | ~40% | Network 탭에 XHR/Fetch 요청 없음 | `requests + BeautifulSoup` |
| XHR API 방식 | ~10% | Network 탭에 JSON API 호출 보임 | `requests` (API 직접 호출) |
| JS 동적 렌더링 | ~50% | Network 탭에 XHR 있거나 빈 HTML | `Playwright` |

**판단 방법 (브라우저 개발자도구 F12)**
1. Network 탭 → XHR/Fetch 필터 → 페이지 새로고침
2. 요청이 없으면 → 정적 HTML → `requests`
3. JSON 응답 요청이 보이면 → 그 URL 직접 호출 → `requests`
4. 요청은 있는데 HTML/JS 파일들만 있거나, `requests`로 가져온 HTML이 데이터 없이 비어있으면 → `Playwright`

**`requests`를 먼저 시도하고, 실패하면 `Playwright`로 전환한다.**

---

## 표준 크롤러 클래스 구조

```python
import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class {HospitalCode}Crawler:
    """
    {병원 전체명} 크롤러
    출처: {크롤링 대상 URL}
    고유키: deptcd + drcd
    """

    BASE_URL = "{병원 기본 URL}"
    SCHEDULE_URL = "{스케줄 조회 URL}"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "{BASE_URL}",
    }

    def get_departments(self) -> List[Dict]:
        """진료과 목록 반환. 반드시 deptcd 포함."""
        raise NotImplementedError

    def get_doctors(self, deptcd: str) -> List[Dict]:
        """특정 진료과의 의사 목록 반환. 반드시 drcd 포함."""
        raise NotImplementedError

    def get_schedule(self, deptcd: str, drcd: str) -> List[Dict]:
        """특정 의사의 진료 스케줄 반환."""
        raise NotImplementedError

    def crawl_all(self) -> List[Dict]:
        """전체 크롤링 실행. 표준 결과 포맷으로 반환."""
        results = []
        try:
            departments = self.get_departments()
            for dept in departments:
                doctors = self.get_doctors(dept["deptcd"])
                for doctor in doctors:
                    schedule = self.get_schedule(dept["deptcd"], doctor["drcd"])
                    results.append({
                        "hospital_code": "{hospital_code}",
                        "deptcd": dept["deptcd"],
                        "dept_name": dept["dept_name"],
                        "drcd": doctor["drcd"],
                        "doctor_name": doctor["doctor_name"],
                        "schedule": schedule,
                    })
        except Exception as e:
            logger.error(f"{HospitalCode}Crawler.crawl_all error: {e}")
        return results
```

---

## 표준 반환 포맷

### 진료과 (get_departments)
```python
[
    {"deptcd": "001", "dept_name": "내과"},
    {"deptcd": "002", "dept_name": "외과"},
]
```

### 의사 (get_doctors)
```python
[
    {"drcd": "D001", "doctor_name": "홍길동", "position": "교수"},
]
```

### 스케줄 (get_schedule)
```python
[
    {"day_of_week": "MON", "am_pm": "AM", "available": True},
    {"day_of_week": "MON", "am_pm": "PM", "available": False},
    # day_of_week: MON/TUE/WED/THU/FRI/SAT
    # am_pm: AM/PM
]
```

### crawl_all 최종 결과
```python
[
    {
        "hospital_code": "SNUH",       # 병원 식별 코드 (대문자)
        "deptcd": "001",
        "dept_name": "내과",
        "drcd": "D001",
        "doctor_name": "홍길동",
        "schedule": [...]
    }
]
```

---

## 병원 사이트 구조 유형

대부분의 병원은 아래 **3단계 구조**를 따른다. 이것이 표준 패턴이다.

```
1단계: 진료과 목록 페이지
   └── 2단계: 진료과별 의사 목록 페이지  (진료과 코드로 필터)
           └── 3단계: 의사 개인 스케줄 페이지  (의사 코드로 조회)
```

**AMC(서울아산병원) — 표준 다단계 구조의 참조 기준**
- 진료과 목록: `deptListTypeA.do` → 진료과 코드(`D006` 등) 추출
- 의사 목록: `staffBaseInfoList.do?searchHpCd=D006` → `requests` 정적 HTML
- 의사 식별자: `doct` 파라미터 (암호화된 문자열)
- 스케줄 상세: JS 렌더링 가능성 높음 → Playwright 필요할 수 있음
→ 상세 구현: `references/amc_reference.md`

**SNUH(서울대학교병원) — 특수 케이스 (참조 기준 아님)**
- 전체 스케줄이 URL 한 번으로 한 HTML에 다 담기는 예외적으로 쉬운 구조
- 새 병원 작성 시 이 패턴으로 접근하면 안 됨
→ 참고용: `references/snuh_reference.md`

---

## 새 병원 추가 체크리스트

1. [ ] 병원 홈페이지에서 진료과/의사 조회 URL 확인
2. [ ] 정적 HTML인지 동적(JS) 렌더링인지 확인
   - 정적 → `requests.get()` 직접 사용
   - 동적 → **Playwright 사용 금지**, 대신 XHR/API 엔드포인트 찾기 (개발자도구 Network 탭)
3. [ ] `deptcd`, `drcd`에 해당하는 파라미터명 확인
4. [ ] `crawlers/{hospital_code_lower}.py` 파일 생성
5. [ ] `crawlers/__init__.py`에 import 추가
6. [ ] DB의 `hospitals` 테이블에 병원 레코드 추가
7. [ ] 크롤러 단독 실행 테스트: `python -m crawlers.{hospital_code_lower}`

---

## 자주 쓰는 BeautifulSoup 패턴

```python
# GET 요청
resp = requests.get(url, headers=self.HEADERS, timeout=10)
resp.raise_for_status()
soup = BeautifulSoup(resp.text, "html.parser")

# POST (form 데이터)
resp = requests.post(url, data={"deptcd": deptcd}, headers=self.HEADERS, timeout=10)

# JSON API
resp = requests.get(url, params={"deptcd": deptcd}, headers=self.HEADERS)
data = resp.json()

# 테이블 파싱
rows = soup.select("table.schedule tbody tr")
for row in rows:
    cols = row.find_all("td")
    # cols[0].text.strip() 등으로 접근

# select_one으로 단일 요소
dept_name = soup.select_one(".dept-title").text.strip()
```

---

## 에러 처리 표준

```python
# 개별 의사 실패 시 → 해당 의사만 건너뜀, 전체 중단 금지
try:
    schedule = self.get_schedule(deptcd, drcd)
except requests.Timeout:
    logger.warning(f"Timeout: deptcd={deptcd}, drcd={drcd}")
    schedule = []
except Exception as e:
    logger.error(f"Schedule fetch error: {e}")
    schedule = []

# IP 차단 대응 (재시도)
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_schedule(self, deptcd, drcd):
    ...
```

---

## 크롤러 Celery 태스크 연결

완성된 크롤러는 `tasks/crawl_tasks.py`에서 Celery 태스크로 래핑한다.
→ 상세 패턴은 `references/celery_integration.md` 참조

---

## 참조 파일

- `references/amc_reference.md` — AMC 표준 다단계 크롤러 구현 (참조 기준)
- `references/snuh_reference.md` — SNUH 단일 페이지 크롤러 (특수 케이스, 참고용)
- `references/playwright_pattern.md` — JS 동적 렌더링 병원용 Playwright 패턴
- `references/celery_integration.md` — Celery 태스크 연결 패턴
