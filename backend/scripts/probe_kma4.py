"""KMA 4차 — httpx GET 로 직접 호출. 테이블 rows HTML 확인."""
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import httpx
from bs4 import BeautifulSoup

URL = "https://edu.kma.org/edu/schedule"


def fetch(start, end, label=""):
    params = {
        "start_dt": start,
        "end_dt": end,
        "sch_type": "1",
        "sch_txt": "",
        "s_smallcode_Nm": "",
        "s_place": "",
        "siidx": "",
        "s_escidx": "",
        "s_scode": "",
        "pageNo": "1",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    r = httpx.get(URL, params=params, headers=headers, timeout=20.0, follow_redirects=True)
    print(f"\n=== {label} ({start} ~ {end}) ===")
    print(f"Status: {r.status_code}, Length: {len(r.text)}")
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table")
    if not table:
        print("NO TABLE")
        return
    rows = table.select("tbody tr")
    # 의미있는 row 만 (td 비어있지 않은)
    real_rows = [row for row in rows if row.get_text(strip=True)]
    print(f"rows total={len(rows)}, non-empty={len(real_rows)}")
    for i, row in enumerate(real_rows[:5]):
        cells = row.find_all("td")
        print(f"--- row[{i}] {len(cells)} cells ---")
        for ci, td in enumerate(cells):
            txt = td.get_text(" ", strip=True)[:140]
            # link/onclick extraction
            link = td.find("a")
            href = link.get("href") if link else None
            onclick = link.get("onclick") if link else None
            print(f"  td[{ci}]={txt!r}")
            if href or onclick:
                print(f"          href={href} onclick={onclick}")


if __name__ == "__main__":
    fetch("2026-04-01", "2026-05-31", "2026-04-05")
    fetch("2025-01-01", "2025-12-31", "2025 전체")
    fetch("2024-06-01", "2024-08-31", "2024 여름")
    fetch("2026-04-12", "2027-04-12", "1년 앞")
