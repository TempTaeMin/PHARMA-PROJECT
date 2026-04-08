"""Playwright 범용 크롤러 엔진

모든 병원에 공통으로 사용하는 브라우저 기반 크롤러.
병원별 차이는 HospitalConfig(URL 패턴, 셀렉터)로 처리.

구조:
  PlaywrightEngine (공통 브라우저 관리)
    → HospitalConfig (병원별 URL/셀렉터 설정)
    → PlaywrightCrawler (BaseCrawler 구현체)
"""
import sys
import asyncio
import re
import logging
from datetime import datetime
from dataclasses import dataclass, field

# Windows asyncio 호환 패치
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright, Browser, Page

logger = logging.getLogger(__name__)

DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
TIME_SLOT_MAP = {"오전": "morning", "오후": "afternoon", "야간": "evening"}
TIME_RANGES = {"morning": ("09:00", "12:00"), "afternoon": ("13:00", "17:00"), "evening": ("18:00", "21:00")}


@dataclass
class HospitalConfig:
    """병원별 크롤링 설정 - URL만 바꾸면 새 병원 추가 가능"""
    code: str
    name: str

    # URL 패턴
    dept_list_url: str = ""                         # 진료과 목록 페이지
    doctor_list_url: str = ""                       # 의료진 목록 (진료과별)
    doctor_detail_url: str = ""                     # 의료진 상세 페이지
    doctor_schedule_url: str = ""                   # 의료진 진료시간표 (별도 페이지인 경우)

    # URL에서 변수 치환 패턴
    dept_param: str = "{dept_code}"                 # 진료과 코드 자리
    staff_param: str = "{staff_id}"                 # 의료진 ID 자리

    # CSS 셀렉터 (기본값 = 범용 패턴)
    staff_link_selector: str = "a[href*='staff'], a[href*='doctor'], a[href*='emp']"
    staff_id_pattern: str = r"(?:staffId|empNo|empId|DR_NO|doctorId)[=\/](\w+)"
    doctor_name_selector: str = "h3, h2, .name, .doctor-name, .staffName, [class*='name']"
    schedule_table_selector: str = "table"

    # 목록 페이지에서 이름 추출용 카드 셀렉터 (설정 시 개별 상세 페이지 방문 없이 이름 추출)
    card_selector: str = ""           # 의사 카드 컨테이너 (예: "li:has(a[href*='drEmpId'])")
    card_name_selector: str = ""      # 카드 안 이름 요소 (예: "[class*=name]")

    # 탭 클릭 텍스트 목록 (비어있으면 탭 클릭 건너뜀)
    tab_texts: list = field(default_factory=lambda: ["의료진 소개", "의료진소개"])

    # 진료과 목록 (사전 정의)
    departments: dict = field(default_factory=dict)

    # 대기 시간 (ms)
    wait_after_load: int = 2000


# ═══ 빅5 병원 설정 ═══

