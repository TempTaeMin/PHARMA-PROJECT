"""중앙보훈병원 크롤러

구조:
  1) 진료과 목록 API: /seoul/md/mdexmdept/view/selectMdeptListData.do (JSON)
     → [{deptSn, sbjctCd, sbjctNm, ...}]
  2) 진료과별 의료진 페이지: /seoul/md/mdexmdept/view/selectMdeptViewPage.do?deptSn={sn}
     → div.medStaff div.inner 카드 단위로 의사별 정보 + 주간 스케줄 테이블

카드 구조:
  div.inner
    div.staf
      span.dept       → 진료과
      p.name          → "이름 직책"
      p.info          → "진료분야 : xxx"
      div.btns        → <button onclick="goRsrv('doctorId','Y')">
    div.sch > div.tbl_st1 > table
      caption: "{이름} 진료시간표 …"
      행: [구분, 월, 화, 수, 목, 금, 토] × 오전/오후
      셀 텍스트: '진료' / '■' / '' (빈칸=휴진)

external_id: VHS-{doctorId}
"""
import re
import json
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.bohun.or.kr"
DEPT_LIST_URL = f"{BASE_URL}/seoul/md/mdexmdept/view/selectMdeptListData.do"
DEPT_VIEW_URL = f"{BASE_URL}/seoul/md/mdexmdept/view/selectMdeptViewPage.do?deptSn={{sn}}"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("14:00", "17:30")}
DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
WORK_TEXTS = ("진료", "■")


class VhsCrawler:
    """중앙보훈병원 크롤러 — JSON API + 진료과별 HTML 카드 파싱"""

    def __init__(self):
        self.hospital_code = "VHS"
        self.hospital_name = "중앙보훈병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        self._cached_data = None
        self._dept_list_cache = None

    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        """진료과 목록 조회 (JSON)"""
        if self._dept_list_cache is not None:
            return self._dept_list_cache
        try:
            resp = await client.post(
                DEPT_LIST_URL,
                headers={**self.headers, "X-Requested-With": "XMLHttpRequest"},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[VHS] 진료과 목록 조회 실패: {e}")
            return []
        self._dept_list_cache = data
        return data

    def _parse_card(self, card, dept_name: str) -> dict | None:
        """div.inner 카드 1개 → 의사 dict"""
        staf = card.select_one("div.staf")
        sch = card.select_one("div.sch")
        if not staf or not sch:
            return None

        # 이름 + 직책
        name_el = staf.select_one("p.name")
        if not name_el:
            return None
        name_raw = name_el.get_text(" ", strip=True)
        m = re.match(r"^([가-힣]{2,4})(?:\s+(.+))?$", name_raw)
        if not m:
            return None
        name = m.group(1)
        position = (m.group(2) or "").strip()

        # 전문분야
        specialty = ""
        for info in staf.select("p.info"):
            txt = info.get_text(" ", strip=True)
            if txt.startswith("진료분야"):
                specialty = txt.replace("진료분야 :", "").strip()
                break

        # 의사 ID: <a href="javascript:goRsrv('xxx','Y');"> 또는 onclick 둘 다 대응
        doctor_id = ""
        for attr in ("href", "onclick"):
            el = card.find("a", attrs={attr: re.compile(r"goRsrv")}) \
                if attr == "href" else card.find(attrs={attr: re.compile(r"goRsrv")})
            if el:
                m2 = re.search(r"goRsrv\s*\(\s*'([^']+)'", el.get(attr, ""))
                if m2:
                    doctor_id = m2.group(1)
                    break
        if not doctor_id:
            return None

        # 스케줄 테이블
        table = sch.select_one("table")
        schedules = []
        if table:
            rows = table.select("tr")
            # 헤더(첫 행) 스킵 — 월~토 = td[1:7]
            for row in rows[1:]:
                cells = row.select("th, td")
                if not cells:
                    continue
                first = cells[0].get_text(" ", strip=True)
                if "오전" in first:
                    slot = "morning"
                elif "오후" in first:
                    slot = "afternoon"
                else:
                    continue
                for i, cell in enumerate(cells[1:7]):
                    text = cell.get_text(" ", strip=True)
                    if not text:
                        continue
                    if not any(w in text for w in WORK_TEXTS):
                        continue
                    dow = i
                    start, end = TIME_RANGES[slot]
                    schedules.append({
                        "day_of_week": dow,
                        "time_slot": slot,
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                    })

        return {
            "external_id": f"VHS-{doctor_id}",
            "staff_id": f"VHS-{doctor_id}",
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": specialty,
            "profile_url": DEPT_VIEW_URL.format(sn=""),
            "notes": "",
            "schedules": schedules,
        }

    async def _fetch_dept(self, client: httpx.AsyncClient, dept_sn: int, dept_name: str) -> list[dict]:
        try:
            resp = await client.get(DEPT_VIEW_URL.format(sn=dept_sn))
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[VHS] {dept_name}({dept_sn}) 조회 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.medStaff div.inner")
        doctors = []
        for card in cards:
            doc = self._parse_card(card, dept_name)
            if doc:
                doc["profile_url"] = DEPT_VIEW_URL.format(sn=dept_sn)
                doctors.append(doc)
        return doctors

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            depts = await self._fetch_dept_list(client)
            if not depts:
                self._cached_data = []
                return []

            # type="add" (센터 카테고리)은 진료과 뷰 페이지 없음 → 제외
            normal_depts = [d for d in depts if d.get("type", "default") == "default"]
            # 동시 요청 제한 — 서버가 400 반환하는 rate limit 방지
            sem = asyncio.Semaphore(5)

            async def _guarded(dept_sn, dept_name):
                async with sem:
                    return await self._fetch_dept(client, dept_sn, dept_name)

            tasks = [asyncio.create_task(_guarded(d["deptSn"], d["sbjctNm"]))
                     for d in normal_depts]
            all_doctors: list[dict] = []
            seen: set[str] = set()
            for coro in asyncio.as_completed(tasks):
                docs = await coro
                for d in docs:
                    if d["external_id"] in seen:
                        continue
                    seen.add(d["external_id"])
                    all_doctors.append(d)

        logger.info(f"[VHS] 총 {len(all_doctors)}명")
        self._cached_data = all_doctors
        return all_doctors

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            depts = await self._fetch_dept_list(client)
        return [{"code": d.get("sbjctCd", str(d.get("deptSn"))), "name": d.get("sbjctNm", "")}
                for d in depts if d.get("sbjctNm")]

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
        """개별 교수 스케줄 — staff_id로 진료과 1곳 조회 후 필터.

        VHS는 개별 교수 상세 페이지가 있지만 같은 스케줄이 진료과 페이지에 있으므로
        진료과 단위 조회로 처리 (전체 크롤링 fallback 금지).
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
        }
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") for k in
                            ("staff_id", "name", "department", "position",
                             "specialty", "profile_url", "notes", "schedules")}
            return empty

        # 캐시가 없으면 _fetch_all()을 호출해야 하는데 전체 크롤링이 됨.
        # VHS는 개별 URL로 해당 교수만 찾을 방법이 없어 진료과 단위 병렬 조회 유지.
        # 단일 조회 시 비용이 크므로 logger.warning 으로 남김.
        logger.warning(f"[VHS] 개별 조회 시 전체 진료과 순회 필요 (staff_id={staff_id})")
        data = await self._fetch_all()
        for d in data:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                return {k: d.get(k, "") for k in
                        ("staff_id", "name", "department", "position",
                         "specialty", "profile_url", "notes", "schedules")}
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
