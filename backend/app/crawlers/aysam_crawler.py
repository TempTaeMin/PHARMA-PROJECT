"""안양샘병원(AYSAM) 크롤러

홈페이지: https://anyang.samhospital.com (효산의료재단 안양샘병원)
구조:
  진료과별 소개 페이지: /bbs/content.php?co_id={co_id}
    → `<ul class="doctor_info_list">` 의 `<li>` 가 각 의사 블록
       - <h2 class="name">이름 <span class="dept">직책</span></h2>
       - <ul class="doc_history"> 안에 전문분야/경력 (HTML 혼재)
       - <table> 주간 스케줄: 월(dd) 화(dd) 수(dd) 목(dd) 금(dd) 토(dd)
                tr[0] 오전, tr[1] 오후, <td><span>진료</span></td>
                (진료/내시경/수술/시술/검사/검진/클리닉 등은 진료, 휴진/휴무는 제외)
       - <a href="/doctor/doc_info.php?doctor_no={ID}"> 로 상세페이지 이동

external_id: AYSAM-{co_id}-{doctor_no}
"""
from __future__ import annotations

import asyncio
import logging
import re
import ssl
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

# 안양샘병원 서버는 오래된 DH 키(<1024bit) 를 사용 → 기본 OpenSSL SECLEVEL=2 에서
# "DH_KEY_TOO_SMALL" 에러가 난다. 전용 ssl context 로 SECLEVEL=1 낮춤.
_AYSAM_SSL_CTX = ssl.create_default_context()
_AYSAM_SSL_CTX.set_ciphers("DEFAULT:@SECLEVEL=1")
_AYSAM_SSL_CTX.check_hostname = False
_AYSAM_SSL_CTX.verify_mode = ssl.CERT_NONE

logger = logging.getLogger(__name__)

BASE_URL = "https://anyang.samhospital.com"
DEPT_URL_TMPL = f"{BASE_URL}/bbs/content.php?co_id={{cid}}"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
DAYS = ["월", "화", "수", "목", "금", "토"]

DEPARTMENTS: list[tuple[str, str]] = [
    ("fmclinic", "가정의학과"),
    ("ifmedical", "감염내과"),
    ("igymedical", "난임부인과"),
    ("edmedical", "내분비내과"),
    ("rmmedical", "류마티스내과"),
    ("almedical", "알레르기내과"),
    ("pedmedical", "소아청소년과"),
    ("gimedical", "소화기내과"),
    ("cmedical", "순환기내과"),
    ("numedical", "신경과"),
    ("nmedical", "신장내과"),
    ("npdmedical", "정신건강의학과"),
    ("rhmedical", "재활의학과"),
    ("km", "한방과"),
    ("homedical", "혈액종양내과"),
    ("pmmedical", "호흡기내과"),
    ("emd", "응급의학과"),
    ("oem", "직업환경의학과"),
    ("lm", "진단검사의학과"),
    ("brainns", "뇌신경외과"),
    ("btsurgery", "유방갑상선외과"),
    ("cs", "심장혈관흉부외과"),
    ("gsr", "외과"),
    ("ns", "신경외과"),
    ("ane", "마취통증의학과"),
    ("ent", "이비인후과"),
    ("den", "치과"),
    ("ap", "병리과"),
]

ACTIVE_SCHE_KEYWORDS = (
    "진료", "내시경", "수술", "시술", "검사", "검진", "클리닉",
    "투석", "상담", "심장초음파", "관상동맥",
)
INACTIVE_SCHE_KEYWORDS = ("휴진", "휴무", "휴", "공휴일")

DOC_NO_RE = re.compile(r"doctor_no=(\d+)")


