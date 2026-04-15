"""대한의사협회 연수교육센터 (edu.kma.org) 학술행사 크롤러.

설계 배경:
- 목록 페이지(`/edu/schedule`) 는 익명 GET 시 빈 tbody 만 돌려주기 때문에 사용 불가.
- 그러나 개별 상세 페이지(`/edu/schedule_view?eduidx=N`) 는 공개 접근 가능하며
  `table.scheduleView` 에 모든 필드가 server-side 렌더링됨.
- eduidx 는 정수 ID 이며 등록 순서로 증가. 이진 탐색으로 max 를 찾고,
  그 범위에서 역순으로 상세 페이지를 훑어 `교육일자` 가 타겟 윈도우에
  들어오는 것만 수집한다. ID 는 등록순이라 "오래된 ID = 멀리 앞 날짜" 조합도
  있으므로 단순 날짜 기준 조기 종료는 하지 않고 `scan_back` 만큼 전부 순회.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.crawlers.academic._filters import is_online_only

logger = logging.getLogger(__name__)

DETAIL_URL = "https://edu.kma.org/edu/schedule_view?eduidx={idx}"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_lectures(soup: BeautifulSoup) -> list[dict]:
    """`table.scheduleList` 에서 강의 프로그램을 추출.

    KMA 상세 페이지의 프로그램 테이블 헤더는 다음 6열로 구성된다:
        구분 | 월/일 | 시간 | 강의제목 | 강사 | 소속

    - 첫 row 는 헤더(th) 행이므로 skip.
    - 강사 셀이 비어 있으면(개회사/폐회사/등록 등) skip.
    - 실패 시 빈 리스트 반환.
    """
    table = soup.select_one("table.scheduleList")
    if not table:
        return []

    rows = table.find_all("tr")
    if len(rows) < 2:
        return []

    # 헤더 인덱스 매핑
    header_cells = rows[0].find_all(["th", "td"])
    headers = [c.get_text(" ", strip=True) for c in header_cells]
    idx = {name: i for i, name in enumerate(headers)}

    i_date = idx.get("월/일") or idx.get("일/시") or 1
    i_time = idx.get("시간", 2)
    i_title = idx.get("강의제목") or idx.get("강의명") or 3
    i_lecturer = idx.get("강사") or idx.get("연자") or 4
    i_aff = idx.get("소속") or idx.get("소속기관") or 5

    lectures: list[dict] = []
    for row in rows[1:]:
        cells = row.find_all(["th", "td"])
        if len(cells) <= max(i_lecturer, i_aff):
            continue
        lecturer = cells[i_lecturer].get_text(" ", strip=True)
        if not lecturer:
            continue
        title = cells[i_title].get_text(" ", strip=True) if i_title < len(cells) else ""
        time_str = cells[i_time].get_text(" ", strip=True) if i_time < len(cells) else ""
        aff = cells[i_aff].get_text(" ", strip=True) if i_aff < len(cells) else ""
        lectures.append({
            "time": time_str or None,
            "title": title or None,
            "lecturer": lecturer,
            "affiliation": aff or None,
        })
    return lectures


def _parse_detail(html: str) -> Optional[dict]:
    """상세 페이지 HTML → dict. 실패 시 None."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.scheduleView")
    if not table:
        return None

    fields: dict[str, str] = {}
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"])
        i = 0
        while i < len(cells) - 1:
            th, td = cells[i], cells[i + 1]
            if th.name == "th" and td.name == "td":
                key = th.get_text(strip=True)
                val = td.get_text(" ", strip=True)
                if key and key not in fields:
                    fields[key] = val
                i += 2
            else:
                i += 1

    # 필수 필드
    date_str = fields.get("교육일자", "").strip()
    if not DATE_RE.match(date_str):
        return None
    name = fields.get("교육명", "").strip()
    if not name:
        return None

    return {
        "name": name,
        "organizer": (fields.get("기관명") or "").strip() or None,
        "sub_organizer": (fields.get("주관") or "").strip() or None,
        "start_date": date_str,
        "end_date": date_str,
        "location": (fields.get("장소") or "").strip() or None,
        "region": (fields.get("지역") or "").strip() or None,
        "kma_category": (fields.get("교육종류(임상의학)") or "").strip() or None,
        "description": (fields.get("비고") or "").strip() or None,
        "detail_url_external": (fields.get("교육 URL") or "").strip() or None,
        "code": (fields.get("교육코드") or "").strip() or None,
        "lectures": _parse_lectures(soup),
    }


