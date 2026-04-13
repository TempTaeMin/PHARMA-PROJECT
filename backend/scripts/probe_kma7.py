"""KMA 7차 — sch_es 체크박스 해제 후 + 여러 필터 조합."""
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import httpx
from bs4 import BeautifulSoup


URL = "https://edu.kma.org/edu/schedule"


def fetch(label, **kwargs):
    defaults = {
        "start_dt": "2026-04-01",
        "end_dt": "2026-06-30",
        "sch_type": "1",
        "sch_txt": "",
        "s_smallcode_Nm": "",
        "s_place": "",
        "siidx": "",
        "s_escidx": "",
        "s_scode": "",
        "pageNo": "1",
    }
    defaults.update(kwargs)
    r = httpx.get(URL, params=defaults, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36",
    }, timeout=20.0)
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table")
    real = [row for row in table.select("tbody tr") if row.get_text(strip=True)] if table else []
    print(f"\n=== {label} === params={ {k:v for k,v in defaults.items() if v} } ===")
    print(f"rows={len(real)} status={r.status_code} len={len(r.text)}")
    for i, row in enumerate(real[:3]):
        cells = row.find_all("td")
        texts = [td.get_text(" ", strip=True)[:80] for td in cells]
        print(f"  row[{i}]: {texts}")
        for td in cells:
            a = td.find("a")
            if a and (a.get("href") or a.get("onclick")):
                print(f"    link: href={a.get('href')} onclick={a.get('onclick')}")
                break


if __name__ == "__main__":
    # sch_es 없이
    fetch("sch_es 없음")
    fetch("sch_es=Y", sch_es="Y")
    fetch("sch_es=N", sch_es="N")
    # 임상의학 전체
    fetch("임상의학", s_escidx="47")
    # 비뇨의학과
    fetch("임상의학+비뇨", s_escidx="47", s_scode="13")
    # 이전 연도
    fetch("2024 임상의학", start_dt="2024-06-01", end_dt="2024-08-31", s_escidx="47")
    # sch_type 3 (세부 제목)
    fetch("sch_type=3 (세부교육 제목)", sch_type="3")
    # infos 파라미터 없이 + full form
    fetch("full params", infos="", uId="", uPwd="")
