"""포천우리병원(SWOORI) 크롤러

홈페이지: http://www.swoori.co.kr
구조:
  진료과 목록: 메뉴에 sub3.php(sub=1) ~ sub3_24.php(sub=23) 링크
  각 진료과 페이지: `<h5>{name} <span class="name_tit"> {position} / {dept}</span></h5>
                     <a href="./sub3_{slug}.php?top=3&sub={N}">프로필 상세보기</a>`
  상세 페이지: 전문분야 + 약력. ※ 주간 진료시간표는 이미지로만 제공되어 파싱 불가.
            schedules 는 빈 배열, notes 에 안내 문구.

external_id: SWOORI-{sub_no}-{slug}  (sub_no: 1~23, slug: 파일명에서 sub3_ 제거한 값)
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "http://www.swoori.co.kr"
DEPT_INDEX_URL = f"{BASE_URL}/page/sub3.php"

NOTE_TEXT = (
    "※ 포천우리병원은 홈페이지에 주간 진료시간표를 텍스트가 아닌 이미지로만 제공합니다. "
    "요일별 진료 가능 시간은 대표번호 1800-9356 또는 홈페이지를 통해 확인해 주세요."
)

DOCTOR_RE = re.compile(
    r'<h5>\s*([^<]+?)\s*<span[^>]*class="name_tit"[^>]*>([^<]+)</span>\s*</h5>\s*'
    r'<a href="([^"]+)"',
    re.DOTALL,
)
DEPT_LINK_RE = re.compile(r'href="[^"]*page/(sub3(?:_\d+)?\.php)\?top=3&sub=(\d+)"[^>]*>([^<]+)')


class SwooriCrawler:
    def __init__(self):
        self.hospital_code = "SWOORI"
        self.hospital_name = "포천우리병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: list[dict] | None = None
        self._cached_depts: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        if self._cached_depts is not None:
            return self._cached_depts
        try:
            resp = await client.get(DEPT_INDEX_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[SWOORI] 진료과 목록 실패: {e}")
            return []

        seen: dict[int, dict] = {}
        for m in DEPT_LINK_RE.finditer(resp.text):
            filename, sub_no, name = m.group(1), int(m.group(2)), m.group(3).strip()
            if not name:
                continue
            if sub_no in seen:
                continue
            seen[sub_no] = {"sub_no": sub_no, "filename": filename, "name": name}

        depts = [seen[k] for k in sorted(seen)]
        self._cached_depts = depts
        return depts

    def _parse_doctors(self, html: str, dept: dict) -> list[dict]:
        doctors: list[dict] = []
        seen_slugs: set[str] = set()
        for m in DOCTOR_RE.finditer(html):
            name = re.sub(r"\s+", "", m.group(1)).strip()
            raw_info = re.sub(r"\s+", " ", m.group(2)).strip()
            href = m.group(3).strip()
            if not name:
                continue

            # raw_info 형식: "과장 / 정형외과" 또는 "과장/제2정형외과"
            position = ""
            dept_override = ""
            parts = [p.strip() for p in raw_info.split("/", 1)]
            if len(parts) == 2:
                position, dept_override = parts
            else:
                position = raw_info

            # href 에서 slug 추출: ./sub3_kimsh.php → kimsh
            slug_m = re.search(r"sub3_([a-z0-9_]+)\.php", href)
            if slug_m:
                slug = slug_m.group(1)
            else:
                slug = re.sub(r"[^a-z0-9가-힣]+", "_", name.lower()) or f"{len(doctors)}"
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            profile_url = href
            if profile_url.startswith("./"):
                profile_url = f"{BASE_URL}/page/{profile_url[2:]}"
            elif profile_url.startswith("/"):
                profile_url = f"{BASE_URL}{profile_url}"

            external_id = f"SWOORI-{dept['sub_no']}-{slug}"
            doctors.append({
                "staff_id": external_id,
                "external_id": external_id,
                "name": name,
                "department": dept_override or dept["name"],
                "position": position,
                "specialty": "",
                "profile_url": profile_url,
                "notes": NOTE_TEXT,
                "schedules": [],
                "date_schedules": [],
            })
        return doctors

    async def _fetch_dept_doctors(self, client: httpx.AsyncClient, dept: dict) -> list[dict]:
        url = f"{BASE_URL}/page/{dept['filename']}?top=3&sub={dept['sub_no']}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[SWOORI] {dept['name']} 페이지 실패: {e}")
            return []
        return self._parse_doctors(resp.text, dept)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            if not depts:
                self._cached_data = []
                return []

            sem = asyncio.Semaphore(4)

            async def job(d):
                async with sem:
                    return await self._fetch_dept_doctors(client, d)

            tasks = [asyncio.create_task(job(d)) for d in depts]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        seen: set[str] = set()
        all_docs: list[dict] = []
        for r in results:
            if isinstance(r, Exception):
                continue
            for d in r:
                if d["external_id"] in seen:
                    continue
                seen.add(d["external_id"])
                all_docs.append(d)

        logger.info(f"[SWOORI] 총 {len(all_docs)}명")
        self._cached_data = all_docs
        return all_docs

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
        return [{"code": d["name"], "name": d["name"]} for d in depts]

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
        """개별 조회 — staff_id 에 담긴 sub_no 로 해당 진료과 1페이지만 요청 (skill 규칙 #7)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, [] if k in ("schedules", "date_schedules") else "")
                            for k in ("staff_id","name","department","position",
                                     "specialty","profile_url","notes",
                                     "schedules","date_schedules")}
            return empty

        prefix = "SWOORI-"
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        parts = raw.split("-", 1)
        if len(parts) != 2:
            return empty
        try:
            sub_no = int(parts[0])
        except ValueError:
            return empty

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            dept = next((d for d in depts if d["sub_no"] == sub_no), None)
            if not dept:
                return empty
            doctors = await self._fetch_dept_doctors(client, dept)

        for d in doctors:
            if d["external_id"] == staff_id or d["staff_id"] == staff_id:
                return {k: d.get(k, [] if k in ("schedules", "date_schedules") else "")
                        for k in ("staff_id","name","department","position",
                                 "specialty","profile_url","notes",
                                 "schedules","date_schedules")}
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
