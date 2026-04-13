"""KMA 5차 — $.search() 구현 확인 + 네트워크 로그 완전 캡처."""
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

        all_reqs = []

        async def on_req(req):
            all_reqs.append((req.method, req.url, req.resource_type, req.post_data))

        page.on("request", on_req)

        await page.goto(URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        # 1. $.search() 와 $.today() 소스 찾기
        sources = await page.evaluate("""
            () => {
                const out = {};
                if (typeof $.search === 'function') out.search = $.search.toString();
                if (typeof $.today === 'function') out.today = $.today.toString();
                if (typeof $.goPage === 'function') out.goPage = $.goPage.toString();
                return out;
            }
        """)
        for name, src in sources.items():
            print(f"=== $.{name} ===")
            print(src[:1500])
            print()

        # 2. 페이지 내 모든 JS 파일 중 search 관련된 것 찾기
        scripts = await page.query_selector_all("script[src]")
        for s in scripts:
            src = await s.get_attribute("src")
            if src and ("common" in src or "schedule" in src or "front" in src):
                print(f"[script src] {src}")

        # 3. 그냥 페이지 소스에서 schedule 관련 JS 문자열 검색
        html = await page.content()
        # goPage/search 정의 찾기
        import re
        for m in re.finditer(r"\$\.(\w+)\s*=\s*function[^{]*\{[^}]{0,400}\}", html):
            name = m.group(1)
            if name in ("search", "today", "goPage", "go_excel"):
                print(f"\n### inline $.{name} ###")
                print(m.group(0)[:800])

        # 4. 전체 inline scripts 의 함수 정의 검색
        inline_scripts = await page.query_selector_all("script:not([src])")
        for i, sc in enumerate(inline_scripts):
            text = await sc.inner_text()
            if "search" in text or "today" in text or "goPage" in text:
                print(f"\n--- inline script #{i} (rel. parts) ---")
                for line in text.split("\n"):
                    if "search" in line or "today" in line or "goPage" in line or "location.href" in line or "submit" in line:
                        print(f"  {line.strip()[:200]}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
