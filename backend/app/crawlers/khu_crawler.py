"""경희대병원 크롤러

경희의료원(khmc.or.kr) 리뉴얼 후 크롤러.
기존 khuh.or.kr 도메인은 폐쇄됨 → www.khmc.or.kr 로 변경.

API:
  진료과 목록: POST /api/department.do (instNo=1, deptClsf=A)
    → JSON 배열 [{deptCd, deptNm, deptClsf}, ...]
  진료시간표: GET /en/treatment/department/{deptCd}/timetable.do
    → 서버렌더링 HTML (영문 페이지가 안정적, 한글은 리다이렉트 이슈)
  의사 프로필: /kr/treatment/doctor/{doctorId}/profile.do
  즐겨찾기 API에서 doctor ID 사용: favoNo 파라미터

스케줄 테이블:
  열: Mon | Tue | Wed | Thu | Fri | Sat
  행: AM, PM (각 의사별)
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.khmc.or.kr"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_COLS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
DAY_COLS_KR = ["월", "화", "수", "목", "금", "토"]


class KhuCrawler:
    """경희대병원 크롤러"""

    def __init__(self):
        self.hospital_code = "KHU"
        self.hospital_name = "경희대병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
        }
        self._cached_data = None
        self._cached_depts = None

    # ─── 진료과 목록 ───

    async def _fetch_departments(self) -> list[dict]:
        """진료과 목록 (POST /api/department.do)"""
        if self._cached_depts is not None:
            return self._cached_depts

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.post(
                    f"{BASE_URL}/api/department.do",
                    data={"instNo": "1", "deptClsf": "A"},
                    headers={
                        **self.headers,
                        "Accept": "application/json, text/plain, */*",
                        "X-Requested-With": "XMLHttpRequest",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                # 응답: JSON 배열 [{deptCd, deptNm, deptClsf}, ...]
                dept_list = data if isinstance(data, list) else data.get("data", data.get("list", []))

                depts = []
                for item in dept_list:
                    code = str(item.get("deptCd", "")).strip()
                    name = str(item.get("deptNm", "")).strip()
                    if code and name:
                        depts.append({"code": code, "name": name})

                logger.info(f"[KHU] 진료과 {len(depts)}개 (API)")
                self._cached_depts = depts
                return depts
            except Exception as e:
                logger.warning(f"[KHU] API 실패, 폴백 사용: {e}")
                # 폴백: 영문 department list 페이지 파싱
                return await self._fetch_departments_fallback(client)

    async def _fetch_departments_fallback(self, client: httpx.AsyncClient) -> list[dict]:
        """폴백: 영문 진료과 목록 페이지 HTML 파싱"""
        try:
            resp = await client.get(f"{BASE_URL}/en/treatment/department/list.do")
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            depts = []
            seen = set()
            for a in soup.select("a[href*='/treatment/department/']"):
                href = a.get("href", "")
                m = re.search(r"/treatment/department/(\d{10})/", href)
                if not m:
                    continue
                code = m.group(1)
                if code in seen:
                    continue
                seen.add(code)
                name = a.get_text(strip=True)
                if name:
                    depts.append({"code": code, "name": name})

            logger.info(f"[KHU] 진료과 {len(depts)}개 (폴백)")
            self._cached_depts = depts
            return depts
        except Exception as e:
            logger.error(f"[KHU] 진료과 폴백도 실패: {e}")
            self._cached_depts = []
            return []

    # ─── 진료과별 의사 목록 + 스케줄 (HTML 파싱) ───

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        """영문 timetable 페이지에서 의사 + 스케줄 파싱

        페이지 구조:
          .timetable_wrap > .doctor_profile > .doctor_profile_list > li.profile_outer
          각 li.profile_outer 안에:
            - .doctor_img > img[src*="displayFile?attachNo=XXXX"]
            - .doctor_cont_inner > .doctor_name (이름)
            - .doctor_cont_inner 에 "Medical Fields:" + 전문분야 텍스트
            - .doctor_info > table (스케줄 - 동적 로드라 비어있을 수 있음)
        """
        try:
            resp = await client.get(
                f"{BASE_URL}/en/treatment/department/{dept_code}/timetable.do",
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[KHU] {dept_name} timetable 페이지 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        doctors = []
        seen_names = set()

        # 각 의사는 li.profile_outer 안에 있음
        profile_items = soup.select("li.profile_outer")
        if not profile_items:
            # 폴백: .doctor_name 엘리먼트 직접 탐색
            profile_items = []
            for name_el in soup.select(".doctor_name"):
                container = name_el.find_parent("li") or name_el.find_parent("div", class_=re.compile(r"profile|doctor|timetable"))
                if container and container not in profile_items:
                    profile_items.append(container)

        for item in profile_items:
            # 이름 추출
            name_el = item.select_one(".doctor_name")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 2 or name in seen_names:
                continue
            seen_names.add(name)

            # 이미지에서 attachNo 추출 (doctor ID 대용)
            attach_no = ""
            img = item.select_one("img[src*='displayFile']")
            if img:
                m = re.search(r"attachNo=(\d+)", img.get("src", ""))
                if m:
                    attach_no = m.group(1)

            # 전문분야 추출: p.doctor_info 에 "Medical Fields:..." 텍스트
            specialty = ""
            spec_el = item.select_one("p.doctor_info, .doctor_info.mt10")
            if spec_el:
                spec_text = spec_el.get_text(strip=True)
                specialty = re.sub(r"^Medical Fields\s*:?\s*", "", spec_text).strip()
            if not specialty:
                # 폴백: doctor_cont_inner 전체에서 추출
                cont = item.select_one(".doctor_cont_inner, .doctor_cont")
                if cont:
                    for p_el in cont.select("p, dd, span"):
                        text = p_el.get_text(strip=True)
                        if "Medical Fields" in text:
                            specialty = re.sub(r"^Medical Fields\s*:?\s*", "", text).strip()
                            break
                        elif text and text != name and "favorite" not in text.lower() and len(text) > 5:
                            specialty = text
                            break

            # 비고/노트
            notes = ""
            holiday_el = item.select_one(".doctor_holiday")
            if holiday_el:
                notes = holiday_el.get_text(strip=True)

            # 스케줄 추출 (테이블이 있는 경우)
            schedules = self._extract_schedule_from_item(item)

            id_key = attach_no or name
            ext_id = f"KHU-{id_key}"

            doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept_name,
                "position": "",
                "specialty": specialty,
                "profile_url": "",
                "notes": notes,
                "schedules": schedules,
                "_attach_no": attach_no,
            })

        logger.info(f"[KHU] {dept_name}: {len(doctors)}명")
        return doctors

    def _extract_schedule_from_item(self, item) -> list[dict]:
        """의사 항목에서 스케줄 테이블 파싱 (있는 경우)"""
        schedules = []
        table = item.select_one(".doctor_info table, table")
        if not table:
            return schedules

        rows = table.select("tr")
        if not rows:
            return schedules

        # 헤더에서 요일 열 매핑
        header_cells = rows[0].select("th, td")
        header_texts = [c.get_text(strip=True) for c in header_cells]

        day_col_map = {}
        for ci, text in enumerate(header_texts):
            for di, day in enumerate(DAY_COLS):
                if day.lower() in text.lower():
                    day_col_map[ci] = di
                    break
            else:
                for di, day in enumerate(DAY_COLS_KR):
                    if day in text:
                        day_col_map[ci] = di
                        break

        if not day_col_map:
            return schedules

        for row in rows[1:]:
            cells = row.select("td, th")
            if not cells:
                continue
            first = cells[0].get_text(strip=True)
            if "AM" in first.upper() or "오전" in first:
                slot = "morning"
            elif "PM" in first.upper() or "오후" in first:
                slot = "afternoon"
            else:
                continue

            for ci, cell in enumerate(cells):
                if ci not in day_col_map:
                    continue
                text = cell.get_text(strip=True)
                has_marker = bool(text) or cell.select("i, img, span.on, span.sche1")
                if has_marker and text not in ("", "-", "X", "x", "off"):
                    start, end = TIME_RANGES[slot]
                    schedules.append({
                        "day_of_week": day_col_map[ci],
                        "time_slot": slot,
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                    })

        return schedules

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
                docs = await self._fetch_dept_doctors(
                    client, dept["code"], dept["name"]
                )
                for doc in docs:
                    ext_id = doc["external_id"]
                    if ext_id in all_doctors:
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
                        if doc["specialty"] and doc["specialty"] not in existing.get("specialty", ""):
                            existing["specialty"] = (
                                f"{existing['specialty']}, {doc['specialty']}"
                                if existing.get("specialty") else doc["specialty"]
                            )
                    else:
                        all_doctors[ext_id] = doc

        result = list(all_doctors.values())
        logger.info(f"[KHU] 총 {len(result)}명 (병합 후)")
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
        """개별 교수 진료시간 조회"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
        }

        # 캐시가 이미 있으면 캐시에서 조회
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return self._to_schedule_dict(d)
            if staff_id.startswith("KHU-"):
                search_key = staff_id.split("-", 1)[-1]
                for d in self._cached_data:
                    if d["name"] == search_key or d.get("_doctor_id") == search_key:
                        return self._to_schedule_dict(d)
            return empty

        # 개별 조회: 진료과 순회하며 해당 의사 찾기
        prefix = "KHU-"
        search_key = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            depts = await self._fetch_departments()
            for dept in depts:
                docs = await self._fetch_dept_doctors(
                    client, dept["code"], dept["name"]
                )
                for doc in docs:
                    if doc["staff_id"] == staff_id or doc["external_id"] == staff_id:
                        return self._to_schedule_dict(doc)
                    if doc.get("_doctor_id") == search_key or doc["name"] == search_key:
                        return self._to_schedule_dict(doc)

        return empty

    @staticmethod
    def _to_schedule_dict(d: dict) -> dict:
        return {
            "staff_id": d["staff_id"],
            "name": d["name"],
            "department": d["department"],
            "position": d.get("position", ""),
            "specialty": d["specialty"],
            "profile_url": d["profile_url"],
            "notes": d.get("notes", ""),
            "schedules": d["schedules"],
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
                position=d.get("position", ""),
                specialty=d["specialty"],
                profile_url=d["profile_url"],
                external_id=d["external_id"],
                notes=d.get("notes", ""),
                schedules=d["schedules"],
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
