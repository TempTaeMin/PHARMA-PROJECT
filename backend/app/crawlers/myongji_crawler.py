"""명지병원 크롤러

정적 HTML 기반 크롤러. (Nanum 계열 사이트, KBSMC 와 URL 구조 비슷하나 AJAX 스케줄 없음)

페이지 구조:
  진료과 목록: GET /main/part/list.do
    → <div class="deptinfo">진료과명</div> + <a href="../doctor/list.do?mp_idx=N">
  의사 목록 + 주간 스케줄: GET /main/doctor/list.do?mp_idx={mp_idx}
    → <li> 카드 안에 d_info(이름/전문분야) + d_sche(주간 테이블)
    → <td><span class="sche_icon sche1"></span></td> 형태로 요일/시간대 표시
  의사 상세: GET /main/doctor/view.do?md_idx=X&doctor_code=Y&part_code=Z
    → 학력/경력/논문/스케줄 모두 포함

스케줄 아이콘:
  sche1 → 진료 (외래) ✓ 포함
  sche2 → 클리닉 ✓ 포함
  sche3 → 센터 ✓ 포함
  sche9 → 기타 ✗ 제외 (검사/행사/비외래)

external_id 형식: MYONGJI-{md_idx}-{doctor_code}
  예: MYONGJI-9-EN005 (이재혁, 내분비내과)
  part_code 는 doctor_code 앞 2글자와 같아 별도 저장하지 않음
"""
import re
import logging
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://www.mjh.or.kr"

TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00")}

DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}

# 외래 진료로 포함할 sche 클래스
CLINIC_SCHE_CLASSES = {"sche1", "sche2", "sche3"}
# 제외 (기타: 검사/행사/비외래)
EXCLUDE_SCHE_CLASSES = {"sche9"}

# 진료/외래 키워드 (셀 텍스트가 있을 때 판정)
CLINIC_KEYWORDS = ("진료", "외래", "클리닉", "센터", "검진", "격주", "순환")
EXCLUDE_KEYWORDS = (
    "수술", "내시경", "시술", "초음파", "조영", "CT", "MRI", "PET",
    "회진", "실험", "연구", "검사",
)
INACTIVE_KEYWORDS = ("휴진", "휴무", "공휴일", "부재", "출장", "학회")


def _classify_cell(cell) -> bool:
    """주간 스케줄 셀을 외래 진료로 포함할지 판정"""
    # 1) sche_icon 클래스 확인
    include = False
    for span in cell.select("span.sche_icon"):
        classes = span.get("class", [])
        for c in classes:
            if c in EXCLUDE_SCHE_CLASSES:
                return False
            if c in CLINIC_SCHE_CLASSES:
                include = True

    # 2) 텍스트 키워드 확인 (아이콘 없이 텍스트만 있는 경우)
    text = cell.get_text(" ", strip=True)
    if text:
        for kw in INACTIVE_KEYWORDS:
            if kw in text:
                return False
        for kw in EXCLUDE_KEYWORDS:
            if kw in text:
                return False
        if not include:
            for kw in CLINIC_KEYWORDS:
                if kw in text:
                    include = True
                    break

    return include


