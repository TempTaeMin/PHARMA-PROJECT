"""베스티안서울병원(Bestian Seoul Hospital) 크롤러

병원 공식명: 베스티안서울병원 (화상 전문병원)
홈페이지: www.bestianseoul.com (WordPress, SSL self-signed → verify=False)
기술: 정적 HTML (httpx + BeautifulSoup)

구조:
  4개 카테고리 URL 에 의료진이 분산 배치:
    - 성인화상_의료진
    - 전문센터/소아화상센터/소아화상_의료진
    - 전문센터/화상재건센터/화상재건_의료진
    - 진료과-클리닉/내과

각 페이지 내 의료진은 반복되는 블록:
  <h4>{이름} {직책}</h4> (또는 caption 안)
  <table class="... acdemic-table ...">
    <caption class="blind">{이름} {직책} 스케쥴</caption>
    <thead>[진료과목, 월, 화, 수, 목, 금, 토]</thead>
    <tbody>
      <tr>[진료과목, 오전 6칸 (dot_dr_on.png / dot_dr_off.png)]
      <tr>[진료과목, 오후 6칸]
    </tbody>
  </table>

external_id: BESEOUL-{category}-{name_slug}
"""
import re
import asyncio
import logging
import httpx
import hashlib
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "http://www.bestianseoul.com"

# (카테고리 코드, 한글 진료과명, URL 경로)
CATEGORIES = [
    ("adult", "화상외과", "/성인화상_의료진/"),
    ("child", "소아화상", "/전문센터/소아화상센터/소아화상_의료진/"),
    ("recon", "화상재건", "/전문센터/화상재건센터/화상재건_의료진/"),
    ("internal", "내과", "/진료과-클리닉/내과/"),
]

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
DAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}


