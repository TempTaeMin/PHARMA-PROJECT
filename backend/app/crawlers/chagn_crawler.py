"""강남차병원(Gangnam CHA Hospital) 크롤러

병원 공식명: 강남차병원
홈페이지: gangnam.chamc.co.kr
기술: ASP.NET JSP 정적 렌더링 (httpx + BeautifulSoup)

구조:
  1) 진료과 목록: /treatment/list.cha
       → `<li class="blue">` 에 slug URL + 진료과명
         `<a href="/treatment/list/{slug}/reservation.cha">` 또는
         `<a href="/treatment/{slug}/reservation.cha">` (소아청소년과)
       → `<p class="center_name">` 으로 진료과명 추출
  2) 진료과별 의료진 + 스케줄: 각 reservation.cha URL
       → `div.medical_schedule_list` 가 의사 1명
         · `div.pic_area img` = 프로필 사진
         · `p.doctor_name strong` = "{이름} {직책}" (예: "김문영 교수")
         · `dl.professional dd` = 전문분야
         · `a.reserve[href*="reservation.cha?deptcd=..&meddr=.."]` = meddr
         · `table.table_type_schedule` = 주간 스케줄 (월~토 × 오전/오후)
             cell 텍스트 = "진료"/"초음파"/"순환진료" → 진료 있음
             빈 셀 = 휴진

external_id: CHAGN-{slug}-{meddr}
  slug 을 포함하여 개별 조회 시 해당 진료과 페이지 1회만 GET 하도록 설계.

/appointment/schedule.cha 는 ASP.NET PostBack 기반이라 사용하지 않음.
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://gangnam.chamc.co.kr"
LIST_URL = f"{BASE_URL}/treatment/list.cha"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 헤더 "월/화/수/목/금/토" 컬럼 → day_of_week
DAY_ORDER = ["월", "화", "수", "목", "금", "토"]

# fallback: list.cha 조회 실패 시 사용할 하드코딩 슬러그
_FALLBACK_SLUGS: list[tuple[str, str, str]] = [
    ("list/obstetrics", "산부인과(산과/부인과)", f"{BASE_URL}/treatment/list/obstetrics/reservation.cha"),
    ("list/Infertility", "산부인과(난임센터)", f"{BASE_URL}/treatment/list/Infertility/reservation.cha"),
    ("list/gastroenterology", "소화기병센터(소화기내과/외과)", f"{BASE_URL}/treatment/list/gastroenterology/reservation.cha"),
    ("list/endocrinology", "내분비내과", f"{BASE_URL}/treatment/list/endocrinology/reservation.cha"),
    ("list/cardiology", "순환기내과", f"{BASE_URL}/treatment/list/cardiology/reservation.cha"),
    ("list/pulmonology", "호흡기내과", f"{BASE_URL}/treatment/list/pulmonology/reservation.cha"),
    ("list/generalsurgery", "외과(유방·갑상선센터)", f"{BASE_URL}/treatment/list/generalsurgery/reservation.cha"),
    ("list/plasticsurgery", "성형외과", f"{BASE_URL}/treatment/list/plasticsurgery/reservation.cha"),
    ("pediatrics", "소아청소년과", f"{BASE_URL}/treatment/pediatrics/reservation.cha"),
    ("list/urology", "비뇨의학과", f"{BASE_URL}/treatment/list/urology/reservation.cha"),
    ("list/psychiatry", "정신건강의학과", f"{BASE_URL}/treatment/list/psychiatry/reservation.cha"),
    ("list/dentistry", "치과", f"{BASE_URL}/treatment/list/dentistry/reservation.cha"),
    ("list/pediatricsurgery", "소아외과", f"{BASE_URL}/treatment/list/pediatricsurgery/reservation.cha"),
    ("list/anesthesia", "마취통증의학과", f"{BASE_URL}/treatment/list/anesthesia/reservation.cha"),
    ("list/radiology", "영상의학과", f"{BASE_URL}/treatment/list/radiology/reservation.cha"),
    ("list/diagnostic-check", "진단검사의학과", f"{BASE_URL}/treatment/list/diagnostic-check/reservation.cha"),
    ("list/pathology", "병리과", f"{BASE_URL}/treatment/list/pathology/reservation.cha"),
]

_MEDDR_RE = re.compile(r"meddr=([A-Za-z0-9,]+)")
_DEPTCD_RE = re.compile(r"deptcd=([A-Za-z0-9]+)")
_APROFILE_RE = re.compile(r"aProfile(\d+)")


class ChagnCrawler:
    """강남차병원 크롤러"""

    def __init__(self):
        self.hospital_code = "CHAGN"
        self.hospital_name = "강남차병원"
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
        """list.cha 에서 (slug, 진료과명, reservation URL) 추출"""
        if self._cached_depts is not None:
            return self._cached_depts
        try:
            resp = await client.get(LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[CHAGN] list.cha 실패, fallback 사용: {e}")
            self._cached_depts = list(_FALLBACK_SLUGS)
            return self._cached_depts

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("li.blue")
        out: list[tuple[str, str, str]] = []
        for li in items:
            name_el = li.select_one("p.center_name")
            link_el = li.select_one('a[href*="reservation.cha"]')
            if not name_el or not link_el:
                continue
            href = link_el.get("href", "")
            # slug 추출: /treatment/list/{slug}/reservation.cha 또는 /treatment/{slug}/reservation.cha
            m = re.search(r"/treatment/(.+?)/reservation\.cha", href)
            if not m:
                continue
            slug = m.group(1)
            dept_name = name_el.get_text(strip=True)
            url = href if href.startswith("http") else f"{BASE_URL}{href}"
            out.append((slug, dept_name, url))

        if not out:
            logger.warning("[CHAGN] list.cha 파싱 실패, fallback 사용")
            out = list(_FALLBACK_SLUGS)

        self._cached_depts = out
        return out

    # ────────────────────────────────────────────
    # 의사 카드 파싱
    # ────────────────────────────────────────────
    @staticmethod
    def _split_name_position(raw: str) -> tuple[str, str]:
        """"김문영 교수" → ("김문영", "교수")"""
        raw = (raw or "").strip()
        if not raw:
            return "", ""
        parts = raw.split()
        if len(parts) == 1:
            return parts[0], ""
        # 마지막 토큰이 직책으로 간주 (교수/원장/센터장 등)
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
                text = td.get_text(strip=True)
                if not text:
                    continue
                # 휴진/수술 표기가 있으면 제외 (현재는 "진료"/"초음파"/"순환진료" 만 관찰됨)
                if text in {"휴진", "수술"}:
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
            if src and "staff_blank" not in src:
                photo_url = src

        # 전문분야
        specialty_el = card.select_one("dl.professional dd")
        specialty = specialty_el.get_text(" ", strip=True) if specialty_el else ""

        # meddr + deptcd 추출 (진료예약 가능한 의사)
        reserve_link = card.select_one('a.reserve[href*="meddr="]')
        meddr_primary = ""
        deptcd = ""
        profile_url = ""
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
                profile_url = href if href.startswith("http") else f"{BASE_URL}{href}"

        # fallback: 예약 링크 없는 진료과 (치과/영상의학과/병리과 등)는
        # a#aProfileN 을 원내 식별자로 사용
        doctor_id = meddr_primary
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

        ext_id = f"CHAGN-{slug}-{doctor_id}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": specialty,
            "profile_url": profile_url or f"{BASE_URL}/treatment/{slug}/reservation.cha",
            "photo_url": photo_url,
            "notes": "",
            "meddr": meddr_primary,
            "deptcd": deptcd,
            "slug": slug,
            "doctor_id": doctor_id,
            "schedules": schedules,
            "date_schedules": [],
        }

    async def _fetch_dept_reservation(
        self, client: httpx.AsyncClient, slug: str, dept_name: str, url: str,
    ) -> list[dict]:
        """진료과 reservation.cha 1페이지 → 해당 과 의사 전원"""
        async with self._sem:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"[CHAGN] {slug} 페이지 실패: {e}")
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
                self._fetch_dept_reservation(client, slug, name, url)
                for slug, name, url in depts
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        merged: dict[str, dict] = {}
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"[CHAGN] 진료과 수집 예외: {r}")
                continue
            for d in r:
                merged.setdefault(d["external_id"], d)

        out = list(merged.values())
        logger.info(f"[CHAGN] 총 {len(out)}명 수집")
        self._cached_data = out
        return out

    # ────────────────────────────────────────────
    # 공개 인터페이스
    # ────────────────────────────────────────────
    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
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
        """개별 교수 조회 — external_id 의 slug 로 해당 진료과 페이지 1회만 GET"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 인스턴스 캐시
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, [] if k in ("schedules", "date_schedules") else "")
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}
            return empty

        # external_id 파싱: CHAGN-{slug}-{meddr}  (slug 에 '/' 포함 가능)
        prefix = f"{self.hospital_code}-"
        if not staff_id.startswith(prefix):
            return empty
        tail = staff_id[len(prefix):]
        # 마지막 '-' 이후가 meddr, 그 앞이 slug
        # meddr 는 영숫자/쉼표만, slug 은 '/' 포함 가능 — 마지막 '-' 기준 분리
        idx = tail.rfind("-")
        if idx < 0:
            return empty
        slug = tail[:idx]
        doctor_id = tail[idx + 1:]

        # slug 이 알려진 것인지 (fallback 에 있는 것 기준) 검증
        url = f"{BASE_URL}/treatment/{slug}/reservation.cha"

        async with self._make_client() as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[CHAGN] 개별 조회 실패 {staff_id}: {e}")
                return empty

        soup = BeautifulSoup(resp.text, "html.parser")
        # 진료과명은 페이지 제목/h1 에서 추출 어려움 → fallback 에서 조회
        dept_name = ""
        for s, name, _ in _FALLBACK_SLUGS:
            if s == slug:
                dept_name = name
                break

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
