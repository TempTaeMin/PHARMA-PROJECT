"""원광대학교병원(WKUH) 크롤러

전라북도 익산시 무왕로 895 / www.wkuh.org

구조 (정적 HTML, httpx 가능):
  1) 진료과 목록 페이지
       /main/mc_medicalpart/medipart.do
     → div.deptlink 안의 partname + doctor.do?sh_mp_part_code={dept} 링크 추출
  2) 진료과별 의료진 목록 페이지 (의사 카드 + 인라인 주간 시간표 포함)
       /main/mc_medicalpart/doctor.do?sh_mp_part_code={dept}
     → 카드 안에 이름/팀/전문분야/주간 시간표 + doctorProfile.do?d_num={d_num} 링크
  3) 의사 개별 상세 페이지 (개별 조회 시 — 3개월치 일별 스케줄 포함)
       /main/mc_medicalpart/doctorProfile.do?d_num={d_num}
     → div.sche_calrendar 안에 td#td_YYYYMMDD_am / _pm 형태의 일별 스케줄 (현재월 + 다음2개월)

스케줄 마크:
  <span class='iconset sche{N}'>레이블</span>
    sche1=외래진료, sche2=인공신장실(투석실 — 제외), sche3=심뇌혈관센터,
    sche4=암센터, sche5=노화방지센터, sche6=소아심장검사(검사 — 제외),
    sche7=정신건강의학과[내과], sche8=외상진료, sche9=휴진(제외),
    sche10=내분비질환
  weekend / 빈 td 는 비활성.

external_id 포맷: WKUH-{d_num}
"""
import re
import asyncio
import logging
from datetime import datetime, date

import httpx
from bs4 import BeautifulSoup

from app.crawlers._schedule_rules import is_clinic_cell

logger = logging.getLogger(__name__)

BASE_URL = "https://www.wkuh.org"
DEPT_LIST_URL = f"{BASE_URL}/main/mc_medicalpart/medipart.do"
DEPT_DOCTORS_URL = f"{BASE_URL}/main/mc_medicalpart/doctor.do"
DOCTOR_PROFILE_URL = f"{BASE_URL}/main/mc_medicalpart/doctorProfile.do"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_KO = ("월", "화", "수", "목", "금", "토", "일")
DAY_INDEX = {ko: i for i, ko in enumerate(DAY_KO)}

# 진료 셀 마크는 <span class="iconset scheN">레이블</span>.
# 레이블 자체로 활동 종류가 구분되므로 라벨 기반 필터링.
# 명시 제외: 휴진(inactive), 검사(검사실 활동), 인공신장실(투석실).
EXCLUDE_LABEL_TOKENS = ("휴진", "검사", "신장실", "수술", "내시경", "시술")


