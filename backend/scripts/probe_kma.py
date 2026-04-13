"""KMA 교육 일정 페이지 구조 탐색 스크립트 (일회성).

목적:
1. 테이블 컬럼 순서
2. 월 이동 UI
3. 카테고리 드롭다운 실제 값
4. 첫 10개 row HTML 샘플
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
        await page.goto(URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        print("=" * 60)
        print("URL:", page.url)
        print("Title:", await page.title())

        # 1. HTML 스캔 — 어떤 테이블/form/select 이 있는지
        tables = await page.query_selector_all("table")
        print(f"\n[tables] count={len(tables)}")
        for i, t in enumerate(tables[:3]):
            html = (await t.inner_html())[:500]
            print(f"--- table #{i} (first 500 chars) ---")
            print(html)

        # 2. select 태그 모두
        selects = await page.query_selector_all("select")
        print(f"\n[selects] count={len(selects)}")
        for i, s in enumerate(selects):
            name = await s.get_attribute("name")
            _id = await s.get_attribute("id")
            options = await s.query_selector_all("option")
            opt_vals = []
            for o in options:
                v = await o.get_attribute("value")
                t = (await o.inner_text()).strip()
                opt_vals.append(f"{v}={t}")
            print(f"select[{i}] name={name} id={_id} ({len(opt_vals)} options)")
            for v in opt_vals[:60]:
                print(f"  {v}")

        # 3. form 분석
        forms = await page.query_selector_all("form")
        print(f"\n[forms] count={len(forms)}")
        for i, f in enumerate(forms):
            action = await f.get_attribute("action")
            method = await f.get_attribute("method")
            print(f"form[{i}] action={action} method={method}")

        # 4. 월/년 이동 버튼들
        btns = await page.query_selector_all("button, a.btn, input[type='button']")
        print(f"\n[buttons] count={len(btns)}")
        seen_text = set()
        for b in btns[:80]:
            txt = (await b.inner_text()).strip()[:30]
            onclick = (await b.get_attribute("onclick") or "")[:60]
            href = (await b.get_attribute("href") or "")[:60]
            key = f"{txt}|{onclick}|{href}"
            if key in seen_text or not (txt or onclick or href):
                continue
            seen_text.add(key)
            print(f"  txt={txt!r} onclick={onclick!r} href={href!r}")

        # 5. 첫 페이지 main 테이블 rows (실제 데이터)
        print("\n[DOM dump: #contents or body] (first 3000 chars)")
        main = await page.query_selector("#contents, #content, main, .content")
        if main:
            body_html = (await main.inner_html())[:3000]
        else:
            body_html = (await page.content())[:3000]
        print(body_html)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
