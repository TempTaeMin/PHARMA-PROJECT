"""원주세브란스기독병원(Wonju Severance Christian Hospital) 크롤러.

병원 공식명: 원주세브란스기독병원
홈페이지: https://www.ywmc.or.kr  (Liferay 기반 정적 HTML)
기술: httpx + BeautifulSoup
인코딩: UTF-8

전체 구조 (특수 케이스 — 한 페이지에 모든 진료과의 시간표가 있음):
  1) 통합 진료시간표: /web/www/treatment_schedule
       - 한 페이지에 40개 진료과의 schedule 테이블이 모두 포함됨
       - 각 테이블 = 1개 진료과
       - 테이블 윗쪽 형제 노드(div) 텍스트에 진료과 이름 명시
       - 테이블 구조 (rowspan 무시 시):
            row0(7th):  의사명 | 월~토 | 특진/진료분야
            row1(12th): 오전/오후 × 6일
            row2~(14td): 의사명 + 12 슬롯 + 특진/진료분야
       - 셀 텍스트 "진료" 가 들어 있으면 활성, 빈 셀이면 비활성
       - 의사명 cell 의 "일반진료" 행은 건너뜀(특정 의사가 아닌 잔여 진료)

  2) 진료과별 의사 목록 (empNo 추출용): /web/www/{slug}/doc
       - `<div class="doctor_bx">` 카드. 각 카드에 다음 포함:
            * `<img src="...empNo={Base64}&deptCode={CODE}">` (Base64 안에 + / = 가 들어감)
            * `<p class="depart">진료과명</p>`
            * `<p class="name"><strong>이름</strong><span>직책</span></p>`
       - empNo 는 Base64 → URL-safe 변환(+→-, /→_, =→.) 으로 external_id 안전화

  3) 의사 1명 스케줄 (개별): /web/www/{slug}/schedule
       - 의사별 doctor_bx + 작은 schedule 테이블 (3행: 헤더 / 오전 / 오후)
       - 같은 페이지에 같은 진료과의 모든 의사가 있어 empNo 로 매칭

external_id 포맷: `YWMC-{deptCode}-{safe_empNo}`
   예: `YWMC-FM-Xfd3PCVvUw2aUJYOdsVtHg..`
   `..` 는 raw `==` 의 안전 변환(.= padding 두 글자), 디코드 시 역치환.

날짜별 스케줄: 통합 진료시간표만 제공되므로, 주간 패턴을 오늘부터 3개월 앞으로 투영.

개별 교수 조회 (`crawl_doctor_schedule`) — 절대 `_fetch_all` 호출 금지:
  external_id 에서 deptCode 추출 → slug 사전(_DEPT_CODE_TO_SLUG) 으로 변환 →
  해당 진료과의 `/schedule` + `/doc` 두 페이지만 fetch (1명만 보더라도 진료과 단위)
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import unquote

import httpx
from bs4 import BeautifulSoup

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "https://www.ywmc.or.kr"
TREATMENT_SCHEDULE_URL = f"{BASE_URL}/web/www/treatment_schedule"
MEDICAL_OFFICE_URL = f"{BASE_URL}/web/www/medical_office"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# treatment_schedule 페이지의 진료과명 → 진료과별 페이지 slug
# (값이 None 인 경우는 slug 매핑이 medical_office 동적 추출에 의존)
# 캐시: 첫 호출에서 medical_office 를 파싱해 채움.
_DEPT_NAME_TO_SLUG: dict[str, str] = {}

# 정적으로 사전 추출한 deptCode → slug 매핑 (개별 조회 fallback 시 빠른 라우팅).
# medical_office + 각 진료과의 /doc 을 한 번씩 크롤링하여 얻은 결과 (40+ 진료과).
# 누락 시 동적 fallback 으로도 보완됨.
_STATIC_DEPT_CODE_TO_SLUG: dict[str, str] = {
    "FM": "family_medicine",
    "AI": "anesthesiology_pain_medicine",
    "RT": "radiation_oncology",
    "AP": "pathology",
    "URO": "urololgy",
    "GYN": "obstetrics_gynecology",
    "PS": "plastic_reconstructive_surgery",
    "PED": "pediatrics",
    "NM": "neurology",
    "NS": "neurosurgery",
    "CVNS": "cvns",
    "CVS": "cardiovascular_surgery",
    "EYE": "ophthalmology",
    "RAD": "radiology",
    "EM": "emergency_care_center",
    "ENT": "otorhinolaryngology",
    "REH": "rehabilitation",
    "PSY": "psychiatry",
    "OS": "orthopedic_surgery",
    "OE": "occupational-and-environmental_medicine",
    "CP": "laboratory_medicine",
    "DENA": "oral_maxillofacial_surgery",
    "DENE": "pediatric_dentistry",
    "DEND": "orthodontics",
    "DENC": "conservative_dentistry",
    "DENB": "prosthodontics",
    "DER": "dermatology",
    "NUM": "nuclear_medicine",
    "CS": "chest_surgery",
    "INF": "infectious_diseases",
    "END": "endocrinology_metabolism",
    "RMT": "rheumatology",
    "GI": "gastroenterology",
    "NEP": "nephrology",
    "CAR9": "cardiology",
    "IIM": "intergrated_internal_medicine",
    "ONC": "hematology",
    "PUL4": "pulmonology",
    "HBP": "hbp_surgery",
    "TE": "thyroid2_surgery",
    "CRS": "lgi_surgery",
    "TCS": "trauma_surgery",
    "EGIS": "ugi_surgery",
    "BS": "breast_surgery",
    "ACS": "acs_surgery",
}

# slug → deptCode (`empNo` URL 의 deptCode 파라미터). 정적 사전을 역으로 사용 + 런타임 보강.
_SLUG_TO_DEPT_CODE: dict[str, str] = {v: k for k, v in _STATIC_DEPT_CODE_TO_SLUG.items()}

# deptCode → slug (개별 조회용 역인덱스). 정적 사전으로 시작.
_DEPT_CODE_TO_SLUG: dict[str, str] = dict(_STATIC_DEPT_CODE_TO_SLUG)


def _safe_empno(emp: str) -> str:
    """Base64 에서 / + = 를 path-safe 문자로 치환.
    `/` 는 FastAPI path 충돌(SKILL.md #9), `+` 는 URL-encode 시 공백, `=` 는 padding.
    """
    return emp.replace("+", "-").replace("/", "_").replace("=", ".")


def _restore_empno(safe: str) -> str:
    """`_safe_empno` 의 역연산."""
    return safe.replace("-", "+").replace("_", "/").replace(".", "=")


class YwmcCrawler:
    """원주세브란스기독병원 크롤러 — 통합 페이지 기반 (정적 HTML, UTF-8)."""

    def __init__(self):
        self.hospital_code = "YWMC"
        self.hospital_name = "원주세브란스기독병원"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: Optional[list[dict]] = None

    # ─── httpx ─────────────────────────────────────────────────
    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    @staticmethod
    def _clean(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "")).strip()

    @staticmethod
    def _normalize_dept_name(s: str) -> str:
        """치료과 페이지 vs medical_office 의 표기 차이 흡수.
        예: '심장혈관센터(심장내과)' ↔ '심장내과' / '신경외과 (뇌혈관)' ↔ '신경외과 (뇌혈관)'.
        괄호 안 텍스트만 떼어 매칭에 사용한다.
        """
        s = (s or "").strip()
        # 공백 정규화
        s = re.sub(r"\s+", "", s)
        return s

    # ─── slug / deptCode 사전 구축 ─────────────────────────────
    async def _ensure_dept_index(self, client: httpx.AsyncClient) -> None:
        """medical_office 에서 (slug, dept_name) 목록 추출. dept_code 는 첫 사용 시 lazy 로 채움."""
        if _DEPT_NAME_TO_SLUG:
            return
        try:
            resp = await client.get(MEDICAL_OFFICE_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[YWMC] medical_office 로드 실패: {e}")
            return
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            h = a["href"]
            t = self._clean(a.get_text(" ", strip=True))
            if not t or "/web/www/" not in h or not h.endswith("/intro"):
                continue
            parts = h.split("/")
            # /web/www/{slug}/intro
            if len(parts) < 5:
                continue
            slug = parts[-2]
            if slug == "introduction":
                continue
            # 첫 등장만 유지
            key_full = self._normalize_dept_name(t)
            if key_full and key_full not in _DEPT_NAME_TO_SLUG:
                _DEPT_NAME_TO_SLUG[key_full] = slug
            # 괄호 안에 있는 별칭도 매핑 (예: '신경외과 (뇌혈관)' → 추가로 '뇌혈관')
            m_paren = re.search(r"\(([^)]+)\)", t)
            if m_paren:
                inner = self._normalize_dept_name(m_paren.group(1))
                if inner and inner not in _DEPT_NAME_TO_SLUG:
                    _DEPT_NAME_TO_SLUG[inner] = slug
                # 괄호 빼고도 등록
                stripped = re.sub(r"\([^)]*\)", "", t)
                stripped_n = self._normalize_dept_name(stripped)
                if stripped_n and stripped_n not in _DEPT_NAME_TO_SLUG:
                    _DEPT_NAME_TO_SLUG[stripped_n] = slug

    def _resolve_slug(self, dept_name: str) -> Optional[str]:
        """진료과명 → slug. 정확/괄호 안/괄호 밖 매칭 순서로 시도."""
        if not dept_name:
            return None
        key = self._normalize_dept_name(dept_name)
        if key in _DEPT_NAME_TO_SLUG:
            return _DEPT_NAME_TO_SLUG[key]
        # 괄호 안 별칭 시도
        m = re.search(r"\(([^)]+)\)", dept_name)
        if m:
            k2 = self._normalize_dept_name(m.group(1))
            if k2 in _DEPT_NAME_TO_SLUG:
                return _DEPT_NAME_TO_SLUG[k2]
            # 괄호 빼고
            stripped = self._normalize_dept_name(re.sub(r"\([^)]*\)", "", dept_name))
            if stripped in _DEPT_NAME_TO_SLUG:
                return _DEPT_NAME_TO_SLUG[stripped]
        # 부분 매칭 (예: '종양내과' → '혈액종양내과' 와는 다르므로 주의 — 같은 글자가 끝까지 포함될 때만)
        for k, slug in _DEPT_NAME_TO_SLUG.items():
            if key and (key == k or (len(key) >= 3 and key in k)):
                return slug
        return None

    # ─── /doc 페이지 파싱 ──────────────────────────────────────
    async def _fetch_dept_doc(
        self, client: httpx.AsyncClient, slug: str
    ) -> dict[str, dict]:
        """`/web/www/{slug}/doc` → {name: {position, empNo, deptCode, photo_url, depart}}"""
        try:
            resp = await client.get(f"{BASE_URL}/web/www/{slug}/doc")
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[YWMC] /doc 로드 실패 {slug}: {e}")
            return {}
        soup = BeautifulSoup(resp.text, "html.parser")

        out: dict[str, dict] = {}
        for d in soup.find_all("div", class_="doctor_bx"):
            n = d.select_one("p.name strong")
            if not n:
                continue
            name = self._clean(n.get_text(" ", strip=True))
            if not name or name == "일반진료":
                continue
            pos_el = d.select_one("p.name span")
            position = self._clean(pos_el.get_text(" ", strip=True)) if pos_el else ""
            depart_el = d.select_one("p.depart")
            depart = self._clean(depart_el.get_text(" ", strip=True)) if depart_el else ""

            img = d.find("img")
            src = img.get("src") if img else ""
            emp = ""
            dept_code = ""
            if src:
                m_emp = re.search(r"empNo=([^&]+)", src)
                m_dept = re.search(r"deptCode=([^&]+)", src)
                emp = unquote(m_emp.group(1)) if m_emp else ""
                dept_code = m_dept.group(1) if m_dept else ""
            if dept_code and slug not in _SLUG_TO_DEPT_CODE:
                _SLUG_TO_DEPT_CODE[slug] = dept_code
                _DEPT_CODE_TO_SLUG[dept_code] = slug

            # 같은 이름 중복 발생 시 첫번째만 유지 (pop 레이어 + 본문에 동일 카드 중복 노출)
            if name in out:
                continue
            out[name] = {
                "name": name,
                "position": position,
                "empNo": emp,
                "deptCode": dept_code,
                "photo_url": (src or "").strip(),
                "depart": depart,
            }
        return out

    # ─── treatment_schedule 통합 파싱 ─────────────────────────
    @staticmethod
    def _previous_text_for_table(table) -> str:
        """테이블의 진료과 이름을 찾는다. 부모/조상의 형제 중 텍스트가 있는 가장 가까운 노드."""
        node = table
        for _ in range(10):
            parent = node.parent
            if not parent or parent.name == "body":
                return ""
            sib = parent.find_previous_sibling()
            if sib:
                txt = re.sub(r"\s+", " ", sib.get_text(" ", strip=True)).strip()
                if txt:
                    # '... 진료과 바로가기' 접미사 제거
                    txt = re.sub(r"\s*진료과\s*바로가기\s*$", "", txt).strip()
                    return txt
            node = parent
        return ""

    @staticmethod
    def _cell_is_active(td) -> bool:
        """YWMC 시간표의 활성 셀 판정.

        활성 신호 (둘 중 하나):
          1) `<span class="t_selc">…</span>` 가 들어 있음 (예약 '선택' 버튼) — 가장 일반
          2) 셀 텍스트가 EXCLUDE/INACTIVE 가 아닌 진료 키워드/마크
        """
        if td is None:
            return False
        # 1차: t_selc 마크
        if td.find("span", class_="t_selc"):
            return True
        # 2차: 텍스트 기반 (혹시 다른 표기 사용 시 대비)
        txt = re.sub(r"\s+", " ", td.get_text(" ", strip=True)).strip()
        if txt and txt != "선택":
            return is_clinic_cell(txt)
        return False

    def _parse_treatment_schedule(self, soup: BeautifulSoup) -> list[dict]:
        """통합 진료시간표 → 의사 dict 리스트."""
        results: list[dict] = []
        for table in soup.find_all("table"):
            cap = table.find("caption")
            if not cap or "진료" not in cap.get_text():
                continue
            dept_name = self._previous_text_for_table(table)
            if not dept_name:
                continue
            rows = table.find_all("tr")
            if len(rows) < 3:
                continue
            # 첫 두 행은 헤더(요일 / 오전·오후), 그 이후가 데이터
            for row in rows[2:]:
                cells = row.find_all(["th", "td"])
                if len(cells) < 13:
                    continue
                name = self._clean(cells[0].get_text(" ", strip=True))
                if not name or name == "일반진료":
                    continue
                # cells[1..12] = 12 슬롯
                schedules: list[dict] = []
                for k in range(12):
                    if not self._cell_is_active(cells[1 + k]):
                        continue
                    dow = k // 2  # 0=월..5=토
                    slot = "morning" if (k % 2 == 0) else "afternoon"
                    start, end = TIME_RANGES[slot]
                    schedules.append({
                        "day_of_week": dow,
                        "time_slot": slot,
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                    })
                specialty = ""
                if len(cells) > 13:
                    specialty = self._clean(cells[13].get_text(" ", strip=True))
                results.append({
                    "name": name,
                    "department": dept_name,
                    "specialty": specialty,
                    "schedules": schedules,
                })
        return results

    # ─── 주간 → 날짜 투영 ─────────────────────────────────────
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
            # 1) 진료과 인덱스 + 통합 시간표
            await self._ensure_dept_index(client)
            try:
                resp = await client.get(TREATMENT_SCHEDULE_URL)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[YWMC] treatment_schedule 로드 실패: {e}")
                self._cached_data = []
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            schedule_rows = self._parse_treatment_schedule(soup)
            if not schedule_rows:
                logger.error("[YWMC] 시간표 0건 — 페이지 구조가 변경됐을 수 있음")
                self._cached_data = []
                return []

            # 2) 진료과별 /doc 병렬 로드 (중복 dept 제거)
            unique_depts = sorted({d["department"] for d in schedule_rows})
            slugs: dict[str, str] = {}
            for dept in unique_depts:
                slug = self._resolve_slug(dept)
                if slug:
                    slugs[dept] = slug
                else:
                    logger.warning(f"[YWMC] slug 매칭 실패: {dept!r}")

            sem = asyncio.Semaphore(5)

            async def run(slug):
                async with sem:
                    return slug, await self._fetch_dept_doc(client, slug)

            slug_to_doc: dict[str, dict[str, dict]] = {}
            if slugs:
                results = await asyncio.gather(
                    *[run(s) for s in set(slugs.values())], return_exceptions=True,
                )
                for r in results:
                    if isinstance(r, Exception):
                        continue
                    slug, doc_map = r
                    slug_to_doc[slug] = doc_map

        # 3) 매칭 + dict 합치기
        out: list[dict] = []
        for row in schedule_rows:
            dept = row["department"]
            slug = slugs.get(dept)
            doc_meta = (slug_to_doc.get(slug, {}) if slug else {}).get(row["name"], {})
            emp = doc_meta.get("empNo", "")
            dept_code = doc_meta.get("deptCode", "")
            position = doc_meta.get("position", "")
            photo_url = doc_meta.get("photo_url", "")
            # external_id 결정
            if emp and dept_code:
                ext_id = f"YWMC-{dept_code}-{_safe_empno(emp)}"
                profile_url = (
                    f"{BASE_URL}/web/www/{slug}/doc"
                    f"?_doctorView_WAR_reservportlet_empNo={emp}"
                    f"&_doctorView_WAR_reservportlet_deptCode={dept_code}"
                ) if slug else ""
            else:
                # /doc 매칭 실패 → 시간표 기반 합성 ID (이름+진료과 hash). 폴백.
                fallback = re.sub(r"\s+", "", f"{dept}-{row['name']}")
                ext_id = f"YWMC-NA-{fallback}"
                profile_url = ""

            schedules = row["schedules"]
            date_schedules = self._project_weekly_to_dates(schedules)
            out.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": row["name"],
                "department": doc_meta.get("depart") or dept,
                "position": position,
                "specialty": row.get("specialty", ""),
                "profile_url": profile_url,
                "photo_url": photo_url,
                "notes": "",
                "schedules": schedules,
                "date_schedules": date_schedules,
                "_slug": slug or "",
                "_emp": emp,
                "_dept_code": dept_code,
            })

        # 같은 external_id 중복 제거 (일반진료 등은 이미 제외됨)
        seen: dict[str, dict] = {}
        for d in out:
            seen.setdefault(d["external_id"], d)
        result = list(seen.values())
        logger.info(f"[YWMC] 총 {len(result)}명 수집 ({len(unique_depts)}개 진료과)")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ──────────────────────────────────────
    async def get_departments(self) -> list[dict]:
        """treatment_schedule 페이지에서 진료과 추출."""
        async with self._make_client() as client:
            try:
                resp = await client.get(TREATMENT_SCHEDULE_URL)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[YWMC] dept 로드 실패: {e}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            depts: list[dict] = []
            seen = set()
            for t in soup.find_all("table"):
                cap = t.find("caption")
                if not cap or "진료" not in cap.get_text():
                    continue
                name = self._previous_text_for_table(t)
                if name and name not in seen:
                    seen.add(name)
                    depts.append({"code": name, "name": name})
            return depts

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        keys = ("staff_id", "external_id", "name", "department",
                "position", "specialty", "profile_url", "photo_url", "notes")
        return [{k: d.get(k, "") for k in keys} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 스케줄 — 해당 진료과 1개의 페이지만 fetch (skill 규칙 #7)."""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 캐시
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["external_id"] == staff_id or d["staff_id"] == staff_id:
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

        # external_id 파싱: "YWMC-{deptCode}-{safe_emp}"
        prefix = f"{self.hospital_code}-"
        if not staff_id.startswith(prefix):
            return empty
        rest = staff_id[len(prefix):]
        parts = rest.split("-", 1)
        if len(parts) != 2:
            return empty
        dept_code, safe_emp = parts
        if dept_code == "NA":
            # 폴백 ID — 매칭 불가
            return empty
        emp_raw = _restore_empno(safe_emp)

        async with self._make_client() as client:
            await self._ensure_dept_index(client)

            slug = _DEPT_CODE_TO_SLUG.get(dept_code)
            if slug is None:
                # /doc 페이지를 한 번씩 훑어 해당 deptCode 발견 시 슬러그 등록
                # (폴백: 매핑된 slug 들을 한 번씩 조회)
                slugs = list(set(_DEPT_NAME_TO_SLUG.values()))
                # 빠르게 첫 매칭만
                for s in slugs:
                    doc_map = await self._fetch_dept_doc(client, s)
                    if any(v.get("deptCode") == dept_code for v in doc_map.values()):
                        slug = s
                        break
                if slug is None:
                    logger.warning(f"[YWMC] dept_code 매칭 실패: {dept_code} ({staff_id})")
                    return empty

            # 1) 해당 진료과 /doc 에서 이름·직책·진료과 텍스트 확보
            doc_map = await self._fetch_dept_doc(client, slug)
            target = None
            for v in doc_map.values():
                if v.get("empNo") == emp_raw:
                    target = v
                    break
            if not target:
                logger.warning(f"[YWMC] empNo 매칭 실패: {staff_id}")
                return empty

            # 2) 해당 진료과 /schedule 에서 의사별 schedule 테이블 추출
            try:
                resp = await client.get(f"{BASE_URL}/web/www/{slug}/schedule")
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[YWMC] /schedule 로드 실패 {slug}: {e}")
                return empty
            soup = BeautifulSoup(resp.text, "html.parser")
            schedules = self._extract_dept_schedule_for_emp(soup, emp_raw, target["name"])

        date_schedules = self._project_weekly_to_dates(schedules)
        profile_url = (
            f"{BASE_URL}/web/www/{slug}/doc"
            f"?_doctorView_WAR_reservportlet_empNo={emp_raw}"
            f"&_doctorView_WAR_reservportlet_deptCode={dept_code}"
        )
        return {
            "staff_id": staff_id,
            "name": target.get("name", ""),
            "department": target.get("depart", ""),
            "position": target.get("position", ""),
            "specialty": "",
            "profile_url": profile_url,
            "notes": "",
            "schedules": schedules,
            "date_schedules": date_schedules,
        }

    def _extract_dept_schedule_for_emp(
        self, soup: BeautifulSoup, emp_raw: str, name: str,
    ) -> list[dict]:
        """`/schedule` 페이지에서 특정 의사(empNo 또는 이름)의 schedule 테이블만 추출.

        구조: 각 doctor_bx 다음에 같은 컨테이너 내에 1개의 schedule 테이블이 있다.
        테이블은 3행 7컬럼 (헤더 / 오전 / 오후) 구조.
        """
        # 후보: doctor_bx 의 부모 컨테이너 안에 schedule 테이블이 함께 있음
        candidates = soup.find_all("div", class_="doctor_bx")
        for d in candidates:
            img = d.find("img")
            src = img.get("src") if img else ""
            if not src:
                continue
            m = re.search(r"empNo=([^&]+)", src)
            cur_emp = unquote(m.group(1)) if m else ""
            n = d.select_one("p.name strong")
            cur_name = self._clean(n.get_text(" ", strip=True)) if n else ""
            if cur_emp != emp_raw and cur_name != name:
                continue

            # 가까운 schedule 테이블 찾기: 부모를 위로 올라가면서 형제 table 또는 다음 형제 검색
            # 우선 부모 컨테이너 내 모든 table 중 caption "진료" 가 있는 첫 테이블
            container = d.parent
            for _ in range(5):
                if not container:
                    break
                tbl = None
                for t in container.find_all("table"):
                    cap = t.find("caption")
                    if cap and "진료" in cap.get_text():
                        tbl = t
                        break
                if tbl:
                    return self._parse_dept_schedule_table(tbl)
                container = container.parent
        return []

    def _parse_dept_schedule_table(self, table) -> list[dict]:
        """`/schedule` 페이지의 1인용 작은 표:
            row0(7th): '진료시간표' | 월 | 화 | 수 | 목 | 금 | 토
            row1(7th): '오전' | 진료/공백 ×6
            row2(7th): '오후' | 진료/공백 ×6
        """
        rows = table.find_all("tr")
        if len(rows) < 2:
            return []
        out: list[dict] = []
        for ri in (1, 2):
            if ri >= len(rows):
                break
            cells = rows[ri].find_all(["th", "td"])
            if len(cells) < 7:
                continue
            slot_label = self._clean(cells[0].get_text(" ", strip=True))
            slot = "morning" if "오전" in slot_label else "afternoon"
            start, end = TIME_RANGES[slot]
            for dow in range(6):  # 월=0..토=5
                if not self._cell_is_active(cells[1 + dow]):
                    continue
                out.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return out

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
