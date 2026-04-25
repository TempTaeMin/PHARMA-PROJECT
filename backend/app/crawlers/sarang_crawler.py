"""안산사랑의병원(Sarang Medical Center) 크롤러

병원 공식명: 칠석의료재단 안산사랑의병원
홈페이지: www.sarangmc.co.kr (UTF-8)

구조:
  1) 의료진 전체 페이지 한 장에 모든 교수가 렌더링 (`/index.php/html/615`)
     - `section.doctorSection` 안에 `.profileBox` 반복 (약 40명)
     - 각 profileBox:
         `.profilePic > img`          — 프로필 이미지
         `.profileTxt > p.dKind`      — "진료과1, 진료과2, ... / {전문의}" 형식
         `.profileTxt > h3.dName > strong` — 이름
         `.profileTxt > h3.dName > span`   — 직책
         `aside.doctorPop`            — 상세 팝업 (전문분야 / 학력 / 진료일정)
             `table[summary="진료시간입니다."]` — 진료시간표 (2개 존재할 수 있음, 첫 번째 사용)
                 thead: 월~토
                 tbody: 오전행 / 오후행
                 각 td 텍스트 또는 `data-text` 속성으로 "진료 / 수술 / 2,4주 진료 / 빈칸" 표기
  2) 진료과 목록 페이지 (`/index.php/html/614`): `.kindUl li.kindLi h3` 로 공식 진료과명 수집

external_id: SARANG-{hash(name + primary_dept)}
  — 사이트에 원내코드가 노출되지 않음 (data-name=이름 뿐). 동명이인 대비 name+dept 해시.
  — 포맷 예: "SARANG-a3f8b2c1"

개별 교수 조회:
  의료진 전체 페이지 한 번만 GET 후 external_id 매칭 필터링 (페이지가 1개뿐이므로 규칙 위배 아님).
"""
import re
import hashlib
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "https://www.sarangmc.co.kr"
DOCTORS_URL = f"{BASE_URL}/index.php/html/615"
DEPTS_URL = f"{BASE_URL}/index.php/html/614"

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:30")}


def _short_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:10]


