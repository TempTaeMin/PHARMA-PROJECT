"""충북대학교병원(Chungbuk National University Hospital) 크롤러

병원 공식명: 충북대학교병원
홈페이지: https://www.cbnuh.or.kr
기술: 정적 HTML (httpx + BeautifulSoup), eGovFramework 기반
인코딩: UTF-8 (서버가 명시함)

구조 (목록형 + 개별 상세):
  1) 의료진 목록(페이지네이션):
     /prog/doctor/main/sub01_01_02/list.do?pageIndex={N}
       - 페이지당 10명, `data-key="{drNo}"` 가 의사 고유 ID
       - 각 카드에 이름/진료과/전문분야/사진/주간 시간표 가 모두 들어있음
       - `table#doc_time_table` → 첫 행 헤더(월~금), 2행=오전, 3행=오후, 4행=비고
       - 셀 안의 `<span class="dot on">진료</span>` 가 진료 마크
       - `<span class="tri on">진료</span>` 는 "격주 진료" 마크 (legend 기준)
  2) 의사 상세 페이지: /prog/doctor/main/sub01_01_01/view.do?drNo={drNo}
       - `p.doc_op` (진료과), `strong.doc_name` (이름+직책)
       - `div.doc_sub > span` (전문분야)
       - 같은 `table#doc_time_table` (5컬럼: 월~금)

날짜별 스케줄: cbnuh.or.kr 가 월별 달력을 제공하지 않음 → 주간 패턴을 오늘부터
3개월 앞으로 투영해서 `date_schedules` 채운다.

external_id: `CBNUH-{drNo}`
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "https://www.cbnuh.or.kr"
DOCTOR_LIST_URL = f"{BASE_URL}/prog/doctor/main/sub01_01_02/list.do"
DOCTOR_DETAIL_URL = f"{BASE_URL}/prog/doctor/main/sub01_01_01/view.do"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 충북대 시간표 행 라벨 → time_slot 매핑
SLOT_BY_LABEL = {"오전": "morning", "오후": "afternoon"}
# "야간"·"비고"·"진료시간" 행은 외래 진료가 아님 → 스킵


class CbnuhCrawler:
    """충북대학교병원 크롤러 — 정적 HTML (UTF-8)"""

    def __init__(self):
        self.hospital_code = "CBNUH"
        self.hospital_name = "충북대학교병원"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: Optional[list[dict]] = None
        self._max_pages = 25  # 안전 상한 (현재 약 19페이지)

    # ─── httpx client ─────────────────────────────────────────
    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    # ─── 공용 헬퍼 ─────────────────────────────────────────────
    @staticmethod
    def _clean(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "")).strip()

    @staticmethod
    def _abs_url(src: str) -> str:
        if not src:
            return ""
        if src.startswith("http"):
            return src
        if src.startswith("//"):
            return "https:" + src
        return f"{BASE_URL}/{src.lstrip('/')}"

    # ─── 스케줄 셀 판정 ───────────────────────────────────────
    @staticmethod
    def _cell_is_active(td) -> tuple[bool, bool]:
        """td 셀이 진료 활성인지 판정.

        반환: (active, biweekly)
          - active: schedules 에 추가할지
          - biweekly: 격주 진료 (notes 에 표기 가능)
        """
        if td is None:
            return False, False
        # span.dot.on / span.tri.on 직접 매칭이 가장 확실
        for sp in td.find_all("span"):
            classes = sp.get("class") or []
            if "on" not in classes:
                continue
            txt = (sp.get_text(" ", strip=True) or "")
            # "휴진" 등이 dot.on 으로 표시되는 케이스 방어
            if any(kw in txt for kw in ("휴진", "휴무", "부재", "출장")):
                return False, False
            if any(kw in txt for kw in ("수술", "내시경", "시술", "검사")):
                return False, False
            if "dot" in classes:
                return True, False
            if "tri" in classes:
                return True, True
            # 그 외 on 클래스 → 텍스트 판정
            if is_clinic_cell(txt):
                return True, False
        # 마크가 없어도 셀 텍스트 자체가 진료/시간을 나타내면 포함
        plain = td.get_text(" ", strip=True)
        if plain and is_clinic_cell(plain) and plain not in ("-", ""):
            return True, False
        return False, False

    # ─── 시간표 파싱 ───────────────────────────────────────────
    def _parse_schedule_table(self, tbl) -> tuple[list[dict], bool]:
        """`table#doc_time_table` → (schedules, has_biweekly)

        목록 페이지(6컬럼: 진료시간 + 월~금)와 상세 페이지(5컬럼: 월~금) 모두에서
        동일하게 동작하도록, "오전"/"오후" 라벨을 가진 행만 채택하고
        해당 행에서 첫 라벨 th 를 제외한 td 5개를 월~금 으로 매핑한다.
        """
        schedules: list[dict] = []
        has_biweekly = False
        if tbl is None:
            return schedules, has_biweekly

        for tr in tbl.find_all("tr"):
            # 행 라벨 th: 직접 자식 th 만 (rowspan 등 영향 없도록 첫 th)
            th = tr.find("th")
            if not th:
                continue
            label = self._clean(th.get_text(" ", strip=True))
            slot = SLOT_BY_LABEL.get(label)
            if not slot:
                continue  # "진료시간"/"야간"/"비고"/"" 행 스킵
            tds = tr.find_all("td")
            if not tds:
                continue
            # 5개 td 가 월~금 순서
            for dow, td in enumerate(tds[:5]):
                active, biweekly = self._cell_is_active(td)
                if not active:
                    continue
                start, end = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
                if biweekly:
                    has_biweekly = True
        return schedules, has_biweekly

    # ─── 목록 카드 파싱 ────────────────────────────────────────
    def _parse_doctor_card(self, li) -> Optional[dict]:
        """`<li>` 카드 → dict"""
        # data-key (drNo)
        btn = li.select_one("div.btn_wrap")
        dr_no = (btn.get("data-key") if btn else "") or ""
        if not dr_no:
            return None

        # 이름 + 진료과 (`<p class="doc_name">이름 <em>진료과</em></p>`)
        name_p = li.select_one("p.doc_name")
        if not name_p:
            return None
        em = name_p.find("em")
        department = self._clean(em.get_text(" ", strip=True)) if em else ""
        # em 을 빼고 이름만
        if em:
            em.extract()
        name = self._clean(name_p.get_text(" ", strip=True))
        if not name:
            return None

        # 전문분야: 첫 doc_subjact em
        specialty = ""
        sub_em = li.select_one("p.doc_subjact em")
        if sub_em:
            specialty = self._clean(sub_em.get_text(" ", strip=True))

        # 진료특이사항(있으면 notes 후보)
        notes_extra = ""
        for p in li.select("p.doc_subjact"):
            sp = p.find("span")
            sp_text = self._clean(sp.get_text(" ", strip=True)) if sp else ""
            if sp_text in ("진료특이사항", "특이사항"):
                em2 = p.find("em")
                if em2:
                    notes_extra = self._clean(em2.get_text(" ", strip=True))

        # 사진
        photo_url = ""
        img = li.select_one("div.doc_img img")
        if img:
            photo_url = self._abs_url((img.get("src") or "").strip())

        # 시간표
        tbl = li.select_one("table#doc_time_table")
        schedules, biweekly = self._parse_schedule_table(tbl)

        # 비고 행(있으면 부재/출장 안내일 가능성)
        absence_note = ""
        if tbl:
            for tr in tbl.find_all("tr"):
                th = tr.find("th")
                if th and self._clean(th.get_text()) == "비고":
                    td = tr.find("td")
                    if td:
                        v = self._clean(td.get_text(" ", strip=True))
                        if v and v != "-":
                            absence_note = v

        notes_parts = []
        if biweekly:
            notes_parts.append("격주 진료 일정 포함")
        if absence_note:
            notes_parts.append(absence_note)
        if notes_extra:
            notes_parts.append(notes_extra)
        notes = "\n".join(notes_parts)[:600]

        ext_id = f"CBNUH-{dr_no}"
        profile_url = f"{DOCTOR_DETAIL_URL}?drNo={dr_no}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "dr_no": dr_no,
            "name": name,
            "department": department,
            "position": "",  # 목록에는 직책 없음 → 상세에서 보강
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": notes,
            "schedules": schedules,
            "absence_note": absence_note,
            "date_schedules": [],
        }

    async def _fetch_list_page(
        self, client: httpx.AsyncClient, page_index: int,
    ) -> list[dict]:
        """목록 페이지 1개 → doctor dict 리스트"""
        try:
            resp = await client.get(DOCTOR_LIST_URL, params={"pageIndex": page_index})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[CBNUH] 목록 page={page_index} 로드 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        # 의사 카드 = doc_img 를 포함하는 li
        cards = []
        for li in soup.find_all("li"):
            if li.select_one("div.doc_img") and li.select_one("div.btn_wrap"):
                cards.append(li)
        out: list[dict] = []
        for li in cards:
            try:
                d = self._parse_doctor_card(li)
            except Exception as e:
                logger.warning(f"[CBNUH] 카드 파싱 실패 page={page_index}: {e}")
                continue
            if d:
                out.append(d)
        return out

    # ─── 상세 페이지 파싱 ──────────────────────────────────────
    def _parse_detail(self, html: str, dr_no: str) -> dict:
        """상세 페이지 HTML → dict (목록 카드와 동일 스키마)"""
        empty = {
            "staff_id": f"CBNUH-{dr_no}",
            "external_id": f"CBNUH-{dr_no}",
            "dr_no": dr_no,
            "name": "",
            "department": "",
            "position": "",
            "specialty": "",
            "profile_url": f"{DOCTOR_DETAIL_URL}?drNo={dr_no}",
            "photo_url": "",
            "notes": "",
            "schedules": [],
            "absence_note": "",
            "date_schedules": [],
        }
        soup = BeautifulSoup(html, "html.parser")
        info = soup.select_one("div.doc_team_info") or soup.select_one("div.doc_txt")
        if not info:
            return empty

        # 진료과
        op = info.select_one("p.doc_op")
        department = self._clean(op.get_text(" ", strip=True)) if op else ""

        # 이름 + 직책
        name = ""
        position = ""
        name_strong = info.select_one("strong.doc_name")
        if name_strong:
            spans = name_strong.find_all("span")
            if spans:
                position = self._clean(spans[0].get_text(" ", strip=True))
                for sp in spans:
                    sp.extract()
            name = self._clean(name_strong.get_text(" ", strip=True))

        # 전문분야
        specialty = ""
        sub_span = info.select_one("div.doc_sub span")
        if sub_span:
            specialty = self._clean(sub_span.get_text(" ", strip=True))

        # 사진 (상세에는 없을 수도 있음)
        photo_url = ""
        img = soup.select_one("div.doc_team_info img")
        if img:
            photo_url = self._abs_url((img.get("src") or "").strip())

        # 시간표
        tbl = soup.select_one("table#doc_time_table")
        schedules, biweekly = self._parse_schedule_table(tbl)

        # 비고 행 (-)
        absence_note = ""
        if tbl:
            for tr in tbl.find_all("tr"):
                th = tr.find("th")
                if th and self._clean(th.get_text()) == "비고":
                    td = tr.find("td")
                    if td:
                        v = self._clean(td.get_text(" ", strip=True))
                        if v and v != "-":
                            absence_note = v

        notes_parts = []
        if biweekly:
            notes_parts.append("격주 진료 일정 포함")
        if absence_note:
            notes_parts.append(absence_note)
        notes = "\n".join(notes_parts)[:600]

        ext_id = f"CBNUH-{dr_no}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "dr_no": dr_no,
            "name": name,
            "department": department,
            "position": position,
            "specialty": specialty,
            "profile_url": f"{DOCTOR_DETAIL_URL}?drNo={dr_no}",
            "photo_url": photo_url,
            "notes": notes,
            "schedules": schedules,
            "absence_note": absence_note,
            "date_schedules": [],
        }

    async def _fetch_detail(
        self, client: httpx.AsyncClient, dr_no: str,
    ) -> dict:
        url = f"{DOCTOR_DETAIL_URL}?drNo={dr_no}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[CBNUH] 상세 drNo={dr_no} 로드 실패: {e}")
            return self._parse_detail("", dr_no)
        return self._parse_detail(resp.text, dr_no)

    # ─── 주간 → 3개월 날짜 투영 ────────────────────────────────
    @staticmethod
    def _project_weekly_to_dates(schedules: list[dict]) -> list[dict]:
        if not schedules:
            return []
        today = date.today()
        end = today + timedelta(days=93)  # 약 3개월
        by_dow: dict[int, list[dict]] = {}
        for s in schedules:
            by_dow.setdefault(int(s["day_of_week"]), []).append(s)
        out: list[dict] = []
        cur = today
        while cur <= end:
            dow = cur.weekday()
            if dow in by_dow:
                for s in by_dow[dow]:
                    out.append({
                        "schedule_date": cur.isoformat(),
                        "time_slot": s["time_slot"],
                        "start_time": s["start_time"],
                        "end_time": s["end_time"],
                        "location": s.get("location", ""),
                        "status": "진료",
                    })
            cur += timedelta(days=1)
        return out

    # ─── 진료과 ────────────────────────────────────────────────
    async def get_departments(self) -> list[dict]:
        """전체 의료진을 훑어 진료과 목록을 추출.

        충북대 사이트는 진료과 코드가 없고 진료과 이름만 표시되므로
        `code` 와 `name` 을 동일하게 둔다.
        """
        data = await self._fetch_all()
        seen: dict[str, str] = {}
        for d in data:
            dept = d.get("department") or ""
            if dept and dept not in seen:
                seen[dept] = dept
        return [{"code": v, "name": v} for v in seen.values()]

    # ─── 전체 ──────────────────────────────────────────────────
    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with self._make_client() as client:
            sem = asyncio.Semaphore(4)

            async def _run_page(page_idx: int):
                async with sem:
                    return await self._fetch_list_page(client, page_idx)

            # 우선 페이지 1 부터 끝까지 순차 탐색하되, 빈 페이지가 나오면 멈춘다.
            pages = list(range(1, self._max_pages + 1))
            results = await asyncio.gather(
                *[_run_page(p) for p in pages],
                return_exceptions=True,
            )

            empty_streak = 0
            for r in results:
                if isinstance(r, Exception):
                    continue
                if not r:
                    empty_streak += 1
                    if empty_streak >= 2:
                        # 두 페이지 연속 비어 있으면 사실상 끝
                        pass
                    continue
                empty_streak = 0
                for doc in r:
                    if doc["dr_no"] in all_doctors:
                        continue
                    all_doctors[doc["dr_no"]] = doc

        # 날짜 투영 (네트워크 불필요)
        for doc in all_doctors.values():
            doc["date_schedules"] = self._project_weekly_to_dates(doc["schedules"])

        out = list(all_doctors.values())
        logger.info(f"[CBNUH] 총 {len(out)}명 수집")
        self._cached_data = out
        return out

    # ─── 공개 인터페이스 ──────────────────────────────────────
    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        keys = (
            "staff_id", "external_id", "name", "department",
            "position", "specialty", "profile_url", "notes",
        )
        return [{k: d.get(k, "") for k in keys} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회 — 해당 교수 1명만 네트워크 요청 (skill 규칙 #7)

        충북대는 `view.do?drNo=N` 으로 1명의 시간표/이름/진료과/직책/전문분야가
        모두 같은 페이지에 들어 있어 한 번의 요청으로 끝난다.
        """
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 내 캐시가 있으면 재사용 (crawl_doctors 흐름에서)
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {
                        "staff_id": staff_id,
                        "name": d.get("name", ""),
                        "department": d.get("department", ""),
                        "position": d.get("position", ""),
                        "specialty": d.get("specialty", ""),
                        "profile_url": d.get("profile_url", ""),
                        "notes": d.get("notes", ""),
                        "schedules": d.get("schedules", []),
                        "date_schedules": d.get("date_schedules", []),
                    }
            return empty

        prefix = f"{self.hospital_code}-"
        raw_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not raw_id:
            return empty

        async with self._make_client() as client:
            try:
                detail = await self._fetch_detail(client, raw_id)
            except Exception as e:
                logger.error(f"[CBNUH] 개별 조회 실패 {staff_id}: {e}")
                return empty

        date_schedules = self._project_weekly_to_dates(detail.get("schedules", []))
        return {
            "staff_id": staff_id,
            "name": detail.get("name", ""),
            "department": detail.get("department", ""),
            "position": detail.get("position", ""),
            "specialty": detail.get("specialty", ""),
            "profile_url": detail.get("profile_url", ""),
            "notes": detail.get("notes", ""),
            "schedules": detail.get("schedules", []),
            "date_schedules": date_schedules,
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
                photo_url=d.get("photo_url", ""),
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