class BeseoulCrawler:
    """베스티안서울병원 크롤러 — 4개 카테고리 페이지 정적 HTML 파싱"""

    def __init__(self):
        self.hospital_code = "BESEOUL"
        self.hospital_name = "베스티안서울병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        self._cached_data: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    @staticmethod
    def _slugify(name: str) -> str:
        h = hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
        return h

    @staticmethod
    def _split_name_position(text: str) -> tuple[str, str]:
        """'윤천재 의료원장' → ('윤천재', '의료원장')"""
        text = text.strip()
        if not text:
            return "", ""
        parts = text.split()
        if len(parts) == 1:
            return parts[0], ""
        # 이름은 보통 2~4자 한글, 직책이 뒤
        # 이름 후보를 가장 앞 토큰으로 가정하고, 그 외 뒷부분을 직책
        return parts[0], " ".join(parts[1:])

    def _parse_schedule_table(self, table) -> list[dict]:
        if table is None:
            return []

        # 헤더 추출: thead > th 텍스트
        thead = table.find("thead")
        if thead is None:
            return []
        header_cells = thead.find_all(["th", "td"])
        col_to_dow: dict[int, int] = {}
        for ci, cell in enumerate(header_cells):
            t = cell.get_text(strip=True)
            if t in DAY_INDEX:
                col_to_dow[ci] = DAY_INDEX[t]
        if not col_to_dow:
            return []

        tbody = table.find("tbody") or table
        schedules: list[dict] = []
        for row in tbody.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if not cells:
                continue
            # 첫 셀의 "오전"/"오후" 텍스트로 slot 결정
            label = cells[0].get_text(strip=True)
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            else:
                # 진료과목이 첫 셀, 그 다음이 오전/오후 라벨일 수도 있음
                if len(cells) >= 2:
                    label2 = cells[1].get_text(strip=True)
                    if "오전" in label2:
                        slot = "morning"
                    elif "오후" in label2:
                        slot = "afternoon"
                    else:
                        continue
                else:
                    continue
            start, end = TIME_RANGES[slot]
            for ci, cell in enumerate(cells):
                if ci not in col_to_dow:
                    continue
                # dot_dr_on 이면 진료
                img = cell.find("img")
                is_on = False
                if img and img.get("src"):
                    src = img["src"].lower()
                    if "dot_dr_on" in src or "_on." in src or "dot_on" in src:
                        is_on = True
                else:
                    # 텍스트로 ● 있으면 진료
                    t = cell.get_text(strip=True)
                    if t == "●":
                        is_on = True
                if not is_on:
                    continue
                schedules.append({
                    "day_of_week": col_to_dow[ci],
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return schedules

    def _find_name_for_table(self, table) -> str:
        """table 근처에서 의사 이름 추출. 1) caption, 2) 이전 형제 h3/h4"""
        caption = table.find("caption")
        if caption:
            text = caption.get_text(" ", strip=True)
            # "{이름} {직책} 스케쥴" 패턴
            m = re.match(r"^(.+?)\s*스케[쥬줄]", text)
            if m:
                return m.group(1).strip()
            return text

        # caption 없으면 이전 형제들에서 h4/h3 탐색
        prev = table.find_previous(["h4", "h3"])
        if prev:
            return prev.get_text(" ", strip=True)
        return ""

    def _parse_category_page(self, soup: BeautifulSoup, category_code: str, dept_name: str, page_url: str) -> list[dict]:
        result: list[dict] = []
        seen: set[str] = set()

        tables = soup.find_all("table", class_=re.compile(r"acdemic|doc_time"))
        if not tables:
            # class 패턴 불일치 시 caption 에 "스케" 포함된 테이블만
            tables = [t for t in soup.find_all("table") if t.find("caption") and "스케" in t.find("caption").get_text()]

        for table in tables:
            full_text = self._find_name_for_table(table)
            name, position = self._split_name_position(full_text)
            if not name:
                continue

            schedules = self._parse_schedule_table(table)
            name_slug = self._slugify(f"{category_code}-{name}-{position}")
            ext_id = f"BESEOUL-{category_code}-{name_slug}"
            if ext_id in seen:
                continue
            seen.add(ext_id)

            result.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": "",
                "profile_url": page_url,
                "notes": "",
                "schedules": schedules,
                "date_schedules": [],
            })

        return result

    async def _fetch_category(
        self, client: httpx.AsyncClient, category_code: str, dept_name: str, path: str
    ) -> list[dict]:
        url = f"{BASE_URL}{path}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[BESEOUL] {dept_name} 페이지 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        docs = self._parse_category_page(soup, category_code, dept_name, url)
        logger.info(f"[BESEOUL] {dept_name}: {len(docs)}명")
        return docs

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            tasks = [
                asyncio.create_task(self._fetch_category(client, code, name, path))
                for code, name, path in CATEGORIES
            ]
            all_doctors: list[dict] = []
            seen: set[str] = set()
            for coro in asyncio.as_completed(tasks):
                docs = await coro
                for d in docs:
                    if d["external_id"] in seen:
                        continue
                    seen.add(d["external_id"])
                    all_doctors.append(d)

        logger.info(f"[BESEOUL] 총 {len(all_doctors)}명")
        self._cached_data = all_doctors
        return all_doctors

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        return [{"code": code, "name": name} for code, name, _ in CATEGORIES]

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
        """개별 교수 조회 — staff_id 에서 카테고리 추출해 해당 페이지만 조회"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, []) if k in ("schedules", "date_schedules") else d.get(k, "")
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}
            return empty

        # external_id 포맷: BESEOUL-{category}-{hash}
        m = re.match(r"^BESEOUL-([a-z]+)-", staff_id)
        if not m:
            return empty
        cat_code = m.group(1)
        target = next(((c, n, p) for c, n, p in CATEGORIES if c == cat_code), None)
        if target is None:
            return empty

        async with self._make_client() as client:
            docs = await self._fetch_category(client, target[0], target[1], target[2])

        for d in docs:
            if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                return {k: d.get(k, []) if k in ("schedules", "date_schedules") else d.get(k, "")
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
