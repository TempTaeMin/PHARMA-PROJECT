"""울산대학교병원(Ulsan University Hospital) 크롤러

병원 공식명: 울산대학교병원
홈페이지: https://www.uuh.ulsan.kr
기술: 정적 HTML (httpx + BeautifulSoup)
인코딩: UTF-8

구조 (3단계):
  1) 진료과 목록: /kr/index.php?pCode=treat
     - `div.mpart-hover > p` = 진료과 이름
     - 그 안의 `a[href*="idx=N&tab=2"]` = 의료진 탭 진입 idx
  2) 진료과별 의료진 목록: /kr/index.php?pCode=treat&mode=view&idx={dept_idx}&tab=2
     - `div.doctor-list-box > ul > li` 의사 카드
         * `<a class="btnMore" href="?pCode=doctor&idx={dr_idx}">`
         * `<strong class="name">` = 이름, `<span class="pos">` = 직책
         * `.m-pt-cont` = 진료분야
         * `.doctor-th img[src]` = 사진
  3) 의사 상세: /kr/index.php?pCode=doctor&idx={dr_idx}
     - `#docIntro .teamIntro_visual` → 이름/진료과/진료분야
     - `div.doc-list ul li.doc-item` = 학력/경력/소속학회/직책
     - `div.month_schedule .team_table table` = 월간 진료일정
         * thead tr: 날짜 (N<br>요일) 컬럼들
         * tbody tr[0] = 오전, tbody tr[1] = 오후
         * 각 td 에 `<span class="ex_01">진료</span>` 있으면 진료
         * `ex_02` 클리닉, `ex_03` 휴진, 빈 span = 해당사항 없음
     - 다음 달: ?pCode=doctor&idx={dr_idx}&next=Y

external_id: `UUH-{dr_idx}`
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.uuh.ulsan.kr"
TREAT_URL = f"{BASE_URL}/kr/index.php?pCode=treat"
DEPT_VIEW_URL = f"{BASE_URL}/kr/index.php"  # ?pCode=treat&mode=view&idx=N&tab=2
DOCTOR_URL = f"{BASE_URL}/kr/index.php"     # ?pCode=doctor&idx=N

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 진료(clinic) 표시 클래스 — ex_01=진료, ex_02=클리닉
CLINIC_SPAN_CLASSES = {"ex_01", "ex_02"}

DR_LINK_RE = re.compile(r"pCode=doctor&(?:amp;)?idx=(\d+)")
DEPT_IDX_RE = re.compile(r"pCode=treat&(?:amp;)?mode=view&(?:amp;)?idx=(\d+)")
TH_DATE_RE = re.compile(r"^\s*(\d{1,2})\s*")


class UuhCrawler:
    """울산대학교병원 크롤러 — 정적 HTML (UTF-8)"""

    def __init__(self):
        self.hospital_code = "UUH"
        self.hospital_name = "울산대학교병원"
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

    # ─── 유틸 ─────────────────────────────────────────────
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

    # ─── 진료과 ───────────────────────────────────────────
    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await client.get(TREAT_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[UUH] 진료과 리스트 로드 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        depts: list[dict] = []
        seen: set[str] = set()
        for block in soup.select("div.mpart-hover"):
            p = block.find("p")
            if not p:
                continue
            name = self._clean(p.get_text(" ", strip=True))
            if not name:
                continue
            # 의료진 탭 a 요소에서 idx 추출
            idx_val = ""
            for a in block.find_all("a", href=True):
                m = DEPT_IDX_RE.search(a["href"])
                if m:
                    idx_val = m.group(1)
                    break
            if not idx_val or idx_val in seen:
                continue
            seen.add(idx_val)
            depts.append({"code": idx_val, "name": name})
        return depts

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            return await self._fetch_dept_list(client)

    # ─── 진료과별 의사 카드 ────────────────────────────────
    def _parse_doctor_card(self, li, dept_name: str) -> Optional[dict]:
        a = li.find("a", class_="btnMore", href=True)
        if not a:
            a = li.find("a", href=True)
        dr_idx = ""
        if a:
            m = DR_LINK_RE.search(a.get("href", ""))
            if m:
                dr_idx = m.group(1)
        if not dr_idx:
            # 상세보기 링크에서도 탐색
            for anchor in li.find_all("a", href=True):
                m = DR_LINK_RE.search(anchor["href"])
                if m:
                    dr_idx = m.group(1)
                    break
        if not dr_idx:
            return None

        name = ""
        strong = li.select_one(".doc-info-wr .name") or li.find("strong", class_="name")
        if strong:
            name = self._clean(strong.get_text(" ", strip=True))
        if not name:
            # 이미지 alt 폴백
            img = li.select_one(".doctor-th img")
            if img:
                name = self._clean(img.get("alt") or "")
        if not name:
            return None

        position = ""
        pos_el = li.select_one(".doc-info-wr .pos") or li.find("span", class_="pos")
        if pos_el:
            position = self._clean(pos_el.get_text(" ", strip=True))

        specialty = ""
        sp_el = li.select_one(".m-pt-cont")
        if sp_el:
            specialty = self._clean(sp_el.get_text(" ", strip=True))

        photo_url = ""
        img = li.select_one(".doctor-th img")
        if img:
            photo_url = self._abs_url((img.get("src") or "").strip())

        ext_id = f"UUH-{dr_idx}"
        profile_url = f"{DOCTOR_URL}?pCode=doctor&idx={dr_idx}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "dr_idx": dr_idx,
            "name": name,
            "department": dept_name,
            "position": position,
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": "",
            "schedules": [],
            "date_schedules": [],
        }

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        url = f"{DEPT_VIEW_URL}?pCode=treat&mode=view&idx={dept_code}&tab=2"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[UUH] dept {dept_code}({dept_name}) 로드 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        box = soup.select_one("div.doctor-list-box")
        if not box:
            return []
        out: list[dict] = []
        for li in box.select("ul > li"):
            try:
                d = self._parse_doctor_card(li, dept_name)
            except Exception as e:
                logger.warning(f"[UUH] 카드 파싱 실패 ({dept_name}): {e}")
                continue
            if d:
                out.append(d)
        return out

    # ─── 스케줄 파싱 (월간 달력) ───────────────────────────
    def _parse_schedule_page(
        self, html: str,
    ) -> tuple[list[dict], list[dict], dict]:
        """
        returns: (schedules, date_schedules_for_this_month, doctor_meta)
          * doctor_meta = {name, department, position, specialty, photo_url, notes}
        """
        soup = BeautifulSoup(html, "html.parser")

        # 의사 메타 (teamIntro_visual)
        meta = {
            "name": "", "department": "", "position": "",
            "specialty": "", "photo_url": "", "notes": "",
        }
        intro = soup.select_one("#docIntro .teamIntro_visual")
        if intro:
            dep = intro.select_one(".depart")
            if dep:
                meta["department"] = self._clean(dep.get_text(" ", strip=True))
            nm = intro.select_one(".txt01")
            if nm:
                meta["name"] = self._clean(nm.get_text(" ", strip=True))
            pos = intro.select_one(".txt02")
            if pos:
                meta["position"] = self._clean(pos.get_text(" ", strip=True))
            if not meta["position"]:
                # h2 안에 직책이 없는 경우 있음, 위치 span에서 시도
                pass
            # 진료분야
            fi01 = intro.select_one(".fi01 span")
            if fi01:
                meta["specialty"] = self._clean(fi01.get_text(" ", strip=True))
            img = intro.select_one(".docImg img")
            if img:
                meta["photo_url"] = self._abs_url((img.get("src") or "").strip())

        # notes: 학력/경력/소속학회
        notes_parts: list[str] = []
        for item in soup.select("#doctorInfo li.doc-item"):
            tit = item.find("h3", class_="tit")
            if not tit:
                continue
            key = self._clean(tit.get_text(" ", strip=True))
            if key in ("논문", "언론"):
                continue
            lis = item.select("ul.c-list01 > li")
            lines = [self._clean(x.get_text(" ", strip=True)) for x in lis]
            lines = [x for x in lines if x]
            if lines:
                notes_parts.append(f"[{key}] " + ", ".join(lines))
        meta["notes"] = "\n".join(notes_parts)[:800]

        # 스케줄 테이블
        schedules: list[dict] = []
        date_schedules: list[dict] = []
        table = soup.select_one(".month_schedule .team_table table")
        if not table:
            return [], [], meta

        # 월 추출
        month_sel = soup.select_one(".month_schedule .team_gnb .tit span")
        cur_year = date.today().year
        cur_month = date.today().month
        if month_sel:
            mm = re.search(r"(\d{1,2})\s*월", month_sel.get_text(" ", strip=True))
            if mm:
                parsed_month = int(mm.group(1))
                # 연도는 보여주지 않으므로 오늘 기준으로 가장 가까운 해 선택
                today = date.today()
                # parsed_month 가 현재 월보다 작으면 다음 해로 판정
                if parsed_month >= today.month:
                    cur_year = today.year
                else:
                    cur_year = today.year + 1
                cur_month = parsed_month

        # thead 의 날짜 컬럼 (일자 순서)
        thead = table.find("thead")
        if not thead:
            return [], [], meta
        ths = thead.find_all("th")
        # 첫 th 는 "날짜"
        day_cols: list[int] = []  # 각 컬럼의 일자 (1..31)
        for th in ths[1:]:
            txt = th.get_text(" ", strip=True)
            m = re.search(r"(\d{1,2})", txt)
            if m:
                day_cols.append(int(m.group(1)))
            else:
                day_cols.append(0)  # 해당 없음

        tbody = table.find("tbody")
        if not tbody:
            return [], [], meta
        rows = tbody.find_all("tr", recursive=False)

        today = date.today()
        weekly_set: set[tuple[int, str]] = set()

        for row_idx, tr in enumerate(rows[:2]):  # 0=오전, 1=오후
            slot = "morning" if row_idx == 0 else "afternoon"
            start, end = TIME_RANGES[slot]
            tds = tr.find_all("td", recursive=False)
            for ci, td in enumerate(tds):
                if ci >= len(day_cols):
                    break
                day_num = day_cols[ci]
                if day_num == 0:
                    continue
                # `<span class="ex_01">` 등
                marker = None
                for sp in td.find_all("span", recursive=False):
                    cls_list = sp.get("class") or []
                    for c in cls_list:
                        if c in CLINIC_SPAN_CLASSES:
                            marker = c
                            break
                    if marker:
                        break
                if not marker:
                    # 중첩 span 도 체크
                    for sp in td.find_all("span"):
                        cls_list = sp.get("class") or []
                        if any(c in CLINIC_SPAN_CLASSES for c in cls_list):
                            marker = "match"
                            break
                if not marker:
                    continue

                try:
                    the_date = date(cur_year, cur_month, day_num)
                except ValueError:
                    continue

                dow = the_date.weekday()
                weekly_set.add((dow, slot))
                if the_date >= today:
                    date_schedules.append({
                        "schedule_date": the_date.isoformat(),
                        "time_slot": slot,
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                        "status": "진료",
                    })

        schedules = [
            {
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": TIME_RANGES[slot][0],
                "end_time": TIME_RANGES[slot][1],
                "location": "",
            }
            for dow, slot in sorted(weekly_set)
        ]
        return schedules, date_schedules, meta

    async def _fetch_doctor_schedule_both_months(
        self, client: httpx.AsyncClient, dr_idx: str,
    ) -> tuple[list[dict], list[dict], dict]:
        """이번 달 + 다음 달 스케줄 수집"""
        url_cur = f"{DOCTOR_URL}?pCode=doctor&idx={dr_idx}"
        url_next = f"{DOCTOR_URL}?pCode=doctor&idx={dr_idx}&next=Y"

        try:
            resp_cur = await client.get(url_cur)
            resp_cur.raise_for_status()
            html_cur = resp_cur.text
        except Exception as e:
            logger.warning(f"[UUH] 의사 상세(이번달) 로드 실패 idx={dr_idx}: {e}")
            return [], [], {"name": "", "department": "", "position": "",
                            "specialty": "", "photo_url": "", "notes": ""}

        sched_cur, dates_cur, meta = self._parse_schedule_page(html_cur)

        # 다음 달
        dates_next: list[dict] = []
        sched_next: list[dict] = []
        try:
            resp_next = await client.get(url_next)
            resp_next.raise_for_status()
            sched_next, dates_next, _ = self._parse_schedule_page(resp_next.text)
        except Exception as e:
            logger.debug(f"[UUH] 의사 상세(다음달) 로드 실패 idx={dr_idx}: {e}")

        # 주간 패턴 합치기
        weekly_set: set[tuple[int, str]] = set()
        for s in sched_cur + sched_next:
            weekly_set.add((s["day_of_week"], s["time_slot"]))
        schedules = [
            {
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": TIME_RANGES[slot][0],
                "end_time": TIME_RANGES[slot][1],
                "location": "",
            }
            for dow, slot in sorted(weekly_set)
        ]

        # 날짜별 병합 + 중복 제거
        all_dates = dates_cur + dates_next
        seen = set()
        uniq = []
        for d in all_dates:
            k = (d["schedule_date"], d["time_slot"])
            if k in seen:
                continue
            seen.add(k)
            uniq.append(d)
        uniq.sort(key=lambda d: (d["schedule_date"], d["time_slot"]))
        return schedules, uniq, meta

    # ─── 전체 ──────────────────────────────────────────────
    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            if not depts:
                logger.error("[UUH] 진료과 0개 — 크롤링 중단")
                self._cached_data = []
                return []

            sem_dept = asyncio.Semaphore(6)

            async def _run_dept(d):
                async with sem_dept:
                    return await self._fetch_dept_doctors(client, d["code"], d["name"])

            dept_results = await asyncio.gather(
                *[_run_dept(d) for d in depts],
                return_exceptions=True,
            )

            seen: dict[str, dict] = {}
            for r in dept_results:
                if isinstance(r, Exception):
                    continue
                for doc in r:
                    if doc["dr_idx"] in seen:
                        continue
                    seen[doc["dr_idx"]] = doc

            # 각 의사의 월간 스케줄 조회 (병렬, 세마포어 제한)
            sem_dr = asyncio.Semaphore(8)

            async def _fill(doc: dict):
                async with sem_dr:
                    sch, date_sch, meta = await self._fetch_doctor_schedule_both_months(
                        client, doc["dr_idx"],
                    )
                doc["schedules"] = sch
                doc["date_schedules"] = date_sch
                # 메타가 더 풍부하면 보완
                if meta.get("specialty") and not doc.get("specialty"):
                    doc["specialty"] = meta["specialty"]
                if meta.get("position") and not doc.get("position"):
                    doc["position"] = meta["position"]
                if meta.get("photo_url") and not doc.get("photo_url"):
                    doc["photo_url"] = meta["photo_url"]
                if meta.get("notes"):
                    doc["notes"] = meta["notes"]

            await asyncio.gather(
                *[_fill(d) for d in seen.values()],
                return_exceptions=True,
            )

        out = list(seen.values())
        logger.info(f"[UUH] 총 {len(out)}명 수집")
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
            try:
                sched, date_sched, meta = await self._fetch_doctor_schedule_both_months(
                    client, raw_idx,
                )
            except Exception as e:
                logger.error(f"[UUH] 개별 조회 실패 {staff_id}: {e}")
                return empty

        if not meta.get("name"):
            # 스케줄 페이지에서 이름을 못 뽑았으면 비어있을 수 있음
            return {
                **empty,
                "profile_url": f"{DOCTOR_URL}?pCode=doctor&idx={raw_idx}",
                "schedules": sched,
                "date_schedules": date_sched,
            }

        return {
            "staff_id": staff_id,
            "name": meta.get("name", ""),
            "department": meta.get("department", ""),
            "position": meta.get("position", ""),
            "specialty": meta.get("specialty", ""),
            "profile_url": f"{DOCTOR_URL}?pCode=doctor&idx={raw_idx}",
            "notes": meta.get("notes", ""),
            "schedules": sched,
            "date_schedules": date_sched,
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
