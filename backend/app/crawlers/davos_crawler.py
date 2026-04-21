"""다보스병원(DAVOS) 크롤러

병원 공식명: 의료법인 영문의료재단 다보스병원 (경기 용인시 처인구 김량장동)
홈페이지: davoshospital.co.kr (정적 HTML, UTF-8)

구조:
- 의료진 목록: GET `/depart/page02.html?page={1..N}` — 페이지당 약 10명, 현재 총 38명
  a.item 안에:
    div.img > img src (프로필 사진 URL)
    div.info > div.top > span.name "{이름} <small>{직책}</small>"
                         span.department "{진료과}"
           > div.category > span "{전문분야(/로 구분)}"
    button onclick="location.href='/depart/page02-detail.html?dr_idx={N}'"
- 개인 상세/스케줄: GET `/depart/page02-detail.html?dr_idx={N}`
  div.section-doctor > div._top > div.doc-info-txt:
    div.top > h1 "{진료과}"
             > p "{이름} <b>{직책}</b>"
    div.field > span "{전문분야}"
    div.time > table:
      thead: 시간/월/화/수/목/금/토
      tbody 2행 (오전/오후) 각 6셀(월~토)
        td.on > span.diag "진료"  → 진료 → schedule
        td     > span.oper "수술"  → 수술 (not 진료, 건너뜀)
        td     > span.oper "문의"  → 문의 (unknown)
        td     (빈)                → 휴진
  div.career (학력/경력)

진료/수술 중 "진료" 만 스케줄로 반영한다 (MR 방문 가능 시간 기준).
external_id: DAVOS-{dr_idx}
"""
from __future__ import annotations

import re
import asyncio
import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://davoshospital.co.kr"
LIST_URL = f"{BASE_URL}/depart/page02.html"
DETAIL_URL = f"{BASE_URL}/depart/page02-detail.html"

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:30")}
_DR_IDX_PAT = re.compile(r"dr_idx=(\d+)")


