"""계명대학교동산병원(Keimyung University Dongsan Medical Center) 크롤러

병원 공식명: 계명대학교 동산병원
홈페이지: https://dongsan.dsmc.or.kr
  (상위 의료원 포털: https://www.dsmc.or.kr:49848 — 실제 의료진 정보는 dongsan 도메인에 있음)
기술: 정적 HTML (httpx + BeautifulSoup)
인코딩: UTF-8

구조 (3단계):
  1) 진료과 목록: /content/02depart/01_01.php
     - `<a href="/content/02depart/01_0102.php?mp_idx=N" title="{name}">의료진</a>`
  2) 진료과별 의사 목록: /content/02depart/01_0103.php?mp_idx={N}
     - `ul.dr_list > li > div.dr_wrap`
         * `div.photo img` (src, alt)
         * `p.part` = 진료과
         * `p.name` = "{이름} {직책}" (예: "황재석 교수")
         * `p.f_care .conttx` = 진료분야
         * 같은 li 안의 `a.dr_btn[href*="doctor_view.php?md_idx=N"]` = 상세 링크
         * `div.hos_part` = 근무 캠퍼스 (동산병원 / 대구동산병원 등)
         * `table.d_table` = 주간 시간표 (월~금, 오전/오후)
            - `<span class="green">●</span>` 있으면 진료
  3) 의사 상세: /content/02depart/doctor_view.php?md_idx={N}
     - `.doctor_cont` 안에 `.medi`(진료과), `.name`, `.speci`(진료분야)
     - 학력/경력/학회활동/수상 dl/dt/dd

날짜별 스케줄: 월별 달력 미제공 → 주간 패턴을 오늘~3개월로 투영
external_id: `DSMC-{md_idx}`
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://dongsan.dsmc.or.kr:49870"
DEPT_LIST_URL = f"{BASE_URL}/content/02depart/01_01.php"
DEPT_DOCTORS_URL = f"{BASE_URL}/content/02depart/01_0103.php"
DOCTOR_VIEW_URL = f"{BASE_URL}/content/02depart/doctor_view.php"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

MD_IDX_RE = re.compile(r"md_idx=(\d+)")
MP_IDX_RE = re.compile(r"mp_idx=(\d+)")

CLINIC_MARKS = {"●", "○", "◎", "◯", "★", "ㅇ", "O", "V", "v", "◆", "■", "✓"}


class DsmcCrawler:
    """계명대학교동산병원 크롤러 — 정적 HTML (UTF-8)"""

    def __init__(self):
        self.hospital_code = "DSMC"
        self.hospital_name = "계명대학교동산병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: Optional[list[dict]] = None

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

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

    # ─── 진료과 ─────────────────────────────────────────────
    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await client.get(DEPT_LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[DSMC] 진료과 리스트 로드 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        depts: list[dict] = []
        seen: set[str] = set()
        # 사이트 버전에 따라 '/01_0102.php' (소개) 또는 '/01_0103.php' (의료진) 링크에
        # title={진료과명} 이 들어있다. 둘 다 지원한다.
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ("01_0102.php" not in href) and ("01_0103.php" not in href):
                continue
            m = MP_IDX_RE.search(href)
            if not m:
                continue
            title = (a.get("title") or "").strip()
            if not title or title in ("소개", "의료진", "센터", "클리닉"):
                continue
            mp_idx = m.group(1)
            if mp_idx in seen:
                continue
            seen.add(mp_idx)
            depts.append({"code": mp_idx, "name": title})
        return depts

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            return await self._fetch_dept_list(client)

    # ─── 스케줄 테이블 파싱 ─────────────────────────────────
    def _parse_d_table(self, table) -> list[dict]:
        """의사 카드 내 주간 시간표 (월~금 × 오전/오후) → schedules"""
        if table is None:
            return []
        tbody = table.find("tbody")
        if not tbody:
            return []
        rows = tbody.find_all("tr", recursive=False)
        if not rows:
            return []
        schedules: list[dict] = []
        # 각 tr 의 첫 th = "오전"/"오후", 이후 td 5개 = 월~금
        for tr in rows:
            ths = tr.find_all("th", recursive=False)
            slot_label = ""
            if ths:
                slot_label = self._clean(ths[0].get_text(" ", strip=True))
            if "오전" in slot_label:
                slot = "morning"
            elif "오후" in slot_label:
                slot = "afternoon"
            else:
                continue
            tds = tr.find_all("td", recursive=False)
            for dow_idx, td in enumerate(tds[:5]):
                txt = self._clean(td.get_text(" ", strip=True))
                # 외래 제외 키워드
                exclude_kw = ("수술", "내시경", "시술", "초음파", "조영",
                              "CT", "MRI", "PET", "회진", "실험", "연구", "검사")
                inactive_kw = ("휴진", "휴무", "공휴일", "부재", "출장", "학회")
                if any(k in txt for k in inactive_kw):
                    continue
                if any(k in txt for k in exclude_kw):
                    continue
                has_mark = any(m in txt for m in CLINIC_MARKS)
                # span green (●) 또는 다른 마크
                has_span_mark = False
                for sp in td.find_all("span"):
                    sp_txt = self._clean(sp.get_text(" ", strip=True))
                    if any(m in sp_txt for m in CLINIC_MARKS):
                        has_span_mark = True
                        break
                has_kw = any(
                    k in txt for k in (
                        "진료", "외래", "예약", "격주", "순환",
                        "왕진", "클리닉", "상담", "투석", "검진",
                    )
                )
                if not (has_mark or has_span_mark or has_kw):
                    continue
                start, end = TIME_RANGES[slot]
                schedules.append({
                    "day_of_week": dow_idx,  # 0=월..4=금
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
        return schedules

    @staticmethod
    def _project_weekly_to_dates(schedules: list[dict]) -> list[dict]:
        """주간 패턴을 오늘부터 3개월 날짜로 투영"""
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

    # ─── 의사 카드 파싱 ──────────────────────────────────────
    def _parse_doctor_li(self, li, dept_name: str) -> Optional[dict]:
        dr_wrap = li.find("div", class_="dr_wrap")
        if not dr_wrap:
            return None

        # 이름+직책 분리
        name_el = dr_wrap.select_one(".info .name")
        if not name_el:
            return None
        raw_name = self._clean(name_el.get_text(" ", strip=True))
        if not raw_name:
            return None
        parts = raw_name.split()
        name = parts[0] if parts else raw_name
        position = " ".join(parts[1:]) if len(parts) > 1 else ""

        # 진료과
        part_el = dr_wrap.select_one(".info .part")
        department = dept_name
        if part_el:
            txt = self._clean(part_el.get_text(" ", strip=True))
            if txt:
                department = txt

        # 진료분야
        specialty = ""
        care_el = dr_wrap.select_one(".info .f_care .conttx")
        if care_el:
            specialty = self._clean(care_el.get_text(" ", strip=True))

        # 사진
        photo_url = ""
        img = dr_wrap.select_one(".photo img")
        if img:
            photo_url = self._abs_url((img.get("src") or "").strip())

        # md_idx (li 안 어디에라도 있는 doctor_view.php 링크)
        md_idx = ""
        for a in li.find_all("a", href=True):
            m = MD_IDX_RE.search(a["href"])
            if m:
                md_idx = m.group(1)
                break
        if not md_idx:
            return None

        # 근무 캠퍼스 (동산병원 / 대구동산병원)
        campuses: list[str] = []
        hos_part = li.find("div", class_="hos_part")
        if hos_part:
            for p in hos_part.find_all("p"):
                t = self._clean(p.get_text(" ", strip=True))
                if t:
                    campuses.append(t)

        # 스케줄
        table = li.find("table", class_="d_table")
        schedules = self._parse_d_table(table)
        date_schedules = self._project_weekly_to_dates(schedules)

        notes = ""
        if campuses:
            notes = "근무: " + ", ".join(campuses)

        ext_id = f"DSMC-{md_idx}"
        profile_url = f"{DOCTOR_VIEW_URL}?md_idx={md_idx}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "md_idx": md_idx,
            "name": name,
            "department": department,
            "position": position,
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": notes,
            "schedules": schedules,
            "date_schedules": date_schedules,
        }

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        url = f"{DEPT_DOCTORS_URL}?mp_idx={dept_code}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[DSMC] dept {dept_code}({dept_name}) 로드 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        out: list[dict] = []
        for li in soup.select("ul.dr_list > li"):
            try:
                d = self._parse_doctor_li(li, dept_name)
            except Exception as e:
                logger.warning(f"[DSMC] 카드 파싱 실패 ({dept_name}): {e}")
                continue
            if d:
                out.append(d)
        return out

    # ─── 개별 상세 ───────────────────────────────────────────
    async def _fetch_detail(
        self, client: httpx.AsyncClient, md_idx: str,
    ) -> dict:
        url = f"{DOCTOR_VIEW_URL}?md_idx={md_idx}"
        empty = {
            "name": "", "department": "", "position": "",
            "specialty": "", "photo_url": "", "notes": "",
            "profile_url": url, "schedules": [],
        }
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[DSMC] 상세 로드 실패 md_idx={md_idx}: {e}")
            return empty
        soup = BeautifulSoup(resp.text, "html.parser")
        cont = soup.select_one(".doctor_cont")
        name = ""
        department = ""
        position = ""
        specialty = ""
        if cont:
            dep = cont.select_one(".medi")
            if dep:
                department = self._clean(dep.get_text(" ", strip=True))
            name_el = cont.select_one(".name")
            if name_el:
                raw = self._clean(name_el.get_text(" ", strip=True))
                parts = raw.split()
                name = parts[0] if parts else raw
                position = " ".join(parts[1:]) if len(parts) > 1 else ""
            spec_el = cont.select_one(".speci")
            if spec_el:
                ps = spec_el.find_all("p")
                if len(ps) >= 2:
                    specialty = self._clean(ps[-1].get_text(" ", strip=True))
                else:
                    specialty = self._clean(spec_el.get_text(" ", strip=True))

        photo_url = ""
        img = soup.select_one(".img_wrap .swiper-slide img") or soup.select_one(".doctor_wrap img")
        if img:
            photo_url = self._abs_url((img.get("src") or "").strip())

        # notes: 학력/경력 + 학회활동 요약
        notes_parts: list[str] = []
        for sec in soup.select(".prd_list"):
            tit = sec.find("h4")
            if not tit:
                continue
            key = self._clean(tit.get_text(" ", strip=True))
            if key not in ("학력/경력", "학회활동", "수상"):
                continue
            lines: list[str] = []
            for dl in sec.select(".history dl"):
                dt = dl.find("dt")
                dd = dl.find("dd")
                dt_t = self._clean(dt.get_text(" ", strip=True)) if dt else ""
                if dd:
                    for li in dd.find_all("li"):
                        t = self._clean(li.get_text(" ", strip=True))
                        if not t:
                            continue
                        lines.append(f"{dt_t}  {t}" if dt_t else t)
            if lines:
                notes_parts.append(f"[{key}]\n" + "\n".join(lines[:10]))
        notes = "\n\n".join(notes_parts)[:1000]

        # 스케줄 (상세에도 table_doctor 있음)
        schedules: list[dict] = []
        tbl = soup.select_one("table.table_doctor")
        if tbl:
            schedules = self._parse_d_table(tbl)

        return {
            "name": name,
            "department": department,
            "position": position,
            "specialty": specialty,
            "photo_url": photo_url,
            "notes": notes,
            "profile_url": url,
            "schedules": schedules,
        }

    # ─── 전체 ──────────────────────────────────────────────
    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            if not depts:
                logger.error("[DSMC] 진료과 0개 — 크롤링 중단")
                self._cached_data = []
                return []

            sem = asyncio.Semaphore(6)

            async def _run(d):
                async with sem:
                    return await self._fetch_dept_doctors(client, d["code"], d["name"])

            results = await asyncio.gather(
                *[_run(d) for d in depts],
                return_exceptions=True,
            )
            seen: dict[str, dict] = {}
            for r in results:
                if isinstance(r, Exception):
                    continue
                for doc in r:
                    if doc["md_idx"] in seen:
                        continue
                    seen[doc["md_idx"]] = doc

        out = list(seen.values())
        logger.info(f"[DSMC] 총 {len(out)}명 수집")
        self._cached_data = out
        return out

    # ─── 공개 인터페이스 ──────────────────────────────────
    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        keys = ("staff_id", "external_id", "name", "department",
                "position", "specialty", "profile_url", "notes")
        return [{k: d.get(k, "") for k in keys} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회 — 해당 교수 1명만 네트워크 요청 (skill 규칙 #7)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

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
        raw_idx = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not raw_idx.isdigit():
            return empty

        async with self._make_client() as client:
            detail = await self._fetch_detail(client, raw_idx)

        schedules = detail.get("schedules", [])
        date_schedules = self._project_weekly_to_dates(schedules)
        return {
            "staff_id": staff_id,
            "name": detail.get("name", ""),
            "department": detail.get("department", ""),
            "position": detail.get("position", ""),
            "specialty": detail.get("specialty", ""),
            "profile_url": detail.get("profile_url", ""),
            "notes": detail.get("notes", ""),
            "schedules": schedules,
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
