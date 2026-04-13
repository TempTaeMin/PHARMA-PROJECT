"""KMA 6차 — searchForm 분석 + 실제 form 제출 후 rows 확인."""
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

        reqs = []
        page.on("request", lambda r: reqs.append((r.method, r.url, r.post_data)) if "kma" in r.url else None)

        await page.goto(URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # searchForm action / method
        form_info = await page.evaluate("""
            () => {
                const f = document.querySelector('#searchForm');
                if (!f) return {error: 'no #searchForm'};
                const fields = [];
                for (const el of f.querySelectorAll('input, select')) {
                    fields.push({name: el.name, value: el.value, type: el.type});
                }
                return {action: f.action, method: f.method, fields};
            }
        """)
        print("[searchForm]", form_info.get("action"), form_info.get("method"))
        for f in form_info.get("fields", []):
            print(f"  {f}")

        # 한 달 범위 설정 후 submit
        await page.evaluate("""
            () => {
                document.querySelector('#start_dt').value = '2026-04-01';
                document.querySelector('#end_dt').value = '2026-05-31';
            }
        """)
        # 직접 form submit
        try:
            await page.evaluate("document.getElementById('searchForm').submit()")
        except Exception as e:
            print("submit err:", e)
        await page.wait_for_load_state("networkidle", timeout=20000)
        await page.wait_for_timeout(2000)

        print(f"\n[after submit] URL: {page.url}")
        rows = await page.query_selector_all("table tbody tr")
        real = []
        for r in rows:
            txt = (await r.inner_text()).strip()
            if txt:
                real.append(r)
        print(f"rows: total={len(rows)} non-empty={len(real)}")

        for ri, row in enumerate(real[:5]):
            cells = await row.query_selector_all("td")
            print(f"--- row #{ri} ({len(cells)} cells) ---")
            for ci, td in enumerate(cells):
                txt = (await td.inner_text()).strip().replace("\n", " | ")[:180]
                inner = (await td.inner_html())[:250]
                print(f"  td[{ci}]={txt!r}")
                if "href" in inner or "onclick" in inner or "img" in inner:
                    print(f"          html={inner!r}")

        print(f"\n[requests]")
        for m, u, d in reqs[-10:]:
            print(f"  {m} {u[:100]}")
            if d:
                print(f"    data={d[:200]}")

        # 혹시 다른 탭/뷰 타입 (달력 뷰)
        print("\n[전체 tbody after submit HTML (2000)]")
        try:
            th = await page.inner_html("table tbody")
            print(th[:2000])
        except Exception as e:
            print(e)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
