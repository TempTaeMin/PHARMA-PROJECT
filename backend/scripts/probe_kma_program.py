"""KMA 상세 페이지 HTML 구조 탐색 (일회성).

사용법:
    cd backend
    python scripts/probe_kma_program.py <eduidx> [eduidx2 eduidx3 ...]

`table.scheduleView` 이외의 모든 table 을 클래스/헤더/샘플 row 와 함께 덤프해서
강의 프로그램 섹션의 구조(클래스명, 컬럼 헤더)를 파악한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.crawlers.academic.kma_edu_crawler import DEFAULT_HEADERS, DETAIL_URL  # noqa: E402


def probe(idx: int) -> None:
    url = DETAIL_URL.format(idx=idx)
    print(f"\n{'=' * 70}\neduidx={idx}  url={url}\n{'=' * 70}")
    try:
        r = httpx.get(url, headers=DEFAULT_HEADERS, timeout=15.0)
    except Exception as e:
        print(f"[ERROR] request failed: {e}")
        return
    if r.status_code != 200:
        print(f"[ERROR] status={r.status_code}")
        return

    soup = BeautifulSoup(r.text, "html.parser")
    tables = soup.find_all("table")
    print(f"total <table> count: {len(tables)}")

    for i, t in enumerate(tables):
        cls = " ".join(t.get("class") or []) or "(no class)"
        print(f"\n--- table #{i}  class='{cls}' ---")
        # 헤더 행 (th 가 있는 첫 tr)
        ths = t.find_all("th")
        if ths:
            headers = [th.get_text(" ", strip=True) for th in ths[:12]]
            print(f"th headers: {headers}")

        # 본문 샘플 (처음 3개 row)
        rows = t.find_all("tr")
        print(f"tr count: {len(rows)}")
        for r_idx, row in enumerate(rows[:3]):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            print(f"  row[{r_idx}]: {cells}")

    # 프로그램/강의 힌트 검색
    for kw in ["프로그램", "강의", "강사", "연자", "Program", "Lecture"]:
        hits = [el for el in soup.find_all(string=lambda s: s and kw in s)][:5]
        if hits:
            print(f"\n[text hit: '{kw}'] -> {len(hits)} occurrence(s)")
            for h in hits[:3]:
                parent = h.parent
                print(f"  <{parent.name} class={parent.get('class')}> '{h.strip()[:80]}'")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/probe_kma_program.py <eduidx> [<eduidx> ...]")
        return 1
    for arg in sys.argv[1:]:
        try:
            probe(int(arg))
        except ValueError:
            print(f"[SKIP] not an integer: {arg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
