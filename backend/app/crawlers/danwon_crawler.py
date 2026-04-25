"""단원병원(Danwon Hospital) 크롤러

병원 공식명: 단원병원 (경기 안산시 단원구 원포공원1로 20)
홈페이지: www.dwhosp.co.kr (cafe24 호스팅 PHP, UTF-8)

구조:
  1) 진료과 목록: /page/1_0.php?pageIndex=100100 — 정적 nav 에 pageIndex 100101~100122 매핑
  2) 진료과별 의료진+스케줄: /page/1_{N}.php?pageIndex={PAGE_INDEX}
      `div.doctor-info-wrap > div.doctor-info` 카드 반복. 각 카드:
        - `.pull-left .img-wrap img` src=사진, alt=이름(폴백)
        - `.pull-left .doctor-record p` = 약력 (notes 로 사용 가능)
        - `.pull-right p`(첫번째) = 세부 진료과
        - `.pull-right h4` = "{이름} <em>{직책}</em>"
        - `.pull-right p.doctor-text` = 전문진료분야 (specialty)
        - `.pull-right table` = 시간표
            - thead 7열(월화수목금토일), tbody 2행(오전/오후)
            - `td.col1` 텍스트 "진료" = 외래
            - 빈 td / "내시경" / "수술" = 외래 아님

external_id: DANWON-{pageIndex}-{순번}
  — 진료과별 페이지 내 순번(index, 0-based)으로 동명이인 안전.
  개별 조회 시 external_id 의 pageIndex 로 해당 진료과 페이지 1회만 GET (skill 규칙 #7 준수).
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "https://www.dwhosp.co.kr"

# 진료과 목록 (pageIndex → 이름). 웹사이트 nav 기준, 외부 링크(소아청소년과: 별도 도메인) 제외.
# 순서는 external_id 안정성을 위해 절대 변경 금지 (추가/매핑 교체만 가능).
# slug_n = /page/1_{slug_n}.php 의 숫자
DEPT_MAP: list[tuple[int, int, str]] = [
    # (pageIndex, slug_n, 진료과명)
    (100101, 1,  "내과"),
    (100102, 2,  "심장내과"),
    (100103, 3,  "산부인과"),
    (100105, 5,  "신경과"),
    (100106, 6,  "신경외과"),
    (100107, 7,  "외과"),
    (100108, 8,  "재활의학과"),
    (100109, 9,  "정형외과"),
    (100110, 10, "심장혈관흉부외과"),
    (100111, 11, "응급의학과"),
    (100112, 12, "마취통증의학과"),
    (100113, 13, "영상의학과"),
    (100114, 14, "진단검사의학과"),
    (100115, 15, "피부·비뇨기과(원내의원)"),
    (100116, 16, "치과"),
    (100117, 17, "안과(원내의원)"),
    (100118, 18, "가정의학과"),
    (100119, 19, "정신건강의학과"),
    (100120, 20, "성형외과"),
    (100121, 21, "한방과"),
    (100122, 22, "혈관외과"),
    # 소아청소년과(100104)는 별도 도메인 www.dwkids.co.kr 이라 제외
]

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:30")}

# 월~일 헤더 순서 고정 (DANWON 은 일요일 컬럼도 포함하지만 schedules 는 일요일까지 수집)
# day_of_week: 0=월 ... 5=토, 6=일


class DanwonCrawler:
    """단원병원 크롤러 — 정적 HTML (httpx + BeautifulSoup)"""

    def __init__(self):
        self.hospital_code = "DANWON"
        self.hospital_name = "단원병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: list[dict] | None = None

    # ─── 내부 파서 ───

    @staticmethod
    def _dept_page_url(slug_n: int, page_index: int) -> str:
        return f"{BASE_URL}/page/1_{slug_n}.php?pageIndex={page_index}"

    def _parse_schedule_table(self, table) -> list[dict]:
        """의사 카드 안의 시간표 <table> → schedules dict 리스트"""
        if table is None:
            return []
        tbody = table.find("tbody") or table
        trs = tbody.find_all("tr", recursive=False) or tbody.find_all("tr")
        schedules: list[dict] = []
        for tr in trs:
            th = tr.find("th")
            if not th:
                continue
            label = th.get_text(strip=True)
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            else:
                continue
            tds = tr.find_all("td")
            # 월~일 (최대 7칸). 사이트는 일요일 칸도 존재
            for dow, td in enumerate(tds[:7]):
                text = td.get_text(" ", strip=True)
                if not is_clinic_cell(text):
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

    def _parse_doctor_card(
        self, card, dept_name_fallback: str, page_index: int, seq: int,
    ) -> dict | None:
        """div.doctor-info 1개 → 의사 dict"""
        pull_right = card.select_one(".pull-right")
        if pull_right is None:
            return None

        # 이름 + 직책
        h4 = pull_right.find("h4")
        name = ""
        position = ""
        if h4 is not None:
            em = h4.find("em")
            if em is not None:
                position = em.get_text(" ", strip=True)
                em_text = em.get_text()
                full = h4.get_text(" ", strip=True)
                # em 텍스트 제거 후 남는 게 이름
                name = full.replace(em_text, "").strip()
            else:
                name = h4.get_text(" ", strip=True)

        if not name:
            # 폴백: img alt
            img = card.select_one(".img-wrap img")
            if img is not None:
                name = (img.get("alt", "") or "").strip()
        if not name:
            return None

        # 세부 진료과 — pull-right 의 첫번째 <p> (h4 앞). 없으면 상위 진료과명 사용
        sub_dept = ""
        first_p = None
        for child in pull_right.children:
            if getattr(child, "name", None) == "p":
                first_p = child
                break
        if first_p is not None:
            sub_dept = first_p.get_text(" ", strip=True)
        department = sub_dept or dept_name_fallback

        # 전문진료분야
        specialty = ""
        spec_el = pull_right.select_one("p.doctor-text")
        if spec_el is not None:
            # <br> 을 공백으로
            copy = BeautifulSoup(str(spec_el), "html.parser")
            for br in copy.find_all("br"):
                br.replace_with(" ")
            specialty = copy.get_text(" ", strip=True)
            # 공백 정리
            specialty = re.sub(r"\s+", " ", specialty).strip()

        # 약력(notes) — 길어질 수 있어 너무 길면 컷
        notes = ""
        record_el = card.select_one(".doctor-record p")
        if record_el is not None:
            copy = BeautifulSoup(str(record_el), "html.parser")
            for br in copy.find_all("br"):
                br.replace_with(" / ")
            notes = copy.get_text(" ", strip=True)
            notes = re.sub(r"\s+", " ", notes).strip()
            if len(notes) > 500:
                notes = notes[:497] + "..."

        # 사진 URL
        photo_url = ""
        img = card.select_one(".img-wrap img")
        if img is not None:
            src = img.get("src", "") or ""
            if src.startswith("../"):
                photo_url = f"{BASE_URL}/{src[3:]}"
            elif src.startswith("/"):
                photo_url = f"{BASE_URL}{src}"
            elif src.startswith("http"):
                photo_url = src

        # 스케줄
        table = pull_right.find("table")
        schedules = self._parse_schedule_table(table)

        ext_id = f"{self.hospital_code}-{page_index}-{seq}"
        profile_url = f"{BASE_URL}/page/1_0.php?pageIndex={page_index}"

        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": name,
            "department": department,
            "position": position,
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": notes,
            "schedules": schedules,
            "date_schedules": [],
        }

    def _parse_dept_page(self, html: str, dept_name: str, page_index: int) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.doctor-info")
        results: list[dict] = []
        for seq, card in enumerate(cards):
            doc = self._parse_doctor_card(card, dept_name, page_index, seq)
            if doc is None:
                continue
            results.append(doc)
        return results

    # ─── 네트워크 ───

    async def _fetch_dept(
        self,
        client: httpx.AsyncClient,
        slug_n: int,
        page_index: int,
        dept_name: str,
    ) -> list[dict]:
        url = self._dept_page_url(slug_n, page_index)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[DANWON] {dept_name}({page_index}) 실패: {e}")
            return []
        try:
            return self._parse_dept_page(resp.text, dept_name, page_index)
        except Exception as e:
            logger.error(f"[DANWON] {dept_name}({page_index}) 파싱 실패: {e}")
            return []

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            results = await asyncio.gather(
                *[
                    self._fetch_dept(client, slug_n, page_idx, dept_name)
                    for page_idx, slug_n, dept_name in DEPT_MAP
                ],
                return_exceptions=True,
            )

        for res in results:
            if isinstance(res, Exception):
                continue
            for d in res:
                key = d["external_id"]
                if key not in all_doctors:
                    all_doctors[key] = d

        result = list(all_doctors.values())
        logger.info(f"[DANWON] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        """진료과 목록 — 홈페이지 nav 기준 하드코딩. 코드=pageIndex 문자열, 이름=한글."""
        return [{"code": str(page_idx), "name": name} for page_idx, _, name in DEPT_MAP]

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
        """개별 조회 — external_id 의 pageIndex 로 해당 진료과 페이지 1회 GET"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 인스턴스 내 캐시가 있으면 활용
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

        m = re.match(r"^DANWON-(\d+)-(\d+)$", staff_id)
        if not m:
            return empty
        page_index = int(m.group(1))
        seq = int(m.group(2))

        # pageIndex → (slug_n, dept_name) 매핑
        slug_n = None
        dept_name = None
        for pi, sn, dn in DEPT_MAP:
            if pi == page_index:
                slug_n = sn
                dept_name = dn
                break
        if slug_n is None:
            return empty

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            doctors = await self._fetch_dept(client, slug_n, page_index, dept_name)

        for d in doctors:
            if d["external_id"] == staff_id:
                return {
                    "staff_id": staff_id,
                    "name": d["name"],
                    "department": d["department"],
                    "position": d["position"],
                    "specialty": d["specialty"],
                    "profile_url": d["profile_url"],
                    "notes": d["notes"],
                    "schedules": d["schedules"],
                    "date_schedules": d["date_schedules"],
                }
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