HOSPITAL_CONFIGS = {
    "AMC": HospitalConfig(
        code="AMC", name="서울아산병원",
        dept_list_url="https://www.amc.seoul.kr/asan/departments/deptListTypeA.do",
        doctor_list_url="https://www.amc.seoul.kr/asan/staff/base/staffBaseInfoList.do?searchHpCd={dept_code}",
        doctor_detail_url="https://www.amc.seoul.kr/asan/staff/base/staffBaseInfoDetail.do?drEmpId={staff_id}",
        staff_id_pattern=r"fnDrDetail\('([A-Za-z0-9+/=]{10,})'",
        staff_link_selector="a[onclick*='fnDrDetail']",
        card_selector="li:has(p.doctor_name)",
        card_name_selector="p.doctor_name",
        tab_texts=[],  # staffBaseInfoList 페이지는 탭 클릭 불필요 (GNB 오클릭 방지)
        wait_after_load=2000,
        departments={},  # 빈 값 → 첫 크롤링 시 dept_list_url에서 동적으로 로딩
    ),
    "SNUH": HospitalConfig(
        code="SNUH", name="서울대학교병원",
        doctor_list_url="https://www.snuh.org/medical/doctor/findDoctor.do?deptCd={dept_code}",
        doctor_detail_url="https://www.snuh.org/medical/doctor/doctorDetail.do?empNo={staff_id}",
        doctor_schedule_url="https://www.snuh.org/medical/doctor/doctorSchedule.do?empNo={staff_id}",
        staff_id_pattern=r"empNo[='\"](\w+)",
        departments={
            "GS": "외과", "IM": "내과", "OS": "정형외과", "NS": "신경외과",
            "OG": "산부인과", "PD": "소아청소년과", "DM": "피부과",
            "UR": "비뇨의학과", "EY": "안과", "EN": "이비인후과",
            "NR": "신경과", "PS": "정신건강의학과", "RM": "재활의학과",
            "CS": "흉부외과",
        },
    ),
    "SEVERANCE": HospitalConfig(
        code="SEVERANCE", name="세브란스병원",
        doctor_list_url="https://sev.severance.healthcare/sev/doctor/doctor.do?deptCd={dept_code}",
        doctor_detail_url="https://sev.severance.healthcare/sev/doctor/doctorDetail.do?siteId=sev&empId={staff_id}",
        staff_id_pattern=r"empId[='\"](\w+)",
        departments={
            "GI": "소화기내과", "CV": "심장내과", "PU": "호흡기내과",
            "HO": "혈액내과", "ED": "내분비내과",
            "GS": "외과", "NS": "신경외과", "OS": "정형외과",
            "OG": "산부인과", "PD": "소아청소년과", "NR": "신경과",
            "DM": "피부과", "UR": "비뇨의학과", "EY": "안과", "EN": "이비인후과",
        },
    ),
    "CMCSEOUL": HospitalConfig(
        code="CMCSEOUL", name="서울성모병원",
        doctor_list_url="https://www.cmcseoul.or.kr/page/doctor/search?deptCd={dept_code}",
        doctor_detail_url="https://www.cmcseoul.or.kr/page/doctor/{staff_id}",
        staff_id_pattern=r"/page/doctor/(\w+)",
        departments={
            "GI": "소화기내과", "CV": "순환기내과", "PU": "호흡기내과",
            "HO": "혈액내과", "ED": "내분비내과",
            "GS": "외과", "NS": "신경외과", "OS": "정형외과",
            "OG": "산부인과", "PD": "소아청소년과", "NR": "신경과",
            "DM": "피부과", "UR": "비뇨의학과", "EY": "안과", "EN": "이비인후과",
        },
    ),
}


class PlaywrightEngine:
    """Playwright 브라우저 관리 (싱글톤)"""

    _instance = None
    _browser: Browser = None

    @classmethod
    async def get_browser(cls) -> Browser:
        if cls._browser is None or not cls._browser.is_connected():
            pw = await async_playwright().start()
            cls._browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
            logger.info("Playwright 브라우저 시작")
        return cls._browser

    @classmethod
    async def new_page(cls) -> Page:
        browser = await cls.get_browser()
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ko-KR",
        )
        return await context.new_page()

    @classmethod
    async def close(cls):
        if cls._browser:
            await cls._browser.close()
            cls._browser = None


