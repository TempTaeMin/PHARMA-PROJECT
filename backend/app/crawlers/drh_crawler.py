"""대림성모병원(DRH) 크롤러

병원 공식명: 대림성모병원 (서울 영등포, 유방암·갑상선 특화)
홈페이지: www.drh.co.kr (SPA, /new/front/ 기반)
기술: JS 동적 렌더링 → Playwright 사용

구조:
  센터별 `의료진 소개` 페이지에서 `.doctor_box` 카드를 파싱.
  한 페이지에 카드 여러개 + 카드마다 `예약 가능 시간표` 테이블(2행: 오전/오후 × 월~토).
    진료 표시: `<span class="poss">O</span>` 만 진료로 간주
    그 외 (`noposs` 의 수술/연구/휴진 또는 공백) → 휴진

의사 고유 ID: `a.DoctorInfo` 의 rel 속성 (예: rel="20")
external_id: `DRH-{C_IDX}-{rel}`  (C_IDX 를 포함해야 개별 조회시 해당 센터만 1회 GET)
"""
import re
import logging
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.drh.co.kr/new/front/"

# (C_IDX, m_page, center_name)
CENTERS = [
    (1, "center01_02", "유방암병원"),
    (2, "center02_02", "갑상선병원"),
    (3, "center03_02", "소화기센터"),
    (4, "center04_02", "척추관절센터"),
    (5, "center05_02", "건강증진센터"),
    (9, "checkup08", "건강증진센터"),
    (24, "center07_02", "방사선종양센터"),
    (25, "center08_01", "로봇수술센터"),
]

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("14:00", "17:00")}


class DrhCrawler:
    def __init__(self):
        self.hospital_code = "DRH"
        self.hospital_name = "대림성모병원"
        self._cached_data: list[dict] | None = None

    def _center_url(self, cidx: int, m_page: str) -> str:
        return f"{BASE_URL}?g_page=center&m_page={m_page}&act=center.staff&C_IDX={cidx}"

    def _parse_center_page(self, html: str, cidx: int, center_name: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        boxes = soup.select(".doctor_box")
        result: list[dict] = []
        for b in boxes:
            info_btn = b.select_one("a.DoctorInfo")
            if not info_btn:
                continue
            rel = info_btn.get("rel")
            if isinstance(rel, list):
                rel = rel[0] if rel else ""
            if not rel:
                continue

            name_el = b.select_one(".don_name")
            raw_name = name_el.get_text(" ", strip=True) if name_el else ""
            # "김성원 이사장 [유방외과]" → name="김성원", position="이사장", dept="유방외과"
            m_dept = re.search(r"\[([^\]]+)\]", raw_name)
            department = m_dept.group(1).strip() if m_dept else center_name
            name_wo_dept = re.sub(r"\[[^\]]+\]", "", raw_name).strip()
            m_name = re.match(r"^([가-힣]{2,4})\s*(.*)", name_wo_dept)
            if m_name:
                name = m_name.group(1)
                position = m_name.group(2).strip()
            else:
                name = name_wo_dept.split()[0] if name_wo_dept else ""
                position = ""

            spec_el = b.select_one(".don_part span")
            specialty = spec_el.get_text(" ", strip=True) if spec_el else ""

            img_el = b.select_one(".doc_img img")
            img_src = img_el.get("src", "") if img_el else ""
            profile_url = self._center_url(cidx, CENTERS[0][1])  # page reference

            # 스케줄 테이블 파싱
            schedules: list[dict] = []
            table = b.select_one("table")
            if table:
                tbody_rows = table.select("tbody tr")
                for tr in tbody_rows:
                    label_el = tr.select_one("th")
                    if not label_el:
                        continue
                    label = label_el.get_text(strip=True)
                    slot = "morning" if "오전" in label else ("afternoon" if "오후" in label else None)
                    if slot is None:
                        continue
                    tds = tr.select("td")
                    for dow, td in enumerate(tds[:6]):
                        poss = td.select_one("span.poss")
                        if poss:
                            s, e = TIME_RANGES[slot]
                            schedules.append({
                                "day_of_week": dow, "time_slot": slot,
                                "start_time": s, "end_time": e, "location": "",
                            })

            ext_id = f"{self.hospital_code}-{cidx}-{rel}"
            result.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": department,
                "position": position,
                "specialty": specialty,
                "profile_url": profile_url,
                "notes": "",
                "schedules": schedules,
                "date_schedules": [],
                "_cidx": cidx,
                "_rel": rel,
            })
        return result

    async def _fetch_center_html(self, page, cidx: int, m_page: str) -> str:
        url = self._center_url(cidx, m_page)
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(0.3)
            return await page.content()
        except Exception as e:
            logger.warning(f"[DRH] 센터 {cidx} 로드 실패: {e}")
            return ""

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        from playwright.async_api import async_playwright

        all_doctors: dict[str, dict] = {}
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
                )
                page = await context.new_page()
                for cidx, m_page, center_name in CENTERS:
                    html = await self._fetch_center_html(page, cidx, m_page)
                    if not html:
                        continue
                    doctors = self._parse_center_page(html, cidx, center_name)
                    for d in doctors:
                        # rel(의사고유) 기준 dedup — 첫 등장 센터를 canonical 로
                        key = d["_rel"]
                        if key not in all_doctors:
                            all_doctors[key] = d
                await context.close()
            finally:
                await browser.close()

        result = list(all_doctors.values())
        logger.info(f"[DRH] 총 {len(result)}명")
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
        """개별 조회 — external_id 에서 C_IDX 파싱 후 해당 센터 1개만 렌더링"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") if k not in ("schedules", "date_schedules")
                            else d.get(k, [])
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}
            return empty

        m = re.match(r"^DRH-(\d+)-(\d+)$", staff_id)
        if not m:
            return empty
        cidx = int(m.group(1))
        rel = m.group(2)
        center = next((c for c in CENTERS if c[0] == cidx), None)
        if not center:
            return empty

        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
                )
                page = await context.new_page()
                html = await self._fetch_center_html(page, cidx, center[1])
                await context.close()
            finally:
                await browser.close()

        if not html:
            return empty
        doctors = self._parse_center_page(html, cidx, center[2])
        for d in doctors:
            if d["_rel"] == rel:
                return {k: d.get(k, "") if k not in ("schedules", "date_schedules")
                        else d.get(k, [])
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
