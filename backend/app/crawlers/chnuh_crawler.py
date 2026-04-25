"""충남대학교병원(Chungnam National University Hospital) 크롤러

병원 공식명 : 충남대학교병원
홈페이지     : https://www.cnuh.co.kr  (메인 홈은 /home/index.do)
HOSPITAL_CODE: CHNUH (전남대 JNUH 와 충돌 회피)
기술         : 정적 HTML (httpx + BeautifulSoup)
인코딩       : UTF-8

사이트 구조 요약 (3 단계):
  1) 진료과 목록   : /home/index.do 의 좌측 GNB / 또는 /prog/cnuhTreatment/home/list.do
       - 의료진 페이지의 `<select id="gwaCode">` 에 모든 진료과 코드/이름이 들어있어
         이를 단일 진실 원천(SOT)으로 사용한다.
  2) 진료과별 의사 : /prog/cnuhTreatment/home/view.do?gwaCode={GWA}&mno=sub01_0101&tabGubun=tab2
       - `div.lists ul li > div.block` 가 의사 카드
         · 이름/진료과 : `strong` (텍스트 = 이름, 자식 `<span>` = 진료과)
         · 전문분야    : `<p>` 첫 번째
         · 부가설명    : `<p><span class="color-blue">` (예: "건강검진센터(매주2회) : 월,화" 등)
         · 사진        : `div.photos > img[src]`
         · 상세 링크   : `a[href*=doctorId]` → /prog/cnuhDoctor/homepage.do?doctorId={DC...}
         · 진료시간표  : `<table>` (thead 7개 = 월~일, tbody 첫 두 행 = 오전/오후,
                         td 안에 `<span>진료</span>` 또는 `<em>(부가)</em>` 가 있으면 진료)
  3) 개별 의사 상세: /prog/cnuhDoctor/homepage.do?doctorId={DC...}
       - 동일 형식 진료시간표 + 학력/경력/학회활동/임상내용 H3 섹션
       - `<select id="gwaCode">` 의 selected option 으로 진료과 검증

날짜별 스케줄:
  cnuh.co.kr 가 월별 달력을 제공하지 않음 → 주간 패턴을 오늘부터 3개월치
  실제 날짜로 투영해 `date_schedules` 채움.

external_id : `CHNUH-{doctorId}`  예) CHNUH-DC00000140
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

BASE_URL = "https://www.cnuh.co.kr"
DEPT_VIEW_URL = f"{BASE_URL}/prog/cnuhTreatment/home/view.do"
DEPT_LIST_URL = f"{BASE_URL}/prog/cnuhTreatment/home/list.do"
DOCTOR_HOME_URL = f"{BASE_URL}/prog/cnuhDoctor/homepage.do"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DOCTOR_ID_RE = re.compile(r"doctorId=([A-Za-z0-9]+)")


class ChnuhCrawler:
    """충남대학교병원 크롤러 — 정적 HTML (UTF-8)

    HOSPITAL_CODE = "CHNUH" (전남대 JNUH 와 코드 충돌 회피)
    """

    def __init__(self):
        self.hospital_code = "CHNUH"
        self.hospital_name = "충남대학교병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/home/index.do",
        }
        self._cached_data: Optional[list[dict]] = None
        self._dept_cache: Optional[list[dict]] = None  # [{code, name}, ...]

    # ─── httpx 클라이언트 ─────────────────────────────────────
    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers,
            timeout=30,
            follow_redirects=True,
            verify=False,
        )

    # ─── 공용 헬퍼 ────────────────────────────────────────────
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

    @staticmethod
    async def _get(client: httpx.AsyncClient, url: str) -> str:
        """UTF-8 로 디코드해 반환. 실패 시 빈 문자열."""
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[CHNUH] GET 실패 {url}: {e}")
            return ""
        try:
            return resp.content.decode("utf-8", errors="replace")
        except Exception:
            return resp.text

    # ─── 진료과 ───────────────────────────────────────────────
    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        """진료과 코드/이름 목록 추출.

        1차: `list.do` 의 진료과 카드 — 각 카드 `div.photos > img[alt]` 에 진료과명,
              `a[href*=gwaCode]` 에 코드가 있다.
        2차(폴백): 임의 의사 homepage.do 의 `select#gwaCode` (전체 진료과 목록).
        """
        if self._dept_cache is not None:
            return self._dept_cache

        depts: list[dict] = []
        seen: set[str] = set()

        # 1차: list.do
        list_text = await self._get(client, DEPT_LIST_URL + "?ordBy=gwaName")
        if list_text:
            lsoup = BeautifulSoup(list_text, "html.parser")
            # 각 진료과 카드는 `div.photos` 를 포함하며 그 안의 img[alt] 에 진료과명
            for photos in lsoup.select("div.photos"):
                img = photos.find("img")
                if not img:
                    continue
                name = self._clean((img.get("alt") or ""))
                if not name:
                    continue
                # 가까운 a[href*=gwaCode] 에서 코드 추출
                container = photos.parent or photos
                a = container.select_one("a[href*=gwaCode]") if hasattr(container, "select_one") else None
                if not a:
                    # photos 자체나 그 형제에서 찾기
                    a = photos.find_next("a", href=re.compile(r"gwaCode="))
                if not a:
                    continue
                m = re.search(r"gwaCode=([A-Za-z0-9]+)", a.get("href", ""))
                if not m:
                    continue
                code = m.group(1)
                if code in seen:
                    continue
                seen.add(code)
                depts.append({"code": code, "name": name})

        # 2차 폴백: homepage.do 의 select#gwaCode
        if not depts:
            # 임의의 doctorId 가 필요 — list.do 에서 한 의사 페이지를 찾아본다.
            sample_id = ""
            if list_text:
                m = DOCTOR_ID_RE.search(list_text)
                if m:
                    sample_id = m.group(1)
            if not sample_id:
                # FM 진료과 첫 의사로 시도
                fm_text = await self._get(
                    client,
                    f"{DEPT_VIEW_URL}?gwaCode=FM&mno=sub01_0101&tabGubun=tab2",
                )
                if fm_text:
                    m = DOCTOR_ID_RE.search(fm_text)
                    if m:
                        sample_id = m.group(1)
            if sample_id:
                hp_text = await self._get(
                    client, f"{DOCTOR_HOME_URL}?doctorId={sample_id}"
                )
                if hp_text:
                    hsoup = BeautifulSoup(hp_text, "html.parser")
                    sel = hsoup.select_one("select#gwaCode")
                    if sel:
                        for opt in sel.find_all("option"):
                            code = (opt.get("value") or "").strip()
                            name = self._clean(opt.get_text(" ", strip=True))
                            if not code or not name or name.startswith("-"):
                                continue
                            if code in seen:
                                continue
                            seen.add(code)
                            depts.append({"code": code, "name": name})

        self._dept_cache = depts
        return depts

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
        return [{"code": d["code"], "name": d["name"]} for d in depts]

    # ─── 진료시간표 파싱 ──────────────────────────────────────
    def _parse_schedule_table(self, tbl) -> list[dict]:
        """`<table>` (thead 월~일, tbody 오전/오후) → schedules 리스트

        td 안에 `<span>진료</span>` 또는 `<em>(부가)</em>` 가 있거나 텍스트가
        외래로 판정되면 진료 슬롯으로 추가.
        """
        schedules: list[dict] = []
        if not tbl:
            return schedules

        # thead 의 컬럼 순서를 day_of_week 매핑으로 구성
        thead = tbl.find("thead")
        if not thead:
            return schedules
        head_ths = thead.find_all("th")
        # 첫 번째 th 는 빈칸(시간대 라벨), 이후 th 들이 요일
        day_map = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
        col_dows: list[int] = []
        for th in head_ths[1:]:
            t = self._clean(th.get_text(" ", strip=True))
            col_dows.append(day_map.get(t, -1))

        tbody = tbl.find("tbody")
        if not tbody:
            return schedules

        for tr in tbody.find_all("tr", recursive=False):
            tds = tr.find_all("td", recursive=False)
            row_th = tr.find("th")
            slot_label = self._clean(row_th.get_text(" ", strip=True)) if row_th else ""
            if "오전" in slot_label:
                slot = "morning"
            elif "오후" in slot_label:
                slot = "afternoon"
            else:
                # "비고" 같은 행은 건너뜀
                continue
            # td 가 7개여야 정상 — 모자라거나 (col5 colspan) 안내성 행은 skip
            if len(tds) < 7:
                continue

            for idx, td in enumerate(tds[:7]):
                if idx >= len(col_dows):
                    break
                dow = col_dows[idx]
                if dow < 0:
                    continue

                # span 의 자체 텍스트 + em 의 부가설명 분리
                span = td.find("span")
                em = td.find("em")
                span_text = self._clean(span.get_text(" ", strip=True)) if span else ""
                em_text = self._clean(em.get_text(" ", strip=True)) if em else ""
                cell_text = (span_text + " " + em_text).strip()

                # 빈 셀은 진료 없음
                if not cell_text:
                    continue

                # 외래 진료 판정.
                # CHNUH 는 활성 셀에 `<span>가능</span>` 마크를 사용하므로
                # 공용 is_clinic_cell 외에 `가능` 도 클리닉 마크로 인정한다.
                # 단 EXCLUDE/INACTIVE 키워드 검사는 그대로 유지.
                if not is_clinic_cell(cell_text):
                    if "가능" not in cell_text:
                        continue
                    # 가능 매칭 — 그러나 EXCLUDE/INACTIVE 키워드 보호
                    from app.crawlers._schedule_rules import (
                        EXCLUDE_KEYWORDS, INACTIVE_KEYWORDS,
                    )
                    if any(k in cell_text for k in INACTIVE_KEYWORDS):
                        continue
                    if any(k in cell_text for k in EXCLUDE_KEYWORDS):
                        continue

                # location: em 의 (괄호) 안 텍스트가 진료 장소인 경우가 많음
                # 예: "(통합건강증진센터)" → "통합건강증진센터"
                location = ""
                if em_text:
                    m = re.search(r"\(([^)]+)\)", em_text)
                    if m:
                        location = self._clean(m.group(1))
                    else:
                        location = em_text

                start, end = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": location,
                })
        return schedules

    # ─── 의사 카드 파싱 ───────────────────────────────────────
    def _parse_doctor_card(self, block, dept_code: str, dept_name: str) -> Optional[dict]:
        """의사 카드(`div.block`) → dict"""
        # 상세 링크 / doctorId
        a = block.select_one("a[href*=doctorId]")
        if not a:
            return None
        href = a.get("href", "")
        m = DOCTOR_ID_RE.search(href)
        if not m:
            return None
        doctor_id = m.group(1)

        # 이름 + 진료과 (strong > 텍스트 + span)
        strong = block.find("strong", recursive=True)
        name = ""
        dept_in_card = ""
        if strong:
            # 이름은 strong 의 직속 텍스트, span 은 진료과
            sub_span = strong.find("span")
            if sub_span:
                dept_in_card = self._clean(sub_span.get_text(" ", strip=True))
                # span 제거 후 strong 의 나머지 텍스트
                sub_span.extract()
                name = self._clean(strong.get_text(" ", strip=True))
            else:
                name = self._clean(strong.get_text(" ", strip=True))
        if not name:
            return None

        # 전문분야 (첫 번째 p) + notes (color-blue 보충 안내)
        specialty = ""
        notes_extra = ""
        ps = block.find_all("p")
        if ps:
            specialty = self._clean(ps[0].get_text(" ", strip=True))
            for p in ps[1:]:
                cb = p.find("span", class_="color-blue")
                if cb:
                    notes_extra = self._clean(cb.get_text("\n", strip=True))
                    break

        # 사진
        photo_url = ""
        img = block.select_one("div.photos img")
        if img:
            photo_url = self._abs_url((img.get("src") or "").strip())

        # 진료시간표
        tbl = block.find("table")
        schedules = self._parse_schedule_table(tbl)

        ext_id = f"CHNUH-{doctor_id}"
        profile_url = f"{DOCTOR_HOME_URL}?doctorId={doctor_id}"

        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "doctor_id": doctor_id,
            "dept_code": dept_code,
            "name": name,
            "department": dept_in_card or dept_name,
            "position": "",  # 카드에는 직책 없음 (상세 진입해야 보일 수도 있음)
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": notes_extra,
            "schedules": schedules,
            "date_schedules": [],
        }

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        url = f"{DEPT_VIEW_URL}?gwaCode={dept_code}&mno=sub01_0101&tabGubun=tab2"
        text = await self._get(client, url)
        if not text:
            return []
        soup = BeautifulSoup(text, "html.parser")
        out: list[dict] = []
        for block in soup.select("div.lists ul li div.block"):
            try:
                d = self._parse_doctor_card(block, dept_code, dept_name)
            except Exception as e:
                logger.warning(f"[CHNUH] 카드 파싱 실패 ({dept_name}): {e}")
                continue
            if d:
                out.append(d)
        return out

    # ─── 개별 의사 상세 ───────────────────────────────────────
    def _parse_doctor_homepage(self, html: str, doctor_id: str) -> dict:
        """의사 homepage.do 파싱 → 부가 상세(학력/경력 등 → notes), 시간표"""
        empty = {
            "name": "", "department": "", "position": "",
            "specialty": "", "notes": "",
            "profile_url": f"{DOCTOR_HOME_URL}?doctorId={doctor_id}",
            "photo_url": "", "schedules": [],
        }
        if not html:
            return empty
        soup = BeautifulSoup(html, "html.parser")

        # 진료과: select#gwaCode 의 selected option
        department = ""
        sel_gwa = soup.select_one("select#gwaCode")
        if sel_gwa:
            opt = sel_gwa.find("option", selected=True)
            if opt:
                department = self._clean(opt.get_text(" ", strip=True))

        # 이름 + 직책: "{진료과} {이름} 교수 자세히보기" 형태의 strong 에서 추출
        name = ""
        position = ""
        for s in soup.find_all("strong"):
            t = self._clean(s.get_text(" ", strip=True))
            if not t or "바로가기" in t:
                continue
            # 패턴: "{진료과} {이름} {직책} 자세히보기"  또는  "{진료과} {이름} 진료"
            if "자세히보기" in t:
                head = t.replace("자세히보기", "").strip()
                toks = head.split()
                if len(toks) >= 2:
                    # 마지막 토큰이 직책(교수/임상교수/조교수 등)
                    position = toks[-1]
                    # 이름은 직책 앞 토큰 (가장 우측)
                    name = toks[-2]
                break

        # 사진
        photo_url = ""
        photo_img = soup.select_one("div.photos img")
        if photo_img:
            photo_url = self._abs_url((photo_img.get("src") or "").strip())

        # 학력/경력/학회활동/임상내용 → notes
        notes_parts: list[str] = []
        for h3 in soup.select("h3"):
            label = self._clean(h3.get_text(" ", strip=True))
            if not label:
                continue
            sib = h3.find_next_sibling()
            if not sib:
                continue
            body = self._clean(sib.get_text("\n", strip=True))
            if body:
                notes_parts.append(f"[{label}]\n{body}")
        notes = "\n\n".join(notes_parts)[:800]

        # 진료시간표
        tbl = soup.find("table")
        schedules = self._parse_schedule_table(tbl) if tbl else []

        return {
            "name": name,
            "department": department,
            "position": position,
            "specialty": "",
            "notes": notes,
            "profile_url": f"{DOCTOR_HOME_URL}?doctorId={doctor_id}",
            "photo_url": photo_url,
            "schedules": schedules,
        }

    # ─── 주간 → 3개월 날짜 투영 ───────────────────────────────
    def _project_weekly_to_dates(self, schedules: list[dict]) -> list[dict]:
        if not schedules:
            return []
        today = date.today()
        end = today + timedelta(days=93)

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

    # ─── 전체 ─────────────────────────────────────────────────
    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            if not depts:
                logger.error("[CHNUH] 진료과가 0개 — 크롤링 중단")
                self._cached_data = []
                return []

            sem = asyncio.Semaphore(6)

            async def _run_dept(d: dict):
                async with sem:
                    return await self._fetch_dept_doctors(client, d["code"], d["name"])

            results = await asyncio.gather(
                *[_run_dept(d) for d in depts],
                return_exceptions=True,
            )

        # 중복 제거: 같은 doctorId 는 첫 진료과만 유지 (단, 스케줄은 합산)
        seen: dict[str, dict] = {}
        for r in results:
            if isinstance(r, Exception):
                continue
            for doc in r:
                key = doc["doctor_id"]
                if key not in seen:
                    seen[key] = doc
                else:
                    # 같은 의사가 다른 진료과에서 또 등장하면 스케줄만 합치기
                    existing = seen[key]
                    seen_keys = {
                        (s["day_of_week"], s["time_slot"], s.get("location", ""))
                        for s in existing["schedules"]
                    }
                    for s in doc["schedules"]:
                        k2 = (s["day_of_week"], s["time_slot"], s.get("location", ""))
                        if k2 not in seen_keys:
                            existing["schedules"].append(s)
                            seen_keys.add(k2)

        # 날짜 투영
        for doc in seen.values():
            doc["date_schedules"] = self._project_weekly_to_dates(doc["schedules"])

        out = list(seen.values())
        logger.info(f"[CHNUH] 총 {len(out)}명 / 진료과 {len(depts)}개 수집")
        self._cached_data = out
        return out

    # ─── 공개 인터페이스 ─────────────────────────────────────
    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        keys = ("staff_id", "external_id", "name", "department",
                "position", "specialty", "profile_url", "notes")
        return [{k: d.get(k, "") for k in keys} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회 — 해당 교수 1명의 homepage.do 만 호출 (skill 규칙 #7)."""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 캐시
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
        doctor_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not doctor_id:
            return empty

        url = f"{DOCTOR_HOME_URL}?doctorId={doctor_id}"
        async with self._make_client() as client:
            html = await self._get(client, url)
            if not html:
                return empty
            detail = self._parse_doctor_homepage(html, doctor_id)

            # 의사 카드 페이지에서 specialty / notes(보충 안내) 보강.
            # 진료과 코드를 찾아 1개 진료과만 1회 GET (전체 크롤링 금지).
            specialty = ""
            notes_extra = ""
            if detail.get("department"):
                depts = await self._fetch_dept_list(client)
                dept_code = ""
                for d in depts:
                    if d["name"] == detail["department"]:
                        dept_code = d["code"]
                        break
                if dept_code:
                    dept_docs = await self._fetch_dept_doctors(
                        client, dept_code, detail["department"]
                    )
                    for doc in dept_docs:
                        if doc["doctor_id"] == doctor_id:
                            specialty = doc.get("specialty", "")
                            notes_extra = doc.get("notes", "")
                            # homepage 에서 못 잡은 경우 보강
                            if not detail["name"]:
                                detail["name"] = doc.get("name", "")
                            if not detail["photo_url"]:
                                detail["photo_url"] = doc.get("photo_url", "")
                            # homepage 시간표가 비었으면 카드 시간표로 폴백
                            if not detail["schedules"]:
                                detail["schedules"] = doc.get("schedules", [])
                            break

        notes_final = detail.get("notes", "")
        if notes_extra:
            notes_final = (notes_extra + "\n\n" + notes_final).strip()
        notes_final = notes_final[:800]

        date_schedules = self._project_weekly_to_dates(detail.get("schedules", []))

        return {
            "staff_id": staff_id,
            "name": detail.get("name", ""),
            "department": detail.get("department", ""),
            "position": detail.get("position", ""),
            "specialty": specialty,
            "profile_url": detail.get("profile_url", url),
            "notes": notes_final,
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
