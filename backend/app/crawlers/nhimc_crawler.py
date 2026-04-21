"""국민건강보험공단 일산병원(NHIMC) 크롤러

홈페이지: https://www.nhimc.or.kr

페이지 구조:
  진료과 목록:   GET /dept/deptList.do
  의료진 목록:   GET /dept/profList.do?deptNo=N
    → 카드: <span class="t">이름</span>, <dt>진료분야</dt><dd>...</dd>,
            openDoctorView(deptNo, profNo, 'Y'), fastReserve(deptCd, profEmpCd, 'Y')
  의료진 상세:   GET /doctor/profViewPop.do?deptNo=X&profNo=Y
    → 주간 시간표 셀(<td id="weekAm1"> 등)은 비어있고,
      JS 가 ./getMonthSchedule.do AJAX 로 채워넣음 → 직접 호출 필요
  스케줄 AJAX:   POST /doctor/getMonthSchedule.do
    body: { deptCd, profEmpCd, yyyyMM }
    응답: { "YYYYMMDD": { "AMPM": "AM"|"PM"|"ALL"|"", "amClsn": "", "pmClsn": "" }, ... }

external_id: NHIMC-{deptNo}-{profNo}-{empNo}
  - 단독 프로필 조회에 deptNo+profNo 필요, AJAX 호출에 deptCd+empNo 필요
"""
import re
import json
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, date

logger = logging.getLogger(__name__)

BASE_URL = "https://www.nhimc.or.kr"
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

KNOWN_DEPTS: list[tuple[str, str]] = [
    ("1", "소화기내과"), ("2", "심장내과"), ("3", "호흡기내과"), ("4", "내분비내과"),
    ("5", "신장내과"), ("6", "종양혈액내과"), ("7", "감염내과"), ("8", "류마티스내과"),
    ("9", "통합내과"), ("10", "신경과"), ("11", "정신건강의학과"), ("12", "외과"),
    ("13", "정형외과"), ("14", "신경외과"), ("15", "심장혈관흉부외과"),
    ("16", "성형외과"), ("17", "마취통증의학과"), ("18", "산부인과"),
    ("19", "소아청소년과"), ("20", "안과"), ("21", "이비인후과"), ("22", "피부과"),
    ("23", "비뇨의학과"), ("24", "영상의학과"), ("25", "방사선종양학과"),
    ("26", "병리과"), ("27", "진단검사의학과"), ("28", "재활의학과"),
    ("29", "가정의학과"), ("30", "핵의학과"),
]

_DETAIL_RE = re.compile(r"openDoctorView\s*\(\s*(\d+)\s*,\s*(\d+)\s*,")
_FAST_RESERVE_RE = re.compile(r"fastReserve\s*\(\s*'([^']*)'\s*,\s*'?([^,'\s]+)'?\s*,")


