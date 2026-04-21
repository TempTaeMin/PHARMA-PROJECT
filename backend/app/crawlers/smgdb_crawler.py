"""서울특별시 동부병원(Seoul Metropolitan Government Dongbu Hospital) 크롤러

병원 공식명: 서울특별시 동부병원
홈페이지: www.dbhosp.go.kr
기술: 단일 JSP 정적 HTML (httpx + BeautifulSoup)

구조:
  진료시간표: /clinic/clinic_timetable2.jsp
    — 하나의 `table.datacol-type02.th-type` 에 전체 의사가 담겨 있음
    — 한 행(tr)이 한 명의 의사.
    — 진료과 셀은 rowspan 으로 여러 의사를 묶음
      * td 수가 6이면 첫 td = 진료과, 이후 [이름, 오전, 오후, 전문, 주요이력]
      * td 수가 5이면 rowspan 진료과 계승, td = [이름, 오전, 오후, 전문, 주요이력]
    — "월,화,수,목" / "월~금" / "월,목" / "-" 같은 요일 토큰 파싱
    — colspan 이 있거나 첫 셀에 "내시경" 주석이 오는 행은 스케줄 row 아님 → 스킵

external_id: SMGDB-{dept}-{name}  (의사 ID 없음)
  개별 조회 URL 없음 → `crawl_doctor_schedule` 는 시간표 페이지 1회 GET 후 해당 row 만 파싱.
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.dbhosp.go.kr"
TIMETABLE_URL = f"{BASE_URL}/clinic/clinic_timetable2.jsp"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
DAY_ORDER = ["월", "화", "수", "목", "금", "토", "일"]


def _expand_day_range(token: str) -> list[int]:
    """요일 토큰 → day_of_week 인덱스 리스트"""
    token = (token or "").strip()
    if not token or token in {"-", "휴진", "예약"}:
        return []
    # 괄호 안 부가 설명 제거
    token = re.sub(r"\([^)]*\)", "", token)
    token = re.sub(r"\s+", "", token)
    indices: set[int] = set()
    for part in token.split(","):
        part = part.strip()
        if not part:
            continue
        if "~" in part:
            start, _, end = part.partition("~")
            if start in DAY_INDEX and end in DAY_INDEX:
                si, ei = DAY_INDEX[start], DAY_INDEX[end]
                if si <= ei:
                    for i in range(si, ei + 1):
                        indices.add(i)
                continue
        # 단일 요일 or 다중 연속 문자(예: "월화수")
        matched = False
        for ch in part:
            if ch in DAY_INDEX:
                indices.add(DAY_INDEX[ch])
                matched = True
        if not matched:
            # 알 수 없는 토큰 — 무시
            continue
    return sorted(indices)


class SmgdbCrawler:
    """서울특별시 동부병원 크롤러"""

    def __init__(self):
        self.hospital_code = "SMGDB"
        self.hospital_name = "서울특별시 동부병원"
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
            logger.error(f"[SMGDB] 페이지 로드 실패: {e}")
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        self._cached_soup = soup
        return soup

    @staticmethod
    def _clean_dept(raw: str) -> str:
        """'내과\nT.920-9120 9129' → '내과'"""
        first = raw.split("\n")[0].strip()
        # 'T.xxxx' 접두 제거
        first = re.sub(r"T\.[\d \-]+", "", first).strip()
        return first

    @staticmethod
    def _clean_name(raw: str) -> str:
        """'최선아\n(유지희)' → '최선아'"""
        name = raw.split("\n")[0].strip()
        name = re.sub(r"\([^)]*\)", "", name).strip()
        return name

    def _parse_table(self, table) -> list[dict]:
        """시간표 테이블 → 의사 리스트"""
        tbody = table.find("tbody") or table
        rows = tbody.find_all("tr", recursive=False)

        doctors: list[dict] = []
        current_dept = ""
        seen: set[str] = set()

        for tr in rows:
            tds = tr.find_all("td", recursive=False)
            if not tds:
                continue
            # 노트/주석 행 스킵 (colspan 있거나 첫 td 가 colspan)
            if any(td.has_attr("colspan") and td["colspan"] != "1" for td in tds):
                # 다만 '진료과 셀 전체가 '-' 인 플레이스홀더' 는 tds 개수만 보면 됨 → colspan 로는 판단 불가
                # 여기선 colspan 가 있으면 주석행으로 간주
                continue

            idx_offset = 0
            if len(tds) >= 6:
                # 새 진료과 + 의사 행
                dept_raw = tds[0].get_text("\n", strip=True)
                current_dept = self._clean_dept(dept_raw)
                idx_offset = 1
            elif len(tds) == 5:
                # rowspan 으로 이어진 진료과 + 의사 행
                idx_offset = 0
            else:
                continue

            name_td = tds[idx_offset]
            am_td = tds[idx_offset + 1] if len(tds) > idx_offset + 1 else None
            pm_td = tds[idx_offset + 2] if len(tds) > idx_offset + 2 else None
            spec_td = tds[idx_offset + 3] if len(tds) > idx_offset + 3 else None
            notes_td = tds[idx_offset + 4] if len(tds) > idx_offset + 4 else None

            name_raw = name_td.get_text("\n", strip=True)
            name = self._clean_name(name_raw)
            if not name or name == "-":
                continue

            am_text = am_td.get_text(" ", strip=True) if am_td else ""
            pm_text = pm_td.get_text(" ", strip=True) if pm_td else ""
            specialty = spec_td.get_text(" ", strip=True).replace("\n", " ") if spec_td else ""
            notes = notes_td.get_text(" ", strip=True).replace("\n", " ") if notes_td else ""

            schedules: list[dict] = []
            for dow in _expand_day_range(am_text):
                s, e = TIME_RANGES["morning"]
                schedules.append({"day_of_week": dow, "time_slot": "morning",
                                  "start_time": s, "end_time": e, "location": ""})
            for dow in _expand_day_range(pm_text):
                s, e = TIME_RANGES["afternoon"]
                schedules.append({"day_of_week": dow, "time_slot": "afternoon",
                                  "start_time": s, "end_time": e, "location": ""})

            ext_id = f"SMGDB-{current_dept}-{name}"
            if ext_id in seen:
                continue
            seen.add(ext_id)
            doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": current_dept,
                "position": "",
                "specialty": specialty,
                "profile_url": TIMETABLE_URL,
                "photo_url": "",
                "notes": notes,
                "schedules": schedules,
                "date_schedules": [],
            })
        return doctors

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            soup = await self._fetch_page(client)
        if soup is None:
            self._cached_data = []
            return []

        table = soup.select_one("table.datacol-type02")
        if table is None:
            logger.warning("[SMGDB] 시간표 테이블 미발견")
            self._cached_data = []
            return []

        result = self._parse_table(table)
        logger.info(f"[SMGDB] 총 {len(result)}명")
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
        """개별 교수 조회 — 시간표 페이지 1회 GET 후 해당 의사만 추출"""
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

        # 시간표 페이지는 전체가 단일 테이블이라 "개별" 의 개념이 네트워크 레벨로는 불가능.
        # 대신 1회 GET 후 인메모리 파싱은 매우 저렴하므로 규칙 위반 아님.
        async with self._make_client() as client:
            soup = await self._fetch_page(client)
        if soup is None:
            return empty

        table = soup.select_one("table.datacol-type02")
        if table is None:
            return empty
        all_docs = self._parse_table(table)
        for d in all_docs:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                return {k: d.get(k, [] if k in ("schedules","date_schedules") else "")
                        for k in ("staff_id","name","department","position",
                                 "specialty","profile_url","notes",
                                 "schedules","date_schedules")}
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