class DavosCrawler:
    def __init__(self):
        self.hospital_code = "DAVOS"
        self.hospital_name = "다보스병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: list[dict] | None = None

    # ─── 리스트 페이지 파싱 ───

    def _parse_list_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []
        for item in soup.select("a.item"):
            btn = item.find("button", onclick=_DR_IDX_PAT)
            m = _DR_IDX_PAT.search(btn.get("onclick", "")) if btn else None
            if not m:
                continue
            dr_idx = m.group(1)

            name = ""
            position = ""
            name_span = item.select_one(".name")
            if name_span:
                small = name_span.find("small")
                if small:
                    position = small.get_text(" ", strip=True)
                    small.extract()
                name = name_span.get_text(" ", strip=True)

            dept_span = item.select_one(".department")
            department = dept_span.get_text(" ", strip=True) if dept_span else ""

            specialty = ""
            cat = item.select_one(".category span")
            if cat:
                specialty = cat.get_text(" ", strip=True)

            photo_url = ""
            img = item.select_one("div.img img")
            if img and img.get("src"):
                photo_url = img["src"]

            out.append({
                "dr_idx": dr_idx,
                "name": name,
                "position": position,
                "department": department,
                "specialty": specialty,
                "photo_url": photo_url,
            })
        return out

    # ─── 상세 페이지 파싱 ───

    @staticmethod
    def _parse_schedule(detail_soup: BeautifulSoup) -> list[dict]:
        tbl = detail_soup.select_one(".section-doctor table")
        if not tbl:
            return []
        rows = tbl.find("tbody").find_all("tr") if tbl.find("tbody") else []
        out: list[dict] = []
        for tr in rows:
            th = tr.find("th")
            if not th:
                continue
            label = th.get_text(" ", strip=True)
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            else:
                continue
            tds = tr.find_all("td")
            for dow, td in enumerate(tds[:6]):
                diag = td.find("span", class_="diag")
                if not diag:
                    continue
                text = diag.get_text(strip=True)
                if "진료" not in text:
                    continue
                s, e = TIME_RANGES[slot]
                out.append({
                    "day_of_week": dow, "time_slot": slot,
                    "start_time": s, "end_time": e, "location": "",
                })
        return out

    def _parse_detail(self, html: str, dr_idx: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        info = soup.select_one(".section-doctor .doc-info-txt")
        name, position, department, specialty = "", "", "", ""
        if info:
            h1 = info.select_one(".top h1")
            if h1:
                department = h1.get_text(" ", strip=True)
            p = info.select_one(".top p")
            if p:
                b = p.find("b")
                if b:
                    position = b.get_text(" ", strip=True)
                    b.extract()
                name = p.get_text(" ", strip=True)
            sp = info.select_one(".field span")
            if sp:
                specialty = sp.get_text(" ", strip=True)

        schedules = self._parse_schedule(soup)
        return {
            "name": name,
            "position": position,
            "department": department,
            "specialty": specialty,
            "schedules": schedules,
            "profile_url": f"{DETAIL_URL}?dr_idx={dr_idx}",
        }

    # ─── 네트워크 ───

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            items: list[dict] = []
            seen: set[str] = set()
            for page in range(1, 8):  # 안전 상한
                try:
                    resp = await client.get(LIST_URL, params={"page": page})
                    resp.raise_for_status()
                except Exception as e:
                    logger.warning(f"[DAVOS] list page {page} 실패: {e}")
                    break
                html = resp.content.decode("utf-8", errors="replace")
                page_items = self._parse_list_page(html)
                new = [it for it in page_items if it["dr_idx"] not in seen]
                if not new:
                    break
                for it in new:
                    seen.add(it["dr_idx"])
                items.extend(new)
                if len(page_items) < 10:  # 마지막 페이지
                    break

            logger.info(f"[DAVOS] 목록: {len(items)}명")

            # 각 의사의 상세(스케줄) 병렬 fetch
            async def fetch_detail(it):
                try:
                    r = await client.get(DETAIL_URL, params={"dr_idx": it["dr_idx"]})
                    r.raise_for_status()
                except Exception as e:
                    logger.warning(f"[DAVOS] detail {it['dr_idx']} 실패: {e}")
                    return {"schedules": []}
                return self._parse_detail(r.content.decode("utf-8", errors="replace"), it["dr_idx"])

            sem = asyncio.Semaphore(5)

            async def bounded(it):
                async with sem:
                    return it, await fetch_detail(it)

            results = await asyncio.gather(*[bounded(it) for it in items])

        doctors: list[dict] = []
        for it, detail in results:
            external_id = f"{self.hospital_code}-{it['dr_idx']}"
            schedules = detail.get("schedules", [])
            notes = "" if schedules else "※ 홈페이지에 진료시간이 '진료' 로 명시되어 있지 않거나 '문의/수술' 로 표기되어 있습니다. 정확한 외래 시간은 병원에 문의해 주세요."
            doctors.append({
                "staff_id": external_id,
                "external_id": external_id,
                "name": detail.get("name") or it["name"],
                "department": detail.get("department") or it["department"],
                "position": detail.get("position") or it["position"],
                "specialty": detail.get("specialty") or it["specialty"],
                "profile_url": f"{DETAIL_URL}?dr_idx={it['dr_idx']}",
                "notes": notes,
                "schedules": schedules,
                "date_schedules": [],
            })

        self._cached_data = doctors
        return doctors

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        data = await self._fetch_all()
        depts = sorted({d["department"] for d in data if d["department"]})
        return [{"code": dn, "name": dn} for dn in depts]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if department in d["department"]]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department",
                                "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 조회 — 상세 페이지 1회 GET (rule #7 준수)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") if k not in ("schedules", "date_schedules")
                            else d.get(k, [])
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}

        prefix = f"{self.hospital_code}-"
        dr_idx = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id
        if not dr_idx.isdigit():
            return empty

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        ) as client:
            try:
                r = await client.get(DETAIL_URL, params={"dr_idx": dr_idx})
                r.raise_for_status()
            except Exception as e:
                logger.warning(f"[DAVOS] 개별 {staff_id} 실패: {e}")
                return empty
            detail = self._parse_detail(r.content.decode("utf-8", errors="replace"), dr_idx)

        schedules = detail.get("schedules", [])
        notes = "" if schedules else "※ 홈페이지에 진료시간이 '진료' 로 명시되어 있지 않거나 '문의/수술' 로 표기되어 있습니다. 정확한 외래 시간은 병원에 문의해 주세요."
        return {
            "staff_id": staff_id,
            "name": detail.get("name", ""),
            "department": detail.get("department", ""),
            "position": detail.get("position", ""),
            "specialty": detail.get("specialty", ""),
            "profile_url": detail.get("profile_url", f"{DETAIL_URL}?dr_idx={dr_idx}"),
            "notes": notes,
            "schedules": schedules,
            "date_schedules": [],
        }

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if department in d["department"]]

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
