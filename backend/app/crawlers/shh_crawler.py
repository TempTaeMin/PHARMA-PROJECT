"""서울현대병원(Seoul Hyundai Hospital) 크롤러

병원 공식명: 서울현대병원
홈페이지: www.seoulhyundai.co.kr
기술: 단일 정적 HTML (httpx + BeautifulSoup)

구조:
  단일 페이지 /page/sub0103.php 안에:
    상단 카드: <ul class="doc-ul"><li data-cat="{진료과}" data-wr-id="{ID}"> ...
    하단 모달: <section class="doc-detail"><figure data-wr-id="{ID}" data-cat="{진료과}"> ...

  각 figure 안에 스케줄 테이블:
    <table class="box-shadow">
      <thead><tr><th>시간</th><th>월</th>...<th>토</th></tr></thead>
      <tbody>
        <tr><td>오전</td> 6칸 (span.treat=진료, span.surgery=수술, 빈/텍스트=휴진)</tr>
        <tr><td>오후</td> 6칸</tr>
      </tbody>
    </table>

  span.treat ● → 외래진료, span.surgery ● → 수술(제외), 그 외 → 휴진.

external_id: SHH-{data-wr-id}
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.seoulhyundai.co.kr"
TIMETABLE_URL = f"{BASE_URL}/page/sub0103.php"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("14:00", "17:30")}
DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}


class ShhCrawler:
    """서울현대병원 크롤러 — 단일 페이지 정적 HTML + 모달 figure 파싱"""

    def __init__(self):
        self.hospital_code = "SHH"
        self.hospital_name = "서울현대병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        self._cached_data: list[dict] | None = None
        self._cached_soup: BeautifulSoup | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    async def _fetch_page(self, client: httpx.AsyncClient) -> BeautifulSoup | None:
        if self._cached_soup is not None:
            return self._cached_soup
        try:
            resp = await client.get(TIMETABLE_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[SHH] 페이지 로드 실패: {e}")
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        self._cached_soup = soup
        return soup

    @staticmethod
    def _normalize_name(raw: str) -> str:
        """'이 우 태' → '이우태' (공백 제거)"""
        return re.sub(r"\s+", "", raw).strip()

    @staticmethod
    def _split_position_dept(h5_text: str) -> tuple[str, str]:
        """'병원장 / 정형외과' → ('병원장', '정형외과')"""
        if "/" in h5_text:
            pos, dept = h5_text.split("/", 1)
            return pos.strip(), dept.strip()
        return "", h5_text.strip()

    def _parse_schedule_table(self, table) -> list[dict]:
        if table is None:
            return []

        thead = table.find("thead")
        if thead is None:
            return []
        header_cells = thead.find_all(["th", "td"])
        col_to_dow: dict[int, int] = {}
        for ci, cell in enumerate(header_cells):
            t = cell.get_text(strip=True)
            if t in DAY_INDEX:
                col_to_dow[ci] = DAY_INDEX[t]
        if not col_to_dow:
            return []

        tbody = table.find("tbody") or table
        schedules: list[dict] = []
        for row in tbody.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if not cells:
                continue
            label = cells[0].get_text(strip=True)
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            else:
                continue
            start, end = TIME_RANGES[slot]
            for ci, cell in enumerate(cells):
                if ci not in col_to_dow:
                    continue
                # span.treat 이 있으면 외래진료, span.surgery 는 수술(제외)
                treat_span = cell.find("span", class_="treat")
                if treat_span is None:
                    continue
                # surgery 전용 셀은 span.surgery 만 있고 span.treat 없음 → 위 조건으로 이미 제외됨
                schedules.append({
                    "day_of_week": col_to_dow[ci],
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return schedules

    def _parse_figure(self, figure, card_info: dict) -> dict | None:
        wr_id = figure.get("data-wr-id", "").strip()
        if not wr_id:
            return None

        h1 = figure.find("h1")
        h3 = figure.find("h3")
        if h1 is None:
            return None
        name = self._normalize_name(h1.get_text(" ", strip=True))
        if not name:
            return None

        h3_text = h3.get_text(" ", strip=True) if h3 else ""
        position, dept_from_h3 = self._split_position_dept(h3_text)

        # 카드 쪽 data-cat 을 우선, 없으면 h3 의 뒤쪽
        department = card_info.get("department") or dept_from_h3

        table = figure.find("table", class_=re.compile(r"box-shadow"))
        schedules = self._parse_schedule_table(table)

        ext_id = f"SHH-{wr_id}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": name,
            "department": department,
            "position": position,
            "specialty": "",
            "profile_url": TIMETABLE_URL,
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
        }

    def _collect_card_info(self, soup: BeautifulSoup) -> dict[str, dict]:
        """상단 카드(ul.doc-ul)에서 wr_id → {department, position} 매핑"""
        result: dict[str, dict] = {}
        ul = soup.find("ul", class_=re.compile(r"doc-ul"))
        if ul is None:
            return result
        for li in ul.find_all("li"):
            wr_id = li.get("data-wr-id", "").strip()
            if not wr_id:
                continue
            dept = li.get("data-cat", "").strip()
            h5 = li.find("h5")
            position = ""
            if h5:
                pos, _ = self._split_position_dept(h5.get_text(" ", strip=True))
                position = pos
            result[wr_id] = {"department": dept, "position": position}
        return result

    def _parse_all_doctors(self, soup: BeautifulSoup) -> list[dict]:
        card_map = self._collect_card_info(soup)

        section = soup.find("section", class_=re.compile(r"doc-detail"))
        if section is None:
            # fallback: 전체 문서에서 figure[data-wr-id] 검색
            figures = soup.find_all("figure", attrs={"data-wr-id": True})
        else:
            figures = section.find_all("figure", attrs={"data-wr-id": True})

        result: list[dict] = []
        seen: set[str] = set()
        for fig in figures:
            wr_id = fig.get("data-wr-id", "").strip()
            card = card_map.get(wr_id, {})
            doc = self._parse_figure(fig, card)
            if not doc:
                continue
            if not doc.get("position") and card.get("position"):
                doc["position"] = card["position"]
            if doc["external_id"] in seen:
                continue
            seen.add(doc["external_id"])
            result.append(doc)

        return result

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            soup = await self._fetch_page(client)

        if soup is None:
            self._cached_data = []
            return []

        result = self._parse_all_doctors(soup)
        logger.info(f"[SHH] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        seen: list[str] = []
        for d in data:
            dept = d.get("department", "")
            if dept and dept not in seen:
                seen.append(dept)
        return [{"code": dept, "name": dept} for dept in seen]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department",
                                "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회 — 통합 페이지 1회 GET 후 해당 figure 만 파싱"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, []) if k in ("schedules", "date_schedules") else d.get(k, "")
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}
            return empty

        prefix = "SHH-"
        wr_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not wr_id:
            return empty

        async with self._make_client() as client:
            soup = await self._fetch_page(client)
        if soup is None:
            return empty

        card_map = self._collect_card_info(soup)
        figure = soup.find("figure", attrs={"data-wr-id": wr_id})
        if figure is None:
            return empty
        doc = self._parse_figure(figure, card_map.get(wr_id, {}))
        if not doc:
            return empty
        card = card_map.get(wr_id, {})
        if not doc.get("position") and card.get("position"):
            doc["position"] = card["position"]

        return {k: doc.get(k, []) if k in ("schedules", "date_schedules") else doc.get(k, "")
                for k in ("staff_id", "name", "department", "position",
                         "specialty", "profile_url", "notes",
                         "schedules", "date_schedules")}

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]

        doctors = [
            CrawledDoctor(
                name=d["name"],
                department=d["department"],
                position=d.get("position", ""),
                specialty=d.get("specialty", ""),
                profile_url=d.get("profile_url", ""),
                external_id=d["external_id"],
                notes=d.get("notes", ""),
                schedules=d["schedules"],
                date_schedules=d.get("date_schedules", []),
            )
            for d in data
        ]

        return CrawlResult(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            status="success" if doctors else "partial",
            doctors=doctors,
            crawled_at=datetime.utcnow(),
        )
