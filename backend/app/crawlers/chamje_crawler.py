"""참조은병원(CHAMJE) 크롤러

병원 공식명: 참조은병원 (경기 광주)
홈페이지: chamhosp.co.kr (워드프레스 스타일 /?p=N)

구조:
- 목록: POST `/_Prog/cje/medical/teamListHtml.php`
    data: page={1..}, p=10, pageNm=, gubun=department, searchTxt=
    응답: div.medi_staff > ul > li HTML 조각 (10명/페이지, 8페이지 내외)
    항목:
      div.cate_wrap > span        → 진료과
      strong                       → 이름
      "이름" 다음 텍스트            → 직책/소속 ("교수", "교수/중환자실장")
      span                          → 전문분야(쉼표 구분)
      a[href*="doctorId="]          → 상세 ID 추출
- 상세: GET `/?p=10_view&doctorId={N}&dType=department`
    - div.intro > em = 진료과, strong = 이름, 옆 텍스트 = 직책
    - div.schedule > table.cont_tbl: 오전/오후 × 월~토, 셀 텍스트: "진료"/"-"/"격주진료"/"전화문의"

external_id: CHAMJE-{doctorId}
"""
from __future__ import annotations

import re
import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.crawlers._schedule_rules import find_exclude_keyword, has_biweekly_mark

logger = logging.getLogger(__name__)

BASE_URL = "https://chamhosp.co.kr"
LIST_AJAX = f"{BASE_URL}/_Prog/cje/medical/teamListHtml.php"

TIME_RANGES = {"morning": ("09:00", "12:30"), "afternoon": ("13:30", "17:30")}
_ID_PAT = re.compile(r"doctorId=(\d+)")


