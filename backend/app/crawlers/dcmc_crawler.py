"""대구가톨릭대학교병원(Daegu Catholic University Medical Center) 크롤러

병원 공식명: 대구가톨릭대학교병원
홈페이지: https://dcmc.co.kr
기술: 정적 HTML (httpx + BeautifulSoup)
인코딩: UTF-8

구조 (3단계):
  1) 진료과 목록 (정적, select#sh_ct_codeno)
     URL: /content/01reserv/01_02.asp
     - option value="C0;C2586;" 형식 → 뒤쪽 C##### 추출 (dept_code)
  2) 진료과별 의료진 목록
     URL: /content/01reserv/01_02.asp?sh_ct_codeno=C0%3B{dept_code}%3B
     - `div.box > div.doctor_info` 카드
         * 이름: `p.name` (span 앞 텍스트)
         * 진료과: `p.name > span`
         * 전문분야: `dl > dd`
         * 사진: `p.photo img[src]`
         * 상세: `a.rev_btn.white` → M_NUM 파라미터 (원내코드)
  3) 의사 개별 상세/시간표
     URL: /content/01reserv/01_0103.asp?M_NUM={M_NUM}&rdate=YYYY-MM-DD
     - `table.doc_table` 내 첫 번째 `tr#tr_schedule` 는 오전, 다음 tr 는 오후
     - 요일 th 는 `월(20)` 형식 — 숫자는 일자
     - `span.iconset.sche1` = 진료, `sche2` = 클리닉 (둘 다 외래로 포함)
     - `rdate` 파라미터로 다른 주를 조회할 수 있음 → 13주 순회해서 3개월치 수집
     - 프로필 직책/진료분야: `dl.position dd`, `dl.part dd`
     - 경력 등: `h3.h3_t` 형제 `ul.list`

external_id: `DCMC-{M_NUM}`
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://dcmc.co.kr"
DEPT_LIST_URL = f"{BASE_URL}/content/01reserv/01_02.asp"
DOCTOR_DETAIL_URL = f"{BASE_URL}/content/01reserv/01_0103.asp"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 셀 텍스트 분류
CLINIC_KEYWORDS = ("진료", "외래", "예약", "격주", "순환", "왕진",
                   "클리닉", "상담", "투석", "검진")
EXCLUDE_KEYWORDS = ("수술", "내시경", "시술", "초음파", "조영",
                    "CT", "MRI", "PET", "회진", "실험", "연구", "검사")
INACTIVE_KEYWORDS = ("휴진", "휴무", "공휴일", "부재", "출장", "학회")

# 진료과 select value → dept_code 패턴
DEPT_VAL_RE = re.compile(r"C0;(C\d+);")
# th "월(20)" 형식
DAY_NUM_RE = re.compile(r"\(\s*(\d{1,2})\s*\)")


class DcmcCrawler:
    """대구가톨릭대학교병원 크롤러 — 정적 HTML (UTF-8)"""

    def __init__(self):
        self.hospital_code = "DCMC"
        self.hospital_name = "대구가톨릭대학교병원"
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
        return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()

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
    def _mondays(start: date, weeks: int) -> list[date]:
        """start 가 속한 주의 월요일부터 시작하여 weeks 주 각각의 월요일 반환"""
        monday = start - timedelta(days=start.weekday())
        return [monday + timedelta(weeks=i) for i in range(weeks)]

    # ─── 진료과 ────────────────────────────────────────────────
    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        """의료진 검색 페이지의 select 옵션에서 진료과 추출"""
        try:
            resp = await client.get(DEPT_LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[DCMC] 진료과 리스트 로드 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        sel = soup.select_one("select#sh_ct_codeno")
        if not sel:
            logger.error("[DCMC] sh_ct_codeno select 를 찾지 못함")
            return []

        depts: list[dict] = []
        for opt in sel.find_all("option"):
            val = (opt.get("value") or "").strip()
            name = self._clean(opt.get_text(" ", strip=True))
            if not val or not name:
                continue
            m = DEPT_VAL_RE.search(val)
            if not m:
                continue
            depts.append({
                "code": m.group(1),
                "value": val,      # 원래 "C0;C2586;"
                "name": name,
            })
        return depts

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
        return [{"code": d["code"], "name": d["name"]} for d in depts]

    # ─── 의사 카드 파싱 ────────────────────────────────────────
    def _parse_doctor_list_page(
        self, html: str, dept_code: str, dept_name: str
    ) -> list[dict]:
        """진료과별 의료진 목록 페이지 → 의사 리스트"""
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []
        # 각 의사 카드 = div.box > div.doctor_info (medical_intro 안쪽)
        for box in soup.select("div.medical_intro div.box"):
            info = box.select_one("div.doctor_info")
            if not info:
                continue
            # 이름 + 진료과
            name_el = info.select_one("p.name")
            if not name_el:
                continue
            span = name_el.find("span")
            dept_in_card = self._clean(span.get_text(" ", strip=True)) if span else dept_name
            name_text = name_el.get_text(" ", strip=True)
            if span:
                name_text = name_text.replace(span.get_text(" ", strip=True), "")
            name = self._clean(name_text)
            if not name:
                continue

            # 전문분야
            specialty = ""
            dd = info.select_one("dl dd")
            if dd:
                specialty = self._clean(dd.get_text(" ", strip=True))
                specialty = specialty.rstrip("&").rstrip().rstrip(",")

            # 사진
            photo_url = ""
            img = info.select_one("p.photo img")
            if img:
                photo_url = self._abs_url((img.get("src") or "").strip())

            # 직책 (목록에선 비어있음, 상세에서 채움)
            traning = info.select_one("p.traning")
            position = self._clean(traning.get_text(" ", strip=True)) if traning else ""

            # 상세 버튼에서 M_NUM 추출
            m_num = ""
            a = box.select_one("a.rev_btn.white")
            if a and a.get("href"):
                href = a["href"]
                try:
                    q = parse_qs(urlparse(href).query)
                    if "M_NUM" in q and q["M_NUM"]:
                        m_num = q["M_NUM"][0]
                except Exception:
                    pass
            if not m_num:
                # 폴백: 정규식
                if a and a.get("href"):
                    m = re.search(r"M_NUM=(\d+)", a["href"])
                    if m:
                        m_num = m.group(1)
            if not m_num:
                continue

            ext_id = f"DCMC-{m_num}"
            profile_url = f"{DOCTOR_DETAIL_URL}?M_NUM={m_num}"
            out.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "m_num": m_num,
                "dept_code": dept_code,
                "name": name,
                "department": dept_in_card or dept_name,
                "position": position,
                "specialty": specialty,
                "profile_url": profile_url,
                "photo_url": photo_url,
                "notes": "",
                "schedules": [],
                "date_schedules": [],
            })
        return out

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_value: str,
        dept_code: str, dept_name: str,
    ) -> list[dict]:
        url = DEPT_LIST_URL
        params = {"sh_ct_codeno": dept_value, "sh_keyword": ""}
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[DCMC] dept {dept_code}({dept_name}) 로드 실패: {e}")
            return []
        return self._parse_doctor_list_page(resp.text, dept_code, dept_name)

    # ─── 의사 상세/시간표 ──────────────────────────────────────
    def _classify_cell(self, txt: str) -> bool:
        """셀 텍스트 → 외래 진료 여부"""
        if not txt:
            return False
        for kw in INACTIVE_KEYWORDS:
            if kw in txt:
                return False
        for kw in EXCLUDE_KEYWORDS:
            if kw in txt:
                return False
        for kw in CLINIC_KEYWORDS:
            if kw in txt:
                return True
        return False

    def _parse_week_table(
        self, soup: BeautifulSoup, week_monday: date
    ) -> list[dict]:
        """`table.doc_table` 한 주 테이블 → date_schedules (한 주 분량)

        리턴 dict: {schedule_date, time_slot, start_time, end_time, location, status}
        """
        out: list[dict] = []
        tbl = soup.select_one("table.doc_table")
        if not tbl:
            return out
        thead = tbl.find("thead")
        ths = []
        if thead:
            ths = thead.find_all("th")
        # ths: [시간, 월(20), 화(21), ..., 토(25)] — 6개 요일
        if len(ths) < 7:
            return out

        # th 에서 각 요일의 일자 숫자 추출 → 실제 date 로 변환
        day_dates: list[Optional[date]] = []
        for th in ths[1:7]:  # 월..토
            t = th.get_text(" ", strip=True)
            m = DAY_NUM_RE.search(t)
            if not m:
                day_dates.append(None)
                continue
            day = int(m.group(1))
            # 주 월요일 기준으로 offset (0=월..5=토)
            idx = len(day_dates)
            guess = week_monday + timedelta(days=idx)
            # 만약 해당 주의 해당 요일 일자와 다르다면 월 경계를 넘은 것 → 보정
            if guess.day != day:
                # 다음 달로 넘어간 경우 (4월 말 → 5월 초)
                next_candidate = guess
                for _ in range(12):
                    next_candidate += timedelta(days=1)
                    if next_candidate.day == day and next_candidate.weekday() == idx:
                        break
                else:
                    next_candidate = None
                if next_candidate:
                    day_dates.append(next_candidate)
                else:
                    # 추가 시도: 현재 월요일 기준 같은 요일 +1주
                    alt = guess + timedelta(weeks=1)
                    day_dates.append(alt if alt.day == day else None)
            else:
                day_dates.append(guess)

        tbody = tbl.find("tbody")
        if not tbody:
            return out

        # tbody 의 실제 tr 들 중 앞 2개만 사용 (오전/오후). 주석(<!-- --> 안의 tr 은 파싱 대상 아님)
        trs = tbody.find_all("tr", recursive=False)
        if len(trs) < 2:
            return out

        for slot_idx, tr in enumerate(trs[:2]):
            slot = "morning" if slot_idx == 0 else "afternoon"
            start, end = TIME_RANGES[slot]
            tds = tr.find_all("td", recursive=False)
            # tds[0] = 오전/오후 라벨, [1..6] = 월..토
            if len(tds) < 7:
                continue
            for i, td in enumerate(tds[1:7]):
                the_date = day_dates[i] if i < len(day_dates) else None
                if the_date is None:
                    continue
                # span.iconset 이 있거나 텍스트로 진료/클리닉 등이 있어야 포함
                span = td.find("span", class_="iconset")
                txt = td.get_text(" ", strip=True)
                active = False
                if span:
                    span_cls = span.get("class", [])
                    span_txt = span.get_text(" ", strip=True)
                    # sche1, sche2 = 진료/클리닉/센터진료 → 외래 포함
                    # sche3/기타도 일단 text 로 판정
                    if any(c in ("sche1", "sche2", "sche3") for c in span_cls):
                        active = True
                    else:
                        active = self._classify_cell(span_txt)
                else:
                    active = self._classify_cell(txt)
                if not active:
                    continue
                out.append({
                    "schedule_date": the_date.isoformat(),
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                    "status": "진료",
                })
        return out

    def _parse_doctor_detail(self, html: str) -> dict:
        """의사 상세 페이지(프로필+현재 주 스케줄)에서 메타 추출"""
        soup = BeautifulSoup(html, "html.parser")
        out = {
            "name": "", "department": "", "position": "", "specialty": "",
            "notes": "", "photo_url": "",
        }
        profile = soup.select_one("div.profile")
        if profile:
            team = profile.select_one("p.team")
            if team:
                out["department"] = self._clean(team.get_text(" ", strip=True))
            name_el = profile.select_one("p.name")
            if name_el:
                out["name"] = self._clean(name_el.get_text(" ", strip=True))
            # 직위/직책
            for dl in profile.select("dl"):
                dt = dl.find("dt")
                dd = dl.find("dd")
                if not dt or not dd:
                    continue
                key = self._clean(dt.get_text(" ", strip=True))
                val = self._clean(dd.get_text(" ", strip=True))
                if not val:
                    continue
                if "직위" in key or "직책" in key:
                    out["position"] = val
                elif "진료" in key or "분야" in key:
                    out["specialty"] = val

        # 배경 이미지 추출 (data-img-1 or background-image)
        sec = soup.select_one("#section0")
        if sec:
            img1 = sec.get("data-img-1") or ""
            if img1:
                out["photo_url"] = self._abs_url(img1.strip())

        # 경력/학력 — h3.h3_t 뒤의 ul.list
        notes_parts: list[str] = []
        for h3 in soup.select("h3.h3_t"):
            title = self._clean(h3.get_text(" ", strip=True))
            if title in ("학력사항", "경력사항"):
                ul = h3.find_next_sibling("ul", class_="list")
                if ul:
                    items = [self._clean(li.get_text(" ", strip=True))
                             for li in ul.find_all("li")]
                    items = [x for x in items if x]
                    if items:
                        notes_parts.append(f"[{title}]\n" + "\n".join(items))
        out["notes"] = "\n\n".join(notes_parts)[:800]
        return out

    async def _fetch_doctor_week(
        self, client: httpx.AsyncClient, m_num: str, week_monday: date
    ) -> tuple[dict, list[dict]]:
        """한 주 분량 상세 페이지 → (meta, date_schedules)"""
        url = DOCTOR_DETAIL_URL
        params = {"M_NUM": m_num, "rdate": week_monday.isoformat()}
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[DCMC] 의사 주간 로드 실패 M_NUM={m_num} {week_monday}: {e}")
            return {}, []
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        meta = self._parse_doctor_detail(html)
        ds = self._parse_week_table(soup, week_monday)
        return meta, ds

    async def _fetch_doctor_full(
        self, client: httpx.AsyncClient, doc: dict, weeks: int = 13,
        sem: Optional[asyncio.Semaphore] = None,
    ) -> None:
        """doc 의 schedules/date_schedules/메타 채우기 (in-place)"""
        today = date.today()
        mondays = self._mondays(today, weeks)

        async def _one(md: date):
            if sem is not None:
                async with sem:
                    return await self._fetch_doctor_week(client, doc["m_num"], md)
            return await self._fetch_doctor_week(client, doc["m_num"], md)

        results = await asyncio.gather(
            *[_one(md) for md in mondays], return_exceptions=True,
        )

        meta_final: dict = {}
        all_dates: list[dict] = []
        for r in results:
            if isinstance(r, Exception):
                continue
            meta, ds = r
            if not meta_final and meta:
                meta_final = meta
            all_dates.extend(ds)

        # 과거 스케줄은 제외 + 중복 제거
        today_iso = today.isoformat()
        seen: set[tuple[str, str]] = set()
        uniq: list[dict] = []
        for d in all_dates:
            if d["schedule_date"] < today_iso:
                continue
            k = (d["schedule_date"], d["time_slot"])
            if k in seen:
                continue
            seen.add(k)
            uniq.append(d)
        uniq.sort(key=lambda d: (d["schedule_date"], d["time_slot"]))
        doc["date_schedules"] = uniq

        # 주간 요약: 요일+slot 고유 집합
        weekly: set[tuple[int, str]] = set()
        for d in uniq:
            try:
                dt = date.fromisoformat(d["schedule_date"])
            except ValueError:
                continue
            weekly.add((dt.weekday(), d["time_slot"]))
        doc["schedules"] = [
            {
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": TIME_RANGES[slot][0],
                "end_time": TIME_RANGES[slot][1],
                "location": "",
            }
            for dow, slot in sorted(weekly)
        ]

        # 메타 업데이트 (상세에서 더 정확한 정보)
        if meta_final:
            if meta_final.get("position"):
                doc["position"] = meta_final["position"]
            if meta_final.get("specialty"):
                doc["specialty"] = meta_final["specialty"]
            if meta_final.get("notes"):
                doc["notes"] = meta_final["notes"]
            if meta_final.get("department") and not doc.get("department"):
                doc["department"] = meta_final["department"]
            if meta_final.get("photo_url") and not doc.get("photo_url"):
                doc["photo_url"] = meta_final["photo_url"]

    # ─── 전체 ──────────────────────────────────────────────────
    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            if not depts:
                logger.error("[DCMC] 진료과가 0개 — 중단")
                self._cached_data = []
                return []

            # 진료과별 의사 목록 병렬 (세마포어로 제한)
            dept_sem = asyncio.Semaphore(6)

            async def _dept(d: dict):
                async with dept_sem:
                    return await self._fetch_dept_doctors(
                        client, d["value"], d["code"], d["name"],
                    )

            dept_results = await asyncio.gather(
                *[_dept(d) for d in depts], return_exceptions=True,
            )
            # M_NUM 기준 중복 제거 (같은 의사가 여러 진료과에 속할 수 있음)
            seen: dict[str, dict] = {}
            for r in dept_results:
                if isinstance(r, Exception):
                    continue
                for doc in r:
                    if doc["m_num"] not in seen:
                        seen[doc["m_num"]] = doc

            uniq = list(seen.values())
            logger.info(f"[DCMC] 의사 목록 {len(uniq)}명, 스케줄 수집 시작")

            # 의사별 13주 시간표 병렬 — 서버 부하를 고려해 동시 요청 제한
            sched_sem = asyncio.Semaphore(8)
            await asyncio.gather(
                *[self._fetch_doctor_full(client, doc, weeks=13, sem=sched_sem)
                  for doc in uniq],
                return_exceptions=True,
            )

        logger.info(f"[DCMC] 총 {len(uniq)}명 수집 완료")
        self._cached_data = uniq
        return uniq

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

        # 동일 인스턴스 캐시 재사용
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
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not raw.isdigit():
            return empty

        doc = {
            "staff_id": staff_id,
            "external_id": staff_id,
            "m_num": raw,
            "dept_code": "",
            "name": "",
            "department": "",
            "position": "",
            "specialty": "",
            "profile_url": f"{DOCTOR_DETAIL_URL}?M_NUM={raw}",
            "photo_url": "",
            "notes": "",
            "schedules": [],
            "date_schedules": [],
        }

        sched_sem = asyncio.Semaphore(8)
        async with self._make_client() as client:
            try:
                await self._fetch_doctor_full(client, doc, weeks=13, sem=sched_sem)
            except Exception as e:
                logger.error(f"[DCMC] 개별 조회 실패 {staff_id}: {e}")
                return empty

        return {
            "staff_id": staff_id,
            "name": doc.get("name", ""),
            "department": doc.get("department", ""),
            "position": doc.get("position", ""),
            "specialty": doc.get("specialty", ""),
            "profile_url": doc.get("profile_url", ""),
            "notes": doc.get("notes", ""),
            "schedules": doc.get("schedules", []),
            "date_schedules": doc.get("date_schedules", []),
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
