"""한도병원(Handoh Hospital) 크롤러

병원 공식명: 한도병원 (경기)
홈페이지: www.handoh.com  (PHP, UTF-8)
기술: 정적 HTML (httpx + BeautifulSoup)

구조:
  1) 진료과 목록: /sub_treatment/department.php
       `ul` 내부 `li.ssm_{cate}` > `a[href*="department_view.php?cate={cate}"]`
       cate 예: "0001_" (소화기내과), "0002_" (심장내과) ...
  2) 전체 의료진 + 스케줄: /sub_treatment/department_view.php  (쿼리 없음 = 전체)
     진료과별: /sub_treatment/department_view.php?cate={cate}
       `div.doctor_wrap` 블록 = 진료과 1개
         - `p.tit` 텍스트 = "{진료과명} 의료진 소개"
         - `ul.sub_doctors > li` = 의사 카드
             - `p.t1` = 직책(예: "소화기센터 명예원장/센터장")
             - `p.t2` = 이름
             - `p.t3` = 전문분야
             - `p.t4` = 전화번호/진료일정 등
             - `table.board_st.st1` = 진료시간표 (월~토, 오전/오후)
                 셀: `<p class="cir flex vc hc jin">진료</p>`
                      `<p class="cir flex vc hc si">시술</p>`
                      `<p class="cir flex vc hc no">휴무</p>`
                      빈 `<p class="cir ...">` = 진료 없음
             - 약력/진료시간표 링크: `pop_pro.php?number={doc_no}` / `pop_hours.php?number={doc_no}`

external_id: HANDOH-{cate}-{doc_no}
  - cate: 진료과 코드(예 "0001_") — 개별 조회 시 해당 진료과만 요청
  - doc_no: pop_pro.php?number= 값. 동일 병원 내 고유.
  폴백: HANDOH-{cate}-n-{name} (doc_no 추출 실패 시)
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "http://www.handoh.com"
DEPT_LIST_URL = f"{BASE_URL}/sub_treatment/department.php"
DOCTORS_URL = f"{BASE_URL}/sub_treatment/department_view.php"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 헤더 요일 순서(월~토)
DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}

DOC_NO_RE = re.compile(r"number=(\d+)")
CATE_RE = re.compile(r"cate=([0-9A-Za-z_]+)")


class HandohCrawler:
    """한도병원 크롤러 — 정적 HTML, cate 쿼리 파라미터 기반"""

    def __init__(self):
        self.hospital_code = "HANDOH"
        self.hospital_name = "한도병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: list[dict] | None = None
        self._cached_departments: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    def _parse_soup(self, content: bytes | str) -> BeautifulSoup:
        """인코딩 안전하게 파싱. 한도병원은 UTF-8이지만 혹시 모를 EUC-KR 대비."""
        if isinstance(content, bytes):
            # httpx 가 자동 디코드 실패한 경우 대비하여 content 로 받을 경우
            try:
                return BeautifulSoup(content, "html.parser")
            except Exception:
                return BeautifulSoup(content, "html.parser", from_encoding="euc-kr")
        return BeautifulSoup(content, "html.parser")

    # ─── 진료과 파싱 ───

    async def _fetch_departments(self, client: httpx.AsyncClient) -> list[dict]:
        if self._cached_departments is not None:
            return self._cached_departments
        try:
            resp = await client.get(DEPT_LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[HANDOH] 진료과 목록 로드 실패: {e}")
            self._cached_departments = []
            return []

        soup = self._parse_soup(resp.text)
        depts: list[dict] = []
        seen_codes: set[str] = set()

        for a in soup.select('a[href*="department_view.php"]'):
            href = a.get("href", "")
            m = CATE_RE.search(href)
            if not m:
                continue
            cate = m.group(1)
            # 주석으로만 남아있는 비활성 항목 제거 — BeautifulSoup 은 주석 안쪽을 파싱하지 않으므로 자동 제외됨
            name_el = a.select_one("span.tt")
            name = name_el.get_text(strip=True) if name_el else a.get_text(strip=True)
            if not name:
                continue
            if cate in seen_codes:
                continue
            seen_codes.add(cate)
            depts.append({"code": cate, "name": name})

        self._cached_departments = depts
        return depts

    # ─── 의사 카드 파싱 ───

    def _parse_schedule_table(self, table) -> list[dict]:
        """table.board_st.st1 → schedules 리스트.
        행 구조:
          tr[0]: thead (구분, 월, 화, 수, 목, 금, 토)
          tbody tr[0]: td[0]=오전, td[1..6]=월..토
          tbody tr[1]: td[0]=오후, td[1..6]=월..토
        """
        if table is None:
            return []
        tbody = table.find("tbody")
        if tbody is None:
            return []
        rows = tbody.find_all("tr", recursive=False)

        schedules: list[dict] = []
        for row in rows:
            tds = row.find_all("td", recursive=False)
            if len(tds) < 7:
                continue
            label = tds[0].get_text(strip=True)
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            else:
                continue
            start, end = TIME_RANGES[slot]
            for di, cell in enumerate(tds[1:7]):
                text = cell.get_text(" ", strip=True)
                if not is_clinic_cell(text):
                    continue
                schedules.append({
                    "day_of_week": di,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return schedules

    def _parse_doctor_li(self, li, dept_name: str, cate: str) -> dict | None:
        info = li.select_one("div.doc_info_wrap .info") or li.select_one(".info")
        if info is None:
            return None
        name_el = info.select_one("p.t2")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            return None
        pos_el = info.select_one("p.t1")
        position = pos_el.get_text(strip=True) if pos_el else ""
        spec_el = info.select_one("p.t3")
        specialty = spec_el.get_text(strip=True) if spec_el else ""

        # notes: t4 값들(전화번호 / 진료일정) 결합
        t4_parts: list[str] = []
        for t4 in info.select("p.t4"):
            text = t4.get_text(" ", strip=True)
            if text:
                t4_parts.append(text)
        notes = " / ".join(t4_parts)

        # doc_no 추출 — pop_pro.php?number=NN 링크에서
        doc_no = ""
        for a in li.select('a[href*="pop_pro.php"], a[href*="pop_hours.php"]'):
            href = a.get("href", "")
            m = DOC_NO_RE.search(href)
            if m:
                doc_no = m.group(1)
                break

        # 사진
        img = li.select_one("div.img_wrap img")
        img_src = img.get("src", "") if img else ""
        photo_url = ""
        if img_src:
            if img_src.startswith("http"):
                photo_url = img_src
            elif img_src.startswith("../"):
                photo_url = f"{BASE_URL}/{img_src[3:]}"
            elif img_src.startswith("/"):
                photo_url = f"{BASE_URL}{img_src}"
            else:
                photo_url = f"{BASE_URL}/{img_src}"

        # 스케줄 테이블
        table = li.select_one("table.board_st.st1") or li.select_one("table.board_st")
        schedules = self._parse_schedule_table(table)

        ident = doc_no if doc_no else f"n-{name}"
        external_id = f"{self.hospital_code}-{cate}-{ident}"

        return {
            "staff_id": external_id,
            "external_id": external_id,
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": specialty,
            "profile_url": f"{DOCTORS_URL}?cate={cate}",
            "photo_url": photo_url,
            "notes": notes,
            "schedules": schedules,
            "date_schedules": [],
            "_cate": cate,
            "_doc_no": doc_no,
        }

    def _parse_doctors_page(self, soup: BeautifulSoup) -> list[dict]:
        """department_view.php 페이지 전체를 파싱.
        `div.doctor_wrap` 하나 = 진료과 하나. 각 블록 안에 `ul.sub_doctors > li` 가 의사 카드.
        """
        result: list[dict] = []
        seen: set[str] = set()
        for block in soup.select("div.doctor_wrap"):
            title_el = block.select_one("p.tit")
            title = title_el.get_text(strip=True) if title_el else ""
            # "소화기내과 의료진 소개" → "소화기내과"
            dept_name = re.sub(r"\s*의료진\s*소개\s*$", "", title).strip()
            if not dept_name:
                dept_name = title

            # 해당 블록에 속하는 진료과 cate 코드를 찾기 — 진료과 목록 캐시에서 역매핑
            cate = self._dept_name_to_cate(dept_name)

            for li in block.select("ul.sub_doctors > li"):
                doc = self._parse_doctor_li(li, dept_name, cate)
                if not doc:
                    continue
                ext = doc["external_id"]
                if ext in seen:
                    continue
                seen.add(ext)
                result.append(doc)
        return result

    def _dept_name_to_cate(self, dept_name: str) -> str:
        """진료과명 → cate 코드. 캐시에 없으면 이름 해시로 폴백."""
        if self._cached_departments:
            for d in self._cached_departments:
                if d["name"] == dept_name:
                    return d["code"]
        # 폴백: 이름 그대로 — 후속 조회 시 cate 파라미터 없이 전체 페이지를 파싱하게 됨
        return dept_name or "UNKNOWN"

    # ─── 전체 크롤링 ───

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            # 먼저 진료과 목록 확보 (이름→cate 매핑용)
            await self._fetch_departments(client)
            try:
                resp = await client.get(DOCTORS_URL)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[HANDOH] 의료진 페이지 로드 실패: {e}")
                self._cached_data = []
                return []

            soup = self._parse_soup(resp.text)

        result = self._parse_doctors_page(soup)
        logger.info(f"[HANDOH] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            depts = await self._fetch_departments(client)
        return [{"code": d["code"], "name": d["name"]} for d in depts]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {k: d.get(k, "") for k in ("staff_id", "external_id", "name", "department",
                                        "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회.
        external_id 포맷: HANDOH-{cate}-{doc_no|n-name}
        cate 가 추출되면 해당 진료과 페이지만 요청. 전체 _fetch_all() 호출 금지.
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 내 캐시 우선
        if self._cached_data is not None:
            for d in self._cached_data:
                if d.get("staff_id") == staff_id or d.get("external_id") == staff_id:
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

        # external_id 파싱: HANDOH-{cate}-{rest}
        prefix = f"{self.hospital_code}-"
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        cate = ""
        rest = ""
        # cate 는 영숫자+언더스코어, '-' 로 구분
        m = re.match(r"([0-9A-Za-z_]+?)-(.+)$", raw)
        if m:
            cate = m.group(1)
            rest = m.group(2)
        else:
            cate = ""
            rest = raw

        # 해당 진료과 페이지만 요청 (cate 있으면)
        url = f"{DOCTORS_URL}?cate={cate}" if cate else DOCTORS_URL
        async with self._make_client() as client:
            # 진료과명 매핑을 위해 depts 도 확보 (가볍게 1회)
            await self._fetch_departments(client)
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[HANDOH] 개별 조회 페이지 로드 실패 {staff_id}: {e}")
                return empty

            soup = self._parse_soup(resp.text)

        try:
            doctors = self._parse_doctors_page(soup)
        except Exception as e:
            logger.error(f"[HANDOH] 개별 조회 파싱 실패 {staff_id}: {e}")
            return empty

        # 1차: external_id 정확 일치
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

        # 2차: doc_no 또는 이름 기반 매칭 (폴백)
        if rest:
            if rest.startswith("n-"):
                target_name = rest[2:]
                for d in doctors:
                    if d["name"] == target_name:
                        return {
                            "staff_id": staff_id, "name": d["name"],
                            "department": d["department"], "position": d["position"],
                            "specialty": d["specialty"], "profile_url": d["profile_url"],
                            "notes": d["notes"], "schedules": d["schedules"],
                            "date_schedules": d["date_schedules"],
                        }
            else:
                for d in doctors:
                    if d.get("_doc_no") == rest:
                        return {
                            "staff_id": staff_id, "name": d["name"],
                            "department": d["department"], "position": d["position"],
                            "specialty": d["specialty"], "profile_url": d["profile_url"],
                            "notes": d["notes"], "schedules": d["schedules"],
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
