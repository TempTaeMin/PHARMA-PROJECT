import httpx, asyncio, sys, re
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
from bs4 import BeautifulSoup

async def main():
    async with httpx.AsyncClient(headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.nhimc.or.kr"}, timeout=30, follow_redirects=True) as c:
        r = await c.get("https://www.nhimc.or.kr/dept/profList.do", params={"deptNo":"29"})
        m = re.search(r"openDoctorView\s*\((\d+),\s*(\d+)", r.text)
        if m:
            i = m.start()
            print("WINDOW:")
            print(r.text[max(0,i-400):i+600])
        soup = BeautifulSoup(r.text, "html.parser")
        # show all h tags
        print("\nH3:", [h.get_text(strip=True) for h in soup.select("h3")][:8])
        print("H4:", [h.get_text(strip=True) for h in soup.select("h4")][:8])
        # find prof view url
        m2 = re.search(r"openDoctorView\s*\((\d+),\s*(\d+)", r.text)
        if m2:
            r2 = await c.get("https://www.nhimc.or.kr/doctor/profViewPop.do", params={"deptNo":m2.group(1),"profNo":m2.group(2)})
            print("\nprofViewPop status:", r2.status_code, "len:", len(r2.text))
            soup2 = BeautifulSoup(r2.text, "html.parser")
            tbls = soup2.select("table")
            print("tables:", len(tbls))
            for t in tbls[:2]:
                print("---")
                print(t.get_text(" | ", strip=True)[:400])

asyncio.run(main())
