"""강북삼성병원 크롤러

HTML + AJAX 기반 크롤러 (리뉴얼 후 main.kbsmc.co.kr 도메인).
기존 www.kbsmc.co.kr → main.kbsmc.co.kr 로 변경됨.

API/페이지:
  진료과 목록: GET /main/part/list.do → HTML 파싱 (mp_idx 추출)
  의사 목록: GET /main/doctor/list.do?mp_idx={id} → HTML 카드 파싱 (md_idx, 이름, 전문분야)
  의사 상세: GET /main/doctor/view.do?md_idx={id}&mp_idx={dept}
  스케줄 AJAX: POST /main/doctor_schedule/ajax_schedule.do
    → params: part_idx, doctor_idx, sdate, edate
    → JSON 응답: am/pm 가용 플래그
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

BASE_URL = "https://main.kbsmc.co.kr"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}


class KbsmcCrawler:
    """강북삼성병원 크롤러"""

    def __init__(self):
        self.hospital_code = "KBSMC"
        self.hospital_name = "강북삼성병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/main/doctor/list.do",
        }
        self._cached_data = None
        self._cached_depts = None

    # ─── 진료과 목록 ───

    async def _fetch_departments(self) -> list[dict]:
        """진료과 목록 (/main/part/list.do HTML 파싱 - mp_idx 추출)"""
        if self._cached_depts is not None:
            return self._cached_depts

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(f"{BASE_URL}/main/part/list.do")
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                depts = []
                seen = set()
                # 의사 목록 링크에서 mp_idx 추출: ../doctor/list.do?mp_idx=1
                for a in soup.select("a[href*='doctor/list.do']"):
                    href = a.get("href", "")
                    m = re.search(r"mp_idx=(\d+)", href)
                    if not m:
                        continue
                    code = m.group(1)
                    if code in seen:
                        continue
                    seen.add(code)

                    # 부모 li에서 진료과명 추출
                    parent_li = a.find_parent("li")
                    name = ""
                    if parent_li:
                        # li 직속 텍스트 또는 첫 번째 텍스트 노드
                        for child in parent_li.children:
                            if isinstance(child, str):
                                text = child.strip()
                                if text and text not in ("의료진", "위치"):
                                    name = text
                                    break
                            elif hasattr(child, 'get_text'):
                                text = child.get_text(strip=True)
                                if text and text not in ("의료진", "위치") and "href" not in str(child):
                                    name = text
                                    break
                    if not name:
                        # a 태그 이전의 텍스트
                        prev = a.previous_sibling
                        if prev and isinstance(prev, str):
                            name = prev.strip()
                    if not name:
                        name = f"진료과{code}"

                    depts.append({"code": code, "name": name})

                logger.info(f"[KBSMC] 진료과 {len(depts)}개")
                self._cached_depts = depts
                return depts
            except Exception as e:
                logger.error(f"[KBSMC] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

    # ─── 진료과별 의사 목록 ───

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        """진료과별 의사 카드 파싱 (/main/doctor/list.do?mp_idx={code})"""
        try:
            resp = await client.get(
                f"{BASE_URL}/main/doctor/list.do",
                params={"mp_idx": dept_code},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[KBSMC] {dept_name} 의사 목록 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        doctors = []
        # doctor/view.do 링크에서 md_idx 추출
        # 구조: <div class="name"><a href="/main/doctor/view.do?md_idx=1&mp_idx=1">강재헌<span>가정의학과</span></a></div>
        # 또는: 부모 div.name에서 이름과 진료과가 별도 텍스트 노드
        seen_ids = set()
        for a in soup.select("a[href*='doctor/view.do']"):
            href = a.get("href", "")
            m = re.search(r"md_idx=(\d+)", href)
            if not m:
                continue
            md_idx = m.group(1)
            if md_idx in seen_ids:
                continue

            # "상세보기" 등 버튼 링크 건너뛰기
            link_text = a.get_text(strip=True)
            if link_text in ("상세보기", "진료예약", "예약"):
                continue

            seen_ids.add(md_idx)

            # 이름 추출: 여러 전략 시도
            name = ""

            # 전략 1: span[data-name-ko] 속성에서 직접 추출
            name_span = a.select_one("span[data-name-ko]")
            if name_span:
                name = name_span.get("data-name-ko", "").strip()
                if not name:
                    name = name_span.get_text(strip=True)

            # 전략 2: span.part를 제외한 링크 내 텍스트
            if not name:
                for child in a.children:
                    if hasattr(child, 'get') and 'part' in (child.get('class') or []):
                        continue  # span.part (진료과명) 건너뛰기
                    if isinstance(child, str):
                        t = child.strip()
                        if t and re.fullmatch(r'[가-힣]{2,5}', t):
                            name = t
                            break
                    elif hasattr(child, 'get_text'):
                        t = child.get_text(strip=True)
                        if t and re.fullmatch(r'[가-힣]{2,5}', t):
                            name = t
                            break

            # 전략 3: img alt 속성 ("강재헌 이미지" → "강재헌")
            if not name:
                parent_card = a.find_parent("li") or a.find_parent("div")
                if parent_card:
                    img = parent_card.select_one("img[alt]")
                    if img:
                        alt = img.get("alt", "").strip()
                        alt_clean = re.sub(r'\s*(이미지|교수|전문의|과장|원장|의사|프로필)\s*$', '', alt).strip()
                        if alt_clean and re.fullmatch(r'[가-힣]{2,5}', alt_clean):
                            name = alt_clean

            # 전략 4: 링크 텍스트에서 진료과명 제거
            if not name:
                if link_text and link_text not in ("상세보기", "진료예약", "예약"):
                    if dept_name and link_text.endswith(dept_name):
                        name = link_text[:-len(dept_name)].strip()
                    elif len(link_text) <= 10:
                        m_name = re.match(r'^([가-힣]{2,4})', link_text)
                        if m_name:
                            name = m_name.group(1)

            if not name or len(name) > 30 or name in ("상세보기", "진료예약"):
                continue

            # 상위 카드 요소 (li 또는 div) 찾기
            parent_card = a.find_parent("li") or a.find_parent("div", class_=re.compile(r"doctor|card|item"))
            if not parent_card:
                parent_card = a.find_parent("div")

            specialty = ""
            position = ""
            if parent_card:
                # 진료분야 텍스트 찾기
                full_text = parent_card.get_text(separator="|", strip=True)
                if "진료분야" in full_text:
                    parts = full_text.split("진료분야")
                    if len(parts) > 1:
                        spec_text = parts[1].strip().lstrip("|").strip()
                        # 예약/상세보기 관련 텍스트 제거
                        spec_text = re.split(r"\|?(?:진료예약|상세보기|온라인|예약)", spec_text)[0].strip()
                        # 파이프 제거
                        spec_text = spec_text.replace("|", ", ").strip(", ")
                        specialty = spec_text

                # 직위 추출
                for sel in [".sub_txt", "span.position", "span.title", "span.job", "em"]:
                    pos_el = parent_card.select_one(sel)
                    if pos_el:
                        pos_text = pos_el.get_text(strip=True)
                        if pos_text and pos_text != name and len(pos_text) < 20:
                            position = pos_text
                            break

            ext_id = f"KBSMC-{md_idx}-{dept_code}"
            doctors.append({
                "staff_id": ext_id,
                "external_id": ext_id,
                "name": name,
                "department": dept_name,
                "position": position,
                "specialty": specialty,
                "profile_url": f"{BASE_URL}/main/doctor/view.do?md_idx={md_idx}&mp_idx={dept_code}",
                "notes": "",
                "schedules": [],
                "_md_idx": md_idx,
                "_mp_idx": dept_code,
            })

        logger.info(f"[KBSMC] {dept_name}: {len(doctors)}명")
        return doctors

    # ─── 개별 스케줄 조회 (AJAX) ───

    async def _fetch_doctor_schedule(
        self, client: httpx.AsyncClient, md_idx: str, mp_idx: str
    ) -> list[dict]:
        """AJAX로 의사 스케줄 조회 (/main/doctor_schedule/ajax_schedule.do)"""
        if not md_idx:
            return []

        # 당월 1일~말일 날짜 계산 (1개월치로 주간 패턴을 더 정확하게 추출)
        today = datetime.now()
        first_day = today.replace(day=1)
        if today.month == 12:
            last_day = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last_day = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        sdate = first_day.strftime("%Y-%m-%d")
        edate = last_day.strftime("%Y-%m-%d")

        try:
            resp = await client.post(
                f"{BASE_URL}/main/doctor_schedule/ajax_schedule.do",
                data={
                    "part_idx": mp_idx,
                    "doctor_idx": md_idx,
                    "sdate": sdate,
                    "edate": edate,
                },
                headers={
                    **self.headers,
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[KBSMC] 스케줄 AJAX 실패 (md_idx={md_idx}): {e}")
            # 폴백: doctor view 페이지에서 스케줄 파싱 시도
            return await self._fetch_schedule_from_view(client, md_idx, mp_idx)

        schedules = []
        # AJAX 응답 파싱: 날짜별 am/pm 가용 플래그
        schedule_list = data if isinstance(data, list) else data.get("data", data.get("list", []))
        if isinstance(schedule_list, dict):
            schedule_list = [schedule_list]

        # 날짜 → 요일 매핑하여 스케줄 생성
        for item in schedule_list:
            date_str = str(item.get("date", item.get("sche_date", item.get("sdate", "")))).strip()
            am_flag = str(item.get("am", item.get("jsAm", item.get("am_yn", "")))).strip()
            pm_flag = str(item.get("pm", item.get("jsPm", item.get("pm_yn", "")))).strip()

            # 날짜에서 요일 추출
            dow = None
            if date_str:
                try:
                    dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                    dow = dt.weekday()  # 0=월 ~ 5=토
                except ValueError:
                    pass

            if dow is None or dow > 5:
                continue

            if am_flag and am_flag not in ("", "0", "N", "null", "None", "close"):
                start, end = TIME_RANGES["morning"]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": "morning",
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })
            if pm_flag and pm_flag not in ("", "0", "N", "null", "None", "close"):
                start, end = TIME_RANGES["afternoon"]
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": "afternoon",
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })

        # 중복 제거 (같은 요일+슬롯)
        seen = set()
        unique = []
        for s in schedules:
            key = (s["day_of_week"], s["time_slot"])
            if key not in seen:
                seen.add(key)
                unique.append(s)

        return unique

    async def _fetch_monthly_schedule(
        self, client: httpx.AsyncClient, md_idx: str, mp_idx: str, months: int = 3
    ) -> list[dict]:
        """3개월치 날짜별 스케줄 수집 (date_schedules용)"""
        if not md_idx:
            return []

        all_date_schedules = []
        now = datetime.now()

        for i in range(months):
            target = now + timedelta(days=i * 30)
            first_day = target.replace(day=1)
            if first_day.month == 12:
                last_day = first_day.replace(year=first_day.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                last_day = first_day.replace(month=first_day.month + 1, day=1) - timedelta(days=1)

            sdate = first_day.strftime("%Y-%m-%d")
            edate = last_day.strftime("%Y-%m-%d")

            try:
                resp = await client.post(
                    f"{BASE_URL}/main/doctor_schedule/ajax_schedule.do",
                    data={
                        "part_idx": mp_idx,
                        "doctor_idx": md_idx,
                        "sdate": sdate,
                        "edate": edate,
                    },
                    headers={
                        **self.headers,
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "X-Requested-With": "XMLHttpRequest",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning(f"[KBSMC] 월별 스케줄 실패 ({sdate}~{edate}, md_idx={md_idx}): {e}")
                continue

            schedule_list = data if isinstance(data, list) else data.get("data", data.get("list", []))
            if isinstance(schedule_list, dict):
                schedule_list = [schedule_list]

            for item in schedule_list:
                date_str = str(item.get("date", item.get("sche_date", item.get("sdate", "")))).strip()
                am_flag = str(item.get("am", item.get("jsAm", item.get("am_yn", "")))).strip()
                pm_flag = str(item.get("pm", item.get("jsPm", item.get("pm_yn", "")))).strip()

                if not date_str or len(date_str) < 10:
                    continue

                formatted_date = date_str[:10]
                try:
                    datetime.strptime(formatted_date, "%Y-%m-%d")
                except ValueError:
                    continue

                if am_flag and am_flag not in ("", "0", "N", "null", "None", "close"):
                    start, end = TIME_RANGES["morning"]
                    all_date_schedules.append({
                        "schedule_date": formatted_date,
                        "time_slot": "morning",
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                        "status": "진료",
                    })
                if pm_flag and pm_flag not in ("", "0", "N", "null", "None", "close"):
                    start, end = TIME_RANGES["afternoon"]
                    all_date_schedules.append({
                        "schedule_date": formatted_date,
                        "time_slot": "afternoon",
                        "start_time": start,
                        "end_time": end,
                        "location": "",
                        "status": "진료",
                    })

        return all_date_schedules

    async def _fetch_schedule_from_view(
        self, client: httpx.AsyncClient, md_idx: str, mp_idx: str
    ) -> list[dict]:
        """폴백: doctor view 페이지에서 스케줄 HTML 파싱"""
        try:
            resp = await client.get(
                f"{BASE_URL}/main/doctor/view.do",
                params={"md_idx": md_idx, "mp_idx": mp_idx},
            )
            resp.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # 캘린더/스케줄 테이블에서 AM/PM 파싱
        schedules = []
        # jsCalendar 패턴 또는 일반 테이블
        table = soup.select_one("table.schedule, table.tbl_schedule, .jsCalendar table, table")
        if not table:
            return []

        rows = table.select("tr")
        header_cells = rows[0].select("th, td") if rows else []
        header_texts = [c.get_text(strip=True) for c in header_cells]

        # 요일이 헤더에 있는지 확인
        day_in_header = any(d in "".join(header_texts) for d in ["월", "화", "수", "일"])

        if day_in_header:
            col_to_dow = {}
            for ci, text in enumerate(header_texts):
                for day_char, dow in DAY_MAP.items():
                    if day_char in text:
                        col_to_dow[ci] = dow
                        break

            for row in rows[1:]:
                cells = row.select("th, td")
                if not cells:
                    continue
                first_text = cells[0].get_text(strip=True)
                if "오전" in first_text or "AM" in first_text.upper():
                    slot = "morning"
                elif "오후" in first_text or "PM" in first_text.upper():
                    slot = "afternoon"
                else:
                    continue

                for ci, cell in enumerate(cells):
                    if ci not in col_to_dow:
                        continue
                    text = cell.get_text(strip=True)
                    has_schedule = bool(text) or cell.select("i, img, span.on, span.sche1")
                    if has_schedule and text not in ("", "-", "X", "x", "휴진"):
                        start, end = TIME_RANGES[slot]
                        schedules.append({
                            "day_of_week": col_to_dow[ci],
                            "time_slot": slot,
                            "start_time": start,
                            "end_time": end,
                            "location": "",
                        })

        return schedules

    # ─── 전체 크롤링 ───

    async def _fetch_all(self) -> list[dict]:
        """전체 진료과별 의료진 크롤링 후 캐시. 의사별 스케줄은 병렬 fetch."""
        import asyncio

        if self._cached_data is not None:
            return self._cached_data

        depts = await self._fetch_departments()
        all_doctors = {}

        async with httpx.AsyncClient(
            headers=self.headers, timeout=60, follow_redirects=True,
        ) as client:
            # 1단계: 모든 부서에서 의사 메타데이터 수집 (dedup)
            for dept in depts:
                docs = await self._fetch_dept_doctors(
                    client, dept["code"], dept["name"]
                )
                for doc in docs:
                    ext_id = doc["external_id"]
                    if ext_id in all_doctors:
                        existing = all_doctors[ext_id]
                        if doc["specialty"] and doc["specialty"] not in existing.get("specialty", ""):
                            existing["specialty"] = (
                                f"{existing['specialty']}, {doc['specialty']}"
                                if existing.get("specialty") else doc["specialty"]
                            )
                        continue
                    if "_mp_idx" not in doc or not doc.get("_mp_idx"):
                        doc["_mp_idx"] = dept["code"]
                    doc.setdefault("schedules", [])
                    doc.setdefault("date_schedules", [])
                    all_doctors[ext_id] = doc

            # 2단계: 강북삼성은 월별 캘린더형 병원이라 date_schedules만 저장한다.
            sem = asyncio.Semaphore(8)

            async def fetch_one(doc):
                md_idx = doc.get("_md_idx", "")
                if not md_idx:
                    return
                mp_idx = doc.get("_mp_idx", "")
                async with sem:
                    try:
                        date_sched = await self._fetch_monthly_schedule(client, md_idx, mp_idx)
                        doc["schedules"] = []
                        doc["date_schedules"] = date_sched
                    except Exception as e:
                        logger.warning(f"[KBSMC] {doc.get('name','')} 스케줄 실패: {e}")

            await asyncio.gather(*(fetch_one(d) for d in all_doctors.values()))

        result = list(all_doctors.values())
        logger.info(f"[KBSMC] 총 {len(result)}명")
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
            "date_schedules": [],
        }

        # 캐시가 이미 있으면 캐시에서 조회
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return self._to_schedule_dict(d)
            if staff_id.startswith("KBSMC-"):
                search_key = staff_id.split("-", 1)[-1]
                for d in self._cached_data:
                    if d["name"] == search_key or d.get("_md_idx") == search_key:
                        return self._to_schedule_dict(d)
            return empty

        # 개별 조회: external_id에서 md_idx, mp_idx 파싱
        # 형식: KBSMC-{md_idx}-{mp_idx} 또는 KBSMC-{md_idx}
        prefix = "KBSMC-"
        raw = staff_id.replace(prefix, "") if staff_id.startswith(prefix) else staff_id
        parts = raw.split("-", 1)
        md_idx = parts[0]
        mp_idx = parts[1] if len(parts) > 1 else ""

        # mp_idx가 없으면 profile_url에서 추출 시도
        if not mp_idx:
            m = re.search(r"mp_idx=(\d+)", staff_id)
            if m:
                mp_idx = m.group(1)

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            # mp_idx가 없으면 view 페이지에서 추출
            if not mp_idx:
                try:
                    resp = await client.get(
                        f"{BASE_URL}/main/doctor/view.do",
                        params={"md_idx": md_idx},
                    )
                    m = re.search(r"mp_idx[=:]\s*[\"']?(\d+)", resp.text)
                    if m:
                        mp_idx = m.group(1)
                except Exception:
                    pass
            mp_idx = mp_idx or "1"

            date_schedules = await self._fetch_monthly_schedule(client, md_idx, mp_idx)

            ext_id = f"KBSMC-{md_idx}-{mp_idx}"
            return {
                "staff_id": ext_id,
                "name": "",
                "department": "",
                "position": "",
                "specialty": "",
                "profile_url": f"{BASE_URL}/main/doctor/view.do?md_idx={md_idx}&mp_idx={mp_idx}",
                "notes": "",
                "schedules": [],
                "date_schedules": date_schedules,
            }

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
                position=d.get("position", ""),
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
