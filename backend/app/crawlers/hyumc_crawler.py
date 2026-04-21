"""한양대병원 크롤러

의사 목록: HTML /seoul/mediteam/mediofCent.do (userTab1=mediteam)
스케줄: HTML /seoul/scheduleMonthmethod.do (AJAX, 월간 달력)
"""
import re
import asyncio
import random
import logging
import httpx
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

BASE_URL = "https://seoul.hyumc.com"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

HYUMC_DEPARTMENTS = {
    "1": "가정의학과", "2": "감염내과", "4": "내분비대사내과",
    "6": "마취통증의학과", "8": "방사선종양학과", "9": "병리과",
    "10": "비뇨의학과", "11": "산부인과", "12": "성형외과",
    "15": "소아청소년과", "16": "소화기내과", "17": "신경과",
    "18": "신경외과", "19": "신장내과", "20": "심장내과",
    "37": "심장혈관흉부외과", "21": "안과", "23": "영상의학과",
    "24": "외과", "25": "응급의학과", "26": "이비인후과",
    "27": "재활의학과", "28": "정신건강의학과", "29": "정형외과",
    "31": "진단검사의학과", "32": "치과", "33": "피부과",
    "34": "핵의학과", "36": "호흡기알레르기내과", "35": "혈액종양내과",
    "72": "류마티스내과",
}


