"""원광대학교산본병원(WMCSB) 크롤러

홈페이지: https://www.wmcsb.co.kr
구조:
  진료과 목록: /medicalpart/medicalpart_01.php
    → `<a href="medicalpart_01_02.php?mpart={N}">{과명}</a>` 구조
  진료과별 의료진: /medicalpart/medicalpart_01_02.php?mpart={N}
    → `<ul class="dr_list"><li>` 각 의사 블록:
       - img src="/data/medicaldoctor/{mdoc}.gif"
       - span.name, span.team, p.part
       - table.table1 thead: 월 화 수 목 금 (토 없음)
                   tbody tr[0] 오전, tr[1] 오후
                   <td><span class="iconset sche1">진료</span></td>
                   sche1=외래진료, sche2=인공신장실, sche3=심뇌혈관센터, ...
       - <a href="/medicalpart/medicalpart_07.php?mpart={N}&mdoc={ID}">간편예약</a>

external_id: WMCSB-{mpart}-{mdoc}
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.wmcsb.co.kr"
DEPT_INDEX_URL = f"{BASE_URL}/medicalpart/medicalpart_01.php"
DEPT_DOC_URL_TMPL = f"{BASE_URL}/medicalpart/medicalpart_01_02.php?mpart={{mpart}}"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}
DAYS = ["월", "화", "수", "목", "금", "토"]

SCHE_LOCATION = {
    "sche1": "",
    "sche2": "인공신장실",
    "sche3": "심뇌혈관센터",
    "sche4": "암센터",
    "sche5": "노화방지센터",
    "sche6": "소아심장과",
    "sche7": "정신건강의학과[내과]",
}

MDOC_RE = re.compile(r"mdoc=(\d+)")
IMG_ID_RE = re.compile(r"/data/medicaldoctor/(\d+)\.")


class WmcsbCrawler:
    def __init__(self):
        self.hospital_code = "WMCSB"
        self.hospital_name = "원광대학교산본병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
            logger.error(f"[WMCSB] 진료과 목록 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        seen: dict[int, str] = {}
        for a in soup.select(".medi_box a[href*='medicalpart_01_02.php?mpart=']"):
            m = re.search(r"mpart=(\d+)", a.get("href", ""))
            if not m:
                continue
            mpart = int(m.group(1))
            if mpart in seen:
                continue
            # name 은 형제 <p> 에서 추출
            parent = a.find_parent("div", class_="deptinfo")
            name = ""
            if parent:
                p = parent.find("p")
                if p:
                    name = p.get_text(strip=True)
            if not name:
                name = a.get_text(strip=True)
                if name in ("소개", "의료진"):
                    continue
            seen[mpart] = name

        depts = [{"code": str(k), "name": v, "mpart": k} for k, v in sorted(seen.items())]
        self._cached_depts = depts
        return depts

    def _parse_schedule(self, table, day_header: list[int]) -> list[dict]:
        if table is None:
            return []
        thead = table.find("thead")
        if thead is None:
            return []
        ths = thead.find_all("th")
        day_cols: dict[int, int] = {}
        for ci, th in enumerate(ths):
            t = th.get_text(strip=True)
            if t in DAYS:
                day_cols[ci] = DAYS.index(t)
        if not day_cols:
            return []

        tbody = table.find("tbody")
        if tbody is None:
            return []

        schedules: list[dict] = []
        for tr in tbody.find_all("tr", recursive=False):
            th = tr.find("th")
            if th is None:
                continue
            label = th.get_text(" ", strip=True)
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            else:
                continue
            cells = tr.find_all(["td", "th"], recursive=False)
            for ci, cell in enumerate(cells):
                if ci not in day_cols:
                    continue
                dow = day_cols[ci]
                span = cell.select_one("span.iconset")
                if span is None:
                    continue
                classes = [c for c in (span.get("class") or []) if c.startswith("sche")]
                if not classes:
                    continue
                sche_cls = classes[0]
                location = SCHE_LOCATION.get(sche_cls, "")
                s, e = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": s,
                    "end_time": e,
                    "location": location,
                })
        return schedules

    def _parse_doctors(self, html: str, dept: dict) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        result: list[dict] = []
        seen_mdoc: set[str] = set()

        for li in soup.select("ul.dr_list > li"):
            name_el = li.select_one("span.name")
            if name_el is None:
                continue
            name = name_el.get_text(strip=True)
            if not name:
                continue

            team_el = li.select_one("span.team")
            dept_name = team_el.get_text(strip=True) if team_el else dept["name"]

            part_el = li.select_one("p.part")
            specialty = part_el.get_text(" ", strip=True) if part_el else ""

            # mdoc 추출 — 간편예약 링크 우선, 없으면 img src 에서
            mdoc = ""
            rsv = li.select_one("a.btn_rsv")
            if rsv:
                m = MDOC_RE.search(rsv.get("href", ""))
                if m:
                    mdoc = m.group(1)
            if not mdoc:
                img = li.select_one("img")
                if img and img.get("src"):
                    m = IMG_ID_RE.search(img["src"])
                    if m:
                        mdoc = m.group(1)
            if not mdoc or mdoc in seen_mdoc:
                continue
            seen_mdoc.add(mdoc)

            photo_url = ""
            img = li.select_one(".img_area img")
            if img and img.get("src"):
                src = img["src"].strip()
                photo_url = src if src.startswith("http") else f"{BASE_URL}{src}"

            # 경력 (details > .cont)
            career_lines: list[str] = []
            for details in li.select("details"):
                for item in details.select("ul.list li"):
                    t = item.get_text(" ", strip=True)
                    if t:
                        career_lines.append(t)
            career_text = "\n".join(career_lines)

            # position 은 경력에서 "부장/과장/교수" 등의 첫 타이틀 추출 시도
            position = ""
            for line in career_lines:
                if re.search(r"(진료부장|과장|센터장|교수|원장|부원장|의무원장)", line):
                    mpos = re.search(r"(진료부장|과장|센터장|교수|원장|부원장|의무원장)", line)
                    position = mpos.group(1) if mpos else ""
                    break

            tbl = li.select_one("table.table1")
            schedules = self._parse_schedule(tbl, [])

            profile_url = f"{BASE_URL}/medicalpart/medicalpart_01_02.php?mpart={dept['mpart']}#mdoc{mdoc}"
            external_id = f"WMCSB-{dept['mpart']}-{mdoc}"
            result.append({
                "staff_id": external_id,
                "external_id": external_id,
                "mpart": dept["mpart"],
                "mdoc": mdoc,
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": specialty,
                "profile_url": profile_url,
                "photo_url": photo_url,
                "notes": "",
                "schedules": schedules,
                "date_schedules": [],
                "_career": career_text,
            })
        return result

    async def _fetch_dept_doctors(self, client: httpx.AsyncClient, dept: dict) -> list[dict]:
        url = DEPT_DOC_URL_TMPL.format(mpart=dept["mpart"])
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[WMCSB] {dept['name']} 실패: {e}")
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

        logger.info(f"[WMCSB] 총 {len(all_docs)}명")
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
        """개별 조회 — 해당 진료과(mpart) 1페이지만 요청 (skill 규칙 #7)"""
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

        prefix = "WMCSB-"
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        parts = raw.split("-", 1)
        if len(parts) != 2:
            return empty
        try:
            mpart = int(parts[0])
        except ValueError:
            return empty

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            dept = next((d for d in depts if d["mpart"] == mpart), None)
            if not dept:
                dept = {"code": str(mpart), "name": "", "mpart": mpart}
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
