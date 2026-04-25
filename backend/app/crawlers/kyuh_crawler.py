"""건양대학교병원(Konyang University Hospital) 크롤러

병원 공식명: 건양대학교병원 (대전)
홈페이지: https://www.kyuh.ac.kr
기술: 정적 HTML (httpx + BeautifulSoup), 인코딩: UTF-8

사이트 구조:
  - 진료과 목록 nav: 홈/진료과 페이지에서
        <a href="/prog/treatment/view.do?deptCd=GAS...">소화기내과</a>
    (36개 진료과 — code=GAS, CIR, RES … 한글명은 nav 의 <span>)
  - 진료과별 의료진: /prog/treatment/view.do?deptCd={CODE}
        한 페이지에 소속 교수 카드(<li class="item" id="{doctorId32hex}">)들이 모두 embed
        카드: 사진, <strong class="bold">{이름} {직책}<span>{진료과명}</span></strong>,
              <span class="part-tit">전문분야</span> + <p>{전문분야}</p>
  - 의사 상세/스케줄 단일 URL:
        /prog/doctor/homepage.do?deptCd={CODE}&doctorId={32-hex}
        본원 페이지 안에 <table> 으로 7행/colgroup x 2 (오전/오후, 비고) 진료시간표 embed
        활성 셀: <img alt="진료"> + " 진료" 텍스트
  - 월별 달력 데이터(date_schedules)는 JS 인터랙션 + 로그인 필요 → 주간 패턴을 3개월 투영

external_id: KYUH-{deptCd}-{doctorId32hex}
  - deptCd 가 같이 있어야 단독 조회 시 homepage.do 직접 호출 가능
  - 프로필 URL 의 모든 요소가 그대로 들어감 (슬래시 미사용 — `-` 구분자)

스케줄 마크:
  - "진료" 텍스트 또는 <img alt="진료"> → 외래 진료
  - 빈 셀 / 공백 → 비활성
  - is_clinic_cell() 로 검증
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "https://www.kyuh.ac.kr"
DEPT_LIST_URL = f"{BASE_URL}/prog/treatment/list.do"
DEPT_VIEW_URL = f"{BASE_URL}/prog/treatment/view.do"
DOC_HOMEPAGE_URL = f"{BASE_URL}/prog/doctor/homepage.do"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 폴백 진료과 (홈/리스트 nav 수집 실패 시 사용 — 2026-04 기준)
FALLBACK_DEPTS: dict[str, str] = {
    "GAS": "소화기내과", "CIR": "심장내과", "RES": "호흡기내과",
    "END": "내분비내과", "NEP": "신장내과", "ONC": "혈액종양내과",
    "RHE": "류마티스내과", "INF": "감염내과", "PED": "소아청소년과",
    "NEU": "신경과", "PSY": "정신건강의학과", "DER": "피부과",
    "GS": "외과", "BC": "유방·갑상선클리닉", "GC": "유전상담클리닉",
    "CS": "심장혈관흉부외과", "NS": "신경외과", "OS": "정형외과",
    "PS": "성형외과", "OBG": "산부인과", "OPH": "안과",
    "ENT": "이비인후과", "URO": "비뇨의학과", "REH": "재활의학과",
    "ANE": "마취통증의학과", "PC": "통증클리닉", "RAD": "영상의학과",
    "RO": "방사선종양학과", "CP": "진단검사의학과", "AP": "병리과",
    "FM": "가정의학과", "DEN": "치과", "ER": "응급의학과",
    "OEM": "직업환경의학과", "NM": "핵의학과", "RDC": "희귀질환클리닉",
}

# 32-hex doctorId 패턴
DOCTOR_ID_RE = re.compile(r"^[0-9A-Fa-f]{32}$")
# external_id 분해: KYUH-{deptCd}-{doctorId}
EXTERNAL_ID_RE = re.compile(r"^(?:KYUH-)?([A-Z]+)-([0-9A-Fa-f]{32})$")


class KyuhCrawler:
    """건양대학교병원 크롤러 — 정적 HTML."""

    def __init__(self):
        self.hospital_code = "KYUH"
        self.hospital_name = "건양대학교병원"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
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
    def _abs_url(src: str) -> str:
        if not src:
            return ""
        if src.startswith("http"):
            return src
        if src.startswith("//"):
            return "https:" + src
        return f"{BASE_URL}/{src.lstrip('/')}"

    # ─── 진료과 ────────────────────────────────────────────────
    async def _fetch_dept_map(self, client: httpx.AsyncClient) -> dict[str, str]:
        """진료과 code → 한글명 매핑.
        홈 또는 진료과 list.do 에서 nav 의 <a href=...?deptCd=X><span>NAME</span></a> 추출.
        실패 시 폴백.
        """
        for url in (DEPT_LIST_URL, f"{BASE_URL}/"):
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                html = resp.text
            except Exception as e:
                logger.warning(f"[KYUH] dept map fetch fail {url}: {e}")
                continue
            depts = self._parse_dept_map(html)
            if len(depts) >= 5:
                return depts

        logger.warning("[KYUH] 진료과 동적 수집 실패 → 폴백 사용")
        return dict(FALLBACK_DEPTS)

    @staticmethod
    def _parse_dept_map(html: str) -> dict[str, str]:
        """HTML 에서 deptCd → 한글명 매핑 추출"""
        depts: dict[str, str] = {}
        pattern = re.compile(
            r'href="/prog/treatment/view\.do\?deptCd=([A-Z]+)[^"]*"[^>]*>\s*<span>([^<]+)</span>'
        )
        for m in pattern.finditer(html):
            code = m.group(1)
            name = re.sub(r"\s+", " ", m.group(2)).strip()
            if not name or name in ("진료과", "의료진"):
                continue
            # 첫 등장 우선 — 이후 중복은 무시
            depts.setdefault(code, name)
        return depts

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            depts = await self._fetch_dept_map(client)
        return [{"code": c, "name": n} for c, n in depts.items()]

    # ─── 의사 카드 파싱 ────────────────────────────────────────
    def _parse_doctor_cards(
        self, html: str, dept_code: str, dept_name: str
    ) -> list[dict]:
        """진료과 view.do 페이지의 <li class="item" id="{doctorId}"> 들을 파싱.

        스케줄은 여기서 안 채움(=빈 list). 상세/스케줄은 homepage.do 페이지에서.
        """
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []
        for li in soup.find_all("li", class_="item"):
            did = (li.get("id") or "").strip()
            if not DOCTOR_ID_RE.match(did):
                continue
            try:
                doc = self._parse_one_card(li, dept_code, dept_name, did)
            except Exception as e:
                logger.warning(f"[KYUH] 카드 파싱 실패 ({dept_code}/{did}): {e}")
                continue
            if doc:
                out.append(doc)
        return out

    def _parse_one_card(
        self, li, dept_code: str, dept_name: str, doctor_id: str
    ) -> Optional[dict]:
        # 이름 + 직책 + 진료과 (세부)
        bold = li.find("strong", class_="bold")
        name = ""
        position = ""
        sub_dept = ""
        if bold:
            sub_span = bold.find("span")
            if sub_span:
                sub_dept = self._clean(sub_span.get_text(" ", strip=True))
                sub_span.extract()  # 제거 후 남은 텍스트가 "이름 직책"
            txt = self._clean(bold.get_text(" ", strip=True))
            # "이상혁 교수" → split
            tokens = txt.split()
            if tokens:
                name = tokens[0]
                if len(tokens) > 1:
                    position = " ".join(tokens[1:])
        if not name:
            return None

        # 전문분야: <span class="part-tit">전문분야</span> 다음의 <p>
        specialty = ""
        part = li.find("span", class_="part-tit")
        if part:
            p = part.find_next("p")
            if p:
                specialty = self._clean(p.get_text(" ", strip=True))
                # 주석 텍스트가 같은 노드에 들어갈 수 있으니 짧게 정리
                specialty = specialty[:300]

        # 사진
        photo_url = ""
        img = li.find("img")
        if img:
            photo_url = self._abs_url((img.get("src") or "").strip())

        # 부재/공지: <em>출장</em> : <em>...~...</em> 같은 텍스트
        notes = ""
        for p in li.find_all("p"):
            t = self._clean(p.get_text(" ", strip=True))
            if not t or t == specialty:
                continue
            # 출장/휴진/연수 등 안내문 수집
            if any(k in t for k in ("출장", "휴진", "휴무", "부재", "연수", "학회")):
                notes = (notes + " " + t).strip() if notes else t
        notes = notes[:300]

        ext_id = f"KYUH-{dept_code}-{doctor_id}"
        profile_url = f"{DOC_HOMEPAGE_URL}?deptCd={dept_code}&doctorId={doctor_id}"

        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "doctor_id": doctor_id,
            "dept_code": dept_code,
            "name": name,
            "department": sub_dept or dept_name,
            "position": position,
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": notes,
            "schedules": [],
            "date_schedules": [],
        }

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        """진료과 페이지에서 의사 카드 추출 (스케줄 미포함)."""
        url = f"{DEPT_VIEW_URL}?deptCd={dept_code}&lyMcd=sub01_01{dept_code}"
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
        except Exception as e:
            logger.warning(f"[KYUH] dept fetch fail {dept_code}: {e}")
            return []
        return self._parse_doctor_cards(resp.text, dept_code, dept_name)

    # ─── 스케줄 파싱 (homepage.do) ────────────────────────────
    def _parse_schedule_table(self, html: str) -> list[dict]:
        """homepage.do 의 진료시간표 <table> 파싱.

        구조: thead(빈|월|화|수|목|금|토) + tbody 3행:
          - 오전 행: 6 td (월~토), 진료 있으면 <img alt="진료"> + " 진료"
          - 오후 행: 동일
          - 비고 행 (last-tr): colspan=6 자유 텍스트
        """
        soup = BeautifulSoup(html, "html.parser")

        # caption "진료일정" 또는 헤더에 월/화/수.. 있는 첫 번째 table 선택
        target = None
        for tbl in soup.find_all("table"):
            cap = tbl.find("caption")
            cap_txt = cap.get_text(" ", strip=True) if cap else ""
            if "진료일정" in cap_txt or "진료시간" in cap_txt:
                target = tbl
                break
            # 헤더로도 판단
            ths = [self._clean(th.get_text()) for th in tbl.find_all("th")]
            if "월" in ths and "화" in ths and ("오전" in ths or "오후" in ths):
                target = tbl
                break
        if target is None:
            return []

        schedules: list[dict] = []
        tbody = target.find("tbody")
        if not tbody:
            return []

        rows = tbody.find_all("tr", recursive=False)
        for tr in rows:
            row_th = tr.find("th")
            if not row_th:
                continue
            row_label = self._clean(row_th.get_text(" ", strip=True))
            if "오전" in row_label:
                slot = "morning"
            elif "오후" in row_label:
                slot = "afternoon"
            else:
                continue

            tds = tr.find_all("td", recursive=False)
            for dow, td in enumerate(tds[:6]):
                if not self._is_active_cell(td):
                    continue
                start, end = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return schedules

    @staticmethod
    def _is_active_cell(td) -> bool:
        """td 안에 진료(외래) 표시가 있는지."""
        # 1) <img alt="..."> 의 alt 가 "진료" 면 활성
        for img in td.find_all("img"):
            alt = (img.get("alt") or "").strip()
            if alt == "진료":
                return True
        # 2) 텍스트 판정 (수술/내시경/검사/휴진 등 EXCLUDE 우선)
        text = re.sub(r"\s+", " ", td.get_text(" ", strip=True))
        if not text:
            return False
        return is_clinic_cell(text)

    def _parse_extra_notes(self, html: str) -> str:
        """비고(last-tr) 텍스트만 추출 (휴진 기간 등)."""
        soup = BeautifulSoup(html, "html.parser")
        for tr in soup.find_all("tr", class_="last-tr"):
            td = tr.find("td")
            if td:
                t = re.sub(r"\s+", " ", td.get_text(" ", strip=True))
                if t:
                    return t[:300]
        return ""

    def _parse_profile_meta(self, html: str) -> dict:
        """homepage.do 페이지의 이름/진료과/직책/전문분야/사진 추출."""
        soup = BeautifulSoup(html, "html.parser")
        name = ""
        department = ""
        position = ""
        specialty = ""
        photo_url = ""

        # 이름 + 진료과 + 직책: <h2 class="tit intro-name"><span class="small-tit">진료과</span>이름 직책</h2>
        h2 = soup.find("h2", class_="intro-name") or soup.find("h2", class_="tit")
        if h2:
            sub = h2.find("span", class_="small-tit")
            if sub:
                department = self._clean(sub.get_text(" ", strip=True))
                sub.extract()
            txt = self._clean(h2.get_text(" ", strip=True))
            tokens = txt.split()
            if tokens:
                name = tokens[0]
                if len(tokens) > 1:
                    position = " ".join(tokens[1:])

        # 전문분야: <p class="con con01"><span class="tit">전문분야</span>...
        for p in soup.find_all(["p", "div"], class_=re.compile(r"con\s*con01|con01")):
            t = self._clean(p.get_text(" ", strip=True))
            t = re.sub(r"^전문분야\s*[:：]?\s*", "", t)
            if t:
                specialty = t[:300]
                break

        # 사진
        for img in soup.find_all("img"):
            alt = (img.get("alt") or "")
            src = (img.get("src") or "")
            if "증명사진" in alt or "/thumbnail/doctor/" in src:
                photo_url = self._abs_url(src)
                break

        return {
            "name": name,
            "department": department,
            "position": position,
            "specialty": specialty,
            "photo_url": photo_url,
        }

    async def _fetch_homepage(
        self, client: httpx.AsyncClient, dept_code: str, doctor_id: str
    ) -> tuple[dict, list[dict], str]:
        """homepage.do 1회 호출 → (meta, schedules, notes)."""
        url = f"{DOC_HOMEPAGE_URL}?deptCd={dept_code}&doctorId={doctor_id}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.warning(f"[KYUH] homepage fail {dept_code}/{doctor_id}: {e}")
            return {}, [], ""
        meta = self._parse_profile_meta(html)
        schedules = self._parse_schedule_table(html)
        notes = self._parse_extra_notes(html)
        return meta, schedules, notes

    # ─── 주간 → 3개월 날짜 투영 ────────────────────────────────
    @staticmethod
    def _project_weekly_to_dates(schedules: list[dict]) -> list[dict]:
        if not schedules:
            return []
        today = date.today()
        end = today + timedelta(days=93)

        by_dow: dict[int, list[dict]] = {}
        for s in schedules:
            by_dow.setdefault(int(s["day_of_week"]), []).append(s)

        out: list[dict] = []
        cur = today
        while cur <= end:
            dow = cur.weekday()
            if dow in by_dow:
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
            dept_map = await self._fetch_dept_map(client)
            if not dept_map:
                logger.error("[KYUH] 진료과 0건 — 중단")
                self._cached_data = []
                return []

            sem = asyncio.Semaphore(6)

            async def _list_dept(code: str, name: str) -> list[dict]:
                async with sem:
                    return await self._fetch_dept_doctors(client, code, name)

            list_results = await asyncio.gather(
                *[_list_dept(c, n) for c, n in dept_map.items()],
                return_exceptions=True,
            )

            # 중복 제거 (doctor_id 기준)
            seen: dict[str, dict] = {}
            for r in list_results:
                if isinstance(r, Exception):
                    continue
                for d in r:
                    seen.setdefault(d["doctor_id"], d)

            doctors = list(seen.values())
            logger.info(
                f"[KYUH] 카드 {len(doctors)}명 수집 ({len(dept_map)} 진료과) — 스케줄 가져오는 중..."
            )

            # 각 의사 homepage 호출 → 스케줄/비고
            sem2 = asyncio.Semaphore(6)

            async def _enrich(d: dict):
                async with sem2:
                    meta, schedules, notes = await self._fetch_homepage(
                        client, d["dept_code"], d["doctor_id"]
                    )
                if meta:
                    # 비어있는 필드만 보강
                    if not d.get("specialty") and meta.get("specialty"):
                        d["specialty"] = meta["specialty"]
                    if not d.get("photo_url") and meta.get("photo_url"):
                        d["photo_url"] = meta["photo_url"]
                    if not d.get("position") and meta.get("position"):
                        d["position"] = meta["position"]
                d["schedules"] = schedules
                if notes:
                    d["notes"] = (d.get("notes") + " " + notes).strip() if d.get("notes") else notes
                d["date_schedules"] = self._project_weekly_to_dates(schedules)
                await asyncio.sleep(0.05)  # 서버 부하 완화

            await asyncio.gather(
                *[_enrich(d) for d in doctors], return_exceptions=True,
            )

        logger.info(f"[KYUH] 총 {len(doctors)}명 수집 완료")
        self._cached_data = doctors
        return doctors

    # ─── 공개 인터페이스 ──────────────────────────────────────
    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        keys = ("staff_id", "external_id", "name", "department",
                "position", "specialty", "profile_url", "notes")
        return [{k: d.get(k, "") for k in keys} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회 — 해당 교수 1명만 네트워크 요청.

        external_id 포맷: KYUH-{deptCd}-{doctorId}
        homepage.do 한 번 호출로 이름/진료과/직책/전문분야/사진/스케줄/비고 모두 획득.
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 캐시 (crawl_doctors 흐름에서 의미)
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

        # external_id 분해
        m = EXTERNAL_ID_RE.match(staff_id)
        if not m:
            logger.warning(f"[KYUH] external_id 포맷 불일치: {staff_id}")
            return empty
        dept_code, doctor_id = m.group(1), m.group(2)
        profile_url = f"{DOC_HOMEPAGE_URL}?deptCd={dept_code}&doctorId={doctor_id}"

        async with self._make_client() as client:
            try:
                meta, schedules, notes = await self._fetch_homepage(
                    client, dept_code, doctor_id
                )
            except Exception as e:
                logger.error(f"[KYUH] 개별 조회 실패 {staff_id}: {e}")
                return empty

        if not meta and not schedules:
            return empty

        # 부서명: meta 우선, 폴백 dept_map
        department = meta.get("department") or FALLBACK_DEPTS.get(dept_code, "")

        date_schedules = self._project_weekly_to_dates(schedules)
        return {
            "staff_id": staff_id,
            "name": meta.get("name", ""),
            "department": department,
            "position": meta.get("position", ""),
            "specialty": meta.get("specialty", ""),
            "profile_url": profile_url,
            "notes": notes,
            "schedules": schedules,
            "date_schedules": date_schedules,
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