class AysamCrawler:
    def __init__(self):
        self.hospital_code = "AYSAM"
        self.hospital_name = "안양샘병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
            verify=_AYSAM_SSL_CTX,
        )

    def _parse_schedule(self, table) -> list[dict]:
        if table is None:
            return []
        rows = table.find_all("tr")
        if len(rows) < 2:
            return []
        # 첫 번째 tr: 요일 헤더 (월(20) 화(21) ...)
        header_cells = rows[0].find_all(["th", "td"])
        day_cols: dict[int, int] = {}
        for ci, cell in enumerate(header_cells):
            t = cell.get_text(" ", strip=True)
            for di, day in enumerate(DAYS):
                if t.startswith(day) or t == day:
                    day_cols[ci] = di
                    break
        if not day_cols:
            return []

        schedules: list[dict] = []
        for tr in rows[1:]:
            cells = tr.find_all(["th", "td"])
            if not cells:
                continue
            label = cells[0].get_text(" ", strip=True)
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            else:
                continue
            for ci, cell in enumerate(cells):
                if ci not in day_cols:
                    continue
                dow = day_cols[ci]
                # cell 내 의미있는 span 텍스트 추출
                text = ""
                for span in cell.find_all("span"):
                    st = span.get_text(" ", strip=True)
                    if st:
                        text = st
                        break
                if not text:
                    text = cell.get_text(" ", strip=True)
                if not text or text == "-":
                    continue
                if any(k in text for k in INACTIVE_SCHE_KEYWORDS):
                    continue
                is_active = any(k in text for k in ACTIVE_SCHE_KEYWORDS)
                if not is_active:
                    continue
                s, e = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": s,
                    "end_time": e,
                    "location": "",
                })
        return schedules

    def _parse_doctors(self, html: str, co_id: str, dept_name: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        ul = soup.select_one("ul.doctor_info_list")
        if ul is None:
            return []
        result: list[dict] = []
        seen: set[str] = set()

        for li in ul.find_all("li", recursive=False):
            a_detail = li.find("a", href=DOC_NO_RE)
            doctor_no = ""
            if a_detail:
                m = DOC_NO_RE.search(a_detail.get("href", ""))
                if m:
                    doctor_no = m.group(1)
            if not doctor_no or doctor_no in seen:
                continue
            seen.add(doctor_no)

            # 이름과 직책
            name = ""
            position = ""
            h = li.select_one("h2.name")
            if h:
                dept_span = h.select_one("span.dept")
                if dept_span:
                    position = dept_span.get_text(" ", strip=True)
                    dept_span.extract()
                name = h.get_text(" ", strip=True)
            if not name:
                continue

            # 전문분야 — doc_history 안의 태그에서 "주 전문분야" 또는 굵은 텍스트들 취합
            specialty = ""
            dh = li.select_one("ul.doc_history")
            if dh:
                text = dh.get_text(" ", strip=True)
                text = re.sub(r"\s+", " ", text)
                # "주 전문분야 : X" 같은 패턴 우선
                m = re.search(r"주\s*전문분야\s*[:：]\s*([^·\n]+)", text)
                if m:
                    specialty = m.group(1).strip()
                else:
                    specialty = text[:200]

            img = li.select_one(".doctor_picture img")
            photo_url = ""
            if img and img.get("src"):
                src = img["src"].strip()
                photo_url = src if src.startswith("http") else f"{BASE_URL}{src}"

            # 주간 스케줄
            tbl = None
            for cand in li.find_all("table"):
                if cand.find("tr"):
                    tbl = cand
                    break
            schedules = self._parse_schedule(tbl)

            profile_url = f"{BASE_URL}/doctor/doc_info.php?doctor_no={doctor_no}"
            external_id = f"AYSAM-{co_id}-{doctor_no}"
            result.append({
                "staff_id": external_id,
                "external_id": external_id,
                "co_id": co_id,
                "doctor_no": doctor_no,
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": specialty,
                "profile_url": profile_url,
                "photo_url": photo_url,
                "notes": "",
                "schedules": schedules,
                "date_schedules": [],
            })
        return result

    async def _fetch_dept(self, client: httpx.AsyncClient, co_id: str, dept_name: str) -> list[dict]:
        url = DEPT_URL_TMPL.format(cid=co_id)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[AYSAM] {co_id} ({dept_name}) 실패: {e}")
            return []
        return self._parse_doctors(resp.text, co_id, dept_name)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            sem = asyncio.Semaphore(5)

            async def job(cid, name):
                async with sem:
                    return await self._fetch_dept(client, cid, name)

            tasks = [asyncio.create_task(job(cid, name)) for cid, name in DEPARTMENTS]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        seen: set[str] = set()
        all_docs: list[dict] = []
        for r in results:
            if isinstance(r, Exception):
                continue
            for d in r:
                if d["external_id"] in seen:
                    continue
                seen.add(d["external_id"])
                all_docs.append(d)

        logger.info(f"[AYSAM] 총 {len(all_docs)}명")
        self._cached_data = all_docs
        return all_docs

    async def get_departments(self) -> list[dict]:
        return [{"code": name, "name": name} for _, name in DEPARTMENTS]

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
        """개별 조회 — 해당 진료과(co_id) 1페이지만 요청 (skill 규칙 #7)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, [] if k in ("schedules", "date_schedules") else "")
                            for k in ("staff_id","name","department","position",
                                     "specialty","profile_url","notes",
                                     "schedules","date_schedules")}
            return empty

        prefix = "AYSAM-"
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        parts = raw.rsplit("-", 1)
        if len(parts) != 2:
            return empty
        co_id, doctor_no = parts[0], parts[1]
        dept_name = next((n for c, n in DEPARTMENTS if c == co_id), "")

        async with self._make_client() as client:
            doctors = await self._fetch_dept(client, co_id, dept_name)
        for d in doctors:
            if d["external_id"] == staff_id or d["staff_id"] == staff_id or d["doctor_no"] == doctor_no:
                return {k: d.get(k, [] if k in ("schedules", "date_schedules") else "")
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
