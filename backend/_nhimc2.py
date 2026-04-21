import httpx, asyncio, sys, re
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
from bs4 import BeautifulSoup

async def main():
    async with httpx.AsyncClient(headers={"User-Agent":"Mozilla/5.0"}, timeout=30, follow_redirects=True) as c:
        r = await c.get("https://www.nhimc.or.kr/dept/profList.do", params={"deptNo":"29"})
        text = r.text
        idx = text.find("openDoctorView")
        print("idx:", idx, file=sys.stderr)
        if idx >= 0:
            window = text[max(0,idx-1500):idx+1500]
            with open("C:/tmp/nhimc_window.txt", "w", encoding="utf-8") as f:
                f.write(window)
            print("WROTE", len(window), "chars", file=sys.stderr)
        # also save profViewPop
        m = re.search(r"openDoctorView\s*\(\s*(\d+)\s*,\s*(\d+)", text)
        if m:
            r2 = await c.get("https://www.nhimc.or.kr/doctor/profViewPop.do", params={"deptNo":m.group(1),"profNo":m.group(2)})
            with open("C:/tmp/nhimc_profview.html", "w", encoding="utf-8") as f:
                f.write(r2.text)
            print("PROF", r2.status_code, len(r2.text), file=sys.stderr)

asyncio.run(main())