class KmaEduCrawler:
    """KMA 교육센터 상세 페이지를 eduidx 역순으로 순회하는 크롤러."""

    def __init__(
        self,
        concurrency: int = 5,
        request_delay: float = 0.15,
        timeout: float = 15.0,
    ):
        self.concurrency = concurrency
        self.request_delay = request_delay
        self.timeout = timeout

    async def _get(self, client: httpx.AsyncClient, idx: int) -> Optional[str]:
        try:
            r = await client.get(DETAIL_URL.format(idx=idx))
        except Exception as e:
            logger.debug(f"KMA {idx}: request error {e}")
            return None
        if r.status_code != 200:
            return None
        return r.text

    async def find_max_eduidx(
        self, client: httpx.AsyncClient, lo: int = 140000, hi: int = 250000
    ) -> int:
        """이진 탐색으로 현재 유효한 최대 eduidx 를 찾는다."""
        async def valid(idx: int) -> bool:
            html = await self._get(client, idx)
            return bool(html and _parse_detail(html))

        # hi 가 유효하면 더 넓혀야 함
        while await valid(hi):
            lo, hi = hi, hi * 2
            if hi > 5_000_000:
                break

        while lo < hi:
            mid = (lo + hi + 1) // 2
            if await valid(mid):
                lo = mid
            else:
                hi = mid - 1
        logger.info(f"KmaEduCrawler: max eduidx ≈ {lo}")
        return lo

    async def crawl_events(
        self,
        months_ahead: int = 3,
        scan_back: int = 1500,
        today: Optional[date] = None,
    ) -> list[dict]:
        """max eduidx 를 찾고 역방향으로 scan_back 개 ID 를 순회, 날짜 필터링."""
        today = today or date.today()
        window_end = today + timedelta(days=months_ahead * 31)

        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=self.timeout,
            http2=False,
        ) as client:
            max_idx = await self.find_max_eduidx(client)
            start_idx = max(1, max_idx - scan_back + 1)
            logger.info(
                f"KmaEduCrawler: scanning eduidx [{start_idx}, {max_idx}] "
                f"window [{today}, {window_end}]"
            )

            sem = asyncio.Semaphore(self.concurrency)
            results: list[dict] = []
            stats = {"scanned": 0, "missing": 0, "out_of_range": 0, "kept": 0}

            async def worker(idx: int):
                async with sem:
                    html = await self._get(client, idx)
                    stats["scanned"] += 1
                    if not html:
                        stats["missing"] += 1
                        await asyncio.sleep(self.request_delay)
                        return
                    parsed = _parse_detail(html)
                    await asyncio.sleep(self.request_delay)
                    if not parsed:
                        stats["missing"] += 1
                        return
                    if is_online_only(parsed.get("name"), parsed.get("location")):
                        stats["out_of_range"] += 1
                        return
                    try:
                        d = datetime.strptime(parsed["start_date"], "%Y-%m-%d").date()
                    except ValueError:
                        stats["missing"] += 1
                        return
                    if d < today or d > window_end:
                        stats["out_of_range"] += 1
                        return
                    parsed["eduidx"] = str(idx)
                    parsed["url"] = DETAIL_URL.format(idx=idx)
                    results.append(parsed)
                    stats["kept"] += 1

            tasks = [worker(i) for i in range(start_idx, max_idx + 1)]
            # gather in chunks to keep memory/output tractable
            chunk = 200
            for i in range(0, len(tasks), chunk):
                await asyncio.gather(*tasks[i:i + chunk])

            logger.info(f"KmaEduCrawler stats: {stats}")
            return results
