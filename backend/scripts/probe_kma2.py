"""KMA 교육 일정 페이지 2차 탐색 — AJAX 로드 후 테이블 구조 + 소분류.

1. $.search() 또는 $.today() 트리거 → tbody 채워질 때까지 대기
2. 첫 20개 row 의 td 내용 인덱스별로 dump
3. 대분류 = 임상의학(47) 선택 시 소분류 값 수집
"""
import asyncio
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright

URL = "https://edu.kma.org/edu/schedule"


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(locale="ko-KR")
        page = await ctx.new_page()
        # 네트워크 응답 로깅
        requests = []
        page.on("request", lambda req: requests.append((req.method, req.url)) if "edu" in req.url or "schedule" in req.url else None)

        await page.goto(URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # 1. $.search() 호출로 오늘 날짜 기준 이벤트 로드
        try:
            await page.evaluate("$.search()")
        except Exception as e:
            print("search err:", e)
        await page.wait_for_timeout(4000)

        # 2. 테이블 tbody 재확인
        table_html = await page.inner_html("table")
        print("=" * 60)
        print("[table after $.search()] (first 3500 chars)")
        print(table_html[:3500])

        # 3. row 개수 + 첫 3 row 의 td 내용
        rows = await page.query_selector_all("table tbody tr")
        print(f"\n[rows] count={len(rows)}")
        for ri, row in enumerate(rows[:3]):
            cells = await row.query_selector_all("td")
            print(f"--- row #{ri} ({len(cells)} cells) ---")
            for ci, td in enumerate(cells):
                txt = (await td.inner_text()).strip()[:120]
                inner_html = (await td.inner_html())[:200]
                print(f"  td[{ci}] text={txt!r}")
                print(f"          html={inner_html!r}")

        # 4. 네트워크 요청 (어떤 AJAX endpoint 가 호출되는지)
        print(f"\n[edu/schedule related requests]")
        for m, u in requests[:20]:
            print(f"  {m} {u}")

        # 5. 대분류 임상의학 선택 → 소분류 수집
        try:
            await page.select_option("select[name='s_escidx']", value="47")
            await page.wait_for_timeout(1500)
            sub = await page.query_selector("select[name='s_scode']")
            opts = await sub.query_selector_all("option")
            print(f"\n[소분류 after 임상의학 선택] count={len(opts)}")
            for o in opts:
                v = await o.get_attribute("value")
                t = (await o.inner_text()).strip()
                print(f"  {v}={t}")
        except Exception as e:
            print("소분류 err:", e)

        # 6. 대분류 = 기초의학 (48)
        try:
            await page.select_option("select[name='s_escidx']", value="48")
            await page.wait_for_timeout(1500)
            sub = await page.query_selector("select[name='s_scode']")
            opts = await sub.query_selector_all("option")
            print(f"\n[소분류 after 기초의학 선택] count={len(opts)}")
            for o in opts:
                v = await o.get_attribute("value")
                t = (await o.inner_text()).strip()
                print(f"  {v}={t}")
        except Exception as e:
            print("소분류2 err:", e)

        # 7. 검색 조건 초기화 후 $.today() 호출
        await page.evaluate("$.today && $.today()")
        await page.wait_for_timeout(2000)
        rows2 = await page.query_selector_all("table tbody tr")
        print(f"\n[rows after $.today()] count={len(rows2)}")
        if rows2:
            cells = await rows2[0].query_selector_all("td")
            print(f"first row: {len(cells)} cells")
            for ci, td in enumerate(cells):
                txt = (await td.inner_text()).strip()[:120]
                print(f"  td[{ci}]={txt!r}")

        # 8. 전체 페이지 HTML 길이 + form 값들
        print("\n[form values]")
        form_vals = await page.evaluate("""
            () => {
                const vals = {};
                document.querySelectorAll('input, select').forEach(el => {
                    vals[el.name || el.id] = el.value;
                });
                return vals;
            }
        """)
        for k, v in form_vals.items():
            print(f"  {k}={v}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
