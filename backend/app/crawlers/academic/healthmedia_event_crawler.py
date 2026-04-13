"""메디칼허브(healthmedia.co.kr) 국내 학술일정 크롤러.

목록 페이지는 월별 요약 기사(`2026년 4월 국내 학술일정`) 를 나열하고,
각 기사 본문 안에 `<p>` 태그 하나당 학술행사 1건을 담고 있다.

한 줄 포맷 (여러 공백/nbsp 로 구분):
    YYYY-MM-DD   행사명   주최 학회   장소
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.crawlers.academic._filters import is_online_only

logger = logging.getLogger(__name__)

LIST_URL = "https://www.healthmedia.co.kr/news/articleList.html"
LIST_PARAMS = {
    "sc_sub_section_code": "S2N13",
    "view_type": "sm",
}

DATE_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})(?:\s*[~\-]\s*(\d{4}-\d{2}-\d{2}|\d{2}-\d{2}|\d{2}))?\s*(.*)$")


class HealthmediaEventCrawler:
    """월별 요약 기사 → 개별 학술행사 파싱."""

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self._client_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

    async def crawl_events(self, max_pages: int = 3) -> list[dict]:
        """목록 페이지 N개를 돌며 모든 이벤트 수집."""
        events: list[dict] = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=self._client_headers) as client:
            article_urls: list[str] = []
            for page in range(1, max_pages + 1):
                params = {**LIST_PARAMS, "page": page}
                resp = await client.get(LIST_URL, params=params)
                if resp.status_code != 200:
                    logger.warning(f"healthmedia list page {page}: {resp.status_code}")
                    break
                page_urls = self._parse_list(resp.text)
                if not page_urls:
                    break
                article_urls.extend(page_urls)

            # 중복 제거, 순서 유지
            seen = set()
            article_urls = [u for u in article_urls if not (u in seen or seen.add(u))]
            logger.info(f"healthmedia: {len(article_urls)} article URLs")

            for url in article_urls:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    events.extend(self._parse_article(resp.text, url))
                except Exception as exc:
                    logger.warning(f"healthmedia article fail: {url} — {exc}")

        logger.info(f"healthmedia: parsed {len(events)} events")
        return events

    def _parse_list(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        for li in soup.select("#section-list ul li.item"):
            a = li.select_one("h2.titles a, h4.titles a, .titles a")
            if not a:
                continue
            href = a.get("href", "")
            if href:
                urls.append(href)
        return urls

    def _parse_article(self, html: str, article_url: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        body = soup.select_one("#article-view-content-div")
        if not body:
            return []

        events: list[dict] = []
        for p in body.find_all("p"):
            # nbsp 는 그대로 유지해서 필드 경계로 활용
            raw = p.get_text(" ", strip=True)
            if not raw or not re.match(r"^\d{4}-\d{2}-\d{2}", raw):
                continue

            parsed = self._parse_event_line(raw)
            if parsed:
                if is_online_only(parsed.get("name"), parsed.get("location")):
                    continue
                parsed["url"] = article_url
                events.append(parsed)
        return events

    def _parse_event_line(self, line: str) -> Optional[dict]:
        """한 줄을 필드로 분해. 원본은 `&nbsp;` 여러 개로 구분됨.

        전략: 토큰을 `\xa0` 유무로 두 종류로 만들고, `\xa0` 2 개 이상이 연속된
        지점을 field separator 로 본다. 정규화 후 `split(2+ whitespace)` 와
        동일한 효과.
        """
        # 날짜 분리
        m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:\s*[~\-]\s*(\d{4}-\d{2}-\d{2}))?\s+(.*)$", line)
        if not m:
            return None
        start_date = m.group(1)
        end_date = m.group(2) or start_date
        rest = m.group(3)
        if not rest:
            return None

        # 필드 구분: nbsp 1 개 이상 + 일반 공백 혼합으로 2 글자 이상의 공백 시퀀스
        # 예: `\xa0 \xa0` 또는 `\xa0\xa0` 를 필드 경계로 본다
        # 먼저 nbsp 와 space 가 혼합된 2 글자 이상 연속을 TAB 으로 치환
        rest_sep = re.sub(r"[\xa0\s]{2,}", "\t", rest)
        fields = [f.strip() for f in rest_sep.split("\t") if f.strip()]

        # 단일 공백으로도 한 번 더 정리
        fields = [re.sub(r"\s+", " ", f) for f in fields]

        name: Optional[str] = None
        organizer: Optional[str] = None
        location: Optional[str] = None

        if len(fields) >= 3:
            name, organizer, location = fields[0], fields[1], " ".join(fields[2:])
        elif len(fields) == 2:
            # 2개 필드 — organizer + location 또는 name + organizer
            # 두 번째 필드가 학회/협회/병원 류면 그게 organizer 로 추정
            if re.search(r"(학회|협회|의사회|의학회|연구회|병원|대학교|센터)$", fields[1]):
                name, organizer = fields[0], fields[1]
            else:
                name, location = fields[0], fields[1]
        elif len(fields) == 1:
            name = fields[0]
        else:
            return None

        return {
            "name": name,
            "organizer": organizer,
            "start_date": start_date,
            "end_date": end_date,
            "location": location,
            "description": None,
        }


async def _main():
    logging.basicConfig(level=logging.INFO)
    crawler = HealthmediaEventCrawler()
    events = await crawler.crawl_events(max_pages=1)
    print(f"total: {len(events)}")
    for e in events[:10]:
        print(e)


if __name__ == "__main__":
    import asyncio
    asyncio.run(_main())
