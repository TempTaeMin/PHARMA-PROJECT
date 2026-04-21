"""서울부민병원(BUMIN) 크롤러

병원 공식명: 서울부민병원 (서울 강서구 등촌동)
홈페이지: bumin.co.kr/seoul (JSP, 정적 HTML, UTF-8)

구조:
- 목록: POST `/seoul/medical/profList.do` 에 `siteNo=001000000&page={N}` 전송
  페이지 6개, 각 10명씩 수록. 의사별 `<table class="tb">` 에 주간 진료시간표가 inline 렌더.
- 상세: GET `/seoul/medical/profView.do?siteNo=...&deptNo=...&profNo=...&profEmpNo=...&scheDd=YYYY-MM&dpCd=...`
  (목록 페이지에 이미 스케줄이 들어있어서 상세를 따로 호출할 필요 없음)
- 각 의사 카드:
    p.doctor_part  → "{position} / {dept}" 형식
    p.doctor_name  → 이름
    p.doctor_explain → 전문분야(specialty)
    onclick=fn_DeatilPop(siteNo, deptNo, profNo, profEmpNo, emrDpCd)
    table.tb > tbody > tr (오전/오후 라벨 행 + 요일 7개 td)
- 스케줄 셀: `<img alt="외래">` 있으면 진료, 빈 셀이면 휴진

external_id: BUMIN-{deptNo}-{profNo}  (profEmpNo 는 상세조회용으로 id 내부 보관 생략)
- 개별 조회는 해당 (deptNo, profNo) 의 의사 한 명을 담은 목록 페이지만 역으로 호출할 수 없는 구조라,
  목록 전체를 6 페이지 GET 해야 함. 페이지 수 적고 한 번에 모든 의사가 들어있어 rule #7 취지 준수.
"""
from __future__ import annotations

import re
import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://bumin.co.kr"
LIST_URL = f"{BASE_URL}/seoul/medical/profList.do"

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:30")}
DAYS = ["월", "화", "수", "목", "금", "토"]

_DETAIL_PAT = re.compile(
    r"fn_DeatilPop\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*\)"
)


class BuminCrawler:
    def __init__(self):
        self.hospital_code = "BUMIN"
        self.hospital_name = "서울부민병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/seoul/",
        }
        self._cached_data: list[dict] | None = None

    def _parse_doctor_li(self, li) -> dict | None:
        part = li.select_one("p.doctor_part")
        name_el = li.select_one("p.doctor_name")
        if not part or not name_el:
            return None
        part_text = part.get_text(" ", strip=True)
        name = name_el.get_text(" ", strip=True).split()[0] if name_el.get_text(strip=True) else ""
        if not name:
            return None

        # "{position} / {dept}" 또는 단일 "{dept}" 형태
        if "/" in part_text:
            position, dept = [s.strip() for s in part_text.split("/", 1)]
        else:
            position, dept = "", part_text

        specialty_el = li.select_one("p.doctor_explain")
        specialty = specialty_el.get_text(" ", strip=True) if specialty_el else ""

        # 상세 파라미터
        detail_btn = li.find("a", onclick=True)
        site_no, dept_no, prof_no, prof_emp_no, dp_cd = "", "", "", "", ""
        if detail_btn:
            m = _DETAIL_PAT.search(detail_btn.get("onclick", ""))
            if m:
                site_no, dept_no, prof_no, prof_emp_no, dp_cd = m.groups()
        if not dept_no or not prof_no:
            return None

        external_id = f"{self.hospital_code}-{dept_no}-{prof_no}"

        # 스케줄 파싱
        schedules: list[dict] = []
        tbl = li.find("table", class_="tb")
        if tbl:
            tbody = tbl.find("tbody") or tbl
            for tr in tbody.find_all("tr"):
                th = tr.find("th")
                if not th:
                    continue
                label = th.get_text(" ", strip=True).replace("\u00a0", "").replace(" ", "")
                if "오전" in label:
                    slot = "morning"
                elif "오후" in label:
                    slot = "afternoon"
                else:
                    continue
                tds = tr.find_all("td")
                if len(tds) < 6:
                    continue
                for dow, td in enumerate(tds[:6]):
                    img = td.find("img")
                    text = td.get_text(" ", strip=True)
                    # 진료 표시: <img alt="외래"> 또는 "외래"/"진료" 텍스트
                    working = False
                    if img and img.get("alt"):
                        alt = img["alt"].strip()
                        if alt and "휴" not in alt:
                            working = True
                    if not working and any(k in text for k in ("외래", "진료", "수술")):
                        if "휴" not in text:
                            working = True
                    if not working:
                        continue
                    s, e = TIME_RANGES[slot]
                    schedules.append({
                        "day_of_week": dow, "time_slot": slot,
                        "start_time": s, "end_time": e, "location": "",
                    })

        detail_params = {
            "siteNo": site_no or "001000000",
            "deptNo": dept_no,
            "profNo": prof_no,
            "profEmpNo": prof_emp_no,
            "dpCd": dp_cd,
        }
        profile_url = (
            f"{BASE_URL}/seoul/medical/profView.do?siteNo={detail_params['siteNo']}"
            f"&deptNo={dept_no}&profNo={prof_no}&profEmpNo={prof_emp_no}"
            f"&dpCd={dp_cd}&scheDd={datetime.utcnow().strftime('%Y-%m')}"
        )

        return {
            "staff_id": external_id,
            "external_id": external_id,
            "name": name,
            "department": dept,
            "position": position,
            "specialty": specialty,
            "profile_url": profile_url,
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
        }

    def _parse_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        result: list[dict] = []
        for ul in soup.select("ul.doctor_list"):
            for li in ul.find_all("li", recursive=False):
                doc = self._parse_doctor_li(li)
                if doc:
                    result.append(doc)
        return result

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data
        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            for page in range(1, 11):  # 최대 10 페이지까지만 시도
                try:
                    resp = await client.post(
                        LIST_URL,
                        data={"siteNo": "001000000", "page": str(page)},
                    )
                    resp.raise_for_status()
                except Exception as e:
                    logger.warning(f"[BUMIN] page={page} 실패: {e}")
                    break
                html = resp.content.decode("utf-8", errors="replace")
                parsed = self._parse_page(html)
                if not parsed:
                    break
                added = 0
                for doc in parsed:
                    if doc["external_id"] not in all_doctors:
                        all_doctors[doc["external_id"]] = doc
                        added += 1
                logger.info(f"[BUMIN] page={page} parsed={len(parsed)} new={added}")
                if added == 0:
                    break  # 동일 페이지 반복 (마지막 페이지 초과) → 중단
        result = list(all_doctors.values())
        logger.info(f"[BUMIN] 총 {len(result)}명")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        depts = sorted({d["department"] for d in data if d["department"]})
        return [{"code": dn, "name": dn} for dn in depts]

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
        """개별 조회 — 목록 전체 (6 페이지) 에서 external_id 필터.

        의사별 상세 URL(profView.do) 은 별도 페이지지만 스케줄 정보는 목록 페이지에 이미
        들어있고, 목록 페이지 1장당 전 페이지를 훑어야 하는 구조. 전체 페이지 수가 6 개 내외
        로 소수여서 단일 의사 조회 시에도 목록 전체를 받고 필터링한다.
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }
        data = await self._fetch_all()
        for d in data:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
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
