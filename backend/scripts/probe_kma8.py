"""KMA 8차 — POST + Referer + 세션 쿠키 사용."""
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import httpx
from bs4 import BeautifulSoup


URL = "https://edu.kma.org/edu/schedule"


def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Referer": URL,
        "Origin": "https://edu.kma.org",
    }

    with httpx.Client(headers=headers, timeout=20.0, follow_redirects=True) as client:
        # 1. 세션 시작 — index 먼저
        r0 = client.get(URL)
        print(f"GET init: {r0.status_code}, cookies: {dict(r0.cookies)}")

        data = {
            "start_dt": "2026-04-01",
            "end_dt": "2026-05-31",
            "sch_type": "1",
            "sch_txt": "",
            "s_smallcode_Nm": "",
            "s_place": "",
            "siidx": "",
            "s_escidx": "",
            "s_scode": "",
            "pageNo": "1",
        }

        # 2. POST
        r1 = client.post(URL, data=data)
        print(f"\nPOST: {r1.status_code}, len={len(r1.text)}")
        soup = BeautifulSoup(r1.text, "html.parser")
        table = soup.find("table")
        rows = [row for row in (table.select("tbody tr") if table else []) if row.get_text(strip=True)]
        print(f"rows: {len(rows)}")
        for i, row in enumerate(rows[:5]):
            cells = row.find_all("td")
            print(f"  row[{i}]: {[td.get_text(' ', strip=True)[:80] for td in cells]}")

        # 3. GET with session
        r2 = client.get(URL, params=data)
        print(f"\nGET with session: {r2.status_code}, len={len(r2.text)}")
        soup = BeautifulSoup(r2.text, "html.parser")
        table = soup.find("table")
        rows = [row for row in (table.select("tbody tr") if table else []) if row.get_text(strip=True)]
        print(f"rows: {len(rows)}")
        for i, row in enumerate(rows[:5]):
            cells = row.find_all("td")
            print(f"  row[{i}]: {[td.get_text(' ', strip=True)[:80] for td in cells]}")

        # 4. /edu/schedule 의 <script> 태그에서 initial data embedded? → 전체 HTML 검색
        print("\n[search for inline data in response]")
        for keyword in ["schedule_view", "eduidx=", "교육명", "평점", "var list", "scheduleList"]:
            idx = r2.text.find(keyword)
            if idx >= 0:
                print(f"  found '{keyword}' at {idx}: ...{r2.text[max(0, idx-40):idx+200]}...")


if __name__ == "__main__":
    main()
