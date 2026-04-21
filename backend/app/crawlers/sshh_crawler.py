"""서울성심병원(Seoul Sungsim Hospital) 크롤러

병원 공식명: 서울성심병원
홈페이지: www.sshosp.co.kr
기술: 단일 정적 HTML (httpx + BeautifulSoup)

구조:
  전체 진료과/의사가 `/clinic/schedule.html` (uid 없이) 한 페이지에 모두 렌더링.
  `div.content-text-bx` 블록 = 진료과 1개
    - `p.title` = 진료과 이름
    - `table.table_1 tbody tr` = 의사 데이터 (2행 1세트: 오전 / 오후)
      첫 행의 `td.medical-wrap` (rowspan=2) 안에 이름·직책·사진
      이후 td 6개: 월~토
        `span.dot`        = 진료(외래)
        `span.etc` + 텍스트 = 수술/문의/등 (외래 아님)
        빈 셀             = 휴진

external_id: SSHH-{mxxxxxxx}
  — img src 의 `_m0173293_` 패턴에서 추출. 동명이인 안전.
  폴백: `SSHH-{dept}-{name}` (이미지 없을 때)
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.sshosp.co.kr"
TIMETABLE_URL = f"{BASE_URL}/clinic/schedule.html"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 헤더 요일 순서(월~토). 사이트 구조상 고정이지만 안전하게 텍스트 매핑 병행.
DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}

DOCTOR_ID_RE = re.compile(r"_(m\d{6,})_")


class SshhCrawler:
    """서울성심병원 크롤러 — 단일 페이지 정적 HTML"""

    def __init__(self):
        self.hospital_code = "SSHH"
        self.hospital_name = "서울성심병원"
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
            logger.error(f"[SSHH] 페이지 로드 실패: {e}")
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        self._cached_soup = soup
        return soup

    @staticmethod
    def _extract_doctor_id(img_src: str) -> str:
        m = DOCTOR_ID_RE.search(img_src or "")
        return m.group(1) if m else ""

    def _cell_is_open(self, cell) -> bool:
        """진료(외래) 셀 판정: span.dot 존재."""
        if cell is None:
            return False
        return cell.select_one("span.dot") is not None

    def _parse_doctor_pair(self, tr_am, tr_pm) -> dict | None:
        """2행(오전/오후) 세트 → 의사 1명 dict."""
        wrap = tr_am.select_one("td.medical-wrap")
        if wrap is None:
            return None
        name_el = wrap.select_one("p.name")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            return None
        pos_el = wrap.select_one("p.position")
        position = pos_el.get_text(strip=True) if pos_el else ""
        img = wrap.select_one("img")
        img_src = img.get("src", "") if img else ""
        photo_url = ""
        if img_src:
            photo_url = img_src if img_src.startswith("http") else f"{BASE_URL}{img_src}"
        doctor_id = self._extract_doctor_id(img_src)

        schedules: list[dict] = []
        # AM 행: medical-wrap(1) + am라벨(1) + 월~토 6칸
        am_cells = tr_am.find_all("td")
        # am_cells[0]=wrap, am_cells[1]=오전, am_cells[2..7]=월..토
        for di, cell in enumerate(am_cells[2:8]):
            if self._cell_is_open(cell):
                start, end = TIME_RANGES["morning"]
                schedules.append({
                    "day_of_week": di,
                    "time_slot": "morning",
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })

        if tr_pm is not None:
            pm_cells = tr_pm.find_all("td")
            # pm_cells[0]=오후, pm_cells[1..6]=월..토
            for di, cell in enumerate(pm_cells[1:7]):
                if self._cell_is_open(cell):
                    start, end = TIME_RANGES["afternoon"]
                    schedules.append({
                        "day_of_week": di,
                        "time_slot": "afternoon",
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                    })

        return {
            "name": name,
            "position": position,
            "doctor_id": doctor_id,
            "photo_url": photo_url,
            "schedules": schedules,
        }

    def _parse_dept_block(self, block) -> list[dict]:
        """1개 진료과 블록(div.content-text-bx) → 의사 리스트"""
        title_el = block.select_one("p.title")
        dept = title_el.get_text(strip=True) if title_el else ""
        table = block.select_one("table.table_1")
        if table is None:
            return []
        tbody = table.find("tbody")
        if tbody is None:
            return []
        rows = tbody.find_all("tr", recursive=False)

        doctors: list[dict] = []
        i = 0
        while i < len(rows):
            row = rows[i]
            if row.select_one("td.medical-wrap"):
                tr_pm = rows[i + 1] if (i + 1) < len(rows) else None
                doc = self._parse_doctor_pair(row, tr_pm)
                if doc:
                    doc["department"] = dept
                    doctors.append(doc)
                i += 2
            else:
                i += 1
        return doctors

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            soup = await self._fetch_page(client)

        if soup is None:
            self._cached_data = []
            return []

        result: list[dict] = []
        seen: set[str] = set()
        for block in soup.select("div.content-text-bx"):
            for doc in self._parse_dept_block(block):
                did = doc.get("doctor_id") or f"{doc['department']}-{doc['name']}"
                ext_id = f"SSHH-{did}"
                if ext_id in seen:
                    continue
                seen.add(ext_id)
                doc["staff_id"] = ext_id
                doc["external_id"] = ext_id
                doc["profile_url"] = TIMETABLE_URL
                doc["specialty"] = ""
                doc["notes"] = ""
                doc["date_schedules"] = []
                result.append(doc)

        logger.info(f"[SSHH] 총 {len(result)}명")
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
        """개별 교수 조회 — 1회 GET 후 해당 셀만 파싱 (skill 규칙 #7 준수)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, [] if k in ("schedules", "date_schedules") else "")
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}
            return empty

        # 1회 페이지 로드 후 해당 의사만 파싱 — 전체 파싱도 가볍지만 규칙 준수를 위해 타겟 한정
        async with self._make_client() as client:
            soup = await self._fetch_page(client)
        if soup is None:
            return empty

        prefix = "SSHH-"
        raw_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not raw_id:
            return empty

        # 이미지 src 로 타겟 매칭 (주 경로)
        target_img = soup.select_one(f'img[src*="_{raw_id}_"]') if raw_id.startswith("m") else None
        target_block = None
        target_am = None

        if target_img is not None:
            wrap = target_img.find_parent("td", class_="medical-wrap")
            if wrap is not None:
                target_am = wrap.find_parent("tr")
                target_block = target_am.find_parent("div", class_="content-text-bx") if target_am else None

        # 폴백 경로: {dept}-{name} 포맷
        if target_block is None and "-" in raw_id:
            dept_name, doc_name = raw_id.split("-", 1)
            for blk in soup.select("div.content-text-bx"):
                t = blk.select_one("p.title")
                if not t or t.get_text(strip=True) != dept_name:
                    continue
                for wrap in blk.select("td.medical-wrap"):
                    nm = wrap.select_one("p.name")
                    if nm and nm.get_text(strip=True) == doc_name:
                        target_am = wrap.find_parent("tr")
                        target_block = blk
                        break
                if target_block is not None:
                    break

        if target_block is None or target_am is None:
            return empty

        tbody = target_block.find("tbody")
        rows = tbody.find_all("tr", recursive=False) if tbody else []
        try:
            idx = rows.index(target_am)
        except ValueError:
            return empty
        tr_pm = rows[idx + 1] if (idx + 1) < len(rows) else None

        doc = self._parse_doctor_pair(target_am, tr_pm)
        if not doc:
            return empty
        dept_title = target_block.select_one("p.title")
        doc["department"] = dept_title.get_text(strip=True) if dept_title else ""

        return {
            "staff_id": staff_id,
            "name": doc["name"],
            "department": doc["department"],
            "position": doc["position"],
            "specialty": "",
            "profile_url": TIMETABLE_URL,
            "notes": "",
            "schedules": doc["schedules"],
            "date_schedules": [],
        }

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
