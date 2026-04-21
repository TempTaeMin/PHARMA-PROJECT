"""의정부백병원(UPAIK) 크롤러

홈페이지: http://upaik.co.kr
데이터 구조:
  진료과별 페이지 /Content/Content.asp?FolderName=sub02&FileName=sub02_{NN}
    → var txtIdx = "{dept_idx}"
  의료진 정보 AJAX:
    POST /Module/DoctorInfo/Front/Ajax_DoctorInfo.asp
    data: Idx={dept_idx}&doctorid=
    → 해당 진료과의 의료진 블록들(HTML 조각) 반환

  각 의사 블록: <div class="doctor-container-area">
    <img src="..." alt=""> : 프로필 사진
    <span class="doc-tit-cate">{진료과명}</span>{이름} <span>{직책}</span>
    <table> thead tr: 월 화 수 목 금 토
            tbody tr[0] 오전(08:30~12:30) - td.txt01/txt02(진료) 또는 빈칸
            tbody tr[1] 오후(13:30~17:30)

※ 홈페이지에서 의사 고유 ID를 노출하지 않으므로 index 기반 ID 사용.
   external_id 포맷: UPAIK-{dept_idx}-{order}
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "http://upaik.co.kr"
AJAX_URL = f"{BASE_URL}/Module/DoctorInfo/Front/Ajax_DoctorInfo.asp"

TIME_RANGES = {"morning": ("08:30", "12:30"), "afternoon": ("13:30", "17:30")}
DAYS = ["월", "화", "수", "목", "금", "토"]

# dept_idx → (FileName 번호, 기본 진료과명)
DEPARTMENTS: list[tuple[int, str, str]] = [
    (1, "sub02_01", "내과"),
    (2, "sub02_02", "외과"),
    (3, "sub02_03", "정형외과"),
    (4, "sub02_04", "신경외과"),
    (5, "sub02_05", "신경과"),
    (6, "sub02_06", "피부비뇨기과"),
    (7, "sub02_07", "통증의학과"),
    (8, "sub02_08", "이비인후과"),
    (9, "sub02_09", "치과"),
    (10, "sub02_10", "산부인과"),
    (11, "sub02_11", "가정의학과"),
    (12, "sub02_12", "응급의학과"),
    (13, "sub02_13", "마취과"),
    (14, "sub02_14", "영상의학과"),
    (15, "sub02_15", "진단검사의학과"),
]


class UpaikCrawler:
    def __init__(self):
        self.hospital_code = "UPAIK"
        self.hospital_name = "의정부백병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/",
            "X-Requested-With": "XMLHttpRequest",
        }
        self._cached_data: list[dict] | None = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    def _parse_schedule_table(self, table) -> list[dict]:
        if table is None:
            return []
        thead = table.find("thead")
        if thead is None:
            return []
        header_ths = thead.find_all("th")
        day_cols: dict[int, int] = {}
        for ci, th in enumerate(header_ths):
            t = th.get_text(strip=True)
            if t in DAYS:
                day_cols[ci] = DAYS.index(t)
        if not day_cols:
            return []

        tbody = table.find("tbody")
        if tbody is None:
            return []
        rows = tbody.find_all("tr", recursive=False)
        schedules: list[dict] = []
        for tr in rows:
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
                classes = cell.get("class") or []
                txt = cell.get_text(" ", strip=True)
                if "txt00" in classes:
                    continue
                if not txt or txt in ("-", "\xa0"):
                    continue
                # 진료/수술 등이 있으면 진료 시간대로 간주. "휴진"/"휴무"면 제외
                if any(k in txt for k in ("휴진", "휴무", "휴")):
                    continue
                is_active = ("txt01" in classes or "txt02" in classes or
                             any(k in txt for k in ("진료", "수술", "검진")))
                if not is_active:
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

    def _parse_doctor_blocks(self, html: str, dept_idx: int, dept_name: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        blocks = soup.select("div.doctor-container-area")
        result: list[dict] = []
        for order, block in enumerate(blocks, start=1):
            h3 = block.select_one("h3.doc-tit-text.d-none.d-lg-block") or block.select_one("h3.doc-tit-text")
            if h3 is None:
                continue
            cate_el = h3.select_one("span.doc-tit-cate")
            cate = cate_el.get_text(" ", strip=True) if cate_el else ""
            # h3 의 cate 뒤 텍스트가 이름 + (span)직책
            # h3 에서 cate span 제거 후 나머지 분석
            if cate_el:
                cate_el.extract()
            # 남은 자식: 이름 텍스트 + <span>직책</span>
            name = ""
            position = ""
            for child in h3.children:
                if getattr(child, "name", None) == "span":
                    t = child.get_text(" ", strip=True)
                    if t:
                        position = t
                else:
                    t = (child if isinstance(child, str) else child.get_text(" ", strip=True)).strip()
                    t = re.sub(r"\s+", "", t)
                    if t:
                        name += t
            name = name.strip()
            if not name:
                continue

            img_el = block.select_one(".img-area img")
            photo_url = ""
            if img_el and img_el.get("src"):
                src = img_el["src"].strip()
                photo_url = src if src.startswith("http") else f"{BASE_URL}{src}"

            # 경력
            career_text = ""
            memo = block.select_one(".ProfileMemo")
            if memo:
                items = [li.get_text(" ", strip=True) for li in memo.select("ul li")]
                career_text = "\n".join(it for it in items if it)

            # 진료표: .doc-cont-table table 우선, 없으면 .ProfileTimeTable table
            tbl = block.select_one(".doc-cont-table table")
            if tbl is None:
                tbl = block.select_one(".ProfileTimeTable table")
            schedules = self._parse_schedule_table(tbl)

            # 비고(remarks)는 notes 로 보조 표시
            notes_parts = []
            if cate and cate != dept_name:
                notes_parts.append(f"소속: {cate}")
            notes = "\n".join(notes_parts)

            external_id = f"UPAIK-{dept_idx}-{order}"
            result.append({
                "staff_id": external_id,
                "external_id": external_id,
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": "",
                "profile_url": f"{BASE_URL}/Content/Content.asp?FolderName=sub02&FileName=sub02_{dept_idx:02d}",
                "photo_url": photo_url,
                "notes": notes,
                "schedules": schedules,
                "date_schedules": [],
                "_career": career_text,
            })
        return result

    async def _fetch_dept(self, client: httpx.AsyncClient, dept_idx: int, dept_name: str) -> list[dict]:
        try:
            resp = await client.post(AJAX_URL, data={"Idx": str(dept_idx), "doctorid": ""})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[UPAIK] dept {dept_idx} ({dept_name}) 실패: {e}")
            return []
        return self._parse_doctor_blocks(resp.text, dept_idx, dept_name)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            sem = asyncio.Semaphore(4)

            async def job(idx, name):
                async with sem:
                    return await self._fetch_dept(client, idx, name)

            tasks = [asyncio.create_task(job(idx, name)) for idx, _, name in DEPARTMENTS]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        all_docs: list[dict] = []
        seen: set[str] = set()
        for r in results:
            if isinstance(r, Exception):
                continue
            for d in r:
                if d["external_id"] in seen:
                    continue
                seen.add(d["external_id"])
                all_docs.append(d)

        logger.info(f"[UPAIK] 총 {len(all_docs)}명")
        self._cached_data = all_docs
        return all_docs

    async def get_departments(self) -> list[dict]:
        return [{"code": name, "name": name} for _, _, name in DEPARTMENTS]

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
        """개별 조회 — dept_idx 1개만 AJAX 호출 (skill 규칙 #7)"""
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

        prefix = "UPAIK-"
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        parts = raw.split("-")
        if len(parts) != 2:
            return empty
        try:
            dept_idx = int(parts[0])
            order = int(parts[1])
        except ValueError:
            return empty
        dept_name = next((n for i, _, n in DEPARTMENTS if i == dept_idx), "")
        if not dept_name:
            return empty

        async with self._make_client() as client:
            doctors = await self._fetch_dept(client, dept_idx, dept_name)
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
