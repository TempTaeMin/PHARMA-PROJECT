"""인제대학교 부산백병원(Inje University Busan Paik Hospital) 크롤러

병원 공식명: 인제대학교 부산백병원
홈페이지: www.paik.ac.kr/busan
기술: 서버사이드 JSP 정적 HTML (httpx + BeautifulSoup)

구조 (sgpaik / ispaik 와 동일 플랫폼 — 경로만 /sanggye,/ilsan → /busan, menuNo 만 다름):
  진료시간표 (전체): /busan/user/department/schedule.do?menuNo=800154&searchDepartment={any}&searchYn=Y
    — searchDepartment 에 유효값 + searchYn=Y 파라미터가 있으면 전체 진료과 테이블이 한 번에 렌더링됨
    — `h2.tit-point.mt40` = 진료과 이름
    — 바로 뒤 `table.reply_tbl` = 진료과의 시간표
    — 테이블 행: 의사명 + 월~토(6컬럼) + 전문분야
      * 셀 텍스트: "종일"|"오전"|"오후"|"-"|"특진" 등
      * "종일" → 오전+오후 둘 다 기록
      * "오전"/"오후" → 해당 슬롯만
      * "-" 또는 빈 셀 → 휴진

  개인 프로필: /busan/user/doctor/view.do?doctorId={ID}&menuNo=300007
    — `p.big` = 이름, `p.small > span` = 진료과
    — `div.pro-part > p.conte` = 전문분야
    — `table.time-table` 내 `div.checked` = 진료 슬롯

external_id: PAIKBS-{doctorId}
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.paik.ac.kr"
SCHEDULE_URL = f"{BASE_URL}/busan/user/department/schedule.do"
DOCTOR_VIEW_URL = f"{BASE_URL}/busan/user/doctor/view.do"

# 전체 진료과 한 번에 조회하는 고정 파라미터 (searchDepartment 값은 유효한 진료과 ID 아무거나)
SCHEDULE_PARAMS = {"menuNo": "800154", "searchDepartment": "1", "searchYn": "Y"}

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}

DOCTOR_ID_RE = re.compile(r"doctorId=(\d+)")

# 셀 텍스트 → 슬롯 매핑
SLOT_AM_TOKENS = {"오전"}
SLOT_PM_TOKENS = {"오후"}
SLOT_ALL_TOKENS = {"종일", "오전/오후", "오전·오후"}
# "특진" 등 기타 텍스트도 진료로 간주 (휴진/-/공백 제외)


class PaikbsCrawler:
    """인제대학교 부산백병원 크롤러"""

    def __init__(self):
        self.hospital_code = "PAIKBS"
        self.hospital_name = "인제대학교 부산백병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/busan/",
        }
        self._cached_data: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    @staticmethod
    def _cell_slots(text: str) -> list[str]:
        """셀 텍스트 → 해당되는 슬롯 리스트"""
        t = (text or "").strip()
        if not t or t == "-" or t == "휴진":
            return []
        if t in SLOT_ALL_TOKENS:
            return ["morning", "afternoon"]
        slots: list[str] = []
        if any(tok in t for tok in SLOT_AM_TOKENS):
            slots.append("morning")
        if any(tok in t for tok in SLOT_PM_TOKENS):
            slots.append("afternoon")
        if slots:
            return slots
        # 기타 텍스트("특진", "예약" 등) → 외래로 간주, 오전+오후 표시
        return ["morning", "afternoon"]

    def _parse_schedule_page(self, soup: BeautifulSoup) -> list[dict]:
        """전체 진료과 시간표 페이지 → 의사 리스트"""
        doctors: dict[str, dict] = {}  # external_id → doctor dict (중복 방지)

        for h2 in soup.select("h2.tit-point.mt40"):
            dept_name = h2.get_text(strip=True)
            table = h2.find_next("table", class_="reply_tbl")
            if table is None:
                continue
            # 헤더 요일 → 컬럼 인덱스
            thead = table.find("thead")
            if thead is None:
                continue
            ths = thead.find_all("th")
            col_to_dow: dict[int, int] = {}
            for ci, th in enumerate(ths):
                t = th.get_text(strip=True)
                if t in DAY_INDEX:
                    col_to_dow[ci] = DAY_INDEX[t]
            if not col_to_dow:
                continue

            for tr in table.select("tbody tr"):
                tds = tr.find_all("td", recursive=False)
                if len(tds) < 2:
                    continue
                # 첫 td: 의사명 + 링크(doctorId)
                name_td = tds[0]
                anchor = name_td.find("a")
                name = ""
                doctor_id = ""
                profile_url = ""
                if anchor:
                    name = anchor.get_text(strip=True)
                    href = anchor.get("href", "") or ""
                    m = DOCTOR_ID_RE.search(href)
                    if m:
                        doctor_id = m.group(1)
                    if href.startswith("/"):
                        profile_url = BASE_URL + href
                    elif href.startswith("http"):
                        profile_url = href
                if not name:
                    name = name_td.get_text(" ", strip=True)
                if not name or not doctor_id:
                    continue

                # 전문분야: 마지막 td (헤더 '전문분야')
                specialty = ""
                if len(tds) >= 2:
                    specialty = tds[-1].get_text(" ", strip=True)

                schedules: list[dict] = []
                for ci, td in enumerate(tds):
                    if ci not in col_to_dow:
                        continue
                    text = td.get_text(" ", strip=True)
                    for slot in self._cell_slots(text):
                        start, end = TIME_RANGES[slot]
                        schedules.append({
                            "day_of_week": col_to_dow[ci],
                            "time_slot": slot,
                            "start_time": start,
                            "end_time": end,
                            "location": "",
                        })

                ext_id = f"PAIKBS-{doctor_id}"
                if ext_id in doctors:
                    # 동일 의사가 여러 진료과(클리닉)에 등장 시 첫 진료과의 전문분야/스케줄 우선
                    continue
                doctors[ext_id] = {
                    "staff_id": ext_id,
                    "external_id": ext_id,
                    "doctor_id": doctor_id,
                    "name": name,
                    "department": dept_name,
                    "position": "",
                    "specialty": specialty,
                    "profile_url": profile_url or f"{DOCTOR_VIEW_URL}?doctorId={doctor_id}&menuNo=300007",
                    "photo_url": "",
                    "notes": "",
                    "schedules": schedules,
                    "date_schedules": [],
                }
        return list(doctors.values())

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            try:
                resp = await client.get(SCHEDULE_URL, params=SCHEDULE_PARAMS)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[PAIKBS] 시간표 페이지 실패: {e}")
                self._cached_data = []
                return []
            soup = BeautifulSoup(resp.text, "html.parser")

        result = self._parse_schedule_page(soup)
        logger.info(f"[PAIKBS] 총 {len(result)}명")
        self._cached_data = result
        return result

    def _parse_doctor_profile(self, soup: BeautifulSoup, doctor_id: str) -> dict:
        """개인 프로필 페이지 → 의사 dict"""
        name_el = soup.select_one("div.pro-name p.big")
        name = name_el.get_text(strip=True) if name_el else ""
        dept_el = soup.select_one("div.pro-name p.small span")
        department = dept_el.get_text(strip=True) if dept_el else ""
        spec_el = soup.select_one("div.pro-part p.conte")
        specialty = spec_el.get_text(" ", strip=True) if spec_el else ""

        schedules: list[dict] = []
        table = soup.select_one("table.time-table")
        if table is not None:
            thead = table.find("thead")
            col_to_dow: dict[int, int] = {}
            if thead:
                for ci, th in enumerate(thead.find_all("th")):
                    t = th.get_text(strip=True)
                    if t in DAY_INDEX:
                        col_to_dow[ci] = DAY_INDEX[t]
            tbody = table.find("tbody")
            rows = tbody.find_all("tr") if tbody else []
            for tr in rows:
                tds = tr.find_all("td")
                if not tds:
                    continue
                label = tds[0].get_text(strip=True)
                if label == "오전":
                    slot = "morning"
                elif label == "오후":
                    slot = "afternoon"
                else:
                    continue
                start, end = TIME_RANGES[slot]
                for ci, td in enumerate(tds):
                    if ci not in col_to_dow:
                        continue
                    if td.select_one("div.checked") is not None:
                        schedules.append({
                            "day_of_week": col_to_dow[ci],
                            "time_slot": slot,
                            "start_time": start,
                            "end_time": end,
                            "location": "",
                        })

        return {
            "staff_id": f"PAIKBS-{doctor_id}",
            "external_id": f"PAIKBS-{doctor_id}",
            "doctor_id": doctor_id,
            "name": name,
            "department": department,
            "position": "",
            "specialty": specialty,
            "profile_url": f"{DOCTOR_VIEW_URL}?doctorId={doctor_id}&menuNo=300007",
            "photo_url": "",
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
        }

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
        """개별 교수 조회 — 개인 프로필 페이지 1회 GET (skill 규칙 #7)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, [] if k in ("schedules","date_schedules") else "")
                            for k in ("staff_id","name","department","position",
                                     "specialty","profile_url","notes",
                                     "schedules","date_schedules")}
            return empty

        prefix = "PAIKBS-"
        doctor_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not doctor_id:
            return empty

        async with self._make_client() as client:
            try:
                resp = await client.get(DOCTOR_VIEW_URL, params={"doctorId": doctor_id, "menuNo": "300007"})
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[PAIKBS] 개별 조회 실패 {staff_id}: {e}")
                return empty
            soup = BeautifulSoup(resp.text, "html.parser")

        doc = self._parse_doctor_profile(soup, doctor_id)
        return {k: doc.get(k, [] if k in ("schedules","date_schedules") else "")
                for k in ("staff_id","name","department","position",
                         "specialty","profile_url","notes",
                         "schedules","date_schedules")}

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