class NhimcCrawler:
    """국민건강보험공단 일산병원 크롤러"""

    def __init__(self):
        self.hospital_code = "NHIMC"
        self.hospital_name = "국민건강보험공단 일산병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": BASE_URL,
        }
        self._cached_data = None
        self._cached_depts = None

    # ───────────── 진료과 ─────────────
    async def _fetch_departments(self) -> list[dict]:
        if self._cached_depts is not None:
            return self._cached_depts

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            try:
                resp = await client.get(f"{BASE_URL}/dept/deptList.do")
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                depts: list[dict] = []
                seen: set[str] = set()
                for a_tag in soup.select("a[href*='deptNo=']"):
                    href = a_tag.get("href", "") or ""
                    name = a_tag.get_text(" ", strip=True)
                    if not name:
                        img = a_tag.select_one("img[alt]")
                        if img:
                            name = (img.get("alt") or "").strip()
                    m = re.search(r"deptNo=(\d+)", href)
                    if not m:
                        continue
                    dept_no = m.group(1)
                    if dept_no in seen:
                        continue
                    clean_name = re.sub(r"\s+", " ", name).strip()
                    if not clean_name or len(clean_name) > 20:
                        continue
                    seen.add(dept_no)
                    depts.append({"code": dept_no, "name": clean_name})

                if len(depts) < 10:
                    depts = [{"code": c, "name": n} for c, n in KNOWN_DEPTS]

                logger.info(f"[NHIMC] 진료과 {len(depts)}개")
                self._cached_depts = depts
                return depts
            except Exception as e:
                logger.error(f"[NHIMC] 진료과 실패: {e}")
                fallback = [{"code": c, "name": n} for c, n in KNOWN_DEPTS]
                self._cached_depts = fallback
                return fallback

    # ───────────── 의료진 카드 파싱 ─────────────
    async def _fetch_dept_doctors(self, client: httpx.AsyncClient, dept_no: str, dept_name: str) -> list[dict]:
        """profList.do?deptNo=N 에서 의료진 카드를 li 단위로 파싱."""
        try:
            resp = await client.get(f"{BASE_URL}/dept/profList.do", params={"deptNo": dept_no})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"[NHIMC] {dept_name}(deptNo={dept_no}) 의료진 실패: {e}")
            return []

        doctors: list[dict] = []
        seen_ext: set[str] = set()

        # 의사 카드는 ul.c_doc_list > li
        for li in soup.select("ul.c_doc_list > li"):
            li_html = str(li)

            dm = _DETAIL_RE.search(li_html)
            if not dm:
                continue
            d_no, p_no = dm.group(1), dm.group(2)

            rm = _FAST_RESERVE_RE.search(li_html)
            dept_cd = rm.group(1) if rm else ""
            emp_no = rm.group(2) if rm else ""

            # 이름: span.t 가 가장 정확. 없으면 img alt
            name = ""
            t_el = li.select_one("p.tit span.t") or li.select_one("span.t")
            if t_el:
                name = t_el.get_text(strip=True)
            if not name:
                img = li.select_one("img[alt]")
                if img:
                    alt = (img.get("alt") or "").strip()
                    alt_clean = re.sub(r"\s*(이미지|교수|전문의|과장|원장|의료진)$", "", alt).strip()
                    if alt_clean and re.search(r"[가-힣]", alt_clean):
                        name = alt_clean.split()[0]

            # 진료분야 (specialty)
            specialty = ""
            for dl in li.select("dl.txt"):
                dt = dl.select_one("dt")
                dd = dl.select_one("dd")
                if dt and dd and ("진료분야" in dt.get_text() or "전문분야" in dt.get_text()):
                    specialty = dd.get_text(" ", strip=True)
                    break

            # 직책: span.x 안의 [가정의학과] 같은 진료과 표기는 무시. 별도 직책 라벨이 있으면 사용
            position = ""
            for el in li.select("span.gubun, em.gubun, span.position"):
                t = el.get_text(strip=True)
                if t in ("과장", "부장", "교수", "전문의", "진료과장", "실장", "원장"):
                    position = t
                    break

            ext_id = f"NHIMC-{d_no}-{p_no}-{emp_no}" if emp_no else f"NHIMC-{d_no}-{p_no}"
            if ext_id in seen_ext:
                continue
            seen_ext.add(ext_id)

            doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/doctor/profViewPop.do?deptNo={d_no}&profNo={p_no}",
                "notes": "",
                "schedules": [],
                "date_schedules": [],
                "dept_no": d_no,
                "prof_no": p_no,
                "dept_cd": dept_cd,
                "emp_no": emp_no,
            })

        return doctors

    # ───────────── AJAX 스케줄 ─────────────
    async def _fetch_month_schedule_ajax(
        self, client: httpx.AsyncClient, dept_cd: str, emp_no: str, yyyymm: str, dept_no: str
    ) -> dict:
        """POST /doctor/getMonthSchedule.do — 한 달치 일정 JSON 반환. 실패 시 {}."""
        if not dept_cd or not emp_no:
            return {}
        try:
            ajax_headers = {
                **self.headers,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": f"{BASE_URL}/doctor/profViewPop.do?deptNo={dept_no}",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
            resp = await client.post(
                f"{BASE_URL}/doctor/getMonthSchedule.do",
                data={"deptCd": dept_cd, "profEmpCd": emp_no, "yyyyMM": yyyymm},
                headers=ajax_headers,
            )
            if resp.status_code != 200 or not resp.text.strip():
                return {}
            try:
                return resp.json()
            except Exception:
                return json.loads(resp.text)
        except Exception as e:
            logger.debug(f"[NHIMC] getMonthSchedule {emp_no}/{yyyymm} 실패: {e}")
            return {}

    @staticmethod
    def _months_to_fetch(months: int = 3) -> list[str]:
        today = date.today()
        out = []
        y, m = today.year, today.month
        for _ in range(months):
            out.append(f"{y:04d}{m:02d}")
            m += 1
            if m > 12:
                m = 1
                y += 1
        return out

    async def _fetch_doctor_schedules(
        self, client: httpx.AsyncClient, doc: dict, months: int = 3
    ) -> tuple[list[dict], list[dict]]:
        """doc 한 명의 schedules(요일 요약) + date_schedules(날짜별) 수집."""
        dept_cd = doc.get("dept_cd", "")
        emp_no = doc.get("emp_no", "")
        dept_no = doc.get("dept_no", "")

        if not dept_cd or not emp_no:
            return [], []

        date_schedules: list[dict] = []
        weekday_slots: set[tuple[int, str]] = set()  # (dow, slot)

        for yyyymm in self._months_to_fetch(months):
            data = await self._fetch_month_schedule_ajax(client, dept_cd, emp_no, yyyymm, dept_no)
            if not data:
                continue

            for key, value in data.items():
                if not (isinstance(key, str) and len(key) == 8 and key.isdigit()):
                    continue
                if not isinstance(value, dict):
                    continue
                ampm = (value.get("AMPM") or "").upper()
                if ampm not in ("AM", "PM", "ALL"):
                    continue

                try:
                    d = datetime.strptime(key, "%Y%m%d").date()
                except ValueError:
                    continue

                am_off = (value.get("amDoffYn") or "").upper() == "Y"
                pm_off = (value.get("pmDoffYn") or "").upper() == "Y"
                am_clsn = (value.get("amClsn") or "").upper() == "Y"
                pm_clsn = (value.get("pmClsn") or "").upper() == "Y"

                slots: list[str] = []
                if ampm in ("AM", "ALL"):
                    slots.append("morning")
                if ampm in ("PM", "ALL"):
                    slots.append("afternoon")

                for slot in slots:
                    is_off = (slot == "morning" and am_off) or (slot == "afternoon" and pm_off)
                    is_full = (slot == "morning" and am_clsn) or (slot == "afternoon" and pm_clsn)
                    if is_off:
                        status = "휴진"
                        # 휴진은 schedules 에 누적하지 않음 (요일 패턴 오염 방지)
                    elif is_full:
                        status = "마감"
                    else:
                        status = "진료"

                    if status != "휴진":
                        weekday_slots.add((d.weekday(), slot))

                    start, end = TIME_RANGES[slot]
                    date_schedules.append({
                        "schedule_date": d.strftime("%Y-%m-%d"),
                        "time_slot": slot,
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                        "status": status if status != "휴진" else "마감",
                    })

        schedules = []
        for dow, slot in sorted(weekday_slots):
            start, end = TIME_RANGES[slot]
            schedules.append({
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": start,
                "end_time": end,
                "location": "",
            })

        return schedules, date_schedules

    # ───────────── 전체 ─────────────
    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        depts = await self._fetch_departments()
        all_doctors: dict[str, dict] = {}

        async with httpx.AsyncClient(headers=self.headers, timeout=60, follow_redirects=True) as client:
            # 1단계: 의사 카드 메타 수집
            for dept in depts:
                dept_no = dept["code"]
                dept_name = dept["name"]
                try:
                    doctors = await self._fetch_dept_doctors(client, dept_no, dept_name)
                except Exception as e:
                    logger.error(f"[NHIMC] {dept_name} 실패: {e}")
                    continue

                for doc in doctors:
                    ext_id = doc["external_id"]
                    if ext_id in all_doctors:
                        continue
                    all_doctors[ext_id] = doc

                logger.info(f"[NHIMC] {dept_name}: {len(doctors)}명")
                await asyncio.sleep(0.15)

            # 2단계: AJAX 스케줄 병렬 수집 (Sem(6))
            sem = asyncio.Semaphore(6)

            async def fetch_one(doc):
                async with sem:
                    try:
                        sched, date_sched = await self._fetch_doctor_schedules(client, doc)
                        doc["schedules"] = sched
                        doc["date_schedules"] = date_sched
                    except Exception as e:
                        logger.warning(f"[NHIMC] 스케줄 실패 {doc.get('name','')} ({doc['external_id']}): {e}")

            await asyncio.gather(*(fetch_one(d) for d in all_doctors.values()))

        result = list(all_doctors.values())
        with_sched = sum(1 for d in result if d["schedules"])
        logger.info(f"[NHIMC] 총 {len(result)}명 (스케줄 보유 {with_sched}명)")
        self._cached_data = result
        return result

    # ───────────── 공개 API ─────────────
    async def get_departments(self) -> list[dict]:
        return await self._fetch_departments()

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
                "position": d["position"],
                "specialty": d["specialty"],
                "profile_url": d["profile_url"],
                "notes": d.get("notes", ""),
            }
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 1명만 조회 (핵심 원칙 #7)."""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "",
            "schedules": [], "date_schedules": [],
        }

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return self._to_schedule_dict(d)
            return empty

        prefix = f"{self.hospital_code}-"
        raw_id = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        parts = raw_id.split("-")

        if len(parts) < 3:
            logger.warning(f"[NHIMC] staff_id 파싱 불가 (dept_no-prof_no-emp_no 필요): {staff_id}")
            return empty

        dept_no, prof_no, emp_no = parts[0], parts[1], parts[2]

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            # 카드 메타 조회 (이름/진료과/dept_cd)
            doc_stub = await self._lookup_card(client, dept_no, prof_no)
            if not doc_stub.get("dept_cd"):
                doc_stub["dept_cd"] = ""
            doc_stub["dept_no"] = dept_no
            doc_stub["prof_no"] = prof_no
            doc_stub["emp_no"] = emp_no

            try:
                schedules, date_schedules = await self._fetch_doctor_schedules(client, doc_stub)
            except Exception as e:
                logger.error(f"[NHIMC] 개별 스케줄 실패 {staff_id}: {e}")
                schedules, date_schedules = [], []

        return {
            "staff_id": staff_id,
            "name": doc_stub.get("name", ""),
            "department": doc_stub.get("department", ""),
            "position": doc_stub.get("position", ""),
            "specialty": doc_stub.get("specialty", ""),
            "profile_url": f"{BASE_URL}/doctor/profViewPop.do?deptNo={dept_no}&profNo={prof_no}",
            "notes": "",
            "schedules": schedules,
            "date_schedules": date_schedules,
        }

    async def _lookup_card(self, client: httpx.AsyncClient, dept_no: str, prof_no: str) -> dict:
        """profList.do 에서 해당 prof_no 카드만 추출."""
        stub = {"name": "", "department": "", "position": "", "specialty": "", "dept_cd": ""}
        try:
            # 진료과명 보충
            for c, n in KNOWN_DEPTS:
                if c == dept_no:
                    stub["department"] = n
                    break

            doctors = await self._fetch_dept_doctors(client, dept_no, stub["department"])
            for d in doctors:
                if d["prof_no"] == prof_no:
                    stub.update({
                        "name": d["name"],
                        "department": d["department"],
                        "position": d["position"],
                        "specialty": d["specialty"],
                        "dept_cd": d["dept_cd"],
                    })
                    break
        except Exception as e:
            logger.debug(f"[NHIMC] 카드 조회 실패 dept={dept_no}: {e}")
        return stub

    @staticmethod
    def _to_schedule_dict(d: dict) -> dict:
        return {
            "staff_id": d["staff_id"],
            "name": d.get("name", ""),
            "department": d.get("department", ""),
            "position": d.get("position", ""),
            "specialty": d.get("specialty", ""),
            "profile_url": d.get("profile_url", ""),
            "notes": d.get("notes", ""),
            "schedules": d.get("schedules", []),
            "date_schedules": d.get("date_schedules", []),
        }

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
                external_id=d["external_id"],
                notes=d.get("notes", ""),
                schedules=d.get("schedules", []),
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
