"""경북대학교병원(KNUH) / 칠곡경북대학교병원(KNUHCG) 크롤러

본원: https://www.knuh.kr (경북대학교병원, 대구)
칠곡분원: https://www.knuch.kr:442 (칠곡경북대학교병원, 대구 북구)

두 사이트는 같은 경북대학교병원 법인 산하의 독립 웹사이트로, 페이지 구조가 거의 동일하다.
정적 HTML + 정적 ASP(IIS). 인코딩: UTF-8.

구조 (공통 3단계):
  1) 진료과 목록: BASE/{DEPT_LIST_PATH} — `.doctor_list a[class^="icon"]`, `.depart_list a`
     에서 `ct_idx` + 진료과명 추출.
  2) 진료과 상세: BASE/{DEPT_DETAIL_PATH}?ct_idx={N}
     - 의사 카드: `div.doctor_box dl`
         * 이름: `.name_box p.name`
         * 상세링크: `.gobtn a` (m_num 파라미터)
         * 진료과/진료분야: `ul.section`
         * 진료시간표: `table.doctor_ta` — 2개 tbody tr (오전/오후)
             - 각 `<td>` 안 `<img src>` 로 진료 여부/지점 판정:
                 * 본원: lst_cont01 (knuh.kr) / dot_place01 (knuch.kr) → 경북대학교병원(대구 본원)
                 * 칠곡: lst_cont02 (knuh.kr) / dot_place02 (knuch.kr) → 칠곡경북대학교병원
             - 텍스트/마크(◎,○ 등)도 같은 셀에 올 수 있으므로 `is_clinic_cell` 로 보조 판정
  3) 개별 상세: BASE/{DOCTOR_DETAIL_PATH}?m_num={M}&ct_idx={N}
     - 이름/진료과/전문분야: `.info` 블록 (`.info_name span`, `.info_name` 텍스트, `.treat`)
     - 경력/학력: `.results` 블록

branch 분리:
- KnuhCrawler: knuh.kr 사이트만 크롤, 본원 아이콘이 있는 슬롯만 schedules/date_schedules 에 포함.
  본원 진료가 한 번도 없는 의사는 제외.
- KnuhcgCrawler: knuch.kr 사이트만 크롤, 칠곡 아이콘이 있는 슬롯만 포함.

external_id: KNUH-{m_num}-{ct_idx} / KNUHCG-{m_num}-{ct_idx}
  - ct_idx 를 함께 실어야 개별 조회 시 해당 교수의 진료과 페이지만 직접 요청할 수 있다
    (상세 페이지는 m_num 만으로 기본정보가 나오지만, 진료시간표는 진료과 페이지에만 있고
     ct_idx 가 없으면 서버가 기본값(소화기내과) 으로 응답함).
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from bs4 import BeautifulSoup

try:
    from app.crawlers._schedule_rules import is_clinic_cell
except Exception:  # 유틸 부재시 폴백
    def is_clinic_cell(text: str) -> bool:
        if not text:
            return False
        t = text.strip()
        for kw in ("휴진", "휴무", "공휴일", "부재", "출장", "학회"):
            if kw in t:
                return False
        for kw in ("수술", "내시경", "시술", "초음파", "조영",
                   "CT", "MRI", "PET", "회진", "실험", "연구", "검사"):
            if kw in t:
                return False
        for kw in ("진료", "외래", "예약", "격주", "순환",
                   "왕진", "클리닉", "상담", "투석", "검진"):
            if kw in t:
                return True
        for m in ("●", "○", "◎", "◯", "★", "ㅇ", "O", "V", "v", "◆", "■", "✓"):
            if m in t:
                return True
        if re.search(r"\d{1,2}[:시]\d{0,2}", t):
            return True
        return False


logger = logging.getLogger(__name__)

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 본원 (경북대학교병원) - knuh.kr
KNUH_BASE = "https://www.knuh.kr"
KNUH_DEPT_LIST = f"{KNUH_BASE}/content/01treatment/08_01.asp"
KNUH_DEPT_DETAIL = f"{KNUH_BASE}/content/01treatment/08_0102.asp"  # ?ct_idx=
KNUH_DOCTOR_DETAIL = f"{KNUH_BASE}/content/01treatment/08_doctor01.asp"  # ?m_num=&ct_idx=

# 칠곡 (칠곡경북대학교병원) - knuch.kr:442
KNUHCG_BASE = "https://www.knuch.kr:442"
KNUHCG_DEPT_LIST = f"{KNUHCG_BASE}/content/02depart/01_01.asp"
KNUHCG_DEPT_DETAIL = f"{KNUHCG_BASE}/content/02depart/01_0102.asp"  # ?ct_idx=
KNUHCG_DOCTOR_DETAIL = f"{KNUHCG_BASE}/content/02depart/detail_area01.asp"  # ?m_num=&ct_idx=

# 아이콘 src 패턴 → "branch" 분류
# 본원 사이트(knuh.kr): lst_cont01(본원), lst_cont02(칠곡)
# 칠곡 사이트(knuch.kr): dot_place01(본원), dot_place02(칠곡)
HEADQUARTERS_MARKERS = ("lst_cont01", "dot_place01")  # 경북대학교병원 본원
CHILGOK_MARKERS = ("lst_cont02", "dot_place02")       # 칠곡경북대학교병원

CT_IDX_RE = re.compile(r"ct_idx=(\d+)")
M_NUM_RE = re.compile(r"m_num=(\d+)")


class _KnuhBase:
    """두 병원 공용 베이스 클래스 — 사이트별 URL 만 다름."""

    # subclass override
    hospital_code: str = ""
    hospital_name: str = ""
    base_url: str = ""
    dept_list_url: str = ""
    dept_detail_url: str = ""
    doctor_detail_url: str = ""
    branch_self: str = ""  # "headquarters" | "chilgok"

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{self.base_url}/",
        }
        self._cached_data: Optional[list[dict]] = None

    # ─── httpx ─────────────────────────────────────────────────
    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    # ─── 공통 유틸 ─────────────────────────────────────────────
    @staticmethod
    def _clean(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "")).strip()

    def _abs_url(self, src: str) -> str:
        if not src:
            return ""
        if src.startswith("http"):
            return src
        if src.startswith("//"):
            return "https:" + src
        return f"{self.base_url}/{src.lstrip('/')}"

    @staticmethod
    def _cell_branch(td) -> Optional[str]:
        """셀 안의 <img> 로 진료 지점 판정. 반환: 'headquarters'|'chilgok'|None"""
        if td is None:
            return None
        for img in td.find_all("img"):
            src = (img.get("src") or "").lower()
            alt = (img.get("alt") or "")
            for m in HEADQUARTERS_MARKERS:
                if m in src:
                    return "headquarters"
            for m in CHILGOK_MARKERS:
                if m in src:
                    return "chilgok"
            # 폴백: alt 텍스트
            if "칠곡" in alt:
                return "chilgok"
            if "본원" in alt or ("경북대학교병원" in alt and "칠곡" not in alt):
                return "headquarters"
        return None

    # ─── 진료과 목록 ───────────────────────────────────────────
    async def _fetch_dept_list(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            resp = await client.get(self.dept_list_url)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[{self.hospital_code}] 진료과 목록 로드 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        depts: dict[str, str] = {}  # ct_idx → name (중복 제거)
        # 셀렉터가 사이트마다 조금 다르지만, 공통으로 "ct_idx=<digits>" 를 가진 <a> 들을 수집
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = CT_IDX_RE.search(href)
            if not m:
                continue
            ct_idx = m.group(1)
            name = self._clean(a.get_text(" ", strip=True))
            if not name:
                continue
            # 중복 ct_idx 는 먼저 발견된 이름 유지 (보통 첫 것이 "진료과" 쪽)
            if ct_idx not in depts:
                depts[ct_idx] = name
        return [{"code": k, "name": v} for k, v in depts.items()]

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            return await self._fetch_dept_list(client)

    # ─── 스케줄 테이블 ─────────────────────────────────────────
    def _parse_schedule_table(self, tbl) -> list[dict]:
        """table.doctor_ta → [{day_of_week, time_slot, start_time, end_time, location, _branch}, ...]
        _branch 는 'headquarters'|'chilgok' (그 후 branch_self 와 매칭되는 것만 사용).
        """
        if tbl is None:
            return []
        tbody = tbl.find("tbody")
        if tbody is None:
            return []
        out: list[dict] = []
        trs = tbody.find_all("tr", recursive=False)
        for tr in trs:
            th = tr.find("th")
            row_label = self._clean(th.get_text(" ", strip=True)) if th else ""
            # "오전" or "오후" 로 row slot 판정
            if "오전" in row_label or "am" in row_label.lower():
                slot = "morning"
            elif "오후" in row_label or "pm" in row_label.lower():
                slot = "afternoon"
            else:
                continue
            tds = tr.find_all("td", recursive=False)
            # 월~금 5일 (일부 병원은 토 포함하나 경북대는 평일만)
            for idx, td in enumerate(tds[:7]):
                branch = self._cell_branch(td)
                txt = self._clean(td.get_text(" ", strip=True))
                # 이미지/마크/텍스트 중 하나라도 clinic 으로 판정되면 포함
                if branch is None:
                    if not is_clinic_cell(txt):
                        continue
                    # 텍스트 기반인데 branch 모름 → 소속 사이트를 기본값으로
                    branch = self.branch_self
                else:
                    # 이미지 있음 — 텍스트에 제외 키워드(수술/휴진 등)가 있으면 건너뜀
                    if txt and not is_clinic_cell(txt) and txt not in ("", "\xa0"):
                        # txt 가 있는데 clinic 이 아니면 건너뜀
                        # 단, 공백/nbsp 만 있는 경우는 건너뛰지 않음
                        continue
                dow = idx  # 0=월..4=금 (5=토 가능성 포함)
                if dow > 5:
                    continue
                start, end = TIME_RANGES[slot]
                location = "경북대학교병원" if branch == "headquarters" else "칠곡경북대학교병원"
                out.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": location,
                    "_branch": branch,
                })
        return out

    # ─── 의사 카드 → dict ──────────────────────────────────────
    def _parse_doctor_card(self, dl, ct_idx: str, dept_name: str) -> Optional[dict]:
        """dl (div.doctor_box > dl) → 의사 dict (branch 필터 적용 전)"""
        # 이름
        name_p = dl.select_one(".name_box p.name") or dl.select_one("p.name")
        if not name_p:
            return None
        name = self._clean(name_p.get_text(" ", strip=True))
        if not name:
            return None

        # m_num
        m_num = ""
        for a in dl.find_all("a", href=True):
            mm = M_NUM_RE.search(a["href"])
            if mm:
                m_num = mm.group(1)
                break
        if not m_num:
            return None

        # 사진
        photo_url = ""
        img = dl.select_one("dt.pic img") or dl.select_one(".pic img")
        if img:
            src = (img.get("src") or "").strip()
            if src and "doctor_pic.gif" not in src:
                photo_url = self._abs_url(src)

        # 진료과/진료분야 — <li><strong class="black">진료과 :</strong> 가정의학과</li>
        specialty = ""
        dept_in_card = ""
        section = dl.select_one("ul.section")
        if section:
            for li in section.find_all("li"):
                strong = li.find("strong")
                label = self._clean(strong.get_text(" ", strip=True)) if strong else ""
                # strong 요소를 제거한 뒤 나머지 텍스트만 확인
                if strong is not None:
                    strong.extract()
                rest = self._clean(li.get_text(" ", strip=True))
                # 앞의 콜론/구두점 제거
                rest = re.sub(r"^[\s:：·,\-]+", "", rest)
                if "진료과" in label:
                    dept_in_card = rest
                elif "진료분야" in label or "전문분야" in label:
                    specialty = rest

        # 스케줄 테이블
        tbl = dl.select_one("table.doctor_ta")
        raw_schedules = self._parse_schedule_table(tbl)

        # branch_self 와 일치하는 슬롯만
        branch_schedules = [s for s in raw_schedules if s.get("_branch") == self.branch_self]
        # 공용 스키마에 _branch 제거
        schedules = [{k: v for k, v in s.items() if k != "_branch"}
                     for s in branch_schedules]

        # 프로필 URL
        profile_url = f"{self.doctor_detail_url}?m_num={m_num}&ct_idx={ct_idx}"

        # external_id 에 ct_idx 를 포함: 개별 조회 시 진료과 페이지로 직접 접근해야
        # 시간표를 얻을 수 있음 (상세 페이지는 ct_idx 를 그대로 echo 만 해서 진료과
        # 정보가 쓸모없음). SKILL 규칙상 "고유 키 통일" — 조회에 필요한 모든 파라미터 포함.
        ext_id = f"{self.hospital_code}-{m_num}-{ct_idx}"
        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "m_num": m_num,
            "ct_idx": ct_idx,
            "name": name,
            "department": dept_in_card or dept_name,
            "position": "",
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": "",
            "has_branch_clinic": bool(branch_schedules),
            "schedules": schedules,
            "date_schedules": [],
        }

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, ct_idx: str, dept_name: str,
    ) -> list[dict]:
        url = f"{self.dept_detail_url}?ct_idx={ct_idx}"
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[{self.hospital_code}] dept {ct_idx}({dept_name}) 로드 실패: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        out: list[dict] = []
        for dl in soup.select("div.doctor_box dl"):
            try:
                d = self._parse_doctor_card(dl, ct_idx, dept_name)
            except Exception as e:
                logger.warning(f"[{self.hospital_code}] 카드 파싱 실패 ({dept_name}): {e}")
                continue
            if d:
                out.append(d)
        return out

    # ─── 개별 상세 ─────────────────────────────────────────────
    async def _fetch_doctor_detail(
        self, client: httpx.AsyncClient, m_num: str, ct_idx: str,
    ) -> dict:
        """개별 의사 상세 페이지 → 이름/진료과/전문분야/경력 등"""
        url = f"{self.doctor_detail_url}?m_num={m_num}&ct_idx={ct_idx}"
        empty = {
            "name": "", "department": "", "position": "", "specialty": "",
            "notes": "", "profile_url": url, "photo_url": "",
        }
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[{self.hospital_code}] 상세 로드 실패 m_num={m_num}: {e}")
            return empty

        soup = BeautifulSoup(resp.text, "html.parser")
        info = soup.select_one("div.detail_area div.info") or soup.select_one("div.info")
        name = ""
        department = ""
        if info is not None:
            info_name = info.select_one("p.info_name")
            if info_name:
                span = info_name.find("span")
                if span:
                    department = self._clean(span.get_text(" ", strip=True))
                # span 제거 후 이름만 남김
                txt = info_name.get_text("\n", strip=True)
                # "가정의학과\n송지은" 형태
                lines = [self._clean(x) for x in txt.split("\n") if self._clean(x)]
                if department and lines:
                    for ln in lines:
                        if ln != department:
                            name = ln
                            break
                elif lines:
                    name = lines[-1]

        specialty = ""
        if info is not None:
            treat = info.select_one("p.treat")
            if treat:
                specialty = self._clean(treat.get_text(" ", strip=True))

        photo_url = ""
        img = (info.select_one("p.pic img") if info else None) or soup.select_one("div.detail_area img")
        if img:
            src = (img.get("src") or "").strip()
            if src and "doctor_pic.gif" not in src:
                photo_url = self._abs_url(src)

        # 경력/학력 — .results 블록
        notes = ""
        results = soup.select_one("div.detail_area div.results") or soup.select_one("div.results")
        if results is not None:
            # 내부 텍스트를 라인 단위로 정리
            raw = results.get_text("\n", strip=True)
            # 과도한 빈 줄 제거
            raw = re.sub(r"\n{3,}", "\n\n", raw)
            notes = raw[:800]

        return {
            "name": name,
            "department": department,
            "position": "",
            "specialty": specialty,
            "notes": notes,
            "profile_url": url,
            "photo_url": photo_url,
        }

    # ─── 주간 → 3개월 날짜 투영 ────────────────────────────────
    @staticmethod
    def _project_weekly_to_dates(schedules: list[dict]) -> list[dict]:
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

    # ─── 전체 크롤 ─────────────────────────────────────────────
    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        async with self._make_client() as client:
            depts = await self._fetch_dept_list(client)
            if not depts:
                logger.error(f"[{self.hospital_code}] 진료과 0개 — 크롤링 중단")
                self._cached_data = []
                return []

            sem = asyncio.Semaphore(6)

            async def _run(dept: dict):
                async with sem:
                    return await self._fetch_dept_doctors(client, dept["code"], dept["name"])

            dept_results = await asyncio.gather(
                *[_run(d) for d in depts], return_exceptions=True,
            )

            # 중복 제거 (m_num) — 같은 의사가 여러 진료과에 나올 수 있음
            seen: dict[str, dict] = {}
            for r in dept_results:
                if isinstance(r, Exception):
                    continue
                for doc in r:
                    mk = doc["m_num"]
                    if mk in seen:
                        # 스케줄 합치기 (중복 제거)
                        existing = seen[mk]
                        existing_keys = {(s["day_of_week"], s["time_slot"]) for s in existing["schedules"]}
                        for s in doc["schedules"]:
                            k = (s["day_of_week"], s["time_slot"])
                            if k not in existing_keys:
                                existing["schedules"].append(s)
                                existing_keys.add(k)
                        if doc.get("has_branch_clinic"):
                            existing["has_branch_clinic"] = True
                        continue
                    seen[mk] = doc

            # branch_self 기준으로 필터: 본원 크롤러면 본원 슬롯이 1개 이상 있는 의사만 유지
            filtered = [d for d in seen.values() if d.get("has_branch_clinic")]

            # date_schedules 생성
            for doc in filtered:
                doc["date_schedules"] = self._project_weekly_to_dates(doc["schedules"])

        logger.info(f"[{self.hospital_code}] 총 {len(filtered)}명 수집 (필터 전 {len(seen)}명)")
        self._cached_data = filtered
        return filtered

    # ─── 공개 인터페이스 ──────────────────────────────────────
    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        keys = ("staff_id", "external_id", "name", "department",
                "position", "specialty", "profile_url", "notes")
        return [{k: d.get(k, "") for k in keys} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회 — 해당 교수 1명만 네트워크 요청 (skill 규칙 #7).

        m_num 만 알면 상세 페이지는 바로 가능하지만, 스케줄 테이블은 "진료과 상세 페이지"
        에 있기 때문에 ct_idx 가 필요하다. 캐시에 없으면:
          1) 상세 페이지에서 진료과명(department) 파싱 — ct_idx 없이 m_num 만으로 접근 가능
             (진료과 상세 링크에 ct_idx 가 붙어있음)
          2) 진료과 목록에서 department 매칭으로 ct_idx 역검색
          3) 해당 진료과 1곳의 doctor_box 에서 m_num 매칭
        """
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

        # external_id 포맷: {HOSPITAL_CODE}-{m_num}-{ct_idx}
        prefix = f"{self.hospital_code}-"
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        parts = raw.split("-")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            raw_m_num, ct_idx = parts[0], parts[1]
        elif len(parts) == 1 and parts[0].isdigit():
            # 구버전 external_id (m_num 만) — ct_idx 를 알 수 없음
            raw_m_num = parts[0]
            ct_idx = ""
        else:
            return empty

        async with self._make_client() as client:
            # 상세 페이지로 이름/전문분야/경력 등 얻기 (ct_idx 없으면 1 로 폴백)
            detail = await self._fetch_doctor_detail(client, raw_m_num, ct_idx or "1")

            if not ct_idx:
                # 폴백: 전체 진료과 순회 해서 m_num 매칭되는 ct_idx 찾기 (느림)
                depts = await self._fetch_dept_list(client)
                # 최대 병렬 6개로 순회
                sem = asyncio.Semaphore(6)
                async def _scan(d: dict):
                    async with sem:
                        docs = await self._fetch_dept_doctors(client, d["code"], d["name"])
                    for doc in docs:
                        if doc["m_num"] == raw_m_num:
                            return doc, d["code"], d["name"]
                    return None
                results = await asyncio.gather(*[_scan(d) for d in depts], return_exceptions=True)
                match = None
                for r in results:
                    if isinstance(r, Exception) or r is None:
                        continue
                    match, ct_idx, dept_name_found = r
                    break
                if match is None:
                    return {
                        "staff_id": staff_id,
                        "name": detail.get("name", ""),
                        "department": detail.get("department", ""),
                        "position": "",
                        "specialty": detail.get("specialty", ""),
                        "profile_url": detail.get("profile_url", ""),
                        "notes": detail.get("notes", ""),
                        "schedules": [], "date_schedules": [],
                    }
                dept_docs = [match]
                department = dept_name_found
            else:
                # ct_idx 가 있으므로 해당 진료과 1 곳만 네트워크 요청
                # 진료과명은 상세 페이지의 department echo 가 부정확 → 진료과 목록에서 역매핑
                depts = await self._fetch_dept_list(client)
                department = ""
                for d in depts:
                    if d["code"] == ct_idx:
                        department = d["name"]
                        break
                dept_docs = await self._fetch_dept_doctors(client, ct_idx, department)

        match: Optional[dict] = None
        for doc in dept_docs:
            if doc["m_num"] == raw_m_num:
                match = doc
                break
        if match is None:
            return {
                "staff_id": staff_id,
                "name": detail.get("name", ""),
                "department": department,
                "position": "",
                "specialty": detail.get("specialty", ""),
                "profile_url": detail.get("profile_url", ""),
                "notes": detail.get("notes", ""),
                "schedules": [],
                "date_schedules": [],
            }

        date_schedules = self._project_weekly_to_dates(match["schedules"])
        notes = detail.get("notes", "")
        specialty = detail.get("specialty") or match.get("specialty", "")

        return {
            "staff_id": staff_id,
            "name": detail.get("name") or match.get("name", ""),
            "department": department or match.get("department", ""),
            "position": "",
            "specialty": specialty,
            "profile_url": detail.get("profile_url") or match.get("profile_url", ""),
            "notes": notes,
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


class KnuhCrawler(_KnuhBase):
    """경북대학교병원(대구 본원) 크롤러"""
    hospital_code = "KNUH"
    hospital_name = "경북대학교병원"
    base_url = KNUH_BASE
    dept_list_url = KNUH_DEPT_LIST
    dept_detail_url = KNUH_DEPT_DETAIL
    doctor_detail_url = KNUH_DOCTOR_DETAIL
    branch_self = "headquarters"


class KnuhcgCrawler(_KnuhBase):
    """칠곡경북대학교병원 크롤러"""
    hospital_code = "KNUHCG"
    hospital_name = "칠곡경북대학교병원"
    base_url = KNUHCG_BASE
    dept_list_url = KNUHCG_DEPT_LIST
    dept_detail_url = KNUHCG_DEPT_DETAIL
    doctor_detail_url = KNUHCG_DOCTOR_DETAIL
    branch_self = "chilgok"
