"""단국대학교의과대학부속병원(Dankook University Hospital) 크롤러

병원 공식명: 단국대학교의과대학부속병원 (단국대학교병원, 충남 천안)
홈페이지: https://www.dkuh.co.kr  (→ /html_2016/)
기술: 정적 HTML (httpx + BeautifulSoup), 인코딩: UTF-8 (BOM)

사이트 구조:
  - 전체 진료과 nav: 홈의 `<a href="/html_2016/03/{code}.php">{진료과명}</a>` 목록
  - 진료과별 의료진 페이지: `/html_2016/03/{code}_02.php`
      * 한 페이지에 소속 교수들의 카드 + 주간 진료시간표가 모두 embed 됨
      * 각 교수 = `<table class="drTable">` 1개
          - subj : 세부 진료과명 (내과 계열은 subspecialty 로 노출됨)
          - doctor_name : 교수명
          - 전문분야 : `전문분야 : ...` 시작 span
          - 사진 : `img.DRIMG` (src = /board5/data/doctor/{SUBJCODE}/...)
          - view_dr(XXXXXX) : 주석 안에 남아있는 교수 고유 idx
          - quick_res('XXYY') : 세부 진료과 코드 (subj_code), 예약 URL 에 필요
          - 진료시간표: 내부 `table.calTable`, 3행 (오전/오후/기타)
              · 오전, 오후 행 각각 6 td = 월~토
              · 셀 안 img src=`/reserve/images/am_sc.png` 또는 `am_bl.png` → 진료 있음
                  - am_bl : 진료일정 있음, am_sc : 진료예약 가능 (둘 다 외래 진료)
              · 기타 행: 위치 안내 / 휴진 기간 등 자유 텍스트

비고:
  - 교수 상세 팝업 (`/html_2016/01_02.php?idx=XXX`) 은 현재 404 → 별도 상세 정보 없음
    → 카드에 노출된 subj, doctor_name, 전문분야, 사진, 기타행 텍스트만 사용
  - 일부 진료과 nav 는 `ur_01` 처럼 올라오지만 실제 파일은 `ur.php`/`ur_02.php` → 매핑 table 로 보정
  - 월별 달력이 제공되지 않으므로 주간 패턴을 오늘~3개월 앞으로 투영해 date_schedules 생성.
    기타 행의 "휴진(YYYY.M.DD - YYYY.M.DD)" 구간은 date_schedules 에서 제외.

external_id: DKUH-{idx} (view_dr 의 숫자 idx — 사이트 전역 고유)
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.dkuh.co.kr"
DEPT_BASE = f"{BASE_URL}/html_2016/03"
HOME_URL = f"{BASE_URL}/html_2016/"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 진료 있음 이미지 파일 (외래 진료로 포함)
CLINIC_MARK_IMAGES = {"am_sc.png", "am_bl.png"}

# view_dr 안의 idx
VIEW_DR_RE = re.compile(r"view_dr\((\d+)\)")
# quick_res 의 subj_code
QUICK_RES_RE = re.compile(r"quick_res\('([^']+)'\)")
# "휴진(2026.4.06 - 2026.6.05)" 형식 기간 추출
ABSENCE_RE = re.compile(
    r"(?:휴진|휴무|부재|출장)\s*\(\s*"
    r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\s*[-~]\s*"
    r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\s*\)"
)

# 홈에서 추출한 부정확한 nav 파일명 → 실제 파일명 (기본 또는 _02) 보정용
# 홈 링크는 /html_2016/03/ur_01.php 이지만 실제 파일은 ur.php / ur_02.php 임
DEPT_CODE_FIX: dict[str, str] = {
    "ur_01": "ur",
}

# 홈 nav 수집 실패 시 폴백용 진료과 (code → 한글명)
FALLBACK_DEPTS: dict[str, str] = {
    "ig": "소화기내과", "cc": "심장혈관내과", "ip": "호흡기-알레르기내과",
    "ie": "내분비대사내과", "in": "신장내과", "ih": "혈액종양내과",
    "ii": "감염내과", "ir": "류마티스내과", "pd": "소아청소년과",
    "gs": "외과", "og": "산부인과", "py": "정신건강의학과",
    "nr": "신경과", "dm": "피부과", "os": "정형외과", "ns": "신경외과",
    "dp": "예방의학과", "cs": "심장혈관 흉부외과", "ps": "성형외과",
    "ey": "안과", "en": "이비인후과", "ur": "비뇨의학과",
    "fm": "가정의학과", "om": "직업환경의학과", "rm": "재활의학과",
    "ms": "구강악안면외과", "er": "응급의학과", "an": "마취통증의학과",
    "cp1": "진단검사의학과", "ap": "병리과", "dr": "영상의학과",
    "tr": "방사선종양학과", "nm": "핵의학과", "ts": "외상학과",
}


class DkuhCrawler:
    """단국대학교의과대학부속병원 크롤러 — 정적 HTML (UTF-8 BOM)"""

    def __init__(self):
        self.hospital_code = "DKUH"
        self.hospital_name = "단국대학교의과대학부속병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: Optional[list[dict]] = None

    # ─── httpx client ─────────────────────────────────────────
    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    # ─── 헬퍼 ─────────────────────────────────────────────────
    @staticmethod
    def _clean(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "")).strip()

    @staticmethod
    def _decode(resp: httpx.Response) -> str:
        """UTF-8 (BOM 포함) 우선, 실패 시 EUC-KR 폴백"""
        content = resp.content
        if content.startswith(b"\xef\xbb\xbf"):
            content = content[3:]
        for enc in ("utf-8", "euc-kr"):
            try:
                return content.decode(enc)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="replace")

    @staticmethod
    def _abs_url(src: str) -> str:
        if not src:
            return ""
        if src.startswith("http"):
            return src
        if src.startswith("//"):
            return "https:" + src
        return f"{BASE_URL}/{src.lstrip('/')}"

    # ─── 진료과 ────────────────────────────────────────────────
    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        """홈페이지 nav 에서 진료과 code/name 수집. 실패 시 폴백."""
        try:
            resp = await client.get(HOME_URL)
            resp.raise_for_status()
            html = self._decode(resp)
        except Exception as e:
            logger.warning(f"[DKUH] 홈 로드 실패 → 폴백 사용: {e}")
            return [{"code": self._normalize_code(c), "name": n}
                    for c, n in FALLBACK_DEPTS.items()]

        depts: dict[str, str] = {}
        # <a href="/html_2016/03/{code}.php">{한글명}</a>
        pattern = re.compile(
            r'href="/html_2016/03/(\w+)\.php"[^>]*>([^<]{1,40})<'
        )
        for m in pattern.finditer(html):
            code_raw = m.group(1)
            name = self._clean(m.group(2))
            code = self._normalize_code(code_raw)
            if not name or name.isdigit():
                continue
            # 기본 한글명 우선 (첫 번째 등장 승)
            depts.setdefault(code, name)

        if not depts:
            return [{"code": c, "name": n} for c, n in FALLBACK_DEPTS.items()]

        return [{"code": c, "name": n} for c, n in depts.items()]

    @staticmethod
    def _normalize_code(code_raw: str) -> str:
        return DEPT_CODE_FIX.get(code_raw, code_raw)

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
        return [{"code": d["code"], "name": d["name"]} for d in depts]

    # ─── 스케줄 파싱 ────────────────────────────────────────────
    def _parse_calTable(self, cal) -> tuple[list[dict], str]:
        """calTable → (schedules, etc_text)

        - 오전(row1), 오후(row2) 각 6 td = 월~토
        - td 내부 img src 가 CLINIC_MARK_IMAGES 에 속하면 진료 있음
        - row3 = 기타 텍스트 (콜스페이스 큰 td 1개)
        """
        schedules: list[dict] = []
        etc_text = ""
        if cal is None:
            return schedules, etc_text
        rows = cal.find_all("tr", recursive=False)
        if len(rows) < 3:
            return schedules, etc_text

        for slot_idx, slot in ((1, "morning"), (2, "afternoon")):
            if slot_idx >= len(rows):
                continue
            tds = rows[slot_idx].find_all("td", recursive=False)
            for dow, td in enumerate(tds[:6]):
                imgs = td.find_all("img")
                has_mark = False
                for img in imgs:
                    src = (img.get("src") or "").split("?")[0]
                    fname = src.rsplit("/", 1)[-1].lower()
                    if fname in CLINIC_MARK_IMAGES:
                        has_mark = True
                        break
                if not has_mark:
                    continue
                start, end = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow,  # 0=월 ~ 5=토
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })

        # 기타 행
        if len(rows) >= 4:
            etc_td = rows[3].find("td", recursive=False)
            if etc_td:
                etc_text = self._clean(etc_td.get_text(" ", strip=True))
        return schedules, etc_text

    def _parse_doctor_table(self, tbl, fallback_dept: str) -> Optional[dict]:
        """drTable → doctor dict"""
        tbl_html = str(tbl)

        # idx (view_dr)
        m = VIEW_DR_RE.search(tbl_html)
        if not m:
            return None
        idx_val = m.group(1)

        # subj code (quick_res)
        subj_m = QUICK_RES_RE.search(tbl_html)
        subj_code = subj_m.group(1) if subj_m else ""

        # 이름
        dn = tbl.find("span", class_="doctor_name")
        name = self._clean(dn.get_text(" ", strip=True)) if dn else ""
        if not name:
            return None

        # 진료과 (subj span = 세부 진료과)
        subj_span = tbl.find("span", class_="subj")
        department = self._clean(subj_span.get_text(" ", strip=True)) if subj_span else ""
        if not department:
            department = fallback_dept

        # 전문분야: 상단 span 중 "전문분야" 시작
        specialty = ""
        for sp in tbl.find_all("span"):
            txt = self._clean(sp.get_text(" ", strip=True))
            if txt.startswith("전문분야"):
                specialty = self._clean(re.sub(r"^전문분야\s*[:：]\s*", "", txt))
                break

        # 사진
        photo_url = ""
        img = tbl.find("img", class_="DRIMG") or tbl.find("img")
        if img:
            photo_url = self._abs_url((img.get("src") or "").strip())

        # 스케줄 + 기타행
        cal = tbl.find("table", class_="calTable")
        schedules, etc_text = self._parse_calTable(cal)

        # notes: 기타행 텍스트 (location / 휴진 안내 등)
        notes = etc_text[:500]

        ext_id = f"DKUH-{idx_val}"
        profile_url = (
            f"{BASE_URL}/html_2016/reserve/reserve.php?menu=04012&dr={subj_code}"
            if subj_code else f"{BASE_URL}/html_2016/"
        )

        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "idx": idx_val,
            "subj_code": subj_code,
            "name": name,
            "department": department,
            "position": "",  # 사이트에 직책 정보 없음
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": notes,
            "etc_text": etc_text,
            "schedules": schedules,
            "date_schedules": [],
        }

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        """/html_2016/03/{code}_02.php 의 drTable 전수 파싱"""
        url = f"{DEPT_BASE}/{dept_code}_02.php"
        try:
            resp = await client.get(url)
            # 302 → notpage.html 이면 무시
            if resp.status_code != 200:
                return []
            if "notpage" in str(resp.url):
                return []
            html = self._decode(resp)
        except Exception as e:
            logger.warning(f"[DKUH] {dept_code}({dept_name}) 로드 실패: {e}")
            return []

        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []
        for tbl in soup.find_all("table", class_="drTable"):
            try:
                d = self._parse_doctor_table(tbl, dept_name)
            except Exception as e:
                logger.warning(f"[DKUH] 카드 파싱 실패 ({dept_name}): {e}")
                continue
            if d:
                out.append(d)
        return out

    # ─── 주간 → 3개월 날짜 투영 ────────────────────────────────
    @staticmethod
    def _parse_absence_ranges(text: str) -> list[tuple[date, date]]:
        if not text:
            return []
        ranges: list[tuple[date, date]] = []
        for m in ABSENCE_RE.finditer(text):
            try:
                y1, mo1, d1, y2, mo2, d2 = map(int, m.groups())
                ranges.append((date(y1, mo1, d1), date(y2, mo2, d2)))
            except ValueError:
                continue
        return ranges

    def _project_weekly_to_dates(
        self, schedules: list[dict], etc_text: str
    ) -> list[dict]:
        """주간 패턴 → 오늘부터 ~93일 (약 3개월). 휴진 기간 제외."""
        if not schedules:
            return []
        today = date.today()
        end = today + timedelta(days=93)
        absence_ranges = self._parse_absence_ranges(etc_text)

        by_dow: dict[int, list[dict]] = {}
        for s in schedules:
            by_dow.setdefault(int(s["day_of_week"]), []).append(s)

        out: list[dict] = []
        cur = today
        while cur <= end:
            dow = cur.weekday()
            if dow in by_dow:
                in_absence = any(a <= cur <= b for (a, b) in absence_ranges)
                if not in_absence:
                    for s in by_dow[dow]:
                        out.append({
                            "schedule_date": cur.isoformat(),
                            "time_slot": s["time_slot"],
                            "start_time": s["start_time"],
                            "end_time": s["end_time"],
                            "location": s.get("location", ""),
                            "status": "진료",
                        })
            cur += timedelta(days=1)
        return out

    # ─── 전체 ──────────────────────────────────────────────────
    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            if not depts:
                logger.error("[DKUH] 진료과 0건 — 중단")
                self._cached_data = []
                return []

            sem = asyncio.Semaphore(6)

            async def _run(d: dict):
                async with sem:
                    return await self._fetch_dept_doctors(client, d["code"], d["name"])

            results = await asyncio.gather(
                *[_run(d) for d in depts], return_exceptions=True,
            )

        # idx 기준 중복 제거 (같은 교수가 여러 진료과 페이지에 있을 수 있음)
        seen: dict[str, dict] = {}
        for r in results:
            if isinstance(r, Exception):
                continue
            for doc in r:
                if doc["idx"] in seen:
                    continue
                seen[doc["idx"]] = doc

        # 날짜 투영
        for doc in seen.values():
            doc["date_schedules"] = self._project_weekly_to_dates(
                doc["schedules"], doc.get("etc_text", ""),
            )

        out = list(seen.values())
        logger.info(f"[DKUH] 총 {len(out)}명 수집 ({len(depts)} 진료과)")
        self._cached_data = out
        return out

    # ─── 공개 인터페이스 ──────────────────────────────────────
    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        keys = ("staff_id", "external_id", "name", "department",
                "position", "specialty", "profile_url", "notes")
        return [{k: d.get(k, "") for k in keys} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회 — _fetch_all() 을 호출하지 않고 진료과 페이지만 순차로 스캔.

        사이트에 교수 단일 상세 엔드포인트가 없으므로 진료과 _02 페이지를 순회하며
        drTable 내부 view_dr(idx) 를 매칭. 발견 즉시 중단 → 평균 절반의 페이지만 로드.
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 인스턴스 캐시 사용 (crawl_doctors 흐름에서 의미)
        if self._cached_data is not None:
            for d in self._cached_data:
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

        prefix = f"{self.hospital_code}-"
        raw_idx = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not raw_idx.isdigit():
            return empty

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            for d in depts:
                try:
                    docs = await self._fetch_dept_doctors(client, d["code"], d["name"])
                except Exception as e:
                    logger.warning(f"[DKUH] 조회 중 오류 {d['code']}: {e}")
                    continue
                for doc in docs:
                    if doc["idx"] == raw_idx:
                        date_schedules = self._project_weekly_to_dates(
                            doc["schedules"], doc.get("etc_text", ""),
                        )
                        return {
                            "staff_id": staff_id,
                            "name": doc.get("name", ""),
                            "department": doc.get("department", ""),
                            "position": doc.get("position", ""),
                            "specialty": doc.get("specialty", ""),
                            "profile_url": doc.get("profile_url", ""),
                            "notes": doc.get("notes", ""),
                            "schedules": doc.get("schedules", []),
                            "date_schedules": date_schedules,
                        }
        logger.warning(f"[DKUH] 개별 조회 매칭 실패: {staff_id}")
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
                photo_url=d.get("photo_url", ""),
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
