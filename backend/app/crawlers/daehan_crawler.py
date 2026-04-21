"""대한병원(Daehan Hospital) 크롤러

병원 공식명: 대한병원 (성화의료재단 종합병원, 서울 강북구 수유동)
홈페이지: www.daehanh.com
기술: 단일 정적 HTML (httpx + BeautifulSoup)

구조:
  통합 페이지 1개 /bbs/content.php?co_id=hosp_doctors 에 전 진료과 × 전 의사(14명) 인라인.
  의사 카드: <div class="doctor">
    - div.doctor_img > img src=".../doctor_NN.png"
    - div.doctor_title > span (진료과) / h4 > strong (이름) + 직책 텍스트
    - div.doctor_schedule > table:
        thead: 구분 / 월 / 화 / 수 / 목 / 금 / 토
        tbody: 2 행 (오전/오후), 각 6개 td
          span.schedule-b "진료"      → 외래 진료
          span.schedule-tb "내시경"   → 시술 (외래 아님, 제외)
          span.schedule-tr "격주휴무" → 제외
          span.schedule-tg "문의요망" → 제외
          빈 td                       → 휴진

external_id: DAEHAN-{doctor_NN}  (이미지 파일명 번호, 14개 고유)
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.daehanh.com"
DOCTORS_URL = f"{BASE_URL}/bbs/content.php?co_id=hosp_doctors"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 외래 진료로 인정할 클래스 (span)
OUTPATIENT_CLASS = "schedule-b"


class DaehanCrawler:
    """대한병원 크롤러 — 단일 통합 페이지 정적 HTML"""

    def __init__(self):
        self.hospital_code = "DAEHAN"
        self.hospital_name = "대한병원"
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
            resp = await client.get(DOCTORS_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[DAEHAN] 페이지 로드 실패: {e}")
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        self._cached_soup = soup
        return soup

    @staticmethod
    def _parse_title(doctor_title) -> tuple[str, str, str]:
        """div.doctor_title 에서 (진료과, 이름, 직책) 추출"""
        dept = ""
        name = ""
        position = ""
        if doctor_title is None:
            return dept, name, position
        span = doctor_title.find("span")
        if span:
            dept = span.get_text(strip=True)
        h4 = doctor_title.find("h4")
        if h4:
            strong = h4.find("strong")
            if strong:
                name = strong.get_text(strip=True)
                strong.extract()
            position = h4.get_text(" ", strip=True)
        return dept, name, position

    def _parse_schedule(self, table) -> list[dict]:
        if table is None:
            return []
        tbody = table.find("tbody") or table
        schedules: list[dict] = []
        for row in tbody.find_all("tr"):
            cells = row.find_all("td")
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
            # cells[1..6] 는 월~토
            for i, td in enumerate(cells[1:7]):
                span = td.find("span", class_=OUTPATIENT_CLASS)
                if span is None:
                    continue
                schedules.append({
                    "day_of_week": i,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return schedules

    def _parse_card(self, card) -> dict | None:
        title = card.find("div", class_="doctor_title")
        dept, name, position = self._parse_title(title)
        if not name:
            return None

        # 이미지 파일명 번호 추출 → external_id
        img = card.find("div", class_="doctor_img")
        img_tag = img.find("img") if img else None
        img_src = img_tag.get("src", "") if img_tag else ""
        m = re.search(r"(doctor_\d+)\.png", img_src)
        img_key = m.group(1) if m else f"name_{name}"

        table = None
        sched_wrap = card.find("div", class_="doctor_schedule")
        if sched_wrap:
            table = sched_wrap.find("table")
        schedules = self._parse_schedule(table)

        # 학력/경력 → notes
        notes = ""
        hist = card.find("div", class_="doctor_history")
        if hist:
            ul = hist.find("ul")
            if ul:
                items = [li.get_text(" ", strip=True) for li in ul.find_all("li")]
                notes = "\n".join(items)

        ext_id = f"DAEHAN-{img_key}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": name,
            "department": dept,
            "position": position,
            "specialty": "",
            "profile_url": DOCTORS_URL,
            "notes": notes,
            "schedules": schedules,
            "date_schedules": [],
        }

    def _parse_all_doctors(self, soup: BeautifulSoup) -> list[dict]:
        result: list[dict] = []
        seen: set[str] = set()
        for card in soup.find_all("div", class_="doctor"):
            # 카드는 반드시 doctor_title 포함
            if not card.find("div", class_="doctor_title"):
                continue
            doc = self._parse_card(card)
            if not doc:
                continue
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
        logger.info(f"[DAEHAN] 총 {len(result)}명")
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
        """개별 교수 조회 — 통합 페이지 1회 GET 후 해당 카드만 매칭"""
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

        async with self._make_client() as client:
            soup = await self._fetch_page(client)
        if soup is None:
            return empty

        doctors = self._parse_all_doctors(soup)
        for d in doctors:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                return {k: d.get(k, []) if k in ("schedules", "date_schedules") else d.get(k, "")
                        for k in ("staff_id", "name", "department", "position",
                                 "specialty", "profile_url", "notes",
                                 "schedules", "date_schedules")}
        return empty

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
