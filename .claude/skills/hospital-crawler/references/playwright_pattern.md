# Playwright 크롤러 패턴

JS 동적 렌더링 병원 사이트에 사용하는 Playwright 기반 크롤러 패턴.

## 언제 사용하는가

- `requests`로 가져온 HTML이 데이터 없이 거의 비어있을 때
- JS가 실행된 후에야 진료과/의사/스케줄 데이터가 DOM에 채워질 때
- 페이지 내에서 클릭, 선택, 탭 전환 등 인터랙션이 필요할 때

## 설치

```bash
pip install playwright --break-system-packages
playwright install chromium
```

## 기본 구조 (async)

```python
from playwright.async_api import async_playwright
import asyncio
import logging

logger = logging.getLogger(__name__)

class {HospitalCode}Crawler:
    """
    {병원명} Playwright 기반 크롤러
    사유: JS 동적 렌더링 사이트
    """

    BASE_URL = "{병원 URL}"

    async def get_departments(self) -> list:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            })
            try:
                await page.goto(self.BASE_URL, timeout=30000)
                await page.wait_for_selector(".dept-list", timeout=10000)
                # 진료과 목록 파싱
                items = await page.query_selector_all(".dept-item")
                result = []
                for item in items:
                    deptcd = await item.get_attribute("data-deptcd")
                    name = await item.inner_text()
                    result.append({"deptcd": deptcd, "dept_name": name.strip()})
                return result
            except Exception as e:
                logger.error(f"get_departments error: {e}")
                return []
            finally:
                await browser.close()

    async def get_schedule(self, deptcd: str, drcd: str) -> list:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(self.BASE_URL)
                # 진료과 선택 클릭
                await page.click(f"[data-deptcd='{deptcd}']")
                # 의사 선택 클릭
                await page.click(f"[data-drcd='{drcd}']")
                # 스케줄 로드 대기
                await page.wait_for_selector(".schedule-table", timeout=10000)
                # 스케줄 파싱 (병원마다 다름)
                ...
            except Exception as e:
                logger.error(f"get_schedule error: {e}")
                return []
            finally:
                await browser.close()

    def crawl_all(self) -> list:
        """동기 래퍼 — Celery 태스크에서 호출 시 사용"""
        return asyncio.run(self._crawl_all_async())

    async def _crawl_all_async(self) -> list:
        results = []
        try:
            departments = await self.get_departments()
            for dept in departments:
                doctors = await self.get_doctors(dept["deptcd"])
                for doctor in doctors:
                    schedule = await self.get_schedule(dept["deptcd"], doctor["drcd"])
                    results.append({
                        "hospital_code": "{HOSPITAL_CODE}",
                        "deptcd": dept["deptcd"],
                        "dept_name": dept["dept_name"],
                        "drcd": doctor["drcd"],
                        "doctor_name": doctor["doctor_name"],
                        "schedule": schedule,
                    })
        except Exception as e:
            logger.error(f"crawl_all error: {e}")
        return results
```

## 브라우저 재사용 패턴 (성능 최적화)

병원별 의사가 많을 경우, 매번 브라우저를 열고 닫으면 느림.
브라우저 1개를 열고 페이지만 재사용하는 패턴:

```python
async def _crawl_all_async(self) -> list:
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            departments = await self._get_departments_with_page(page)
            for dept in departments:
                doctors = await self._get_doctors_with_page(page, dept["deptcd"])
                for doctor in doctors:
                    schedule = await self._get_schedule_with_page(
                        page, dept["deptcd"], doctor["drcd"]
                    )
                    results.append({...})
                    await asyncio.sleep(0.5)  # IP 차단 방지
        finally:
            await browser.close()
    return results
```

## 주의사항

- `headless=True` 기본값. 디버깅 시만 `headless=False` 사용
- `wait_for_selector` timeout은 10000ms(10초) 권장
- 병원 JS 로딩이 느린 경우 `wait_for_load_state("networkidle")` 추가
- 요청 간 `await asyncio.sleep(0.5~1.0)` 필수 (IP 차단 방지)
- Celery에서 호출 시 `asyncio.run()` 동기 래퍼 사용

## requests vs Playwright 성능 비교

| 항목 | requests | Playwright |
|------|----------|------------|
| 속도 | 빠름 | 3~5배 느림 |
| 메모리 | 낮음 | 높음 (브라우저 프로세스) |
| 안정성 | 높음 | 사이트 변경에 취약 |
| 적용 가능 범위 | 정적/XHR | 모든 사이트 |

가능하면 `requests` 먼저 시도하고, 안 될 때만 Playwright 사용.