class WkuhCrawler:
    """원광대학교병원 (전북) 크롤러."""

    def __init__(self):
        self.hospital_code = "WKUH"
        self.hospital_name = "원광대학교병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }
        self._cached_data: list[dict] | None = None
        self._dept_map: dict[str, str] | None = None  # sh_mp_part_code → 진료과명

    # ───────────────────── 공용 ─────────────────────

    @staticmethod
    def _clean(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "")).strip()

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True, verify=False,
        )

    # ───────────────────── 진료과 목록 ─────────────────────

    async def _fetch_dept_map(self, client: httpx.AsyncClient) -> dict[str, str]:
        """진료과 목록 페이지에서 {sh_mp_part_code: 진료과명} 추출."""
        if self._dept_map is not None:
            return self._dept_map

        try:
            resp = await client.get(DEPT_LIST_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[WKUH] 진료과 목록 로드 실패: {e}")
            self._dept_map = {}
            return self._dept_map

        soup = BeautifulSoup(resp.text, "html.parser")
        result: dict[str, str] = {}

        # div.deptlink 블록마다 partname(이름) + doctor.do (의료진 링크) 페어
        for dl in soup.find_all("div", class_="deptlink"):
            pn = dl.find("p", class_="partname")
            if pn is None:
                continue
            name = self._clean(pn.get_text())
            if not name:
                continue
            code = ""
            for a in dl.find_all("a", href=True):
                m = re.search(r"sh_mp_part_code=([A-Za-z0-9_]+)", a["href"])
                if m and "doctor.do" in a["href"]:
                    code = m.group(1)
                    break
            if not code:
                # fallback: 어떤 링크든 첫 번째
                for a in dl.find_all("a", href=True):
                    m = re.search(r"sh_mp_part_code=([A-Za-z0-9_]+)", a["href"])
                    if m:
                        code = m.group(1)
                        break
            if code and code not in result:
                result[code] = name

        self._dept_map = result
        logger.info(f"[WKUH] 진료과 {len(result)}개 추출")
        return result

    # ───────────────────── 시간표 셀 판정 ─────────────────────

    def _label_is_clinic(self, label: str) -> bool:
        """iconset 레이블이 외래 진료에 해당하는지."""
        if not label:
            return False
        t = label.strip()
        if not t:
            return False
        for tok in EXCLUDE_LABEL_TOKENS:
            if tok in t:
                return False
        # 외래/진료/센터/클리닉 등 — is_clinic_cell 로 통일
        if is_clinic_cell(t):
            return True
        # 명시 키워드 외에도 "센터" / "질환" 으로 끝나는 활동(암센터/내분비질환 등)은 진료로 본다
        if "센터" in t or "질환" in t:
            return True
        return False

    @staticmethod
    def _extract_icon_label(td) -> str:
        """<td> 안의 첫 번째 iconset span 레이블 반환. 없으면 빈 문자열."""
        if td is None:
            return ""
        if "weekend" in (td.get("class") or []):
            return ""
        span = td.find("span", class_="iconset")
        if span is None:
            return ""
        return re.sub(r"\s+", " ", span.get_text(" ", strip=True)).strip()

    # ───────────────────── 주간 스케줄 (의사 카드 내 table) ─────────────────────

    def _parse_weekly_table(self, table) -> list[dict]:
        """진료과 페이지의 주간 시간표 (월~금 또는 월~토) 파싱.

        구조:
          thead: th(빈) + th 월/화/수/목/금
          tbody: tr1: th '오전' + td×요일
                 tr2: th '오후' + td×요일
        """
        if table is None:
            return []
        thead = table.find("thead")
        if thead is None:
            return []
        head_ths = thead.find_all("th")
        days: list[int] = []
        for th in head_ths:
            t = self._clean(th.get_text())
            if t in DAY_INDEX:
                days.append(DAY_INDEX[t])
        if not days:
            return []

        result: list[dict] = []
        tbody = table.find("tbody")
        if tbody is None:
            return result

        for tr in tbody.find_all("tr"):
            cells = tr.find_all(["th", "td"], recursive=False)
            if not cells:
                continue
            slot_label = self._clean(cells[0].get_text())
            if "오전" in slot_label:
                slot = "morning"
            elif "오후" in slot_label:
                slot = "afternoon"
            else:
                continue
            start_t, end_t = TIME_RANGES[slot]
            day_cells = cells[1:]
            for di, td in enumerate(day_cells):
                if di >= len(days):
                    break
                day_idx = days[di]
                label = self._extract_icon_label(td)
                if not label:
                    # iconset 없으면 텍스트로 fallback (드물게 텍스트만 있는 경우)
                    txt = self._clean(td.get_text())
                    if not is_clinic_cell(txt):
                        continue
                    label = ""  # location 모름
                else:
                    if not self._label_is_clinic(label):
                        continue
                result.append({
                    "day_of_week": day_idx,
                    "time_slot": slot,
                    "start_time": start_t,
                    "end_time": end_t,
                    "location": label if label != "외래진료" else "",
                })
        return result

    # ───────────────────── 월별 스케줄 (profile 페이지) ─────────────────────

    def _parse_monthly_calendar(self, soup) -> list[dict]:
        """profile 페이지의 sche_calrendar 안 td#td_YYYYMMDD_am/_pm 파싱.

        반환: date_schedules 리스트
        """
        result: list[dict] = []
        seen_keys: set[tuple[str, str]] = set()
        for td in soup.find_all("td", id=re.compile(r"^td_\d{8}_(am|pm)$")):
            tid = td.get("id", "")
            m = re.match(r"^td_(\d{4})(\d{2})(\d{2})_(am|pm)$", tid)
            if not m:
                continue
            y, mo, d, ap = m.group(1), m.group(2), m.group(3), m.group(4)
            try:
                schedule_date = date(int(y), int(mo), int(d))
            except ValueError:
                continue
            slot = "morning" if ap == "am" else "afternoon"
            key = (schedule_date.isoformat(), slot)
            if key in seen_keys:
                continue
            label = self._extract_icon_label(td)
            if not label:
                continue
            if not self._label_is_clinic(label):
                # 휴진/검사 등 표시는 '마감'으로 기록
                if "휴진" in label or "휴무" in label:
                    seen_keys.add(key)
                    start_t, end_t = TIME_RANGES[slot]
                    result.append({
                        "schedule_date": schedule_date.isoformat(),
                        "time_slot": slot,
                        "start_time": start_t,
                        "end_time": end_t,
                        "location": "",
                        "status": "마감",
                    })
                continue
            seen_keys.add(key)
            start_t, end_t = TIME_RANGES[slot]
            result.append({
                "schedule_date": schedule_date.isoformat(),
                "time_slot": slot,
                "start_time": start_t,
                "end_time": end_t,
                "location": label if label != "외래진료" else "",
                "status": "진료",
            })
        return result

    # ───────────────────── 카드 파싱 (진료과 페이지) ─────────────────────

    def _parse_doctor_card(self, card, dept_code: str, dept_name: str) -> dict | None:
        """doctor.do 페이지의 의사 카드 1개 파싱."""
        # 상세 링크에서 d_num 추출
        d_num = ""
        for a in card.find_all("a", href=True):
            m = re.search(r"d_num=(\d+)", a["href"])
            if m:
                d_num = m.group(1)
                break
        if not d_num:
            return None

        # 이름
        name_el = card.find("span", class_="name") or card.find("p", class_="name")
        if name_el is None:
            return None
        name = self._clean(name_el.get_text())
        if not name:
            return None

        # 분과(team)
        team_el = card.find("span", class_="team") or card.find("p", class_="team")
        team = self._clean(team_el.get_text()) if team_el else ""
        department = team or dept_name

        # 전문분야
        part_el = card.find("p", class_="part")
        specialty = self._clean(part_el.get_text(" ", strip=True)) if part_el else ""
        # 부수기호 정리 (▣ 등)
        specialty = re.sub(r"[▣■◆▶▷●▲]+", "", specialty).strip()

        # 사진
        photo_url = ""
        img = card.find("img")
        if img and img.get("src"):
            src = img["src"]
            if src.startswith("/"):
                src = BASE_URL + src
            photo_url = src

        # 주간 시간표
        table = card.find("table")
        schedules = self._parse_weekly_table(table)

        external_id = f"{self.hospital_code}-{d_num}"
        profile_url = f"{DOCTOR_PROFILE_URL}?d_num={d_num}"

        return {
            "staff_id": external_id,
            "external_id": external_id,
            "name": name,
            "department": department,
            "position": "",
            "specialty": specialty,
            "profile_url": profile_url,
            "photo_url": photo_url,
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
            "_d_num": d_num,
            "_dept_code": dept_code,
        }

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        """한 진료과의 의료진 목록 + 주간 시간표를 가져온다."""
        try:
            resp = await client.get(DEPT_DOCTORS_URL, params={"sh_mp_part_code": dept_code})
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[WKUH] {dept_name}({dept_code}) 의료진 페이지 로드 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[dict] = []
        # 카드는 보통 div.box / div.list_box / d_info 형태로 묶이지만,
        # 가장 안전한 식별자는 doctorProfile.do?d_num= 링크가 있는 컨테이너.
        # → btn_intro 앵커의 가장 가까운 박스(div) 단위로 파싱.
        seen_d_nums: set[str] = set()
        for a in soup.find_all("a", class_="btn_intro", href=True):
            m = re.search(r"d_num=(\d+)", a["href"])
            if not m:
                continue
            d_num = m.group(1)
            if d_num in seen_d_nums:
                continue
            seen_d_nums.add(d_num)
            # 가까운 카드 컨테이너: div 부모를 따라 올라가다 d_info 가 보이는 지점까지
            card = a
            for _ in range(8):
                card = card.parent
                if card is None:
                    break
                if card.find("div", class_="d_info") is not None or card.find("p", class_="name") or card.find("span", class_="name"):
                    if card.find("table") is not None:
                        break
            if card is None:
                continue
            try:
                doc = self._parse_doctor_card(card, dept_code, dept_name)
                if doc:
                    results.append(doc)
            except Exception as e:
                logger.debug(f"[WKUH] {dept_name} 카드 파싱 오류: {e}")
                continue
        return results

    # ───────────────────── 전체 크롤링 ─────────────────────

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with self._make_client() as client:
            dept_map = await self._fetch_dept_map(client)
            if not dept_map:
                self._cached_data = []
                return self._cached_data

            sem = asyncio.Semaphore(5)

            async def _job(code: str, name: str):
                async with sem:
                    return await self._fetch_dept_doctors(client, code, name)

            tasks = [_job(code, name) for code, name in dept_map.items()]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in results:
                if isinstance(res, Exception):
                    logger.warning(f"[WKUH] 진료과 크롤링 예외: {res}")
                    continue
                for doc in res:
                    eid = doc["external_id"]
                    if eid not in all_doctors:
                        all_doctors[eid] = doc

            # 각 의사의 일별 스케줄(date_schedules) 보강 — profile 페이지에서 3개월치
            doctor_list = list(all_doctors.values())

            async def _enrich(doc: dict):
                async with sem:
                    try:
                        ds = await self._fetch_doctor_date_schedules(client, doc["_d_num"])
                        doc["date_schedules"] = ds
                    except Exception as e:
                        logger.debug(f"[WKUH] {doc['name']} 일별 스케줄 실패: {e}")
                        doc["date_schedules"] = []

            await asyncio.gather(*[_enrich(d) for d in doctor_list], return_exceptions=True)

        result_list = list(all_doctors.values())
        self._cached_data = result_list
        logger.info(f"[WKUH] 총 의사 {len(result_list)}명 수집")
        return result_list

    # ───────────────────── 개별 profile 조회 ─────────────────────

    async def _fetch_doctor_date_schedules(
        self, client: httpx.AsyncClient, d_num: str
    ) -> list[dict]:
        """profile 페이지에서 3개월치 일별 스케줄만 추출."""
        try:
            resp = await client.get(DOCTOR_PROFILE_URL, params={"d_num": d_num})
            resp.raise_for_status()
        except Exception as e:
            logger.debug(f"[WKUH] profile 로드 실패 d_num={d_num}: {e}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        return self._parse_monthly_calendar(soup)

    def _parse_profile_full(self, html: str, d_num: str) -> dict:
        """profile 페이지에서 이름/진료과/전문분야/주간 + 일별 스케줄 모두 추출."""
        soup = BeautifulSoup(html, "html.parser")

        # 이름/팀/전문분야
        name = ""
        team = ""
        specialty = ""
        d_info = soup.find("div", class_="d_info")
        if d_info:
            n = d_info.find("p", class_="name") or d_info.find("span", class_="name")
            if n:
                name = self._clean(n.get_text())
            t = d_info.find("p", class_="team") or d_info.find("span", class_="team")
            if t:
                team = self._clean(t.get_text())
            p = d_info.find("p", class_="part")
            if p:
                specialty = self._clean(p.get_text(" ", strip=True))
                specialty = re.sub(r"[▣■◆▶▷●▲]+", "", specialty).strip()

        # 사진
        photo_url = ""
        img_root = d_info.find_parent() if d_info else soup
        if img_root:
            for img in img_root.find_all("img"):
                src = img.get("src") or ""
                if "praise_relay" in src or "doctor" in src.lower() or "dr_" in src.lower():
                    if src.startswith("/"):
                        src = BASE_URL + src
                    photo_url = src
                    break

        # 주간 시간표 — sche_calrendar 가 있는 profile 에서는 일별만 의미가 큼.
        # 카드 형태(table.table1) 가 별도로 없을 수 있으므로 일별에서 요일 패턴 도출 fallback.
        date_schedules = self._parse_monthly_calendar(soup)

        # 주간 패턴 도출: date_schedules 중 가장 빈도가 높은 (요일,슬롯,location) 조합
        weekly_seen: dict[tuple[int, str, str], int] = {}
        for ds in date_schedules:
            try:
                d = date.fromisoformat(ds["schedule_date"])
            except Exception:
                continue
            if ds.get("status") != "진료":
                continue
            key = (d.weekday(), ds["time_slot"], ds.get("location", ""))
            weekly_seen[key] = weekly_seen.get(key, 0) + 1

        schedules: list[dict] = []
        # 같은 (요일,슬롯) 에 여러 location 이 있으면 빈도 높은 순으로 추가
        # 단, 매주 반복되지 않는(1회성) 스케줄은 제외하기 위해 최소 2회 이상 노출만 채택
        for (dow, slot, loc), cnt in weekly_seen.items():
            if cnt < 2:
                continue
            start_t, end_t = TIME_RANGES[slot]
            schedules.append({
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": start_t,
                "end_time": end_t,
                "location": loc,
            })

        external_id = f"{self.hospital_code}-{d_num}"
        return {
            "staff_id": external_id,
            "name": name,
            "department": team,
            "position": "",
            "specialty": specialty,
            "profile_url": f"{DOCTOR_PROFILE_URL}?d_num={d_num}",
            "photo_url": photo_url,
            "notes": "",
            "schedules": schedules,
            "date_schedules": date_schedules,
        }

    # ───────────────────── 표준 인터페이스 ─────────────────────

    async def get_departments(self) -> list[dict]:
        async with self._make_client() as client:
            dept_map = await self._fetch_dept_map(client)
        return [{"code": c, "name": n} for c, n in dept_map.items()]

    async def crawl_doctor_list(self, department: str | None = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [
            {
                "staff_id": d["staff_id"],
                "external_id": d["external_id"],
                "name": d["name"],
                "department": d["department"],
                "position": d.get("position", ""),
                "specialty": d.get("specialty", ""),
                "profile_url": d.get("profile_url", ""),
                "photo_url": d.get("photo_url", ""),
                "notes": d.get("notes", ""),
            }
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 1명만 네트워크 조회. _fetch_all 절대 호출하지 않음.

        external_id 포맷: WKUH-{d_num}
        """
        empty = {
            "staff_id": staff_id,
            "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "photo_url": "",
            "notes": "",
            "schedules": [], "date_schedules": [],
        }

        # 동일 인스턴스 캐시 우선
        if self._cached_data is not None:
            for d in self._cached_data:
                if d.get("staff_id") == staff_id or d.get("external_id") == staff_id:
                    return {
                        "staff_id": staff_id,
                        "name": d.get("name", ""),
                        "department": d.get("department", ""),
                        "position": d.get("position", ""),
                        "specialty": d.get("specialty", ""),
                        "profile_url": d.get("profile_url", ""),
                        "photo_url": d.get("photo_url", ""),
                        "notes": d.get("notes", ""),
                        "schedules": d.get("schedules", []),
                        "date_schedules": d.get("date_schedules", []),
                    }
            return empty

        # external_id 파싱 — "WKUH-{d_num}"
        prefix = f"{self.hospital_code}-"
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        if not raw or not raw.isdigit():
            logger.warning(f"[WKUH] external_id 형식 오류: {staff_id}")
            return empty
        d_num = raw

        async with self._make_client() as client:
            try:
                resp = await client.get(DOCTOR_PROFILE_URL, params={"d_num": d_num})
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[WKUH] 개별 조회 실패 {staff_id}: {e}")
                return empty
            try:
                doc = self._parse_profile_full(resp.text, d_num)
                doc["staff_id"] = staff_id
                return doc
            except Exception as e:
                logger.error(f"[WKUH] 개별 조회 파싱 실패 {staff_id}: {e}")
                return empty

    async def crawl_doctors(self, department: str | None = None):
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
