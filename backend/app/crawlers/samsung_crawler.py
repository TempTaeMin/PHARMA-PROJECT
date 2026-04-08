"""서울삼성병원 크롤러

HTML 파싱 기반 크롤러. Playwright 불필요.
API:
  진료과 목록: GET /home/reservation/DoctorScheduleGubun.do?dp_type=O
  진료시간표: POST /home/reservation/DoctorSchedule.do  (dp_type=O&dst={dept_code})
    → 진료과 전체 의사 카드 + 주간 스케줄 테이블이 서버 렌더링으로 반환됨

스케줄 테이블 구조 (주간 swiper-slide 안):
  <th>시간</th> <th>06(월)</th> <th>07(화)</th> ...
  <th>오전</th>  <td>아이콘</td>  <td></td> ...
  <th>오후</th>  <td></td>       <td>아이콘</td> ...

아이콘: icon-medi-schedule01=본원외래, 02=본원클리닉, 04=암병원외래 등
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from collections import Counter

logger = logging.getLogger(__name__)

BASE_URL = "https://www.samsunghospital.com"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_CHAR_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}

LOCATION_MAP = {
    "icon-medi-schedule01": "본원외래",
    "icon-medi-schedule02": "본원클리닉",
    "icon-medi-schedule03": "본원육아상담",
    "icon-medi-schedule04": "암병원외래",
    "icon-medi-schedule05": "암병원클리닉",
    "icon-medi-schedule06": "암병원육아상담",
}


class SamsungCrawler:
    """서울삼성병원 크롤러"""

    def __init__(self):
        self.hospital_code = "SMC"
        self.hospital_name = "삼성서울병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/home/reservation/DoctorSchedule.do",
        }
        self._cached_data = None
        self._cached_depts = None

    # ─── 진료과 목록 ───

    async def _fetch_departments(self) -> list[dict]:
        """진료과 목록 (HTML <option> 파싱)"""
        if self._cached_depts is not None:
            return self._cached_depts

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(
                    f"{BASE_URL}/home/reservation/DoctorScheduleGubun.do",
                    params={"dp_type": "O"},
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                depts = []
                for option in soup.select("option"):
                    code = option.get("value", "").strip()
                    name = option.get_text(strip=True)
                    if code and name:
                        depts.append({"code": code, "name": name})

                logger.info(f"[SMC] 진료과 {len(depts)}개")
                self._cached_depts = depts
                return depts
            except Exception as e:
                logger.error(f"[SMC] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

    # ─── 진료과별 스케줄 크롤링 (핵심) ───

    async def _fetch_dept_schedule(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        """DoctorSchedule.do POST로 진료과 전체 의사 카드 + 스케줄 파싱"""
        try:
            resp = await client.post(
                f"{BASE_URL}/home/reservation/DoctorSchedule.do",
                data={"dp_type": "O", "dst": dept_code},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[SMC] {dept_name} 스케줄 페이지 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # 각 의사 카드: li.card-doctor-profile-schedule
        cards = soup.select("li.card-doctor-profile-schedule")
        if not cards:
            # 폴백: card-item 클래스
            cards = soup.select("li.card-item")

        doctors = []
        for card in cards:
            doc = self._parse_doctor_card(card, dept_name)
            if doc and doc["name"]:
                doctors.append(doc)

        logger.info(f"[SMC] {dept_name}: {len(doctors)}명")
        return doctors

    def _parse_doctor_card(self, card, dept_name: str) -> dict | None:
        """의사 카드 HTML에서 정보 + 스케줄 추출"""
        # DR_NO
        dr_no = ""
        for m in re.finditer(r"searchDoctorInfo\('(\d+)'\)", str(card)):
            dr_no = m.group(1)
            break

        # 이름
        name_el = card.select_one("span[name=fullName]")
        name = name_el.get_text(strip=True) if name_el else ""

        if not name:
            return None

        # 직위: fullName 다음 span
        position = ""
        title_el = card.select_one("h3.card-content-title")
        if title_el:
            spans = title_el.select("span")
            for span in spans:
                text = span.get_text(strip=True)
                if text and text != name and "treatment-parts" not in (span.get("class") or []) and not text.startswith("["):
                    position = text
                    break

        # 진료과
        dept_el = card.select_one("span.treatment-parts")
        department = dept_el.get_text(strip=True).strip("[]") if dept_el else dept_name

        # 전문분야
        spec_el = card.select_one("p.card-content-text")
        specialty = spec_el.get_text(strip=True) if spec_el else ""

        # 스케줄 파싱: swiper-slide 안의 주간 테이블들
        schedules, date_schedules = self._parse_schedule_slides(card)

        ext_id = f"SMC-{dr_no}" if dr_no else f"SMC-{name}"

        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": name,
            "department": department,
            "position": position,
            "specialty": specialty,
            "profile_url": f"{BASE_URL}/home/reservation/common/doctorProfile.do?DR_NO={dr_no}" if dr_no else "",
            "notes": "",
            "schedules": schedules,
            "date_schedules": date_schedules,
        }

    def _parse_schedule_slides(self, card) -> tuple[list[dict], list[dict]]:
        """swiper-slide 안의 주간 테이블들에서 요일별 오전/오후 스케줄 추출

        Returns: (schedules, date_schedules)
        - schedules: 요일 기반 정기 패턴
        - date_schedules: 날짜별 진료 일정 (달력 표시용)
        """
        pattern_counts = {}
        date_schedules = []

        now = datetime.now()
        current_year = now.year
        current_month = now.month
        prev_max_day = 0

        slides = card.select("li.swiper-slide")
        for slide in slides:
            table = slide.select_one("table")
            if not table:
                continue

            rows = table.select("tr")
            if len(rows) < 3:
                continue

            # 헤더행에서 열 → (요일, 일자) 매핑
            header_row = rows[0]
            header_cells = header_row.select("th")
            col_info = {}  # col_index → {"dow": int, "day": int|None}
            for ci, th in enumerate(header_cells):
                txt = th.get_text(strip=True)
                m = re.search(r"(\d+)?\s*\(([월화수목금토])\)", txt)
                if m:
                    day_num = int(m.group(1)) if m.group(1) else None
                    dow = DAY_CHAR_MAP.get(m.group(2))
                    if dow is not None:
                        col_info[ci] = {"dow": dow, "day": day_num}

            # 월 전환 감지
            slide_days = [info["day"] for info in col_info.values() if info["day"] is not None]
            if slide_days:
                min_day = min(slide_days)
                if prev_max_day >= 15 and min_day <= 7:
                    current_month += 1
                    if current_month > 12:
                        current_month = 1
                        current_year += 1
                prev_max_day = max(slide_days)

            # 각 열의 날짜 문자열 생성
            col_dates = {}
            for ci, info in col_info.items():
                if info["day"] is not None:
                    try:
                        datetime(current_year, current_month, info["day"])
                        col_dates[ci] = f"{current_year}-{current_month:02d}-{info['day']:02d}"
                    except ValueError:
                        pass

            # 오전/오후 행 파싱
            for row in rows[1:]:
                cells = row.select("th, td")
                if not cells:
                    continue

                first_text = cells[0].get_text(strip=True)
                if "오전" in first_text:
                    slot = "morning"
                elif "오후" in first_text:
                    slot = "afternoon"
                else:
                    continue

                for ci, cell in enumerate(cells):
                    if ci not in col_info:
                        continue
                    dow = col_info[ci]["dow"]

                    icons = cell.select("i[class*=icon-medi-schedule]")
                    if not icons:
                        continue

                    for icon in icons:
                        classes = icon.get("class", [])
                        location = ""
                        for cls in classes:
                            if cls in LOCATION_MAP:
                                location = LOCATION_MAP[cls]
                                break

                        # 주간 패턴
                        key = (dow, slot, location)
                        pattern_counts[key] = pattern_counts.get(key, 0) + 1

                        # 날짜별 스케줄
                        if ci in col_dates:
                            start, end = TIME_RANGES[slot]
                            date_schedules.append({
                                "schedule_date": col_dates[ci],
                                "time_slot": slot,
                                "start_time": start,
                                "end_time": end,
                                "location": location,
                                "status": "진료",
                            })

        # 패턴을 스케줄로 변환
        schedules = []
        seen = set()
        for (dow, slot, location), count in sorted(pattern_counts.items()):
            dedup_key = (dow, slot, location)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            start, end = TIME_RANGES[slot]
            schedules.append({
                "day_of_week": dow,
                "time_slot": slot,
                "start_time": start,
                "end_time": end,
                "location": location,
            })

        return schedules, date_schedules

    # ─── 전체 크롤링 ───

    async def _fetch_all(self) -> list[dict]:
        """전체 진료과별 의료진 크롤링 후 캐시"""
        if self._cached_data is not None:
            return self._cached_data

        depts = await self._fetch_departments()
        all_doctors = {}  # ext_id → doctor dict

        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True,
        ) as client:
            for dept in depts:
                docs = await self._fetch_dept_schedule(
                    client, dept["code"], dept["name"]
                )
                for doc in docs:
                    ext_id = doc["external_id"]
                    if ext_id in all_doctors:
                        # 이미 있는 교수 → 스케줄 병합
                        existing = all_doctors[ext_id]
                        existing_keys = {
                            (s["day_of_week"], s["time_slot"], s["location"])
                            for s in existing["schedules"]
                        }
                        for s in doc["schedules"]:
                            skey = (s["day_of_week"], s["time_slot"], s["location"])
                            if skey not in existing_keys:
                                existing["schedules"].append(s)
                                existing_keys.add(skey)
                        # date_schedules 병합
                        existing_ds_keys = {
                            (s["schedule_date"], s["time_slot"], s["location"])
                            for s in existing.get("date_schedules", [])
                        }
                        for s in doc.get("date_schedules", []):
                            dskey = (s["schedule_date"], s["time_slot"], s["location"])
                            if dskey not in existing_ds_keys:
                                existing.setdefault("date_schedules", []).append(s)
                                existing_ds_keys.add(dskey)
                        # 전문분야 병합
                        if doc["specialty"] and doc["specialty"] not in existing["specialty"]:
                            existing["specialty"] = (
                                f"{existing['specialty']}, {doc['specialty']}"
                                if existing["specialty"] else doc["specialty"]
                            )
                    else:
                        all_doctors[ext_id] = doc

        # 여러 장소에서 진료하는 경우 특이사항 생성
        result = []
        for doc in all_doctors.values():
            locations = set(s["location"] for s in doc["schedules"] if s["location"])
            notes = ""
            if len(locations) > 1:
                day_names = ["월", "화", "수", "목", "금", "토"]
                lines = []
                for loc in sorted(locations):
                    loc_scheds = [s for s in doc["schedules"] if s["location"] == loc]
                    if loc_scheds:
                        day_slots = []
                        for s in loc_scheds:
                            day = day_names[s["day_of_week"]] if s["day_of_week"] < 6 else "?"
                            slot_name = "오전" if s["time_slot"] == "morning" else "오후"
                            day_slots.append(f"{day} {slot_name}")
                        lines.append(f"{loc}: {', '.join(day_slots)}")
                notes = "\n".join(lines)

            doc["notes"] = notes
            result.append(doc)

        logger.info(f"[SMC] 총 {len(result)}명 (병합 후)")
        self._cached_data = result
        return result

    # ─── 공개 인터페이스 ───

    async def get_departments(self) -> list[dict]:
        """진료과 목록 반환"""
        depts = await self._fetch_departments()
        return [{"code": d["code"], "name": d["name"]} for d in depts]

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        """교수 목록 (스케줄 제외)"""
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
        """개별 교수 진료시간 조회 (개별 요청, 전체 크롤링 안 함)"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
            "date_schedules": [],
        }

        # 캐시가 이미 있으면 캐시에서 조회
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return self._to_schedule_dict(d)

        # 개별 조회: 프로필 페이지에서 이름 → 이름검색으로 스케줄 파싱
        dr_no = staff_id.replace("SMC-", "") if staff_id.startswith("SMC-") else staff_id

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            # 1) 프로필 페이지에서 이름/진료과/직위/전문분야 추출
            try:
                resp = await client.get(
                    f"{BASE_URL}/home/reservation/common/doctorProfile.do",
                    params={"DR_NO": dr_no},
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                title_tag = soup.find("title")
                name, department, position = "", "", ""
                if title_tag:
                    parts = title_tag.get_text(strip=True).split("-")[0].strip().split()
                    if len(parts) >= 2:
                        department = parts[0]
                        name = parts[1]
                        if len(parts) >= 3:
                            position = parts[2]

                specialty = ""
                for dt in soup.select("dt"):
                    if "진료분야" in dt.get_text():
                        dd = dt.find_next_sibling("dd")
                        if dd:
                            specialty = dd.get_text(strip=True)
                        break

                if not name:
                    return empty
            except Exception as e:
                logger.error(f"[SMC] 프로필 조회 실패 ({staff_id}): {e}")
                return empty

            # 2) DoctorSchedule.do 이름검색으로 스케줄 파싱
            try:
                resp = await client.post(
                    f"{BASE_URL}/home/reservation/DoctorSchedule.do",
                    data={"SW": name},
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                # DR_NO가 일치하는 카드 찾기
                cards = soup.select("li.card-doctor-profile-schedule, li.card-item")
                target_card = None
                for card in cards:
                    if f"searchDoctorInfo('{dr_no}')" in str(card):
                        target_card = card
                        break

                schedules, date_schedules = [], []
                if target_card:
                    schedules, date_schedules = self._parse_schedule_slides(target_card)
            except Exception as e:
                logger.error(f"[SMC] 스케줄 검색 실패 ({name}): {e}")
                schedules, date_schedules = [], []

            ext_id = f"SMC-{dr_no}"
            return {
                "staff_id": ext_id,
                "name": name,
                "department": department,
                "position": position,
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/home/reservation/common/doctorProfile.do?DR_NO={dr_no}",
                "notes": "",
                "schedules": schedules,
                "date_schedules": date_schedules,
            }

    @staticmethod
    def _to_schedule_dict(d: dict) -> dict:
        return {
            "staff_id": d["staff_id"],
            "name": d["name"],
            "department": d["department"],
            "position": d["position"],
            "specialty": d["specialty"],
            "profile_url": d["profile_url"],
            "notes": d.get("notes", ""),
            "schedules": d["schedules"],
            "date_schedules": d.get("date_schedules", []),
        }

    async def crawl_doctors(self, department: str = None):
        """전체 크롤링 (CrawlResult 반환)"""
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        data = await self._fetch_all()
        if department:
            data = [d for d in data if d["department"] == department]

        doctors = [
            CrawledDoctor(
                name=d["name"],
                department=d["department"],
                position=d["position"],
                specialty=d["specialty"],
                profile_url=d["profile_url"],
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
