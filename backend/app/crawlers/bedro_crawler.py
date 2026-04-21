"""강남베드로병원(Gangnam Bedro Hospital) 크롤러

병원 공식명: 강남베드로병원
홈페이지: www.goodspine.org
기술: 단일 정적 HTML (httpx + BeautifulSoup)

구조:
  단일 URL `/bbs/h04.php` 안에 14개 진료과 탭과 38명 의사 카드 존재.
  각 카드는 `div.alert.alert-warning`이며 내부에 `table.doc_time` 스케줄 포함.
  범례:
    div.h04_circle  = 진료 (외래)
    div.h04_triangle = 수술 (외래 아님 → 스케줄 미포함)
    빈 셀           = 휴진

external_id: BEDRO-{modal번호}  (예: BEDRO-1-1)
  — 모달 data-target="#doc1-1Modal" 에서 추출, 동명이인 리스크 없음.
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.goodspine.org"
TIMETABLE_URL = f"{BASE_URL}/bbs/h04.php"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 헤더 순서가 월~토 고정이지만 안전하게 텍스트 매핑도 지원
DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}

MODAL_RE = re.compile(r"#doc(\d+(?:-\d+)?)Modal")


class BedroCrawler:
    """강남베드로병원 크롤러 — 단일 페이지 정적 HTML"""

    def __init__(self):
        self.hospital_code = "BEDRO"
        self.hospital_name = "강남베드로병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
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
            logger.error(f"[BEDRO] 페이지 로드 실패: {e}")
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        self._cached_soup = soup
        return soup

    @staticmethod
    def _extract_modal_id(card) -> str:
        tag = card.select_one('a[data-target^="#doc"]')
        if tag:
            m = MODAL_RE.search(tag.get("data-target", ""))
            if m:
                return m.group(1)
        # fallback: 이미지 경로 doc01_01 → "1-1"
        img = card.select_one('img[src*="/img/doc"]')
        if img:
            m = re.search(r"doc0*(\d+)_0*(\d+)", img.get("src", ""))
            if m:
                return f"{m.group(1)}-{m.group(2)}"
        return ""

    def _parse_schedule_table(self, table) -> list[dict]:
        if table is None:
            return []
        rows = table.find_all("tr")
        if len(rows) < 3:
            return []

        # 헤더: 요일/월/화/.../토 → 컬럼 인덱스 → dow 매핑
        header_cells = rows[0].find_all(["th", "td"])
        col_to_dow: dict[int, int] = {}
        for ci, cell in enumerate(header_cells):
            t = cell.get_text(strip=True)
            if t in DAY_INDEX:
                col_to_dow[ci] = DAY_INDEX[t]
        if not col_to_dow:
            return []

        schedules: list[dict] = []
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if not cells:
                continue
            label = cells[0].get_text(strip=True)
            if label == "오전":
                slot = "morning"
            elif label == "오후":
                slot = "afternoon"
            else:
                continue
            start, end = TIME_RANGES[slot]
            for ci, cell in enumerate(cells):
                if ci not in col_to_dow:
                    continue
                # h04_circle 있는 셀만 진료로 인정 (triangle=수술, 빈 셀=휴진)
                if cell.select_one(".h04_circle") is None:
                    continue
                schedules.append({
                    "day_of_week": col_to_dow[ci],
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return schedules

    def _parse_card(self, card) -> dict | None:
        modal_id = self._extract_modal_id(card)
        if not modal_id:
            return None

        h4 = card.select_one("h4")
        if not h4:
            return None
        small = h4.select_one("small")
        position = small.get_text(strip=True) if small else ""
        if small:
            small.extract()
        name = h4.get_text(" ", strip=True)
        if not name:
            return None

        dept_p = card.select_one("li.text-left p")
        department = dept_p.get_text(strip=True) if dept_p else ""

        img = card.select_one('img[src*="/img/doc"]')
        photo_url = ""
        if img and img.get("src"):
            src = img["src"]
            photo_url = src if src.startswith("http") else f"{BASE_URL}{src}"

        ext_id = f"BEDRO-{modal_id}"
        profile_url = f"{TIMETABLE_URL}#doc{modal_id}Modal"
        schedules = self._parse_schedule_table(card.select_one("table.doc_time"))

        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "modal_id": modal_id,
            "name": name,
            "department": department,
            "position": position,
            "specialty": "",
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
        }

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            soup = await self._fetch_page(client)

        if soup is None:
            self._cached_data = []
            return []

        seen: set[str] = set()
        result: list[dict] = []
        for card in soup.select("div.alert.alert-warning"):
            if card.select_one("table.doc_time") is None:
                continue
            doc = self._parse_card(card)
            if not doc:
                continue
            if doc["external_id"] in seen:
                continue
            seen.add(doc["external_id"])
            result.append(doc)

        logger.info(f"[BEDRO] 총 {len(result)}명")
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
        """개별 교수 조회 — 1회 GET 후 해당 카드만 파싱 (skill 규칙 #7 준수)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 같은 인스턴스의 이전 전체 크롤링 결과가 있으면 재사용
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, []) if k in ("schedules", "date_schedules") else d.get(k, "")
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}
            return empty

        prefix = "BEDRO-"
        raw_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not raw_id:
            return empty

        async with self._make_client() as client:
            soup = await self._fetch_page(client)

        if soup is None:
            return empty

        target_attr = f"#doc{raw_id}Modal"
        match_tag = soup.select_one(f'a[data-target="{target_attr}"]')
        if match_tag is None:
            return empty
        card = match_tag.find_parent(
            "div", attrs={"class": lambda c: c and "alert" in c and "alert-warning" in c},
        )
        if card is None:
            return empty

        doc = self._parse_card(card)
        if not doc:
            return empty
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
