"""동아대학교병원(Dong-A University Medical Center) 크롤러

병원 공식명: 동아대학교병원
홈페이지: https://damc.or.kr
기술: 정적 HTML (httpx + BeautifulSoup)
인코딩: UTF-8

구조 (3단계 요약):
  1) 진료과 목록 페이지: /02/02_2017.php
     - `select#depart_select > option` 에서 dept_code(6자리) + dept_name 추출
  2) 진료과별 의사 목록 페이지: /02/02_2_2017.php?code={dept_code}&chk=1
     - `div.doc_info` 가 의사 카드
         * 이름: `dt > b`
         * 진료과: `dt > span`
         * 전문분야: `dd > div`
         * 사진: `div.simg img[src]`
         * 상세(layerPOP): `/mypage/inc.medical.view.php?idx={idx}&aomp_cd={aomp_cd}`
           → idx, aomp_cd 추출 + layerPOP 두 번째 인자 = "{이름} {직책}" → 직책 파싱
         * 주간 진료시간표: `table.layout_doc tbody tr`
             - 10개 td (월오전/월오후/화오전/...금오후) 안에 `<span>○</span>` 마크가 있으면 진료
             - `tr[title]` 에 "YYYY년 MM월 DD일부터 YYYY년 MM월 DD일까지 출장 입니다." 같은 부재 기간 명시 가능
  3) 개별 의사 상세 팝업: /mypage/inc.medical.view.php?idx={idx}&aomp_cd={aomp_cd}
     - 소속/진료분야/학력/경력/현직/학회활동 테이블 (th+td 구조)

날짜별 스케줄: damc.or.kr 가 월별 달력을 제공하지 않음 → 주간 패턴을 오늘~3개월 앞으로 투영해서
`date_schedules` 에 채운다. `tr[title]` 의 부재 기간 범위 내 날짜는 제외.

external_id: `DAMC-{idx}` (aomp_cd 는 내부 dict 에 보관하여 상세 재조회 시 사용)
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

BASE_URL = "https://damc.or.kr"
DEPT_LIST_URL = f"{BASE_URL}/02/02_2017.php"
DEPT_DOCTORS_URL = f"{BASE_URL}/02/02_2_2017.php"
DOCTOR_DETAIL_URL = f"{BASE_URL}/mypage/inc.medical.view.php"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# layerPOP 두 번째 인자 패턴: 'idx=XXXXX&aomp_cd=YYYYY&detl_aomp_cd=','이름 직책'
LAYERPOP_RE = re.compile(
    r"layerPOP\(\s*'/mypage/inc\.medical\.view\.php\?"
    r"idx=([^&']+)&aomp_cd=([^&']*)&detl_aomp_cd=([^']*)'"
    r"\s*,\s*'([^']*)'",
)

# 부재 기간: "2026년 04월 24일부터 2026년 04월 26일까지 출장 입니다."
ABSENCE_RE = re.compile(
    r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*부터\s*"
    r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*까지"
)


class DamcCrawler:
    """동아대학교병원 크롤러 — 정적 HTML (UTF-8)"""

    def __init__(self):
        self.hospital_code = "DAMC"
        self.hospital_name = "동아대학교병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/",
        }
        self._cached_data: Optional[list[dict]] = None

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

    # ─── 진료과 ────────────────────────────────────────────────
    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        """`/02/02_2017.php` 의 select 에서 진료과 리스트 추출"""
        try:
            resp = await client.get(DEPT_LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[DAMC] 진료과 리스트 로드 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        sel = soup.select_one("select#depart_select")
        if not sel:
            logger.error("[DAMC] depart_select 을 찾지 못함")
            return []

        depts: list[dict] = []
        for opt in sel.find_all("option"):
            val = (opt.get("value") or "").strip()
            name = self._clean(opt.get_text(" ", strip=True))
            if not val or not name:
                continue
            # value 예: "02_1_2017.php?code=623500&chk=1"
            m = re.search(r"code=(\d+)", val)
            if not m:
                continue
            depts.append({"code": m.group(1), "name": name})
        return depts

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
        return [{"code": d["code"], "name": d["name"]} for d in depts]

    # ─── 의사 카드 파싱 ────────────────────────────────────────
    def _parse_schedule_table(self, row_tr) -> tuple[list[dict], str]:
        """table.layout_doc 의 1개 tr → (schedules, absence_title)

        10개 td 가 월오전/월오후/화오전/...금오후 순으로 배치됨.
        첫 td 는 의사 이름(+아이콘).
        마지막 td 들은 전문분야/예약.
        → 1..10 번 td 만 슬롯으로 해석.
        """
        schedules: list[dict] = []
        absence_title = (row_tr.get("title") or "").strip()
        # 사이트 HTML 이 첫 td 를 닫지 않는 경우가 많아(<td>이름<br/> 뒤에 td 가 이어짐)
        # BeautifulSoup 이 td 를 중첩시켜 recursive=False 로는 1개만 잡힘.
        # → 전체 td 를 수집하되, 순서상 [이름, 월오전, 월오후, ..., 금오후, 전문분야, (예약)] 구조.
        tds_all = row_tr.find_all("td")
        if len(tds_all) < 11:
            return schedules, absence_title

        slot_tds = tds_all[1:11]  # 10개 (월오전~금오후)
        for idx, td in enumerate(slot_tds):
            # `<span>○</span>` 또는 `<span>●</span>` 같은 마크가 있어야 진료
            span = td.find("span")
            # 하위 td 가 중첩될 수 있으므로, 이 td 직속 텍스트만 뽑는다(자식 span 포함)
            txt_parts: list[str] = []
            for child in td.children:
                if getattr(child, "name", None) == "td":
                    # 중첩된 다음 셀은 건너뛰어야 함
                    break
                if isinstance(child, str):
                    txt_parts.append(child)
                else:
                    txt_parts.append(child.get_text(" ", strip=True))
            txt = self._clean(" ".join(txt_parts))
            if not span and not txt:
                continue
            # 외래 아님으로 판정할 키워드
            exclude_kw = ("수술", "내시경", "시술", "초음파", "조영",
                          "CT", "MRI", "PET", "회진", "실험", "연구",
                          "검사")
            inactive_kw = ("휴진", "휴무", "공휴일", "부재", "출장", "학회")
            if any(k in txt for k in inactive_kw):
                continue
            if any(k in txt for k in exclude_kw):
                continue

            # 마크 / 진료 키워드 / 시간 패턴 중 하나가 있어야 포함
            clinic_marks = {"●", "○", "◎", "◯", "★", "ㅇ", "O", "V", "v", "◆", "■", "✓"}
            clinic_keywords = ("진료", "외래", "예약", "격주", "순환",
                               "왕진", "클리닉", "상담", "투석", "검진")
            has_mark = any(m in txt for m in clinic_marks)
            has_kw = any(k in txt for k in clinic_keywords)
            has_time = bool(re.search(r"\d{1,2}[:시]\d{0,2}", txt))
            if not (has_mark or has_kw or has_time):
                continue

            dow = idx // 2  # 0=월..4=금
            slot = "morning" if (idx % 2 == 0) else "afternoon"
            start, end = TIME_RANGES[slot]
            schedules.append({
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": start,
                "end_time": end,
                "location": "",
            })
        return schedules, absence_title

    def _parse_doctor_card(self, box, dept_code: str, dept_name: str) -> Optional[dict]:
        """`div.doc_info` → dict"""
        # 이름 + 진료과 (dl > dt > b, span)
        dt = box.select_one("dl dt")
        if not dt:
            return None
        b = dt.find("b")
        name = self._clean(b.get_text(" ", strip=True)) if b else ""
        if not name:
            return None
        span = dt.find("span")
        dept_in_card = self._clean(span.get_text(" ", strip=True)) if span else dept_name

        # 전문분야
        specialty = ""
        dd = box.select_one("dl dd div")
        if dd:
            specialty = self._clean(dd.get_text(" ", strip=True))

        # 사진
        photo_url = ""
        img = box.select_one("div.simg img")
        if img:
            photo_url = self._abs_url((img.get("src") or "").strip())

        # layerPOP 에서 idx, aomp_cd, 직책
        idx_val = ""
        aomp_cd = ""
        position = ""
        pop_a = box.select_one("div.docDetailBtn a")
        if pop_a:
            href = pop_a.get("href") or ""
            m = LAYERPOP_RE.search(href)
            if m:
                idx_val = m.group(1)
                aomp_cd = m.group(2)
                pop_title = m.group(4)  # 예: "박주성 교수"
                # 이름 뒤 공백 이후 토큰 = 직책
                if pop_title.startswith(name):
                    position = self._clean(pop_title[len(name):])
        if not idx_val:
            return None

        # 상세 팝업 URL (profile_url)
        aomp_q = aomp_cd or dept_code
        profile_url = (f"{DOCTOR_DETAIL_URL}?idx={idx_val}"
                       f"&aomp_cd={aomp_q}&detl_aomp_cd=")

        # 스케줄
        schedules: list[dict] = []
        absence_title = ""
        tbl = box.select_one("table.layout_doc")
        if tbl:
            tbody = tbl.find("tbody")
            if tbody:
                tr = tbody.find("tr")
                if tr:
                    schedules, absence_title = self._parse_schedule_table(tr)

        # notes 에 부재 안내 기록
        notes = absence_title.strip()

        ext_id = f"DAMC-{idx_val}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "idx": idx_val,
            "aomp_cd": aomp_cd,
            "dept_code": dept_code,
            "name": name,
            "department": dept_in_card or dept_name,
            "position": position,
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": notes,
            "schedules": schedules,
            "absence_title": absence_title,
            "date_schedules": [],
        }

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        url = f"{DEPT_DOCTORS_URL}?code={dept_code}&chk=1"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[DAMC] dept {dept_code}({dept_name}) 로드 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        out: list[dict] = []
        for box in soup.select("div.doc_info"):
            try:
                d = self._parse_doctor_card(box, dept_code, dept_name)
            except Exception as e:
                logger.warning(f"[DAMC] 카드 파싱 실패 ({dept_name}): {e}")
                continue
            if d:
                out.append(d)
        return out

    # ─── 개별 상세 팝업 ────────────────────────────────────────
    async def _fetch_detail(
        self, client: httpx.AsyncClient, idx_val: str, aomp_cd: str
    ) -> dict:
        """개별 의사 상세 팝업 → {name, department, position, specialty, notes, profile_url, photo_url}"""
        url = f"{DOCTOR_DETAIL_URL}?idx={idx_val}&aomp_cd={aomp_cd}&detl_aomp_cd="
        empty = {
            "name": "", "department": "", "position": "",
            "specialty": "", "notes": "",
            "profile_url": url, "photo_url": "",
        }
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[DAMC] 상세 로드 실패 idx={idx_val}: {e}")
            return empty

        soup = BeautifulSoup(resp.text, "html.parser")
        docDetail = soup.select_one("div.docDetail") or soup
        # 이름: docLeft 에서 b/span 없음, 이미지 alt 가 이름
        name = ""
        img = docDetail.select_one("div.simg img")
        photo_url = ""
        if img:
            name = (img.get("alt") or "").strip()
            photo_url = self._abs_url((img.get("src") or "").strip())

        info: dict[str, str] = {}
        tbl = docDetail.select_one("table.write") or soup.select_one("table.write")
        if tbl:
            for tr in tbl.find_all("tr"):
                th = tr.find("th")
                td = tr.find("td")
                if not th or not td:
                    continue
                key = self._clean(th.get_text(" ", strip=True))
                val = self._clean(td.get_text(" ", strip=True))
                if key and val:
                    info[key] = val

        department = ""
        position = ""
        # 현직: "동아대학교병원 가정의학과 교수" → 진료과 + 직책 동시 파싱
        if "현직" in info:
            current = info["현직"].split("\n")[0]
            toks = [t for t in current.split() if t]
            if toks:
                position = toks[-1]
                # 병원명 제외, 직책 제외한 가운데 토큰들을 진료과로 결합
                # "동아대학교병원 가정의학과 교수" → "가정의학과"
                if len(toks) >= 3:
                    dept_toks = toks[1:-1]
                    department = " ".join(dept_toks)
                elif len(toks) == 2:
                    department = toks[0]
        # 현직이 없으면 소속 폴백
        if not department and "소속" in info:
            department = re.sub(r"\s*\(.*?\)\s*$", "", info["소속"]).strip() or info["소속"]

        specialty = info.get("진료분야", "")

        # notes: 경력 + 학회활동 요약
        notes_parts: list[str] = []
        for k in ("경력", "학회활동 및 사회활동", "학력"):
            if k in info and info[k]:
                notes_parts.append(f"[{k}]\n{info[k]}")
        notes = "\n\n".join(notes_parts)[:800]

        return {
            "name": name,
            "department": department,
            "position": position,
            "specialty": specialty,
            "notes": notes,
            "profile_url": url,
            "photo_url": photo_url,
        }

    # ─── 주간 → 3개월 날짜 투영 ────────────────────────────────
    @staticmethod
    def _parse_absence_ranges(absence_title: str) -> list[tuple[date, date]]:
        """tr[title] 에서 부재 기간 (시작, 종료) 들 추출"""
        if not absence_title:
            return []
        ranges: list[tuple[date, date]] = []
        for m in ABSENCE_RE.finditer(absence_title):
            try:
                y1, mo1, d1, y2, mo2, d2 = map(int, m.groups())
                ranges.append((date(y1, mo1, d1), date(y2, mo2, d2)))
            except ValueError:
                continue
        return ranges

    def _project_weekly_to_dates(
        self, schedules: list[dict], absence_title: str
    ) -> list[dict]:
        """주간 패턴을 오늘부터 3개월치 실제 날짜로 투영. 부재 기간은 제외."""
        if not schedules:
            return []
        today = date.today()
        end = today + timedelta(days=93)  # 약 3개월
        absence_ranges = self._parse_absence_ranges(absence_title)

        by_dow: dict[int, list[dict]] = {}
        for s in schedules:
            by_dow.setdefault(int(s["day_of_week"]), []).append(s)

        out: list[dict] = []
        cur = today
        while cur <= end:
            dow = cur.weekday()
            if dow in by_dow:
                in_absence = any(a <= cur <= b for (a, b) in absence_ranges)
                if not in_absence:
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

    # ─── 전체 ──────────────────────────────────────────────────
    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            if not depts:
                logger.error("[DAMC] 진료과가 0개 — 크롤링 중단")
                self._cached_data = []
                return []

            # 진료과별 의사 병렬 수집 (부하 방지로 세마포어)
            sem = asyncio.Semaphore(6)

            async def _run_dept(d: dict):
                async with sem:
                    return await self._fetch_dept_doctors(client, d["code"], d["name"])

            dept_results = await asyncio.gather(
                *[_run_dept(d) for d in depts],
                return_exceptions=True,
            )

            # 중복 제거: 같은 idx 는 첫 진료과만 유지
            seen: dict[str, dict] = {}
            for r in dept_results:
                if isinstance(r, Exception):
                    continue
                for doc in r:
                    if doc["idx"] in seen:
                        continue
                    seen[doc["idx"]] = doc

        # 날짜 투영 (네트워크 불필요)
        for doc in seen.values():
            doc["date_schedules"] = self._project_weekly_to_dates(
                doc["schedules"], doc.get("absence_title", ""),
            )

        out = list(seen.values())
        logger.info(f"[DAMC] 총 {len(out)}명 수집")
        self._cached_data = out
        return out

    # ─── 공개 인터페이스 ──────────────────────────────────────
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

        # 동일 인스턴스 내 캐시 사용 (crawl_doctors 흐름에서)
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
        if not raw_idx:
            return empty

        async with self._make_client() as client:
            # 1) 상세 팝업으로 기본 정보 + aomp_cd 는 알 수 없어 빈 값 fallback
            try:
                detail = await self._fetch_detail(client, raw_idx, "")
            except Exception as e:
                logger.error(f"[DAMC] 상세 조회 실패 {staff_id}: {e}")
                return empty
            department = detail.get("department", "")
            if not department:
                # 스케줄 테이블을 찾을 방법이 없음 → 빈 스케줄로 반환
                return {
                    "staff_id": staff_id,
                    "name": detail.get("name", ""),
                    "department": "",
                    "position": detail.get("position", ""),
                    "specialty": detail.get("specialty", ""),
                    "profile_url": detail.get("profile_url", ""),
                    "notes": detail.get("notes", ""),
                    "schedules": [],
                    "date_schedules": [],
                }

            # 2) 해당 진료과의 code 를 선택 박스에서 역검색 (1 페이지 로드)
            depts = await self._fetch_dept_list(client)
            dept_code = ""
            for d in depts:
                if d["name"] == department:
                    dept_code = d["code"]
                    break
            if not dept_code:
                logger.warning(f"[DAMC] 진료과 매칭 실패 {department} ({staff_id})")
                return {
                    "staff_id": staff_id,
                    "name": detail.get("name", ""),
                    "department": department,
                    "position": detail.get("position", ""),
                    "specialty": detail.get("specialty", ""),
                    "profile_url": detail.get("profile_url", ""),
                    "notes": detail.get("notes", ""),
                    "schedules": [],
                    "date_schedules": [],
                }

            # 3) 해당 진료과 1개만 로드해 idx 매칭
            dept_docs = await self._fetch_dept_doctors(client, dept_code, department)

        match: Optional[dict] = None
        for doc in dept_docs:
            if doc["idx"] == raw_idx:
                match = doc
                break
        if match is None:
            # 스케줄 못 찾음 — 상세만 반환
            return {
                "staff_id": staff_id,
                "name": detail.get("name", ""),
                "department": department,
                "position": detail.get("position", ""),
                "specialty": detail.get("specialty", ""),
                "profile_url": detail.get("profile_url", ""),
                "notes": detail.get("notes", ""),
                "schedules": [],
                "date_schedules": [],
            }

        date_schedules = self._project_weekly_to_dates(
            match["schedules"], match.get("absence_title", ""),
        )
        # notes: 상세의 경력/학력 우선, 목록의 부재 안내는 덧붙임
        notes_final = detail.get("notes", "") or match.get("notes", "")
        if match.get("absence_title") and match["absence_title"] not in notes_final:
            notes_final = (notes_final + "\n\n" + match["absence_title"]).strip()

        return {
            "staff_id": staff_id,
            "name": detail.get("name") or match.get("name", ""),
            "department": department or match.get("department", ""),
            "position": detail.get("position") or match.get("position", ""),
            "specialty": detail.get("specialty") or match.get("specialty", ""),
            "profile_url": detail.get("profile_url") or match.get("profile_url", ""),
            "notes": notes_final[:800],
            "schedules": match.get("schedules", []),
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