class HyumcCrawler:
    """한양대병원 크롤러"""

    def __init__(self):
        self.hospital_code = "HYUMC"
        self.hospital_name = "한양대병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/seoul/main/main.do",
        }
        self._cached_data = None

    async def get_departments(self) -> list[dict]:
        return [{"code": code, "name": name} for code, name in HYUMC_DEPARTMENTS.items()]

    async def _fetch_dept_doctors(self, client: httpx.AsyncClient, seq: str, dept_nm: str, max_retries: int = 3) -> list[dict]:
        """진료과별 의사 목록 HTML 파싱. 빈 응답은 rate limit 으로 간주하고 재시도."""
        name_pattern = re.compile(
            r'class="namea"[^>]*onclick="viewDoctor\s*\(\s*\'(\d+)\'\s*,\s*\'(\d+)\'\s*\)[^"]*"[^>]*>\s*([^<]+)',
        )
        has_any_pattern = re.compile(r'class="namea"')

        html = ""
        for attempt in range(max_retries + 1):
            try:
                resp = await client.get(
                    f"{BASE_URL}/seoul/mediteam/mediofCent.do",
                    params={
                        "action": "detailList",
                        "searchCondition1": "seqMediteam",
                        "searchCommonSeq": seq,
                        "searchKeyword": dept_nm,
                        "userTab1": "mediteam",
                        "searchCondition2": "all",
                        "currentPageNo": "1",
                        "recordCountPerPage": "200",
                    },
                )
                resp.raise_for_status()
                html = resp.text
            except Exception as e:
                if attempt >= max_retries:
                    logger.error(f"[HYUMC] {dept_nm} 의사 목록 실패: {e}")
                    return []
                await asyncio.sleep((2 ** attempt) + random.uniform(0.5, 1.5))
                continue

            if has_any_pattern.search(html) or attempt >= max_retries:
                break
            delay = (2 ** attempt) + random.uniform(0.5, 1.5)
            logger.info(f"[HYUMC] {dept_nm} 빈 응답 — {delay:.1f}s 후 재시도 ({attempt+1}/{max_retries})")
            await asyncio.sleep(delay)

        doctors = []
        seen = set()
        for m in name_pattern.finditer(html):
            doct_cd = m.group(1)
            mediof_cd = m.group(2)
            name = m.group(3).strip()
            if doct_cd in seen or not name:
                continue
            seen.add(doct_cd)
            doctors.append({
                "doct_cd": doct_cd,
                "mediof_cd": mediof_cd,
                "name": name,
                "dept_nm": dept_nm,
                "position": "",
            })

        logger.info(f"[HYUMC] {dept_nm}: {len(doctors)}명")
        return doctors

    def _parse_schedule_html(self, html: str, year: int, month: int) -> tuple[list[dict], list[dict]]:
        """월간 스케줄 HTML 파싱 → (weekly_schedules, date_schedules)

        circle=외래(진료가능), circle_red=외래(정원초과, 진료일로 포함),
        triangle=클리닉, red=휴진(제외)
        """
        day_map = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
        day_slots = {}  # (day_of_week, time_slot) → location
        date_schedules = []

        table_pattern = re.compile(
            r'<table\s+class="tbl_doctor_schedule">(.*?)</table>',
            re.DOTALL,
        )
        for table_m in table_pattern.finditer(html):
            table_html = table_m.group(1)

            # 날짜+요일 추출: "6(월)" → (6, 0)
            date_dows = []
            for dm in re.finditer(r'(\d{1,2})\s*\(([월화수목금토일])\)', table_html):
                day_num = int(dm.group(1))
                dow = day_map.get(dm.group(2), -1)
                if dow >= 0:
                    date_dows.append((day_num, dow))

            if not date_dows:
                continue

            tbody_m = re.search(r'<tbody>(.*?)</tbody>', table_html, re.DOTALL)
            if not tbody_m:
                continue
            tbody = tbody_m.group(1)
            cells = re.findall(r'<td[^>]*>(.*?)</td>', tbody, re.DOTALL)

            col_idx = 0
            for cell in cells:
                date_idx = col_idx // 2
                is_pm = col_idx % 2 == 1

                if date_idx >= len(date_dows):
                    break

                day_num, dow = date_dows[date_idx]
                if dow > 5:
                    col_idx += 1
                    continue

                # 휴진 제외 (red 클래스만 있고 circle/triangle 아닌 경우)
                has_circle = "treatment_state circle" in cell
                has_circle_red = "circle_red" in cell
                has_triangle = "treatment_state triangle" in cell

                # circle, circle_red, triangle 모두 진료일
                if has_circle or has_circle_red or has_triangle:
                    slot = "afternoon" if is_pm else "morning"
                    loc = "클리닉" if has_triangle else "외래"
                    key = (dow, slot)
                    if key not in day_slots:
                        day_slots[key] = loc

                    # 날짜별 스케줄
                    try:
                        date_str = f"{year}-{month:02d}-{day_num:02d}"
                        datetime(year, month, day_num)  # validate
                        start, end = TIME_RANGES[slot]
                        date_schedules.append({
                            "schedule_date": date_str,
                            "time_slot": slot,
                            "start_time": start,
                            "end_time": end,
                            "location": loc,
                            "status": "정원초과" if has_circle_red else "진료",
                        })
                    except ValueError:
                        pass

                col_idx += 1

        schedules = []
        for (dow, slot), loc in sorted(day_slots.items()):
            start, end = TIME_RANGES[slot]
            schedules.append({
                "day_of_week": dow, "time_slot": slot,
                "start_time": start, "end_time": end, "location": loc,
            })

        return schedules, date_schedules

    async def _fetch_schedule(self, client: httpx.AsyncClient, doct_cd: str, mediof_cd: str, name: str) -> list[dict]:
        """월간 스케줄 → 요일 기반 정기 스케줄 (하위 호환)"""
        now = datetime.now()
        # API 버그: month 파라미터에 month-1을 전달해야 해당 월 데이터 반환
        api_month = now.month - 1 if now.month > 1 else 12
        api_year = now.year if now.month > 1 else now.year - 1
        try:
            resp = await client.get(
                f"{BASE_URL}/seoul/scheduleMonthmethod.do",
                params={
                    "doctCd": doct_cd, "mediofCd": mediof_cd,
                    "year": str(api_year), "month": str(api_month), "doctNm": name,
                },
            )
            resp.raise_for_status()
            schedules, _ = self._parse_schedule_html(resp.text, now.year, now.month)
            return schedules
        except Exception:
            return []

    async def _fetch_monthly_schedule(self, client: httpx.AsyncClient, doct_cd: str, mediof_cd: str, name: str, months: int = 3) -> list[dict]:
        """3개월치 날짜별 스케줄 수집"""
        all_date_schedules = []
        now = datetime.now()
        for i in range(months):
            target = now + timedelta(days=i * 30)
            y, m = target.year, target.month
            # API 버그: month 파라미터에 month-1을 전달해야 해당 월 데이터 반환
            api_month = m - 1 if m > 1 else 12
            api_year = y if m > 1 else y - 1
            try:
                resp = await client.get(
                    f"{BASE_URL}/seoul/scheduleMonthmethod.do",
                    params={
                        "doctCd": doct_cd, "mediofCd": mediof_cd,
                        "year": str(api_year), "month": str(api_month), "doctNm": name,
                    },
                )
                resp.raise_for_status()
                _, date_scheds = self._parse_schedule_html(resp.text, y, m)
                all_date_schedules.extend(date_scheds)
            except Exception as e:
                logger.warning(f"[HYUMC] 월별 스케줄 실패 ({y}-{m}, {doct_cd}): {e}")
        return all_date_schedules

    async def _fetch_schedule_and_date(
        self, client: httpx.AsyncClient, doct_cd: str, mediof_cd: str, name: str, months: int = 3,
    ) -> tuple[list[dict], list[dict]]:
        """주간 + 날짜별 스케줄 단일 경로 — 월0 응답에서 weekly 재사용. (4회→3회 API)"""
        now = datetime.now()
        weekly: list[dict] = []
        all_date_schedules: list[dict] = []
        for i in range(months):
            target = now + timedelta(days=i * 30)
            y, m = target.year, target.month
            api_month = m - 1 if m > 1 else 12
            api_year = y if m > 1 else y - 1
            try:
                resp = await client.get(
                    f"{BASE_URL}/seoul/scheduleMonthmethod.do",
                    params={
                        "doctCd": doct_cd, "mediofCd": mediof_cd,
                        "year": str(api_year), "month": str(api_month), "doctNm": name,
                    },
                )
                resp.raise_for_status()
                scheds, date_scheds = self._parse_schedule_html(resp.text, y, m)
                if i == 0:
                    weekly = scheds
                all_date_schedules.extend(date_scheds)
            except Exception as e:
                logger.warning(f"[HYUMC] 스케줄 실패 ({y}-{m}, {doct_cd}): {e}")
        return weekly, all_date_schedules

    async def _fetch_all(self) -> list[dict]:
        import asyncio

        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}

        async with httpx.AsyncClient(headers=self.headers, timeout=60, follow_redirects=True) as client:
            # 1단계: 모든 부서에서 의사 메타데이터 수집 (dedup)
            for seq, dept_nm in HYUMC_DEPARTMENTS.items():
                docs = await self._fetch_dept_doctors(client, seq, dept_nm)
                for doc in docs:
                    doct_cd = doc["doct_cd"]
                    if doct_cd in all_doctors:
                        continue
                    ext_id = f"HYUMC-{doct_cd}-{doc['mediof_cd']}"
                    all_doctors[doct_cd] = {
                        "staff_id": ext_id, "external_id": ext_id,
                        "name": doc["name"], "department": doc["dept_nm"],
                        "position": doc.get("position", ""),
                        "specialty": "",
                        "profile_url": f"{BASE_URL}/seoul/mediteam/mediofCent.do?action=detailView&doctCd={doct_cd}&mediofCd={doc['mediof_cd']}",
                        "notes": "", "schedules": [],
                        "date_schedules": [],
                        "_doct_cd": doct_cd, "_mediof_cd": doc["mediof_cd"],
                    }

            # 2단계: 의사별 스케줄 + 월별 스케줄 병렬 수집 (rate limit 회피)
            sem = asyncio.Semaphore(3)

            async def fetch_one(doc_dict):
                doct_cd = doc_dict["_doct_cd"]
                mediof_cd = doc_dict["_mediof_cd"]
                name = doc_dict["name"]
                async with sem:
                    try:
                        sched, date_sched = await self._fetch_schedule_and_date(
                            client, doct_cd, mediof_cd, name,
                        )
                        doc_dict["schedules"] = sched
                        doc_dict["date_schedules"] = date_sched
                    except Exception as e:
                        logger.warning(f"[HYUMC] {name} 스케줄 실패: {e}")

            await asyncio.gather(*(fetch_one(d) for d in all_doctors.values()))

        result = list(all_doctors.values())
        logger.info(f"[HYUMC] 총 {len(result)}명")
        self._cached_data = result
        return result

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [{k: d[k] for k in ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "notes")} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회 — external_id 에서 mediof_cd 를 파싱해 스케줄 API 만 호출.

        규칙 #7 준수: `_fetch_all()` 또는 전체 진료과 순회 금지.
        external_id 포맷: `HYUMC-{doct_cd}-{mediof_cd}`
        구 포맷(`HYUMC-{doct_cd}`)은 mediof_cd 가 없어 스케줄 API 호출 불가 → 빈 값 반환 + 재동기화 안내.
        """
        _keys = ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules", "date_schedules")
        empty = {"staff_id": staff_id, "name": "", "department": "", "position": "",
                 "specialty": "", "profile_url": "", "notes": "", "schedules": [], "date_schedules": []}

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "" if k not in ("schedules", "date_schedules") else []) for k in _keys}
            return empty

        prefix = "HYUMC-"
        if not staff_id.startswith(prefix):
            return empty
        tail = staff_id[len(prefix):]
        parts = tail.split("-", 1)
        if len(parts) != 2 or not parts[1]:
            logger.warning(f"[HYUMC] 구 포맷 external_id {staff_id} — 스케줄 API 호출 불가. 병원 재동기화 필요.")
            return empty
        doct_cd, mediof_cd = parts[0], parts[1]

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            try:
                schedules, date_schedules = await self._fetch_schedule_and_date(
                    client, doct_cd, mediof_cd, "",
                )
            except Exception as e:
                logger.error(f"[HYUMC] 개별 조회 실패 {staff_id}: {e}")
                return empty

        return {
            "staff_id": staff_id, "name": "", "department": "", "position": "", "specialty": "",
            "profile_url": f"{BASE_URL}/seoul/mediteam/mediofCent.do?action=detailView&doctCd={doct_cd}&mediofCd={mediof_cd}",
            "notes": "", "schedules": schedules, "date_schedules": date_schedules,
        }

    async def crawl_doctors(self, department: str = None):
        from app.schemas.schemas import CrawlResult, CrawledDoctor
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        doctors = [
            CrawledDoctor(name=d["name"], department=d["department"], position=d["position"],
                          specialty=d["specialty"], profile_url=d["profile_url"],
                          external_id=d["external_id"], notes=d.get("notes", ""),
                          schedules=d["schedules"], date_schedules=d.get("date_schedules", []))
            for d in data
        ]
        return CrawlResult(hospital_code=self.hospital_code, hospital_name=self.hospital_name,
                           status="success" if doctors else "partial", doctors=doctors, crawled_at=datetime.utcnow())