class MyongjiCrawler:
    """명지병원 크롤러

    출처: https://www.mjh.or.kr/
    """

    def __init__(self):
        self.hospital_code = "MYONGJI"
        self.hospital_name = "명지병원"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/main/main.do",
        }
        self._cached_data = None
        self._cached_depts = None

    # ─── 진료과 목록 ───

    async def _fetch_departments(self) -> list[dict]:
        """진료과 목록 (/main/part/list.do HTML 파싱)

        구조:
          <div class="medipart_list"><ul><li>
            <div class="deptinfo" ...>진료과명</div>
            <div class="deptlink"><a href="../doctor/list.do?mp_idx=N">의료진</a></div>
          </li></ul></div>
        """
        if self._cached_depts is not None:
            return self._cached_depts

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(f"{BASE_URL}/main/part/list.do")
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"[MYONGJI] 진료과 목록 실패: {e}")
                self._cached_depts = []
                return []

        soup = BeautifulSoup(resp.text, "html.parser")
        depts: list[dict] = []
        seen: set[str] = set()

        for li in soup.select(".medipart_list li"):
            info = li.select_one(".deptinfo")
            if not info:
                continue
            name = info.get_text(strip=True)
            if not name:
                continue

            # doctor/list.do?mp_idx=N 링크에서 코드 추출
            code = ""
            for a in li.select("a[href*='doctor/list.do']"):
                m = re.search(r"mp_idx=(\d+)", a.get("href", ""))
                if m:
                    code = m.group(1)
                    break
            if not code or code in seen:
                continue
            seen.add(code)
            depts.append({"code": code, "name": name})

        logger.info(f"[MYONGJI] 진료과 {len(depts)}개")
        self._cached_depts = depts
        return depts

    # ─── 진료과별 의사 목록 + 주간 스케줄 ───

    def _parse_doctor_card(
        self, card, dept_name: str
    ) -> dict | None:
        """단일 li.dr_list > li 카드에서 의사 정보 파싱"""
        # 이름 추출: div.name (텍스트에 span.part 가 섞여있으므로 분리)
        name_el = card.select_one("div.name")
        if not name_el:
            return None

        # span.part 텍스트는 제거
        part_el = name_el.select_one("span.part")
        if part_el:
            part_text = part_el.get_text(strip=True)
            part_el.extract()
        else:
            part_text = ""
        name = name_el.get_text(strip=True)

        if not name:
            return None
        # 일반진료, 검진예약 등 특수 엔트리 제외
        if not re.fullmatch(r"[가-힣]{2,5}", name):
            return None

        # 상세 링크에서 md_idx / doctor_code / part_code 추출
        md_idx = ""
        doctor_code = ""
        part_code = ""
        for a in card.select("a[href*='doctor/view.do']"):
            href = a.get("href", "")
            m_md = re.search(r"md_idx=(\d+)", href)
            m_dc = re.search(r"doctor_code=([A-Za-z0-9]+)", href)
            m_pc = re.search(r"part_code=([A-Za-z0-9]+)", href)
            if m_md:
                md_idx = m_md.group(1)
            if m_dc:
                doctor_code = m_dc.group(1)
            if m_pc:
                part_code = m_pc.group(1)
            if md_idx and doctor_code:
                break

        if not md_idx:
            return None

        # part_code 폴백: doctor_code 앞 글자
        if not part_code and doctor_code:
            m = re.match(r"([A-Za-z]+)", doctor_code)
            if m:
                part_code = m.group(1)

        # 전문분야
        specialty = ""
        clinic_el = card.select_one(".clinic")
        if clinic_el:
            text = clinic_el.get_text(" ", strip=True)
            # "전문진료분야" 라벨 제거
            text = re.sub(r"^전문\s*진료\s*분야\s*", "", text)
            specialty = text.strip()

        # 주간 스케줄 파싱
        schedules = self._parse_schedule_table(card)

        # external_id: MYONGJI-{md_idx}-{doctor_code}  (슬래시 금지)
        if doctor_code:
            ext_id = f"MYONGJI-{md_idx}-{doctor_code}"
        else:
            ext_id = f"MYONGJI-{md_idx}"

        profile_url = (
            f"{BASE_URL}/main/doctor/view.do?md_idx={md_idx}"
            f"&doctor_code={doctor_code}&mp_idx=&part_code={part_code}"
        )

        return {
            "staff_id": ext_id,
            "external_id": ext_id,
            "name": name,
            "department": dept_name or part_text,
            "position": "",
            "specialty": specialty,
            "profile_url": profile_url,
            "notes": "",
            "schedules": schedules,
            "date_schedules": [],
            "_md_idx": md_idx,
            "_doctor_code": doctor_code,
            "_part_code": part_code,
        }

    def _parse_schedule_table(self, container) -> list[dict]:
        """d_sche > table 에서 주간 스케줄 파싱

        table 구조:
          thead: <th> / <th>월~토</th>
          tbody:
            <tr><th>오전</th><td>...</td>×6</tr>
            <tr><th>오후</th><td>...</td>×6</tr>
        """
        table = container.select_one("div.d_sche table") or container.select_one("table")
        if not table:
            return []

        # 헤더에서 요일 순서 추출
        thead = table.select_one("thead")
        day_cols: list[int | None] = []
        if thead:
            for th in thead.select("th"):
                txt = th.get_text(strip=True)
                day_cols.append(DAY_MAP.get(txt))
        if not any(d is not None for d in day_cols):
            # 기본값: 월화수목금토
            day_cols = [None, 0, 1, 2, 3, 4, 5]

        schedules: list[dict] = []
        seen_keys: set[tuple] = set()

        for row in table.select("tbody tr"):
            row_header = row.select_one("th")
            if not row_header:
                continue
            slot_text = row_header.get_text(strip=True)
            if "오전" in slot_text:
                slot = "morning"
            elif "오후" in slot_text:
                slot = "afternoon"
            else:
                continue

            cells = row.select("td")
            # colspan 로 된 주석 행 건너뛰기 (◆ 클리닉 안내)
            if len(cells) == 1 and cells[0].get("colspan"):
                continue

            # day_cols 를 기준으로 셀과 매핑
            # thead 가 "시간/월/화/수/목/금/토" 형태면 day_cols[0]=None, day_cols[1]=월...
            # tbody tr 는 <th>(시간)</th><td>월</td><td>화</td>... 이므로 day_cols[1:] 에 맞춤
            dow_sequence = [d for d in day_cols if d is not None]

            for i, cell in enumerate(cells):
                if i >= len(dow_sequence):
                    break
                dow = dow_sequence[i]
                if dow is None or dow > 5:
                    continue
                if not _classify_cell(cell):
                    continue
                start, end = TIME_RANGES[slot]
                key = (dow, slot)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                schedules.append({
                    "day_of_week": dow,
                    "time_slot": slot,
                    "start_time": start,
                    "end_time": end,
                    "location": "",
                })

        return schedules

    async def _fetch_dept_doctors(
        self, client: httpx.AsyncClient, dept_code: str, dept_name: str
    ) -> list[dict]:
        """진료과별 의사 카드 + 스케줄 파싱"""
        try:
            resp = await client.get(
                f"{BASE_URL}/main/doctor/list.do",
                params={"mp_idx": dept_code},
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[MYONGJI] {dept_name} 의사 목록 실패: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        doctors: list[dict] = []
        # ul.dr_list > li 가 의사 카드
        for card in soup.select("ul.dr_list > li"):
            doc = self._parse_doctor_card(card, dept_name)
            if doc:
                doctors.append(doc)

        logger.info(f"[MYONGJI] {dept_name}: {len(doctors)}명")
        return doctors

    # ─── 개별 교수 상세 조회 ───

    async def _fetch_doctor_detail(
        self, client: httpx.AsyncClient, md_idx: str, doctor_code: str, part_code: str
    ) -> dict:
        """view.do 에서 상세 정보 + 스케줄 파싱

        반환: name, department, specialty, schedules
        """
        empty = {"name": "", "department": "", "specialty": "", "schedules": []}
        if not md_idx or not doctor_code:
            return empty
        if not part_code:
            m = re.match(r"([A-Za-z]+)", doctor_code)
            part_code = m.group(1) if m else ""

        url = f"{BASE_URL}/main/doctor/view.do"
        params = {
            "md_idx": md_idx,
            "doctor_code": doctor_code,
            "mp_idx": "",
            "part_code": part_code,
        }
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[MYONGJI] 상세 조회 실패 (md_idx={md_idx}): {e}")
            return empty

        soup = BeautifulSoup(resp.text, "html.parser")
        profile = soup.select_one(".medipart_profile") or soup

        # 이름/진료과/전문분야
        name = ""
        department = ""
        specialty = ""

        name_el = profile.select_one("p.name")
        if name_el:
            name = name_el.get_text(strip=True)
        part_el = profile.select_one("p.part")
        if part_el:
            department = part_el.get_text(strip=True)
        clinic_el = profile.select_one("p.clinic")
        if clinic_el:
            text = clinic_el.get_text(" ", strip=True)
            text = re.sub(r"^전문\s*진료\s*분야\s*", "", text)
            specialty = text.strip()

        # 스케줄
        schedules = self._parse_schedule_table(profile)

        return {
            "name": name,
            "department": department,
            "specialty": specialty,
            "schedules": schedules,
        }

    # ─── 전체 크롤링 ───

    async def _fetch_all(self) -> list[dict]:
        """전체 진료과별 의료진 크롤링 후 캐시"""
        if self._cached_data is not None:
            return self._cached_data

        depts = await self._fetch_departments()
        all_doctors: dict[str, dict] = {}

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
                        continue
                    all_doctors[ext_id] = doc

        result = list(all_doctors.values())
        logger.info(f"[MYONGJI] 총 {len(result)}명")
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
                "position": d.get("position", ""),
                "specialty": d.get("specialty", ""),
                "profile_url": d.get("profile_url", ""),
                "notes": d.get("notes", ""),
            }
            for d in data
        ]

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """개별 교수 진료시간표 조회 — 해당 교수 1명만 네트워크 요청"""
        empty = {
            "staff_id": staff_id, "name": "", "department": "", "position": "",
            "specialty": "", "profile_url": "", "notes": "", "schedules": [],
            "date_schedules": [],
        }

        # 동일 인스턴스 캐시
        if self._cached_data is not None:
            for d in self._cached_data:
                if d["staff_id"] == staff_id or d["external_id"] == staff_id:
                    return self._to_schedule_dict(d)
            return empty

        # external_id 파싱: MYONGJI-{md_idx}-{doctor_code}
        prefix = "MYONGJI-"
        raw = staff_id[len(prefix):] if staff_id.startswith(prefix) else staff_id
        parts = raw.split("-", 1)
        md_idx = parts[0] if parts else ""
        doctor_code = parts[1] if len(parts) > 1 else ""

        if not md_idx or not doctor_code:
            logger.warning(f"[MYONGJI] staff_id 파싱 실패: {staff_id}")
            return empty

        # part_code 추출 (doctor_code 앞 글자)
        m = re.match(r"([A-Za-z]+)", doctor_code)
        part_code = m.group(1) if m else ""

        async with httpx.AsyncClient(
            headers=self.headers, timeout=30, follow_redirects=True,
        ) as client:
            detail = await self._fetch_doctor_detail(
                client, md_idx, doctor_code, part_code
            )

        profile_url = (
            f"{BASE_URL}/main/doctor/view.do?md_idx={md_idx}"
            f"&doctor_code={doctor_code}&mp_idx=&part_code={part_code}"
        )

        return {
            "staff_id": staff_id,
            "name": detail.get("name", ""),
            "department": detail.get("department", ""),
            "position": "",
            "specialty": detail.get("specialty", ""),
            "profile_url": profile_url,
            "notes": "",
            "schedules": detail.get("schedules", []),
            "date_schedules": [],
        }

    @staticmethod
    def _to_schedule_dict(d: dict) -> dict:
        return {
            "staff_id": d["staff_id"],
            "name": d["name"],
            "department": d["department"],
            "position": d.get("position", ""),
            "specialty": d.get("specialty", ""),
            "profile_url": d.get("profile_url", ""),
            "notes": d.get("notes", ""),
            "schedules": d.get("schedules", []),
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
