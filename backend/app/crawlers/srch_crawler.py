"""서울적십자병원(Seoul Red Cross Hospital) 크롤러

병원 공식명: 서울적십자병원 (대한적십자사)
홈페이지: www.rch.or.kr
기술: 정적 HTML (httpx + BeautifulSoup)

구조:
  진료과별 페이지 /web/rchseoul/contents/C{NN} (18개 과)
  각 진료과 페이지 안에 해당 과의 모든 의사 카드 + 스케줄 테이블 인라인.

  의사 카드: div.flex.flex-col.md:flex-row (border-b-dot 클래스 포함)
    - h3 > font > span.font-bold = 이름 / 일반 텍스트 = 직책 / span.text-orange = 세부 진료과
    - dl > dt "전문 분야" 다음 dd = 전문분야
    - table.table.text-center (스케줄):
        thead: 시간 / 월 / 화 / 수 / 목 / 금 / (토 또는 "-")
        tbody: 2 행 (오전/오후), 각 6개 td
          "진료" 텍스트 → 외래 진료
          "-" 또는 공백 → 휴진

external_id: SRCH-{C코드}-{이름} (의사별 개별 URL 없음)
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.rch.or.kr"
DEPT_URL = f"{BASE_URL}/web/rchseoul/contents/{{code}}"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}

# 진료과 코드 → 진료과 이름 (C01~C19, C03은 존재하지 않음 가능)
DEPARTMENTS = [
    ("C01", "내과"),
    ("C02", "신경과"),
    ("C04", "산부인과"),
    ("C05", "비뇨의학과"),
    ("C06", "정신건강의학과"),
    ("C07", "정형외과"),
    ("C08", "외과"),
    ("C09", "안과"),
    ("C10", "마취통증의학과"),
    ("C11", "영상의학과"),
    ("C12", "병리과"),
    ("C13", "피부과"),
    ("C14", "이비인후과"),
    ("C15", "가정의학과"),
    ("C16", "진단검사의학과"),
    ("C17", "소아청소년과"),
    ("C18", "응급의학과"),
    ("C19", "치과"),
]


class SrchCrawler:
    """서울적십자병원 크롤러 — 진료과별 페이지 파싱"""

    def __init__(self):
        self.hospital_code = "SRCH"
        self.hospital_name = "서울적십자병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        self._cached_data: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    def _parse_schedule_table(self, table) -> list[dict]:
        if table is None:
            return []
        thead = table.find("thead")
        if thead is None:
            return []
        header_cells = thead.find_all(["th", "td"])
        col_to_dow: dict[int, int] = {}
        for ci, cell in enumerate(header_cells):
            t = cell.get_text(" ", strip=True)
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
            label = cells[0].get_text(" ", strip=True)
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
                text = cell.get_text(" ", strip=True)
                if "진료" not in text:
                    continue
                schedules.append({
                    "day_of_week": col_to_dow[ci],
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return schedules

    def _parse_doctor_card(self, card, dept_code: str, dept_name: str) -> dict | None:
        h3 = card.find("h3")
        if h3 is None:
            return None
        name_span = h3.find("span", class_=re.compile(r"font-bold"))
        if name_span is None:
            return None
        name = name_span.get_text(" ", strip=True)
        if not name:
            return None

        # 세부 진료과 — text-orange span
        sub_dept = ""
        orange = h3.find("span", class_=re.compile(r"text-orange"))
        if orange:
            sub_dept = orange.get_text(" ", strip=True)

        # 직책 — h3 전체 텍스트에서 이름/세부과 제거
        full = h3.get_text(" ", strip=True)
        position = full.replace(name, "", 1)
        if sub_dept:
            position = position.replace(sub_dept, "", 1)
        position = re.sub(r"\s+", " ", position).strip()

        # 전문분야 — dl 안에 dt "전문 분야" 다음 dd
        specialty = ""
        for dl in card.find_all("dl"):
            dt = dl.find("dt")
            if dt and "전문" in dt.get_text():
                dd = dl.find("dd")
                if dd:
                    specialty = dd.get_text(" ", strip=True)
                break

        table = card.find("table", class_=re.compile(r"table"))
        schedules = self._parse_schedule_table(table)

        ext_id = f"SRCH-{dept_code}-{name}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": name,
            "department": sub_dept or dept_name,
            "position": position,
            "specialty": specialty,
            "profile_url": DEPT_URL.format(code=dept_code),
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
        }

    async def _fetch_dept(self, client: httpx.AsyncClient, code: str, name: str) -> list[dict]:
        try:
            resp = await client.get(DEPT_URL.format(code=code))
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SRCH] {name}({code}) 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")

        doctors: list[dict] = []
        seen: set[str] = set()
        # 의사 카드: border-b-dot 클래스 가진 flex-col 컨테이너
        for card in soup.find_all("div", class_=re.compile(r"border-b-dot")):
            if not card.find("h3"):
                continue
            if not card.find("table"):
                continue
            doc = self._parse_doctor_card(card, code, name)
            if not doc:
                continue
            if doc["external_id"] in seen:
                continue
            seen.add(doc["external_id"])
            doctors.append(doc)

        logger.info(f"[SRCH] {name}({code}): {len(doctors)}명")
        return doctors

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with self._make_client() as client:
            tasks = [
                asyncio.create_task(self._fetch_dept(client, code, name))
                for code, name in DEPARTMENTS
            ]
            for coro in asyncio.as_completed(tasks):
                docs = await coro
                for d in docs:
                    if d["external_id"] not in all_doctors:
                        all_doctors[d["external_id"]] = d

        result = list(all_doctors.values())
        logger.info(f"[SRCH] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        return [{"code": code, "name": name} for code, name in DEPARTMENTS]

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
        """개별 교수 조회 — external_id 에서 C코드 추출 후 해당 진료과 1개만 조회"""
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

        # external_id = SRCH-{C코드}-{이름}
        m = re.match(r"SRCH-(C\d{2})-(.+)$", staff_id)
        if not m:
            return empty
        code = m.group(1)
        dept_name = dict(DEPARTMENTS).get(code, "")

        async with self._make_client() as client:
            docs = await self._fetch_dept(client, code, dept_name)

        for d in docs:
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