class PlaywrightCrawler:
    """Playwright 기반 범용 크롤러"""

    def __init__(self, config: HospitalConfig):
        self.config = config
        self.hospital_code = config.code
        self.hospital_name = config.name

    async def get_departments(self) -> list[dict]:
        if not self.config.departments and self.config.dept_list_url:
            self.config.departments = await self._discover_departments()
        return [{"code": k, "name": v} for k, v in self.config.departments.items()]

    async def _discover_departments(self) -> dict:
        """dept_list_url 페이지에서 진료과 코드를 동적으로 추출"""
        departments = {}
        if not self.config.dept_list_url:
            return departments

        page = await PlaywrightEngine.new_page()
        try:
            await page.goto(self.config.dept_list_url, wait_until="networkidle", timeout=20000)
            await page.wait_for_timeout(self.config.wait_after_load)

            # searchHpCd= 파라미터가 있는 링크에서 진료과 코드 + 이름 추출
            # (staffBaseInfoList.do 사이드바 또는 deptListTypeA.do 링크)
            links = await page.query_selector_all("a[href*='searchHpCd='], a[href*='/depts/'][href*='deptLink']")
            for link in links:
                href = await link.get_attribute("href") or ""
                code_match = re.search(r"searchHpCd=([A-Z0-9]+)", href) or re.search(r"/depts/([A-Z0-9]+)/K/deptLink", href)
                if not code_match:
                    continue
                code = code_match.group(1)
                name = (await link.inner_text()).strip().split("\n")[0].strip()
                if name and 2 <= len(name) <= 20 and code not in departments:
                    departments[code] = name

            logger.info(f"[{self.config.code}] 진료과 {len(departments)}개 동적 발견")
        except Exception as e:
            logger.error(f"[{self.config.code}] 진료과 목록 가져오기 실패: {e}")
        finally:
            await page.context.close()

        return departments

    async def crawl_doctor_list(self, department: str = None) -> list[dict]:
        """1차 경량 크롤링: 브라우저로 교수 목록 페이지 열고 이름/ID 추출"""
        all_doctors = []

        # 진료과 목록이 비어있으면 동적으로 가져오기
        if not self.config.departments and self.config.dept_list_url:
            self.config.departments = await self._discover_departments()
            if not self.config.departments:
                logger.warning(f"[{self.config.code}] 진료과 목록을 가져올 수 없습니다")
                return []

        targets = (
            {k: v for k, v in self.config.departments.items()
             if v == department or k == department}
            if department else self.config.departments
        )

        if not self.config.doctor_list_url:
            logger.warning(f"[{self.config.code}] doctor_list_url 미설정")
            return []

        page = await PlaywrightEngine.new_page()
        try:
            for dept_code, dept_name in targets.items():
                url = self.config.doctor_list_url.replace("{dept_code}", dept_code)
                try:
                    await page.goto(url, wait_until="networkidle", timeout=20000)
                    await page.wait_for_timeout(self.config.wait_after_load)

                    # 리다이렉트 감지: 예상 도메인 벗어나면 건너뜀
                    from urllib.parse import urlparse
                    expected_netloc = urlparse(self.config.doctor_list_url).netloc
                    current_netloc = urlparse(page.url).netloc
                    if expected_netloc and current_netloc != expected_netloc:
                        logger.warning(f"[{self.config.code}] {dept_name}({dept_code}): 리다이렉트 감지 → {page.url[:60]}, 건너뜀")
                        continue

                    # 탭 클릭 (tab_texts가 설정된 경우에만)
                    for tab_text in self.config.tab_texts:
                        try:
                            tab = await page.query_selector(f"text={tab_text}")
                            if tab:
                                await tab.click()
                                await page.wait_for_timeout(2000)
                                break
                        except:
                            pass

                    # 스크롤 다운으로 모든 교수 로딩 (lazy loading 대응)
                    for _ in range(5):
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(800)

                    content = await page.content()

                    # 방법 1: staffId 패턴으로 ID 추출
                    staff_ids = set(re.findall(self.config.staff_id_pattern, content))

                    # 방법 2: 링크에서 이름+ID 매핑
                    links = await page.query_selector_all(self.config.staff_link_selector)
                    name_map = {}
                    for link in links:
                        href = await link.get_attribute("href") or ""
                        onclick = await link.get_attribute("onclick") or ""
                        search_text = href + " " + onclick
                        id_match = re.search(self.config.staff_id_pattern, search_text)
                        if id_match:
                            name = (await link.inner_text()).strip().split("\n")[0].strip()
                            if name and 1 < len(name) < 20:
                                name_map[id_match.group(1)] = name

                    # 방법 3: 페이지 텍스트에서 직접 교수 정보 추출 (서울아산병원 새 구조)
                    if not staff_ids:
                        # "의료진소개 더보기" 또는 "진료예약하기" 버튼의 onclick에서 ID 추출
                        buttons = await page.query_selector_all("a, button")
                        for btn in buttons:
                            href = await btn.get_attribute("href") or ""
                            onclick = await btn.get_attribute("onclick") or ""
                            combined = href + " " + onclick
                            id_match = re.search(self.config.staff_id_pattern, combined)
                            if id_match:
                                staff_ids.add(id_match.group(1))

                    # 방법 4: card_selector + card_name_selector로 카드에서 직접 이름 추출
                    if self.config.card_selector and self.config.card_name_selector:
                        cards = await page.query_selector_all(self.config.card_selector)
                        for card in cards:
                            name_el = await card.query_selector(self.config.card_name_selector)
                            if not name_el:
                                continue
                            name = (await name_el.inner_text()).strip().split("\n")[0].strip()
                            if not name or not (1 < len(name) < 10):
                                continue
                            # 카드 안 모든 링크에서 staff_id 패턴 찾기 (href + onclick)
                            card_links = await card.query_selector_all("a")
                            for cl in card_links:
                                href = await cl.get_attribute("href") or ""
                                onclick = await cl.get_attribute("onclick") or ""
                                id_match = re.search(self.config.staff_id_pattern, href + " " + onclick)
                                if id_match:
                                    name_map[id_match.group(1)] = name
                                    break

                    # 결과 조합
                    skip_ids = {"search", "department", "doctor", "list", "view", "do", "K", "A", "B", "type"}
                    for sid in staff_ids:
                        if sid in skip_ids or len(sid) < 3:
                            continue
                        all_doctors.append({
                            "staff_id": sid,
                            "name": name_map.get(sid, ""),
                            "department": dept_name,
                        })

                    logger.info(f"[{self.config.code}] {dept_name}({dept_code}): {len(staff_ids)}명 발견 (누적 {len(all_doctors)}명)")

                except Exception as e:
                    logger.error(f"[{self.config.code}] {dept_name} 목록 크롤링 실패: {e}")

        finally:
            await page.context.close()

        return all_doctors

    async def crawl_doctor_schedule(self, staff_id: str) -> dict:
        """2차 상세 크롤링: 브라우저로 교수 상세 페이지 열고 진료시간표 추출"""
        result = {
            "staff_id": staff_id, "name": "", "department": "",
            "position": "", "specialty": "", "profile_url": "",
            "photo_url": "", "schedules": [],
        }

        page = await PlaywrightEngine.new_page()
        try:
            # 상세 페이지
            if self.config.doctor_detail_url:
                url = self.config.doctor_detail_url.replace("{staff_id}", staff_id)
                result["profile_url"] = url
                try:
                    await page.goto(url, wait_until="networkidle", timeout=15000)
                    await page.wait_for_timeout(self.config.wait_after_load)

                    # 이름 추출 - AMC는 og:title 우선 (h3가 "의료진" 섹션 헤더를 잡음)
                    if self.config.code == "AMC":
                        og = await page.query_selector("meta[property='og:title']")
                        if og:
                            content = await og.get_attribute("content")
                            if content:
                                result["name"] = content.split("|")[0].strip()

                    if not result["name"]:
                        for selector in self.config.doctor_name_selector.split(","):
                            elem = await page.query_selector(selector.strip())
                            if elem:
                                text = (await elem.inner_text()).strip()
                                if text and len(text) < 30 and text not in ("의료진", "진료과"):
                                    result["name"] = text.split("\n")[0].strip()
                                    break

                    # og:title 폴백 (비-AMC)
                    if not result["name"]:
                        og = await page.query_selector("meta[property='og:title']")
                        if og:
                            content = await og.get_attribute("content")
                            if content:
                                result["name"] = content.split("|")[0].split("-")[0].strip()

                    # 페이지 텍스트에서 전문분야 추출
                    text = await page.inner_text("body")
                    spec_match = re.search(r"(?:전문\s*분야|전문\s*진료|진료\s*분야)[:\s]*([^\n]{3,80})", text)
                    if spec_match:
                        result["specialty"] = spec_match.group(1).strip()

                except Exception as e:
                    logger.error(f"[{self.config.code}] {staff_id} 상세 크롤링 실패: {e}")

            # 진료시간표 페이지 (별도 URL이 있는 경우)
            schedule_url = self.config.doctor_schedule_url or self.config.doctor_detail_url
            if schedule_url and schedule_url != result.get("_last_url"):
                url = schedule_url.replace("{staff_id}", staff_id)
                try:
                    if url != result["profile_url"]:
                        await page.goto(url, wait_until="networkidle", timeout=15000)
                        await page.wait_for_timeout(self.config.wait_after_load)

                    if self.config.code == "AMC":
                        result["schedules"] = await self._extract_schedule_amc(page)
                    else:
                        result["schedules"] = await self._extract_schedule(page)

                except Exception as e:
                    logger.error(f"[{self.config.code}] {staff_id} 시간표 크롤링 실패: {e}")

        finally:
            await page.context.close()

        logger.info(f"[{self.config.code}] {result['name']}({staff_id}) - {len(result['schedules'])}개 일정")
        return result

    async def _extract_schedule_amc(self, page: Page) -> list[dict]:
        """AMC 진료정보표에서 진료시간 추출
        테이블 구조: 구분 | 질병/치료범위 | 예약방법 | 오전 | 오후
        오전/오후 셀에 "화,금" 형태로 요일이 들어있음"""
        schedules = []
        try:
            table = await page.query_selector("table.tableLayout")
            if not table:
                return schedules

            # thead에서 오전/오후 열 인덱스 파악
            headers = await table.query_selector_all("th")
            slot_col = {}  # {col_index: time_slot}
            for th in headers:
                text = (await th.inner_text()).strip()
                if text in TIME_SLOT_MAP:
                    slot_col[text] = TIME_SLOT_MAP[text]

            if not slot_col:
                return schedules

            # tbody 행에서 reservSchedule 셀 파싱
            rows = await table.query_selector_all("tbody tr")
            for row in rows:
                # reservSchedule 클래스를 가진 셀 찾기
                schedule_cells = await row.query_selector_all("td.reservSchedule")
                if not schedule_cells:
                    continue

                # schedule_cells 순서 = 오전, 오후 (thead 순서와 동일)
                slot_keys = list(slot_col.values())  # ["morning", "afternoon"]
                for i, cell in enumerate(schedule_cells):
                    if i >= len(slot_keys):
                        break
                    slot = slot_keys[i]
                    text = (await cell.inner_text()).strip()
                    if not text or text == "-":
                        continue
                    # "화,금" 또는 "월,화,수" 형태 파싱
                    for day_char in re.split(r"[,\s·]+", text):
                        day_char = day_char.strip()
                        dow = DAY_MAP.get(day_char)
                        if dow is not None:
                            start, end = TIME_RANGES.get(slot, ("", ""))
                            schedules.append({
                                "day_of_week": dow, "time_slot": slot,
                                "start_time": start, "end_time": end, "location": "",
                            })

        except Exception as e:
            logger.debug(f"AMC 진료정보표 파싱 실패: {e}")

        # 중복 제거
        seen = set()
        unique = []
        for s in schedules:
            key = (s["day_of_week"], s["time_slot"])
            if key not in seen:
                seen.add(key)
                unique.append(s)

        return unique

    async def _extract_schedule(self, page: Page) -> list[dict]:
        """페이지에서 진료시간표 추출 (테이블 + 텍스트 패턴)"""
        schedules = []

        # 방법 1: 테이블에서 추출
        tables = await page.query_selector_all(self.config.schedule_table_selector)
        for table in tables:
            try:
                rows = await table.query_selector_all("tr")
                if len(rows) < 2:
                    continue

                # 헤더에서 요일 찾기
                header_cells = await rows[0].query_selector_all("th, td")
                day_indices = {}
                for i, cell in enumerate(header_cells):
                    text = (await cell.inner_text()).strip()
                    if text in DAY_MAP:
                        day_indices[i] = DAY_MAP[text]

                if not day_indices:
                    continue

                # 데이터 행
                for row in rows[1:]:
                    cells = await row.query_selector_all("th, td")
                    if not cells:
                        continue
                    first_text = (await cells[0].inner_text()).strip()
                    slot = TIME_SLOT_MAP.get(first_text)
                    if not slot:
                        continue

                    for col_idx, dow in day_indices.items():
                        if col_idx < len(cells):
                            cell_text = (await cells[col_idx].inner_text()).strip()
                            cell_html = await cells[col_idx].inner_html()
                            has_clinic = bool(
                                re.search(r"[○●◎OV진료]|진료|예약", cell_text)
                                or "img" in cell_html
                                or "check" in cell_html.lower()
                                or "on" in (await cells[col_idx].get_attribute("class") or "").lower()
                            )
                            if has_clinic:
                                start, end = TIME_RANGES.get(slot, ("", ""))
                                schedules.append({
                                    "day_of_week": dow, "time_slot": slot,
                                    "start_time": start, "end_time": end, "location": "",
                                })
            except Exception as e:
                logger.debug(f"테이블 파싱 실패: {e}")

        # 방법 2: 텍스트 패턴으로 추출 (폴백)
        if not schedules:
            try:
                text = await page.inner_text("body")
                # "월(오전)" 패턴
                for m in re.findall(r"([월화수목금토일])\s*\(\s*(오전|오후|야간)\s*\)", text):
                    dow = DAY_MAP.get(m[0])
                    slot = TIME_SLOT_MAP.get(m[1])
                    if dow is not None and slot:
                        start, end = TIME_RANGES.get(slot, ("", ""))
                        schedules.append({
                            "day_of_week": dow, "time_slot": slot,
                            "start_time": start, "end_time": end, "location": "",
                        })
                # "월요일 오전" 패턴
                for m in re.findall(r"([월화수목금토일])요일?\s*(오전|오후)", text):
                    dow = DAY_MAP.get(m[0])
                    slot = TIME_SLOT_MAP.get(m[1])
                    if dow is not None and slot:
                        start, end = TIME_RANGES.get(slot, ("", ""))
                        schedules.append({
                            "day_of_week": dow, "time_slot": slot,
                            "start_time": start, "end_time": end, "location": "",
                        })
            except Exception as e:
                logger.debug(f"텍스트 파싱 실패: {e}")

        return schedules

    async def crawl_doctors(self, department: str = None):
        """전체 크롤링 - 이름 중심 (목록 페이지에서만 추출, 개별 상세 페이지 방문 없음)"""
        from app.schemas.schemas import CrawlResult, CrawledDoctor

        doc_list = await self.crawl_doctor_list(department)
        all_doctors = [
            CrawledDoctor(
                name=d.get("name", ""),
                department=d.get("department", ""),
                position="",
                specialty="",
                profile_url=self.config.doctor_detail_url.replace("{staff_id}", d["staff_id"]) if self.config.doctor_detail_url else "",
                photo_url="",
                external_id=d["staff_id"],
                schedules=[],
            )
            for d in doc_list
        ]

        return CrawlResult(
            hospital_code=self.hospital_code,
            hospital_name=self.hospital_name,
            status="success" if all_doctors else "failed",
            doctors=all_doctors,
            crawled_at=datetime.utcnow(),
        )
