import httpx, asyncio, sys
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

async def main():
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.nhimc.or.kr/doctor/profViewPop.do?deptNo=29&profNo=125",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    async with httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=True) as c:
        r = await c.post(
            "https://www.nhimc.or.kr/doctor/getMonthSchedule.do",
            data={"deptCd": "02400", "profEmpCd": "111712", "yyyyMM": "202604"},
        )
        print("STATUS:", r.status_code, file=sys.stderr)
        print("LEN:", len(r.text), file=sys.stderr)
        print("HEAD:", r.text[:1500], file=sys.stderr)

asyncio.run(main())