class ChamjeCrawler:
    def __init__(self):
        self.hospital_code = "CHAMJE"
        self.hospital_name = "참조은병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/?p=10",
            "X-Requested-With": "XMLHttpRequest",
        }
        self._cached_data: list[dict] | None = None

    @staticmethod
    def _parse_schedule_table(tbl) -> list[dict]:
        if tbl is None:
            return []
        out: list[dict] = []
        tbody = tbl.find("tbody") or tbl
        for tr in tbody.find_all("tr"):
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
            if len(tds) < 6:
                continue
            for dow, td in enumerate(tds[:6]):
                text = td.get_text(" ", strip=True)
                if not text or text in ("-", "—", "–") or "휴진" in text or "휴무" in text:
                    continue
                # 수술/시술/검사 등은 외래 아님 — 제외
                if find_exclude_keyword(text):
                    continue
                if not any(k in text for k in ("진료", "외래", "격주", "클리닉")):
                    # 진료 키워드 없으면 스킵 (예: 전화문의만 있는 경우)
                    continue
                s, e = TIME_RANGES[slot]
                out.append({
                    "day_of_week": dow, "time_slot": slot,
                    "start_time": s, "end_time": e,
                    "location": "격주진료" if "격주" in text else "",
                })
        return out

    def _parse_list_item(self, li) -> dict | None:
        cate = li.select_one("div.cate_wrap span")
        dept = cate.get_text(" ", strip=True) if cate else ""
        strong = li.find("strong")
        if not strong:
            return None
        name = strong.get_text(" ", strip=True)
        if not name:
            return None
        # 직책: "이름" 다음 텍스트
        position = ""
        p_el = strong.parent
        if p_el and p_el.name == "p":
            p_text = p_el.get_text(" ", strip=True)
            position = p_text.replace(name, "", 1).strip()

        # 전문분야: 마지막 p 또는 span(class 없음)
        spec_el = None
        for sp in li.find_all("span"):
            if not sp.get("class") and sp.get_text(strip=True):
                spec_el = sp
        specialty = spec_el.get_text(" ", strip=True) if spec_el else ""

        detail_a = li.find("a", href=lambda h: h and "doctorId=" in h)
        doctor_id = ""
        if detail_a:
            m = _ID_PAT.search(detail_a["href"])
            if m:
                doctor_id = m.group(1)
        if not doctor_id:
            return None

        external_id = f"{self.hospital_code}-{doctor_id}"
        return {
            "staff_id": external_id,
            "external_id": external_id,
            "_doctor_id": doctor_id,
            "name": name,
            "department": dept,
            "position": position,
            "specialty": specialty,
            "profile_url": f"{BASE_URL}/?p=10_view&doctorId={doctor_id}&dType=department",
            "notes": "",
            "schedules": [],
            "date_schedules": [],
        }

    async def _fetch_list_page(self, client: httpx.AsyncClient, page: int) -> list[dict]:
        try:
            resp = await client.post(
                LIST_AJAX,
                data={
                    "page": str(page), "p": "10",
                    "pageNm": "", "gubun": "department", "searchTxt": "",
                },
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[CHAMJE] list page={page} 실패: {e}")
            return []
        html = resp.content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []
        for ul in soup.select("div.medi_staff ul"):
            for li in ul.find_all("li", recursive=False):
                d = self._parse_list_item(li)
                if d:
                    out.append(d)
        return out

    async def _fetch_detail(self, client: httpx.AsyncClient, doctor_id: str) -> dict:
        """상세 페이지에서 스케줄 + 이름/진료과 재확인"""
        url = f"{BASE_URL}/?p=10_view&doctorId={doctor_id}&dType=department"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[CHAMJE] detail {doctor_id} 실패: {e}")
            return {}
        html = resp.content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")

        intro = soup.select_one("div.intro")
        name, dept, position = "", "", ""
        if intro:
            em = intro.find("em")
            if em:
                dept = em.get_text(" ", strip=True)
            strong = intro.find("strong")
            if strong:
                name = strong.get_text(" ", strip=True)
                p_el = strong.parent
                if p_el and p_el.name == "p":
                    position = p_el.get_text(" ", strip=True).replace(name, "", 1).strip()

        # 전문진료분야
        specialty = ""
        spec_tit = soup.find("p", class_="tit", string=lambda s: s and "전문진료분야" in s)
        if spec_tit and spec_tit.find_next_sibling():
            info = spec_tit.find_next_sibling()
            specs = [s.get_text(" ", strip=True) for s in info.find_all("span")]
            specialty = ", ".join(s for s in specs if s)

        tbl = soup.select_one("div.schedule table.cont_tbl")
        schedules = self._parse_schedule_table(tbl)
        return {
            "name": name, "department": dept, "position": position,
            "specialty": specialty, "schedules": schedules,
        }

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            # 1) 모든 목록 페이지
            doctors: list[dict] = []
            seen: set[str] = set()
            for page in range(1, 20):
                items = await self._fetch_list_page(client, page)
                if not items:
                    break
                new = 0
                for d in items:
                    if d["external_id"] not in seen:
                        doctors.append(d)
                        seen.add(d["external_id"])
                        new += 1
                if new == 0:
                    break
            logger.info(f"[CHAMJE] 목록 파싱: {len(doctors)}명")

            # 2) 각 의사 상세 → 스케줄 병합
            for d in doctors:
                detail = await self._fetch_detail(client, d["_doctor_id"])
                if detail:
                    # 상세 페이지 값이 우선 (비어 있으면 목록 값 유지)
                    for k in ("name", "department", "position", "specialty"):
                        v = detail.get(k, "")
                        if v:
                            d[k] = v
                    d["schedules"] = detail.get("schedules", [])
                if any(has_biweekly_mark(s.get("location") or "") for s in d["schedules"]):
                    if not has_biweekly_mark(d.get("notes") or ""):
                        d["notes"] = "격주 근무"

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
            data = [d for d in data if d["department"] == department]
        return [
            {k: d[k] for k in ("staff_id", "external_id", "name", "department",
                                "position", "specialty", "profile_url", "notes")}
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 조회 — 상세 페이지 1회 GET 으로 한 의사만 조회 (rule #7 준수)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 캐시가 있으면 사용
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "") if k not in ("schedules", "date_schedules")
                            else d.get(k, [])
                            for k in ("staff_id", "name", "department", "position",
                                     "specialty", "profile_url", "notes",
                                     "schedules", "date_schedules")}
            return empty

        # external_id → doctorId 파싱
        prefix = f"{self.hospital_code}-"
        doctor_id = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id
        if not doctor_id.isdigit():
            return empty

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            detail = await self._fetch_detail(client, doctor_id)
        if not detail:
            return empty
        schedules = detail.get("schedules", [])
        notes = ""
        if any(has_biweekly_mark(s.get("location") or "") for s in schedules):
            notes = "격주 근무"
        return {
            "staff_id": staff_id,
            "name": detail.get("name", ""),
            "department": detail.get("department", ""),
            "position": detail.get("position", ""),
            "specialty": detail.get("specialty", ""),
            "profile_url": f"{BASE_URL}/?p=10_view&doctorId={doctor_id}&dType=department",
            "notes": notes,
            "schedules": schedules,
            "date_schedules": [],
        }

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
