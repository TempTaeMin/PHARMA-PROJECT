"""청담 우리들병원(WOORIDUL) 크롤러

병원 공식명: 청담 우리들병원 (서울 강남구 청담동, 척추 전문)
홈페이지: cheongdam.wooridul.co.kr (정적 HTML, UTF-8)

구조:
- 의료진 전체: GET `/about/doctors`   (sca 필터 없으면 29명 전부 한 페이지)
  ul.team > li 안에:
    div.img > img alt="{이름}"
    div.cont > p > span > strong "{이름} {직책}"
           > p > span 텍스트 "{전문의 과목}"
           > p 자식 텍스트 "{진료과(복수는 ' / ' 구분)}"
    a[href*="doctors?id="] → id 추출
- 상세/스케줄: GET `/about/doctors?id={id}&sca=1`
  table.schedule > tbody > tr (오전/오후, 월~토 7셀)
    셀 텍스트에 `●` 있으면 진료, 없으면 휴진
  일부 의사 (예: 이상호 박사 id=1) 는 스케줄 테이블이 비어있음 → schedules=[]

external_id: WOORIDUL-{id}
"""
from __future__ import annotations

import re
import asyncio
import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "http://cheongdam.wooridul.co.kr"
LIST_URL = f"{BASE_URL}/about/doctors"

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("14:00", "17:30")}
_ID_PAT = re.compile(r"doctors\?id=(\d+)")


class WooridulCrawler:
    def __init__(self):
        self.hospital_code = "WOORIDUL"
        self.hospital_name = "청담 우리들병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: list[dict] | None = None

    @staticmethod
    def _parse_schedule_table(tbl) -> list[dict]:
        if tbl is None:
            return []
        out: list[dict] = []
        tbody = tbl.find("tbody") or tbl
        for tr in tbody.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 7:
                continue
            label = tds[0].get_text(" ", strip=True).replace("\u00a0", "").replace(" ", "")
            if "오전" in label:
                slot = "morning"
            elif "오후" in label:
                slot = "afternoon"
            else:
                continue
            for dow, td in enumerate(tds[1:7]):
                text = td.get_text(" ", strip=True)
                if "●" not in text and "○" not in text and "진료" not in text:
                    continue
                if "휴" in text:
                    continue
                s, e = TIME_RANGES[slot]
                out.append({
                    "day_of_week": dow, "time_slot": slot,
                    "start_time": s, "end_time": e, "location": "",
                })
        return out

    def _parse_list_page(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []
        for ul in soup.select("ul.team"):
            for li in ul.find_all("li", recursive=False):
                detail_a = li.find("a", href=_ID_PAT)
                if not detail_a:
                    continue
                m = _ID_PAT.search(detail_a["href"])
                if not m:
                    continue
                doctor_id = m.group(1)

                cont = li.find("div", class_="cont")
                if not cont:
                    continue
                strong = cont.find("strong")
                name = ""
                position = ""
                if strong:
                    name_pos = strong.get_text(" ", strip=True)
                    parts = name_pos.split(maxsplit=1)
                    if parts:
                        name = parts[0]
                    if len(parts) > 1:
                        position = parts[1]

                # specialty: strong 다음 span 의 텍스트 ("신경외과 전문의")
                specialty = ""
                p_span = strong.find_parent("span") if strong else None
                if p_span:
                    # strong 다음의 tail text
                    after = strong.next_sibling
                    while after:
                        if isinstance(after, str):
                            t = after.strip()
                            if t:
                                specialty = t
                                break
                        after = after.next_sibling

                # department: span 바깥의 p 직속 텍스트 ("척추진료부 / 흉추진료부")
                dept = ""
                p_el = None
                if strong:
                    p_el = strong.find_parent("p")
                if p_el:
                    # p 의 텍스트 - span 내부 텍스트 제거
                    p_all = p_el.get_text(" ", strip=True)
                    span = p_el.find("span")
                    if span:
                        span_text = span.get_text(" ", strip=True)
                        dept = p_all.replace(span_text, "", 1).strip()
                    else:
                        dept = p_all.replace(name, "", 1).replace(position, "", 1).strip()

                external_id = f"{self.hospital_code}-{doctor_id}"
                out.append({
                    "staff_id": external_id,
                    "external_id": external_id,
                    "_doctor_id": doctor_id,
                    "name": name,
                    "department": dept,
                    "position": position,
                    "specialty": specialty,
                    "profile_url": f"{BASE_URL}/about/doctors?id={doctor_id}&sca=1",
                    "notes": "",
                    "schedules": [],
                    "date_schedules": [],
                })
        return out

    async def _fetch_list(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await client.get(LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[WOORIDUL] list 실패: {e}")
            return []
        html = resp.content.decode("utf-8", errors="replace")
        return self._parse_list_page(html)

    async def _fetch_schedule(self, client: httpx.AsyncClient, doctor_id: str) -> list[dict]:
        url = f"{BASE_URL}/about/doctors?id={doctor_id}&sca=1"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[WOORIDUL] schedule {doctor_id} 실패: {e}")
            return []
        html = resp.content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        tbl = soup.select_one("table.schedule")
        return self._parse_schedule_table(tbl)

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            doctors = await self._fetch_list(client)
            logger.info(f"[WOORIDUL] 목록: {len(doctors)}명")
            for d in doctors:
                d["schedules"] = await self._fetch_schedule(client, d["_doctor_id"])
                # 서버 WAF 레이트 리밋 회피: 요청 간 소량의 지연
                await asyncio.sleep(0.5)
        for d in doctors:
            d.pop("_doctor_id", None)
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
        """개별 조회 — 의사 상세 페이지 1회 GET (rule #7 준수)"""
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
        doctor_id = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id
        if not doctor_id.isdigit():
            return empty

        # 상세 페이지에서 이름/진료과 + 스케줄 함께 파싱
        url = f"{BASE_URL}/about/doctors?id={doctor_id}&sca=1"
        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.warning(f"[WOORIDUL] 개별 {staff_id} 실패: {e}")
                return empty
        html = resp.content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")

        # 상세 페이지에도 ul.team 이 들어있음 (상단 목록 축약버전). 해당 의사를 골라서 메타 추출.
        name, dept, position, specialty = "", "", "", ""
        for ul in soup.select("ul.team"):
            for li in ul.find_all("li", recursive=False):
                a = li.find("a", href=lambda h: h and f"id={doctor_id}" in h)
                if not a:
                    continue
                strong = li.find("strong")
                if strong:
                    parts = strong.get_text(" ", strip=True).split(maxsplit=1)
                    if parts:
                        name = parts[0]
                    if len(parts) > 1:
                        position = parts[1]
                    after = strong.next_sibling
                    while after and not specialty:
                        if isinstance(after, str) and after.strip():
                            specialty = after.strip()
                            break
                        after = after.next_sibling
                    p_el = strong.find_parent("p")
                    if p_el:
                        p_all = p_el.get_text(" ", strip=True)
                        span = p_el.find("span")
                        if span:
                            dept = p_all.replace(span.get_text(" ", strip=True), "", 1).strip()
                break
            if name:
                break

        tbl = soup.select_one("table.schedule")
        schedules = self._parse_schedule_table(tbl)

        return {
            "staff_id": staff_id,
            "name": name, "department": dept, "position": position,
            "specialty": specialty,
            "profile_url": url, "notes": "",
            "schedules": schedules, "date_schedules": [],
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
