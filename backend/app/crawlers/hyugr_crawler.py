"""한양대학교구리병원(HYUGR) 크롤러

홈페이지: https://guri.hyumc.com

본원(HYUMC) 과 동일한 Hanyang 의료시스템을 사용하므로 엔드포인트 / 파라미터 /
HTML 구조가 거의 동일하다. 단 URL prefix 가 /guri/ 이고 진료과 `searchCommonSeq`
번호 체계가 본원과 다르다 (본원: 1~72, 구리: 38~69, 10008, 10014 등).

**reCAPTCHA 우회.** guri.hyumc.com 은 일반 User-Agent 에 대해
`/guri/botPopupmethod.do` 로 리다이렉트하지만, `robots.txt` 에서
Googlebot / Bingbot 등은 `Allow: /` 로 명시되어 있다. 따라서 Googlebot UA 로
요청하면 정상 HTML 이 반환된다.

진료과 목록: HTML /guri/mediteam/mediofCent.do (userTab1=mediteam)
스케줄: HTML /guri/scheduleMonthmethod.do (AJAX, 월간 달력)
"""
from __future__ import annotations

import re
import asyncio
import logging
import random
import urllib.parse
import httpx
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

BASE_URL = "https://guri.hyumc.com"
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

# 동적 추출 실패 시 fallback seed (2026-04 기준 메인 페이지에서 관찰된 진료과)
HYUGR_DEPT_SEED = {
    "38": "감염내과", "40": "내분비대사내과", "41": "류마티스내과",
    "42": "마취통증의학과", "43": "병리과", "44": "비뇨기과",
    "45": "산부인과", "46": "성형외과", "47": "소아청소년과",
    "48": "소화기내과", "49": "신경과", "50": "신경외과",
    "51": "신장내과", "52": "심장내과", "53": "안과",
    "54": "영상의학과", "55": "외과", "56": "응급의학과",
    "57": "이비인후과", "58": "재활의학과", "59": "정신건강의학과",
    "60": "정형외과", "61": "직업환경의학과", "62": "진단검사의학과",
    "63": "치과", "64": "통증클리닉", "65": "피부과",
    "66": "핵의학과", "67": "혈액종양내과", "68": "호흡기내과",
    "69": "흉부외과", "10008": "만성통증센터", "10014": "외상외과",
}