class SarangCrawler:
    """안산사랑의병원 크롤러 — 단일 페이지 정적 HTML"""

    def __init__(self):
        self.hospital_code = "SARANG"
        self.hospital_name = "안산사랑의병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    # ─── 내부 파서 ───

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "")).strip()

    def _parse_dkind(self, dkind_text: str) -> tuple[str, list[str], str]:
        """dKind 텍스트 → (primary_dept, all_depts, specialty_tag)

        예: "정형외과, 척추정형외과, 관절∙척추센터 / 정형외과 전문의"
          → ("정형외과", ["정형외과", "척추정형외과", "관절∙척추센터"], "정형외과 전문의")
        """
        t = self._clean(dkind_text)
        if not t:
            return "", [], ""
        parts = t.split("/", 1)
        left = parts[0].strip()
        right = parts[1].strip() if len(parts) > 1 else ""
        depts = [d.strip() for d in left.split(",") if d.strip()]
        primary = depts[0] if depts else ""
        return primary, depts, right

    def _parse_schedule_table(self, table) -> list[dict]:
        """table[summary='진료시간입니다.'] → schedules 리스트.

        헤더: 시간 | 월 | 화 | 수 | 목 | 금 | 토
        tbody의 첫 행 = 오전, 두 번째 행 = 오후.
        각 요일 td 의 텍스트 or data-text 로 셀 판정.
        """
        if table is None:
            return []
        tbody = table.find("tbody")
        if tbody is None:
            return []
        trs = tbody.find_all("tr", recursive=False)

        schedules: list[dict] = []
        for tr in trs:
            tds = tr.find_all("td", recursive=False)
            if len(tds) < 2:
                continue
            label = self._clean(tds[0].get_text(" ", strip=True))
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            else:
                continue
            start, end = TIME_RANGES[slot]

            # 월~토 = tds[1..6]
            day_cells = tds[1:7]
            for day_idx, cell in enumerate(day_cells):
                if day_idx > 5:
                    break
                text = self._clean(cell.get_text(" ", strip=True))
                if not text:
                    # data-text 보조 확인
                    text = self._clean(cell.get("data-text", ""))
                if not is_clinic_cell(text):
                    continue
                schedules.append({
                    "day_of_week": day_idx,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return schedules

    def _parse_doctor_pop_notes(self, pop_el) -> str:
        """doctorPop 안의 '전문분야' 내용을 짧게 요약해 notes 로 반환."""
        if pop_el is None:
            return ""
        for dl in pop_el.select(".docInfo dl"):
            dt = dl.find("dt")
            if not dt:
                continue
            dt_text = self._clean(dt.get_text(" ", strip=True))
            if "전문분야" in dt_text:
                dd = dl.find("dd")
                if dd:
                    txt = dd.get_text(" ", strip=True)
                    txt = re.sub(r"\s+", " ", txt).strip()
                    # 너무 길면 120자로 컷
                    if len(txt) > 120:
                        txt = txt[:120].rstrip() + "…"
                    return txt
        return ""

    def _parse_profile_box(self, box) -> dict | None:
        """.profileBox 1개 → doctor dict"""
        name_el = box.select_one(".profileTxt h3.dName strong")
        name = self._clean(name_el.get_text(strip=True)) if name_el else ""
        if not name:
            # data-name 폴백
            name = self._clean(box.get("data-name", ""))
        if not name:
            return None

        pos_el = box.select_one(".profileTxt h3.dName span")
        position = self._clean(pos_el.get_text(strip=True)) if pos_el else ""

        dkind_el = box.select_one(".profileTxt p.dKind")
        dkind_text = dkind_el.get_text(" ", strip=True) if dkind_el else ""
        primary_dept, all_depts, specialty_tag = self._parse_dkind(dkind_text)

        img_el = box.select_one(".profilePic img")
        profile_url = ""
        if img_el:
            src = (img_el.get("src") or "").strip()
            if src:
                profile_url = src if src.startswith("http") else f"{BASE_URL}{src}"

        pop_el = box.select_one("aside.doctorPop")
        notes = self._parse_doctor_pop_notes(pop_el)

        # 스케줄 테이블: doctorPop 안의 진료일정 테이블 우선
        schedules: list[dict] = []
        if pop_el is not None:
            table = pop_el.find("table", attrs={"summary": "진료시간입니다."})
            if table is None:
                # 폴백: class 로 시도
                table = pop_el.find("table", class_="depth02")
            schedules = self._parse_schedule_table(table)

        # external_id 생성 — name + primary_dept 해시 (동명이인 안전)
        hash_key = f"{name}|{primary_dept}"
        ext_id = f"SARANG-{_short_hash(hash_key)}"

        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": name,
            "department": primary_dept,
            "all_departments": all_depts,
            "position": position,
            "specialty": specialty_tag,
            "profile_url": profile_url,
            "notes": notes,
            "schedules": schedules,
            "date_schedules": [],
        }

    async def _fetch_doctors_soup(self, client: httpx.AsyncClient) -> BeautifulSoup | None:
        try:
            resp = await client.get(DOCTORS_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[SARANG] 의료진 페이지 로드 실패: {e}")
            return None
        # UTF-8 확인됨 — 그대로 파싱
        return BeautifulSoup(resp.text, "html.parser")

    async def _fetch_depts_soup(self, client: httpx.AsyncClient) -> BeautifulSoup | None:
        try:
            resp = await client.get(DEPTS_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[SARANG] 진료과 페이지 로드 실패: {e}")
            return None
        return BeautifulSoup(resp.text, "html.parser")

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            soup = await self._fetch_doctors_soup(client)

        if soup is None:
            self._cached_data = []
            return []

        result: list[dict] = []
        seen: set[str] = set()
        for box in soup.select("section.doctorSection .profileBox"):
            doc = self._parse_profile_box(box)
            if not doc:
                continue
            if doc["external_id"] in seen:
                continue
            seen.add(doc["external_id"])
            result.append(doc)

        logger.info(f"[SARANG] 총 {len(result)}명 수집")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        """진료과 목록 페이지에서 공식 진료과명 수집. 실패 시 의료진 페이지에서 파생."""
        async with self._make_client() as client:
            soup = await self._fetch_depts_soup(client)

        depts: list[str] = []
        if soup is not None:
            for h3 in soup.select(".kindUl li.kindLi h3"):
                name = self._clean(h3.get_text(strip=True))
                if name and name not in depts:
                    depts.append(name)

        if not depts:
            # 폴백: 의료진 페이지에서 primary_dept 집계
            data = await self._fetch_all()
            for d in data:
                dept = d.get("department", "")
                if dept and dept not in depts:
                    depts.append(dept)

        return [{"code": d, "name": d} for d in depts]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [
                d for d in data
                if d["department"] == department or department in d.get("all_departments", [])
            ]
        return [
            {
                "staff_id": d["staff_id"],
                "external_id": d["external_id"],
                "name": d["name"],
                "department": d["department"],
                "position": d.get("position", ""),
                "specialty": d.get("specialty", ""),
                "profile_url": d.get("profile_url", ""),
                "notes": d.get("notes", ""),
            }
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회 — 의료진 페이지 1회 GET 후 매칭 필터.

        사랑의병원은 전체 교수가 단일 URL 에 렌더되므로 페이지 1개만 가져오면 됨.
        (규칙 #7 "전체 크롤링 fallback 금지" 에 위배되지 않음: 단일 페이지 병원)
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 캐시 우선
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return self._to_result(d, staff_id)
            return empty

        async with self._make_client() as client:
            soup = await self._fetch_doctors_soup(client)
        if soup is None:
            return empty

        for box in soup.select("section.doctorSection .profileBox"):
            doc = self._parse_profile_box(box)
            if not doc:
                continue
            if doc["external_id"] == staff_id or doc["staff_id"] == staff_id:
                return self._to_result(doc, staff_id)

        return empty

    @staticmethod
    def _to_result(doc: dict, staff_id: str) -> dict:
        return {
            "staff_id": staff_id,
            "name": doc.get("name", ""),
            "department": doc.get("department", ""),
            "position": doc.get("position", ""),
            "specialty": doc.get("specialty", ""),
            "profile_url": doc.get("profile_url", ""),
            "notes": doc.get("notes", ""),
            "schedules": doc.get("schedules", []),
            "date_schedules": doc.get("date_schedules", []),
        }

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [
                d for d in data
                if d["department"] == department or department in d.get("all_departments", [])
            ]

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
