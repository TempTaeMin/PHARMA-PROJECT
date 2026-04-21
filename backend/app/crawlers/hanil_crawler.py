"""한일병원(KEPCO 의료재단 한일병원) 크롤러

병원 공식명: 한일병원
홈페이지: www.hanilmed.net
기술: 단일 정적 HTML (httpx + BeautifulSoup lxml)

구조:
  통합 페이지 1개 URL 에 전 진료과(30개) × 전 의사(92명) × 주간 스케줄 inline.
  진료과 구분: <h3> 태그
  의사 카드: <div class="docintrolist">
    - div.docleft: 이름/프로필 링크
      <img class="doc_pic" alt="{이름}사진">
      <a href="...dcCode={8자리}&dtCode={8자리}..."><img alt="{이름}프로필"></a>
    - div.docright: 전문분야 + 스케줄 table
      <ul>
        <li><span class="tit">의사명</span>{이름}</li>
        <li><span class="tit">전문분야</span>{분야}</li>
      </ul>
      <table>
        <thead> (2행: 월~토 colspan=2 / 12개 오전/오후) </thead>
        <tbody>
          <tr> 12개 td (img alt="외래진료"/"검사및수술"/빈) </tr>
          <tr><td colspan=12>{비고}</td></tr>
        </tbody>
      </table>

external_id: HANIL-{dcCode}
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.hanilmed.net"
SCHEDULE_URL = f"{BASE_URL}/portal/ScheMn/ScheMnSchedule.do?menuNo=20301000"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("14:00", "17:30")}

# "외래진료" 는 외래, "검사및수술" 은 외래 아님 → 스케줄 제외
OUTPATIENT_KEYWORDS = ("외래진료", "외래")
EXCLUDE_KEYWORDS = ("검사", "수술")

SLOT_MAP_12 = [
    (0, "morning"), (0, "afternoon"),
    (1, "morning"), (1, "afternoon"),
    (2, "morning"), (2, "afternoon"),
    (3, "morning"), (3, "afternoon"),
    (4, "morning"), (4, "afternoon"),
    (5, "morning"), (5, "afternoon"),
]


class HanilCrawler:
    """한일병원 크롤러 — 단일 통합 페이지 정적 HTML"""

    def __init__(self):
        self.hospital_code = "HANIL"
        self.hospital_name = "한일병원"
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
            resp = await client.get(SCHEDULE_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[HANIL] 페이지 로드 실패: {e}")
            return None
        # lxml 파서 — 이 사이트는 중첩 테이블이 많아 lxml이 html.parser 보다 정확
        try:
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception:
            soup = BeautifulSoup(resp.text, "html.parser")
        self._cached_soup = soup
        return soup

    @staticmethod
    def _is_outpatient_cell(cell) -> bool:
        """td 내부 img alt 가 '외래진료' 류면 True. '검사' 또는 '수술' 포함이면 False."""
        img = cell.find("img")
        if img is None:
            return False
        alt = (img.get("alt") or "").strip()
        if not alt:
            return False
        for kw in EXCLUDE_KEYWORDS:
            if kw in alt:
                return False
        for kw in OUTPATIENT_KEYWORDS:
            if kw in alt:
                return True
        return False

    def _parse_schedule(self, table) -> list[dict]:
        if table is None:
            return []
        # tbody 태그가 없는 경우도 있음 → table 직계 tr 중 td 12개인 것 찾기
        target_tr = None
        for tr in table.find_all("tr"):
            tds = tr.find_all("td", recursive=False)
            if len(tds) >= 12:
                target_tr = tr
                break
        if target_tr is None:
            return []
        cells = target_tr.find_all("td", recursive=False)
        schedules: list[dict] = []
        for i, td in enumerate(cells[:12]):
            if not self._is_outpatient_cell(td):
                continue
            dow, slot = SLOT_MAP_12[i]
            start, end = TIME_RANGES[slot]
            schedules.append({
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": start,
                "end_time": end,
                "location": "",
            })
        return schedules

    def _find_department_for_card(self, card) -> str:
        """카드 이전의 가장 가까운 h3 텍스트를 진료과로 사용"""
        h3 = card.find_previous("h3")
        if h3:
            return h3.get_text(" ", strip=True)
        return ""

    def _parse_card(self, card) -> dict | None:
        left = card.find("div", class_="docleft")
        right = card.find("div", class_="docright")
        if left is None or right is None:
            return None

        # 링크에서 dcCode, dtCode 추출
        link = left.find("a", href=re.compile(r"dcCode="))
        if link is None:
            return None
        href = link.get("href", "")
        m = re.search(r"dcCode=(\d+)", href)
        if not m:
            return None
        dc_code = m.group(1)
        dt_code = ""
        m2 = re.search(r"dtCode=(\d+)", href)
        if m2:
            dt_code = m2.group(1)

        # 이름: docright 내 <li><span class="tit">의사명</span>{이름}</li>
        name = ""
        position = ""
        specialty = ""
        ul = right.find("ul")
        if ul:
            for li in ul.find_all("li"):
                tit = li.find("span", class_="tit")
                label = tit.get_text(strip=True) if tit else ""
                # tit 제거 후 남은 텍스트
                if tit:
                    tit_copy = li.get_text(" ", strip=True).replace(label, "", 1).strip()
                else:
                    tit_copy = li.get_text(" ", strip=True)
                if label == "의사명":
                    name = tit_copy
                elif label == "전문분야":
                    specialty = tit_copy
                elif label == "진료과" and tit_copy:
                    # 대개 비어있으나 일부 채워져있을 수 있음
                    position = tit_copy

        if not name:
            # fallback: 이미지 alt "{이름}프로필" 에서 추출
            img_profile = link.find("img")
            if img_profile and img_profile.get("alt"):
                name = img_profile["alt"].replace("프로필", "").strip()
        if not name:
            return None

        table = right.find("table")
        schedules = self._parse_schedule(table)

        dept = self._find_department_for_card(card)
        profile_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        ext_id = f"HANIL-{dc_code}"

        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": name,
            "department": dept,
            "position": position,
            "specialty": specialty,
            "profile_url": profile_url,
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
            "_dc_code": dc_code,
            "_dt_code": dt_code,
        }

    def _parse_all_doctors(self, soup: BeautifulSoup) -> list[dict]:
        result: list[dict] = []
        seen: set[str] = set()
        for card in soup.find_all("div", class_="docintrolist"):
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
        logger.info(f"[HANIL] 총 {len(result)}명")
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
        """개별 교수 조회 — 통합 페이지 1회 GET 후 해당 카드만 파싱"""
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

        prefix = "HANIL-"
        dc_code = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not dc_code:
            return empty

        async with self._make_client() as client:
            soup = await self._fetch_page(client)
        if soup is None:
            return empty

        # 해당 dcCode 가진 링크 포함 카드만 찾기
        for card in soup.find_all("div", class_="docintrolist"):
            link = card.find("a", href=re.compile(rf"dcCode={dc_code}\b"))
            if not link:
                continue
            doc = self._parse_card(card)
            if not doc:
                continue
            return {k: doc.get(k, []) if k in ("schedules", "date_schedules") else doc.get(k, "")
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
