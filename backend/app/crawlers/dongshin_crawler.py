"""동신병원(Dongshin Hospital) 크롤러

병원 공식명: 동신병원 (서울 서대문구 홍은)
홈페이지: www.dshospital.co.kr
기술: 정적 HTML (httpx + BeautifulSoup)

구조:
  단일 페이지 /cmnt/25978/contentInfo.do 에 전체 진료시간표 테이블이 있음.
  한 의사당 2행(오전/오후). 행 구성:
    [진료과(rs=N)] [직책/진료과 (rs=2)] [이름(rs=2)] [오전/오후] [월] [화] [수] [목] [금] [토(cs=5 혹은 1주~5주 5셀)]
  진료 표시 텍스트: "●", "수술", "내시경", "검진", "투" 등 → 진료 / "-" 또는 빈셀 → 휴진

external_id: DONGSHIN-{md5(dept+name)[:10]}
"""
import re
import hashlib
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.dshospital.co.kr"
SCHEDULE_URL = f"{BASE_URL}/cmnt/25978/contentInfo.do"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("14:00", "17:00")}

_NON_WORKING = {"", "-", "―", "x", "X", "X"}


def _is_working(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if t in _NON_WORKING:
        return False
    # 하이픈만 / 공백만 이면 휴진
    if re.fullmatch(r"[-\s]+", t):
        return False
    return True


class DongshinCrawler:
    def __init__(self):
        self.hospital_code = "DONGSHIN"
        self.hospital_name = "동신병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": BASE_URL,
        }
        self._cached_data: list[dict] | None = None

    @staticmethod
    def _mk_id(dept: str, name: str) -> str:
        raw = f"{dept}|{name}".encode("utf-8")
        return hashlib.md5(raw).hexdigest()[:10]

    def _parse_schedule_table(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("table")
        if table is None:
            return []

        rows = table.select("tbody tr") or table.select("tr")
        # 헤더/서브헤더 2행 스킵
        data_rows = rows[2:]

        doctors: list[dict] = []
        current_dept = ""
        i = 0
        while i < len(data_rows):
            row = data_rows[i]
            cells = row.select("td, th")
            if not cells:
                i += 1
                continue

            idx = 0
            # 진료과 셀: rowspan >= 4 (최소 의사 2명 × 2행)
            first = cells[0]
            first_rs = int(first.get("rowspan", "1"))
            if first_rs >= 4:
                current_dept = first.get_text(" ", strip=True)
                idx = 1

            # 의사 시작 행은 section(rs=2) + name(rs=2) 이 선두
            if idx + 1 >= len(cells):
                i += 1
                continue

            section_cell = cells[idx]
            name_cell = cells[idx + 1]
            if int(section_cell.get("rowspan", "1")) != 2 or int(name_cell.get("rowspan", "1")) != 2:
                i += 1
                continue

            section_text = section_cell.get_text(" ", strip=True)
            name = name_cell.get_text(" ", strip=True)

            # 빈 이름 또는 "-" 이면 스킵
            if not name or name in ("-", "―"):
                i += 2
                continue

            # 직책/specialty 분리: "1내과 의무원장 (내분비내과)" → position="의무원장", specialty="내분비내과"
            position = ""
            specialty = ""
            m_spec = re.search(r"\(([^)]+)\)", section_text)
            if m_spec:
                specialty = m_spec.group(1).strip()
                sec_wo_spec = section_text.replace(m_spec.group(0), "").strip()
            else:
                sec_wo_spec = section_text
            m_pos = re.search(
                r"(의무원장|진료부원장|진료원장|부원장|원장|진료부장|주임과장|부과장|과장|전문의|센터장|팀장)",
                sec_wo_spec,
            )
            if m_pos:
                position = m_pos.group(1)

            # 오전 행 날짜 셀
            morning_day_cells = cells[idx + 2 + 1:]  # section, name, slot 이후
            # 오후 행
            afternoon_day_cells: list = []
            if i + 1 < len(data_rows):
                r2 = data_rows[i + 1]
                r2_cells = r2.select("td, th")
                # 오후 행: [slot, 월, 화, 수, 목, 금, 토...]
                if r2_cells and r2_cells[0].get_text(strip=True) in ("오후", ""):
                    afternoon_day_cells = r2_cells[1:]

            def parse_days(day_cells) -> list[bool]:
                """월~토(6) 반환. 토가 colspan=5 이면 단일 판정, 아니면 5셀 중 하나라도 진료면 True."""
                flags = [False] * 6
                # 월~금
                for dow in range(5):
                    if dow < len(day_cells):
                        flags[dow] = _is_working(day_cells[dow].get_text(" ", strip=True))
                # 토
                rest = day_cells[5:]
                if not rest:
                    flags[5] = False
                elif len(rest) == 1:
                    flags[5] = _is_working(rest[0].get_text(" ", strip=True))
                else:
                    # 5주 분할 — 하나라도 진료면 True
                    flags[5] = any(_is_working(c.get_text(" ", strip=True)) for c in rest)
                return flags

            morning_flags = parse_days(morning_day_cells)
            afternoon_flags = parse_days(afternoon_day_cells)

            schedules: list[dict] = []
            for dow, on in enumerate(morning_flags):
                if on:
                    s, e = TIME_RANGES["morning"]
                    schedules.append({
                        "day_of_week": dow, "time_slot": "morning",
                        "start_time": s, "end_time": e, "location": "",
                    })
            for dow, on in enumerate(afternoon_flags):
                if on:
                    s, e = TIME_RANGES["afternoon"]
                    schedules.append({
                        "day_of_week": dow, "time_slot": "afternoon",
                        "start_time": s, "end_time": e, "location": "",
                    })

            # 진료과 라벨 정리 (e.g. "1내과 의무원장" → 정식 과명 유추)
            dept_display = current_dept or ""

            ext_id = f"{self.hospital_code}-{self._mk_id(dept_display, name)}"
            doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept_display,
                "position": position,
                "specialty": specialty or section_text,
                "profile_url": SCHEDULE_URL,
                "notes": "",
                "schedules": schedules,
                "date_schedules": [],
            })
            i += 2

        return doctors

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            try:
                resp = await client.get(SCHEDULE_URL)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[DONGSHIN] 진료시간표 실패: {e}")
                return []

        result = self._parse_schedule_table(resp.text)
        # external_id 중복 제거
        seen = {}
        for d in result:
            seen.setdefault(d["external_id"], d)
        result = list(seen.values())
        logger.info(f"[DONGSHIN] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        seen = {}
        for d in data:
            dept = d["department"]
            if dept and dept not in seen:
                seen[dept] = {"code": dept, "name": dept}
        return list(seen.values())

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
        """개별 조회 — 전체 스케줄이 단일 URL 이므로 1회 GET 후 필터"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            source = self._cached_data
        else:
            async with httpx.AsyncClient(
                headers=self.headers, timeout=30, follow_redirects=True, verify=False,
            ) as client:
                try:
                    resp = await client.get(SCHEDULE_URL)
                    resp.raise_for_status()
                except Exception as e:
                    logger.warning(f"[DONGSHIN] 개별 조회 실패 {staff_id}: {e}")
                    return empty
            source = self._parse_schedule_table(resp.text)

        for d in source:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                return {
                    "staff_id": staff_id,
                    "name": d.get("name", ""),
                    "department": d.get("department", ""),
                    "position": d.get("position", ""),
                    "specialty": d.get("specialty", ""),
                    "profile_url": d.get("profile_url", ""),
                    "notes": d.get("notes", ""),
                    "schedules": d.get("schedules", []),
                    "date_schedules": d.get("date_schedules", []),
                }
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
