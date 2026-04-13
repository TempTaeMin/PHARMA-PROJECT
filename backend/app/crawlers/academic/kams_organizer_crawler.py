"""대한의학회(KAMS) 회원학회 마스터 리스트 크롤러.

`http://kams.or.kr/association/sub2.php` 의 HTML 테이블에서
영역(I~VIII) × 정회원/준회원(기간학회)/준회원(세부·융합학회) 구조의
회원학회 목록을 추출한다. 연 1회 seed 용도.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

KAMS_URL = "http://kams.or.kr/association/sub2.php"

# tbody 행 인덱스 → 영역 (I ~ VIII)
DOMAINS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]

# tbody 행의 td 컬럼 인덱스 → membership_type
# 각 행은 3개 td: [정회원, 준회원(기간학회), 준회원(세부·융합학회)]
COLUMN_MEMBERSHIP = {
    0: "정회원",
    1: "준회원(기간학회)",
    2: "준회원(세부·융합학회)",
}


class KamsOrganizerCrawler:
    """KAMS 회원학회 페이지에서 학회명 + 홈페이지를 추출."""

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def crawl_organizers(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(KAMS_URL, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            html = resp.content.decode("utf-8", errors="replace")

        return self._parse(html)

    def _parse(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            logger.warning("KAMS: table not found")
            return []

        table = tables[0]
        tbody = table.find("tbody") or table
        data_rows = tbody.find_all("tr", recursive=False)

        organizers: list[dict] = []
        seen: set[str] = set()

        for row_idx, row in enumerate(data_rows):
            cells = row.find_all("td", recursive=False)
            domain = DOMAINS[row_idx] if row_idx < len(DOMAINS) else None

            for idx, membership in COLUMN_MEMBERSHIP.items():
                if idx >= len(cells):
                    continue
                cell = cells[idx]

                # <a href>텍스트</a><br> 형태로 나열
                links = cell.find_all("a")
                if links:
                    for a in links:
                        name = a.get_text(" ", strip=True)
                        homepage = a.get("href") or None
                        if not name or name in seen:
                            continue
                        seen.add(name)
                        organizers.append({
                            "name": self._normalize_name(name),
                            "name_en": None,
                            "domain": domain,
                            "membership_type": membership,
                            "homepage": homepage,
                        })
                else:
                    # 링크 없이 텍스트만 있는 경우 (공백 구분)
                    text = cell.get_text("\n", strip=True)
                    if not text:
                        continue
                    for name in text.splitlines():
                        name = name.strip()
                        if not name or name in seen:
                            continue
                        seen.add(name)
                        organizers.append({
                            "name": self._normalize_name(name),
                            "name_en": None,
                            "domain": domain,
                            "membership_type": membership,
                            "homepage": None,
                        })

        logger.info(f"KAMS: parsed {len(organizers)} organizers")
        return organizers

    @staticmethod
    def _normalize_name(name: str) -> str:
        # 중점/공백 등 통일
        return " ".join(name.split()).strip()


async def _main():
    crawler = KamsOrganizerCrawler()
    rows = await crawler.crawl_organizers()
    print(f"total: {len(rows)}")
    for r in rows[:5]:
        print(r)


if __name__ == "__main__":
    import asyncio
    asyncio.run(_main())
