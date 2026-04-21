"""경찰병원 크롤러

구조:
  1) 진료과 목록: /nph/med/dept/list.do?menuNo=200140 → dcDept 코드 31개
  2) 진료과별 의료진+스케줄: /nph/med/doctor/treatment.do?menuNo=200163&dcDept={code}
     테이블: 의료진(rowspan=2) | 선택진료 | 주(오전/오후) | 월~토 | 전문분야(rowspan=2) | 예약
     스케줄 셀에는 `<img alt="이름 오전/오후 요일 예약가능" src=".../circle.png">` 가 있음

개별 교수 조회: 진료과 1곳만 조회 → dcDept 파라미터 필터.
external_id: NPH-{dcDept}{원내코드} (goTreat('01100','2005011') → dcDept + medDr)
"""
import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.nph.go.kr"
DEPT_LIST_URL = f"{BASE_URL}/nph/med/dept/list.do?menuNo=200140"
TREATMENT_URL = f"{BASE_URL}/nph/med/doctor/treatment.do?menuNo=200163&dcDept={{code}}"

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("14:00", "17:30")}
DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}


class NphCrawler:
    """경찰병원 크롤러 — 진료과별 HTML 테이블 + 이미지 alt 속성 파싱"""

    def __init__(self):
        self.hospital_code = "NPH"
        self.hospital_name = "경찰병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        self._cached_data = None

    async def _fetch_dept_codes(self, client: httpx.AsyncClient) -> list[tuple[str, str]]:
        """진료과 목록 페이지에서 (dcDept코드, 진료과명) 추출"""
        resp = await client.get(DEPT_LIST_URL)
        resp.raise_for_status()
        html = resp.text
        found: dict[str, str] = {}
        for m in re.finditer(r'menuNo=\d+&dcDept=(\d+)', html):
            code = m.group(1)
            # 진료과명 찾기 — 링크 주변 텍스트
            if code in found:
                continue
            # 해당 위치 앞/뒤 100자 내에서 진료과명 후보 추출
            pos = m.start()
            near = html[max(0, pos - 200):pos + 200]
            soup = BeautifulSoup(near, "html.parser")
            text = soup.get_text(" ", strip=True)
            # "…과" 로 끝나는 단어
            name_match = re.search(r'([가-힣]{2,10}(?:내과|외과|과|실|센터))\s*(?:\d*)\s*$', text.split("menuNo")[0])
            if name_match:
                found[code] = name_match.group(1)
        # 텍스트 매칭 실패 시 전체 soup에서 링크 순회
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select('a[href*="dcDept="]'):
            m = re.search(r'dcDept=(\d+)', a.get("href", ""))
            if not m:
                continue
            t = a.get_text(" ", strip=True)
            if t and len(t) < 20:
                # "순환기내과 내과" 같은 중복어 정리 — 첫 토큰만 사용
                first = t.split()[0] if t.split() else t
                found[m.group(1)] = first
        return list(found.items())

    def _parse_treatment_table(self, table, dept_code: str, dept_name: str) -> list[dict]:
        """treatment.do 의 의료진 스케줄 테이블 파싱.

        행 구조:
          헤더 1행: [의료진, 선택진료, 주, 월, 화, 수, 목, 금, 토, 전문분야, 예약]
          의사 2행:
            오전 행: [이름(rs=2), 선택(rs=2), '오전', 월, 화, 수, 목, 금, 토, 전문(rs=2), 예약(rs=2)]
            오후 행: ['오후', 월, 화, 수, 목, 금, 토]
        스케줄 셀 내부:
          <img alt="이름 오전/오후 요일 예약가능" src="/static/img/nph/sub/circle.png">
        """
        rows = table.select("tr")
        if len(rows) < 2:
            return []

        doctors: list[dict] = []
        current: dict | None = None

        for row in rows[1:]:
            cells = row.select("th, td")
            if not cells:
                continue
            first = cells[0].get_text(" ", strip=True)

            if first in ("오전", "오후"):
                # 의사의 오후 행 — 월~토 = cells[1:7]
                if current is None:
                    continue
                slot = "morning" if first == "오전" else "afternoon"
                schedule_cells = cells[1:7]
            else:
                # 새 의사 행 — 이름 + 선택진료 + 오전 레이블 + 월~토 + 전문분야 + 예약
                name = first
                if not name or len(name) > 10:
                    continue
                # 예약 버튼에서 원내 ID 추출
                res_id = ""
                resv = row.select_one('a[onclick*="goTreat"]')
                if resv:
                    m = re.search(r"goTreat\('(\d+)','(\d+)'\)", resv.get("onclick", ""))
                    if m:
                        res_id = m.group(2)
                if not res_id:
                    res_id = name  # fallback
                # 전문분야는 뒤쪽에 위치 — -2 번째 셀
                specialty = cells[-2].get_text(" ", strip=True) if len(cells) >= 2 else ""
                current = {
                    "external_id": f"NPH-{dept_code}-{res_id}",
                    "name": name,
                    "department": dept_name,
                    "position": "",
                    "specialty": specialty,
                    "schedules": [],
                    "notes": "",
                    "_seen": set(),
                }
                doctors.append(current)
                # 같은 행에 '오전' 레이블 (index=2) + 월~토 (index=3~8)
                slot = "morning"
                if len(cells) >= 9:
                    schedule_cells = cells[3:9]
                else:
                    continue

            # 각 요일 셀에 circle.png 이미지가 있으면 예약 가능 → 스케줄로 등록
            for i, cell in enumerate(schedule_cells):
                if i >= 6:
                    break
                if cell.select_one('img[src*="circle"]'):
                    dow = i
                    key = (dow, slot)
                    if key in current["_seen"]:
                        continue
                    current["_seen"].add(key)
                    start, end = TIME_RANGES[slot]
                    # 토요일 오후는 없음
                    if dow == 5 and slot == "morning":
                        end = "12:30"
                    current["schedules"].append({
                        "day_of_week": dow,
                        "time_slot": slot,
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                    })

        for d in doctors:
            d.pop("_seen", None)
            d["staff_id"] = d["external_id"]
            d["profile_url"] = TREATMENT_URL.format(code=dept_code)
        return doctors

    async def _fetch_dept(self, client: httpx.AsyncClient, dept_code: str, dept_name: str) -> list[dict]:
        try:
            resp = await client.get(TREATMENT_URL.format(code=dept_code))
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[NPH] {dept_name}({dept_code}) 조회 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.select_one("table")
        if not table:
            return []
        return self._parse_treatment_table(table, dept_code, dept_name)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            try:
                dept_codes = await self._fetch_dept_codes(client)
            except Exception as e:
                logger.error(f"[NPH] 진료과 목록 조회 실패: {e}")
                self._cached_data = []
                return []

            tasks = [asyncio.create_task(self._fetch_dept(client, code, name))
                     for code, name in dept_codes]
            all_doctors: list[dict] = []
            seen_ids: set[str] = set()
            for coro in asyncio.as_completed(tasks):
                docs = await coro
                for d in docs:
                    if d["external_id"] in seen_ids:
                        continue
                    seen_ids.add(d["external_id"])
                    all_doctors.append(d)

        logger.info(f"[NPH] 총 {len(all_doctors)}명")
        self._cached_data = all_doctors
        return all_doctors

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        seen = {}
        for d in data:
            dept = d.get("department") or ""
            if dept and dept not in seen:
                seen[dept] = {"code": dept, "name": dept}
        return list(seen.values())

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
        """개별 교수 진료시간표 — staff_id 에서 dcDept 파싱해 해당 진료과만 조회"""
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

        # external_id 포맷: NPH-{dcDept}-{medDr}
        m = re.match(r"^NPH-(\d{5})-", staff_id)
        if not m:
            logger.warning(f"[NPH] staff_id 파싱 실패: {staff_id}")
            return empty
        dept_code = m.group(1)

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            docs = await self._fetch_dept(client, dept_code, "")
            # 진료과명은 의사 목록 자체에서 가져올 수 없으므로 dept_list 에서 추가 조회
            if docs:
                try:
                    dept_codes = await self._fetch_dept_codes(client)
                    name_map = dict(dept_codes)
                    for d in docs:
                        d["department"] = name_map.get(dept_code, "")
                except Exception:
                    pass

        for d in docs:
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
