"""혜민병원 크롤러

구조: 단일 진료시간표 페이지에 모든 의사 + 주간 스케줄 포함.
URL: https://www.e-hyemin.co.kr/html/?pmode=medtm&spag=medtimetbl&smode=timetbl&pseq=1

페이지 레이아웃:
  <li>
    <div class="hil_img" ...>  # 의사 사진 (f= 파라미터에 해시 ID)
    <div class="hil_txt">
      <p class="middle">
        <span>{진료과}</span>
        <strong>{이름}</strong> {직책}
      </p>
      <table>요일 헤더 + 오전/오후 2행</table>
    </div>
  </li>

셀 텍스트: '진료' / '휴진' / '격주진료' / '내시경' / '수술' / '검진' / '' (빈칸=휴진)
"""
import re
import hashlib
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

from app.crawlers._schedule_rules import find_exclude_keyword, has_biweekly_mark

logger = logging.getLogger(__name__)

BASE_URL = "https://www.e-hyemin.co.kr"
TIMETABLE_URL = f"{BASE_URL}/html/?pmode=medtm&spag=medtimetbl&smode=timetbl&pseq=1"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
# 스케줄로 인정할 셀 텍스트 키워드 (빈 문자열/휴진 계열 + 외래 아닌 활동 제외)
WORK_TEXTS = ("진료", "격주", "검진", "왕진", "외래", "클리닉")
SKIP_TEXTS = ("휴진", "", "-", "x", "X", "OFF", "off")


class HyeminCrawler:
    """혜민병원 크롤러 — 단일 페이지 정적 HTML"""

    def __init__(self):
        self.hospital_code = "HYEMIN"
        self.hospital_name = "혜민병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        self._cached_data = None

    @staticmethod
    def _make_ext_id(department: str, name: str) -> str:
        """진료과 + 이름으로 안정적 external_id 생성"""
        digest = hashlib.md5(f"{department}|{name}".encode("utf-8")).hexdigest()[:10]
        return f"HYEMIN-{digest}"

    def _parse_doctor_li(self, li) -> dict | None:
        """<li> 요소 1개에서 의사 정보 + 스케줄 추출"""
        middle = li.select_one("p.middle")
        if not middle:
            return None

        span = middle.select_one("span")
        strong = middle.select_one("strong")
        if not strong:
            return None

        department = span.get_text(strip=True) if span else ""
        name = strong.get_text(strip=True)
        if not name:
            return None

        # 직책: p.middle 전체 텍스트에서 span/strong 제외한 나머지
        full_text = middle.get_text(" ", strip=True)
        position = full_text.replace(department, "").replace(name, "").strip()

        table = li.select_one("table")
        if not table:
            return {
                "external_id": self._make_ext_id(department, name),
                "name": name,
                "department": department,
                "position": position,
                "specialty": "",
                "schedules": [],
            }

        # 헤더 행에서 요일 → 컬럼 인덱스
        header_row = table.select_one("thead tr") or table.select_one("tr")
        col_to_dow = {}
        if header_row:
            cells = header_row.select("th, td")
            for ci, c in enumerate(cells):
                t = c.get_text(strip=True)
                for ch, dow in DAY_MAP.items():
                    if ch in t:
                        col_to_dow[ci] = dow
                        break

        schedules = []
        seen = set()
        body_rows = table.select("tbody tr") or table.select("tr")[1:]
        for row in body_rows:
            cells = row.select("th, td")
            if not cells:
                continue
            first = cells[0].get_text(strip=True)
            if "오전" in first:
                slot = "morning"
            elif "오후" in first:
                slot = "afternoon"
            else:
                continue

            for ci, cell in enumerate(cells):
                if ci not in col_to_dow:
                    continue
                text = cell.get_text(" ", strip=True)
                if not text or text in SKIP_TEXTS:
                    continue
                # EXCLUDE 우선 — 수술/내시경/검사 등은 제외
                if find_exclude_keyword(text):
                    continue
                # 업무 키워드가 포함된 경우만 진료로 인정
                if not any(w in text for w in WORK_TEXTS):
                    continue
                dow = col_to_dow[ci]
                key = (dow, slot)
                if key in seen:
                    continue
                seen.add(key)
                start, end = TIME_RANGES[slot]
                location = ""
                if "격주" in text:
                    location = "격주"
                elif "검진" in text:
                    location = "검진"
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": location,
                })

        notes = ""
        if any(has_biweekly_mark(s.get("location") or "") for s in schedules):
            notes = "격주 근무"

        return {
            "external_id": self._make_ext_id(department, name),
            "name": name,
            "department": department,
            "position": position,
            "specialty": "",
            "notes": notes,
            "schedules": schedules,
        }

    async def _fetch_all(self) -> list[dict]:
        """진료시간표 페이지 1회 요청 → 전체 의사+스케줄 파싱 후 캐싱"""
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(TIMETABLE_URL)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
            except Exception as e:
                logger.error(f"[HYEMIN] 페이지 조회 실패: {e}")
                self._cached_data = []
                return []

        doctors = []
        seen_ids = set()
        for li in soup.select("li:has(p.middle)"):
            doc = self._parse_doctor_li(li)
            if not doc:
                continue
            ext_id = doc["external_id"]
            if ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)
            doc["staff_id"] = ext_id
            doc["profile_url"] = TIMETABLE_URL
            doc.setdefault("notes", "")
            doctors.append(doc)

        logger.info(f"[HYEMIN] 총 {len(doctors)}명")
        self._cached_data = doctors
        return doctors

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
        """개별 교수 진료시간 — HYEMIN은 단일 페이지 구조이므로 캐시/1회 조회로 해결"""
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
