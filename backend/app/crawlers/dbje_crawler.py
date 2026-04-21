"""동부제일병원 크롤러

구조: 단일 진료시간표 페이지에 복잡한 rowspan 테이블 1개.
URL: http://www.dbjeil.co.kr/bbs/board.php?bo_table=1_3

테이블 구조(table index=2):
  헤더 2행: [진료과, 의사명, 구분, 월, 화, 수, 목, 금, 토, 기타, 진료 분야]
  본문: 의사별 2행(오전/오후). 진료과는 여러 의사를 묶고, 의사명은 2행 묶는 rowspan.
셀 텍스트: '●'=진료, '수술'=수술, '예약 진료'=예약, '-'=휴진, '12:30 까지'=토 단축진료
"""
import re
import hashlib
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "http://www.dbjeil.co.kr"
TIMETABLE_URL = f"{BASE_URL}/bbs/board.php?bo_table=1_3"

TIME_RANGES = {"morning": ("08:00", "13:00"), "afternoon": ("14:00", "17:30")}
DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
# '수술'은 외래 진료가 아니므로 제외. 진료로 인정되는 마크만 등록
WORK_MARKS = ("●", "예약", "12:30")
SKIP_MARKS = ("-", "", "휴진", "수술")
LUNCH_NOTE = "점심시간 13:00~14:00"


class DbjeCrawler:
    """동부제일병원 크롤러 — 단일 페이지 정적 HTML"""

    def __init__(self):
        self.hospital_code = "DBJE"
        self.hospital_name = "동부제일병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        self._cached_data = None

    @staticmethod
    def _make_ext_id(department: str, name: str) -> str:
        digest = hashlib.md5(f"{department}|{name}".encode("utf-8")).hexdigest()[:10]
        return f"DBJE-{digest}"

    @staticmethod
    def _expand_grid(table) -> list[list[str]]:
        """rowspan/colspan을 고려해 테이블을 2차원 배열로 펼침"""
        rows = table.select("tr")
        if not rows:
            return []
        width = 20
        grid = [[None] * width for _ in range(len(rows))]
        for r, row in enumerate(rows):
            ci = 0
            for cell in row.select("th, td"):
                while ci < width and grid[r][ci] is not None:
                    ci += 1
                if ci >= width:
                    break
                rs = int(cell.get("rowspan", 1) or 1)
                cs = int(cell.get("colspan", 1) or 1)
                text = cell.get_text(" ", strip=True)
                for dr in range(rs):
                    for dc in range(cs):
                        rr, cc = r + dr, ci + dc
                        if rr < len(grid) and cc < width:
                            grid[rr][cc] = text
                ci += cs
        return grid

    def _parse_schedule_table(self, table) -> list[dict]:
        grid = self._expand_grid(table)
        if len(grid) < 3:
            return []

        # 헤더 2행 후 본문 시작 (r=2부터)
        # 컬럼 구조: 0=진료과, 1=의사명, 2=구분(오전/오후), 3~8=월~토, 9=기타, 10=진료분야
        doctors = {}
        for r in range(2, len(grid)):
            row = grid[r]
            dept = (row[0] or "").strip()
            name = (row[1] or "").strip()
            slot_text = (row[2] or "").strip()
            specialty = (row[10] or "").strip()
            note = (row[9] or "").strip()
            if not dept or not name:
                continue

            if "오전" in slot_text:
                slot = "morning"
            elif "오후" in slot_text:
                slot = "afternoon"
            else:
                continue

            key = (dept, name)
            if key not in doctors:
                doctors[key] = {
                    "name": name,
                    "department": dept,
                    "position": "",
                    "specialty": specialty,
                    "schedules": [],
                    "notes": note,
                    "_seen": set(),
                }

            # 월~토 컬럼 3~8
            for ci in range(3, 9):
                cell = (row[ci] or "").strip()
                if not cell or cell in SKIP_MARKS:
                    continue
                # '수술'은 외래 진료가 아니라 수술일 → 스케줄 제외
                if "수술" in cell:
                    continue
                # 토요일 '12:30 까지'는 오후엔 제외, 오전만 인정
                if "12:30" in cell and slot == "afternoon":
                    continue
                if not any(m in cell for m in WORK_MARKS):
                    continue
                dow = ci - 3
                seen_key = (dow, slot)
                if seen_key in doctors[key]["_seen"]:
                    continue
                doctors[key]["_seen"].add(seen_key)

                start, end = TIME_RANGES[slot]
                # 토요일은 12:30까지
                if dow == 5 and slot == "morning" and "12:30" in cell:
                    end = "12:30"
                location = "예약" if "예약" in cell else ""

                doctors[key]["schedules"].append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": location,
                })

        result = []
        for d in doctors.values():
            d.pop("_seen", None)
            result.append(d)
        return result

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            try:
                resp = await client.get(TIMETABLE_URL)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
            except Exception as e:
                logger.error(f"[DBJE] 페이지 조회 실패: {e}")
                self._cached_data = []
                return []

        # 요일+진료분야 헤더를 가진 테이블 찾기 (table[2])
        target = None
        for t in soup.select("table"):
            rows = t.select("tr")
            if len(rows) < 3:
                continue
            first_text = " ".join(c.get_text(" ", strip=True) for c in rows[0].select("th, td"))
            if "진료과" in first_text and "의사명" in first_text:
                target = t
                break
        if not target:
            logger.error("[DBJE] 진료시간표 테이블을 찾지 못함")
            self._cached_data = []
            return []

        parsed = self._parse_schedule_table(target)
        all_doctors = []
        seen_ids = set()
        for doc in parsed:
            ext_id = self._make_ext_id(doc["department"], doc["name"])
            if ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)
            doc["external_id"] = ext_id
            doc["staff_id"] = ext_id
            doc["profile_url"] = TIMETABLE_URL
            # 점심시간 안내를 기존 notes 앞에 붙임
            existing = doc.get("notes", "").strip()
            doc["notes"] = f"{LUNCH_NOTE} / {existing}" if existing else LUNCH_NOTE
            all_doctors.append(doc)

        logger.info(f"[DBJE] 총 {len(all_doctors)}명")
        self._cached_data = all_doctors
        return all_doctors

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        seen = {}
        for d in data:
            dept = d.get("department") or ""
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
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
        }
        data = await self._fetch_all()
        for d in data:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                return {k: d.get(k, "") for k in
                        ("staff_id", "name", "department", "position",
                         "specialty", "profile_url", "notes", "schedules")}
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
