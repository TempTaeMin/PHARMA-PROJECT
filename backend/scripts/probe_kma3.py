"""KMA 교육 일정 3차 탐색 — 날짜 범위 설정 + AJAX endpoint 캡처.

start_dt/end_dt 를 한 달 범위로 설정한 뒤 $.search() → 응답 내용 + table dump.
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

        # 모든 XHR/fetch 응답 캡처
        responses_info = []

        async def on_response(resp):
            try:
                url = resp.url
                if "edu.kma.org" not in url:
                    return
                ct = resp.headers.get("content-type", "")
                if resp.request.resource_type not in ("xhr", "fetch", "document"):
                    return
                body = ""
                try:
                    body = (await resp.text())[:800]
                except Exception:
                    pass
                responses_info.append((resp.request.method, url, ct, body))
            except Exception:
                pass

        page.on("response", on_response)

        await page.goto(URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # 날짜 범위 설정 — 한 달
        await page.evaluate("""
            () => {
                document.querySelector("input[name='start_dt']").value = '2026-04-01';
                document.querySelector("input[name='end_dt']").value = '2026-05-31';
            }
        """)
        await page.wait_for_timeout(500)

        # $.search() 호출
        try:
            await page.evaluate("$.search()")
        except Exception as e:
            print("search err:", e)
        await page.wait_for_timeout(5000)

        # tbody 확인
        rows = await page.query_selector_all("table tbody tr")
        print(f"[rows after range + search] count={len(rows)}")

        # 각 row 의 td 내용 dump
        for ri, row in enumerate(rows[:8]):
            cells = await row.query_selector_all("td")
            print(f"--- row #{ri} ({len(cells)} cells) ---")
            for ci, td in enumerate(cells):
                txt = (await td.inner_text()).strip().replace("\n", " | ")[:160]
                html = (await td.inner_html())[:250]
                print(f"  td[{ci}] text={txt!r}")
                if "a " in html or "onclick" in html or "href" in html or "img" in html:
                    print(f"          html={html!r}")

        # 응답 dump
        print(f"\n[responses captured] count={len(responses_info)}")
        for m, u, ct, body in responses_info[-15:]:
            print(f"--- {m} {u} ct={ct[:30]}")
            if "html" in ct or "json" in ct or "text" in ct:
                print(f"  body (800 chars): {body[:800]!r}")

        # 실제 table HTML 일부
        print("\n[tbody HTML after load]")
        tbody_html = await page.inner_html("table tbody")
        print(tbody_html[:4000])

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