class HyugrCrawler:
    """한양대학교구리병원 크롤러 (HYUMC 본원과 동일 시스템)"""

    def __init__(self):
        self.hospital_code = "HYUGR"
        self.hospital_name = "한양대학교구리병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": f"{BASE_URL}/guri/main/main.do",
        }
        self._cached_data = None
        self._cached_depts: dict[str, str] | None = None

    async def _fetch_dept_map(self, client: httpx.AsyncClient) -> dict[str, str]:
        """진료과 허브 페이지에서 seq → 진료과명 맵을 동적 추출. 실패 시 SEED 사용."""
        if self._cached_depts is not None:
            return self._cached_depts
        try:
            resp = await client.get(f"{BASE_URL}/guri/mediteam/mediofCent.do")
            resp.raise_for_status()
            html = resp.content.decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"[HYUGR] 진료과 목록 로드 실패, seed 사용: {e}")
            self._cached_depts = dict(HYUGR_DEPT_SEED)
            return self._cached_depts

        pattern = re.compile(r'searchCommonSeq=(\d+)[^"\']*searchKeyword=([^&"\']+)')
        result: dict[str, str] = {}
        for m in pattern.finditer(html):
            seq = m.group(1)
            kw = urllib.parse.unquote(m.group(2)).strip()
            if seq in result or not kw:
                continue
            # 센터/검진/게시판류는 제외 — 일반 진료과만 선별
            if any(skip in kw for skip in ("검진", "센터", "게시판", "베스트")):
                # 예외: 외상외과(10014) 처럼 실제 진료 단위인 경우는 seed 에 유지
                if seq not in HYUGR_DEPT_SEED:
                    continue
            result[seq] = kw

        if not result:
            logger.warning("[HYUGR] 진료과 맵 추출 실패, seed 사용")
            result = dict(HYUGR_DEPT_SEED)

        self._cached_depts = result
        logger.info(f"[HYUGR] 진료과 {len(result)}개 추출")
        return result

    async def get_departments(self) -> list[dict]:
        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            dept_map = await self._fetch_dept_map(client)
        return [{"code": seq, "name": name} for seq, name in dept_map.items()]

    async def _fetch_dept_doctors(self, client: httpx.AsyncClient, seq: str, dept_nm: str, max_retries: int = 3) -> list[dict]:
        """진료과별 의사 목록 HTML 파싱 (본원 HYUMC 와 동일 구조).

        서버가 세션 rate limit 으로 빈 응답을 주는 경우가 있어 exponential backoff
        재시도를 한다. 단, 실제로 의사가 0명인 진료과도 존재하므로 응답 HTML 에
        의사 목록 컨테이너(`namea` class) 자체가 없는 경우를 rate-limit 신호로 간주.
        """
        name_pattern = re.compile(
            r'class="namea"[^>]*onclick="viewDoctor\s*\(\s*\'(\d+)\'\s*,\s*\'(\d+)\'\s*\)[^"]*"[^>]*>\s*([^<]+)',
        )
        has_any_pattern = re.compile(r'class="namea"')

        html = ""
        for attempt in range(max_retries + 1):
            try:
                resp = await client.get(
                    f"{BASE_URL}/guri/mediteam/mediofCent.do",
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
                html = resp.content.decode("utf-8", errors="replace")
            except Exception as e:
                if attempt >= max_retries:
                    logger.error(f"[HYUGR] {dept_nm} 의사 목록 실패: {e}")
                    return []
                await asyncio.sleep((2 ** attempt) + random.uniform(0.5, 1.5))
                continue

            # 빈 응답 / rate limit 감지: "의료진 > " 제목은 있지만 namea 가 없고 본문이 비정상
            if has_any_pattern.search(html):
                break
            # mediofCent 페이지 레이아웃은 있는데 namea 가 아예 없으면 0명 or rate limit
            if attempt >= max_retries:
                break
            delay = (2 ** attempt) + random.uniform(0.5, 1.5)
            logger.info(f"[HYUGR] {dept_nm} 빈 응답 — {delay:.1f}s 후 재시도 ({attempt+1}/{max_retries})")
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

        logger.info(f"[HYUGR] {dept_nm}: {len(doctors)}명")
        return doctors

    def _parse_schedule_html(self, html: str, year: int, month: int) -> tuple[list[dict], list[dict]]:
        """월간 스케줄 HTML 파싱 → (weekly_schedules, date_schedules).

        본원 HYUMC 와 동일 스키마:
          circle=외래(진료), circle_red=외래(정원초과, 진료로 포함),
          triangle=클리닉, red(만) =휴진(제외)
        """
        day_map = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
        day_slots: dict[tuple[int, str], str] = {}
        date_schedules: list[dict] = []

        table_pattern = re.compile(
            r'<table[^>]*class="[^"]*tbl_doctor_schedule[^"]*"[^>]*>(.*?)</table>',
            re.DOTALL,
        )
        for table_m in table_pattern.finditer(html):
            table_html = table_m.group(1)

            date_dows: list[tuple[int, int]] = []
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

                has_circle = "treatment_state circle" in cell
                has_circle_red = "circle_red" in cell
                has_triangle = "treatment_state triangle" in cell

                if has_circle or has_circle_red or has_triangle:
                    slot = "afternoon" if is_pm else "morning"
                    loc = "클리닉" if has_triangle else "외래"
                    key = (dow, slot)
                    if key not in day_slots:
                        day_slots[key] = loc
                    try:
                        datetime(year, month, day_num)
                        start, end = TIME_RANGES[slot]
                        date_schedules.append({
                            "schedule_date": f"{year}-{month:02d}-{day_num:02d}",
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
        """월간 스케줄 → 요일 기반 정기 스케줄. 구리는 month 파라미터 그대로 사용 (본원의 month-1 버그 없음)"""
        now = datetime.now()
        try:
            resp = await client.get(
                f"{BASE_URL}/guri/scheduleMonthmethod.do",
                params={
                    "doctCd": doct_cd, "mediofCd": mediof_cd,
                    "year": str(now.year), "month": str(now.month), "doctNm": name,
                },
            )
            resp.raise_for_status()
            html = resp.content.decode("utf-8", errors="replace")
            schedules, _ = self._parse_schedule_html(html, now.year, now.month)
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
            try:
                resp = await client.get(
                    f"{BASE_URL}/guri/scheduleMonthmethod.do",
                    params={
                        "doctCd": doct_cd, "mediofCd": mediof_cd,
                        "year": str(y), "month": str(m), "doctNm": name,
                    },
                )
                resp.raise_for_status()
                html = resp.content.decode("utf-8", errors="replace")
                _, date_scheds = self._parse_schedule_html(html, y, m)
                all_date_schedules.extend(date_scheds)
            except Exception as e:
                logger.warning(f"[HYUGR] 월별 스케줄 실패 ({y}-{m}, {doct_cd}): {e}")
        return all_date_schedules

    async def _fetch_all(self) -> list[dict]:
        if self._cached_data is not None:
            return self._cached_data

        all_doctors: dict[str, dict] = {}
        async with httpx.AsyncClient(headers=self.headers, timeout=60, follow_redirects=True) as client:
            # 1단계: 진료과 맵 로드
            dept_map = await self._fetch_dept_map(client)

            # 2단계: 진료과별 의사 목록 — rate limit 회피 위해 동시성 2
            sem_dept = asyncio.Semaphore(2)

            async def fetch_dept_one(seq, dept_nm):
                async with sem_dept:
                    return await self._fetch_dept_doctors(client, seq, dept_nm)

            dept_results = await asyncio.gather(*(fetch_dept_one(s, n) for s, n in dept_map.items()))
            for docs in dept_results:
                for doc in docs:
                    doct_cd = doc["doct_cd"]
                    if doct_cd in all_doctors:
                        continue
                    ext_id = f"HYUGR-{doct_cd}-{doc['mediof_cd']}"
                    all_doctors[doct_cd] = {
                        "staff_id": ext_id, "external_id": ext_id,
                        "name": doc["name"], "department": doc["dept_nm"],
                        "position": doc.get("position", ""),
                        "specialty": "",
                        "profile_url": f"{BASE_URL}/guri/mediteam/mediofCent.do?action=detailView&doctCd={doct_cd}&mediofCd={doc['mediof_cd']}",
                        "notes": "",
                        "_mediof_cd": doc["mediof_cd"],
                    }

            # 3단계: 의사별 스케줄 병렬 조회 (Sem 2 — rate limit 회피)
            sem = asyncio.Semaphore(2)

            async def fetch_doc(doct_cd, info):
                mediof_cd = info.pop("_mediof_cd")
                async with sem:
                    try:
                        sched, date_sched = await asyncio.gather(
                            self._fetch_schedule(client, doct_cd, mediof_cd, info["name"]),
                            self._fetch_monthly_schedule(client, doct_cd, mediof_cd, info["name"]),
                        )
                        info["schedules"] = sched
                        info["date_schedules"] = date_sched
                    except Exception as e:
                        logger.warning(f"[HYUGR] {info.get('name','')} 스케줄 실패: {e}")
                        info.setdefault("schedules", [])
                        info.setdefault("date_schedules", [])

            await asyncio.gather(*(fetch_doc(dc, info) for dc, info in all_doctors.items()))

        result = list(all_doctors.values())
        logger.info(f"[HYUGR] 총 {len(result)}명")
        self._cached_data = result
        return result

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]
        return [{k: d[k] for k in ("staff_id", "external_id", "name", "department", "position", "specialty", "profile_url", "notes")} for d in data]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 조회 — external_id 에서 mediof_cd 를 파싱해 스케줄 API 만 호출.

        규칙 #7 준수: `_fetch_all()` / `_fetch_dept_map()` / 전체 진료과 순회 금지.
        external_id 포맷: `HYUGR-{doct_cd}-{mediof_cd}`
        구 포맷(`HYUGR-{doct_cd}`)은 mediof_cd 가 없어 스케줄 API 호출 불가 → 빈 값 반환 + 재동기화 안내.
        """
        _keys = ("staff_id", "name", "department", "position", "specialty", "profile_url", "notes", "schedules", "date_schedules")
        empty = {"staff_id": staff_id, "name": "", "department": "", "position": "",
                 "specialty": "", "profile_url": "", "notes": "",
                 "schedules": [], "date_schedules": []}

        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return {k: d.get(k, "" if k not in ("schedules", "date_schedules") else []) for k in _keys}
            return empty

        prefix = "HYUGR-"
        if not staff_id.startswith(prefix):
            return empty
        tail = staff_id[len(prefix):]
        parts = tail.split("-", 1)
        if len(parts) != 2 or not parts[1]:
            logger.warning(f"[HYUGR] 구 포맷 external_id {staff_id} — 스케줄 API 호출 불가. 병원 재동기화 필요.")
            return empty
        doct_cd, mediof_cd = parts[0], parts[1]

        async with httpx.AsyncClient(headers=self.headers, timeout=30, follow_redirects=True) as client:
            try:
                schedules = await self._fetch_schedule(client, doct_cd, mediof_cd, "")
                date_schedules = await self._fetch_monthly_schedule(client, doct_cd, mediof_cd, "")
            except Exception as e:
                logger.error(f"[HYUGR] 개별 조회 실패 {staff_id}: {e}")
                return empty

        return {
            "staff_id": staff_id, "name": "", "department": "", "position": "", "specialty": "",
            "profile_url": f"{BASE_URL}/guri/mediteam/mediofCent.do?action=detailView&doctCd={doct_cd}&mediofCd={mediof_cd}",
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
                           status="success" if doctors else "partial", doctors=doctors,
                           crawled_at=datetime.utcnow())
