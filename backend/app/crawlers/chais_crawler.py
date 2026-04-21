"""일산차병원(Ilsan CHA Hospital) 크롤러

병원 공식명: 일산차병원
홈페이지: ilsan.chamc.co.kr
기술: ASP.NET JSP 정적 렌더링 (httpx + BeautifulSoup)

구조 (강남차병원과 거의 동일하나 URL 베이스 경로가 다름):
  1) 진료과 목록: /medical/list/department.cha
       → 각 항목 `<li>` 내부 `<p class="center_name">` 로 진료과명
         `<a href="/medical/list/department/{slug}/medicalStaff.cha">` 로 의료진 URL
         centers(센터)는 /medical/list.cha 쪽에 있으나 department.cha 가 전체를 커버
  2) 진료과별 의료진 + 스케줄: 각 medicalStaff.cha URL
       → `div.medical_schedule_list` 가 의사 1명
         · `div.pic_area img` = 프로필 사진
         · `p.doctor_name strong` = "{이름} {직책}" (예: "박성철 교수")
         · `dl.professional dd` = 전문분야
         · `a.reserve[href*="reservation.cha?deptcd=..&meddr=.."]` = meddr + deptcd
         · `table.table_type_schedule` = 주간 스케줄 (월~토 × 오전/오후)
             cell 텍스트 = "진료"/"2,4주"/"순환진료" 등 → 진료 있음
             빈 셀 / "휴진"/"수술" = 휴진

external_id: CHAIS-{slug}-{meddr}
  - 강남차병원(CHAGN)과 달리, Ilsan 의 slug 은 `department/childbirth` 처럼 '/' 를 포함할 수 있음
  - 핵심 원칙 #9(FastAPI path param 슬래시 금지) 준수를 위해 '/' → '_' 치환
  - 예: department/childbirth + AG11481 → CHAIS-department_childbirth-AG11481
  - 개별 조회 시 '_' → '/' 복원 후 해당 진료과 페이지 1회만 GET

개별 조회 규칙(핵심 원칙 #7): crawl_doctor_schedule() 은 _fetch_all() 호출 금지 —
  external_id 의 slug 로 해당 medicalStaff.cha 1개 페이지만 가져와 필터.
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://ilsan.chamc.co.kr"
DEPT_LIST_URL = f"{BASE_URL}/medical/list/department.cha"
CENTER_LIST_URL = f"{BASE_URL}/medical/list.cha"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 헤더 "월/화/수/목/금/토" 컬럼 → day_of_week
DAY_ORDER = ["월", "화", "수", "목", "금", "토"]

_MEDDR_RE = re.compile(r"meddr=([A-Za-z0-9,]+)")
_DEPTCD_RE = re.compile(r"deptcd=([A-Za-z0-9]+)")
_APROFILE_RE = re.compile(r"aProfile(\d+)")
_IDX_RE = re.compile(r"idx=(\d+)")

# fallback: department.cha 파싱 실패 시 사용할 하드코딩 (slug, 진료과명)
# slug 은 "department/..." 또는 "center/..." 형식 (list URL 경로에 그대로 들어감)
_FALLBACK_DEPTS: list[tuple[str, str]] = [
    ("department/childbirth", "산부인과(분만센터)"),
    ("department/infertility", "산부인과(난임센터)"),
    ("department/gynecologicOncology", "산부인과(부인종양센터)"),
    ("department/gastroenterology", "소화기내과"),
    ("department/endocrinology", "내분비내과"),
    ("department/cardiology", "순환기내과"),
    ("department/pulmonology", "호흡기내과"),
    ("department/nephrology", "신장내과"),
    ("department/Infectious", "감염내과"),
    ("department/HematoOncology", "혈액종양내과"),
    ("department/OrientalMedicine", "한방내과"),
    ("department/thyroid", "외과(갑상선암센터)"),
    ("department/breast", "외과(유방암센터)"),
    ("department/coloanal", "외과(대장항문)"),
    ("department/hepato-biliary-pancreatic", "외과(간담췌)"),
    ("department/plasticSurgery", "성형외과"),
    ("department/pediatrics", "소아청소년과"),
    ("department/urology", "비뇨의학과"),
    ("department/rehabilitationMedicine", "재활의학과"),
    ("department/psychiatry", "정신건강의학과"),
    ("department/FamilyMedicine", "가정의학과"),
    ("department/anesthesiology", "마취통증의학과"),
    ("department/radiology", "영상의학과"),
    ("department/laboratoryMedicine", "진단검사의학과"),
    ("department/pathology", "병리과"),
    ("department/radiationOncology", "방사선종양학과"),
    ("department/nuclearMedicine", "핵의학과"),
    ("department/localEmergency", "지역응급의료기관"),
    ("department/OrientalGynecology", "한방부인과"),
]

# 셀 판정: CHA 계열은 "진료"/"초음파"/"순환진료"/"2,4주" 등 다양한 텍스트 + 빈칸 구조
# 외래 진료가 아닌 것만 제외하면 됨 (SKILL.md 핵심 원칙 #8)
_EXCLUDE_KEYWORDS = (
    "수술", "내시경", "시술", "초음파", "조영",
    "CT", "MRI", "PET", "회진", "실험", "연구",
)
_INACTIVE_KEYWORDS = (
    "휴진", "휴무", "공휴일", "부재", "출장", "학회",
)


def _is_active_cell(text: str) -> bool:
    """셀 텍스트가 외래 진료에 해당하면 True."""
    if not text:
        return False
    t = text.strip()
    if not t:
        return False
    # 1) 비활성 (휴진 등) 우선
    for kw in _INACTIVE_KEYWORDS:
        if kw in t:
            return False
    # 2) 제외 (수술/내시경 등) — CLINIC 판정보다 먼저
    for kw in _EXCLUDE_KEYWORDS:
        if kw in t:
            return False
    # 3) 남은 것은 전부 진료로 간주 ("진료"/"2,4주"/"격주"/"O" 등)
    return True


def _slug_to_external(slug: str) -> str:
    """slug 내 '/' → '_' 치환 (FastAPI path param 호환)."""
    return slug.replace("/", "_")


def _external_to_slug(s: str) -> str:
    """external_id 에 있던 '_' 를 '/' 로 복원."""
    return s.replace("_", "/")


class ChaisCrawler:
    """일산차병원 크롤러"""

    def __init__(self):
        self.hospital_code = "CHAIS"
        self.hospital_name = "일산차병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: list[dict] | None = None
        self._cached_depts: list[tuple[str, str, str]] | None = None
        self._sem = asyncio.Semaphore(5)

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    # ────────────────────────────────────────────
    # 진료과 목록
    # ────────────────────────────────────────────
    async def _fetch_dept_list(
        self, client: httpx.AsyncClient
    ) -> list[tuple[str, str, str]]:
        """department.cha 에서 (slug, 진료과명, medicalStaff URL) 추출.

        slug 은 '/' 포함 — 예: "department/childbirth"
        """
        if self._cached_depts is not None:
            return self._cached_depts

        out: list[tuple[str, str, str]] = []
        try:
            resp = await client.get(DEPT_LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[CHAIS] department.cha 실패, fallback 사용: {e}")
            out = [
                (slug, name, f"{BASE_URL}/medical/list/{slug}/medicalStaff.cha")
                for slug, name in _FALLBACK_DEPTS
            ]
            self._cached_depts = out
            return out

        soup = BeautifulSoup(resp.text, "html.parser")
        # 각 진료과 item: `<li>` 안에 `<a href="...medicalStaff.cha">` + `<p class="center_name">`
        for li in soup.select("li"):
            name_el = li.select_one("p.center_name")
            link_el = li.select_one('a[href*="medicalStaff.cha"]')
            if not name_el or not link_el:
                continue
            href = link_el.get("href", "")
            # slug 추출: /medical/list/{slug}/medicalStaff.cha   (slug 은 '/' 포함 가능)
            m = re.search(r"/medical/list/(.+?)/medicalStaff\.cha", href)
            if not m:
                continue
            slug = m.group(1)
            dept_name = name_el.get_text(strip=True)
            url = href if href.startswith("http") else f"{BASE_URL}{href}"
            out.append((slug, dept_name, url))

        # department.cha 에 센터(암통합/진료협력 등)는 잘 안잡힘 — list.cha 에서도 보강
        try:
            resp2 = await client.get(CENTER_LIST_URL)
            resp2.raise_for_status()
            soup2 = BeautifulSoup(resp2.text, "html.parser")
            existing_slugs = {s for s, _, _ in out}
            for li in soup2.select("li"):
                name_el = li.select_one("p.center_name")
                link_el = li.select_one('a[href*="medicalStaff.cha"]')
                if not name_el or not link_el:
                    continue
                href = link_el.get("href", "")
                m = re.search(r"/medical/list/(.+?)/medicalStaff\.cha", href)
                if not m:
                    continue
                slug = m.group(1)
                if slug in existing_slugs:
                    continue
                dept_name = name_el.get_text(strip=True)
                url = href if href.startswith("http") else f"{BASE_URL}{href}"
                out.append((slug, dept_name, url))
                existing_slugs.add(slug)
        except Exception as e:
            logger.debug(f"[CHAIS] list.cha 센터 보강 실패(무시): {e}")

        if not out:
            logger.warning("[CHAIS] 진료과 파싱 실패, fallback 사용")
            out = [
                (slug, name, f"{BASE_URL}/medical/list/{slug}/medicalStaff.cha")
                for slug, name in _FALLBACK_DEPTS
            ]

        self._cached_depts = out
        return out

    # ────────────────────────────────────────────
    # 의사 카드 파싱
    # ────────────────────────────────────────────
    @staticmethod
    def _split_name_position(raw: str) -> tuple[str, str]:
        """"박성철 교수" → ("박성철", "교수")"""
        raw = (raw or "").strip()
        if not raw:
            return "", ""
        parts = raw.split()
        if len(parts) == 1:
            return parts[0], ""
        # 마지막 토큰을 직책으로 간주 (교수/원장/센터장/전문의 등)
        position = parts[-1]
        name = " ".join(parts[:-1])
        return name, position

    @staticmethod
    def _parse_schedule_table(table) -> list[dict]:
        """table.table_type_schedule → [{day_of_week, time_slot, ...}]"""
        schedules: list[dict] = []
        tbody = table.find("tbody")
        if tbody is None:
            return schedules

        for tr in tbody.find_all("tr"):
            th = tr.find("th")
            if th is None:
                continue
            row_label = th.get_text(strip=True)
            if "오전" in row_label:
                slot = "morning"
            elif "오후" in row_label:
                slot = "afternoon"
            else:
                continue
            start, end = TIME_RANGES[slot]
            tds = tr.find_all("td")
            # 월~토 6개 td 기대
            for i, td in enumerate(tds[:6]):
                text = td.get_text(" ", strip=True)
                if not _is_active_cell(text):
                    continue
                schedules.append({
                    "day_of_week": i,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return schedules

    def _parse_doctor_card(self, card, slug: str, dept_name: str) -> dict | None:
        """div.medical_schedule_list → 의사 dict"""
        strong_el = card.select_one("p.doctor_name strong")
        if not strong_el:
            return None
        name, position = self._split_name_position(strong_el.get_text(strip=True))
        if not name:
            return None

        # 프로필 사진
        img = card.select_one("div.pic_area img")
        photo_url = ""
        if img is not None:
            src = img.get("src", "")
            if src and "professor_list_default" not in src and "staff_blank" not in src:
                photo_url = src

        # 전문분야
        specialty_el = card.select_one("dl.professional dd")
        specialty = specialty_el.get_text(" ", strip=True) if specialty_el else ""

        # meddr + deptcd 추출 (진료예약 가능한 의사)
        reserve_link = card.select_one('a.reserve[href*="meddr="]')
        meddr_primary = ""
        deptcd = ""
        reserve_url = ""
        if reserve_link is not None:
            href = reserve_link.get("href", "")
            m = _MEDDR_RE.search(href)
            if m:
                # 복수 meddr 가능 — 첫 번째를 식별자로 사용
                meddr_primary = m.group(1).split(",")[0].strip()
            d = _DEPTCD_RE.search(href)
            if d:
                deptcd = d.group(1).strip()
            if href:
                reserve_url = href if href.startswith("http") else f"{BASE_URL}{href}"

        # 상세소개(profile) URL — idx 기반
        profile_idx = ""
        profile_url = ""
        profile_link = card.select_one('a[href*="profile.cha?idx="]')
        if profile_link is not None:
            pm = _IDX_RE.search(profile_link.get("href", ""))
            if pm:
                profile_idx = pm.group(1)
                profile_url = f"{BASE_URL}/professor/profile.cha?idx={profile_idx}"

        # fallback: 예약 링크 없는 경우 profile idx 또는 aProfile 사용
        doctor_id = meddr_primary
        if not doctor_id and profile_idx:
            doctor_id = f"p{profile_idx}"
        if not doctor_id:
            prof_el = card.select_one('a[id^="aProfile"]')
            if prof_el is not None:
                m2 = _APROFILE_RE.search(prof_el.get("id", ""))
                if m2:
                    doctor_id = f"p{m2.group(1)}"

        if not doctor_id:
            # 식별자 없는 카드는 스킵
            return None

        # 스케줄 테이블
        schedules: list[dict] = []
        sched_table = card.select_one("table.table_type_schedule")
        if sched_table is not None:
            schedules = self._parse_schedule_table(sched_table)

        # external_id 에 '/' 금지 — slug 의 '/' 를 '_' 로 치환
        ext_slug = _slug_to_external(slug)
        ext_id = f"CHAIS-{ext_slug}-{doctor_id}"

        # profile_url 이 없으면 reserve_url → medicalStaff.cha 순으로 fallback
        final_profile = profile_url or reserve_url or \
            f"{BASE_URL}/medical/list/{slug}/medicalStaff.cha"

        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": specialty,
            "profile_url": final_profile,
            "photo_url": photo_url,
            "notes": "",
            "meddr": meddr_primary,
            "deptcd": deptcd,
            "slug": slug,
            "doctor_id": doctor_id,
            "schedules": schedules,
            "date_schedules": [],
        }

    async def _fetch_dept_staff(
        self, client: httpx.AsyncClient, slug: str, dept_name: str, url: str,
    ) -> list[dict]:
        """진료과 medicalStaff.cha 1페이지 → 해당 과 의사 전원"""
        async with self._sem:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"[CHAIS] {slug} 페이지 실패: {e}")
                return []

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.medical_schedule_list")
        result: list[dict] = []
        for card in cards:
            parsed = self._parse_doctor_card(card, slug, dept_name)
            if parsed:
                result.append(parsed)
        return result

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            if not depts:
                self._cached_data = []
                return []

            tasks = [
                self._fetch_dept_staff(client, slug, name, url)
                for slug, name, url in depts
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        merged: dict[str, dict] = {}
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"[CHAIS] 진료과 수집 예외: {r}")
                continue
            for d in r:
                merged.setdefault(d["external_id"], d)

        out = list(merged.values())
        logger.info(f"[CHAIS] 총 {len(out)}명 수집")
        self._cached_data = out
        return out

    # ────────────────────────────────────────────
    # 공개 인터페이스
    # ────────────────────────────────────────────
    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
        # code 는 slug 그대로 (내부 식별자) — UI 에서는 name 만 보여줌
        return [{"code": slug, "name": name} for slug, name, _ in depts]

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
        """개별 교수 조회 — external_id 의 slug 로 해당 진료과 페이지 1회만 GET.

        핵심 원칙 #7 준수: _fetch_all() 호출 금지.
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 내 캐시 (crawl_doctors 흐름에서 의미)
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, [] if k in ("schedules", "date_schedules") else "")
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}
            return empty

        # external_id 파싱: CHAIS-{ext_slug}-{doctor_id}
        #   ext_slug 에는 '/' 가 '_' 로 치환되어 있음 (예: department_childbirth)
        #   doctor_id 는 영숫자/쉼표만
        prefix = f"{self.hospital_code}-"
        if not staff_id.startswith(prefix):
            return empty
        tail = staff_id[len(prefix):]
        # 마지막 '-' 이후가 doctor_id, 그 앞이 ext_slug
        idx = tail.rfind("-")
        if idx < 0:
            return empty
        ext_slug = tail[:idx]
        doctor_id = tail[idx + 1:]
        # '_' → '/' 복원
        slug = _external_to_slug(ext_slug)

        url = f"{BASE_URL}/medical/list/{slug}/medicalStaff.cha"

        async with self._make_client() as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[CHAIS] 개별 조회 실패 {staff_id}: {e}")
                return empty

        soup = BeautifulSoup(resp.text, "html.parser")
        # 진료과명 — fallback 리스트에서 먼저 확인, 없으면 페이지에서 추출 시도
        dept_name = ""
        for s, name in _FALLBACK_DEPTS:
            if s == slug:
                dept_name = name
                break
        if not dept_name:
            # breadcrumb / 제목에서 추출 시도 (간단 fallback)
            title_el = soup.select_one("h3, h2, .sub_title, .medical_title")
            if title_el is not None:
                dept_name = title_el.get_text(strip=True)

        for card in soup.select("div.medical_schedule_list"):
            parsed = self._parse_doctor_card(card, slug, dept_name)
            if parsed and parsed["doctor_id"] == doctor_id:
                return {k: parsed.get(k, [] if k in ("schedules", "date_schedules") else "")
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
