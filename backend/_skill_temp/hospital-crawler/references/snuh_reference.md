# SNUH (서울대학교병원) 크롤러 참조 구현

SNUH 크롤러는 MR 스케줄러의 첫 번째 완성 크롤러로, 새 병원 추가 시 참조 기준.

## 특징
- 정적 HTML 기반 (Playwright 불필요)
- `deptcd` + `drcd` 파라미터로 스케줄 조회
- BeautifulSoup으로 파싱

## 기본 정보
```
hospital_code: SNUH
병원명: 서울대학교병원
BASE_URL: https://www.snuh.org
진료과 목록: POST /hn/HNS_DPT_1001.do
의사 목록: POST /hn/HNS_DPT_1002.do  (deptcd 파라미터)
스케줄 조회: POST /hn/HNS_DPT_1003.do  (deptcd + drcd 파라미터)
```

## 크롤러 구조 요약

```python
class SNUHCrawler:
    BASE_URL = "https://www.snuh.org"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 ...",
        "Referer": "https://www.snuh.org",
    }

    def get_departments(self) -> List[Dict]:
        # POST /hn/HNS_DPT_1001.do
        # 응답: HTML 테이블
        # 파싱: deptcd (hidden input 또는 data-* 속성), dept_name (td 텍스트)
        ...

    def get_doctors(self, deptcd: str) -> List[Dict]:
        # POST /hn/HNS_DPT_1002.do, data={"deptcd": deptcd}
        # 파싱: drcd, doctor_name, position
        ...

    def get_schedule(self, deptcd: str, drcd: str) -> List[Dict]:
        # POST /hn/HNS_DPT_1003.do, data={"deptcd": deptcd, "drcd": drcd}
        # 스케줄 테이블: 행=요일, 열=오전/오후
        # 셀 내용으로 available 여부 판단 (진료 텍스트 유무)
        ...
```

## 스케줄 테이블 파싱 핵심 로직

```python
DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT"]
schedule = []

rows = soup.select("table.tbl_schedule tbody tr")
for i, row in enumerate(rows):
    if i >= len(DAYS):
        break
    cols = row.find_all("td")
    am_text = cols[0].text.strip() if len(cols) > 0 else ""
    pm_text = cols[1].text.strip() if len(cols) > 1 else ""
    
    schedule.append({
        "day_of_week": DAYS[i],
        "am_pm": "AM",
        "available": bool(am_text and am_text != "-"),
    })
    schedule.append({
        "day_of_week": DAYS[i],
        "am_pm": "PM",
        "available": bool(pm_text and pm_text != "-"),
    })

return schedule
```

## 주의사항
- 요청 간 `time.sleep(0.5~1.0)` 권장 (IP 차단 방지)
- 진료과 수: 약 40~50개
- 의사 수: 진료과당 평균 10~20명
- 전체 크롤링 소요시간: 약 15~30분 (Celery 비동기 처리 권장)
